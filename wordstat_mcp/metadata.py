"""Server metadata constants."""

from __future__ import annotations


SERVER_NAME = "Yandex Wordstat MCP Server"
SERVER_DESCRIPTION = "MCP server for Yandex Wordstat API v2"
SERVER_VERSION = "0.1.1"
SERVER_SOURCE_URL = "https://github.com/baltic-tea/yandex-wordstat-mcp-test"
SERVER_DOCUMENTATION_URL = f"{SERVER_SOURCE_URL}#readme"


def get_server_version() -> str:
    """Return server version."""

    return SERVER_VERSION
