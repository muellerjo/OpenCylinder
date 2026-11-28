"""Sites and their building structure: zones, doors, time profiles, sealed secrets.

Zone, door and profile *numbers* are the IDs that go onto cards and into
locks; they are fixed once created (renumbering would silently change what
issued cards open).
"""

from sqlalchemy import JSON, BigInteger, Boolean, Column, ForeignKey, Integer, LargeBinary, String, Table, \
    UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.db import Base, Timestamped

door_zone = Table(
    "door_zone", Base.metadata,
    Column("door_id", ForeignKey("door.id", ondelete="CASCADE"), primary_key=True),
    Column("zone_id", ForeignKey("zone.id", ondelete="CASCADE"), primary_key=True),
)


class Site(Timestamped, Base):
    __tablename__ = "site"
    __table_args__ = (UniqueConstraint("tenant_id", "aid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    aid: Mapped[str] = mapped_column(String(6))             # user application, e.g. 4F4331
    admin_aid: Mapped[str] = mapped_column(String(6))       # admin application, e.g. 4F4341
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    posix_tz: Mapped[str] = mapped_column(String(64), default="CET-1CEST,M3.5.0,M10.5.0/3")
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)   # monotonic bundle sequence
    dev_keys: Mapped[bool] = mapped_column(Boolean, default=False)      # public bench test keys!
    zones: Mapped[list["Zone"]] = relationship(back_populates="site", cascade="all, delete-orphan",
                                               order_by="Zone.number")
    doors: Mapped[list["Door"]] = relationship(back_populates="site", cascade="all, delete-orphan",
                                               order_by="Door.number")
    profiles: Mapped[list["TimeProfile"]] = relationship(back_populates="site", cascade="all, delete-orphan",
                                                         order_by="TimeProfile.number")
    secrets: Mapped[list["SiteSecret"]] = relationship(cascade="all, delete-orphan")


class SiteSecret(Base):
    __tablename__ = "site_secret"
    __table_args__ = (UniqueConstraint("site_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(32))
    blob: Mapped[bytes] = mapped_column(LargeBinary)


class Zone(Timestamped, Base):
    __tablename__ = "zone"
    __table_args__ = (UniqueConstraint("site_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    site: Mapped[Site] = relationship(back_populates="zones")
    doors: Mapped[list["Door"]] = relationship(secondary=door_zone, back_populates="zones")


class Door(Timestamped, Base):
    __tablename__ = "door"
    __table_args__ = (UniqueConstraint("site_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    site: Mapped[Site] = relationship(back_populates="doors")
    zones: Mapped[list[Zone]] = relationship(secondary=door_zone, back_populates="doors",
                                             order_by="Zone.number")

    @property
    def zone_numbers(self) -> list[int]:
        return [z.number for z in self.zones]


class TimeProfile(Timestamped, Base):
    __tablename__ = "time_profile"
    __table_args__ = (UniqueConstraint("site_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)                # 1..255, 0 = always (implicit)
    name: Mapped[str] = mapped_column(String(200))
    days: Mapped[list] = mapped_column(JSON)                    # ["Mon", ...]
    intervals: Mapped[list] = mapped_column(JSON)               # [{"from": "06:00", "to": "20:00"}], max 2
    site: Mapped[Site] = relationship(back_populates="profiles")

    def as_dict(self):
        return {"id": self.number, "days": self.days, "intervals": self.intervals}
