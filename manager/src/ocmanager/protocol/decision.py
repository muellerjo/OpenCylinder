"""The lock's decision logic (spec/card-format.md), run on real card bytes."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .card import DAYS, FORMAT_VERSION, MAX_ENTRIES, TYPE_DOOR

OPEN, NO_RIGHT, PROFILE, EXPIRED, BLACKLISTED, NO_TIME = "open", "none", "profile", "expired", \
    "blacklisted", "notime"


@dataclass
class LockModel:
    door_id: int
    zones: set[int]
    timezone: str
    profiles: dict[int, dict]          # id -> {days, intervals}
    blacklist: set[int] = field(default_factory=set)

    def profile_allows(self, profile_id: int, now: int | None) -> bool:
        if profile_id == 0:
            return True
        p = self.profiles.get(profile_id)
        if p is None or now is None:
            return False                                  # fail closed
        local = datetime.fromtimestamp(now, ZoneInfo(self.timezone))
        hhmm = local.strftime("%H:%M")
        today, yesterday = DAYS[local.weekday()], DAYS[(local.weekday() + 6) % 7]
        for iv in p["intervals"]:
            f, t = iv["from"], iv["to"]
            if f < t and today in p["days"] and f <= hhmm < t:
                return True
            if f > t and ((today in p["days"] and hhmm >= f) or (yesterday in p["days"] and hhmm < t)):
                return True
        return False

    def decide(self, file0: bytes, file1: bytes, now: int | None) -> tuple[str, str]:
        version, count, _r, cred, valid_until, _issued = struct.unpack("<BBHIII", file0)
        if version != FORMAT_VERSION:
            return NO_RIGHT, f"unknown format_version {version}"
        if count > MAX_ENTRIES:
            return NO_RIGHT, "malformed entry_count"
        if valid_until and now is None:
            return NO_TIME, "time unknown and card has an expiry"
        if valid_until and now > valid_until:
            return EXPIRED, "card expired"
        if cred in self.blacklist:
            return BLACKLISTED, "credential blacklisted"
        blocked = False
        for i in range(count):
            kind, target, profile = struct.unpack_from("<BHB", file1, 4 * i)
            if (kind == TYPE_DOOR and target == self.door_id) or (kind != TYPE_DOOR and target in self.zones):
                if self.profile_allows(profile, now):
                    what = "door" if kind == TYPE_DOOR else "zone"
                    return OPEN, f"{what} {target}" + (f", profile {profile}" if profile else "")
                blocked = True
        if blocked:
            return PROFILE, "right exists, but not at this time"
        return NO_RIGHT, "no matching door/zone entry"
