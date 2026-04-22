from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from wordstat_mcp.server import (
    find_regions,
    wordstat_env_health,
    get_dynamics,
    get_regions_distribution,
    get_regions_tree,
    get_top,
)


def _configured_credentials() -> dict[str, str]:
    env_values = {
        "WORDSTAT_FOLDER_ID": os.getenv("WORDSTAT_FOLDER_ID"),
        "WORDSTAT_API_KEY": os.getenv("WORDSTAT_API_KEY"),
        "WORDSTAT_IAM_TOKEN": os.getenv("WORDSTAT_IAM_TOKEN"),
    }
    if env_values["WORDSTAT_FOLDER_ID"] and (
        env_values["WORDSTAT_API_KEY"] or env_values["WORDSTAT_IAM_TOKEN"]
    ):
        return {k: v for k, v in env_values.items() if v}

    env_file = Path(".env")
    if not env_file.exists():
        return {}

    file_values = dotenv_values(env_file)
    folder_id = file_values.get("WORDSTAT_FOLDER_ID")
    api_key = file_values.get("WORDSTAT_API_KEY")
    iam_token = file_values.get("WORDSTAT_IAM_TOKEN")
    if folder_id and (api_key or iam_token):
        result = {"WORDSTAT_FOLDER_ID": str(folder_id)}
        if api_key:
            result["WORDSTAT_API_KEY"] = str(api_key)
        if iam_token:
            result["WORDSTAT_IAM_TOKEN"] = str(iam_token)
        return result
    return {}


_LIVE_CREDENTIALS = _configured_credentials()
_RUN_LIVE = os.getenv("WORDSTAT_RUN_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not _RUN_LIVE or not _LIVE_CREDENTIALS,
    reason=(
        "Set WORDSTAT_RUN_LIVE=1 and configure WORDSTAT_* credentials "
        "to run live smoke tests."
    ),
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_wordstat_smoke_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _LIVE_CREDENTIALS.items():
        monkeypatch.setenv(key, value)

    health = await wordstat_env_health()
    top = await get_top(phrases=["python"], pageSize=1)
    dynamics = await get_dynamics(
        phrases=["python"],
        fromDate="2026-01-01T00:00:00Z",
        toDate="2026-01-31T00:00:00Z",
        pageSize=1,
    )
    distribution = await get_regions_distribution(
        phrases=["python"],
        pageSize=1,
    )
    tree = await get_regions_tree()
    regions = await find_regions("Москва", limit=1)

    assert health["status"] == "ok"
    assert top["total"] >= 1
    assert dynamics["total"] >= 1
    assert distribution["total"] >= 1
    assert tree
    assert regions["total"] >= 1
    assert regions["matches"][0]["id"]
