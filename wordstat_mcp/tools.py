"Async MCP tools for Yandex Wordstat API v2."

from __future__ import annotations
from collections.abc import Mapping
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing_extensions import Self

import asyncio
import json
import logging
import math
import re
from typing import Any, Awaitable, Callable

import aiohttp
from mcp.types import ToolAnnotations
from pydantic import TypeAdapter, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import (
    RetriableError,
    WordstatConfigError,
    WordstatError,
)
from wordstat_mcp.models import (
    PhraseModel,
    GetDynamicsRequest,
    GetRegionsDistributionRequest,
    GetTopRequest,
    WordstatDevices,
    WordstatPeriods,
    WordstatRegionModes,
)
from wordstat_mcp.operators import (
    OPERATORS_GUIDE_RESOURCE_URI,
    OPERATORS_PROMPT_NAME,
    WORDSTAT_OPERATORS_AGENT_GUIDE,
    WordstatPhraseBuilder,
    WordstatSearchMethod,
    build_wordstat_phrase_payload,
    render_wordstat_phrase_builder_prompt,
    validate_dynamics_phrase,
)

logger = logging.getLogger("wordstat_mcp")

MAX_PHRASES_PER_CALL = 100
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TIME_TO_REFILL_PATTERN = re.compile(
    r"time to refill:\s*(?P<seconds>\d+(?:\.\d+)?)\s*seconds",
    re.IGNORECASE,
)
DATETIME_ADAPTER = TypeAdapter(datetime)
REGIONS_TREE_CACHE_PATH = Path(".saved") / "regions_tree.json"


@lru_cache(maxsize=1)
def wordstat_settings() -> WordstatSettings:
    return WordstatSettings()  # type: ignore[call-arg]


def tool_annotations(title: str) -> ToolAnnotations:
    """Build common read-only MCP tool annotations."""

    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


mcp = FastMCP(name="Yandex Wordstat MCP Server")


def _to_tool_error(exc: Exception, *, operation: str) -> ToolError:
    """Convert domain exception into MCP ``ToolError``.

    Args:
        exc: Original exception raised during tool execution.
        operation: Human-readable operation name for diagnostics.

    Returns:
        ToolError: Normalized error for MCP client.
    """

    return ToolError(f"{operation} failed: {exc}")


def _clean_phrases(phrases: list[str]) -> list[str]:
    """Validate and normalize phrase list.

    Args:
        phrases: Raw phrase values provided by caller.

    Returns:
        list[str]: Stripped non-empty phrases.
    """
    cleaned = []
    for phrase in phrases:
        try:
            validated_phrase = PhraseModel(phrase=phrase).phrase
            cleaned.append(validated_phrase)
        except ValidationError as e:
            logger.info(f"Skipping invalid phrase: {phrase}. Error: {e}")
    return cleaned


def _validate_dynamics_phrases(phrases: list[str]) -> None:
    """Validate Wordstat operator usage for the dynamics API."""

    for phrase in phrases:
        validate_dynamics_phrase(phrase)


def load_regions_tree_cache(
    cache_path: Path = REGIONS_TREE_CACHE_PATH,
) -> dict[str, Any] | None:
    """Load cached regions tree from disk when present."""
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise WordstatError(
            f"Invalid regions tree cache at {cache_path}: {exc}"
        ) from exc


def save_regions_tree_cache(
    payload: dict[str, Any],
    cache_path: Path = REGIONS_TREE_CACHE_PATH,
) -> dict[str, Any]:
    """Persist regions tree cache and return payload."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file, ensure_ascii=False, indent=2)
            cache_file.write("\n")
    except OSError as exc:
        raise WordstatError(
            f"Could not write regions tree cache to {cache_path}: {exc}"
        ) from exc
    return payload


def split_phrases(
    phrases: list[str], chunk_size: int = MAX_PHRASES_PER_CALL
) -> list[list[str]]:
    """Split phrase list into chunks of up to ``chunk_size``."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0.")
    return [phrases[i : i + chunk_size] for i in range(0, len(phrases), chunk_size)]


