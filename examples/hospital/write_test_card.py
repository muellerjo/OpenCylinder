#!/usr/bin/env python3
"""Write one user of the example hospital onto a DESFire DEV card via Proxmark3.

Sets the card up exactly as spec/card-format.md describes (bench simplification:
keys are NOT diversified per card yet), writes the user's record, reads it back
with the lock's read key and checks the key separation.

  python3 write_test_card.py --dry-run          # only show the commands
  python3 write_test_card.py                    # Sara Yilmaz (2001), asks before wiping
  python3 write_test_card.py --user 2002 --yes  # Max Huber, no question

!! Step 1 FORMATS THE CARD (all applications are deleted). Dev cards only,
!! card master key must still be the factory default.

Needs the Iceman/RRG Proxmark3 client (default: ~/proxmark3/pm3).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_access import access_entries, encode_card  # noqa: E402  (same folder)

# ==== PUBLIC DEV TEST KEYS — bench only, never for a real site. ====
ZERO = "00" * 16
K0_ISSUER = "0F0E0D0C0B0A09080706050403020100"
K1_READ = "00112233445566778899AABBCCDDEEFF"
K2_UID = "A0A1A2A3A4A5A6A7A8A9AAABACADAEAF"

ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Lines the Iceman client uses for errors / warnings
ERROR_MARKERS = ("[!!]", "[-]", "[!] ")
ERROR_WORDS = re.compile(r"error|fail|can't|cannot|not found|denied|timeout", re.I)


def step(desc, cmd, expect="ok", verify_hex=None):
    return {"desc": desc, "cmd": cmd, "expect": expect, "verify": verify_hex}


def build_steps(aid, file0, file1_used):
    auth0 = f"-n 0 -t aes -k {K0_ISSUER}"
    auth1 = f"-n 1 -t aes -k {K1_READ}"
    auth2 = f"-n 2 -t aes -k {K2_UID}"
    rights = "--amode encrypt --rrights key1 --wrights key0 --rwrights key0 --chrights key0"

    def chkey(no, new):
        return (f"hf mfdes changekey --aid {aid} -n 0 -t aes -k {ZERO} --newkeyno {no} "
                f"--oldalgo aes --oldkey {ZERO} --newalgo aes --newkey {new} --newver 01")

    s = [
        step("A1  format card (delete all applications)", "hf mfdes formatpicc"),
        step(f"A2  create application {aid} with 3 AES keys",
             f"hf mfdes createapp --aid {aid} --ks1 0B --dstalgo aes --numkeys 3"),
        step("A3  set key 1 (site read key)", chkey(1, K1_READ)),
        step("A3  set key 2 (UID key)", chkey(2, K2_UID)),
        step("A3  set key 0 (issuer key) — last", chkey(0, K0_ISSUER)),
        step(f"A4  application list contains {aid}", "hf mfdes getaids", verify_hex=aid),
        step("B1  create file 0 (header, 16 bytes)",
             f"hf mfdes createfile --aid {aid} {auth0} --fid 00 --size 000010 {rights}"),
        step("B1  create file 1 (access list, 128 bytes)",
             f"hf mfdes createfile --aid {aid} {auth0} --fid 01 --size 000080 {rights}"),
        step("B2  write header with issuer key",
             f"hf mfdes write --aid {aid} {auth0} -m encrypt --fid 00 -d {file0.hex().upper()}"),
    ]
    if file1_used:
        s.append(step("B2  write access list with issuer key",
                      f"hf mfdes write --aid {aid} {auth0} -m encrypt --fid 01 "
                      f"-d {file1_used.hex().upper()}"))
    s += [
        step("C1  read header with READ key (like a lock)",
             f"hf mfdes read --aid {aid} {auth1} -m encrypt --fid 00",
             verify_hex=file0.hex().upper()),
    ]
    if file1_used:
        s.append(step("C1  read access list with READ key",
                      f"hf mfdes read --aid {aid} {auth1} -m encrypt --fid 01 "
                      f"-l {len(file1_used):06X}",
                      verify_hex=file1_used.hex().upper()))
    s += [
        step("C2  write with READ key must be REFUSED (key separation)",
             f"hf mfdes write --aid {aid} {auth1} -m encrypt --fid 00 -d {'00' * 16}",
             expect="fail"),
        step("C3  read with UID key must be REFUSED (no file rights)",
             f"hf mfdes read --aid {aid} {auth2} -m encrypt --fid 00",
             expect="fail"),
    ]
    return s


def run_pm3(pm3, port, cmd):
    argv = [str(pm3)] + ([port] if port else []) + ["-c", cmd]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return p.returncode, ANSI.sub("", p.stdout + p.stderr)


def looks_failed(out):
    for line in out.splitlines():
        if line.startswith(ERROR_MARKERS) or (line.startswith("[") and ERROR_WORDS.search(line)):
            # The client echoes the session log path etc. with [=]; only flag real errors.
            if "Session log" not in line:
                return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=Path(__file__).with_name("site.json"), type=Path)
    ap.add_argument("--user", type=int, default=2001, help="credential_id (default 2001, Sara)")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3",
                    help="Proxmark3 client launcher (default ~/proxmark3/pm3)")
    ap.add_argument("--port", help="serial port, e.g. /dev/ttyACM1 (default: auto)")
    ap.add_argument("--dry-run", action="store_true", help="only print the commands")
    ap.add_argument("--yes", action="store_true", help="don't ask before formatting the card")
    args = ap.parse_args()

    site = json.loads(args.site.read_text())
    user = next((u for u in site["users"] if u["credential_id"] == args.user), None)
    if user is None:
        sys.exit(f"no user with credential_id {args.user} in {args.site}")

    file0, file1 = encode_card(site, user)
    file1_used = file1[:4 * len(access_entries(site, user))]
    aid = site["site"]["aid"]
    steps = build_steps(aid, file0, file1_used)

    print(f"Card for {user['name']} (credential {user['credential_id']}), site AID {aid}")
    print(f"  file 0: {file0.hex(' ').upper()}")
    print(f"  file 1: {file1_used.hex(' ').upper() or '(empty)'}\n")

    if args.dry_run:
        for s in steps:
            print(f"# {s['desc']}\n{s['cmd']}\n")
        return

    if not args.pm3.exists():
        sys.exit(f"Proxmark3 client not found at {args.pm3} (use --pm3)")
    if not args.yes:
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
            failed = s["verify"].upper() not in re.sub(r"\s", "", out).upper()

        ok = failed if s["expect"] == "fail" else not failed
        if ok:
            print("        ✓ refused as expected" if s["expect"] == "fail" else "        ✓ ok")
            continue

        print("        ✗ unexpected result — stopping. Client output:\n")
        relevant = [l for l in out.splitlines() if l.startswith("[") and "Session log" not in l]
        print("\n".join("          " + l for l in relevant[-25:]))
        sys.exit(1)

    print(f"\nDone: card holds {user['name']}'s record in application {aid}; "
          "read key reads it, read key cannot write, UID key cannot read.")


if __name__ == "__main__":
    main()
