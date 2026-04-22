from __future__ import annotations

import inspect
import json
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import WordstatError
from wordstat_mcp.helpers import (
    build_regions_lookup,
    find_region_matches,
    load_regions_tree_cache,
    normalize_region_name,
    save_regions_tree_cache,
)
from wordstat_mcp.operators import WORDSTAT_OPERATORS_AGENT_GUIDE
from wordstat_mcp.tools import (
    build_wordstat_phrase,
    compare_query_demand_by_region,
    find_keyword_queries,
    find_regions,
    get_query_demand_trends,
    get_region_index,
    get_dynamics,
    get_regions_distribution,
    get_regions_tree,
    get_top,
    mcp,
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
def workspace_tmp_path() -> Iterator[Path]:
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
async def test_get_top_returns_warnings_for_skipped_invalid_phrases(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    response = await get_top(phrases=["python", "   "], numPhrases=10)

    client = patched_tool_dependencies[0]
    assert response["items"] == [{"phrase": "python", "top": {"ok": True}}]
    assert "Skipped invalid phrase" in response["warnings"][0]
    assert client.calls == [
        (
            "topRequests",
            {
                "phrase": "python",
                "regions": [],
                "devices": [],
                "numPhrases": 10,
            },
        )
    ]


@pytest.mark.anyio
async def test_get_top_rejects_when_all_phrases_are_invalid(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    with pytest.raises(Exception, match="No valid phrases provided"):
        await get_top(phrases=["   "])

    assert patched_tool_dependencies == []


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
                "fromDate": "2025-12-31T21:00:00Z",
                "toDate": "2026-01-31T23:59:59.999999Z",
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


@pytest.mark.anyio
async def test_ai_first_aliases_delegate_to_api_tools(
    patched_tool_dependencies: list[FakeWordstatClient],
) -> None:
    await find_keyword_queries(phrases=["python"], numPhrases=5)
    await get_query_demand_trends(
        phrases=["python"], fromDate="2026-01-01T00:00:00Z"
    )
    await compare_query_demand_by_region(phrases=["python"], region="REGION_CITIES")

    assert [client.calls[0][0] for client in patched_tool_dependencies] == [
        "topRequests",
        "dynamics",
        "regions",
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
    assert "message" not in response
    assert "next_action" not in response
    assert "explanation" not in response


@pytest.mark.anyio
async def test_build_wordstat_phrase_tool_keeps_operator_warnings_internal() -> None:
    response = await build_wordstat_phrase(
        natural_query="exact dynamics phrase",
        target_method="getDynamics",
        base_phrase='"foo bar"',
        exact_word_count=True,
    )

    assert response["phrase"] == "foo bar"
    assert response["warnings"] == [
        "DYNAMICS_OPERATOR_LIMIT",
        "DYNAMICS_OPERATORS_STRIPPED",
    ]
    assert "getDynamics supports only" not in json.dumps(response)


@pytest.mark.anyio
async def test_wordstat_operator_resource_and_prompt_are_registered() -> None:
    resources = await mcp.list_resources()
    prompts = await mcp.list_prompts()

    assert any(str(resource.uri) == "wordstat://operators/agent-guide" for resource in resources)
    assert any(prompt.name == "wordstat_phrase_builder" for prompt in prompts)

    resource = await mcp.read_resource("wordstat://operators/agent-guide")
    assert (
        "".join(item.content for item in resource.contents)
        == WORDSTAT_OPERATORS_AGENT_GUIDE
    )

    prompt = await mcp.render_prompt(
        "wordstat_phrase_builder",
        {
            "user_request": "Покажи динамику работы из дома",
            "target_method": "getDynamics",
        },
    )
    rendered = prompt.messages[0].content.text
    assert "build_wordstat_phrase" in rendered
    assert "find_regions" in rendered
    assert "explain that" not in rendered.lower()
    assert "keep operator" in rendered.lower()

    guide = WORDSTAT_OPERATORS_AGENT_GUIDE
    assert "Warning Codes" in guide
    assert "DYNAMICS_OPERATOR_LIMIT" in guide
    assert "Sending phrase" not in guide
    assert "Покажи динамику работы из дома" in rendered


@pytest.mark.anyio
async def test_public_mcp_tool_names_match_documented_api_names() -> None:
    tools = {tool.name for tool in await mcp.list_tools()}

    assert {
        "build_wordstat_phrase",
        "compare_query_demand_by_region",
        "find_keyword_queries",
        "find_regions",
        "getTop",
        "getDynamics",
        "getRegionsDistribution",
        "getRegionsTree",
        "get_query_demand_trends",
        "get_region_index",
        "update_regions_tree",
        "wordstat_env_health",
    } <= tools
    assert "get_top" not in tools
    assert "get_dynamics" not in tools


@pytest.mark.anyio
async def test_public_mcp_tool_open_world_hints_match_side_effects() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    build_annotations = tools["build_wordstat_phrase"].annotations
    assert build_annotations is not None
    assert build_annotations.openWorldHint is False
    health_annotations = tools["wordstat_env_health"].annotations
    assert health_annotations is not None
    assert health_annotations.openWorldHint is False

    for name in {
        "compare_query_demand_by_region",
        "find_keyword_queries",
        "find_regions",
        "getTop",
        "getDynamics",
        "getRegionsDistribution",
        "getRegionsTree",
        "get_query_demand_trends",
        "get_region_index",
        "update_regions_tree",
    }:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.openWorldHint is True


@pytest.mark.anyio
async def test_public_mcp_tool_descriptions_include_wordstat_api_methods() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert (
        "<api>method=Wordstat.GetTop; endpoint=topRequests</api>"
        in (tools["getTop"].description or "")
    )
    assert (
        "<api>method=Wordstat.GetDynamics; endpoint=dynamics</api>"
        in (tools["getDynamics"].description or "")
    )
    assert (
        "<api>method=Wordstat.GetRegionsDistribution; endpoint=regions</api>"
        in (tools["getRegionsDistribution"].description or "")
    )
    assert (
        "<api>method=Wordstat.GetRegionsTree; endpoint=getRegionsTree</api>"
        in (tools["getRegionsTree"].description or "")
    )
    assert (
        "<api>method=Wordstat.GetTop; endpoint=topRequests</api>"
        in (tools["find_keyword_queries"].description or "")
    )
    assert (
        "<api>method=Wordstat.GetDynamics; endpoint=dynamics</api>"
        in (tools["get_query_demand_trends"].description or "")
    )
    health_description = tools["wordstat_env_health"].description or ""
    assert "Use only for troubleshooting" in health_description
    assert "does not call the external Wordstat API" in health_description


@pytest.mark.anyio
async def test_public_mcp_api_tools_have_structured_output_schemas() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    expected_item_fields = {
        "compare_query_demand_by_region": "distribution",
        "find_keyword_queries": "top",
        "getTop": "top",
        "getDynamics": "dynamics",
        "getRegionsDistribution": "distribution",
        "get_query_demand_trends": "dynamics",
    }

    for tool_name, item_field in expected_item_fields.items():
        schema = tools[tool_name].to_mcp_tool().outputSchema
        assert schema is not None
        assert schema["type"] == "object"
        assert {
            "page",
            "pageSize",
            "total",
            "totalPages",
            "hasNextPage",
            "hasPreviousPage",
            "items",
            "message",
            "next_action",
        } <= set(schema["properties"])
        item_schema = schema["properties"]["items"]["items"]
        assert {"phrase", item_field} <= set(item_schema["properties"])


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
    payload = {
        "regions": [
            {"id": "213", "label": "Moscow"},
            {"id": 216, "name": "Зеленоград"},
        ]
    }
    lookup = {
        "by_name": {"moscow": ["213"], "зеленоград": ["216"]},
        "by_id": {
            "213": {"name": "Moscow", "path": ["Moscow"]},
            "216": {"name": "Зеленоград", "path": ["Зеленоград"]},
        },
    }

    assert load_regions_tree_cache(cache_path) is None
    assert save_regions_tree_cache(payload, cache_path) == lookup
    assert load_regions_tree_cache(cache_path) == lookup


def test_build_regions_lookup_recurses_tree_and_lowercases_names() -> None:
    payload = {
        "regions": [
            {
                "id": "1",
                "name": "Россия",
                "children": [
                    {"id": "216", "name": "Зеленоград"},
                    {"id": "20674", "label": "Троицк"},
                ],
            }
        ]
    }

    assert build_regions_lookup(payload) == {
        "by_name": {
            "россия": ["1"],
            "зеленоград": ["216"],
            "троицк": ["20674"],
        },
        "by_id": {
            "1": {"name": "Россия", "path": ["Россия"]},
            "216": {"name": "Зеленоград", "path": ["Россия", "Зеленоград"]},
            "20674": {"name": "Троицк", "path": ["Россия", "Троицк"]},
        },
    }


def test_build_regions_lookup_keeps_first_id_for_duplicate_names() -> None:
    payload = {
        "regions": [
            {"id": "1", "name": "Троицк"},
            {"id": "2", "name": "Троицк"},
        ]
    }

    index = build_regions_lookup(payload)

    assert index["by_name"]["троицк"] == ["1", "2"]
    assert index["by_id"]["1"] == {"name": "Троицк", "path": ["Троицк"]}
    assert index["by_id"]["2"] == {"name": "Троицк", "path": ["Троицк"]}


def test_normalize_region_name_collapses_spaces_and_casefolds() -> None:
    assert normalize_region_name("  МОСКВА   И область  ") == "москва и область"


def test_build_regions_lookup_adds_yo_fallback_key() -> None:
    payload = {"regions": [{"id": "10", "name": "Орёл"}]}

    index = build_regions_lookup(payload)

    assert index["by_name"]["орёл"] == ["10"]
    assert index["by_name"]["орел"] == ["10"]


def test_find_region_matches_ranks_name_matches_before_path_matches() -> None:
    index = {
        "by_name": {"москва": ["1"]},
        "by_id": {
            "1": {"name": "Москва", "path": ["Россия", "Москва"]},
            "2": {"name": "Новая Москва", "path": ["Россия", "Новая Москва"]},
            "3": {
                "name": "Пушкино",
                "path": ["Россия", "Московская область", "Пушкино"],
            },
        },
    }

    matches = find_region_matches(index, "моск")

    assert [(match["id"], match["matchType"]) for match in matches] == [
        ("1", "prefix"),
        ("2", "contains_name"),
        ("3", "contains_path"),
    ]


def test_find_region_matches_uses_yo_fallback_for_exact_lookup() -> None:
    index = build_regions_lookup({"regions": [{"id": "10", "name": "Орёл"}]})

    assert find_region_matches(index, "орел")[0]["matchType"] == "exact"


@pytest.mark.anyio
async def test_find_regions_uses_cached_index_and_returns_duplicate_names(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    save_regions_tree_cache(
        {
            "regions": [
                {"id": "1", "name": "Троицк"},
                {"id": "2", "name": "Троицк"},
                {"id": "216", "name": "Зеленоград"},
            ]
        },
        cache_path,
    )
    monkeypatch.chdir(workspace_tmp_path)

    def fail_settings() -> None:
        pytest.fail("settings should not be loaded when cache exists")

    monkeypatch.setattr("wordstat_mcp.tools.wordstat_settings", fail_settings)

    response = await find_regions("троицк")

    assert response["total"] == 2
    assert [match["id"] for match in response["matches"]] == ["1", "2"]
    assert all(match["matchType"] == "exact" for match in response["matches"])


@pytest.mark.anyio
async def test_get_region_index_alias_returns_cached_index(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    save_regions_tree_cache(
        {"regions": [{"id": "216", "name": "Зеленоград"}]}, cache_path
    )
    monkeypatch.chdir(workspace_tmp_path)

    response = await get_region_index()

    assert response["by_name"]["зеленоград"] == ["216"]


def test_regions_tree_cache_loads_legacy_tree_as_index(workspace_tmp_path: Path) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    cache_path.parent.mkdir()
    cache_path.write_text(
        json.dumps(
            {
                "regions": [
                    {"id": "216", "name": "Зеленоград"},
                    {"id": "20674", "name": "Троицк"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert load_regions_tree_cache(cache_path) == {
        "by_name": {
            "зеленоград": ["216"],
            "троицк": ["20674"],
        },
        "by_id": {
            "216": {"name": "Зеленоград", "path": ["Зеленоград"]},
            "20674": {"name": "Троицк", "path": ["Троицк"]},
        },
    }


def test_regions_tree_cache_loads_legacy_flat_lookup_as_index(
    workspace_tmp_path: Path,
) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    cache_path.parent.mkdir()
    cache_path.write_text(
        json.dumps({"зеленоград": "216", "троицк": "20674"}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_regions_tree_cache(cache_path) == {
        "by_name": {
            "зеленоград": ["216"],
            "троицк": ["20674"],
        },
        "by_id": {
            "216": {"name": "зеленоград", "path": ["зеленоград"]},
            "20674": {"name": "троицк", "path": ["троицк"]},
        },
    }


def test_regions_tree_cache_reports_invalid_json(workspace_tmp_path: Path) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    cache_path.parent.mkdir()
    cache_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(WordstatError, match="Invalid regions tree cache"):
        load_regions_tree_cache(cache_path)


@pytest.mark.parametrize(
    "payload",
    [
        {"by_name": [], "by_id": {}},
        {"by_name": {"moscow": [{"id": "213"}]}, "by_id": {}},
        {"by_name": {"moscow": ["213"]}, "by_id": {"213": "Moscow"}},
    ],
)
def test_regions_tree_cache_reports_invalid_index_shape(
    workspace_tmp_path: Path,
    payload: dict[str, Any],
) -> None:
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    cache_path.parent.mkdir()
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WordstatError, match="Invalid regions tree cache"):
        load_regions_tree_cache(cache_path)


@pytest.mark.anyio
async def test_get_regions_tree_uses_cache_without_api(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_payload = {
        "by_name": {"cached": ["123"]},
        "by_id": {"123": {"name": "Cached", "path": ["Cached"]}},
    }
    cache_path = workspace_tmp_path / ".saved" / "regions_tree.json"
    save_regions_tree_cache(cached_payload, cache_path)
    monkeypatch.chdir(workspace_tmp_path)

    def fail_settings() -> None:
        pytest.fail("settings should not be loaded when cache exists")

    monkeypatch.setattr("wordstat_mcp.tools.wordstat_settings", fail_settings)

    response = await get_regions_tree()

    assert response["by_name"] == cached_payload["by_name"]
    assert response["by_id"] == cached_payload["by_id"]
    assert "find_regions" in response["message"]


@pytest.mark.anyio
async def test_get_regions_tree_fetches_and_saves_missing_cache(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> None:
    payload = {"regions": [{"id": "fresh", "label": "Fresh"}]}
    lookup = {
        "by_name": {"fresh": ["fresh"]},
        "by_id": {"fresh": {"name": "Fresh", "path": ["Fresh"]}},
    }
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

    response = await get_regions_tree()

    assert response["by_name"] == lookup["by_name"]
    assert response["by_id"] == lookup["by_id"]
    assert response["next_action"]
    assert clients[0].calls == [("getRegionsTree", {})]
    assert (
        load_regions_tree_cache(workspace_tmp_path / ".saved" / "regions_tree.json")
        == lookup
    )


@pytest.mark.anyio
async def test_update_regions_tree_refreshes_existing_cache(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wordstat_settings: WordstatSettings,
) -> None:
    old_payload = {"regions": [{"id": "old", "label": "Old"}]}
    fresh_payload = {"regions": [{"id": "fresh", "label": "Fresh"}]}
    fresh_lookup = {
        "by_name": {"fresh": ["fresh"]},
        "by_id": {"fresh": {"name": "Fresh", "path": ["Fresh"]}},
    }
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

    response = await update_regions_tree()

    assert response["by_name"] == fresh_lookup["by_name"]
    assert response["by_id"] == fresh_lookup["by_id"]
    assert "refreshed" in response["message"]
    assert load_regions_tree_cache(cache_path) == fresh_lookup
