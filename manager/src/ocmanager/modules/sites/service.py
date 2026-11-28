"""Site business logic. Used by both the JSON API and the HTML UI."""

import secrets as pysecrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select

from ...core.tenancy import TenantContext
from ...protocol import bundle as B
from ...protocol.an10922 import aid_wire
from ...protocol.commissioning import SiteSecrets
from .models import Door, Site, SiteSecret, TimeProfile, Zone
from .schemas import DoorIn, ProfileIn, SiteIn, ZoneIn

KEY_NAMES = ("issuer_master", "read_master", "uid_key", "admin_issuer_master", "admin_read_master")
SIGNING_KEY = "management_key"

# Other modules extend site.json import/export (e.g. people: roles, users, blacklist).
IMPORT_HOOKS: list[Callable] = []     # fn(ctx, site, data: dict)
EXPORT_HOOKS: list[Callable] = []     # fn(ctx, site, out: dict)
# Other modules veto deleting a zone / door / profile that is still referenced.
USAGE_HOOKS: list[Callable] = []      # fn(ctx, site, kind, number) -> list[str] (where used)


# --------------------------------------------------------------------- secrets

@dataclass
class Keys:
    issuer_master: bytes
    read_master: bytes
    uid_key: bytes
    admin_issuer_master: bytes
    admin_read_master: bytes
    signing_key: object

    def lock_secrets(self, site: Site) -> SiteSecrets:
        return SiteSecrets(aid_wire(site.aid), aid_wire(site.admin_aid), self.read_master,
                           self.uid_key, self.admin_read_master)


def _aad(site: Site, name: str) -> str:
    return f"site:{site.id}:{name}"


def _store(ctx: TenantContext, site: Site, name: str, value: bytes):
    vault = ctx.request.app.state.vault
    row = ctx.db.scalar(select(SiteSecret).where(SiteSecret.site_id == site.id, SiteSecret.name == name))
    blob = vault.seal(value, _aad(site, name))
    if row:
        row.blob = blob
    else:
        ctx.db.add(SiteSecret(site_id=site.id, name=name, blob=blob))


def generate_keys(ctx: TenantContext, site: Site):
    """Fresh random AES masters + a new ECDSA P-256 management key for a real site."""
    for n in KEY_NAMES:
        _store(ctx, site, n, pysecrets.token_bytes(16))
    _store(ctx, site, SIGNING_KEY, B.signing_key_pem(B.generate_signing_key()))
    site.dev_keys = False


def set_dev_keys(ctx: TenantContext, site: Site, dev: dict, pem: bytes):
    if not ctx.request.app.state.settings.allow_dev_keys:
        raise HTTPException(400, "importing dev test keys is disabled (OCM_ALLOW_DEV_KEYS=false)")
    for n in KEY_NAMES:
        v = bytes.fromhex(dev[n])
        if len(v) != 16:
            raise HTTPException(400, f"{n} must be 16 bytes")
        _store(ctx, site, n, v)
    B.load_signing_key_pem(pem)
    _store(ctx, site, SIGNING_KEY, pem)
    site.dev_keys = True


def load_keys(ctx: TenantContext, site: Site) -> Keys:
    vault = ctx.request.app.state.vault
    rows = {r.name: r.blob for r in ctx.db.scalars(select(SiteSecret).where(SiteSecret.site_id == site.id))}
    missing = [n for n in (*KEY_NAMES, SIGNING_KEY) if n not in rows]
    if missing:
        raise HTTPException(409, f"site has no keys yet ({', '.join(missing)})")
    vals = {n: vault.open(rows[n], _aad(site, n)) for n in rows}
    return Keys(**{n: vals[n] for n in KEY_NAMES},
                signing_key=B.load_signing_key_pem(vals[SIGNING_KEY]))


def management_public_key(ctx: TenantContext, site: Site) -> str | None:
    try:
        return B.public_key_raw(load_keys(ctx, site).signing_key).hex().upper()
    except HTTPException:
        return None


def next_sequence(ctx: TenantContext, site: Site) -> int:
    """Monotonic per site; Unix time when possible, so a fresh card always qualifies."""
    ctx.db.refresh(site, with_for_update=True)
    seq = max(int(time.time()), site.last_sequence + 1)
    site.last_sequence = seq
    return seq


