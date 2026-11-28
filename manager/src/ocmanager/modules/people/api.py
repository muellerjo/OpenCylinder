"""JSON API — /api/v1/t/{tenant}/sites/{site_id}/roles|people|credentials|blacklist"""

from fastapi import APIRouter, Depends

from ...core.tenancy import TenantContext, requires
from . import service as P
from .models import AccessRole, Credential, Person
from .schemas import CredentialIn, CredentialOut, PersonIn, PersonOut, RoleIn, RoleOut, StatusIn

router = APIRouter(prefix="/t/{tenant}/sites/{site_id}", tags=["people"])
READ, WRITE, STRUCT = requires("site.read"), requires("people.write"), requires("site.write")


@router.get("/roles", response_model=list[RoleOut])
def roles(site_id: int, ctx: TenantContext = Depends(READ)):
    return P.list_roles(ctx, ctx.site(site_id))


@router.post("/roles", response_model=RoleOut, status_code=201)
def add_role(site_id: int, data: RoleIn, ctx: TenantContext = Depends(STRUCT)):
    return P.save_role(ctx, ctx.site(site_id), data)


@router.put("/roles/{role_id}", response_model=RoleOut)
def put_role(site_id: int, role_id: int, data: RoleIn, ctx: TenantContext = Depends(STRUCT)):
    site = ctx.site(site_id)
    return P.save_role(ctx, site, data, ctx.get(AccessRole, role_id, site))


@router.delete("/roles/{role_id}", status_code=204)
def del_role(site_id: int, role_id: int, ctx: TenantContext = Depends(STRUCT)):
    site = ctx.site(site_id)
    P.delete_role(ctx, site, ctx.get(AccessRole, role_id, site))


@router.get("/people", response_model=list[PersonOut])
def people(site_id: int, q: str = "", ctx: TenantContext = Depends(READ)):
    return P.list_people(ctx, ctx.site(site_id), q)


@router.post("/people", response_model=PersonOut, status_code=201)
def add_person(site_id: int, data: PersonIn, ctx: TenantContext = Depends(WRITE)):
    return P.save_person(ctx, ctx.site(site_id), data)


@router.get("/people/{person_id}", response_model=PersonOut)
def get_person(site_id: int, person_id: int, ctx: TenantContext = Depends(READ)):
    return ctx.get(Person, person_id, ctx.site(site_id))


@router.put("/people/{person_id}", response_model=PersonOut)
def put_person(site_id: int, person_id: int, data: PersonIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    return P.save_person(ctx, site, data, ctx.get(Person, person_id, site))


@router.delete("/people/{person_id}", status_code=204)
def del_person(site_id: int, person_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    P.delete_person(ctx, site, ctx.get(Person, person_id, site))


@router.post("/people/{person_id}/credentials", response_model=CredentialOut, status_code=201)
def add_credential(site_id: int, person_id: int, data: CredentialIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    return P.add_credential(ctx, site, ctx.get(Person, person_id, site), data.number)


@router.put("/credentials/{cred_id}/status", response_model=CredentialOut)
def credential_status(site_id: int, cred_id: int, data: StatusIn, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    cred = ctx.get(Credential, cred_id, site)
    P.set_status(ctx, site, cred, data.status, data.note)
    return cred


@router.get("/blacklist", summary="Current blacklist (credential_id, until) as the locks receive it")
def get_blacklist(site_id: int, ctx: TenantContext = Depends(READ)):
    return [{"credential_id": c, "until": u} for c, u in P.blacklist(ctx, ctx.site(site_id))]
