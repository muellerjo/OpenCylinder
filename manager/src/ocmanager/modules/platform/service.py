import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.audit import record
from ...core.models import ROLES, Membership, Operator, Tenant
from ...core.security import hash_password

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")


def create_tenant(db: Session, slug: str, name: str, actor=None, request=None) -> Tenant:
    slug = slug.strip().lower()
    if not SLUG.match(slug):
        raise HTTPException(400, "slug: 2-48 characters a-z, 0-9, '-'")
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        raise HTTPException(409, f"tenant {slug} exists")
    t = Tenant(slug=slug, name=name.strip() or slug)
    db.add(t)
    db.flush()
    record(db, "tenant.create", slug, {"name": t.name}, operator=actor, request=request)
    return t


def create_operator(db: Session, username: str, password: str, display_name: str = "",
                    platform_admin: bool = False, actor=None, request=None) -> Operator:
    username = username.strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9._-]{1,63}$", username):
        raise HTTPException(400, "user name: 2-64 characters a-z, 0-9, '.', '_', '-'")
    if db.scalar(select(Operator).where(Operator.username == username)):
        raise HTTPException(409, f"user {username} exists")
    try:
        ph = hash_password(password)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    op = Operator(username=username, display_name=display_name or username, password_hash=ph,
                  is_platform_admin=platform_admin)
    db.add(op)
    db.flush()
    record(db, "operator.create", username, {"platform_admin": platform_admin}, operator=actor, request=request)
    return op


def owners(db: Session, tenant: Tenant) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(
        Membership.tenant_id == tenant.id, Membership.role == "owner")) or 0


def set_membership(db: Session, tenant: Tenant, op: Operator, role: str | None, actor=None, request=None):
    """role None = remove. Never leaves a tenant without an owner."""
    if role is not None and role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    m = db.scalar(select(Membership).where(Membership.tenant_id == tenant.id, Membership.operator_id == op.id))
    if m is not None and m.role == "owner" and role != "owner" and owners(db, tenant) <= 1:
        raise HTTPException(409, "a tenant needs at least one owner")
    if role is None:
        if m:
            db.delete(m)
    elif m:
        m.role = role
    else:
        db.add(Membership(tenant_id=tenant.id, operator_id=op.id, role=role))
    db.flush()
    record(db, "member.set", f"{tenant.slug}/{op.username}", {"role": role}, tenant=tenant, operator=actor,
           request=request)
