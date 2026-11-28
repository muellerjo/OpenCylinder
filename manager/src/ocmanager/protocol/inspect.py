"""Decode what is on a card: user files, admin header, bundles, identify record.

Pure functions on bytes (no reader, no database) — the reverse of card.py,
bundle.py and commissioning.py.
"""

from __future__ import annotations

import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from . import bundle as B
from .card import DAYS, TYPE_DOOR

RECORD_NAMES = {
    B.T_BLACKLIST_ADD: "blacklist add", B.T_BLACKLIST_REMOVE: "blacklist remove",
    B.T_BLACKLIST_REPLACE: "blacklist replace", B.T_TIME_PROFILES: "time profiles",
    B.T_TZ_RULE: "time-zone rule", B.T_COMMISSIONING: "commissioning (encrypted to the lock)",
    B.T_LOCK_ASSIGNMENT: "reassignment", B.T_DECOMMISSION: "decommission",
}
ACTION_NAMES = {B.ACT_TIME: "time", B.ACT_BLACKLIST: "blacklist", B.ACT_PROFILES: "profiles/TZ",
                B.ACT_REASSIGN: "reassign", B.ACT_DECOMMISSION: "decommission"}
IDENTIFY_AID = "4F4349"
IDENTIFY_STATES = {0: "FACTORY", 1: "OWNED"}


def user_header(file0: bytes) -> dict:
    version, count, _r, cred, valid_until, issued_at = struct.unpack("<BBHIII", file0[:16])
    return {"format_version": version, "entry_count": count, "credential_id": cred,
            "valid_until": valid_until, "issued_at": issued_at}


def user_entries(file1: bytes, count: int) -> list[dict]:
    out = []
    for i in range(min(count, len(file1) // 4)):
        kind, target, profile = struct.unpack_from("<BHB", file1, 4 * i)
        out.append({"kind": "door" if kind == TYPE_DOOR else "zone", "target": target, "profile": profile})
    return out


def admin_header(file0: bytes) -> dict:
    version, actions, _r, admin_id, valid_until, issued_at = struct.unpack("<BBHIII", file0[:16])
    return {"format_version": version, "actions": [n for bit, n in ACTION_NAMES.items() if actions & bit],
            "admin_id": admin_id, "valid_until": valid_until, "issued_at": issued_at}


def bundle_length(data: bytes) -> int | None:
    """Total length (header + payload + signature) from the header, None if not a bundle."""
    if len(data) < B.HEADER_LEN or data[0] != B.BUNDLE_VERSION:
        return None
    n = B.HEADER_LEN + B.parse_header(data)["payload_len"] + B.SIG_LEN
    return n if n <= len(data) else None


def _profiles(value: bytes) -> list[dict]:
    out = []
    for i in range(0, len(value) - 9, 10):
        pid, days = value[i], value[i + 1]
        ivs = []
        for k in range(2):
            f, t = struct.unpack_from("<HH", value, i + 2 + 4 * k)
            if f or t:
                ivs.append(f"{f // 60:02d}:{f % 60:02d}–{t // 60:02d}:{t % 60:02d}")
        out.append({"id": pid, "days": [d for b, d in enumerate(DAYS) if days & (1 << b)], "intervals": ivs})
    return out


def records(payload: bytes) -> list[dict]:
    out, i = [], 0
    while i + 3 <= len(payload):
        t, n = payload[i], struct.unpack_from("<H", payload, i + 1)[0]
        v = payload[i + 3:i + 3 + n]
        i += 3 + n
        rec = {"type": t, "name": RECORD_NAMES.get(t, f"unknown 0x{t:02X}"), "length": n}
        if t in (B.T_BLACKLIST_ADD, B.T_BLACKLIST_REPLACE):
            rec["entries"] = [dict(zip(("credential_id", "until"), struct.unpack_from("<II", v, k)))
                              for k in range(0, len(v) - 7, 8)]
        elif t == B.T_BLACKLIST_REMOVE:
            rec["entries"] = [{"credential_id": struct.unpack_from("<I", v, k)[0]} for k in range(0, len(v) - 3, 4)]
        elif t == B.T_TIME_PROFILES:
            rec["profiles"] = _profiles(v)
        elif t == B.T_TZ_RULE:
            rec["tz"] = v.decode("ascii", "replace")
        elif t == B.T_LOCK_ASSIGNMENT and len(v) >= 3:
            door, nz = struct.unpack_from("<HB", v)
            rec["door"], rec["zones"] = door, [struct.unpack_from("<H", v, 3 + 2 * k)[0] for k in range(nz)]
        out.append(rec)
    return out


def verify(bundle: bytes, public_key_raw: bytes) -> bool:
    """ECDSA P-256 / SHA-256 over header + payload, signature r || s."""
    try:
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_key_raw)
        sig = bundle[-B.SIG_LEN:]
        pub.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                   bundle[:-B.SIG_LEN], ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def decode_bundle(data: bytes) -> dict | None:
    n = bundle_length(data)
    if n is None:
        return None
    b = data[:n]
    h = B.parse_header(b)
    return {"raw": b, "site_aid": h["site_aid_wire"][::-1].hex().upper(),
            "target_device": None if h["target_device"] == bytes(8) else h["target_device"].hex().upper(),
            "sequence": h["sequence"], "issued_at": h["issued_at"], "valid_until": h["valid_until"],
            "records": records(b[B.HEADER_LEN:B.HEADER_LEN + h["payload_len"]]), "length": n}


def identify_record(rec: bytes) -> dict | None:
    if len(rec) < 51 or rec[0] == 0:
        return None
    dev, pub = rec[2:10].hex().upper(), rec[10:43].hex().upper()
    return {"format": rec[0], "state": IDENTIFY_STATES.get(rec[1], f"? ({rec[1]})"), "device_id": dev,
            "public_key": pub, "firmware": f"{rec[43]}.{rec[44]}.{rec[45]}",
            "site_aid": rec[46:49][::-1].hex().upper(), "door": rec[49] | (rec[50] << 8),
            "qr": f"OC1:{dev}:{pub}"}
