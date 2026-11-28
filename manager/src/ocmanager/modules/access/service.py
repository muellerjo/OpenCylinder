"""Access matrix: run the lock's decision on every person's real card bytes."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ...core.tenancy import TenantContext
from ...protocol.decision import LockModel
from ..people import service as P
from ..sites.models import Site


def parse_at(site: Site, at: str | None) -> int:
    if not at:
        return int(datetime.now(timezone.utc).timestamp())
    return int(datetime.fromisoformat(at).replace(tzinfo=ZoneInfo(site.timezone)).timestamp())


def matrix(ctx: TenantContext, site: Site, now: int | None, door_filter: int | None = None):
    """-> (doors, rows) with rows = [{person, credential, cells: [(symbol, reason)], error}]."""
    profiles = {p.number: p.as_dict() for p in site.profiles}
    black = {c for c, _u in P.blacklist(ctx, site, now or None)}
    doors = [d for d in site.doors if door_filter is None or d.number == door_filter]
    locks = [LockModel(d.number, set(d.zone_numbers), site.timezone, profiles, black) for d in doors]
    rows = []
    for person in P.list_people(ctx, site):
        cred = person.active_credential
        row = {"person": person, "credential": cred, "cells": [], "error": None}
        if cred is None:
            # show blacklisted cards too: what would happen if someone still used one
            cred = next((c for c in reversed(person.credentials) if c.status == "blacklisted"), None)
            row["credential"] = cred
        if cred is None:
            row["error"] = "no card"
        else:
            try:
                f0, f1, _ = P.encode_person(person) if person.active_credential else _encode_for(person, cred)
                row["cells"] = [lk.decide(f0, f1, now) for lk in locks]
            except Exception as e:  # noqa: BLE001
                row["error"] = str(getattr(e, "detail", e))
        rows.append(row)
    return doors, rows


def _encode_for(person, cred):
    from ...protocol import card as C
    entries = P.card_entries(person)
    f0, f1 = C.encode_card(cred.number, entries, P.unix(person.valid_until), 0)
    return f0, f1, entries
