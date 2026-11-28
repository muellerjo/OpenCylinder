from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EntryIn(BaseModel):
    kind: Literal["door", "zone"]
    target: int = Field(ge=1, le=65535)
    profile: int = Field(0, ge=0, le=255)


class EntryOut(EntryIn):
    model_config = ConfigDict(from_attributes=True)


class RoleIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    entries: list[EntryIn] = Field(default_factory=list, max_length=32)


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    entries: list[EntryOut]


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    note: str = ""
    valid_until: datetime | None = None
    roles: list[str] = Field(default_factory=list)          # role keys
    extras: list[EntryIn] = Field(default_factory=list, max_length=32)

    @field_validator("valid_until", mode="before")
    @classmethod
    def empty_none(cls, v):
        return v or None


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int
    status: str
    status_note: str
    card_uid: str | None
    last_written_at: datetime | None
    card_valid_until: int | None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    note: str
    valid_until: datetime | None
    roles: list[str]
    extras: list[EntryOut]
    credentials: list[CredentialOut]

    @field_validator("roles", mode="before")
    @classmethod
    def role_keys(cls, v):
        return [r if isinstance(r, str) else r.key for r in v]


class CredentialIn(BaseModel):
    number: int | None = Field(None, ge=1, le=0xFFFFFFFF)   # None = next free number


class StatusIn(BaseModel):
    status: Literal["active", "blacklisted", "retired"]
    note: str = ""
