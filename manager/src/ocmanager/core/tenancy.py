"""Tenant context: every tenant-scoped route depends on this.

  /t/{tenant}/...            UI
  /api/v1/t/{tenant}/...     JSON API

The context resolves the tenant from the path, checks the caller's membership
and carries the permission set of the membership role. Tenant data must only
be loaded through ctx (ctx.site(), ctx.get()), never by bare id.
"""

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .models import Membership, Operator, Tenant
from .security import current_operator, get_db

PERMISSIONS: dict[str, set[str]] = {
    "auditor":  {"site.read", "audit.read"},
    "operator": {"site.read", "people.write", "cards.issue"},
    "admin":    {"site.read", "site.write", "people.write", "cards.issue", "locks.manage",
                 "bundles.issue", "audit.read"},
    "owner":    {"site.read", "site.write", "people.write", "cards.issue", "locks.manage",
                 "bundles.issue", "audit.read", "members.manage", "secrets.export"},
}


@dataclass
class TenantContext:
    db: Session
    operator: Operator
    tenant: Tenant
    role: str
    request: Request
    perms: set[str] = field(default_factory=set)

    def can(self, perm: str) -> bool:
        return perm in self.perms

    def require(self, perm: str):
        if perm not in self.perms:
            raise HTTPException(403, f"your role '{self.role}' lacks '{perm}'")

    def site(self, site_id: int):
        from ..modules.sites.models import Site
        s = self.db.get(Site, site_id)
        if s is None or s.tenant_id != self.tenant.id:
            raise HTTPException(404, "site not found")
        return s

    def get(self, model, obj_id: int, site=None):
        """Load a site-scoped row and prove it belongs to this tenant (and site)."""
        obj = self.db.get(model, obj_id)
        if obj is None:
            raise HTTPException(404, f"{model.__name__} not found")
        owner_site = self.site(obj.site_id)
        if site is not None and owner_site.id != site.id:
            raise HTTPException(404, f"{model.__name__} not found")
        return obj

    def audit(self, action: str, target: str = "", **detail):
        record(self.db, action, target, detail, tenant=self.tenant, operator=self.operator,
               request=self.request)


def tenant_ctx(tenant: str, request: Request, db: Session = Depends(get_db),
               op: Operator = Depends(current_operator)) -> TenantContext:
    t = db.scalar(select(Tenant).where(Tenant.slug == tenant))
    if t is None or not t.active:
        raise HTTPException(404, "tenant not found")
    m = db.scalar(select(Membership).where(Membership.tenant_id == t.id,
                                           Membership.operator_id == op.id))
    if m is None:
        raise HTTPException(404, "tenant not found")     # do not reveal that it exists
    request.state.tenant = t
    request.state.role = m.role
    return TenantContext(db, op, t, m.role, request, PERMISSIONS[m.role])


def requires(perm: str):
    def dep(ctx: TenantContext = Depends(tenant_ctx)) -> TenantContext:
        ctx.require(perm)
        return ctx
    return dep
