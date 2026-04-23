from __future__ import annotations

from pathlib import Path


def test_dockerfile_runs_application_as_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM ghcr.io/astral-sh/uv:0.11-python3.14-trixie-slim AS builder" in dockerfile
    assert "FROM python:3.14-slim" in dockerfile
    assert "WORKDIR /mcp" in dockerfile
    assert "/mcp_server" not in dockerfile
    assert "COPY pyproject.toml uv.lock README.md ./" in dockerfile
    assert "COPY wordstat_mcp ./wordstat_mcp" in dockerfile
    assert "RUN uv sync --frozen --no-dev" in dockerfile
    assert "groupadd --system mcpgroup" in dockerfile
    assert "useradd --system --create-home --gid mcpgroup mcpuser" in dockerfile
    assert "COPY --from=builder --chown=mcpuser:mcpgroup /mcp/.venv /mcp/.venv" in dockerfile
    assert "COPY --chown=mcpuser:mcpgroup wordstat_mcp ./wordstat_mcp" in dockerfile
    assert 'PATH="/mcp/.venv/bin:$PATH"' in dockerfile
    assert "RUN python -m venv /mcp/.venv" not in dockerfile
    assert "USER mcpuser" in dockerfile
    assert dockerfile.index("USER mcpuser") < dockerfile.index('CMD ["wordstat-mcp"]')
