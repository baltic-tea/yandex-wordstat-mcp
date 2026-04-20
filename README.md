# Yandex Wordstat MCP Server

MCP server for Yandex Wordstat API v2, built with `FastMCP`.

## Features

- MCP tools for Yandex Wordstat API v2 methods:
    - getTop
    - getDynamics
    - getRegionsDistribution
    - getRegionsTree
- Authentication with API-key or IAM-token.
- Batch phrase processing with pagination
- Typed request models
- Local `.saved/regions_tree.json` cache for the Wordstat region tree
- Retry handling for transient transport failures and `429/5xx`

## System Requirements

- Python `3.11+`
- `uv` recommended, `pip` supported
- Yandex Cloud Wordstat API access

## Installation

Clone the repository first:

```bash
git clone https://github.com/baltic-tea/yandex-wordstat-mcp.git
cd yandex-wordstat-mcp
```

### With `uv`

```bash
uv sync
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

## Build From Source

Build steps:

1. Install dependencies with `uv sync --all-groups` or `pip install -e .`.
2. Ensure the virtual environment is active if you use `pip`.
3. Run the build command below.

```bash
uv build
```

## Running The Server

Module entrypoint:

```bash
python -m wordstat_mcp
```

The server uses stdio transport through `FastMCP`.

## Available Tools

### `getTop`

Returns top and associated phrases for one or more input phrases.

### `getDynamics`

Returns demand dynamics for one or more phrases over a date range.

`fromDate` and `toDate` should be RFC3339 timestamps, for example
`2026-01-01T00:00:00Z`.

### `getRegionsDistribution`

Returns regional distribution for one or more phrases.

### `getRegionsTree`

Returns the full region tree supported by Yandex APIs.

When `.saved/regions_tree.json` exists, this tool reads it locally and does not
call the external API. If the file is missing, the tool fetches the tree from the
API and saves it to `.saved/regions_tree.json`.

### `update_regions_tree`

Refreshes `.saved/regions_tree.json` from the API even when a cached file already
exists.

### `wordstat_env_health`

Returns local configuration health without calling the external API.

## Integration

The examples below use the local stdio launch pattern:

```json
{
  "mcpServers": {
    "yandex-wordstat": {
      "command": "python",
      "args": ["-m", "wordstat_mcp"],
      "cwd": "/absolute/path/to/yandex-wordstat-mcp",
      "env": {
        "WORDSTAT_FOLDER_ID": "your-folder-id",
        "WORDSTAT_API_KEY": "your-api-key"
      }
    }
  }
}
```

Replace `python` with your explicit interpreter path if needed.

Clients that support this `mcpServers` JSON shape directly or with only location-specific changes: Claude Desktop, Claude Code, Windsurf, Qwen Codem, Kilo Code, Trae.

Clients that support MCP but use a different setup shape: Codex, OpenCode.

### Claude Code

Recommended project-scoped setup:

```bash
claude mcp add yandex-wordstat --scope project --transport stdio \
  --env WORDSTAT_FOLDER_ID=your-folder-id \
  --env WORDSTAT_API_KEY=your-api-key \
  -- python -m wordstat_mcp
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
claude mcp add-json yandex-wordstat '{"type":"stdio","command":"python","args":["-m","wordstat_mcp"],"cwd":"/absolute/path/to/yandex-wordstat-mcp","env":{"WORDSTAT_FOLDER_ID":"your-folder-id","WORDSTAT_API_KEY":"your-api-key"}}'
```

### Codex

Codex supports MCP in both the CLI and VS Code IDE extension. It does not use
the `mcpServers` JSON object directly; use the CLI or TOML config.

CLI example:

```bash
codex mcp add yandex_wordstat_mcp --command python -- -m wordstat_mcp
codex mcp list
```

If you prefer editing config directly, edit the file `~/.codex/config.toml`:

```toml
[mcp_servers.yandex_wordstat_mcp]
command = "python"
args = ["-m", "wordstat_mcp"]
cwd = "/absolute/path/to/yandex-wordstat-mcp"

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
