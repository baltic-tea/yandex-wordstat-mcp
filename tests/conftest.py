from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wordstat_mcp.api_settings import WordstatSettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def wordstat_settings() -> WordstatSettings:
    return WordstatSettings(
        folder_id="folder-1",
        api_key="secret-key",
        timeout_seconds=3,
        backoff_seconds=0.5,
        max_backoff_seconds=8.0,
        max_attempts=3,
        max_concurrency=2,
    )


@pytest.fixture
def wordstat_settings_int() -> WordstatSettings:
    return WordstatSettings(
        folder_id="folder-1",
        api_key="secret-key",
        timeout_seconds=3,
        backoff_seconds=1,
        max_backoff_seconds=10,
        max_attempts=3,
        max_concurrency=2,
    )
