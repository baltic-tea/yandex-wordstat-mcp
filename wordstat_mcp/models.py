from __future__ import annotations
from numbers import Integral

from datetime import datetime, UTC, timedelta
from typing import Any, Literal, Self
from typing_extensions import NotRequired, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

WordstatDevices = Literal[
    "DEVICE_ALL", "DEVICE_DESKTOP", "DEVICE_PHONE", "DEVICE_TABLET"
]
WordstatPeriods = Literal["PERIOD_DAILY", "PERIOD_WEEKLY", "PERIOD_MONTHLY"]
WordstatRegionModes = Literal["REGION_ALL", "REGION_REGIONS", "REGION_CITIES"]


# -----------------------------------------------------------------------------
# Tool response models (for structured tool output parsing).
# -----------------------------------------------------------------------------
class RegionIndexResponse(TypedDict):
    by_name: dict[str, list[str]]
    by_id: dict[str, dict[str, Any]]
    message: NotRequired[str]
    next_action: NotRequired[str]


class RegionMatch(TypedDict):
    id: str
    name: str
    path: list[str]
    matchType: str


class RegionSearchResponse(TypedDict):
    query: str
    matches: list[RegionMatch]
    total: int
    message: str
    next_action: str


class PaginatedResponseBase(TypedDict):
    page: int
    pageSize: int
    total: int
    totalPages: int
    hasNextPage: bool
    hasPreviousPage: bool
    message: str
    next_action: str
    warnings: NotRequired[list[str]]


class TopQueryItem(TypedDict):
    phrase: str
    top: dict[str, Any]


class GetTopResponse(PaginatedResponseBase):
    items: list[TopQueryItem]


class DynamicsQueryItem(TypedDict):
    phrase: str
    dynamics: dict[str, Any]


class GetDynamicsResponse(PaginatedResponseBase):
    items: list[DynamicsQueryItem]


class RegionsDistributionQueryItem(TypedDict):
    phrase: str
    distribution: dict[str, Any]


class GetRegionsDistributionResponse(PaginatedResponseBase):
    items: list[RegionsDistributionQueryItem]


# -----------------------------------------------------------------------------
# API request models (for Wordstat API interactions).
# -----------------------------------------------------------------------------
def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day(value: datetime) -> datetime:
    return value.replace(hour=23, minute=59, second=59, microsecond=999999)


def fix_date_range(
    period: WordstatPeriods | str,
    from_date: datetime | None,
    to_date: datetime | None = None,
    enable_period_rules: bool = True,
) -> tuple[datetime, datetime]:
    """Fix raw dates to a Wordstat-compatible range."""

    if from_date is None:
        raise ValueError("from_date is required.")

    dt_from = from_date
    dt_to = to_date if to_date else datetime.now(UTC)

    if ensure_utc(dt_from) > ensure_utc(dt_to):
        dt_from, dt_to = dt_to, dt_from

    if enable_period_rules:
        match period:
            case "PERIOD_MONTHLY":
                dt_from = dt_from.replace(day=1)
                next_month = (dt_to.replace(day=28) + timedelta(days=4)).replace(day=1)
                dt_to = next_month - timedelta(days=1)
            case "PERIOD_WEEKLY":
                dt_from = dt_from - timedelta(days=dt_from.weekday())
                dt_to = dt_to - timedelta(days=dt_to.weekday()) + timedelta(days=6)
            case "PERIOD_DAILY":
                pass
            case _:
                raise ValueError(f"Unsupported period: {period}")

    return start_of_day(dt_from), end_of_day(dt_to)


class CustomModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class PhraseModel(CustomModel):
    phrase: str = Field(min_length=1, max_length=400)


class RegionsDevicesModel(PhraseModel):
    regions: list[str] = Field(default_factory=list, max_length=100)
    devices: list[WordstatDevices] = Field(default_factory=list, max_length=3)

    @field_validator("regions", mode="before")
    @classmethod
    def validate_regions(cls, value: list[Any] | None) -> list[str]:
        if value is None:
            return []

        result = []
        for rid in value:
            if isinstance(rid, bool):
                raise ValueError(f"Region ID must be numeric: {rid}")
            elif isinstance(rid, Integral):
                if rid <= 0:
                    raise ValueError(f"Region ID must be positive: {rid}")
                result.append(str(rid))
            elif isinstance(rid, str):
                rid = rid.strip()
                if rid.isdecimal() and int(rid) > 0:
                    result.append(rid)
                else:
                    raise ValueError(f"Region ID must be positive numeric: {rid}")
            else:
                raise ValueError(f"Region ID must be numeric: {rid}")
        return result

    @field_validator("devices", mode="before")
    @classmethod
    def validate_devices(
        cls, value: list[WordstatDevices] | None
    ) -> list[WordstatDevices]:
        if value is None:
            return []
        return value


class GetTopRequest(RegionsDevicesModel):
    num_phrases: int = Field(default=50, alias="numPhrases", ge=1, le=2000)


class GetDynamicsRequest(RegionsDevicesModel):
    period: WordstatPeriods = "PERIOD_MONTHLY"
    from_date: datetime = Field(alias="fromDate")
    to_date: datetime | None = Field(default=None, alias="toDate")

    @field_validator("to_date", mode="before")
    @classmethod
    def validate_to_date(cls, value: Any) -> datetime:
        if value is None:
            return datetime.now(UTC)
        return value

    @model_validator(mode="after")
    def validate_and_fix_date_range(self) -> Self:
        self.from_date, self.to_date = fix_date_range(
            period=self.period,
            from_date=self.from_date,
            to_date=self.to_date,
        )
        return self

    @field_serializer("from_date", "to_date")
    def serialize_dates(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return ensure_utc(value).isoformat().replace("+00:00", "Z")


class GetRegionsDistributionRequest(PhraseModel):
    region: WordstatRegionModes = "REGION_ALL"
    devices: list[WordstatDevices] | None = Field(default=None, max_length=3)


class GetRegionsTreeRequest(CustomModel):
    """The request requires only the `folderId` to be passed."""

    pass
