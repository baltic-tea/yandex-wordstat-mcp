from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import WordstatError
from wordstat_mcp.tools import (
    get_dynamics,
    get_regions_distribution,
    get_regions_tree,
    get_top,
    load_regions_tree_cache,
    save_regions_tree_cache,
    update_regions_tree,
    wordstat_env_health,
)


@dataclass
class FakeWordstatClient:
    settings: WordstatSettings
    response: dict[str, Any] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __aenter__(self) -> FakeWordstatClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def request_json(
        self, endpoint: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = payload or {}
        self.calls.append((endpoint, payload.copy()))
        return self.response or {"ok": True}


@pytest.fixture
def patched_tool_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> list[FakeWordstatClient]:
    clients: list[FakeWordstatClient] = []

    monkeypatch.setattr(
        "wordstat_mcp.tools.wordstat_settings",
        lambda: wordstat_settings,
    )

    def client_factory(settings: WordstatSettings) -> FakeWordstatClient:
        client = FakeWordstatClient(settings)
        clients.append(client)
        return client

    monkeypatch.setattr("wordstat_mcp.tools.WordstatClient", client_factory)
    return clients


@pytest.fixture
def workspace_tmp_path() -> Path:
    path = Path.cwd() / ".test_tmp" / uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.anyio
async def test_get_top_posts_normalized_request_payload(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    patched_tool_dependencies

    response = await get_top(
        phrases=["python"],
        numPhrases=10,
        regions=[213, "2"],  # type: ignore[list-item]
        devices=None,
    )

    client = patched_tool_dependencies[0]
    assert response["items"] == [{"phrase": "python", "top": {"ok": True}}]
    assert client.calls == [
        (
            "topRequests",
            {
                "phrase": "python",
                "regions": ["213", "2"],
                "devices": [],
                "numPhrases": 10,
            },
        )
    ]


@pytest.mark.anyio
async def test_get_dynamics_posts_rfc3339_payload(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    await get_dynamics(
        phrases=["python"],
        fromDate="2026-01-01T03:00:00+03:00",
        toDate="2026-01-31T00:00:00Z",
        devices=["DEVICE_PHONE"],
    )

    client = patched_tool_dependencies[0]
    assert client.calls == [
        (
            "dynamics",
            {
                "phrase": "python",
                "regions": [],
                "devices": ["DEVICE_PHONE"],
                "period": "PERIOD_MONTHLY",
                "fromDate": "2026-01-01T00:00:00Z",
                "toDate": "2026-01-31T00:00:00Z",
            },
        )
    ]


@pytest.mark.anyio
async def test_get_regions_distribution_posts_phrase_payload(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    await get_regions_distribution(
        phrases=["python"],
        region="REGION_CITIES",
        devices=["DEVICE_DESKTOP"],
    )

    client = patched_tool_dependencies[0]
    assert client.calls == [
        (
            "regions",
            {
                "phrase": "python",
                "region": "REGION_CITIES",
                "devices": ["DEVICE_DESKTOP"],
            },
        )
    ]


@pytest.mark.anyio
async def test_wordstat_env_health_returns_ok_status(
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> None:
    monkeypatch.setattr(
        "wordstat_mcp.tools.wordstat_settings",
        lambda: wordstat_settings,
    )

    response = await wordstat_env_health()

    assert response["status"] == "ok"
    assert response["apiUrl"] == wordstat_settings.api_url


def test_regions_tree_cache_round_trip(workspace_tmp_path: Path) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    payload = {"regions": [{"id": "213", "label": "Moscow"}]}

    assert load_regions_tree_cache(cache_path) is None
    assert save_regions_tree_cache(payload, cache_path) == payload
    assert load_regions_tree_cache(cache_path) == payload


def test_regions_tree_cache_reports_invalid_json(workspace_tmp_path: Path) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    cache_path.parent.mkdir()
    cache_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(WordstatError, match="Invalid regions tree cache"):
        load_regions_tree_cache(cache_path)


@pytest.mark.anyio
async def test_get_regions_tree_uses_cache_without_api(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_payload = {"regions": [{"id": "cached", "label": "Cached"}]}
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    save_regions_tree_cache(cached_payload, cache_path)
    monkeypatch.chdir(workspace_tmp_path)

    def fail_settings() -> None:
        pytest.fail("settings should not be loaded when cache exists")

    monkeypatch.setattr("wordstat_mcp.tools.wordstat_settings", fail_settings)

    assert await get_regions_tree() == cached_payload


@pytest.mark.anyio
async def test_get_regions_tree_fetches_and_saves_missing_cache(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> None:
    payload = {"regions": [{"id": "fresh", "label": "Fresh"}]}
    clients: list[FakeWordstatClient] = []
    monkeypatch.chdir(workspace_tmp_path)
    monkeypatch.setattr(
        "wordstat_mcp.tools.wordstat_settings",
        lambda: wordstat_settings,
    )

    def client_factory(settings: WordstatSettings) -> FakeWordstatClient:
        client = FakeWordstatClient(settings=settings, response=payload)
        clients.append(client)
        return client

    monkeypatch.setattr("wordstat_mcp.tools.WordstatClient", client_factory)

    assert await get_regions_tree() == payload
    assert clients[0].calls == [("getRegionsTree", {})]
    assert (
        load_regions_tree_cache(workspace_tmp_path / ".saved" / "regions_tree.json")
        == payload
    )


@pytest.mark.anyio
async def test_update_regions_tree_refreshes_existing_cache(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> None:
    old_payload = {"regions": [{"id": "old", "label": "Old"}]}
    fresh_payload = {"regions": [{"id": "fresh", "label": "Fresh"}]}
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    save_regions_tree_cache(old_payload, cache_path)
    monkeypatch.chdir(workspace_tmp_path)
    monkeypatch.setattr(
        "wordstat_mcp.tools.wordstat_settings",
        lambda: wordstat_settings,
    )

    def client_factory(settings: WordstatSettings) -> FakeWordstatClient:
        return FakeWordstatClient(settings=settings, response=fresh_payload)

    monkeypatch.setattr("wordstat_mcp.tools.WordstatClient", client_factory)

    assert await update_regions_tree() == fresh_payload
    assert load_regions_tree_cache(cache_path) == fresh_payload
