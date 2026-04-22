from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Self

import aiohttp

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import RetriableError, WordstatError

logger = logging.getLogger("wordstat_mcp")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TIME_TO_REFILL_PATTERN = re.compile(
    r"time to refill:\s*(?P<seconds>\d+(?:\.\d+)?)\s*seconds",
    re.IGNORECASE,
)


class WordstatClient:
    """Asynchronous HTTP client for Yandex Wordstat API v2."""

    def __init__(
        self, settings: WordstatSettings, session: aiohttp.ClientSession | None = None
    ) -> None:
        self.settings = settings
        self._external_session = session
        self._session = session

    async def __aenter__(self) -> Self:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.settings.timeout_seconds)
            self._session = aiohttp.ClientSession(
                base_url=self.settings.api_url, timeout=timeout
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session is not None and self._external_session is None:
            await self._session.close()
            self._session = None

    @staticmethod
    def _extract_retry_after(headers: Mapping[str, str], body: str) -> float | None:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                logger.debug("Retry-After header not numeric: %s", retry_after)

        rate_limit_reset = headers.get("x-ratelimit-reset")
        if rate_limit_reset:
            try:
                return max(float(rate_limit_reset), 0.0)
            except ValueError:
                logger.debug(
                    "x-ratelimit-reset header not numeric: %s", rate_limit_reset
                )

        if match := TIME_TO_REFILL_PATTERN.search(body):
            return float(match.group("seconds"))
        return None

    @staticmethod
    def _format_error_message(
        status: int,
        body: str,
        headers: Mapping[str, str],
    ) -> str:
        message = f"HTTP {status}"

        request_id = headers.get("x-request-id")
        trace_id = headers.get("x-server-trace-id")
        rate_limit_remaining = headers.get("x-ratelimit-remaining")
        rate_limit_reset = headers.get("x-ratelimit-reset")

        details = []
        if request_id:
            details.append(f"x-request-id={request_id}")
        if trace_id:
            details.append(f"x-server-trace-id={trace_id}")
        if rate_limit_remaining is not None:
            details.append(f"x-ratelimit-remaining={rate_limit_remaining}")
        if rate_limit_reset is not None:
            details.append(f"x-ratelimit-reset={rate_limit_reset}")

        if details:
            message = f"{message} ({', '.join(details)})"
        if body:
            message = f"{message}: {body}"
        return message

    async def _do_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise WordstatError("Client session is not initialized.")

        logger.debug("Wordstat request url=%s payload=%s", endpoint, payload)

        async with self._session.post(
            endpoint, headers=self.settings.headers, json=payload
        ) as response:
            body = await response.text()
            logger.debug(
                "Wordstat response url=%s status=%s headers=%s body=%s",
                endpoint,
                response.status,
                dict(response.headers),
                body,
            )

            if response.status in RETRYABLE_STATUS_CODES:
                raise RetriableError(
                    self._format_error_message(response.status, body, response.headers),
                    retry_after=self._extract_retry_after(response.headers, body),
                )
            if response.status >= 400:
                raise WordstatError(
                    self._format_error_message(response.status, body, response.headers)
                )
            if not body:
                return {}

            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise WordstatError(
                    f"Invalid JSON response from Wordstat API: {body}"
                ) from exc

    def _retry_delay(self, attempt: int, exc: BaseException) -> float:
        if isinstance(exc, RetriableError) and exc.retry_after is not None:
            return min(exc.retry_after, self.settings.max_backoff_seconds)

        delay = self.settings.backoff_seconds * (2 ** (attempt - 1))
        return min(delay, self.settings.max_backoff_seconds)

    async def request_json(
        self, endpoint: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform POST request with retry policy for rate limits and 5xx errors."""
        max_attempts = self.settings.max_attempts
        request_payload = dict(payload or {})
        request_payload.setdefault("folderId", self.settings.folder_id)

        for attempt in range(1, max_attempts + 1):
            try:
                return await self._do_post(endpoint=endpoint, payload=request_payload)
            except RetriableError as exc:
                if attempt >= max_attempts:
                    raise WordstatError(str(exc)) from exc

                delay = self._retry_delay(attempt, exc)
                logger.warning(
                    "Retryable Wordstat error on attempt=%s/%s delay=%ss error=%s",
                    attempt,
                    max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt >= max_attempts:
                    raise WordstatError(str(exc)) from exc

                delay = self._retry_delay(attempt, exc)
                logger.warning(
                    "Transient transport error on attempt=%s/%s delay=%ss error=%s",
                    attempt,
                    max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        raise WordstatError("Unexpected retry loop termination.")
