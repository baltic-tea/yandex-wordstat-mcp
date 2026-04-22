🇬🇧 [English](./README.md) | 🇷🇺 [Русский](./docs/README_RU.md)

# Yandex Wordstat MCP Server

MCP server for Yandex Wordstat API v2, built with `FastMCP`.

## Features

- MCP tools for Yandex Wordstat API v2 methods:
    - [getTop](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getTop.html)
    - [getDynamics](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getDynamics.html)
    - [getRegionsDistribution](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getRegionsDistribution.html)
    - [getRegionsTree](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getRegionsTree.html)
- Authentication with API-key or IAM-token.
- Batch phrase processing with pagination
- Typed request models
- Local `.saved/regions_tree.json` cache for a compact Wordstat region lookup
- Fast region lookup by name through `find_regions`
- Operator-aware phrase builder for exact forms, stop words, word order, and alternatives
- AI-first aliases for common keyword, trend, and regional demand tasks
- Public tool descriptions include compact `<api>method=...; endpoint=...</api>` metadata
- Retry handling for transient transport failures and `429/5xx`

## System Requirements

- Python `3.11+`
- `uv` recommended, `pip` supported
- Yandex Cloud Wordstat API access

## Installation

For normal MCP client setup, run the server directly from Git with `uvx`:

```bash
uvx --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
```

`uvx` creates an isolated environment and runs the `wordstat-mcp` console
script exposed by the package.

## Development Installation

1. Clone the repository:

```bash
git clone https://github.com/baltic-tea/yandex-wordstat-mcp.git
cd yandex-wordstat-mcp
```

2. Install dependencies with `uv` or `pip`.

### With `uv`

```bash
uv sync --all-groups
```

### With `pip`

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials.

`WORDSTAT_FOLDER_ID` is required for each API request. `WORDSTAT_IAM_TOKEN` will be preferred if `WORDSTAT_API_KEY` is also specified

## Running The Server

Console entrypoint:

```bash
wordstat-mcp
```

The server uses stdio transport through `FastMCP`.

## Available Tools

### `getTop`

Returns top and associated phrases for one or more input phrases.

### `build_wordstat_phrase`

Builds and validates a Wordstat `phrase` from a natural-language Russian request
and optional intent hints. Use it before `getTop`, `getDynamics`, or
`getRegionsDistribution` when the user asks for exact phrases, fixed word order,
required stop words, fixed word forms, or alternatives in natural language.

### `getDynamics`

Returns demand dynamics for one or more phrases over a date range.

`fromDate` is required and should be an RFC3339 timestamp, for example
`2026-01-01T00:00:00Z`. `toDate` is optional; when omitted, the server uses the
current UTC timestamp. Request models normalize the range to Wordstat period
boundaries: `fromDate` is moved to the start of the day, and `toDate` is moved
to the end of the day (`23:59:59.999999Z`) after monthly, weekly, or daily
period alignment.

Wordstat dynamics supports only the `+` operator. The server rejects
`getDynamics` phrases that contain `!`, quotes, `[]`, `()`, or `|`.

### `getRegionsDistribution`

Returns regional distribution for one or more phrases.

### `getRegionsTree`

Returns a compact region index with lowercase region names and region IDs.
The local cache is stored in `.saved/regions_tree.json` with this shape:

```json
{
  "by_name": {
    "зеленоград": ["216"],
    "троицк": ["20674"]
  },
  "by_id": {
    "216": {
      "name": "Зеленоград",
      "path": ["Россия", "Москва и Московская область", "Зеленоград"]
    }
  }
}
```

`by_name` always maps a normalized lowercase name to a list of string IDs,
because one visible region name can map to multiple Wordstat region IDs.

When `.saved/regions_tree.json` exists, this tool reads it locally and does not
call the external API. If the file is missing, the tool fetches the region tree
from the API, converts it to the compact index, and saves the index to
`.saved/regions_tree.json`.

### `find_regions`

