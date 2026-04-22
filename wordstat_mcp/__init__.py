"""MCP Yandex Wordstat package."""

__all__ = ["mcp"]


def __getattr__(name: str) -> object:
    """Lazily expose package-level MCP server."""

    if name == "mcp":
        from wordstat_mcp.tools import mcp

        return mcp
    raise AttributeError(name)
