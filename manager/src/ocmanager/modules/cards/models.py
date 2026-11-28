"""Card jobs: every card the manager prepares (user, maintenance, commissioning,
decommission, reassignment). The payload is fixed when the job is created
(sequence, signature); the Proxmark plan is derived from it plus the card UID.
"""

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base, Timestamped

JOB_KINDS = {
    "user": "User card",
    "maintenance": "Maintenance card (time, blacklist, profiles, TZ)",
    "blacklist": "Blacklist update card",
    "commissioning": "Commissioning card (one lock)",
    "decommission": "Decommission card (one lock)",
    "reassign": "Reassignment card (one lock: new door / zones)",
}
JOB_STATES = ("prepared", "written", "failed", "cancelled")


class CardJob(Timestamped, Base):
    __tablename__ = "card_job"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="prepared")
    credential_id: Mapped[int | None] = mapped_column(ForeignKey("credential.id", ondelete="SET NULL"))
    lock_id: Mapped[int | None] = mapped_column(ForeignKey("lock.id", ondelete="SET NULL"))
    sequence: Mapped[int | None] = mapped_column(BigInteger)
    valid_until: Mapped[int | None] = mapped_column(BigInteger)
    summary: Mapped[str] = mapped_column(String(300), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)     # hex strings: file0/file1/header/bundle
    card_uid: Mapped[str | None] = mapped_column(String(14))
    created_by: Mapped[str] = mapped_column(String(64), default="")
    log: Mapped[str] = mapped_column(Text, default="")
