from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from wordstat_mcp.models import (
    GetDynamicsRequest,
    GetRegionsDistributionRequest,
    GetRegionsTreeRequest,
    GetTopRequest,
    fix_date_range,
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
        regions=[213, " 2 "],
        devices=["DEVICE_DESKTOP"],
    )

    assert request.regions == ["213", "2"]
    assert request.to_payload() == {
        "phrase": "python",
        "regions": ["213", "2"],
        "devices": ["DEVICE_DESKTOP"],
        "numPhrases": 10,
    }


@pytest.mark.parametrize(
    "regions",
    [["moscow"], [1.5], [object()], [True], [False], [0], [-1], ["0"], ["-1"]],
)
def test_get_top_request_rejects_non_numeric_regions(regions: list[object]) -> None:
    with pytest.raises(ValidationError, match="Region ID must be"):
        GetTopRequest(phrase="python", regions=regions)


def test_get_top_request_rejects_phrase_too_long() -> None:
    with pytest.raises(ValidationError, match="at most 400 characters"):
        GetTopRequest(phrase="x" * 401)


def test_get_top_request_enforces_region_and_device_limits() -> None:
    with pytest.raises(ValidationError, match="at most 100 items"):
        GetTopRequest(phrase="python", regions=list(range(1, 102)))

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
        "fromDate": "2025-12-31T21:00:00Z",
        "toDate": "2026-01-31T23:59:59.999999Z",
    }


def test_get_dynamics_request_serializes_naive_datetimes_as_utc() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        fromDate=datetime(2026, 1, 1, 0, 0, 0),
        toDate=datetime(2026, 1, 31, 0, 0, 0),
    )

    assert request.to_payload()["fromDate"] == "2026-01-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-01-31T23:59:59.999999Z"


def test_get_dynamics_request_requires_from_date() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        GetDynamicsRequest(phrase="python")


@pytest.mark.parametrize(
    ("period", "expected_to"),
    [
        ("PERIOD_MONTHLY", "2026-04-30T23:59:59.999999Z"),
        ("PERIOD_WEEKLY", "2026-04-26T23:59:59.999999Z"),
        ("PERIOD_DAILY", "2026-04-21T23:59:59.999999Z"),
    ],
)
def test_get_dynamics_request_none_to_date_uses_current_utc_period_boundary(
    monkeypatch: pytest.MonkeyPatch,
    period: str,
    expected_to: str,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "FrozenDateTime":
            current = cls(2026, 4, 21, 12, 34, 56, tzinfo=UTC)
            if tz is None:
                return current.replace(tzinfo=None)
            return current

    monkeypatch.setattr("wordstat_mcp.models.datetime", FrozenDateTime)

    request = GetDynamicsRequest(
        phrase="python",
        period=period,
        fromDate="2026-04-09T00:00:00Z",
        toDate=None,
    )

    assert request.to_payload()["toDate"] == expected_to


def test_get_dynamics_request_uses_input_timezone_for_period_boundaries() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_MONTHLY",
        fromDate="2026-04-01T00:30:00+03:00",
        toDate="2026-04-02T00:00:00+03:00",
    )

    assert request.to_payload()["fromDate"] == "2026-03-31T21:00:00Z"
    assert request.to_payload()["toDate"] == "2026-04-30T20:59:59.999999Z"


def test_get_dynamics_request_omitted_to_date_uses_current_utc_period_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "FrozenDateTime":
            current = cls(2026, 4, 21, 12, 34, 56, tzinfo=UTC)
            if tz is None:
                return current.replace(tzinfo=None)
            return current

    monkeypatch.setattr("wordstat_mcp.models.datetime", FrozenDateTime)

    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_DAILY",
        fromDate="2026-04-09T00:00:00Z",
    )

    assert request.to_payload()["toDate"] == "2026-04-21T23:59:59.999999Z"


