"Async MCP tools for Yandex Wordstat API v2."

from __future__ import annotations
from datetime import datetime

from typing import Annotated, Any, cast

from pydantic import Field, ValidationError
from fastmcp import FastMCP

from wordstat_mcp import descriptions
from wordstat_mcp.exceptions import WordstatConfigError, WordstatError, to_tool_error
from wordstat_mcp.client import WordstatClient
from wordstat_mcp.helpers import (
    clean_tool_phrases,
    fetch_many,
    find_region_matches,
    load_regions_tree_cache,
    parse_datetime,
    save_regions_tree_cache,
    tool_annotations,
    validate_dynamics_phrases,
    wordstat_settings,
)
from wordstat_mcp.healthcheck import mcp_healthcheck
from wordstat_mcp.metadata import McpServerMetadata
from wordstat_mcp.models import (
    GetDynamicsResponse,
    GetDynamicsRequest,
    GetRegionsDistributionResponse,
    GetRegionsDistributionRequest,
    GetTopRequest,
    GetTopResponse,
    RegionIndexResponse,
    RegionMatch,
    RegionSearchResponse,
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
)


mcp = FastMCP(**McpServerMetadata().model_dump())


@mcp.resource(
    OPERATORS_GUIDE_RESOURCE_URI,
    name="wordstat_operators_agent_guide",
    title="Wordstat Operators Agent Guide",
    description=descriptions.WORDSTAT_OPERATORS_AGENT_GUIDE,
    mime_type="text/markdown",
)
def wordstat_operators_agent_guide() -> str:
    """Return Wordstat operator guidance for MCP clients."""

    return WORDSTAT_OPERATORS_AGENT_GUIDE


@mcp.prompt(
    name=OPERATORS_PROMPT_NAME,
    title="Build a Yandex Wordstat Phrase",
    description=descriptions.WORDSTAT_PHRASE_BUILDER_PROMPT,
)
def wordstat_phrase_builder(
    user_request: str,
    target_method: str = "getTop",
) -> str:
    """Prepare an agent to build a valid Wordstat phrase."""

    return render_wordstat_phrase_builder_prompt(user_request, target_method)


@mcp.tool(
    name="build_wordstat_phrase",
    description=descriptions.BUILD_WORDSTAT_PHRASE,
    annotations=tool_annotations("Build Wordstat Phrase", open_world=False),
)
async def build_wordstat_phrase(
    natural_query: Annotated[
        str,
        Field(
            description=(
                "User's keyword intent and matching rules, e.g. exact phrase "
                "купить авто (buy a car)."
            )
        ),
    ],
    target_method: Annotated[
        WordstatSearchMethod,
        Field(
            description=(
                "Target tool for the generated phrase; used to enforce "
                "Wordstat operator compatibility."
            )
        ),
    ],
    base_phrase: Annotated[
        str | None,
        Field(
            description=(
                "Optional plain phrase to transform, e.g. купить авто (buy a car)."
            )
        ),
    ] = None,
    exact_word_count: Annotated[
        bool,
        Field(description="Request exact word-count semantics when compatible."),
    ] = False,
    fixed_word_order: Annotated[
        bool,
        Field(description="Request fixed word-order semantics when compatible."),
    ] = False,
    alternatives: Annotated[
        list[str] | None,
        Field(
            description=(
                "Alternative words or phrases, e.g. ноутбук (laptop), "
                "компьютер (computer)."
            )
        ),
    ] = None,
    fixed_forms: Annotated[
        list[str] | None,
        Field(description="Words to keep in exact forms, e.g. авто (car)."),
    ] = None,
    required_stop_words: Annotated[
        list[str] | None,
        Field(description="Stop words to force with `+`, e.g. из (from), в (in)."),
    ] = None,
) -> dict[str, Any]:
    """Build a valid Wordstat phrase with structured warning codes."""

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
        raise to_tool_error(exc, operation="build_wordstat_phrase") from exc


