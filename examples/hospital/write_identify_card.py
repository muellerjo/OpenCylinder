#!/usr/bin/env python3
"""Identify card — spec/admin-card.md §5.5.

A DESFire card with the identify application (AID 4F4349): one 64-byte file,
communication mode plain, FREE read and write access. Tap it on any lock (any
state) and the lock writes its public identity into it — nothing secret.

  python3 write_identify_card.py              # set up (or clear) the identify card
  python3 write_identify_card.py --read       # after tapping: read + decode it
  python3 write_identify_card.py --read --qr "OC1:...:..."   # compare with an engraved QR
  python3 write_identify_card.py --remove     # delete the identify application

A card with the identify application never opens a door (the lock checks it
first), so use a separate card. Dev cards only (factory-default card master
key). Needs the Proxmark3 client.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_test_card import ZERO, data_hex, looks_failed, run_pm3, step  # noqa: E402

AID = "4F4349"
SIZE = 64
STATES = {0: "FACTORY", 1: "OWNED"}


def decode(rec: bytes):
    if len(rec) < 51 or rec[0] == 0:
        return None
    dev, pub = rec[2:10], rec[10:43]
    return {
        "format": rec[0],
        "state": STATES.get(rec[1], f"? ({rec[1]})"),
        "device_id": dev.hex().upper(),
        "public_key": pub.hex().upper(),
        "firmware": f"{rec[43]}.{rec[44]}.{rec[45]}",
        "site_aid": rec[46:49][::-1].hex().upper(),   # stored in wire order
        "door_id": rec[49] | (rec[50] << 8),
        "qr": f"OC1:{dev.hex().upper()}:{pub.hex().upper()}",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--read", action="store_true", help="read and decode the identity")
    ap.add_argument("--qr", help="engraved QR text to compare with (OC1:<id>:<key>)")
    ap.add_argument("--remove", action="store_true", help="delete the identify application")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3")
    ap.add_argument("--port")
    args = ap.parse_args()

    def run(cmd):
        _rc, out = run_pm3(args.pm3, args.port, cmd)
        return out

    if args.read:
        out = run(f"hf mfdes read --aid {AID} --fid 00 --no-auth")
        if looks_failed(out):
            sys.exit("could not read the identify card (identify application missing?)")
        info = decode(bytes.fromhex(data_hex(out)[:SIZE * 2]))
        if info is None:
            sys.exit("identify card is empty — tap it on a lock first")
        for k, v in info.items():
            print(f"  {k:<11} {v}")
        if args.qr:
            same = args.qr.strip().upper() == info["qr"]
            print("\n  engraved QR:", "MATCHES the key the lock holds ✓" if same else
                  "DIFFERS from the key the lock holds ✗ — do not commission with the engraved key!")
        return

    if args.remove:
        steps = [step(f"delete identify application {AID}", f"hf mfdes deleteapp --aid {AID}")]
    else:
        exists = AID in run("hf mfdes getaids").upper()
        auth = f"-n 0 -t aes -k {ZERO}"
        steps = [] if exists else [
            step(f"create identify application {AID}",
                 f"hf mfdes createapp --aid {AID} --dstalgo aes --numkeys 1"),
            step("create file 0 (64 bytes, plain, free read/write)",
                 f"hf mfdes createfile --aid {AID} {auth} --fid 00 --size {SIZE:06X} --amode plain "
                 "--rrights free --wrights free --rwrights free --chrights key0"),
        ]
        steps.append(step("clear the identity file",
                          f"hf mfdes write --aid {AID} --fid 00 --no-auth -d {'00' * SIZE}"))

    for i, s in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {s['desc']}")
        out = run(s["cmd"])
        if looks_failed(out):
            print("        ✗ failed. Client output:\n")
            print("\n".join("          " + l for l in out.splitlines()
                            if l.startswith("[") and "Session log" not in l)[-15:])
            sys.exit(1)
        print("        ✓ ok")
    print("\nDone." if args.remove else
          "\nIdentify card ready: tap it on a lock, then run this script with --read.")


if __name__ == "__main__":
    main()
