"""Container healthcheck entrypoint."""

from __future__ import annotations

from typing import Any

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.metadata import SERVER_NAME, get_server_version


def mcp_healthcheck(
    settings: WordstatSettings | None = None,
    *,
    check_registry: bool = False,
) -> dict[str, Any]:
    """Return a health snapshot without calling external Wordstat API."""

    if settings is None:
        settings = WordstatSettings()  # type: ignore[call-arg]
    if check_registry:
        from wordstat_mcp.tools import mcp

        if not mcp.name:
            raise RuntimeError("MCP server name is not configured.")

    return {
        "status": "ok",
        "serverName": SERVER_NAME,
        "serverVersion": get_server_version(),
        "apiUrl": settings.api_url,
        "timeoutSeconds": settings.timeout_seconds,
        "maxAttempts": settings.max_attempts,
        "maxConcurrency": settings.max_concurrency,
        "registryChecked": check_registry,
    }


if __name__ == "__main__":
    mcp_healthcheck(check_registry=True)
