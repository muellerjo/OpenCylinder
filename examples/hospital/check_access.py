#!/usr/bin/env python3
"""Play with the OpenCylinder card format v1 on a fictional hospital.

Builds each user's card bytes (file 0 header + file 1 access list) exactly as
specified in spec/card-format.md, then runs the lock's decision logic on those
bytes for every door.

  python3 check_access.py                          # access matrix, now
  python3 check_access.py --at "2026-11-24 03:00"  # at a site-local time
  python3 check_access.py --time-unknown           # lock lost its clock
  python3 check_access.py --door 4                 # explain one door
  python3 check_access.py --card 2001              # card bytes of one user

Standard library only (Python 3.9+); the format and decision logic come from
the shared package manager/src/ocmanager/protocol (no extra install).
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import _protocol  # noqa: F401  (shared implementation: manager/src/ocmanager/protocol)
from ocmanager.protocol import card as C
from ocmanager.protocol import decision as D

FORMAT_VERSION = C.FORMAT_VERSION
TYPE_DOOR, TYPE_ZONE = C.TYPE_DOOR, C.TYPE_ZONE
FILE1_SIZE = C.FILE1_SIZE
MAX_ENTRIES = C.MAX_ENTRIES

# Result symbols for the matrix
OPEN, NO_RIGHT, PROFILE, EXPIRED, BLACKLISTED, NO_TIME = "✓", "·", "t", "E", "B", "?"
SYMBOL = {D.OPEN: OPEN, D.NO_RIGHT: NO_RIGHT, D.PROFILE: PROFILE, D.EXPIRED: EXPIRED,
          D.BLACKLISTED: BLACKLISTED, D.NO_TIME: NO_TIME}


def unix(iso):
    """ISO 8601 UTC string -> unsigned 32-bit Unix seconds (0 = none)."""
    if not iso:
        return 0
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp())


# ---------------------------------------------------------------- encoder

def access_entries(site, user):
    """Role entries + individual extras, de-duplicated, as (type, id, profile)."""
    raw = [e for r in user["roles"] for e in site["roles"][r]["entries"]]
    raw += user.get("extra", [])
    try:
        entries = C.merge_entries([C.Entry(TYPE_DOOR, e["door"], e.get("profile", 0)) if "door" in e
                                   else C.Entry(TYPE_ZONE, e["zone"], e.get("profile", 0)) for e in raw])
    except ValueError as err:
        raise ValueError(f"{user['name']}: {err}") from err
    return [(e.kind, e.target, e.profile) for e in entries]


def encode_card(site, user):
    """Return (file0, file1) bytes per spec/card-format.md, format v1."""
    entries = [C.Entry(*e) for e in access_entries(site, user)]
    return C.encode_card(user["credential_id"], entries, unix(user.get("valid_until")),
                         unix(site["site"]["issued_at"]))


# ------------------------------------------------------------------- lock

class Lock:
    """What one lock knows after commissioning (never stored on the card)."""

    def __init__(self, site, door):
        self.door_id = door["id"]
        self.zones = set(door["zones"])
        self._model = D.LockModel(door["id"], set(door["zones"]), site["site"]["timezone"],
                                  {p["id"]: C.normalize_profile(p) for p in site["time_profiles"]},
                                  set(site["blacklist"]))

    def profile_allows(self, profile_id, now):
        return self._model.profile_allows(profile_id, now)

    def decide(self, file0, file1, now):
        """Decision logic from the spec, on raw card bytes. Returns (symbol, reason).

        `now` is Unix UTC seconds, or None if the lock's time is unknown.
        (Authentication with the site read key is assumed to have succeeded.)
        """
        result, reason = self._model.decide(file0, file1, now)
        return SYMBOL[result], reason


# -------------------------------------------------------------------- CLI

def parse_now(args, tz):
    if args.time_unknown:
        return None
    if args.at:
        return int(datetime.fromisoformat(args.at).replace(tzinfo=tz).timestamp())
    return int(datetime.now(timezone.utc).timestamp())


def show_card(site, user):
    file0, file1 = encode_card(site, user)
    zones = {z["id"]: z["name"] for z in site["zones"]}
    doors = {d["id"]: d["name"] for d in site["doors"]}
    print(f"{user['name']}  (credential {user['credential_id']}, "
          f"roles: {', '.join(user['roles'])})\n")
    print(f"file 0 (header, 16 bytes): {file0.hex(' ').upper()}")
    print(f"file 1 (access list):      {file1[:4 * len(access_entries(site, user))].hex(' ').upper()}"
          f"  (+ zero padding to {FILE1_SIZE} bytes)\n")
    for etype, target, profile in access_entries(site, user):
        name = doors[target] if etype == TYPE_DOOR else zones[target]
        kind = "door" if etype == TYPE_DOOR else "zone"
        prof = f"profile {profile}" if profile else "always"
        print(f"  {kind} {target:>3}  {name:<28} {prof}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=Path(__file__).with_name("site.json"), type=Path)
    ap.add_argument("--at", help='site-local time, e.g. "2026-11-24 14:30"')
    ap.add_argument("--time-unknown", action="store_true", help="lock has lost its clock")
    ap.add_argument("--door", type=int, help="explain the decisions at one door")
    ap.add_argument("--card", type=int, help="show the card bytes of one credential_id")
    args = ap.parse_args()

    site = json.loads(args.site.read_text())
    users = site["users"]

    if args.card is not None:
        show_card(site, next(u for u in users if u["credential_id"] == args.card))
        return

    tz = ZoneInfo(site["site"]["timezone"])
    now = parse_now(args, tz)
    when = "time UNKNOWN" if now is None else datetime.fromtimestamp(now, tz).strftime("%a %Y-%m-%d %H:%M %Z")
    print(f"{site['site']['name']} — {when}\n")
    cards = {u["credential_id"]: encode_card(site, u) for u in users}

    if args.door is not None:
        door = next(d for d in site["doors"] if d["id"] == args.door)
        lock = Lock(site, door)
        print(f"Door {door['id']}: {door['name']}  (zones {door['zones'] or '-'})\n")
        for u in users:
            sym, why = lock.decide(*cards[u["credential_id"]], now)
            print(f"  {sym}  {u['name']:<16} {why}")
        return

    doors = site["doors"]
    locks = [Lock(site, d) for d in doors]
    print(" " * 18 + " ".join(f"{d['id']:>2}" for d in doors))
    for u in users:
        row = [lock.decide(*cards[u["credential_id"]], now)[0] for lock in locks]
        print(f"{u['name']:<18}" + " ".join(f"{s:>2}" for s in row))
    print(f"\n{OPEN} open   {NO_RIGHT} no right   {PROFILE} not at this time   "
          f"{EXPIRED} expired   {BLACKLISTED} blacklisted   {NO_TIME} time unknown\n")
    for d in doors:
        print(f"  {d['id']:>2}  {d['name']}")


if __name__ == "__main__":
    main()
