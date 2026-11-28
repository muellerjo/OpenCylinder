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
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle import (T_BLACKLIST_REPLACE, T_TIME_PROFILES, T_TZ_RULE,  # noqa: E402
                    blacklist_value, load_signing_key, profiles_value, tlv)
from sitekeys import site_keys  # noqa: E402
from write_test_card import looks_failed, run_pm3, step, verified  # noqa: E402
from ocmanager.protocol.bundle import COMMISSIONING_FILE_SIZE as FILE_SIZE  # noqa: E402
from ocmanager.protocol.commissioning import AID, LockIdentity, SiteSecrets  # noqa: E402
from ocmanager.protocol.commissioning import commissioning_bundle as _commissioning_bundle  # noqa: E402
from ocmanager.protocol.encoder import commissioning_card_plan  # noqa: E402

HERE = Path(__file__).resolve().parent


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
    """Signed commissioning bundle (shared implementation: ocmanager.protocol.commissioning)."""
    zones = next(d["zones"] for d in site["doors"] if d["id"] == door)
    wire = lambda aid: bytes.fromhex(aid)[::-1]  # noqa: E731
    secrets = SiteSecrets(wire(site["site"]["aid"]), wire(site["site"]["admin_aid"]),
                          bytes.fromhex(keys["read_master"]), bytes.fromhex(keys["uid_key"]),
                          bytes.fromhex(keys["admin_read_master"]))
    # Other records: maintenance data so the lock is complete after one tap.
    far = 0xFFFFFFFF
    others = (tlv(T_BLACKLIST_REPLACE, blacklist_value((c, far) for c in site["blacklist"])) +
              tlv(T_TIME_PROFILES, profiles_value(site["time_profiles"])) +
              tlv(T_TZ_RULE, site["site"]["posix_tz"].encode("ascii")))
    bundle = _commissioning_bundle(LockIdentity(device_id, lock_pub33), secrets, key, door, zones, others,
                                   sequence=now, now=now, valid_until=now + int(valid_days * 86400))
    return bundle, zones


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
        steps = commissioning_card_plan(bundle, app_exists=exists)

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
