# Stage 1: Build the MCP server
# ----------------------
FROM ghcr.io/astral-sh/uv:0.11-python3.14-trixie-slim AS builder

WORKDIR /mcp

COPY pyproject.toml uv.lock README.md ./
COPY wordstat_mcp ./wordstat_mcp

RUN uv sync --frozen --no-dev

# Stage 2: Run the MCP server
# --------------------
FROM python:3.14-slim

LABEL org.opencontainers.image.title="Yandex Wordstat MCP Server"
LABEL org.opencontainers.image.description="MCP server for Yandex Wordstat API v2"
LABEL org.opencontainers.image.version="0.1.1"
LABEL org.opencontainers.image.licenses="GPL-3.0-only"
LABEL org.opencontainers.image.source="https://github.com/baltic-tea/yandex-wordstat-mcp-test"
LABEL org.opencontainers.image.url="https://github.com/baltic-tea/yandex-wordstat-mcp-test"
LABEL org.opencontainers.image.documentation="https://github.com/baltic-tea/yandex-wordstat-mcp-test#readme"
LABEL org.opencontainers.image.vendor="baltic-tea"
LABEL org.opencontainers.image.base.name="python:3.14-slim"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/mcp/.venv/bin:$PATH"

WORKDIR /mcp

RUN groupadd --system mcpgroup && \
    useradd --system --create-home --gid mcpgroup mcpuser && \
    chown mcpuser:mcpgroup /mcp

COPY --from=builder --chown=mcpuser:mcpgroup /mcp/.venv /mcp/.venv
COPY --chown=mcpuser:mcpgroup wordstat_mcp ./wordstat_mcp

USER mcpuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -m wordstat_mcp.healthcheck

CMD ["wordstat-mcp"]
