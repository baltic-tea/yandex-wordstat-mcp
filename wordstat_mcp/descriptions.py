"""MCP descriptions for Yandex Wordstat tools, prompts, and resources."""

from __future__ import annotations

from wordstat_mcp.operators import OPERATORS_GUIDE_RESOURCE_URI, OPERATORS_PROMPT_NAME


WORDSTAT_API_GET_TOP = "<api>method=Wordstat.GetTop; endpoint=topRequests</api>"
WORDSTAT_API_GET_DYNAMICS = "<api>method=Wordstat.GetDynamics; endpoint=dynamics</api>"
WORDSTAT_API_GET_REGIONS_DISTRIBUTION = (
    "<api>method=Wordstat.GetRegionsDistribution; endpoint=regions</api>"
)

WORDSTAT_API_GET_REGIONS_TREE = (
    "<api>method=Wordstat.GetRegionsTree; endpoint=getRegionsTree</api>"
)
WORDSTAT_OPERATORS_AGENT_GUIDE = (
    "Operator-selection rules for building Yandex Wordstat `phrase` values. "
    "Read before converting natural-language keyword requests into Wordstat "
    "phrases with exactness, fixed order, fixed forms, alternatives, or forced "
    "stop words."
)

WORDSTAT_PHRASE_BUILDER_PROMPT = (
    "Prompt template for turning a user's natural-language intent into a valid "
    "Wordstat `phrase` while respecting operator compatibility and per-method "
    "limits."
)

BUILD_WORDSTAT_PHRASE = (
    "Build a valid Yandex Wordstat phrase from natural-language intent without "
    "calling the external API.\n"
    "<usecase>Use before query tools when user asks for exact phrase, fixed "
    "word order, fixed word forms, alternatives, optional words, or required "
    "stop words. Use for Russian keyword phrasing when the user describes "
    "matching rules rather than providing final Wordstat syntax.</usecase>\n"
    "<instructions>Use the returned `phrase` as-is in the target Wordstat tool. "
    "Keep operator compatibility details internal; mention warning codes only "
    "when the user asks about query syntax, exactness, or why the phrase "
    f"changed. Rules match {OPERATORS_PROMPT_NAME} and "
    f"{OPERATORS_GUIDE_RESOURCE_URI}.</instructions>\n"
    "<returns>Phrase, target method, applied operators, warning codes, review flag, "
    "and guide references.</returns>"
)

GET_TOP = (
    "Find popular search queries and related keyword expansions for the last "
    "available Wordstat demand window.\n"
    "<usecase>Use when user asks for top queries, keyword ideas, related "
    "phrases, search-demand variants, keyword clusters, or phrase expansion. "
    "Use this for discovery, not time-series trend questions.</usecase>\n"
    "<instructions>Use find_regions first when the user names cities or regions. "
    "Use build_wordstat_phrase first when the request implies exact phrase, "
    "fixed word order, fixed forms, alternatives, or required stop words. This "
    "is the API-compatible tool name; aliases call this tool internally.</instructions>\n"
    "<returns>Paginated phrase results with phrase-level raw Wordstat "
    "topRequests payloads.</returns>\n"
    f"{WORDSTAT_API_GET_TOP}"
)

GET_DYNAMICS = (
    "Get search-demand dynamics for phrases over daily, weekly, or monthly "
    "periods.\n"
    "<usecase>Use when user asks about popularity over time, seasonality, "
    "growth or decline, monthly/weekly/daily dynamics, historical demand, or "
    "comparisons across periods.</usecase>\n"
    "<instructions>`fromDate` is required RFC3339. `toDate` is optional. Dates "
    "normalize to Wordstat period boundaries. Use phrase-builder output as-is "
    "for natural-language operator requests. Use find_regions first when the "
    "user names geographic filters."
    "</instructions>\n"
    "<returns>Paginated phrase results with phrase-level raw Wordstat dynamics "
    "payloads.</returns>\n"
    f"{WORDSTAT_API_GET_DYNAMICS}"
)

GET_REGIONS_DISTRIBUTION = (
    "Compare search demand by regions or cities for phrases during the last "
    "available Wordstat demand window.\n"
    "<usecase>Use when user asks where demand is strongest, wants regional "
    "distribution, compares cities/regions, prioritizes markets, or needs a "
    "ranked geography table.</usecase>\n"
    "<instructions>Use build_wordstat_phrase first for natural-language "
    "operator requests. Use find_regions when the user asks to apply specific "
    "region IDs as filters in getTop or getDynamics. Set region mode to cities "
    "for city-level comparison.</instructions>\n"
    "<returns>Paginated phrase results with phrase-level raw Wordstat regional "
    "payloads.</returns>\n"
    f"{WORDSTAT_API_GET_REGIONS_DISTRIBUTION}"
)

GET_REGIONS_TREE = (
    "Return a compact local index of Wordstat region names and IDs."
    "\n<usecase>Use for debugging, cache inspection, or bulk lookup of cached "
    "region IDs. For a named city or region request, prefer find_regions.</usecase>\n"
    "<instructions>Prefer find_regions for targeted region lookup. Keys in "
    "`by_name` are lowercase region names and values are ID lists. `by_id` "
    "contains normalized names and region paths. If cache is absent, this tool "
    "fetches and saves the region tree.</instructions>\n"
    "<returns>Region index with by_name, by_id, message, next_action.</returns>\n"
    f"{WORDSTAT_API_GET_REGIONS_TREE}"
)

FIND_REGIONS = (
    "Find Yandex Wordstat region IDs by region name.\n"
    "<usecase>Use when user mentions a city, region, or place name and another "
    "tool needs numeric region IDs. Use this before getTop/getDynamics filters "
    "or when building city comparison tables.</usecase>\n"
    "<instructions>Searches cached region index by exact, substring, and path "
    "matches. If cache is missing, fetches the region tree once and saves the "
    "local index. Use returned `id` values in `regions` parameters.</instructions>\n"
    "<returns>Matching region candidates with id, name, path, matchType, and next action.</returns>\n"
    f"{WORDSTAT_API_GET_REGIONS_TREE}"
)

UPDATE_REGIONS_TREE = (
    "Refresh the local Wordstat region index cache from the API.\n"
    "<usecase>Use when region lookup looks outdated, cache is invalid, or "
    "find_regions cannot locate an expected official region.</usecase>\n"
    "<instructions>This writes `.saved/regions_tree.json` but does not modify "
    "remote data. Prefer find_regions for normal lookup; this is a cache "
    "maintenance tool.</instructions>\n"
    "<returns>Fresh region index with by_name, by_id, message, next_action.</returns>\n"
    f"{WORDSTAT_API_GET_REGIONS_TREE}"
)

WORDSTAT_ENV_HEALTH = (
    "Check server health and configuration.\n"
    "<usecase>Use only for troubleshooting, configuration problems, or tool "
    "errors. Do not call during normal keyword, dynamics, or region-analysis "
    "flows.</usecase>\n"
    "<instructions>This is a local diagnostic tool and does not call the "
    "external Wordstat API. It reports server metadata, API URL, timeout, retry, "
    "and concurrency settings with secrets omitted.</instructions>"
)
