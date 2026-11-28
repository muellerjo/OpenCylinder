from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LockIn(BaseModel):
    qr: str = Field(description="OC1:<device ID>:<compressed public key> (engraving / identify card)")
    label: str = ""
    note: str = ""


class LockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str
    public_key: str
    label: str
    door_number: int | None
    state: str
    last_sequence: int | None
    commissioned_at: datetime | None
    note: str