def paginate(items: list[Any], page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Paginate list-like data for MCP tool responses."""
    if page < 1:
        raise ValueError("page must be >= 1.")
    if page_size < 1:
        raise ValueError("page_size must be >= 1.")

    total = len(items)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "hasNextPage": end < total,
        "hasPreviousPage": page > 1,
        "items": items[start:end],
    }


def default_from_date(period: str) -> datetime:
    today = datetime.now()
    match period:
        case "PERIOD_MONTHLY":
            return today - timedelta(days=365)
        case "PERIOD_WEEKLY":
            return today - timedelta(days=90)
        case "PERIOD_DAILY":
            return today - timedelta(days=30)
        case _:
            raise ValueError(f"Unsupported period: {period}")


def parse_datetime(value: str | datetime) -> datetime:
    """Parse datetime-like tool input for typed request models."""

    if isinstance(value, datetime):
        return value
    return DATETIME_ADAPTER.validate_python(value)


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
        self, endpoint: str, payload: dict[str, Any] = {}
    ) -> dict[str, Any]:
        """Perform POST request with retry policy for rate limits and 5xx errors."""
        max_attempts = self.settings.max_attempts
        payload.setdefault("folderId", self.settings.folder_id)

        for attempt in range(1, max_attempts + 1):
            try:
                return await self._do_post(endpoint=endpoint, payload=payload)
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


async def _fetch_many(
    phrases: list[str],
    worker: Callable[[str], Awaitable[dict[str, Any]]],
    *,
    page: int,
    page_size: int,
    max_concurrency: int,
) -> dict[str, Any]:
    """Fetch many phrase-level responses with bounded concurrency.

    Args:
        phrases: Validated phrase list.
        worker: Async worker called per phrase.
        page: 1-based response page.
        page_size: Items per page in aggregated response.
        max_concurrency: Maximum in-flight worker calls.

    Returns:
        dict[str, Any]: Paginated response payload.
    """

    semaphore = asyncio.Semaphore(max_concurrency)
    indexed_results: list[dict[str, Any]] = []

    async def run_worker(phrase: str) -> dict[str, Any]:
        async with semaphore:
            return await worker(phrase)

    for chunk in split_phrases(phrases, MAX_PHRASES_PER_CALL):
        chunk_results = await asyncio.gather(*(run_worker(phrase) for phrase in chunk))
        indexed_results.extend(chunk_results)

    return paginate(indexed_results, page=page, page_size=page_size)


@mcp.resource(
    OPERATORS_GUIDE_RESOURCE_URI,
    name="wordstat_operators_agent_guide",
    title="Wordstat Operators Agent Guide",
    description=(
        "Operator-selection rules for building Yandex Wordstat `phrase` values. "
        "Agents should read this before converting natural-language requests "
        "into Wordstat phrases."
    ),
    mime_type="text/markdown",
)
def wordstat_operators_agent_guide() -> str:
    """Return Wordstat operator guidance for MCP clients."""

    return WORDSTAT_OPERATORS_AGENT_GUIDE


@mcp.prompt(
    name=OPERATORS_PROMPT_NAME,
    title="Build a Yandex Wordstat Phrase",
    description=(
        "Preset prompt that instructs an agent how to convert a natural-language "
        "request into a Wordstat `phrase` while respecting operator limits."
    ),
)
def wordstat_phrase_builder(
    user_request: str,
    target_method: WordstatSearchMethod = "getTop",
) -> str:
    """Prepare an agent to build a valid Wordstat phrase."""

    return render_wordstat_phrase_builder_prompt(user_request, target_method)


@mcp.tool(
    name="build_wordstat_phrase",
    description=(
        "Build and validate a Yandex Wordstat `phrase` from a natural-language "
        "request and optional explicit intent hints. Use this before "
        "`getTop`, `getDynamics`, or `getRegionsDistribution` when a user asks in "
        "natural language. Reads the same rules exposed by the "
        f"`{OPERATORS_PROMPT_NAME}` prompt and `{OPERATORS_GUIDE_RESOURCE_URI}` "
        "resource. For getDynamics, returns only phrases compatible with the `+` "
        "operator restriction."
    ),
    annotations=tool_annotations("Build Wordstat Phrase"),
)
async def build_wordstat_phrase(
    natural_query: str,
    target_method: WordstatSearchMethod,
    base_phrase: str | None = None,
    exact_word_count: bool = False,
    fixed_word_order: bool = False,
    alternatives: list[str] | None = None,
    fixed_forms: list[str] | None = None,
    required_stop_words: list[str] | None = None,
) -> dict[str, Any]:
    """Build a valid Wordstat phrase with warnings and explanation."""

    try:
        request = WordstatPhraseBuilder(
            natural_query=natural_query,
            target_method=target_method,
            base_phrase=base_phrase,
            exact_word_count=exact_word_count,
            fixed_word_order=fixed_word_order,
            alternatives=alternatives or [],
            fixed_forms=fixed_forms or [],
            required_stop_words=required_stop_words or [],
        )
        return build_wordstat_phrase_payload(request)
    except (ValueError, ValidationError) as exc:
        raise _to_tool_error(exc, operation="build_wordstat_phrase") from exc


@mcp.tool(
    name="getTop",
    description=(
        "Find top popular queries containing one or more input phrases and related "
        "queries for the last 30 days. Use this when the user wants popular search "
        "variations, related keywords, or phrase expansion ideas. When the user "
        "describes the phrase in natural language, call `build_wordstat_phrase` "
        "first or apply the `wordstat_phrase_builder` prompt/resource guidance."
    ),
    annotations=tool_annotations("Top Queries"),
)
async def get_top(
    phrases: list[str],
    numPhrases: int = 50,
    regions: list[int] | None = None,
    devices: list[WordstatDevices] | None = None,
    page: int = 1,
    pageSize: int = 50,
) -> dict[str, Any]:
    """Get top and associated phrases for one or many input phrases."""
    try:
        cleaned_phrases = _clean_phrases(phrases)
        settings = wordstat_settings()

        async with WordstatClient(settings) as client:

            async def worker(phrase: str) -> dict[str, Any]:
                request = GetTopRequest(
                    phrase=phrase,
                    numPhrases=numPhrases,
                    regions=[str(region) for region in regions or []],
                    devices=devices or [],
                )
                return {
                    "phrase": phrase,
                    "top": await client.request_json(
                        "topRequests", request.to_payload()
                    ),
                }

            return await _fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
    except (ValueError, WordstatError) as exc:
        raise _to_tool_error(exc, operation="getTop") from exc


@mcp.tool(
    name="getDynamics",
    description=(
        "The frequency of searches containing a specific keyword or phrase "
        "over a given period, aggregated by month, week, or day."
        "Use this when the user wants time-series popularity, trend changes, "
        "or historical demand within a selected period and date range. Wordstat "
        "dynamics supports only the `+` operator; this tool rejects phrases with "
        "`!`, quotes, `[]`, `()`, or `|`. Use `build_wordstat_phrase` first for "
        "natural-language requests."
    ),
    annotations=tool_annotations("Query Demand Dynamics"),
)
async def get_dynamics(
    phrases: list[str],
    period: WordstatPeriods = "PERIOD_MONTHLY",
    fromDate: str | datetime | None = None,
    toDate: datetime | str | None = None,
    regions: list[int] | None = None,
    devices: list[WordstatDevices] | None = None,
    page: int = 1,
    pageSize: int = 50,
) -> dict[str, Any]:
    """Get query demand dynamics for one or many phrases."""

    from_date = parse_datetime(fromDate or default_from_date(period))
    to_date = parse_datetime(toDate) if toDate is not None else None

    try:
        cleaned_phrases = _clean_phrases(phrases)
        _validate_dynamics_phrases(cleaned_phrases)
        settings = wordstat_settings()

        async with WordstatClient(settings) as client:

            async def worker(phrase: str) -> dict[str, Any]:
                request = GetDynamicsRequest(
                    phrase=phrase,
                    period=period,
                    fromDate=from_date,
                    toDate=to_date,
                    regions=[str(region) for region in regions or []],
                    devices=devices or [],
                )
                return {
                    "phrase": phrase,
                    "dynamics": await client.request_json(
                        "dynamics", request.to_payload()
                    ),
                }

            return await _fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
    except (ValueError, WordstatError) as exc:
        raise _to_tool_error(exc, operation="getDynamics") from exc


@mcp.tool(
    name="getRegionsDistribution",
    description=(
        "Return the distribution of the number of search queries containing "
        "the given keyword or phrase globally by region for the last 30 days."
        "Use this when the user wants to compare demand by regions or cities, or "
        "understand geographic concentration of a query. When the user describes "
        "the phrase in natural language, call `build_wordstat_phrase` first or "
        "apply the `wordstat_phrase_builder` prompt/resource guidance."
    ),
    annotations=tool_annotations("Regional Distribution"),
)
async def get_regions_distribution(
    phrases: list[str],
    region: WordstatRegionModes = "REGION_ALL",
    devices: list[WordstatDevices] | None = None,
    page: int = 1,
    pageSize: int = 50,
) -> dict[str, Any]:
    """Get region distribution for one or many phrases."""
    try:
        cleaned_phrases = _clean_phrases(phrases)
        settings = wordstat_settings()

        async with WordstatClient(settings) as client:

            async def worker(phrase: str) -> dict[str, Any]:
                request = GetRegionsDistributionRequest(
                    phrase=phrase, region=region, devices=devices
                )
                return {
                    "phrase": phrase,
                    "distribution": await client.request_json(
                        "regions", request.to_payload()
                    ),
                }

            return await _fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
    except (ValueError, WordstatError) as exc:
        raise _to_tool_error(exc, operation="getRegionsDistribution") from exc


@mcp.tool(
    name="getRegionsTree",
    description=(
        "Return a hierarchical tree of Wordstat-supported regions."
        "Use this before other tools when region identifiers are needed."
    ),
    annotations=tool_annotations("Regions Tree"),
)
async def get_regions_tree() -> dict[str, Any]:
    """Get full tree of supported regions."""
    try:
        cached_payload = load_regions_tree_cache()
        if cached_payload is not None:
            return cached_payload

        settings = wordstat_settings()
        async with WordstatClient(settings) as client:
            payload = await client.request_json("getRegionsTree")
            return save_regions_tree_cache(payload)
    except (ValueError, WordstatError) as e:
        raise _to_tool_error(e, operation="getRegionsTree") from e


@mcp.tool(
    name="update_regions_tree",
    description=(
        "Refresh the local Wordstat regions tree cache from the API and save it to local disk."
        "Use this when the user suspects that region data is outdated or after a change."
    ),
    annotations=tool_annotations("Update Wordstat Regions Tree Cache"),
)
async def update_regions_tree() -> dict[str, Any]:
    """Refresh cached tree of supported regions from Wordstat API."""
    try:
        settings = wordstat_settings()
        async with WordstatClient(settings) as client:
            payload = await client.request_json("getRegionsTree")
            return save_regions_tree_cache(payload)
    except (ValueError, WordstatError) as e:
        raise _to_tool_error(e, operation="update_regions_tree") from e


@mcp.tool(
    name="wordstat_env_health",
    description="Check server health and configuration.",
    annotations=tool_annotations("Wordstat Environment Health"),
)
async def wordstat_env_health() -> dict[str, Any]:
    """Return server health snapshot without external API call.

    Returns:
        dict[str, Any]: Health status and redacted runtime configuration.
    """

    try:
        settings = wordstat_settings()
        return {
            "status": "ok",
            "apiUrl": settings.api_url,
            "timeoutSeconds": settings.timeout_seconds,
            "maxAttempts": settings.max_attempts,
            "maxConcurrency": settings.max_concurrency,
        }
    except WordstatConfigError as e:
        return {"status": "error", "message": str(e)}
