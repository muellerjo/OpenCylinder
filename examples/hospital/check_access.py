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

Standard library only (Python 3.9+).
"""

import argparse
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FORMAT_VERSION = 1
TYPE_DOOR, TYPE_ZONE = 0x01, 0x02
FILE1_SIZE = 128                       # default: 32 entries x 4 bytes
MAX_ENTRIES = FILE1_SIZE // 4
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Result symbols for the matrix
OPEN, NO_RIGHT, PROFILE, EXPIRED, BLACKLISTED, NO_TIME = "✓", "·", "t", "E", "B", "?"


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
    out = []
    for e in raw:
        t = (TYPE_DOOR, e["door"]) if "door" in e else (TYPE_ZONE, e["zone"])
        entry = (*t, e.get("profile", 0))
        if entry not in out:
            out.append(entry)
    if len(out) > MAX_ENTRIES:
        raise ValueError(f"{user['name']}: {len(out)} entries > {MAX_ENTRIES}")
    return out


def encode_card(site, user):
    """Return (file0, file1) bytes per spec/card-format.md, format v1."""
    entries = access_entries(site, user)
    file0 = struct.pack(
        "<BBHIII",
        FORMAT_VERSION,
        len(entries),
        0,                                        # reserved
        user["credential_id"],
        unix(user.get("valid_until")),
        unix(site["site"]["issued_at"]),
    )
    file1 = b"".join(struct.pack("<BHB", *e) for e in entries)
    file1 += bytes(FILE1_SIZE - len(file1))       # unused entries are zero
    return file0, file1


# ------------------------------------------------------------------- lock

class Lock:
    """What one lock knows after commissioning (never stored on the card)."""

    def __init__(self, site, door):
        self.door_id = door["id"]
        self.zones = set(door["zones"])
        self.tz = ZoneInfo(site["site"]["timezone"])
        self.profiles = {p["id"]: p for p in site["time_profiles"]}
        self.blacklist = set(site["blacklist"])

    def profile_allows(self, profile_id, now):
        if profile_id == 0:
            return True                           # 0 = always
        p = self.profiles.get(profile_id)
        if p is None or now is None:
            return False                          # unknown profile / time: fail closed
        local = datetime.fromtimestamp(now, self.tz)
        hhmm = local.strftime("%H:%M")
        return DAYS[local.weekday()] in p["days"] and p["from"] <= hhmm < p["to"]

    def decide(self, file0, file1, now):
        """Decision logic from the spec, on raw card bytes. Returns (symbol, reason).

        `now` is Unix UTC seconds, or None if the lock's time is unknown.
        (Authentication with the site read key is assumed to have succeeded.)
        """
        version, count, _res, cred, valid_until, _issued = struct.unpack("<BBHIII", file0)
        if version != FORMAT_VERSION:
            return NO_RIGHT, f"unknown format_version {version}"
        if count > MAX_ENTRIES:
            return NO_RIGHT, "malformed entry_count"
        if valid_until != 0 and now is None:
            return NO_TIME, "time unknown and card has an expiry"
        if valid_until != 0 and now > valid_until:
            return EXPIRED, "card expired"
        if cred in self.blacklist:
            return BLACKLISTED, "credential blacklisted"

        profile_blocked = False
        for i in range(count):
            etype, target, profile = struct.unpack_from("<BHB", file1, 4 * i)
            if (etype == TYPE_DOOR and target == self.door_id) or \
               (etype == TYPE_ZONE and target in self.zones):
                if self.profile_allows(profile, now):
                    kind = "door" if etype == TYPE_DOOR else "zone"
                    return OPEN, f"{kind} {target}" + (f", profile {profile}" if profile else "")
                profile_blocked = True
        if profile_blocked:
            return PROFILE, "right exists, but not at this time"
        return NO_RIGHT, "no matching door/zone entry"


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
