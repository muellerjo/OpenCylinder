"""Signed management bundle — spec/admin-card.md §2 (file 1).

  header (27 bytes) | TLV payload | ECDSA P-256 signature (r || s, 64 bytes)

Needs the `cryptography` package.
"""

import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

BUNDLE_VERSION = 1

T_BLACKLIST_ADD = 0x10
T_BLACKLIST_REMOVE = 0x11
T_BLACKLIST_REPLACE = 0x12
T_TIME_PROFILES = 0x20
T_TZ_RULE = 0x21

DAY_BITS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def tlv(t, value: bytes) -> bytes:
    return struct.pack("<BH", t, len(value)) + value


def blacklist_value(entries):
    """entries: iterable of (credential_id, until_unix)."""
    return b"".join(struct.pack("<II", c, u) for c, u in entries)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def profiles_value(profiles):
    """site.json time_profiles -> n x 10-byte records (spec/time-profiles.md)."""
    out = b""
    for p in profiles:
        days = sum(1 << DAY_BITS[d] for d in p["days"])
        ivs = p.get("intervals", [{"from": p["from"], "to": p["to"]}])[:2]
        ivs += [{"from": "00:00", "to": "00:00"}] * (2 - len(ivs))
        out += struct.pack("<BB", p["id"], days)
        for iv in ivs:
            to = 1440 if iv["to"] == "24:00" else _minutes(iv["to"])
            out += struct.pack("<HH", _minutes(iv["from"]), to)
    return out


def build_bundle(site_aid_wire: bytes, sequence: int, issued_at: int, valid_until: int,
                 records: bytes, target_device: bytes = bytes(8)) -> bytes:
    """Unsigned bundle (header + payload)."""
    if len(site_aid_wire) != 3 or len(target_device) != 8:
        raise ValueError("site AID must be 3 bytes, target device 8 bytes")
    header = struct.pack("<BB3s8sIIIH", BUNDLE_VERSION, 0, site_aid_wire, target_device,
                         sequence, issued_at, valid_until, len(records))
    return header + records


def load_signing_key(path):
    data = open(path, "rb").read()
    data = data[data.index(b"-----BEGIN"):]  # skip the warning comment
    return serialization.load_pem_private_key(data, password=None)


def sign(unsigned: bytes, key) -> bytes:
    """Append ECDSA P-256 / SHA-256 signature as raw r || s."""
    der = key.sign(unsigned, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return unsigned + r.to_bytes(32, "big") + s.to_bytes(32, "big")


def public_key_raw(key) -> bytes:
    """Uncompressed public point (65 bytes, 0x04 || X || Y) — what locks store."""
    return key.public_key().public_bytes(serialization.Encoding.X962,
                                         serialization.PublicFormat.UncompressedPoint)
