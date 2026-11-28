"""Card inspector: read the card on the reader and explain what it holds.

Works for every application this tenant can decode:
- user application of one of its sites   -> holder, rights, expiry, up to date?, doors it opens now
- admin application of one of its sites  -> maintenance / targeted bundle, signature, staleness
- commissioning card (4F434B)            -> which lock, which site, signature
- identify card (4F4349)                 -> the lock that wrote it
Anything else is listed as a foreign application (other sites, other systems).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from ...core.tenancy import TenantContext
from ...protocol import bundle as B
from ...protocol import card as C
from ...protocol import encoder as E
from ...protocol import inspect as I
from ...protocol.commissioning import AID as COMMISSIONING_AID
from ...protocol.decision import OPEN, LockModel
from ..locks.models import Lock
from ..people import service as P
from ..people.models import Credential
from ..sites import service as S
from ..sites.models import Site


class Pm3Reader:
    """The Proxmark3 attached to this machine."""

    def __init__(self, path: str, port: str | None = None):
        self.path, self.port = path, port

    def batch(self, cmds: list[str]) -> list[str]:
        return E.run_pm3_batch(self.path, self.port, cmds)


def get_reader(ctx: TenantContext):
    app = ctx.request.app
    if getattr(app.state, "card_reader", None) is not None:      # tests inject a fake reader
        return app.state.card_reader
    st = app.state.settings
    if not st.pm3_path:
        raise HTTPException(400, "no reader configured on this machine (Proxmark3: OCM_PM3_PATH)")
    return Pm3Reader(st.pm3_path, st.pm3_port)


def _ts(v: int | None):
    return None if not v else datetime.fromtimestamp(v, timezone.utc)


def _card_type(info: str) -> str:
    for line in info.splitlines():
        if "DESFire" in line or "MIFARE" in line:
            return line.split("]", 1)[-1].strip()
    return ""


def inspect(ctx: TenantContext) -> dict:
    reader = get_reader(ctx)
    info, aids_out = reader.batch(["hf 14a info", "hf mfdes getaids"])
    m = E.UID_RE.search(info)
    if not m:
        return {"present": False, "hint": "No card with a 7-byte UID on the reader (or a random-UID card)."}
    uid_hex = m.group(1).replace(" ", "").upper()
    uid = bytes.fromhex(uid_hex)
    aids = E.parse_aids(aids_out)
    now = int(time.time())
    sites = list(ctx.db.scalars(select(Site).where(Site.tenant_id == ctx.tenant.id)))
    by_user = {s.aid: s for s in sites}
    by_admin = {s.admin_aid: s for s in sites}

    # one batch with every read we can do on this card
    plan: list[tuple[str, str, Site | None, list[str]]] = []
    for aid in aids:
        if aid in by_user:
            s = by_user[aid]
            k = _keys(ctx, s)
            if k:
                _, k1 = E.card_keys(uid, aid, k.issuer_master, k.read_master)
                plan.append(("user", aid, s, [E.read_cmd(aid, 0, 1, k1), E.read_cmd(aid, 1, 1, k1)]))
            else:
                plan.append(("user", aid, s, []))
        elif aid in by_admin:
            s = by_admin[aid]
            k = _keys(ctx, s)
            if k:
                _, k1 = E.card_keys(uid, aid, k.admin_issuer_master, k.admin_read_master)
                plan.append(("admin", aid, s, [E.read_cmd(aid, 0, 1, k1), E.read_cmd(aid, 1, 1, k1)]))
            else:
                plan.append(("admin", aid, s, []))
        elif aid == COMMISSIONING_AID:
            plan.append(("commissioning", aid, None, [E.read_cmd(aid, 0)]))
        elif aid == I.IDENTIFY_AID:
            plan.append(("identify", aid, None, [E.read_cmd(aid, 0)]))
        else:
            plan.append(("foreign", aid, None, []))
    cmds = [c for p in plan for c in p[3]]
    outs = iter(reader.batch(cmds) if cmds else [])

    apps = []
    for kind, aid, site, cs in plan:
        res = [next(outs) for _ in cs]
        app = {"kind": kind, "aid": aid, "site": site, "problems": []}
        if cs and any(E.looks_failed(o) for o in res):
            app["problems"].append("could not read it with this site's keys — the card was written with other "
                                   "keys (another installation, older dev keys) or was changed")
            apps.append(app)
            continue
        data = [bytes.fromhex(E.data_hex(o)) for o in res]
        if kind == "user" and data:
            app.update(_user(ctx, site, uid_hex, data[0], data[1], now))
        elif kind == "admin" and data:
            app.update(_admin(ctx, site, data[0], data[1], now))
        elif kind == "commissioning":
            app.update(_commissioning(ctx, sites, data[0], now))
        elif kind == "identify":
            app.update(_identify(ctx, sites, data[0]))
        elif kind in ("user", "admin"):
            app["problems"].append("this site has no keys in the manager")
        apps.append(app)

    ctx.audit("card.inspect", f"card {uid_hex}", aids=aids)
    return {"present": True, "uid": uid_hex, "type": _card_type(info), "aids": aids, "apps": apps, "now": now}


def _keys(ctx, site):
    try:
        return S.load_keys(ctx, site)
    except HTTPException:
        return None


def _names(site: Site):
    return {"door": {d.number: d.name for d in site.doors}, "zone": {z.number: z.name for z in site.zones},
            "profile": {p.number: p.name for p in site.profiles}}


def _user(ctx: TenantContext, site: Site, uid_hex: str, f0: bytes, f1: bytes, now: int) -> dict:
    h = I.user_header(f0)
    entries = I.user_entries(f1, h["entry_count"])
    out = {"header": h, "entries": entries, "names": _names(site), "valid_until": _ts(h["valid_until"]),
           "issued_at": _ts(h["issued_at"]), "expired": bool(h["valid_until"]) and h["valid_until"] < now}
    cred = ctx.db.scalar(select(Credential).where(Credential.site_id == site.id,
                                                  Credential.number == h["credential_id"]))
    out["credential"], out["person"] = cred, cred.person if cred else None
    problems = []
    if cred is None:
        problems.append(f"credential {h['credential_id']} is not known on this site")
    else:
        if cred.status == "blacklisted":
            problems.append("this card is BLACKLISTED")
        elif cred.status == "retired":
            problems.append("this credential is retired (card should have been returned)")
        if cred.card_uid and cred.card_uid != uid_hex:
            problems.append(f"the manager recorded UID {cred.card_uid} for this credential — this is a "
                            "different card")
        if cred.status == "active":
            try:
                want0, want1, want_entries = P.encode_person(cred.person, issued_at=h["issued_at"])
                if want0 != f0[:16] or want1[:4 * len(want_entries)] != f1[:4 * len(want_entries)] \
                        or h["entry_count"] != len(want_entries):
                    problems.append("out of date: the person's rights or expiry changed since this card was "
                                    "written — issue the card again")
                    out["outdated"] = True
            except HTTPException as e:
                problems.append(str(e.detail))
    # what it opens right now (lock logic on the real bytes)
    black = {c for c, _u in P.blacklist(ctx, site, now)}
    profiles = {p.number: p.as_dict() for p in site.profiles}
    opens = []
    for d in site.doors:
        r, why = LockModel(d.number, set(d.zone_numbers), site.timezone, profiles, black).decide(
            f0[:16], f1 + bytes(max(0, C.FILE1_SIZE - len(f1))), now)
        if r == OPEN:
            opens.append(d)
        elif r != "none" and not out.get("refusal"):
            out["refusal"] = why
    out["opens"], out["problems"] = opens, problems
    return out


def _bundle_checks(ctx, site: Site | None, bundle: dict, now: int) -> list[str]:
    problems = []
    if site is None:
        return ["signed for a site that is not one of yours"]
    pub = S.management_public_key(ctx, site)
    if not pub or not I.verify(bundle["raw"], bytes.fromhex(pub)):
        problems.append("signature does NOT match this site's management key — a lock will refuse it")
    if bundle["valid_until"] < now:
        problems.append("expired — locks refuse it")
    if site.last_sequence and bundle["sequence"] < site.last_sequence:
        problems.append(f"older than the newest bundle issued for this site (sequence {site.last_sequence}) — "
                        "locks that saw a newer one ignore its blacklist / profile part")
    return problems


def _lock(ctx, sites, device_id: str | None):
    if not device_id:
        return None
    return ctx.db.scalar(select(Lock).where(Lock.device_id == device_id,
                                            Lock.site_id.in_([s.id for s in sites])))


def _admin(ctx: TenantContext, site: Site, f0: bytes, f1: bytes, now: int) -> dict:
    hdr = I.admin_header(f0)
    b = I.decode_bundle(f1)
    out = {"admin_header": hdr, "bundle": b, "names": _names(site)}
    if b is None:
        out["problems"] = ["admin application holds no valid bundle"]
        return out
    out["problems"] = _bundle_checks(ctx, site, b, now)
    out["lock"] = _lock(ctx, [site], b["target_device"])
    out["valid_until"], out["issued_at"] = _ts(b["valid_until"]), _ts(b["issued_at"])
    out["people"] = _people_by_cred(ctx, site)
    return out


def _people_by_cred(ctx, site):
    return {c.number: c.person.name for c in ctx.db.scalars(select(Credential).where(Credential.site_id == site.id))}


def _commissioning(ctx: TenantContext, sites: list[Site], data: bytes, now: int) -> dict:
    b = I.decode_bundle(data)
    if b is None:
        return {"problems": ["empty commissioning card"], "bundle": None}
    site = next((s for s in sites if s.aid == b["site_aid"]), None)
    out = {"bundle": b, "site": site, "problems": _bundle_checks(ctx, site, b, now),
           "lock": _lock(ctx, sites, b["target_device"]), "valid_until": _ts(b["valid_until"]),
           "issued_at": _ts(b["issued_at"])}
    if site:
        out["names"], out["people"] = _names(site), _people_by_cred(ctx, site)
    return out


def _identify(ctx: TenantContext, sites: list[Site], data: bytes) -> dict:
    rec = I.identify_record(data)
    if rec is None:
        return {"identity": None, "problems": ["empty — tap it on a lock first"]}
    return {"identity": rec, "lock": _lock(ctx, sites, rec["device_id"]),
            "site": next((s for s in sites if s.aid == rec["site_aid"]), None), "problems": []}
