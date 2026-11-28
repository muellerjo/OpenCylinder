"""Issue cards: build payloads (signed bundles, card files) and Proxmark plans."""

import re
import time

from fastapi import HTTPException
from sqlalchemy import select

from ...core.tenancy import TenantContext
from ...protocol import bundle as B
from ...protocol import encoder as E
from ...protocol.an10922 import aid_wire
from ...protocol.commissioning import AID as COMMISSIONING_AID
from ...protocol.commissioning import commissioning_bundle
from ..locks import service as L
from ..locks.models import Lock
from ..people import service as P
from ..people.models import Credential, Person
from ..sites import service as S
from ..sites.models import Site
from .models import CardJob

UID_RE = re.compile(r"^[0-9A-Fa-f]{14}$")
TARGETED = ("commissioning", "decommission", "reassign")


def _job(ctx, site, kind, summary, payload, **kw) -> CardJob:
    job = CardJob(site_id=site.id, kind=kind, summary=summary, payload=payload,
                  created_by=ctx.operator.username, **kw)
    ctx.db.add(job)
    ctx.db.flush()
    ctx.audit(f"card.{kind}", f"site {site.aid} job {job.id}", summary=summary, sequence=kw.get("sequence"))
    return job


def list_jobs(ctx: TenantContext, site: Site, limit: int = 200) -> list[CardJob]:
    return list(ctx.db.scalars(select(CardJob).where(CardJob.site_id == site.id)
                               .order_by(CardJob.id.desc()).limit(limit)))


# ---------------------------------------------------------------- user cards

def issue_user_card(ctx: TenantContext, site: Site, person: Person) -> CardJob:
    cred = person.active_credential
    if cred is None:
        raise HTTPException(409, f"{person.name} has no active credential — create one first")
    f0, f1, entries = P.encode_person(person)
    S.load_keys(ctx, site)                     # fail early if the site has no keys
    return _job(ctx, site, "user", f"{person.name} — credential {cred.number}, {len(entries)} entries",
                {"file0": f0.hex().upper(), "file1": f1[:4 * len(entries)].hex().upper()},
                credential_id=cred.id, valid_until=P.unix(person.valid_until))


# ------------------------------------------------------------ admin bundles

def _signed(ctx, site, records: bytes, valid_days: float, target: bytes = bytes(8)):
    keys = S.load_keys(ctx, site)
    now = int(time.time())
    seq = S.next_sequence(ctx, site)
    until = now + int(valid_days * 86400)
    bundle = B.sign(B.build_bundle(aid_wire(site.aid), seq, now, until, records, target_device=target),
                    keys.signing_key)
    if len(bundle) > B.BUNDLE_FILE_SIZE:
        raise HTTPException(400, f"bundle too large ({len(bundle)} > {B.BUNDLE_FILE_SIZE} bytes) — "
                                 "blacklist too long? Shorten card lifetimes so entries expire.")
    return bundle, seq, now, until


def _check_valid_days(valid_days: float):
    if not 0.01 <= valid_days <= 30:
        raise HTTPException(400, "admin cards should expire quickly: 0.01 … 30 days")


def issue_maintenance(ctx: TenantContext, site: Site, valid_days: float = 2, blacklist_only: bool = False):
    _check_valid_days(valid_days)
    bl = P.blacklist(ctx, site)
    if blacklist_only:
        records = B.tlv(B.T_BLACKLIST_REPLACE, B.blacklist_value(bl))
        actions, kind = B.ACT_TIME | B.ACT_BLACKLIST, "blacklist"
    else:
        records = S.maintenance_records(site, bl)
        actions, kind = B.ACT_TIME | B.ACT_BLACKLIST | B.ACT_PROFILES, "maintenance"
    bundle, seq, now, until = _signed(ctx, site, records, valid_days)
    return _job(ctx, site, kind, f"{len(bl)} blacklist {'entry' if len(bl) == 1 else 'entries'}"
                + ("" if blacklist_only else f", {len(site.profiles)} profiles, TZ {site.posix_tz}"),
                {"header": B.admin_header(actions, until, now).hex().upper(), "bundle": bundle.hex().upper()},
                sequence=seq, valid_until=until)


def issue_targeted(ctx: TenantContext, site: Site, lock: Lock, kind: str, door: int | None = None,
                   valid_days: float = 2) -> CardJob:
    _check_valid_days(valid_days)
    ident = L.identity(lock)
    if kind == "commissioning":
        if lock.state in ("owned", "decommissioning"):
            raise HTTPException(409, "lock is owned — decommission it (or reassign) instead")
        if door is None:
            raise HTTPException(400, "choose the door")
        zones = L.door_zones(site, door)
        keys = S.load_keys(ctx, site)
        now = int(time.time())
        seq = S.next_sequence(ctx, site)
        until = now + int(valid_days * 86400)
        bundle = commissioning_bundle(ident, keys.lock_secrets(site), keys.signing_key, door, zones,
                                      S.maintenance_records(site, P.blacklist(ctx, site)), seq, now, until)
        if len(bundle) > B.COMMISSIONING_FILE_SIZE:
            raise HTTPException(400, f"commissioning bundle too large ({len(bundle)} bytes)")
        L.set_state(ctx, site, lock, "commissioning", door=door, sequence=seq)
        return _job(ctx, site, kind, f"lock {lock.device_id} → door {door}, zones {zones}",
                    {"bundle": bundle.hex().upper()}, lock_id=lock.id, sequence=seq, valid_until=until)

    if lock.state not in ("owned", "commissioning"):
        raise HTTPException(409, f"lock is {lock.state} — only an owned lock can be {kind}ed")
    if kind == "decommission":
        records, act, summary = B.tlv(B.T_DECOMMISSION, b""), B.ACT_DECOMMISSION, f"lock {lock.device_id} → FACTORY"
    elif kind == "reassign":
        if door is None:
            raise HTTPException(400, "choose the new door")
        zones = L.door_zones(site, door)
        records, act = B.tlv(B.T_LOCK_ASSIGNMENT, B.assignment_value(door, zones)), B.ACT_REASSIGN
        summary = f"lock {lock.device_id} → door {door}, zones {zones}"
    else:
        raise HTTPException(400, f"unknown kind {kind}")
    bundle, seq, now, until = _signed(ctx, site, records, valid_days, target=ident.device_id)
    if kind == "decommission":
        L.set_state(ctx, site, lock, "decommissioning", sequence=seq)
    else:
        L.set_state(ctx, site, lock, lock.state, door=door, sequence=seq)
    return _job(ctx, site, kind, summary,
                {"header": B.admin_header(B.ACT_TIME | act, until, now).hex().upper(), "bundle": bundle.hex().upper()},
                lock_id=lock.id, sequence=seq, valid_until=until)


