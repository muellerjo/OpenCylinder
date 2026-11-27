#!/usr/bin/env python3
"""Commissioning card for ONE lock — spec/admin-card.md §5.3.

Builds a signed commissioning bundle targeted at the lock's device ID. Its
record 0x30 carries the site keys, door ID and zones, encrypted to the lock's
own public key (ECIES: ECDH P-256 + HKDF-SHA256 + AES-128-GCM, bundle header
as AAD) — readable by that lock only. The bundle also carries the site's time
profiles, time-zone rule and blacklist, so the lock is fully configured after
one tap. Written into the commissioning application (AID 4F434B, one file with
free read access: a blank lock has no keys, the content protects itself).

  python3 write_commissioning_card.py --qr "OC1:<device ID>:<public key>" --door 4
  python3 write_commissioning_card.py --qr "OC1:..." --door 4 --dry-run
  python3 write_commissioning_card.py --remove

The QR text comes from the engraving, the lock's banner / `id` command, or an
identify card (write_identify_card.py --read). Locks are recorded in the
git-ignored site database locks.local.json. Dev card only. Needs the
Proxmark3 client and the Python `cryptography` package.
"""

import argparse
import json
import os
import re
import struct
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle import (T_BLACKLIST_REPLACE, T_TIME_PROFILES, T_TZ_RULE,  # noqa: E402
                    blacklist_value, build_bundle, load_signing_key, profiles_value,
                    public_key_raw, sign, tlv)
from sitekeys import site_keys  # noqa: E402
from write_test_card import ZERO, looks_failed, run_pm3, step, verified  # noqa: E402

HERE = Path(__file__).resolve().parent
AID = "4F434B"
FILE_SIZE = 0x200
T_COMMISSIONING = 0x30
HKDF_INFO = b"OpenCylinder commissioning v1"


def parse_qr(text):
    m = re.fullmatch(r"OC1:([0-9A-Fa-f]{16}):([0-9A-Fa-f]{66})", text.strip())
    if not m:
        sys.exit("QR text must look like OC1:<16 hex device ID>:<66 hex compressed public key>")
    return bytes.fromhex(m.group(1)), bytes.fromhex(m.group(2))


def resolve_qr(qr):
    """QR text given, or taken from the site database locks.local.json:
    --qr may be omitted if exactly one lock is recorded, or be just a device ID
    (prefix) of a recorded lock."""
    if qr and qr.strip().upper().startswith("OC1:"):
        return qr
    db_path = HERE / "locks.local.json"
    locks = json.loads(db_path.read_text())["locks"] if db_path.exists() else {}
    matches = [d for d in locks if not qr or d.startswith(qr.strip().upper())]
    if len(matches) != 1:
        sys.exit(f"cannot pick a lock from {db_path.name} ({len(matches)} match): pass --qr \"OC1:...\" "
                 "or a device ID")
    dev = matches[0]
    print(f"Lock from site database: device {dev} (door {locks[dev]['door']})")
    return f"OC1:{dev}:{locks[dev]['public_key']}"


