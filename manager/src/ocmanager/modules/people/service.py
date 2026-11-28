"""Cardholders, roles, credentials, blacklist — and how they become card bytes."""

import time
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from ...core.tenancy import TenantContext
from ...protocol import card as C
from ...protocol.bundle import NO_EXPIRY
from ..sites import service as sites
from ..sites.models import Site
from .models import AccessEntry, AccessRole, Credential, Person
from .schemas import EntryIn, PersonIn, RoleIn


def unix(dt: datetime | None) -> int:
    if dt is None:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ------------------------------------------------------------------ entries

def _validate_entries(site: Site, entries: list[EntryIn]):
    doors = {d.number for d in site.doors}
    zones = {z.number for z in site.zones}
    profiles = {p.number for p in site.profiles}
    for e in entries:
        if e.kind == "door" and e.target not in doors:
            raise HTTPException(400, f"unknown door {e.target}")
        if e.kind == "zone" and e.target not in zones:
            raise HTTPException(400, f"unknown zone {e.target}")
        if e.profile and e.profile not in profiles:
            raise HTTPException(400, f"unknown time profile {e.profile}")


def _entries(site: Site, entries: list[EntryIn], **owner) -> list[AccessEntry]:
    _validate_entries(site, entries)
    return [AccessEntry(site_id=site.id, kind=e.kind, target=e.target, profile=e.profile, position=i, **owner)
            for i, e in enumerate(entries)]


def card_entries(person: Person) -> list[C.Entry]:
    raw = [e for r in person.roles for e in r.entries] + list(person.extras)
    return C.merge_entries([C.Entry(C.TYPE_DOOR if e.kind == "door" else C.TYPE_ZONE, e.target, e.profile)
                            for e in raw])


def encode_person(person: Person, issued_at: int | None = None) -> tuple[bytes, bytes, list[C.Entry]]:
    cred = person.active_credential
    if cred is None:
        raise HTTPException(409, f"{person.name} has no active credential")
    entries = card_entries(person)
    f0, f1 = C.encode_card(cred.number, entries, unix(person.valid_until),
                           issued_at if issued_at is not None else int(time.time()))
    return f0, f1, entries


# -------------------------------------------------------------------- roles

def list_roles(ctx: TenantContext, site: Site) -> list[AccessRole]:
    return list(ctx.db.scalars(select(AccessRole).where(AccessRole.site_id == site.id).order_by(AccessRole.key)))


def save_role(ctx: TenantContext, site: Site, data: RoleIn, role: AccessRole | None = None) -> AccessRole:
    if role is None:
        if ctx.db.scalar(select(AccessRole).where(AccessRole.site_id == site.id, AccessRole.key == data.key)):
            raise HTTPException(409, f"role {data.key} exists")
        role = AccessRole(site_id=site.id, key=data.key)
        ctx.db.add(role)
    role.label = data.label
    role.entries = _entries(site, data.entries)
    for p in role.people:
        card_entries(p)                       # raises if a holder's card would overflow
    ctx.audit("role.save", f"site {site.aid} role {data.key}",
              entries=[e.model_dump() for e in data.entries])
    ctx.db.flush()
    return role


def delete_role(ctx: TenantContext, site: Site, role: AccessRole):
    if role.people:
        raise HTTPException(409, f"role {role.key} is still assigned to {len(role.people)} person(s)")
    ctx.audit("role.delete", f"site {site.aid} role {role.key}")
    ctx.db.delete(role)


# ------------------------------------------------------------------- people

def list_people(ctx: TenantContext, site: Site, q: str = "") -> list[Person]:
    stmt = select(Person).where(Person.site_id == site.id)
    q = q.strip()
    if q.isdigit():
        stmt = stmt.join(Credential).where(Credential.number == int(q))
    elif q:
        stmt = stmt.where(Person.name.ilike(f"%{q}%"))
    return list(ctx.db.scalars(stmt.order_by(Person.name)).unique())


def _roles_by_key(ctx, site, keys):
    roles = {r.key: r for r in list_roles(ctx, site)}
    bad = [k for k in keys if k not in roles]
    if bad:
        raise HTTPException(400, f"unknown role(s) {bad}")
    return [roles[k] for k in dict.fromkeys(keys)]


def save_person(ctx: TenantContext, site: Site, data: PersonIn, person: Person | None = None) -> Person:
    if person is None:
        person = Person(site_id=site.id)
        ctx.db.add(person)
    person.name, person.note, person.valid_until = data.name, data.note, data.valid_until
    person.roles = _roles_by_key(ctx, site, data.roles)
    person.extras = _entries(site, data.extras)
    card_entries(person)                      # raises if > 32 entries
    ctx.audit("person.save", f"site {site.aid} person {person.name}", roles=data.roles,
              valid_until=str(data.valid_until or ""))
    ctx.db.flush()
    return person


def delete_person(ctx: TenantContext, site: Site, person: Person):
    live = [c.number for c in person.credentials if c.status == "active"]
    if live:
        raise HTTPException(409, f"{person.name} still has active card(s) {live} — blacklist or retire "
                                 "them first")
    # Blacklisted credentials must stay on the locks' blacklist until they expire.
    if any(c.status == "blacklisted" for c in person.credentials):
        raise HTTPException(409, "person has blacklisted cards that must stay on the blacklist — "
                                 "keep the record until those cards expire")
    ctx.audit("person.delete", f"site {site.aid} person {person.name}")
    ctx.db.delete(person)


