"""Lock registry. A lock is known by its device identity (QR: OC1:<device ID>:<public key>).

Locks are offline: the manager only knows what it issued. States follow the
cards written for a lock and the operator's confirmation after the tap.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base, Timestamped

LOCK_STATES = {
    "registered": "known, blank (factory) — not commissioned yet",
    "commissioning": "commissioning card issued, waiting for the tap",
    "owned": "commissioned and confirmed",
    "decommissioning": "decommission card issued, waiting for the tap",
    "factory": "decommissioned (confirmed) — blank again",
}


class Lock(Timestamped, Base):
    __tablename__ = "lock"
    __table_args__ = (UniqueConstraint("site_id", "device_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(16))          # hex, 8 bytes
    public_key: Mapped[str] = mapped_column(String(66))         # hex, compressed P-256
    label: Mapped[str] = mapped_column(String(200), default="")
    door_number: Mapped[int | None] = mapped_column(Integer)    # door it is (or will be) commissioned to
    state: Mapped[str] = mapped_column(String(16), default="registered")
    last_sequence: Mapped[int | None] = mapped_column(BigInteger)
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text, default="")

    @property
    def qr(self) -> str:
        return f"OC1:{self.device_id}:{self.public_key}"
