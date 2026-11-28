"""Platform administration (tenants, operator accounts) and tenant members (owners)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.audit import record
from ...core.models import ROLES, Membership, Operator, Tenant
from ...core.modules import Module, NavItem
from ...core.security import get_db, hash_password, require_platform_admin
from ...core.tenancy import TenantContext, requires
from ...core.web import attempt, flash, page, redirect
from . import service as S

ui = APIRouter()
api = APIRouter(tags=["platform"])


class _Ctx:
    """Minimal ctx for core.web.attempt outside a tenant."""
    def __init__(self, db):
        self.db = db


# ------------------------------------------------------------- tenants

@ui.get("/platform/tenants")
def tenants(request: Request, db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    rows = db.scalars(select(Tenant).order_by(Tenant.slug)).all()
    return page(request, "platform/tenants.html", rows=rows,
                operators=db.scalars(select(Operator).order_by(Operator.username)).all(), roles=ROLES)


@ui.post("/platform/tenants")
def tenant_create(request: Request, slug: str = Form(...), name: str = Form(""), owner: str = Form(""),
                  db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    def go():
        t = S.create_tenant(db, slug, name, op, request)
        owner_op = db.scalar(select(Operator).where(Operator.username == (owner or op.username)))
        if owner_op is None:
            raise HTTPException(400, f"unknown user {owner}")
        S.set_membership(db, t, owner_op, "owner", op, request)
        return t
    attempt(_Ctx(db), request, go, "Tenant created.")
    return redirect("/platform/tenants", request)


@ui.post("/platform/tenants/{tenant_id}/active")
def tenant_active(request: Request, tenant_id: int, active: str = Form(""), db: Session = Depends(get_db),
                  op=Depends(require_platform_admin)):
    t = db.get(Tenant, tenant_id)
    if t:
        t.active = bool(active)
        record(db, "tenant.active", t.slug, {"active": t.active}, operator=op, request=request)
        flash(request, f"Tenant {t.slug} {'enabled' if t.active else 'disabled'}.")
    return redirect("/platform/tenants", request)


@ui.post("/platform/tenants/{tenant_id}/members")
def platform_member(request: Request, tenant_id: int, username: str = Form(...), role: str = Form(...),
                    db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    t = db.get(Tenant, tenant_id)
    target = db.scalar(select(Operator).where(Operator.username == username.strip().lower()))
    if t is None or target is None:
        flash(request, "unknown tenant or user", "error")
    else:
        attempt(_Ctx(db), request, lambda: S.set_membership(db, t, target, role or None, op, request), "Saved.")
    return redirect("/platform/tenants", request)


# ------------------------------------------------------------- operators

@ui.get("/platform/operators")
def operators(request: Request, db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    return page(request, "platform/operators.html",
                rows=db.scalars(select(Operator).order_by(Operator.username)).all())


@ui.post("/platform/operators")
def operator_create(request: Request, username: str = Form(...), password: str = Form(...),
                    display_name: str = Form(""), platform_admin: str = Form(""),
                    db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    attempt(_Ctx(db), request, lambda: S.create_operator(db, username, password, display_name,
                                                         bool(platform_admin), op, request), "Account created.")
    return redirect("/platform/operators", request)


@ui.post("/platform/operators/{op_id}")
def operator_update(request: Request, op_id: int, active: str = Form(""), password: str = Form(""),
                    db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    target = db.get(Operator, op_id)
    if target is None:
        raise HTTPException(404)
    if target.id == op.id and not active:
        flash(request, "You cannot disable your own account.", "error")
        return redirect("/platform/operators", request)
    target.active = bool(active)
    if password:
        try:
            target.password_hash = hash_password(password)
        except ValueError as e:
            flash(request, str(e), "error")
            return redirect("/platform/operators", request)
    target.session_version += 1
    record(db, "operator.update", target.username, {"active": target.active, "password_reset": bool(password)},
           operator=op, request=request)
    flash(request, "Saved; the user's sessions were logged out.")
    return redirect("/platform/operators", request)


# ------------------------------------------------------------- tenant members (owners)

@ui.get("/t/{tenant}/members")
def members(ctx: TenantContext = Depends(requires("members.manage"))):
    rows = ctx.db.scalars(select(Membership).where(Membership.tenant_id == ctx.tenant.id)).all()
    return page(ctx.request, "platform/members.html", ctx=ctx, rows=rows, roles=ROLES)


@ui.post("/t/{tenant}/members")
def member_set(username: str = Form(...), role: str = Form(""),
               ctx: TenantContext = Depends(requires("members.manage"))):
    target = ctx.db.scalar(select(Operator).where(Operator.username == username.strip().lower()))
    if target is None:
        flash(ctx.request, "unknown user — a platform admin creates accounts", "error")
    else:
        attempt(ctx, ctx.request, lambda: S.set_membership(ctx.db, ctx.tenant, target, role or None,
                                                           ctx.operator, ctx.request), "Saved.")
    return redirect(f"/t/{ctx.tenant.slug}/members", ctx.request)


# ------------------------------------------------------------- JSON API

class TenantIn(BaseModel):
    slug: str
    name: str = ""
    owner: str | None = None


class MemberIn(BaseModel):
    username: str
    role: str | None


@api.get("/platform/tenants")
def api_tenants(db: Session = Depends(get_db), op=Depends(require_platform_admin)):
    return [{"id": t.id, "slug": t.slug, "name": t.name, "active": t.active}
            for t in db.scalars(select(Tenant).order_by(Tenant.slug))]


@api.post("/platform/tenants", status_code=201)
def api_tenant_create(data: TenantIn, request: Request, db: Session = Depends(get_db),
                      op=Depends(require_platform_admin)):
    t = S.create_tenant(db, data.slug, data.name, op, request)
    owner = db.scalar(select(Operator).where(Operator.username == (data.owner or op.username)))
    if owner is None:
        raise HTTPException(400, "unknown owner")
    S.set_membership(db, t, owner, "owner", op, request)
    return {"id": t.id, "slug": t.slug, "name": t.name}


@api.get("/t/{tenant}/members")
def api_members(ctx: TenantContext = Depends(requires("members.manage"))):
    return [{"username": m.operator.username, "role": m.role}
            for m in ctx.db.scalars(select(Membership).where(Membership.tenant_id == ctx.tenant.id))]


@api.put("/t/{tenant}/members")
def api_member_set(data: MemberIn, ctx: TenantContext = Depends(requires("members.manage"))):
    target = ctx.db.scalar(select(Operator).where(Operator.username == data.username.lower()))
    if target is None:
        raise HTTPException(404, "unknown user")
    S.set_membership(ctx.db, ctx.tenant, target, data.role, ctx.operator, ctx.request)
    return {"username": target.username, "role": data.role}


MODULE = Module(
    name="platform", title="Platform & members", api=api, ui=ui,
    nav=[NavItem("Tenants", "/platform/tenants", "platform", None, 10),
         NavItem("Accounts", "/platform/operators", "platform", None, 20),
         NavItem("Members", "/t/{tenant}/members", "tenant", "members.manage", 80)],
)
