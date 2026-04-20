from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from wordstat_mcp.models import (
    GetDynamicsRequest,
    GetRegionsDistributionRequest,
    GetRegionsTreeRequest,
    GetTopRequest,
)


def test_get_top_request_normalizes_regions_and_devices_defaults() -> None:
    request = GetTopRequest(phrase="  python  ", regions=None, devices=None)

    assert request.phrase == "python"
    assert request.to_payload() == {
        "phrase": "python",
        "regions": [],
        "devices": [],
        "numPhrases": 50,
    }


def test_get_top_request_accepts_integer_and_numeric_string_regions() -> None:
    request = GetTopRequest(
        phrase="python",
        numPhrases=10,
        regions=[213, "2"],
        devices=["DEVICE_DESKTOP"],
    )

    assert request.regions == ["213", "2"]
    assert request.to_payload() == {
        "phrase": "python",
        "regions": ["213", "2"],
        "devices": ["DEVICE_DESKTOP"],
        "numPhrases": 10,
    }


@pytest.mark.parametrize("regions", [["moscow"], [1.5], [object()]])
def test_get_top_request_rejects_non_numeric_regions(regions: list[object]) -> None:
    with pytest.raises(ValidationError, match="Region ID must be numeric"):
        GetTopRequest(phrase="python", regions=regions)


def test_get_top_request_rejects_phrase_too_long() -> None:
    with pytest.raises(ValidationError, match="at most 400 characters"):
        GetTopRequest(phrase="x" * 401)


def test_get_top_request_enforces_region_and_device_limits() -> None:
    with pytest.raises(ValidationError, match="at most 100 items"):
        GetTopRequest(phrase="python", regions=list(range(101)))

    with pytest.raises(ValidationError, match="at most 3 items"):
        GetTopRequest(
            phrase="python",
            devices=[
                "DEVICE_ALL",
                "DEVICE_DESKTOP",
                "DEVICE_PHONE",
                "DEVICE_TABLET",
            ],
        )


def test_get_dynamics_request_serializes_rfc3339_timestamps() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_DAILY",
        fromDate="2026-01-01T03:00:00+03:00",
        toDate="2026-01-31T00:00:00Z",
    )

    assert request.to_payload() == {
        "phrase": "python",
        "regions": [],
        "devices": [],
        "period": "PERIOD_DAILY",
        "fromDate": "2026-01-01T00:00:00Z",
        "toDate": "2026-01-31T00:00:00Z",
    }


def test_get_dynamics_request_serializes_naive_datetimes_as_utc() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        fromDate=datetime(2026, 1, 1, 0, 0, 0),
        toDate=datetime(2026, 1, 31, 0, 0, 0),
    )

    assert request.to_payload()["fromDate"] == "2026-01-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-01-31T00:00:00Z"


def test_get_dynamics_request_preserves_inverted_date_range() -> None:
    with pytest.warns(UserWarning, match="returning a value other than `self`"):
        request = GetDynamicsRequest(
            phrase="python",
            fromDate="2026-02-01T00:00:00Z",
            toDate="2026-01-01T00:00:00Z",
        )

    assert request.to_payload()["fromDate"] == "2026-02-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-01-01T00:00:00Z"


def test_request_models_keep_raw_api_aliases() -> None:
    top_request = GetTopRequest(phrase="python", numPhrases=10)
    dynamics_request = GetDynamicsRequest(
        phrase="python",
        fromDate="2026-01-01T00:00:00Z",
        toDate="2026-01-31T00:00:00Z",
    )

    assert top_request.num_phrases == 10
    assert dynamics_request.from_date.isoformat().startswith("2026-01-01")


def test_get_regions_distribution_request_payload() -> None:
    request = GetRegionsDistributionRequest(
        phrase="python",
        region="REGION_CITIES",
        devices=["DEVICE_PHONE"],
    )

    assert request.to_payload() == {
        "phrase": "python",
        "region": "REGION_CITIES",
        "devices": ["DEVICE_PHONE"],
    }


def test_get_regions_distribution_request_omits_none_devices() -> None:
    request = GetRegionsDistributionRequest(phrase="python")

    assert request.to_payload() == {
        "phrase": "python",
        "region": "REGION_ALL",
    }


def test_regions_tree_request_payload_is_empty() -> None:
    assert GetRegionsTreeRequest().to_payload() == {}