@mcp.tool(
    name="getTop",
    description=descriptions.GET_TOP,
    annotations=tool_annotations("Top Queries"),
)
async def get_top(
    phrases: Annotated[
        list[str],
        Field(
            description=(
                "Final Wordstat phrases, e.g. купить авто (buy a car). Use "
                "build_wordstat_phrase first for exactness, fixed order, forms, "
                "alternatives, or required stop words."
            )
        ),
    ],
    numPhrases: Annotated[
        int,
        Field(
            ge=1,
            le=2000,
            description="Top Wordstat phrases to request per input phrase.",
        ),
    ] = 50,
    regions: Annotated[
        list[int | str] | None,
        Field(
            description=(
                "Yandex Wordstat region IDs. Use find_regions for names, e.g. "
                "Moscow (Москва)."
            )
        ),
    ] = None,
    devices: Annotated[
        list[WordstatDevices] | None,
        Field(description="Device filters; omit for all devices."),
    ] = None,
    page: Annotated[int, Field(ge=1, description="1-based result page.")] = 1,
    pageSize: Annotated[
        int, Field(ge=1, description="Phrase-level items per response page.")
    ] = 50,
) -> GetTopResponse:
    """Get top and associated phrases for one or many input phrases."""
    try:
        cleaned_phrases, phrase_warnings = clean_tool_phrases(phrases)
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

            response = await fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
            response["message"] = (
                "Use returned top query phrases for deeper trend or regional analysis."
            )
            response["next_action"] = (
                "Call getDynamics for time trends or getRegionsDistribution for geography."
            )
            if phrase_warnings:
                response["warnings"] = phrase_warnings
            return cast(GetTopResponse, response)
    except (ValueError, ValidationError, WordstatError) as exc:
        raise to_tool_error(exc, operation="getTop") from exc


@mcp.tool(
    name="getDynamics",
    description=descriptions.GET_DYNAMICS,
    annotations=tool_annotations("Query Demand Dynamics"),
)
async def get_dynamics(
    phrases: Annotated[
        list[str],
        Field(
            description=(
                "Final Wordstat phrases, e.g. купить авто (buy a car). Use "
                "build_wordstat_phrase first for exactness or operators."
            )
        ),
    ],
    fromDate: Annotated[
        str | datetime,
        Field(
            description=(
                "RFC3339 start date, e.g. 2026-04-09T00:00:00Z; "
                "period boundary is normalized automatically."
            )
        ),
    ],
    period: Annotated[
        WordstatPeriods,
        Field(description="Aggregation period: daily, weekly, or monthly."),
    ] = "PERIOD_MONTHLY",
    toDate: Annotated[
        datetime | str | None,
        Field(
            description=(
                "Optional RFC3339 end date; defaults to current UTC time and "
                "normalizes to the period boundary automatically."
            )
        ),
    ] = None,
    regions: Annotated[
        list[int | str] | None,
        Field(description="Yandex Wordstat region IDs; use find_regions for names."),
    ] = None,
    devices: Annotated[
        list[WordstatDevices] | None,
        Field(description="Device filters; omit for all devices."),
    ] = None,
    page: Annotated[int, Field(ge=1, description="1-based result page.")] = 1,
    pageSize: Annotated[
        int, Field(ge=1, description="Phrase-level items per response page.")
    ] = 50,
) -> GetDynamicsResponse:
    """Get query demand dynamics for one or many phrases."""

    try:
        from_date = parse_datetime(fromDate)
        to_date = parse_datetime(toDate) if toDate is not None else None
        cleaned_phrases, phrase_warnings = clean_tool_phrases(phrases)
        validate_dynamics_phrases(cleaned_phrases)
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

            response = await fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
            response["message"] = (
                "Use these trend results to compare periods, devices, or regions."
            )
            response["next_action"] = (
                "Refine period/date range or call getRegionsDistribution for geography."
            )
            if phrase_warnings:
                response["warnings"] = phrase_warnings
            return cast(GetDynamicsResponse, response)
    except (ValueError, ValidationError, WordstatError) as exc:
        raise to_tool_error(exc, operation="getDynamics") from exc


