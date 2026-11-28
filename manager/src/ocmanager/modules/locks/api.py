from fastapi import APIRouter, Body, Depends

from ...core.tenancy import TenantContext, requires
from . import service as L
from .models import Lock
from .schemas import LockIn, LockOut

router = APIRouter(prefix="/t/{tenant}/sites/{site_id}/locks", tags=["locks"])
READ, MANAGE = requires("site.read"), requires("locks.manage")


@router.get("", response_model=list[LockOut])
def locks(site_id: int, ctx: TenantContext = Depends(READ)):
    return L.list_locks(ctx, ctx.site(site_id))


@router.post("", response_model=LockOut, status_code=201)
def register(site_id: int, data: LockIn, ctx: TenantContext = Depends(MANAGE)):
    return L.register(ctx, ctx.site(site_id), data.qr, data.label, data.note)


@router.post("/import-local", summary="Import examples/hospital/locks.local.json (bench)")
def import_local(site_id: int, data: dict = Body(...), ctx: TenantContext = Depends(MANAGE)):
    return {"imported": L.import_locks_local(ctx, ctx.site(site_id), data)}


@router.get("/{lock_id}", response_model=LockOut)
def get_lock(site_id: int, lock_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.get(Lock, lock_id, ctx.site(site_id))


@router.post("/{lock_id}/confirm", response_model=LockOut,
             summary="Operator confirms the tap (commissioning -> owned, decommissioning -> factory)")
def confirm(site_id: int, lock_id: int, ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    lk = ctx.get(Lock, lock_id, site)
    L.confirm(ctx, site, lk)
    return lk


@router.delete("/{lock_id}", status_code=204)
def delete(site_id: int, lock_id: int, ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    L.delete(ctx, site, ctx.get(Lock, lock_id, site))