# -------------------------------------------------------------- credentials

def next_credential_number(ctx: TenantContext, site: Site) -> int:
    top = ctx.db.scalar(select(func.max(Credential.number)).where(Credential.site_id == site.id))
    return (top or 1000) + 1


def add_credential(ctx: TenantContext, site: Site, person: Person, number: int | None = None) -> Credential:
    if person.active_credential is not None:
        raise HTTPException(409, f"{person.name} already has the active card {person.active_credential.number}; "
                                 "blacklist or retire it first")
    number = number or next_credential_number(ctx, site)
    if ctx.db.scalar(select(Credential).where(Credential.site_id == site.id, Credential.number == number)):
        raise HTTPException(409, f"credential {number} is already used on this site (numbers are never reused)")
    cred = Credential(site_id=site.id, person=person, number=number)
    ctx.db.add(cred)
    ctx.audit("credential.add", f"site {site.aid} credential {number}", person=person.name)
    ctx.db.flush()
    return cred


def set_status(ctx: TenantContext, site: Site, cred: Credential, status: str, note: str = ""):
    if status == "active" and cred.status != "active" and cred.person.active_credential is not None:
        raise HTTPException(409, "person already has another active card")
    old, cred.status, cred.status_note = cred.status, status, note
    ctx.audit("credential.status", f"site {site.aid} credential {cred.number}", old=old, new=status, note=note)


def blacklist(ctx: TenantContext, site: Site, now: int | None = None) -> list[tuple[int, int]]:
    """(credential_id, until) for every blacklisted card that can still open something.
    `until` = the card's own expiry, so entries drop out by themselves."""
    now = now or int(time.time())
    out = []
    for c in ctx.db.scalars(select(Credential).where(Credential.site_id == site.id,
                                                     Credential.status == "blacklisted")
                            .order_by(Credential.number)):
        until = c.card_valid_until if c.card_valid_until is not None else unix(c.person.valid_until)
        until = until or NO_EXPIRY
        if until > now:
            out.append((c.number, until))
    return out


def mark_written(ctx: TenantContext, cred: Credential, uid: str, valid_until: int):
    cred.card_uid, cred.card_valid_until = uid, valid_until
    cred.last_written_at = datetime.now(timezone.utc)


# ---------------------------------------------------------- hooks (sites)

def _usage(ctx: TenantContext, site: Site, kind: str, number: int) -> list[str]:
    col = AccessEntry.profile if kind == "profile" else AccessEntry.target
    stmt = select(AccessEntry).where(AccessEntry.site_id == site.id, col == number)
    if kind != "profile":
        stmt = stmt.where(AccessEntry.kind == kind)
    where = []
    for e in ctx.db.scalars(stmt):
        if e.role_id:
            where.append(f"role {ctx.db.get(AccessRole, e.role_id).key}")
        else:
            where.append(ctx.db.get(Person, e.person_id).name)
    return sorted(set(where))


def _import(ctx: TenantContext, site: Site, data: dict):
    ctx.db.flush()
    ctx.db.refresh(site)
    for key, r in data.get("roles", {}).items():
        save_role(ctx, site, RoleIn(key=key, label=r.get("label", key),
                                    entries=[_entry_from_json(e) for e in r.get("entries", [])]))
    ctx.db.flush()
    black = set(data.get("blacklist", []))
    for u in data.get("users", []):
        p = save_person(ctx, site, PersonIn(
            name=u["name"], note=u.get("note", ""), valid_until=u.get("valid_until"),
            roles=u.get("roles", []), extras=[_entry_from_json(e) for e in u.get("extra", [])]))
        ctx.db.flush()
        cred = add_credential(ctx, site, p, u["credential_id"])
        if u["credential_id"] in black:
            cred.status, cred.status_note = "blacklisted", "imported from site.json blacklist"


def _entry_from_json(e: dict) -> EntryIn:
    kind = "door" if "door" in e else "zone"
    return EntryIn(kind=kind, target=e[kind], profile=e.get("profile", 0))


def _export(ctx: TenantContext, site: Site, out: dict):
    out["roles"] = {r.key: {"label": r.label, "entries": [e.as_dict() for e in r.entries]}
                    for r in list_roles(ctx, site)}
    users = []
    for p in list_people(ctx, site):
        for c in p.credentials:
            u = {"credential_id": c.number, "name": p.name, "roles": [r.key for r in p.roles]}
            if p.extras:
                u["extra"] = [e.as_dict() for e in p.extras]
            if p.valid_until:
                u["valid_until"] = p.valid_until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if p.note:
                u["note"] = p.note
            if c.status != "retired":
                users.append(u)
    out["users"] = users
    out["blacklist"] = [c for c, _u in blacklist(ctx, site)]


def register_hooks():
    if _usage not in sites.USAGE_HOOKS:
        sites.USAGE_HOOKS.append(_usage)
        sites.IMPORT_HOOKS.append(_import)
        sites.EXPORT_HOOKS.append(_export)
