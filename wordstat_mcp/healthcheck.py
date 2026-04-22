"""Container healthcheck entrypoint."""

from __future__ import annotations

from typing import Any

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.metadata import McpServerMetadata


def mcp_healthcheck(
    settings: WordstatSettings | None = None,
    *,
    check_registry: bool = False,
) -> dict[str, Any]:
    """Return a health snapshot without calling external Wordstat API."""

    if settings is None:
        settings = WordstatSettings()  # type: ignore[call-arg]

    if check_registry:
        from wordstat_mcp.server import mcp

        if not mcp.name:
            raise RuntimeError("MCP server name is not configured.")

    metadata = McpServerMetadata()
    return {
        "status": "ok",
        "serverName": metadata.name,
        "serverVersion": metadata.version,
        "apiUrl": settings.api_url,
        "timeoutSeconds": settings.timeout_seconds,
        "maxAttempts": settings.max_attempts,
        "maxConcurrency": settings.max_concurrency,
        "registryChecked": check_registry,
    }


if __name__ == "__main__":
    mcp_healthcheck(check_registry=True)
