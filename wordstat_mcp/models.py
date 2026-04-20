from __future__ import annotations
from typing_extensions import Self
import numbers

from datetime import datetime, UTC
from typing import Any, Literal

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
            if isinstance(rid, numbers.Integral):
                result.append(str(rid))
            elif isinstance(rid, str) and rid.isdigit():
                result.append(rid)
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
    to_date: datetime | None = Field(
        default_factory=lambda: datetime.now(UTC), alias="toDate"
    )

    @field_validator("to_date", mode="before")
    @classmethod
    def validate_to_date(cls, value: Any) -> datetime:
        if value is None:
            return datetime.now(UTC)
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.to_date is None:
            return self
        if self.from_date > self.to_date:
            return self.model_copy(
                update={"from_date": self.to_date, "to_date": self.from_date}
            )
        return self

    @field_serializer("from_date", "to_date")
    def serialize_dt(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class GetRegionsDistributionRequest(PhraseModel):
    region: WordstatRegionModes = "REGION_ALL"
    devices: list[WordstatDevices] | None = Field(default=None, max_length=3)


class GetRegionsTreeRequest(CustomModel):
    """The request requires only the `folderId` to be passed."""

    pass
