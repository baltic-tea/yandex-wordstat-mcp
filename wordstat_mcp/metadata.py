"""Server metadata model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class McpServerMetadata(BaseModel):
    """Metadata accepted by FastMCP server construction."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(default="Yandex Wordstat MCP Server")
    version: str = Field(default="0.1.1")
    instructions: str = Field(
        default=(
            "Supported Yandex Wordstat API methods: Wordstat.GetTop, "
            "Wordstat.GetDynamics, Wordstat.GetRegionsDistribution, "
            "Wordstat.GetRegionsTree."
        )
    )
    website_url: str = Field(
        default="https://github.com/baltic-tea/yandex-wordstat-mcp-test"
    )
