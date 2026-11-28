"""Platform models: tenants, operator accounts, memberships, API tokens, audit log.

Tenancy model: one database, every domain row belongs to exactly one tenant
(directly or through its site). All tenant data is reached through a
TenantContext (core/tenancy.py) that checks the membership first — there is no
query path without a tenant. Platform admins manage tenants and accounts but
see a tenant's data only if they are a member of it.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, Timestamped, utcnow


class Tenant(Timestamped, Base):
    __tablename__ = "tenant"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="tenant",
                                                           cascade="all, delete-orphan")


class Operator(Timestamped, Base):
    """A person who logs into the manager (not a cardholder)."""
    __tablename__ = "operator"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1)   # bump = log out everywhere
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    memberships: Mapped[list["Membership"]] = relationship(back_populates="operator",
                                                           cascade="all, delete-orphan")


ROLES = ("owner", "admin", "operator", "auditor")


class Membership(Timestamped, Base):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("tenant_id", "operator_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"))
    operator_id: Mapped[int] = mapped_column(ForeignKey("operator.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    operator: Mapped[Operator] = relationship(back_populates="memberships")


class ApiToken(Timestamped, Base):
    """Bearer token for scripts / an encoder agent. Only the SHA-256 is stored."""
    __tablename__ = "api_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operator.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator: Mapped[Operator] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operator.id", ondelete="SET NULL"))
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
