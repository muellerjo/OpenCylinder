#!/usr/bin/env python3
"""Put a signed maintenance bundle onto a DESFire DEV card (admin application).

Adds the site's admin application (site.json "admin_aid", 2 AES keys,
diversified per card) NEXT TO any existing user application, and writes a
maintenance bundle (spec/admin-card.md): time, blacklist, time profiles and
time-zone rule, signed with the dev management key. A lock that sees the admin
application applies the bundle and never opens.

  python3 write_admin_card.py --dry-run                 # show bundle + commands
  python3 write_admin_card.py                           # full maintenance bundle from site.json
  python3 write_admin_card.py --blacklist-add 2001      # only: blacklist Sara
  python3 write_admin_card.py --blacklist-remove 2001   # only: un-blacklist Sara
  python3 write_admin_card.py --sequence 5              # force a (stale) sequence number
  python3 write_admin_card.py --tamper                  # manipulated bundle (must be refused)
  python3 write_admin_card.py --decommission             # one lock -> FACTORY (lock from locks.local.json)
  python3 write_admin_card.py --reassign --door 6        # one lock -> new door / zones
  python3 write_admin_card.py --remove                  # delete the admin application again

Dev card only (factory-default card master key). Needs the Proxmark3 client
and the Python `cryptography` package.
"""

import argparse
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from an10922 import diversify  # noqa: E402
from bundle import (T_BLACKLIST_ADD, T_BLACKLIST_REMOVE, T_BLACKLIST_REPLACE,  # noqa: E402
                    T_DECOMMISSION, T_LOCK_ASSIGNMENT, T_TIME_PROFILES, T_TZ_RULE, blacklist_value, build_bundle,
                    load_signing_key, profiles_value, public_key_raw, sign, tlv)
from write_test_card import ZERO, looks_failed, read_uid, run_pm3, step, verified  # noqa: E402

HERE = Path(__file__).resolve().parent

# ==== PUBLIC DEV TEST MASTER KEYS — bench only, never for a real site. ====
KA0_ADMIN_ISSUER_MASTER = "1F1E1D1C1B1A19181716151413121110"
KA1_ADMIN_READ_MASTER = "A1B2C3D4E5F60718293A4B5C6D7E8F90"

ADMIN_FORMAT_VERSION = 1
BUNDLE_FILE_SIZE = 0x400
ACT_TIME, ACT_BLACKLIST, ACT_PROFILES = 0x01, 0x02, 0x04
ACT_REASSIGN, ACT_DECOMMISSION = 0x08, 0x10


