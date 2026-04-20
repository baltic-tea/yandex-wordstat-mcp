"""Package entrypoint."""

from __future__ import annotations

import logging

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.tools import mcp


def main() -> None:
    """Run MCP server."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    WordstatSettings()
    mcp.run()


if __name__ == "__main__":
    main()
