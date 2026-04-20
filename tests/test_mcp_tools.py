from __future__ import annotations

import inspect
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import WordstatError
from wordstat_mcp.operators import WORDSTAT_OPERATORS_AGENT_GUIDE
from wordstat_mcp.tools import (
    build_wordstat_phrase,
    get_dynamics,
    get_regions_distribution,
    get_regions_tree,
    get_top,
    load_regions_tree_cache,
    mcp,
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
async def test_get_dynamics_rejects_unsupported_wordstat_operators(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    with pytest.raises(Exception, match="getDynamics supports only"):
        await get_dynamics(
            phrases=['"купить авто"'],
            fromDate="2026-01-01T00:00:00Z",
        )

    assert patched_tool_dependencies == []


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


def test_tool_function_parameters_keep_raw_api_names() -> None:
    assert "numPhrases" in inspect.signature(get_top).parameters
    assert "pageSize" in inspect.signature(get_top).parameters
    assert "fromDate" in inspect.signature(get_dynamics).parameters
    assert "toDate" in inspect.signature(get_dynamics).parameters
    assert "pageSize" in inspect.signature(get_regions_distribution).parameters


@pytest.mark.anyio
async def test_build_wordstat_phrase_tool_returns_phrase_payload() -> None:
    response = await build_wordstat_phrase(
        natural_query="Покажи топ по точной фразе купить авто",
        target_method="getTop",
        base_phrase="купить авто",
        exact_word_count=True,
    )

    assert response["phrase"] == '"купить авто"'
    assert response["target_method"] == "getTop"
    assert response["resource_uri"] == "wordstat://operators/agent-guide"
    assert response["prompt_name"] == "wordstat_phrase_builder"


@pytest.mark.anyio
async def test_wordstat_operator_resource_and_prompt_are_registered() -> None:
    resources = await mcp.list_resources()
    prompts = await mcp.list_prompts()

    assert any(str(resource.uri) == "wordstat://operators/agent-guide" for resource in resources)
    assert any(prompt.name == "wordstat_phrase_builder" for prompt in prompts)

    contents = await mcp.read_resource("wordstat://operators/agent-guide")
    assert "".join(item.content for item in contents) == WORDSTAT_OPERATORS_AGENT_GUIDE

    prompt = await mcp.get_prompt(
        "wordstat_phrase_builder",
        {
            "user_request": "Покажи динамику работы из дома",
            "target_method": "getDynamics",
        },
    )
    rendered = prompt.messages[0].content.text
    assert "build_wordstat_phrase" in rendered
    assert "Покажи динамику работы из дома" in rendered


@pytest.mark.anyio
async def test_public_mcp_tool_names_match_documented_api_names() -> None:
    tools = {tool.name for tool in await mcp.list_tools()}

    assert {
        "build_wordstat_phrase",
        "getTop",
        "getDynamics",
        "getRegionsDistribution",
        "getRegionsTree",
        "update_regions_tree",
        "wordstat_env_health",
    } <= tools
    assert "get_top" not in tools
    assert "get_dynamics" not in tools


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
