#!/usr/bin/env python3
"""Write one user of the example hospital onto a DESFire DEV card via Proxmark3.

Sets the card up exactly as spec/card-format.md describes: keys 0 (issuer)
and 1 (read) diversified per card with NXP AN10922 (M = UID || AID), key 2
(UID key) site-wide. Writes the user's record, reads it back with the lock's
read key, checks the key separation, and verifies the diversification
independently with the Proxmark's own AN10922 implementation (--kdf).

  python3 write_test_card.py --dry-run          # only show the commands
  python3 write_test_card.py                    # Sara Yilmaz (2001), asks before wiping
  python3 write_test_card.py --user 2002 --yes  # Max Huber, no question
  python3 write_test_card.py --dam 2            # EV2/EV3: delegated app in DAM slot 2, no format

!! Step 1 FORMATS THE CARD (all applications are deleted). Dev cards only,
!! card master key must still be the factory default.

Needs the Iceman/RRG Proxmark3 client (default: ~/proxmark3/pm3) and the
Python `cryptography` package.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from an10922 import diversify, opencylinder_input  # noqa: E402
from check_access import access_entries, encode_card  # noqa: E402  (same folder)
from ocmanager.protocol import encoder as E  # noqa: E402  (shared Proxmark plans)
from ocmanager.protocol.encoder import Step  # noqa: E402

# ==== PUBLIC DEV TEST MASTER KEYS — bench only, never for a real site. ====
# Keys 0 and 1 on the card are diversified from these per card (AN10922).
ZERO = "00" * 16
K0_ISSUER_MASTER = "0F0E0D0C0B0A09080706050403020100"
K1_READ_MASTER = "00112233445566778899AABBCCDDEEFF"
K2_UID = "A0A1A2A3A4A5A6A7A8A9AAABACADAEAF"

def step(desc, cmd, expect="ok", verify_hex=None):
    return Step(desc, cmd, expect, verify_hex)


def build_steps(aid, file0, file1_used, k0_card, k1_card, kdf_input, dam_slot=None, dam_grant=None):
    """Commands for one card. Steps come from the shared plan builders."""
    if dam_slot is None:
        create = E.format_and_create_steps(aid)
    else:
        # DAM (EV2/EV3): no format — other sites' applications stay. The card
        # owner's DAM keys must be set (dam_setup.py). The site uses ONLY the
        # owner's grant (EncK, DAMMAC) and the DAM auth key — never the owner's
        # DAM ENC/MAC keys (needs the Proxmark client with --enck/--dammac).
        create = [E.dam_create_step(aid, dam_slot, dam_grant)]
    return (create + E.user_app_steps(aid, file0, file1_used, k0_card, k1_card, K2_UID)
            + E.kdf_check_steps(aid, K1_READ_MASTER, kdf_input))


def run_pm3(pm3, port, cmd):
    return 0, E.run_pm3(str(pm3), port, cmd)


def read_uid(pm3, port):
    """Real 7-byte UID of the card on the Proxmark (fixed-UID cards only)."""
    _rc, out = run_pm3(pm3, port, "hf 14a info")
    mt = E.UID_RE.search(out)
    if not mt:
        sys.exit("could not read a 7-byte card UID (card on the Proxmark? random UID?)")
    return bytes.fromhex(mt.group(1))


data_hex, verified, looks_failed = E.data_hex, E.verified, E.looks_failed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=Path(__file__).with_name("site.json"), type=Path)
    ap.add_argument("--user", type=int, default=2001, help="credential_id (default 2001, Sara)")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3",
                    help="Proxmark3 client launcher (default ~/proxmark3/pm3)")
    ap.add_argument("--port", help="serial port, e.g. /dev/ttyACM1 (default: auto)")
    ap.add_argument("--dry-run", action="store_true", help="only print the commands")
    ap.add_argument("--uid", help="card UID for --dry-run (hex, 7 bytes)")
    ap.add_argument("--yes", action="store_true", help="don't ask before formatting the card")
    ap.add_argument("--grant", type=Path, help="with --dam: the card owner's grant (dam_setup.py "
                    "--grant --out FILE); default: compute it here (bench: acting as owner)")
    ap.add_argument("--dam", type=int, metavar="SLOT",
                    help="EV2/EV3: create the application DELEGATED in this DAM slot instead of "
                         "formatting the card (other sites' applications stay; see dam_setup.py)")
    args = ap.parse_args()

    site = json.loads(args.site.read_text())
    from sitekeys import site_keys
    keys = site_keys(site, args.site)
    global K0_ISSUER_MASTER, K1_READ_MASTER, K2_UID
    K0_ISSUER_MASTER, K1_READ_MASTER, K2_UID = (keys["issuer_master"], keys["read_master"],
                                                keys["uid_key"])
    user = next((u for u in site["users"] if u["credential_id"] == args.user), None)
    if user is None:
        sys.exit(f"no user with credential_id {args.user} in {args.site}")

    file0, file1 = encode_card(site, user)
    file1_used = file1[:4 * len(access_entries(site, user))]
    aid = site["site"]["aid"]
    aid_wire = bytes.fromhex(aid)[::-1]          # LSB first, as on the wire

    if args.dry_run:
        uid = bytes.fromhex(args.uid or "04000000000000")
    else:
        if not args.pm3.exists():
            sys.exit(f"Proxmark3 client not found at {args.pm3} (use --pm3)")
        uid = read_uid(args.pm3, args.port)
    m = opencylinder_input(uid, aid_wire)
    k0_card = diversify(bytes.fromhex(K0_ISSUER_MASTER), m).hex().upper()
    k1_card = diversify(bytes.fromhex(K1_READ_MASTER), m).hex().upper()
    dam_grant = None
    if args.dam is not None:
        if args.grant:
            dam_grant = json.loads(args.grant.read_text())
            if dam_grant["aid"].upper() != aid.upper() or int(dam_grant["dam_slot"]) != args.dam:
                sys.exit(f"grant is for AID {dam_grant['aid']} slot {dam_grant['dam_slot']}, "
                         f"not {aid} slot {args.dam}")
            print(f"Using the card owner's grant from {args.grant.name} (no DAM ENC/MAC keys here)")
        else:
            from dam import DAM_AUTH_KEY, grant
            dam_grant = {"aid": aid, "dam_slot": args.dam, "quota_blocks": 16, "ks1": "0B",
                         "ks2": "83", "dam_auth_key": DAM_AUTH_KEY,
                         **grant(bytes.fromhex(aid)[::-1], args.dam, 16, 0x0B, 0x83, bytes(16))}
            print("No --grant given: computing the owner's grant here (bench: acting as card owner)")
    steps = build_steps(aid, file0, file1_used, k0_card, k1_card, m.hex().upper(), args.dam,
                        dam_grant)

    print(f"Card for {user['name']} (credential {user['credential_id']}), site AID {aid}")
    print(f"  card UID {uid.hex(' ').upper()}  ->  diversification input {m.hex(' ').upper()}")
    print(f"  file 0: {file0.hex(' ').upper()}")
    print(f"  file 1: {file1_used.hex(' ').upper() or '(empty)'}\n")

    if args.dry_run:
        for s in steps:
            print(f"# {s['desc']}\n{s['cmd']}\n")
        return
    if not args.yes and args.dam is None:
        answer = input("Step A1 FORMATS the card on the Proxmark (dev card only). Continue? [y/N] ")
        if answer.strip().lower() not in ("y", "yes", "j", "ja"):
            sys.exit("aborted, nothing was sent to the card")

    for i, s in enumerate(steps, 1):
        print(f"[{i:2}/{len(steps)}] {s['desc']}")
        print(f"        $ {s['cmd']}")
        try:
            _rc, out = run_pm3(args.pm3, args.port, s["cmd"])
        except subprocess.TimeoutExpired:
            sys.exit("        ✗ client timed out — is the Proxmark connected and the card on it?")

        failed = looks_failed(out)
        if not failed and s["verify"]:
            failed = not verified(out, s["verify"])

        ok = failed if s["expect"] == "fail" else not failed
        if ok:
            print("        ✓ refused as expected" if s["expect"] == "fail" else "        ✓ ok")
            continue

        print("        ✗ unexpected result — stopping. Client output:\n")
        relevant = [l for l in out.splitlines() if l.startswith("[") and "Session log" not in l]
        print("\n".join("          " + l for l in relevant[-25:]))
        sys.exit(1)

    print(f"\nDone: card holds {user['name']}'s record in application {aid}; "
          "read key reads it, read key cannot write, UID key cannot read;\n"
          "      keys are diversified per card (AN10922, matches the Proxmark's --kdf).")


if __name__ == "__main__":
    main()