@mcp.tool(
    name="getRegionsDistribution",
    description=descriptions.GET_REGIONS_DISTRIBUTION,
    annotations=tool_annotations("Regional Distribution"),
)
async def get_regions_distribution(
    phrases: Annotated[
        list[str],
        Field(
            description=(
                "Final Wordstat phrases, e.g. купить авто (buy a car). Use "
                "build_wordstat_phrase first for exactness or operators."
            )
        ),
    ],
    region: Annotated[
        WordstatRegionModes,
        Field(description="Distribution mode: all, regions, or cities."),
    ] = "REGION_ALL",
    devices: Annotated[
        list[WordstatDevices] | None,
        Field(description="Device filters; omit for all devices."),
    ] = None,
    page: Annotated[int, Field(ge=1, description="1-based result page.")] = 1,
    pageSize: Annotated[
        int, Field(ge=1, description="Phrase-level items per response page.")
    ] = 50,
) -> GetRegionsDistributionResponse:
    """Get region distribution for one or many phrases."""
    try:
        cleaned_phrases, phrase_warnings = clean_tool_phrases(phrases)
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

            response = await fetch_many(
                cleaned_phrases,
                worker,
                page=page,
                page_size=pageSize,
                max_concurrency=settings.max_concurrency,
            )
            response["message"] = (
                "Use region IDs from distribution results as filters in getTop or getDynamics."
            )
            response["next_action"] = (
                "Call find_regions for exact region IDs or use returned IDs in regions."
            )
            if phrase_warnings:
                response["warnings"] = phrase_warnings
            return cast(GetRegionsDistributionResponse, response)
    except (ValueError, ValidationError, WordstatError) as exc:
        raise to_tool_error(exc, operation="getRegionsDistribution") from exc


@mcp.tool(
    name="getRegionsTree",
    description=descriptions.GET_REGIONS_TREE,
    annotations=tool_annotations("Regions Tree"),
)
async def get_regions_tree() -> RegionIndexResponse:
    """Get cached region index with by_name and by_id lookups."""
    try:
        cached_payload = load_regions_tree_cache()
        if cached_payload is None:
            settings = wordstat_settings()
            async with WordstatClient(settings) as client:
                payload = await client.request_json("getRegionsTree")
                cached_payload = save_regions_tree_cache(payload)

        response = dict(cached_payload)
        response["message"] = (
            "Region index loaded. Prefer find_regions for targeted lookup."
        )
        response["next_action"] = (
            "Use by_name[name.lower()] for fast exact name to ID list lookup."
        )
        return cast(RegionIndexResponse, response)
    except (ValueError, WordstatError) as e:
        raise to_tool_error(e, operation="getRegionsTree") from e


@mcp.tool(
    name="find_regions",
    description=descriptions.FIND_REGIONS,
    annotations=tool_annotations("Find Wordstat Regions"),
)
async def find_regions(
    query: Annotated[
        str,
        Field(description="Region name or substring, e.g. Москва or Troitsk (Троицк)."),
    ],
    limit: Annotated[
        int,
        Field(ge=1, le=50, description="Maximum region candidates to return."),
    ] = 10,
) -> RegionSearchResponse:
    """Find region IDs by lowercase exact lookup and substring fallback."""
    try:
        index = await get_regions_tree()
        matches = cast(
            list[RegionMatch],
            find_region_matches(cast(dict[str, Any], index), query, limit=limit),
        )
        return {
            "query": query,
            "matches": matches,
            "total": len(matches),
            "message": "Use returned id values in the `regions` parameter.",
            "next_action": "Pass selected match.id to getTop or getDynamics regions.",
        }
    except (ValueError, WordstatError) as e:
        raise to_tool_error(e, operation="find_regions") from e


@mcp.tool(
    name="update_regions_tree",
    description=descriptions.UPDATE_REGIONS_TREE,
    annotations=tool_annotations(
        "Update Wordstat Regions Tree Cache", read_only=False, idempotent=True
    ),
)
async def update_regions_tree() -> RegionIndexResponse:
    """Refresh cached region index from Wordstat API."""
    try:
        settings = wordstat_settings()
        async with WordstatClient(settings) as client:
            payload = await client.request_json("getRegionsTree")
            index = save_regions_tree_cache(payload)
            response = dict(index)
            response["message"] = "Region index refreshed and saved locally."
            response["next_action"] = (
                "Call find_regions to look up a region ID by name."
            )
            return cast(RegionIndexResponse, response)
    except (ValueError, WordstatError) as e:
        raise to_tool_error(e, operation="update_regions_tree") from e


@mcp.tool(
    name="wordstat_env_health",
    description=descriptions.WORDSTAT_ENV_HEALTH,
    annotations=tool_annotations("Wordstat Environment Health", open_world=False),
)
async def wordstat_env_health() -> dict[str, Any]:
    """Return server health snapshot without external API call.

    Returns:
        dict[str, Any]: Health status and redacted runtime configuration.
    """

    try:
        return mcp_healthcheck(wordstat_settings())
    except WordstatConfigError as e:
        return {"status": "error", "message": str(e)}
