"""HTML pages: people, credentials, roles, blacklist."""

from fastapi import APIRouter, Depends, Form

from ...core.tenancy import TenantContext, requires
from ...core.web import attempt, form_body, page, redirect
from . import service as P
from .models import AccessRole, Credential, Person
from .schemas import EntryIn, PersonIn, RoleIn

router = APIRouter()
READ, WRITE, STRUCT = requires("site.read"), requires("people.write"), requires("site.write")
SITE = "/t/{tenant}/s/{site_id}"


def _url(ctx, site, sub):
    return f"/t/{ctx.tenant.slug}/s/{site.id}{sub}"


def _list(v):
    return [] if v is None else [v] if isinstance(v, str) else list(v)


def _entries_from_form(f) -> list[EntryIn]:
    out = []
    for target, profile in zip(_list(f.get("e_target")), _list(f.get("e_profile"))):
        if not target:
            continue
        kind, num = target.split(":")
        out.append(EntryIn(kind=kind, target=int(num), profile=int(profile or 0)))
    return out


# ------------------------------------------------------------------- people

@router.get(SITE + "/people")
def people(site_id: int, q: str = "", ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "people/list.html", ctx=ctx, site=site, people=P.list_people(ctx, site, q), q=q,
                roles=P.list_roles(ctx, site))


@router.post(SITE + "/people")
def person_add(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)

    def go():
        p = P.save_person(ctx, site, PersonIn(name=f.get("name", ""), note=f.get("note", ""),
                                              valid_until=f.get("valid_until") or None,
                                              roles=_list(f.get("roles"))))
        ctx.db.flush()
        if f.get("with_card"):
            P.add_credential(ctx, site, p)
        return p
    p, ok = attempt(ctx, ctx.request, go, "Person added.")
    return redirect(_url(ctx, site, f"/people/{p.id}" if ok else "/people"), ctx.request)


@router.get(SITE + "/people/{person_id}")
def person(site_id: int, person_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    p = ctx.get(Person, person_id, site)
    preview, preview_error = None, None
    try:
        if p.active_credential:
            f0, f1, entries = P.encode_person(p)
            preview = {"file0": f0.hex(" ").upper(), "file1": f1[:4 * len(entries)].hex(" ").upper(),
                       "entries": entries}
    except Exception as e:  # noqa: BLE001  (shown to the operator)
        preview_error = str(getattr(e, "detail", e))
    return page(ctx.request, "people/person.html", ctx=ctx, site=site, p=p, roles=P.list_roles(ctx, site),
                preview=preview, preview_error=preview_error,
                names={"door": {d.number: d.name for d in site.doors},
                       "zone": {z.number: z.name for z in site.zones}})


@router.post(SITE + "/people/{person_id}")
def person_save(site_id: int, person_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    p = ctx.get(Person, person_id, site)
    attempt(ctx, ctx.request, lambda: P.save_person(ctx, site, PersonIn(
        name=f.get("name", ""), note=f.get("note", ""), valid_until=f.get("valid_until") or None,
        roles=_list(f.get("roles")), extras=_entries_from_form(f)), p),
        "Saved. Cards already issued keep their old rights until they are rewritten.")
    return redirect(_url(ctx, site, f"/people/{p.id}"), ctx.request)


@router.post(SITE + "/people/{person_id}/delete")
def person_delete(site_id: int, person_id: int, ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    _, ok = attempt(ctx, ctx.request, lambda: P.delete_person(ctx, site, ctx.get(Person, person_id, site)),
                    "Person deleted.")
    return redirect(_url(ctx, site, "/people" if ok else f"/people/{person_id}"), ctx.request)


@router.post(SITE + "/people/{person_id}/credentials")
def credential_add(site_id: int, person_id: int, number: str = Form(""), ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    p = ctx.get(Person, person_id, site)
    attempt(ctx, ctx.request, lambda: P.add_credential(ctx, site, p, int(number) if number else None),
            "New credential created — write it onto a card (Issue card).")
    return redirect(_url(ctx, site, f"/people/{p.id}"), ctx.request)


@router.post(SITE + "/credentials/{cred_id}/status")
def credential_status(site_id: int, cred_id: int, status: str = Form(...), note: str = Form(""),
                      ctx: TenantContext = Depends(WRITE)):
    site = ctx.site(site_id)
    c = ctx.get(Credential, cred_id, site)
    msg = {"blacklisted": "Card blacklisted. Locks learn it with the next maintenance card.",
           "retired": "Card retired.", "active": "Card active again."}.get(status, "Saved.")
    attempt(ctx, ctx.request, lambda: P.set_status(ctx, site, c, status, note), msg)
    return redirect(_url(ctx, site, f"/people/{c.person_id}"), ctx.request)


# -------------------------------------------------------------------- roles

@router.get(SITE + "/roles")
def roles(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "people/roles.html", ctx=ctx, site=site, roles=P.list_roles(ctx, site),
                names={"door": {d.number: d.name for d in site.doors},
                       "zone": {z.number: z.name for z in site.zones}})


@router.post(SITE + "/roles")
def role_add(site_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(STRUCT)):
    site = ctx.site(site_id)
    r, ok = attempt(ctx, ctx.request, lambda: P.save_role(ctx, site, RoleIn(
        key=f.get("key", ""), label=f.get("label", ""), entries=_entries_from_form(f))), "Role added.")
    return redirect(_url(ctx, site, f"/roles/{r.id}" if ok else "/roles"), ctx.request)


@router.get(SITE + "/roles/{role_id}")
def role(site_id: int, role_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "people/role.html", ctx=ctx, site=site, r=ctx.get(AccessRole, role_id, site))


@router.post(SITE + "/roles/{role_id}")
def role_save(site_id: int, role_id: int, f: dict = Depends(form_body), ctx: TenantContext = Depends(STRUCT)):
    site = ctx.site(site_id)
    r = ctx.get(AccessRole, role_id, site)
    attempt(ctx, ctx.request, lambda: P.save_role(ctx, site, RoleIn(
        key=r.key, label=f.get("label", ""), entries=_entries_from_form(f)), r),
        "Saved. Holders' cards change only when they are rewritten.")
    return redirect(_url(ctx, site, f"/roles/{r.id}"), ctx.request)


@router.post(SITE + "/roles/{role_id}/delete")
def role_delete(site_id: int, role_id: int, ctx: TenantContext = Depends(STRUCT)):
    site = ctx.site(site_id)
    _, ok = attempt(ctx, ctx.request, lambda: P.delete_role(ctx, site, ctx.get(AccessRole, role_id, site)),
                    "Role deleted.")
    return redirect(_url(ctx, site, "/roles" if ok else f"/roles/{role_id}"), ctx.request)


@router.get(SITE + "/blacklist")
def blacklist(site_id: int, ctx: TenantContext = Depends(READ)):
    from datetime import datetime, timezone
    from sqlalchemy import select
    site = ctx.site(site_id)
    current = P.blacklist(ctx, site)
    creds = {c.number: c for c in ctx.db.scalars(select(Credential).where(
        Credential.site_id == site.id, Credential.status == "blacklisted"))}
    rows = [{"cred": creds[n], "until": None if u == 0xFFFFFFFF else
             datetime.fromtimestamp(u, timezone.utc)} for n, u in current]
    expired = [c for n, c in creds.items() if n not in {x for x, _ in current}]
    return page(ctx.request, "people/blacklist.html", ctx=ctx, site=site, rows=rows, expired=expired)
