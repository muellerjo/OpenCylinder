"""Cardholders, their credentials (cards) and access roles.

- AccessRole: a template ("Nurse, ward 1") — a list of door/zone entries.
- Person: a cardholder; gets the entries of its roles plus individual extras.
- Credential: one physical card with its on-card credential_id. A lost card is
  blacklisted and the person gets a new credential; the history stays.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.db import Base, Timestamped

person_role = Table(
    "person_role", Base.metadata,
    Column("person_id", ForeignKey("person.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("access_role.id", ondelete="CASCADE"), primary_key=True),
)


class AccessRole(Timestamped, Base):
    __tablename__ = "access_role"
    __table_args__ = (UniqueConstraint("site_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    entries: Mapped[list["AccessEntry"]] = relationship(
        cascade="all, delete-orphan", primaryjoin="AccessRole.id == AccessEntry.role_id",
        order_by="AccessEntry.position")
    people: Mapped[list["Person"]] = relationship(secondary=person_role, back_populates="roles")


class AccessEntry(Base):
    """One door or zone right (+ time profile number, 0 = always)."""
    __tablename__ = "access_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("access_role.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(4))          # "door" | "zone"
    target: Mapped[int] = mapped_column(Integer)          # door / zone number
    profile: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)

    def as_dict(self):
        return {self.kind: self.target, **({"profile": self.profile} if self.profile else {})}


class Person(Timestamped, Base):
    __tablename__ = "person"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    roles: Mapped[list[AccessRole]] = relationship(secondary=person_role, back_populates="people",
                                                   order_by="AccessRole.key")
    extras: Mapped[list[AccessEntry]] = relationship(
        cascade="all, delete-orphan", primaryjoin="Person.id == AccessEntry.person_id",
        order_by="AccessEntry.position")
    credentials: Mapped[list["Credential"]] = relationship(back_populates="person",
                                                           cascade="all, delete-orphan",
                                                           order_by="Credential.id")

    @property
    def active_credential(self):
        return next((c for c in reversed(self.credentials) if c.status == "active"), None)


CRED_STATES = ("active", "blacklisted", "retired")


class Credential(Timestamped, Base):
    __tablename__ = "credential"
    __table_args__ = (UniqueConstraint("site_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(BigInteger)        # on-card credential_id (u32)
    status: Mapped[str] = mapped_column(String(16), default="active")
    status_note: Mapped[str] = mapped_column(Text, default="")
    card_uid: Mapped[str | None] = mapped_column(String(14))
    last_written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    card_valid_until: Mapped[int | None] = mapped_column(BigInteger)   # as written on the card
    person: Mapped[Person] = relationship(back_populates="credentials")
