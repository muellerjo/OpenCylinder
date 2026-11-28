import json

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...core.tenancy import TenantContext, requires
from ...core.web import attempt, flash, page, redirect
from . import service as L
from .models import LOCK_STATES, Lock

router = APIRouter()
READ, MANAGE = requires("site.read"), requires("locks.manage")
SITE = "/t/{tenant}/s/{site_id}"


def _url(ctx, site, sub=""):
    return f"/t/{ctx.tenant.slug}/s/{site.id}/locks{sub}"


@router.get(SITE + "/locks")
def locks(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "locks/list.html", ctx=ctx, site=site, locks=L.list_locks(ctx, site),
                states=LOCK_STATES, doors={d.number: d for d in site.doors})


@router.post(SITE + "/locks")
def register(site_id: int, qr: str = Form(...), label: str = Form(""), ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    lk, ok = attempt(ctx, ctx.request, lambda: L.register(ctx, site, qr, label), "Lock registered.")
    return redirect(_url(ctx, site, f"/{lk.id}" if ok else ""), ctx.request)


@router.post(SITE + "/locks/import-local")
def import_local(site_id: int, file: UploadFile = File(...), ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    try:
        data = json.loads(file.file.read())
    except ValueError:
        flash(ctx.request, "not a JSON file", "error")
        return redirect(_url(ctx, site), ctx.request)
    n, ok = attempt(ctx, ctx.request, lambda: L.import_locks_local(ctx, site, data))
    if ok:
        flash(ctx.request, f"{n} lock(s) imported as commissioned.")
    return redirect(_url(ctx, site), ctx.request)


@router.get(SITE + "/locks/{lock_id}")
def lock(site_id: int, lock_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    lk = ctx.get(Lock, lock_id, site)
    zones = None
    if lk.door_number is not None:
        door = next((d for d in site.doors if d.number == lk.door_number), None)
        zones = door.zone_numbers if door else None
    return page(ctx.request, "locks/lock.html", ctx=ctx, site=site, lk=lk, states=LOCK_STATES,
                zones_now=zones, confirm=L.CONFIRM)


@router.post(SITE + "/locks/{lock_id}")
def save(site_id: int, lock_id: int, label: str = Form(""), note: str = Form(""),
         ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    lk = ctx.get(Lock, lock_id, site)
    attempt(ctx, ctx.request, lambda: L.update(ctx, site, lk, label, note), "Saved.")
    return redirect(_url(ctx, site, f"/{lk.id}"), ctx.request)


@router.post(SITE + "/locks/{lock_id}/confirm")
def confirm(site_id: int, lock_id: int, ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    lk = ctx.get(Lock, lock_id, site)
    attempt(ctx, ctx.request, lambda: L.confirm(ctx, site, lk), "Confirmed.")
    return redirect(_url(ctx, site, f"/{lk.id}"), ctx.request)


@router.post(SITE + "/locks/{lock_id}/delete")
def delete(site_id: int, lock_id: int, ctx: TenantContext = Depends(MANAGE)):
    site = ctx.site(site_id)
    _, ok = attempt(ctx, ctx.request, lambda: L.delete(ctx, site, ctx.get(Lock, lock_id, site)),
                    "Lock removed from the registry.")
    return redirect(_url(ctx, site, "" if ok else f"/{lock_id}"), ctx.request)
