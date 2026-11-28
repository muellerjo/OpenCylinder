"""JSON API — /api/v1/t/{tenant}/sites/..."""

from fastapi import APIRouter, Body, Depends, HTTPException

from ...core.tenancy import TenantContext, requires
from . import service as S
from .models import Door, TimeProfile, Zone
from .schemas import DoorIn, DoorOut, ProfileIn, ProfileOut, SiteIn, SiteOut, ZoneIn, ZoneOut

router = APIRouter(prefix="/t/{tenant}/sites", tags=["sites"])
READ, WRITE = requires("site.read"), requires("site.write")


@router.get("", response_model=list[SiteOut])
def list_sites(ctx: TenantContext = Depends(READ)):
    return S.list_sites(ctx)


@router.post("", response_model=SiteOut, status_code=201,
             summary="Create a site with freshly generated keys")
def create_site(data: SiteIn, ctx: TenantContext = Depends(WRITE)):
    return S.create_site(ctx, data)


@router.post("/import", response_model=SiteOut, status_code=201,
             summary="Import a site.json (examples/*/site.json format); fresh keys are generated")
def import_site(data: dict = Body(...), ctx: TenantContext = Depends(WRITE)):
    try:
        return S.import_site_json(ctx, data)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"bad site.json: {e}") from e


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.site(site_id)


@router.put("/{site_id}", response_model=SiteOut)
def update_site(site_id: int, data: SiteIn, ctx: TenantContext = Depends(WRITE)):
    return S.update_site(ctx, ctx.site(site_id), data)


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, ctx: TenantContext = Depends(requires("members.manage"))):
    S.delete_site(ctx, ctx.site(site_id))


@router.get("/{site_id}/export", summary="site.json without any keys")
def export_site(site_id: int, ctx: TenantContext = Depends(READ)):
    return S.export_site_json(ctx, ctx.site(site_id))


@router.get("/{site_id}/public-key", summary="Management public key (what locks verify bundles with)")
def public_key(site_id: int, ctx: TenantContext = Depends(READ)):
    return {"public_key": S.management_public_key(ctx, ctx.site(site_id))}


# ---- zones
@router.get("/{site_id}/zones", response_model=list[ZoneOut])
def zones(site_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.site(site_id).zones


@router.post("/{site_id}/zones", response_model=ZoneOut, status_code=201)
def add_zone(site_id: int, data: ZoneIn, ctx: TenantContext = Depends(WRITE)):
    return S.save_zone(ctx, ctx.site(site_id), data)


@router.put("/{site_id}/zones/{zone_id}", response_model=ZoneOut)
def put_zone(site_id: int, zone_id: int, data: ZoneIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    return S.save_zone(ctx, site, data, ctx.get(Zone, zone_id, site))


@router.delete("/{site_id}/zones/{zone_id}", status_code=204)
def del_zone(site_id: int, zone_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    S.delete_zone(ctx, site, ctx.get(Zone, zone_id, site))


# ---- doors
@router.get("/{site_id}/doors", response_model=list[DoorOut])
def doors(site_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.site(site_id).doors


@router.post("/{site_id}/doors", response_model=DoorOut, status_code=201)
def add_door(site_id: int, data: DoorIn, ctx: TenantContext = Depends(WRITE)):
    return S.save_door(ctx, ctx.site(site_id), data)


@router.put("/{site_id}/doors/{door_id}", response_model=DoorOut)
def put_door(site_id: int, door_id: int, data: DoorIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    return S.save_door(ctx, site, data, ctx.get(Door, door_id, site))


@router.delete("/{site_id}/doors/{door_id}", status_code=204)
def del_door(site_id: int, door_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    S.delete_door(ctx, site, ctx.get(Door, door_id, site))


# ---- time profiles
@router.get("/{site_id}/profiles", response_model=list[ProfileOut])
def profiles(site_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.site(site_id).profiles


@router.post("/{site_id}/profiles", response_model=ProfileOut, status_code=201)
def add_profile(site_id: int, data: ProfileIn, ctx: TenantContext = Depends(WRITE)):
    return S.save_profile(ctx, ctx.site(site_id), data)


@router.put("/{site_id}/profiles/{profile_id}", response_model=ProfileOut)
def put_profile(site_id: int, profile_id: int, data: ProfileIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    return S.save_profile(ctx, site, data, ctx.get(TimeProfile, profile_id, site))


@router.delete("/{site_id}/profiles/{profile_id}", status_code=204)
def del_profile(site_id: int, profile_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    S.delete_profile(ctx, site, ctx.get(TimeProfile, profile_id, site))
