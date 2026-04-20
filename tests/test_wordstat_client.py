from __future__ import annotations

import json
from typing import Any

import aiohttp
import pytest

from wordstat_mcp.exceptions import RetriableError, WordstatError
from wordstat_mcp.models import (
    GetDynamicsRequest,
    GetRegionsDistributionRequest,
    GetTopRequest,
)
from wordstat_mcp.tools import WordstatClient

from tests.helpers import FakeResponse, FakeSession


@pytest.mark.anyio
async def test_client_context_manager_creates_and_closes_internal_session(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings,
) -> None:
    created: dict[str, Any] = {}
    fake_session = FakeSession()

    def fake_client_session(
        *, base_url: str, timeout: aiohttp.ClientTimeout
    ) -> FakeSession:
        created["base_url"] = base_url
        created["timeout"] = timeout.total
        return fake_session

    monkeypatch.setattr(
        "wordstat_mcp.tools.aiohttp.ClientSession",
        fake_client_session,
    )

    client = WordstatClient(wordstat_settings)
    async with client as session_client:
        assert session_client is client
        assert client._session is fake_session

    assert created["base_url"] == str(wordstat_settings.api_url)
    assert created["timeout"] == wordstat_settings.timeout_seconds
    assert fake_session.closed is True


@pytest.mark.anyio
async def test_client_context_manager_does_not_close_external_session(
    wordstat_settings,
) -> None:
    fake_session = FakeSession()
    client = WordstatClient(wordstat_settings, session=fake_session)

    async with client:
        pass

    assert fake_session.closed is False


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({"Retry-After": "2.5"}, "", 2.5),
        ({"x-ratelimit-reset": "7"}, "", 7.0),
        ({}, "Quota exceeded. Time to refill: 3.5 seconds", 3.5),
        ({}, "No refill hint", None),
    ],
)
def test_extract_retry_after(
    headers: dict[str, str], body: str, expected: float | None
) -> None:
    assert WordstatClient._extract_retry_after(headers, body) == expected


def test_format_error_message_includes_diagnostics() -> None:
    message = WordstatClient._format_error_message(
        429,
        "quota exceeded",
        {
            "x-request-id": "req-id",
            "x-server-trace-id": "trace-id",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "5",
        },
    )

    assert "HTTP 429" in message
    assert "x-request-id=req-id" in message
    assert "x-server-trace-id=trace-id" in message
    assert "quota exceeded" in message


@pytest.mark.anyio
async def test_do_post_requires_initialized_session(wordstat_settings) -> None:
    client = WordstatClient(wordstat_settings)

    with pytest.raises(WordstatError, match="not initialized"):
        await client._do_post("topRequests", {"phrase": "python"})


@pytest.mark.anyio
async def test_do_post_returns_empty_dict_for_empty_body(wordstat_settings) -> None:
    session = FakeSession(FakeResponse(status=200, body=""))
    client = WordstatClient(wordstat_settings, session=session)

    async with client:
        payload = await client._do_post("topRequests", {"phrase": "python"})

    assert payload == {}
    assert session.calls[0]["url"] == "topRequests"
    assert session.calls[0]["headers"] == wordstat_settings.headers
    assert session.calls[0]["json"] == {"phrase": "python"}


@pytest.mark.anyio
async def test_do_post_returns_json_payload(wordstat_settings) -> None:
    session = FakeSession(FakeResponse(status=200, body=json.dumps({"ok": True})))
    client = WordstatClient(wordstat_settings, session=session)

    async with client:
        payload = await client._do_post("topRequests", {"phrase": "python"})

    assert payload == {"ok": True}


@pytest.mark.anyio
async def test_do_post_raises_retryable_error(wordstat_settings) -> None:
    session = FakeSession(
        FakeResponse(
            status=429,
            body="quota exceeded",
            headers={"Retry-After": "4"},
        )
    )
    client = WordstatClient(wordstat_settings, session=session)

    async with client:
        with pytest.raises(RetriableError) as exc_info:
            await client._do_post("topRequests", {"phrase": "python"})

    assert exc_info.value.retry_after == 4.0


@pytest.mark.anyio
async def test_do_post_raises_for_invalid_json(wordstat_settings) -> None:
    session = FakeSession(FakeResponse(status=200, body="{broken json"))
    client = WordstatClient(wordstat_settings, session=session)

    async with client:
        with pytest.raises(WordstatError, match="Invalid JSON response"):
            await client._do_post("topRequests", {"phrase": "python"})


@pytest.mark.anyio
async def test_do_post_raises_for_non_retryable_status(wordstat_settings) -> None:
    session = FakeSession(
        FakeResponse(status=400, body="bad request", headers={"x-request-id": "req-id"})
    )
    client = WordstatClient(wordstat_settings, session=session)

    async with client:
        with pytest.raises(WordstatError, match="HTTP 400"):
            await client._do_post("topRequests", {"phrase": "python"})


def test_retry_delay_uses_retry_after_and_caps_backoff(wordstat_settings) -> None:
    client = WordstatClient(wordstat_settings)

    assert (
        client._retry_delay(1, RetriableError("wait", retry_after=8.0))
        == wordstat_settings.max_backoff_seconds
    )
    assert client._retry_delay(3, RuntimeError("transport")) == 2.0


@pytest.mark.anyio
async def test_request_json_retries_on_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings,
) -> None:
    client = WordstatClient(wordstat_settings)
    calls = {"count": 0, "delay": None}

    async def fake_do_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RetriableError("temporary", retry_after=0.2)
        assert payload["folderId"] == "folder-1"
        return {"ok": True}

    async def fake_sleep(delay: float) -> None:
        calls["delay"] = delay

    monkeypatch.setattr(client, "_do_post", fake_do_post)
    monkeypatch.setattr("wordstat_mcp.tools.asyncio.sleep", fake_sleep)

    response = await client.request_json("topRequests", {"phrase": "python"})

    assert response == {"ok": True}
    assert calls == {"count": 3, "delay": 0.2}


@pytest.mark.anyio
async def test_request_json_retries_on_transport_error(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings,
) -> None:
    client = WordstatClient(wordstat_settings)
    calls = {"count": 0}

    async def fake_do_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise aiohttp.ClientError("network")
        return {"ok": True}

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client, "_do_post", fake_do_post)
    monkeypatch.setattr("wordstat_mcp.tools.asyncio.sleep", fake_sleep)

    assert await client.request_json("topRequests", {"phrase": "python"}) == {
        "ok": True
    }
    assert calls["count"] == 2


@pytest.mark.anyio
async def test_request_json_fails_after_retry_limit(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings,
) -> None:
    settings = wordstat_settings.model_copy(update={"max_attempts": 2})
    client = WordstatClient(settings)

    async def fake_do_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RetriableError("still failing", retry_after=0.0)

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client, "_do_post", fake_do_post)
    monkeypatch.setattr("wordstat_mcp.tools.asyncio.sleep", fake_sleep)

    with pytest.raises(WordstatError, match="still failing"):
        await client.request_json("topRequests", {"phrase": "python"})


@pytest.mark.anyio
async def test_request_json_keeps_explicit_folder_id(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings,
) -> None:
    client = WordstatClient(wordstat_settings)

    async def fake_do_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(client, "_do_post", fake_do_post)

    payload = await client.request_json(
        "topRequests",
        {"folderId": "override", "phrase": "python"},
    )

    assert payload["folderId"] == "override"