Finds region IDs by exact lowercase lookup first and substring fallback second.
Use it before passing user-provided city or region names into the `regions`
parameter of `getTop` or `getDynamics`.

`find_regions` reads the cached `getRegionsTree` index, so repeated lookups are
local after the first cache fill. For many city names in one task, agents can
call `get_region_index` once and resolve exact matches from `by_name`; a
separate batch lookup tool is usually not worth the extra API surface.

### `update_regions_tree`

Refreshes `.saved/regions_tree.json` from the API even when a cached lookup
already exists.

### AI-first aliases

These tools expose the same behavior with task-oriented names:

- `find_keyword_queries` delegates to `getTop`.
- `get_query_demand_trends` delegates to `getDynamics`.
- `compare_query_demand_by_region` delegates to `getRegionsDistribution`.
- `get_region_index` delegates to `getRegionsTree`.

### `wordstat_env_health`

Returns local configuration health without calling the external API.

## Prompt And Resource

The server exposes MCP guidance for agents that need to build Wordstat phrases
from natural language:

- Resource: `wordstat://operators/agent-guide`
- Prompt: `wordstat_phrase_builder`
- Tool: `build_wordstat_phrase`

MCP prompts and resources are advisory context. A server can expose them and
describe when to use them, but the consuming MCP client or LLM decides whether to
load and follow them. Critical constraints are enforced in tools instead:
`getDynamics` validates operator usage server-side, and `build_wordstat_phrase`
returns warnings when it has to drop unsupported operators.

## Integration

The examples below use the `uvx` + Git launch pattern:

```json
{
  "mcpServers": {
    "yandex-wordstat": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/baltic-tea/yandex-wordstat-mcp.git",
        "wordstat-mcp"
      ],
      "env": {
        "WORDSTAT_FOLDER_ID": "your-folder-id",
        "WORDSTAT_API_KEY": "your-api-key"
      }
    }
  }
}
```

For development from a clone, use `wordstat-mcp` from the activated virtual
environment or `uv run wordstat-mcp` inside the repository.

Clients that support this `mcpServers` JSON shape directly or with only location-specific changes: Claude Desktop, Claude Code, Windsurf, Qwen Codem, Kilo Code, Trae.

Clients that support MCP but use a different setup shape: Codex, OpenCode.

### Claude Code

Recommended project-scoped setup:

```bash
claude mcp add yandex-wordstat --scope project --transport stdio \
  --env WORDSTAT_FOLDER_ID=your-folder-id \
  --env WORDSTAT_API_KEY=your-api-key \
  -- uvx --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
```

Verify:

```bash
claude mcp list
```

In Claude Code, run `/mcp` to inspect server status and authenticate remote MCP
servers if needed.

If you prefer a committed project config, create `.mcp.json` in the project root.

Claude Code also supports importing a JSON server definition:

```bash
claude mcp add-json yandex-wordstat '{"type":"stdio","command":"uvx","args":["--from","git+https://github.com/baltic-tea/yandex-wordstat-mcp.git","wordstat-mcp"],"env":{"WORDSTAT_FOLDER_ID":"your-folder-id","WORDSTAT_API_KEY":"your-api-key"}}'
```

### Codex

Codex supports MCP in both the CLI and VS Code IDE extension. It does not use
the `mcpServers` JSON object directly; use the CLI or TOML config.

CLI example:

```bash
codex mcp add yandex_wordstat_mcp --command uvx -- --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
codex mcp list
```

If you prefer editing config directly, edit the file `~/.codex/config.toml`:

```toml
[mcp_servers.yandex_wordstat_mcp]
command = "uvx"
args = ["--from", "git+https://github.com/baltic-tea/yandex-wordstat-mcp.git", "wordstat-mcp"]

[mcp_servers.yandex_wordstat_mcp.env]
WORDSTAT_FOLDER_ID = "your-folder-id"
WORDSTAT_API_KEY = "your-api-key"
```

Verify:

```bash
codex mcp list
```

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](./LICENSE).

## Authors

- [baltic_tea](https://github.com/baltic-tea)