# ------------------------------------------------------------------- plans

def needs_uid(job: CardJob) -> bool:
    return job.kind != "commissioning"


def plan(ctx: TenantContext, site: Site, job: CardJob, uid_hex: str | None, app_exists: bool = False):
    p = job.payload
    if job.kind == "commissioning":
        return E.commissioning_card_plan(bytes.fromhex(p["bundle"]), app_exists)
    if not uid_hex or not UID_RE.match(uid_hex):
        raise HTTPException(400, "need the card's 7-byte UID (14 hex digits) — keys are diversified per card")
    uid = bytes.fromhex(uid_hex)
    keys = S.load_keys(ctx, site)
    if job.kind == "user":
        return E.user_card_plan(site.aid, uid, bytes.fromhex(p["file0"]), bytes.fromhex(p["file1"]),
                                keys.issuer_master, keys.read_master, keys.uid_key)
    return E.admin_card_plan(site.admin_aid, uid, bytes.fromhex(p["header"]), bytes.fromhex(p["bundle"]),
                             keys.admin_issuer_master, keys.admin_read_master, app_exists)


def mark_written(ctx: TenantContext, site: Site, job: CardJob, uid_hex: str | None, log: str = ""):
    if job.status not in ("prepared", "failed"):
        raise HTTPException(409, f"job is {job.status}")
    if job.kind == "user":
        if not uid_hex or not UID_RE.match(uid_hex):
            raise HTTPException(400, "UID of the written card required")
        cred = ctx.db.get(Credential, job.credential_id)
        if cred is not None:
            P.mark_written(ctx, cred, uid_hex.upper(), job.valid_until or 0)
    job.status, job.card_uid = "written", (uid_hex or "").upper() or None
    job.log = (job.log + "\n" + log).strip()
    ctx.audit("card.written", f"site {site.aid} job {job.id}", kind=job.kind, uid=job.card_uid)


def cancel(ctx: TenantContext, site: Site, job: CardJob):
    if job.status != "prepared":
        raise HTTPException(409, f"job is {job.status}")
    job.status = "cancelled"
    ctx.audit("card.cancel", f"site {site.aid} job {job.id}", kind=job.kind)


# ------------------------------------------------------- local Proxmark3

def pm3_available(ctx: TenantContext) -> bool:
    return bool(ctx.request.app.state.settings.pm3_path)


def run_local(ctx: TenantContext, site: Site, job: CardJob, confirm_format: bool) -> tuple[bool, list[dict]]:
    """Write the job with the Proxmark3 attached to THIS machine (local mode)."""
    st = ctx.request.app.state.settings
    if not st.pm3_path:
        raise HTTPException(400, "no local encoder configured (OCM_PM3_PATH)")
    if job.status not in ("prepared", "failed"):
        raise HTTPException(409, f"job is {job.status}")
    if job.kind == "user" and not confirm_format:
        raise HTTPException(400, "writing a user card FORMATS the card — tick the confirmation")
    uid = None
    if needs_uid(job):
        m = E.UID_RE.search(E.run_pm3(st.pm3_path, st.pm3_port, "hf 14a info"))
        if not m:
            raise HTTPException(400, "no card with a fixed 7-byte UID on the Proxmark")
        uid = m.group(1).replace(" ", "").upper()
    exists = False
    if job.kind != "user":
        aid = COMMISSIONING_AID if job.kind == "commissioning" else site.admin_aid
        exists = aid in E.run_pm3(st.pm3_path, st.pm3_port, "hf mfdes getaids").upper()
    results = []
    for step in plan(ctx, site, job, uid, exists):
        out = E.run_pm3(st.pm3_path, st.pm3_port, step.cmd)
        ok = E.step_ok(step, out)
        results.append({"desc": step.desc, "ok": ok,
                        "out": "\n".join(ln for ln in out.splitlines()
                                         if ln.startswith("[") and "Session log" not in ln)[-2000:]})
        if not ok:
            job.status = "failed"
            job.log = "\n".join(f"{'ok ' if r['ok'] else 'ERR'} {r['desc']}" for r in results)
            ctx.audit("card.failed", f"site {site.aid} job {job.id}", step=step.desc, uid=uid)
            return False, results
    mark_written(ctx, site, job, uid, "\n".join(f"ok  {r['desc']}" for r in results))
    return True, results