# ----------------------------------------------------------------------- sites

def list_sites(ctx: TenantContext) -> list[Site]:
    return list(ctx.db.scalars(select(Site).where(Site.tenant_id == ctx.tenant.id).order_by(Site.name)))


def create_site(ctx: TenantContext, data: SiteIn, generate: bool = True) -> Site:
    if ctx.db.scalar(select(Site).where(Site.tenant_id == ctx.tenant.id, Site.aid == data.aid)):
        raise HTTPException(409, f"a site with AID {data.aid} exists already")
    site = Site(tenant_id=ctx.tenant.id, **data.model_dump())
    ctx.db.add(site)
    ctx.db.flush()
    if generate:
        generate_keys(ctx, site)
    ctx.audit("site.create", f"site {site.aid}", name=site.name, generated_keys=generate)
    return site


def update_site(ctx: TenantContext, site: Site, data: SiteIn) -> Site:
    if data.aid != site.aid or data.admin_aid != site.admin_aid:
        raise HTTPException(400, "AIDs cannot change — issued cards and locks depend on them")
    site.name, site.timezone, site.posix_tz = data.name, data.timezone, data.posix_tz
    ctx.audit("site.update", f"site {site.aid}", **data.model_dump())
    return site


def delete_site(ctx: TenantContext, site: Site):
    ctx.audit("site.delete", f"site {site.aid}", name=site.name)
    ctx.db.delete(site)


# ----------------------------------------------------------- zones / doors / profiles

def _check_unused(ctx, site, kind, number):
    where = [w for hook in USAGE_HOOKS for w in hook(ctx, site, kind, number)]
    if where:
        raise HTTPException(409, f"{kind} {number} is still used by: {', '.join(where[:8])}"
                                 + (" …" if len(where) > 8 else ""))


def _zones_by_number(site: Site, numbers: list[int]) -> list[Zone]:
    known = {z.number: z for z in site.zones}
    bad = [n for n in numbers if n not in known]
    if bad:
        raise HTTPException(400, f"unknown zone number(s) {bad}")
    return [known[n] for n in dict.fromkeys(numbers)]


def save_zone(ctx: TenantContext, site: Site, data: ZoneIn, zone: Zone | None = None) -> Zone:
    if zone is None:
        if any(z.number == data.number for z in site.zones):
            raise HTTPException(409, f"zone {data.number} exists")
        zone = Zone(site=site, number=data.number, name=data.name)
        ctx.db.add(zone)
    else:
        if data.number != zone.number:
            raise HTTPException(400, "zone numbers are fixed (they are on cards and in locks)")
        zone.name = data.name
    ctx.db.flush()
    ctx.audit("zone.save", f"site {site.aid} zone {data.number}", name=data.name)
    return zone


def delete_zone(ctx: TenantContext, site: Site, zone: Zone):
    _check_unused(ctx, site, "zone", zone.number)
    if zone.doors:
        raise HTTPException(409, f"zone {zone.number} still contains doors "
                                 f"{[d.number for d in zone.doors]}")
    ctx.audit("zone.delete", f"site {site.aid} zone {zone.number}")
    ctx.db.delete(zone)


def save_door(ctx: TenantContext, site: Site, data: DoorIn, door: Door | None = None) -> Door:
    zones = _zones_by_number(site, data.zones)
    if door is None:
        if any(d.number == data.number for d in site.doors):
            raise HTTPException(409, f"door {data.number} exists")
        door = Door(site=site, number=data.number, name=data.name)
        ctx.db.add(door)
    elif data.number != door.number:
        raise HTTPException(400, "door numbers are fixed (they are on cards and in locks)")
    door.name, door.zones = data.name, zones
    ctx.audit("door.save", f"site {site.aid} door {data.number}", name=data.name, zones=data.zones)
    ctx.db.flush()
    return door


def delete_door(ctx: TenantContext, site: Site, door: Door):
    _check_unused(ctx, site, "door", door.number)
    ctx.audit("door.delete", f"site {site.aid} door {door.number}")
    ctx.db.delete(door)


