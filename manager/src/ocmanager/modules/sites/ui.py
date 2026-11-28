"""HTML pages for sites, zones, doors and time profiles."""

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ...core.tenancy import TenantContext, requires
from ...core.web import attempt, flash, form_body, page, redirect
from . import service as S
from .models import Door, TimeProfile, Zone
from .schemas import DoorIn, ProfileIn, SiteIn, ZoneIn

router = APIRouter()
READ, WRITE = requires("site.read"), requires("site.write")
SITE = "/t/{tenant}/s/{site_id}"


def _site_url(ctx, site, sub=""):
    return f"/t/{ctx.tenant.slug}/s/{site.id}{sub}"


@router.get("/t/{tenant}")
def tenant_home(ctx: TenantContext = Depends(READ)):
    sites = S.list_sites(ctx)
    return page(ctx.request, "sites/tenant_home.html", ctx=ctx, site_list=sites)


@router.post("/t/{tenant}/sites")
def site_create(f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site, ok = attempt(ctx, ctx.request, lambda: S.create_site(ctx, SiteIn(**f)),
                       "Site created with freshly generated keys.")
    return redirect(_site_url(ctx, site) if ok else f"/t/{ctx.tenant.slug}", ctx.request)


@router.post("/t/{tenant}/sites/import")
def site_import(file: UploadFile = File(...), dev_pem: UploadFile | None = File(None),
                ctx: TenantContext = Depends(WRITE)):
    try:
        data = json.loads(file.file.read())
    except ValueError:
        flash(ctx.request, "not a JSON file", "error")
        return redirect(f"/t/{ctx.tenant.slug}", ctx.request)
    pem = dev_pem.file.read() if dev_pem and dev_pem.filename else None
    site, ok = attempt(ctx, ctx.request, lambda: S.import_site_json(ctx, data, pem),
                       "Site imported" + (" with the PUBLIC DEV TEST KEYS (bench only)." if pem
                                          else " with freshly generated keys."))
    return redirect(_site_url(ctx, site) if ok else f"/t/{ctx.tenant.slug}", ctx.request)


@router.get(SITE)
def site_overview(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "sites/overview.html", ctx=ctx, site=site,
                public_key=S.management_public_key(ctx, site))


@router.post(SITE + "/settings")
def site_settings(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.update_site(
        ctx, site, SiteIn(**{**f, "aid": site.aid, "admin_aid": site.admin_aid})), "Saved.")
    return redirect(_site_url(ctx, site), ctx.request)


@router.post(SITE + "/delete")
def site_delete(site_id: int, confirm: str = Form(""), ctx: TenantContext = Depends(requires("members.manage"))):
    site = ctx.site(site_id)
    if confirm != site.aid:
        flash(ctx.request, f"type the AID {site.aid} to confirm deleting the site", "error")
        return redirect(_site_url(ctx, site), ctx.request)
    S.delete_site(ctx, site)
    flash(ctx.request, f"Site {site.name} deleted.")
    return redirect(f"/t/{ctx.tenant.slug}", ctx.request)


@router.get(SITE + "/export.json")
def site_export(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    ctx.audit("site.export", f"site {site.aid}")
    return JSONResponse(S.export_site_json(ctx, site), headers={
        "Content-Disposition": f'attachment; filename="site-{site.aid}.json"'})


# ------------------------------------------------------------------ zones

@router.get(SITE + "/zones")
def zones(site_id: int, ctx: TenantContext = Depends(READ)):
    return page(ctx.request, "sites/zones.html", ctx=ctx, site=ctx.site(site_id))


@router.post(SITE + "/zones")
def zone_add(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.save_zone(ctx, site, ZoneIn(**f)), "Zone added.")
    return redirect(_site_url(ctx, site, "/zones"), ctx.request)


@router.post(SITE + "/zones/{obj_id}")
def zone_save(site_id: int, obj_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    z = ctx.get(Zone, obj_id, site)
    attempt(ctx, ctx.request, lambda: S.save_zone(ctx, site, ZoneIn(number=z.number, name=f.get("name", "")), z),
            "Saved.")
    return redirect(_site_url(ctx, site, "/zones"), ctx.request)


@router.post(SITE + "/zones/{obj_id}/delete")
def zone_delete(site_id: int, obj_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.delete_zone(ctx, site, ctx.get(Zone, obj_id, site)), "Zone deleted.")
    return redirect(_site_url(ctx, site, "/zones"), ctx.request)


# ------------------------------------------------------------------ doors

def _door_in(f, number=None):
    zones = f.get("zones", [])
    zones = [zones] if isinstance(zones, str) else zones
    return DoorIn(number=number if number is not None else f.get("number"), name=f.get("name", ""),
                  zones=[int(z) for z in zones])


@router.get(SITE + "/doors")
def doors(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    locks = {}
    if any(m.name == "locks" for m in ctx.request.app.state.modules):
        from ..locks.service import locks_by_door
        locks = locks_by_door(ctx, site)
    return page(ctx.request, "sites/doors.html", ctx=ctx, site=site, locks=locks)


@router.post(SITE + "/doors")
def door_add(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.save_door(ctx, site, _door_in(f)), "Door added.")
    return redirect(_site_url(ctx, site, "/doors"), ctx.request)


@router.post(SITE + "/doors/{obj_id}")
def door_save(site_id: int, obj_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    d = ctx.get(Door, obj_id, site)
    _, ok = attempt(ctx, ctx.request, lambda: S.save_door(ctx, site, _door_in(f, d.number), d), "Saved.")
    if ok:
        flash(ctx.request, "If a lock is commissioned on this door and its zones changed, issue a "
                           "reassignment card (Locks) — locks only learn zones from a card.", "warn")
    return redirect(_site_url(ctx, site, "/doors"), ctx.request)


@router.post(SITE + "/doors/{obj_id}/delete")
def door_delete(site_id: int, obj_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.delete_door(ctx, site, ctx.get(Door, obj_id, site)), "Door deleted.")
    return redirect(_site_url(ctx, site, "/doors"), ctx.request)


# --------------------------------------------------------------- profiles

def _profile_in(f, number=None):
    days = f.get("days", [])
    days = [days] if isinstance(days, str) else days
    ivs = [{"from": f.get(f"from{i}", ""), "to": f.get(f"to{i}", "")} for i in (1, 2)]
    ivs = [iv for iv in ivs if iv["from"] or iv["to"]]
    return ProfileIn(number=number if number is not None else f.get("number"), name=f.get("name", ""),
                     days=days, intervals=ivs)


@router.get(SITE + "/profiles")
def profiles(site_id: int, ctx: TenantContext = Depends(READ)):
    return page(ctx.request, "sites/profiles.html", ctx=ctx, site=ctx.site(site_id))


@router.post(SITE + "/profiles")
def profile_add(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.save_profile(ctx, site, _profile_in(f)),
            "Profile added — locks learn it with the next maintenance card.")
    return redirect(_site_url(ctx, site, "/profiles"), ctx.request)


@router.post(SITE + "/profiles/{obj_id}")
def profile_save(site_id: int, obj_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    p = ctx.get(TimeProfile, obj_id, site)
    attempt(ctx, ctx.request, lambda: S.save_profile(ctx, site, _profile_in(f, p.number), p),
            "Saved — locks learn it with the next maintenance card.")
    return redirect(_site_url(ctx, site, "/profiles"), ctx.request)


@router.post(SITE + "/profiles/{obj_id}/delete")
def profile_delete(site_id: int, obj_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    attempt(ctx, ctx.request, lambda: S.delete_profile(ctx, site, ctx.get(TimeProfile, obj_id, site)),
            "Profile deleted.")
    return redirect(_site_url(ctx, site, "/profiles"), ctx.request)