@pytest.mark.parametrize(
    ("period", "from_date", "to_date", "expected_from", "expected_to"),
    [
        (
            "PERIOD_MONTHLY",
            datetime(2026, 4, 9, 13, 15, tzinfo=UTC),
            datetime(2026, 4, 9, 13, 15, tzinfo=UTC),
            "2026-04-01T00:00:00+00:00",
            "2026-04-30T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_WEEKLY",
            datetime(2026, 4, 9, 13, 15, tzinfo=UTC),
            datetime(2026, 4, 9, 13, 15, tzinfo=UTC),
            "2026-04-06T00:00:00+00:00",
            "2026-04-12T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_DAILY",
            datetime(2026, 4, 9, 13, 15, tzinfo=UTC),
            datetime(2026, 4, 9, 23, 59, tzinfo=UTC),
            "2026-04-09T00:00:00+00:00",
            "2026-04-09T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_MONTHLY",
            datetime(2026, 4, 9, tzinfo=UTC),
            datetime(2026, 5, 2, tzinfo=UTC),
            "2026-04-01T00:00:00+00:00",
            "2026-05-31T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_WEEKLY",
            datetime(2026, 4, 29, tzinfo=UTC),
            datetime(2026, 5, 3, tzinfo=UTC),
            "2026-04-27T00:00:00+00:00",
            "2026-05-03T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_DAILY",
            datetime(2026, 4, 30, 22, 30, tzinfo=UTC),
            datetime(2026, 5, 1, 1, 15, tzinfo=UTC),
            "2026-04-30T00:00:00+00:00",
            "2026-05-01T23:59:59.999999+00:00",
        ),
        (
            "PERIOD_MONTHLY",
            datetime(2026, 5, 2, tzinfo=UTC),
            datetime(2026, 4, 9, tzinfo=UTC),
            "2026-04-01T00:00:00+00:00",
            "2026-05-31T23:59:59.999999+00:00",
        ),
    ],
)
def test_fix_date_range_outputs_expected_period_boundaries(
    period: str,
    from_date: datetime,
    to_date: datetime,
    expected_from: str,
    expected_to: str,
) -> None:
    fixed_from, fixed_to = fix_date_range(period, from_date, to_date)

    assert fixed_from.isoformat() == expected_from
    assert fixed_to.isoformat() == expected_to


def test_get_dynamics_request_normalizes_monthly_date_range() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_MONTHLY",
        fromDate="2026-04-09T00:00:00Z",
        toDate="2026-04-21T00:00:00Z",
    )

    assert request.to_payload()["fromDate"] == "2026-04-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-04-30T23:59:59.999999Z"


def test_get_dynamics_request_normalizes_future_monthly_to_date_to_month_end() -> None:
    request = GetDynamicsRequest(
        phrase="заказать роллы",
        period="PERIOD_MONTHLY",
        fromDate="2026-01-01T23:59:59.999999Z",
        toDate="2026-04-15T23:59:59.999999Z",
    )

    assert request.to_payload()["fromDate"] == "2026-01-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-04-30T23:59:59.999999Z"


def test_get_dynamics_request_preserves_future_month_end_as_period_end() -> None:
    request = GetDynamicsRequest(
        phrase="заказать роллы",
        period="PERIOD_MONTHLY",
        fromDate="2026-01-01T00:00:00Z",
        toDate="2028-02-29T12:34:56Z",
    )

    assert request.to_payload()["fromDate"] == "2026-01-01T00:00:00Z"
    assert request.to_payload()["toDate"] == "2028-02-29T23:59:59.999999Z"


def test_get_dynamics_request_normalizes_weekly_date_range() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_WEEKLY",
        fromDate="2026-04-09T00:00:00Z",
        toDate="2026-04-21T00:00:00Z",
    )

    assert request.to_payload()["fromDate"] == "2026-04-06T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-04-26T23:59:59.999999Z"


def test_get_dynamics_request_normalizes_future_weekly_dates_to_monday_sunday() -> None:
    request = GetDynamicsRequest(
        phrase="заказать роллы",
        period="PERIOD_WEEKLY",
        fromDate="2026-06-04T23:59:59.999999Z",
        toDate="2026-04-30T23:59:59.999999Z",
    )

    assert request.to_payload()["fromDate"] == "2026-04-27T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-06-07T23:59:59.999999Z"


def test_get_dynamics_request_preserves_future_sunday_as_period_end() -> None:
    request = GetDynamicsRequest(
        phrase="заказать роллы",
        period="PERIOD_WEEKLY",
        fromDate="2026-01-01T00:00:00Z",
        toDate="2027-01-03T12:34:56Z",
    )

    assert request.to_payload()["fromDate"] == "2025-12-29T00:00:00Z"
    assert request.to_payload()["toDate"] == "2027-01-03T23:59:59.999999Z"


def test_get_dynamics_request_normalizes_daily_date_range() -> None:
    request = GetDynamicsRequest(
        phrase="python",
        period="PERIOD_DAILY",
        fromDate="2026-04-21T15:34:56Z",
        toDate="2026-04-09T23:59:59Z",
    )

    assert request.to_payload()["fromDate"] == "2026-04-09T00:00:00Z"
    assert request.to_payload()["toDate"] == "2026-04-21T23:59:59.999999Z"


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
