from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    status: str
    summary: str
    sequence: int | None
    valid_until: int | None
    card_uid: str | None
    created_by: str
    created_at: datetime
    payload: dict


class MaintenanceIn(BaseModel):
    valid_days: float = Field(2, gt=0, le=30)
    blacklist_only: bool = False


class TargetedIn(BaseModel):
    kind: Literal["commissioning", "decommission", "reassign"]
    door: int | None = None
    valid_days: float = Field(2, gt=0, le=30)


class PlanIn(BaseModel):
    uid: str | None = Field(None, description="card UID, 14 hex digits (not needed for commissioning cards)")
    app_exists: bool = False


class WrittenIn(BaseModel):
    uid: str | None = None
    log: str = ""