def save_profile(ctx: TenantContext, site: Site, data: ProfileIn, p: TimeProfile | None = None):
    ivs = [i.as_dict() for i in data.intervals]
    if p is None:
        if any(x.number == data.number for x in site.profiles):
            raise HTTPException(409, f"profile {data.number} exists")
        p = TimeProfile(site=site, number=data.number)
        ctx.db.add(p)
    elif data.number != p.number:
        raise HTTPException(400, "profile numbers are fixed (they are on cards)")
    p.name, p.days, p.intervals = data.name, data.days, ivs
    ctx.audit("profile.save", f"site {site.aid} profile {data.number}", days=data.days, intervals=ivs)
    ctx.db.flush()
    return p


def delete_profile(ctx: TenantContext, site: Site, p: TimeProfile):
    _check_unused(ctx, site, "profile", p.number)
    ctx.audit("profile.delete", f"site {site.aid} profile {p.number}")
    ctx.db.delete(p)


# ------------------------------------------------------------- site.json I/O

def import_site_json(ctx: TenantContext, data: dict, dev_pem: bytes | None = None) -> Site:
    """Create a site from the examples/*/site.json format (structure + people via hooks).

    With dev_keys in the file (or the hospital defaults) and a PEM, the public
    bench test keys are imported so existing dev cards keep working; otherwise
    fresh keys are generated.
    """
    s = data["site"]
    site = create_site(ctx, SiteIn(name=s["name"], aid=s["aid"], admin_aid=s["admin_aid"],
                                   timezone=s.get("timezone", "Europe/Berlin"),
                                   posix_tz=s.get("posix_tz", "CET-1CEST,M3.5.0,M10.5.0/3")),
                       generate=dev_pem is None)
    for z in data.get("zones", []):
        save_zone(ctx, site, ZoneIn(number=z["id"], name=z["name"]))
    ctx.db.flush()
    ctx.db.refresh(site)
    for d in data.get("doors", []):
        save_door(ctx, site, DoorIn(number=d["id"], name=d["name"], zones=d.get("zones", [])))
    for p in data.get("time_profiles", []):
        ivs = p.get("intervals", [{"from": p.get("from"), "to": p.get("to")}])
        save_profile(ctx, site, ProfileIn(number=p["id"], name=p["name"], days=p["days"], intervals=ivs))
    ctx.db.flush()
    if dev_pem is not None:
        from .devkeys import HOSPITAL_DEFAULTS
        dev = {**HOSPITAL_DEFAULTS, **{k: v for k, v in data.get("dev_keys", {}).items() if k in KEY_NAMES}}
        set_dev_keys(ctx, site, dev, dev_pem)
    for hook in IMPORT_HOOKS:
        hook(ctx, site, data)
    ctx.audit("site.import", f"site {site.aid}", dev_keys=site.dev_keys)
    return site


def export_site_json(ctx: TenantContext, site: Site) -> dict:
    """Same format as examples/*/site.json. Never contains keys."""
    out = {
        "site": {"name": site.name, "aid": site.aid, "admin_aid": site.admin_aid,
                 "timezone": site.timezone, "posix_tz": site.posix_tz},
        "zones": [{"id": z.number, "name": z.name} for z in site.zones],
        "doors": [{"id": d.number, "name": d.name, "zones": d.zone_numbers} for d in site.doors],
        "time_profiles": [{"id": p.number, "name": p.name, "days": p.days, "intervals": p.intervals}
                          for p in site.profiles],
    }
    for hook in EXPORT_HOOKS:
        hook(ctx, site, out)
    return out


def profiles_for_lock(site: Site) -> list[dict]:
    return [p.as_dict() for p in site.profiles]


def maintenance_records(site: Site, blacklist: list[tuple[int, int]]) -> bytes:
    """Blacklist replace + time profiles + TZ rule — what every lock of the site should hold."""
    return (B.tlv(B.T_BLACKLIST_REPLACE, B.blacklist_value(blacklist)) +
            B.tlv(B.T_TIME_PROFILES, B.profiles_value(profiles_for_lock(site))) +
            B.tlv(B.T_TZ_RULE, site.posix_tz.encode("ascii")))
