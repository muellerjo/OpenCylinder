"""User card format v1 (spec/card-format.md): file 0 header + file 1 access list."""

from __future__ import annotations

import struct
from dataclasses import dataclass

FORMAT_VERSION = 1
TYPE_DOOR, TYPE_ZONE = 0x01, 0x02
FILE1_SIZE = 128
MAX_ENTRIES = FILE1_SIZE // 4
DAY_BITS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
DAYS = list(DAY_BITS)


def normalize_profile(p: dict) -> dict:
    """site.json profile (either from/to or intervals) -> {id, days, intervals}."""
    ivs = p.get("intervals") or [{"from": p["from"], "to": p["to"]}]
    return {"id": p["id"], "days": list(p["days"]), "intervals": [dict(i) for i in ivs]}


@dataclass(frozen=True)
class Entry:
    kind: int          # TYPE_DOOR or TYPE_ZONE
    target: int        # door or zone id (u16)
    profile: int = 0   # 0 = always

    def pack(self) -> bytes:
        return struct.pack("<BHB", self.kind, self.target, self.profile)


def merge_entries(raw: list[Entry]) -> list[Entry]:
    """De-duplicate, keep order (role entries first, then extras)."""
    out: list[Entry] = []
    for e in raw:
        if e not in out:
            out.append(e)
    if len(out) > MAX_ENTRIES:
        raise ValueError(f"{len(out)} entries > {MAX_ENTRIES} (file 1 is {FILE1_SIZE} bytes)")
    return out


def encode_card(credential_id: int, entries: list[Entry], valid_until: int, issued_at: int):
    """-> (file0 16 bytes, file1 FILE1_SIZE bytes)."""
    file0 = struct.pack("<BBHIII", FORMAT_VERSION, len(entries), 0, credential_id,
                        valid_until, issued_at)
    file1 = b"".join(e.pack() for e in entries)
    return file0, file1 + bytes(FILE1_SIZE - len(file1))
