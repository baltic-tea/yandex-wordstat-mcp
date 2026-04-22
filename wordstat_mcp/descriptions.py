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
WORDSTAT_API_FIND_KEYWORD_QUERIES = (
    "<api>method=Wordstat.GetTop; endpoint=topRequests</api>"
)
WORDSTAT_API_GET_QUERY_DEMAND_TRENDS = (
    "<api>method=Wordstat.GetDynamics; endpoint=dynamics</api>"
)
WORDSTAT_API_COMPARE_QUERY_DEMAND_BY_REGION = (
    "<api>method=Wordstat.GetRegionsDistribution; endpoint=regions</api>"
)
WORDSTAT_API_GET_REGION_INDEX = (
    "<api>method=Wordstat.GetRegionsTree; endpoint=getRegionsTree</api>"
)

WORDSTAT_OPERATORS_AGENT_GUIDE = (
    "Operator-selection rules for building Yandex Wordstat `phrase` values. "
    "Agents should read this before converting natural-language requests "
    "into Wordstat phrases."
)

WORDSTAT_PHRASE_BUILDER_PROMPT = (
    "Preset prompt that instructs an agent how to convert a natural-language "
    "request into a Wordstat `phrase` while respecting operator limits."
)

BUILD_WORDSTAT_PHRASE = (
    "Build a valid Yandex Wordstat phrase from natural-language intent.\n"
    "<usecase>Use before query tools when user asks for exact phrase, fixed "
    "word order, word forms, alternatives, or required stop words.</usecase>\n"
    "<instructions>Use the returned phrase as-is. Keep operator compatibility "
    "details internal; do not mention operator-limit warning codes to the user "
    "unless they ask about query syntax, exactness, or why the phrase changed. "
    f"Reads the same rules exposed by {OPERATORS_PROMPT_NAME} and "
    f"{OPERATORS_GUIDE_RESOURCE_URI}.</instructions>\n"
    "<returns>Phrase, target method, applied operators, warning codes, review flag, "
    "and guide references.</returns>"
)

GET_TOP = (
    "Find popular search queries and related keyword expansions.\n"
    f"{WORDSTAT_API_GET_TOP}\n"
    "<usecase>Use when user asks for top queries, keyword ideas, related "
    "phrases, or demand variants for the last 30 days.</usecase>\n"
    "<instructions>Use find_regions first for geographic filters. Use "
    "build_wordstat_phrase first for natural-language operator requests. "
    "This is the API-compatible tool name.</instructions>\n"
    "<returns>Paginated phrase results with raw Wordstat topRequests payloads.</returns>"
)

GET_DYNAMICS = (
    "Get search-demand trend for phrases over daily, weekly, or monthly periods.\n"
    f"{WORDSTAT_API_GET_DYNAMICS}\n"
    "<usecase>Use when user asks about popularity over time, seasonality, "
    "trend changes, or historical demand.</usecase>\n"
    "<instructions>fromDate is required RFC3339. toDate is optional. Dates "
    "normalize to period boundaries. Use phrase-builder output as-is for "
    "natural-language operator requests. Use find_regions first for region IDs."
    "</instructions>\n"
    "<returns>Paginated phrase results with raw Wordstat dynamics payloads.</returns>"
)

GET_REGIONS_DISTRIBUTION = (
    "Compare search demand by regions or cities for phrases.\n"
    f"{WORDSTAT_API_GET_REGIONS_DISTRIBUTION}\n"
    "<usecase>Use when user asks where demand is strongest, wants regional "
    "distribution, or compares cities/regions for the last 30 days.</usecase>\n"
    "<instructions>Use build_wordstat_phrase first for natural-language "
    "operator requests. Use find_regions when user asks to apply returned "
    "region IDs as filters in other tools.</instructions>\n"
    "<returns>Paginated phrase results with raw Wordstat regional payloads.</returns>"
)

GET_REGIONS_TREE = (
    "Return a compact local index of Wordstat region names and IDs."
    f"\n{WORDSTAT_API_GET_REGIONS_TREE}"
    "\n<usecase>Use for debugging or bulk lookup of cached region IDs.</usecase>\n"
    "<instructions>Prefer find_regions for targeted region lookup. Keys in "
    "`by_name` are lowercase region names and values are ID lists. `by_id` "
    "contains names and paths.</instructions>\n"
    "<returns>Region index with by_name, by_id, message, next_action.</returns>"
)

FIND_REGIONS = (
    "Find Yandex Wordstat region IDs by region name.\n"
    f"{WORDSTAT_API_GET_REGIONS_TREE}\n"
    "<usecase>Use when user mentions a city, region, or place name and another "
    "tool needs numeric region IDs.</usecase>\n"
    "<instructions>Searches cached region index. If cache is missing, fetches "
    "the region tree once and saves the local index. Use returned id values in "
    "`regions` parameters.</instructions>\n"
    "<returns>Matching region candidates with id, name, path, matchType, and next action.</returns>"
)

UPDATE_REGIONS_TREE = (
    "Refresh the local Wordstat region index cache from the API.\n"
    f"{WORDSTAT_API_GET_REGIONS_TREE}\n"
    "<usecase>Use when region lookup looks outdated or cache is invalid.</usecase>\n"
    "<instructions>This writes `.saved/regions_tree.json` but does not modify "
    "remote data. Prefer find_regions for normal lookup.</instructions>\n"
    "<returns>Fresh region index with by_name, by_id, message, next_action.</returns>"
)

FIND_KEYWORD_QUERIES = (
    "Find popular keyword query variants for phrases.\n"
    f"{WORDSTAT_API_FIND_KEYWORD_QUERIES}\n"
    "<usecase>AI-first alias for getTop. Use for keyword expansion, top "
    "queries, and related phrase discovery.</usecase>\n"
    "<instructions>Use find_regions first for geographic filters and "
    "build_wordstat_phrase first for operator-heavy natural language.</instructions>"
)

GET_QUERY_DEMAND_TRENDS = (
    "Get phrase demand trends over time.\n"
    f"{WORDSTAT_API_GET_QUERY_DEMAND_TRENDS}\n"
    "<usecase>AI-first alias for getDynamics. Use for popularity over time, "
    "seasonality, and historical demand.</usecase>\n"
    "<instructions>fromDate is required RFC3339. Use find_regions first for "
    "geographic filters.</instructions>"
)

COMPARE_QUERY_DEMAND_BY_REGION = (
    "Compare phrase demand across regions or cities.\n"
    f"{WORDSTAT_API_COMPARE_QUERY_DEMAND_BY_REGION}\n"
    "<usecase>AI-first alias for getRegionsDistribution. Use for geographic "
    "demand comparison and market prioritization.</usecase>\n"
    "<instructions>Use build_wordstat_phrase first for natural-language "
    "operator requests.</instructions>"
)

GET_REGION_INDEX = (
    "Return cached Wordstat region lookup index.\n"
    f"{WORDSTAT_API_GET_REGION_INDEX}\n"
    "<usecase>AI-first alias for getRegionsTree. Prefer find_regions for "
    "targeted name lookup.</usecase>"
)

WORDSTAT_ENV_HEALTH = (
    "Check server health and configuration.\n"
    "<usecase>Use only for troubleshooting, configuration problems, or tool "
    "errors. Do not call during normal keyword, dynamics, or region-analysis "
    "flows.</usecase>\n"
    "<instructions>This is a local diagnostic tool and does not call the "
    "external Wordstat API.</instructions>"
)
