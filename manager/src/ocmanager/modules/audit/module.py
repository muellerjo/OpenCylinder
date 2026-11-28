from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.models import AuditEvent
from ...core.modules import Module, NavItem
from ...core.security import get_db, require_platform_admin
from ...core.tenancy import TenantContext, requires
from ...core.web import page

ui = APIRouter()
api = APIRouter(tags=["audit"])


def events(db: Session, tenant_id: int | None, q: str = "", limit: int = 300, platform_only=False):
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if platform_only:
        stmt = stmt.where(AuditEvent.tenant_id.is_(None))
    elif tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if q:
        stmt = stmt.where(AuditEvent.action.ilike(f"%{q}%") | AuditEvent.target.ilike(f"%{q}%")
                          | AuditEvent.operator_name.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


@ui.get("/t/{tenant}/audit")
def tenant_audit(q: str = "", ctx: TenantContext = Depends(requires("audit.read"))):
    return page(ctx.request, "audit/list.html", ctx=ctx, events=events(ctx.db, ctx.tenant.id, q), q=q,
                scope="tenant")


@ui.get("/platform/audit")
def platform_audit(request: Request, q: str = "", db: Session = Depends(get_db),
                   _op=Depends(require_platform_admin)):
    """Platform-level events only (logins, tenants, accounts) — not tenants' data."""
    return page(request, "audit/list.html", events=events(db, None, q, platform_only=True), q=q,
                scope="platform")


@api.get("/t/{tenant}/audit")
def tenant_audit_api(q: str = "", limit: int = 300, ctx: TenantContext = Depends(requires("audit.read"))):
    return [{"at": e.at, "operator": e.operator_name, "action": e.action, "target": e.target,
             "detail": e.detail, "ip": e.ip} for e in events(ctx.db, ctx.tenant.id, q, min(limit, 2000))]


MODULE = Module(
    name="audit", title="Audit trail", api=api, ui=ui,
    nav=[NavItem("Audit log", "/t/{tenant}/audit", "tenant", "audit.read", 90),
         NavItem("Platform audit", "/platform/audit", "platform", None, 90)],
)
