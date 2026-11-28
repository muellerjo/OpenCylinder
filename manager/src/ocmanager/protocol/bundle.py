"""Signed management bundles (spec/admin-card.md §2) and the admin header (file 0).

  header (27 bytes) | TLV payload | ECDSA P-256 signature (r || s, 64 bytes)
"""

from __future__ import annotations

import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

BUNDLE_VERSION = 1
HEADER_LEN = 27
SIG_LEN = 64
BUNDLE_FILE_SIZE = 0x400          # admin card file 1
COMMISSIONING_FILE_SIZE = 0x200   # commissioning card file 0

T_BLACKLIST_ADD = 0x10
T_BLACKLIST_REMOVE = 0x11
T_BLACKLIST_REPLACE = 0x12
T_TIME_PROFILES = 0x20
T_TZ_RULE = 0x21
T_COMMISSIONING = 0x30
T_LOCK_ASSIGNMENT = 0x31
T_DECOMMISSION = 0x40

ADMIN_FORMAT_VERSION = 1
ACT_TIME, ACT_BLACKLIST, ACT_PROFILES = 0x01, 0x02, 0x04
ACT_REASSIGN, ACT_DECOMMISSION = 0x08, 0x10

NO_EXPIRY = 0xFFFFFFFF
from .card import DAY_BITS, DAYS, normalize_profile  # noqa: E402,F401  (re-exported)


def tlv(t: int, value: bytes) -> bytes:
    return struct.pack("<BH", t, len(value)) + value


def blacklist_value(entries) -> bytes:
    """entries: iterable of (credential_id, until_unix)."""
    return b"".join(struct.pack("<II", c, u) for c, u in entries)


def minutes(hhmm: str) -> int:
    if hhmm == "24:00":
        return 1440
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def profiles_value(profiles) -> bytes:
    """profiles: iterable of dicts {id, days: [..], intervals: [{from, to}, ..]} -> 10-byte records."""
    out = b""
    for p in map(normalize_profile, profiles):
        days = sum(1 << DAY_BITS[d] for d in p["days"])
        ivs = list(p["intervals"])[:2]
        ivs += [{"from": "00:00", "to": "00:00"}] * (2 - len(ivs))
        out += struct.pack("<BB", p["id"], days)
        for iv in ivs:
            out += struct.pack("<HH", minutes(iv["from"]), minutes(iv["to"]))
    return out


def assignment_value(door: int, zones: list[int]) -> bytes:
    return struct.pack("<HB", door, len(zones)) + b"".join(struct.pack("<H", z) for z in zones)


def build_bundle(site_aid_wire: bytes, sequence: int, issued_at: int, valid_until: int,
                 records: bytes, target_device: bytes = bytes(8)) -> bytes:
    if len(site_aid_wire) != 3 or len(target_device) != 8:
        raise ValueError("site AID must be 3 bytes, target device 8 bytes")
    header = struct.pack("<BB3s8sIIIH", BUNDLE_VERSION, 0, site_aid_wire, target_device,
                         sequence, issued_at, valid_until, len(records))
    return header + records


def admin_header(actions: int, valid_until: int, issued_at: int, admin_id: int = 1) -> bytes:
    return struct.pack("<BBHIII", ADMIN_FORMAT_VERSION, actions, 0, admin_id, valid_until, issued_at)


# ------------------------------------------------------------- signing keys

def generate_signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def signing_key_pem(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def load_signing_key_pem(data: bytes):
    if b"-----BEGIN" in data:
        data = data[data.index(b"-----BEGIN"):]   # dev key files carry a warning comment
    return serialization.load_pem_private_key(data, password=None)


def sign(unsigned: bytes, key) -> bytes:
    der = key.sign(unsigned, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return unsigned + r.to_bytes(32, "big") + s.to_bytes(32, "big")


def public_key_raw(key) -> bytes:
    """Uncompressed point (65 bytes) — what locks store."""
    return key.public_key().public_bytes(serialization.Encoding.X962,
                                         serialization.PublicFormat.UncompressedPoint)


def parse_header(bundle: bytes) -> dict:
    v, _r, aid, target, seq, issued, until, plen = struct.unpack_from("<BB3s8sIIIH", bundle)
    return {"version": v, "site_aid_wire": aid, "target_device": target, "sequence": seq,
            "issued_at": issued, "valid_until": until, "payload_len": plen}