def unix(iso):
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def build_records(site, args):
    recs, actions = b"", ACT_TIME
    far_future = 0xFFFFFFFF
    if args.decommission:
        return tlv(T_DECOMMISSION, b""), actions | ACT_DECOMMISSION
    if args.reassign:
        zones = next(d["zones"] for d in site["doors"] if d["id"] == args.door)
        value = struct.pack("<HB", args.door, len(zones)) + b"".join(struct.pack("<H", z) for z in zones)
        return tlv(T_LOCK_ASSIGNMENT, value), actions | ACT_REASSIGN
    if args.blacklist_add or args.blacklist_remove:
        if args.blacklist_add:
            recs += tlv(T_BLACKLIST_ADD, blacklist_value((c, far_future) for c in args.blacklist_add))
        if args.blacklist_remove:
            recs += tlv(T_BLACKLIST_REMOVE, b"".join(struct.pack("<I", c) for c in args.blacklist_remove))
        actions |= ACT_BLACKLIST
    else:
        recs += tlv(T_BLACKLIST_REPLACE, blacklist_value((c, far_future) for c in site["blacklist"]))
        recs += tlv(T_TIME_PROFILES, profiles_value(site["time_profiles"]))
        recs += tlv(T_TZ_RULE, site["site"]["posix_tz"].encode("ascii"))
        actions |= ACT_BLACKLIST | ACT_PROFILES
    return recs, actions


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=HERE / "site.json", type=Path)
    ap.add_argument("--key", default=None, type=Path,
                    help="management signing key (PEM)")
    ap.add_argument("--decommission", action="store_true",
                    help="decommission ONE lock (needs --qr): it forgets the site -> FACTORY")
    ap.add_argument("--reassign", action="store_true",
                    help="give ONE lock (needs --qr) a new door / zones (needs --door)")
    ap.add_argument("--qr", help="target lock OC1:<device ID>:<public key>, or a device ID from "
                                 "locks.local.json (default: the only recorded lock)")
    ap.add_argument("--door", type=int, help="door ID from site.json (with --reassign)")
    ap.add_argument("--blacklist-add", type=int, nargs="+", metavar="ID")
    ap.add_argument("--blacklist-remove", type=int, nargs="+", metavar="ID")
    ap.add_argument("--sequence", type=int, help="default: current Unix time (monotonic)")
    ap.add_argument("--valid-days", type=float, default=2)
    ap.add_argument("--remove", action="store_true", help="delete the admin application")
    ap.add_argument("--recreate", action="store_true",
                    help="delete + recreate the admin application even if it exists. NOTE: DESFire "
                         "does not free memory on delete — only `hf mfdes formatpicc` does")
    ap.add_argument("--tamper", action="store_true",
                    help="flip one payload byte AFTER signing (lock must refuse: bad signature)")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3")
    ap.add_argument("--port")
    ap.add_argument("--uid", help="card UID for --dry-run (hex, 7 bytes)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    site = json.loads(args.site.read_text())
    from sitekeys import site_keys
    keys = site_keys(site, args.site)
    global KA0_ADMIN_ISSUER_MASTER, KA1_ADMIN_READ_MASTER
    KA0_ADMIN_ISSUER_MASTER = keys["admin_issuer_master"]
    KA1_ADMIN_READ_MASTER = keys["admin_read_master"]
    if args.key is None:
        args.key = keys["management_key_path"]
    admin_aid = site["site"]["admin_aid"]
    site_aid_wire = bytes.fromhex(site["site"]["aid"])[::-1]
    admin_aid_wire = bytes.fromhex(admin_aid)[::-1]

    if args.remove:
        steps = [step(f"delete admin application {admin_aid}",
                      f"hf mfdes deleteapp --aid {admin_aid}")]
    else:
        now = int(time.time())
        seq = args.sequence if args.sequence is not None else now
        target = bytes(8)
        if args.decommission or args.reassign:
            if args.reassign and args.door is None:
                sys.exit("--reassign needs --door")
            from write_commissioning_card import parse_qr, resolve_qr
            target, _pub = parse_qr(resolve_qr(args.qr))
        records, actions = build_records(site, args)
        key = load_signing_key(args.key)
        bundle = sign(build_bundle(site_aid_wire, seq, now, now + int(args.valid_days * 86400),
                                   records, target_device=target), key)
        if target != bytes(8):
            print(f"Targeted at device {target.hex().upper()}: "
                  f"{'DECOMMISSION' if args.decommission else f'reassign to door {args.door}'}")
        if args.tamper:
            b = bytearray(bundle)
            b[30] ^= 0x01  # inside the TLV payload
            bundle = bytes(b)
        if len(bundle) > BUNDLE_FILE_SIZE:
            sys.exit(f"bundle too large: {len(bundle)} bytes")
        header = struct.pack("<BBHIII", ADMIN_FORMAT_VERSION, actions, 0, 1,
                             now + int(args.valid_days * 86400), now)

        uid = bytes.fromhex(args.uid or "04000000000000") if args.dry_run else \
            read_uid(args.pm3, args.port)
        # Reuse an existing admin application: rewriting file contents costs no
        # card memory, while delete + create leaks it until the card is formatted.
        exists = False
        if not args.dry_run and not args.recreate:
            _rc, out = run_pm3(args.pm3, args.port, "hf mfdes getaids")
            exists = admin_aid.upper() in out.upper()
        m = uid + admin_aid_wire
        ka0 = diversify(bytes.fromhex(KA0_ADMIN_ISSUER_MASTER), m).hex().upper()
        ka1 = diversify(bytes.fromhex(KA1_ADMIN_READ_MASTER), m).hex().upper()
        auth0 = f"-n 0 -t aes -k {ka0}"
        auth1 = f"-n 1 -t aes -k {ka1}"
        rights = "--amode encrypt --rrights key1 --wrights key0 --rwrights key0 --chrights key0"

        def chkey(no, new):
            return (f"hf mfdes changekey --aid {admin_aid} -n 0 -t aes -k {ZERO} --newkeyno {no} "
                    f"--oldalgo aes --oldkey {ZERO} --newalgo aes --newkey {new} --newver 01")

        print(("Reusing the existing admin application (only file contents are rewritten).\n"
               if exists else "Creating the admin application.\n") if not args.dry_run else "", end="")
        print(f"Maintenance bundle: sequence {seq}, issued_at {now}, {len(bundle)} bytes, "
              f"signed with {args.key.name}")
        print(f"  lock public key (dev): {public_key_raw(key).hex().upper()}")
        print(f"  bundle: {bundle.hex().upper()}\n")
        create = [
            step(f"A1  delete old admin application {admin_aid} (may not exist)",
                 f"hf mfdes deleteapp --aid {admin_aid}", expect="any"),
            step(f"A2  create admin application {admin_aid} with 2 AES keys",
                 f"hf mfdes createapp --aid {admin_aid} --ks1 0B --dstalgo aes --numkeys 2"),
            step("A3  set key 1 (admin read key, diversified)", chkey(1, ka1)),
            step("A3  set key 0 (admin issuer key, diversified) — last", chkey(0, ka0)),
            step("B1  create file 0 (admin header, 16 bytes)",
                 f"hf mfdes createfile --aid {admin_aid} {auth0} --fid 00 --size 000010 {rights}"),
            step(f"B1  create file 1 (bundle, {BUNDLE_FILE_SIZE} bytes)",
                 f"hf mfdes createfile --aid {admin_aid} {auth0} --fid 01 "
                 f"--size {BUNDLE_FILE_SIZE:06X} {rights}"),
        ]
        steps = ([] if exists else create) + [
            step("B2  write admin header",
                 f"hf mfdes write --aid {admin_aid} {auth0} -m encrypt --fid 00 -d {header.hex().upper()}"),
            step("B2  write signed bundle",
                 f"hf mfdes write --aid {admin_aid} {auth0} -m encrypt --fid 01 -d {bundle.hex().upper()}"),
            step("C1  read bundle back with admin READ key",
                 f"hf mfdes read --aid {admin_aid} {auth1} -m encrypt --fid 01 -l {len(bundle):06X}",
                 verify_hex=bundle.hex().upper()),
        ]

    if args.dry_run:
        for s in steps:
            print(f"# {s['desc']}\n{s['cmd']}\n")
        return
    for i, s in enumerate(steps, 1):
        print(f"[{i:2}/{len(steps)}] {s['desc']}")
        print(f"        $ {s['cmd'][:150]}{' …' if len(s['cmd']) > 150 else ''}")
        _rc, out = run_pm3(args.pm3, args.port, s["cmd"])
        failed = looks_failed(out)
        if not failed and s["verify"]:
            failed = not verified(out, s["verify"])
        if s["expect"] == "any" or (failed if s["expect"] == "fail" else not failed):
            print("        ✓ ok")
            continue
        print("        ✗ unexpected result — stopping. Client output:\n")
        relevant = [l for l in out.splitlines() if l.startswith("[") and "Session log" not in l]
        print("\n".join("          " + l for l in relevant[-25:]))
        sys.exit(1)
    print("\nDone." if args.remove else
          "\nDone: admin application with a signed maintenance bundle is on the card.")


if __name__ == "__main__":
    main()