def commissioning_bundle(site, door, device_id, lock_pub33, key, now, valid_days, keys):
    zones = next(d["zones"] for d in site["doors"] if d["id"] == door)
    wire = lambda aid: bytes.fromhex(aid)[::-1]  # noqa: E731
    mgmt_pub = public_key_raw(key)  # uncompressed, 65 bytes
    plain = (wire(site["site"]["aid"]) + wire(site["site"]["admin_aid"]) +
             bytes.fromhex(keys["read_master"]) + bytes.fromhex(keys["uid_key"]) +
             bytes.fromhex(keys["admin_read_master"]) + mgmt_pub +
             struct.pack("<HB", door, len(zones)) + b"".join(struct.pack("<H", z) for z in zones))

    # Other records: maintenance data so the lock is complete after one tap.
    far = 0xFFFFFFFF
    others = (tlv(T_BLACKLIST_REPLACE, blacklist_value((c, far) for c in site["blacklist"])) +
              tlv(T_TIME_PROFILES, profiles_value(site["time_profiles"])) +
              tlv(T_TZ_RULE, site["site"]["posix_tz"].encode("ascii")))
    rec_len = 65 + 12 + len(plain) + 16
    payload_len = 3 + rec_len + len(others)
    # Header (27 bytes) depends only on the payload length -> build it first, it is the AAD.
    header = build_bundle(wire(site["site"]["aid"]), now, now, now + int(valid_days * 86400),
                          bytes(payload_len), target_device=device_id)[:27]

    lock_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), lock_pub33)
    eph = ec.generate_private_key(ec.SECP256R1())
    shared = eph.exchange(ec.ECDH(), lock_pub)
    aes_key = HKDF(hashes.SHA256(), 16, salt=device_id, info=HKDF_INFO).derive(shared)
    nonce = os.urandom(12)
    ct_tag = AESGCM(aes_key).encrypt(nonce, plain, header)
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.UncompressedPoint)
    record = eph_pub + nonce + ct_tag
    assert len(record) == rec_len
    unsigned = header + tlv(T_COMMISSIONING, record) + others
    assert len(unsigned) == 27 + payload_len
    return sign(unsigned, key), zones


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qr", help="lock identity OC1:<device ID>:<public key>, or a device ID "
                                 "from locks.local.json (default: the only recorded lock)")
    ap.add_argument("--door", type=int, help="door ID from site.json")
    ap.add_argument("--site", default=HERE / "site.json", type=Path)
    ap.add_argument("--key", default=None, type=Path, help="default: the site's management key")
    ap.add_argument("--valid-days", type=float, default=2)
    ap.add_argument("--remove", action="store_true", help="delete the commissioning application")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3")
    ap.add_argument("--port")
    args = ap.parse_args()

    def run(cmd):
        _rc, out = run_pm3(args.pm3, args.port, cmd)
        return out

    if args.remove:
        steps = [step(f"delete commissioning application {AID}", f"hf mfdes deleteapp --aid {AID}")]
    else:
        if args.door is None:
            sys.exit("--door is required")
        site = json.loads(args.site.read_text())
        keys = site_keys(site, args.site)
        device_id, lock_pub33 = parse_qr(resolve_qr(args.qr))
        key = load_signing_key(args.key or keys["management_key_path"])
        now = int(time.time())
        bundle, zones = commissioning_bundle(site, args.door, device_id, lock_pub33, key, now,
                                             args.valid_days, keys)
        if len(bundle) > FILE_SIZE:
            sys.exit(f"bundle too large: {len(bundle)} bytes")
        print(f"Commissioning bundle for device {device_id.hex().upper()}: door {args.door}, "
              f"zones {zones}, sequence {now}, {len(bundle)} bytes")
        if args.dry_run:
            print(bundle.hex().upper())
            return
        exists = AID in run("hf mfdes getaids").upper()
        auth = f"-n 0 -t aes -k {ZERO}"
        steps = [] if exists else [
            step(f"create commissioning application {AID}",
                 f"hf mfdes createapp --aid {AID} --ks1 0B --dstalgo aes --numkeys 1"),
            step(f"create file 0 ({FILE_SIZE} bytes, plain, free read)",
                 f"hf mfdes createfile --aid {AID} {auth} --fid 00 --size {FILE_SIZE:06X} --amode plain "
                 "--rrights free --wrights key0 --rwrights key0 --chrights key0"),
        ]
        steps += [
            step("write commissioning bundle",
                 f"hf mfdes write --aid {AID} {auth} -m plain --fid 00 -d {bundle.hex().upper()}"),
            step("read back (free read)",
                 f"hf mfdes read --aid {AID} --fid 00 --no-auth -l {len(bundle):06X}",
                 verify_hex=bundle.hex().upper()),
        ]

    for i, s in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {s['desc']}")
        out = run(s["cmd"])
        bad = looks_failed(out) or (s["verify"] and not verified(out, s["verify"]))
        if bad:
            print("        ✗ failed. Client output:\n")
            print("\n".join("          " + l for l in out.splitlines()
                            if l.startswith("[") and "Session log" not in l)[-15:])
            sys.exit(1)
        print("        ✓ ok")

    if args.remove:
        print("\nDone.")
        return
    db_path = HERE / "locks.local.json"
    db = json.loads(db_path.read_text()) if db_path.exists() else {"locks": {}}
    db["locks"][device_id.hex().upper()] = {
        "public_key": lock_pub33.hex().upper(), "door": args.door, "zones": zones,
        "commissioned_sequence": now,
        "commissioning_card_written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }
    db_path.write_text(json.dumps(db, indent=2) + "\n")
    print(f"\nCommissioning card ready for device {device_id.hex().upper()} (door {args.door}). "
          f"Recorded in {db_path.name}.\nTap it on the FACTORY lock.")


if __name__ == "__main__":
    main()
