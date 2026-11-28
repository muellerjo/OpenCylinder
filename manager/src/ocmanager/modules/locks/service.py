from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from ...core.tenancy import TenantContext
from ...protocol.commissioning import LockIdentity, parse_qr
from ..sites import service as sites
from ..sites.models import Site
from .models import LOCK_STATES, Lock

# manual confirmations after a tap (the lock cannot report back)
CONFIRM = {"commissioning": "owned", "decommissioning": "factory"}


def list_locks(ctx: TenantContext, site: Site) -> list[Lock]:
    return list(ctx.db.scalars(select(Lock).where(Lock.site_id == site.id).order_by(Lock.door_number,
                                                                                    Lock.device_id)))


def locks_by_door(ctx: TenantContext, site: Site) -> dict[int, list[Lock]]:
    out: dict[int, list[Lock]] = {}
    for lk in list_locks(ctx, site):
        if lk.door_number is not None and lk.state in ("commissioning", "owned", "decommissioning"):
            out.setdefault(lk.door_number, []).append(lk)
    return out


def register(ctx: TenantContext, site: Site, qr: str, label: str = "", note: str = "") -> Lock:
    try:
        ident = parse_qr(qr)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    dev = ident.device_id.hex().upper()
    if ctx.db.scalar(select(Lock).where(Lock.site_id == site.id, Lock.device_id == dev)):
        raise HTTPException(409, f"lock {dev} is already registered on this site")
    lk = Lock(site_id=site.id, device_id=dev, public_key=ident.public_key.hex().upper(), label=label, note=note)
    ctx.db.add(lk)
    ctx.db.flush()
    ctx.audit("lock.register", f"site {site.aid} lock {dev}", label=label)
    return lk


def identity(lk: Lock) -> LockIdentity:
    return parse_qr(lk.qr)


def door_zones(site: Site, door_number: int) -> list[int]:
    door = next((d for d in site.doors if d.number == door_number), None)
    if door is None:
        raise HTTPException(400, f"unknown door {door_number}")
    return door.zone_numbers


def set_state(ctx: TenantContext, site: Site, lk: Lock, state: str, *, door: int | None = None,
              sequence: int | None = None):
    if state not in LOCK_STATES:
        raise HTTPException(400, f"unknown state {state}")
    old = lk.state
    lk.state = state
    if door is not None:
        lk.door_number = door
    if sequence is not None:
        lk.last_sequence = sequence
    if state == "owned":
        lk.commissioned_at = datetime.now(timezone.utc)
    ctx.audit("lock.state", f"site {site.aid} lock {lk.device_id}", old=old, new=state, door=lk.door_number)


def confirm(ctx: TenantContext, site: Site, lk: Lock):
    if lk.state not in CONFIRM:
        raise HTTPException(409, f"nothing to confirm in state {lk.state}")
    set_state(ctx, site, lk, CONFIRM[lk.state])


def update(ctx: TenantContext, site: Site, lk: Lock, label: str, note: str):
    lk.label, lk.note = label, note
    ctx.audit("lock.update", f"site {site.aid} lock {lk.device_id}", label=label)


def delete(ctx: TenantContext, site: Site, lk: Lock):
    if lk.state in ("commissioning", "owned", "decommissioning"):
        raise HTTPException(409, "decommission the lock first (it still holds this site's keys)")
    ctx.audit("lock.delete", f"site {site.aid} lock {lk.device_id}")
    ctx.db.delete(lk)


def _usage(ctx: TenantContext, site: Site, kind: str, number: int) -> list[str]:
    if kind != "door":
        return []
    return [f"lock {lk.device_id}" for lk in locks_by_door(ctx, site).get(number, [])]


def register_hooks():
    if _usage not in sites.USAGE_HOOKS:
        sites.USAGE_HOOKS.append(_usage)


def import_locks_local(ctx: TenantContext, site: Site, data: dict) -> int:
    """examples/hospital/locks.local.json -> registered + owned locks (bench)."""
    n = 0
    for dev, rec in data.get("locks", {}).items():
        lk = register(ctx, site, f"OC1:{dev}:{rec['public_key']}", label="imported from locks.local.json")
        ctx.db.flush()
        set_state(ctx, site, lk, "owned", door=rec.get("door"), sequence=rec.get("commissioned_sequence"))
        door = next((d for d in site.doors if d.number == rec.get("door")), None)
        if door is None or sorted(door.zone_numbers) != sorted(rec.get("zones", [])):
            lk.note = (f"zones in the file {rec.get('zones')} differ from door {rec.get('door')} of this site "
                       f"{door.zone_numbers if door else '(unknown door)'} — commissioned to another site?")
        n += 1
    return n
