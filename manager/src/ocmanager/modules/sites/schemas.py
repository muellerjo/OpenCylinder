import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...protocol.bundle import DAYS

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")
Aid = Annotated[str, Field(pattern=r"^[0-9A-Fa-f]{6}$")]


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aid: Aid
    admin_aid: Aid
    timezone: str = "Europe/Berlin"
    posix_tz: str = Field("CET-1CEST,M3.5.0,M10.5.0/3", max_length=60)

    @field_validator("aid", "admin_aid")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("timezone")
    @classmethod
    def tz_exists(cls, v: str) -> str:
        from zoneinfo import ZoneInfo
        ZoneInfo(v)
        return v

    @model_validator(mode="after")
    def distinct(self):
        if self.aid == self.admin_aid:
            raise ValueError("user and admin AID must differ")
        if "4F434B" in (self.aid, self.admin_aid):
            raise ValueError("4F434B is reserved for commissioning cards")
        return self


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    aid: str
    admin_aid: str
    timezone: str
    posix_tz: str
    last_sequence: int
    dev_keys: bool


class ZoneIn(BaseModel):
    number: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1, max_length=200)


class ZoneOut(ZoneIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DoorIn(BaseModel):
    number: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1, max_length=200)
    zones: list[int] = Field(default_factory=list, max_length=16)   # zone numbers


class DoorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int
    name: str
    zones: list[int] = Field(validation_alias="zone_numbers")


class Interval(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("from_", "to")
    @classmethod
    def hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM (00:00 … 24:00)")
        return v

    def as_dict(self):
        return {"from": self.from_, "to": self.to}


class ProfileIn(BaseModel):
    number: int = Field(ge=1, le=255)
    name: str = Field(min_length=1, max_length=200)
    days: list[str] = Field(min_length=1)
    intervals: list[Interval] = Field(min_length=1, max_length=2)

    @field_validator("days")
    @classmethod
    def days_ok(cls, v):
        bad = [d for d in v if d not in DAYS]
        if bad:
            raise ValueError(f"unknown day(s) {bad}")
        return [d for d in DAYS if d in v]


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int
    name: str
    days: list[str]
    intervals: list[dict]
