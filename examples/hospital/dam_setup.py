#!/usr/bin/env python3
"""Card OWNER: prepare a DESFire EV2/EV3 card for several independent sites (DAM).

Sets the three DAM keys at card level (0x10 auth, 0x11 MAC, 0x12 ENC) with the
card master key. Afterwards each site can create its own application in its
own DAM slot (write_test_card.py --dam SLOT --site <site.json>) — quota- and
AID-limited by the owner's grant; the owner never learns the site's keys.

  python3 dam_setup.py                    # set the DAM keys (factory card master key)
  python3 dam_setup.py --format           # wipe all applications first (dev card!)
  python3 dam_setup.py --grant --site ../ems-station/site.json --slot 1
                                          # owner-side grant for one site (no card needed)

A factory-fresh EV3 has no usable DAM keys: delegated creation is impossible
until the owner runs this. Dev cards only (factory-default card master key).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dam import DAM_AUTH_KEY, DAM_ENC_KEY, DAM_MAC_KEY, grant  # noqa: E402
from write_test_card import ZERO, looks_failed, run_pm3  # noqa: E402

HERE = Path(__file__).resolve().parent
DAM_KEYS = [(0x10, "DAM auth key", DAM_AUTH_KEY), (0x11, "DAM MAC key", DAM_MAC_KEY),
            (0x12, "DAM ENC key", DAM_ENC_KEY)]


def stored_2tdea(hex_key: str, version: int = 0) -> str:
    """How the card stores a 2TDEA key: the lowest bit of each byte is not key
    material; DESFire puts the key version into the first 8 bytes' lowest bits
    (MSB first), the second 8 bytes have it set (as reported by the Proxmark
    after ChangeKey, e.g. D0D1D2D3.. -> D0D0D2D2..D9D9DBDB..)."""
    out = bytearray(bytes.fromhex(hex_key))
    for i in range(8):
        out[i] = (out[i] & 0xFE) | ((version >> (7 - i)) & 1)
    for i in range(8, 16):
        out[i] |= 0x01
    return out.hex().upper()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--format", action="store_true", help="formatpicc first (deletes all apps)")
    ap.add_argument("--grant", action="store_true", help="only compute a grant for --site/--slot")
    ap.add_argument("--site", default=HERE / "site.json", type=Path)
    ap.add_argument("--slot", type=int, default=1)
    ap.add_argument("--quota", type=int, default=16, help="blocks of 32 bytes (default 16)")
    ap.add_argument("--out", type=Path, help="with --grant: write the grant to this JSON file")
    ap.add_argument("--pm3", type=Path, default=Path.home() / "proxmark3" / "pm3")
    ap.add_argument("--port")
    args = ap.parse_args()

    if args.grant:
        site = json.loads(args.site.read_text())
        aid_wire = bytes.fromhex(site["site"]["aid"])[::-1]
        g = grant(aid_wire, args.slot, args.quota, 0x0B, 0x83, initial_key=bytes(16))
        doc = {"site": site["site"]["name"], "aid": site["site"]["aid"],
               "dam_slot": args.slot, "quota_blocks": args.quota, "ks1": "0B", "ks2": "83",
               "initial_key": "00" * 16, "dam_auth_key": DAM_AUTH_KEY, **g}
        print(json.dumps(doc, indent=2))
        if args.out:
            args.out.write_text(json.dumps(doc, indent=2) + "\n")
            print(f"\nGrant written to {args.out}")
        print("\nHand this to the site: it authenticates with the DAM auth key and sends\n"
              "C9 <part1>, then AF <enck><dammac>. The DAM MAC/ENC keys stay with the owner.")
        return

    def run(cmd):
        _rc, out = run_pm3(args.pm3, args.port, cmd)
        return out

    if args.format:
        print("formatpicc ...", "✗" if looks_failed(run("hf mfdes formatpicc")) else "✓")
    for no, name, key in DAM_KEYS:
        print(f"set {name} (0x{no:02X}) ...", end=" ")
        base = f"hf mfdes changekey -n 0 -t 2tdea -k {ZERO} --newkeyno {no} --oldalgo 2tdea "
        out = run(base + f"--oldkey {ZERO} --newalgo 2tdea --newkey {key} --newver 00")
        if not looks_failed(out):
            print("✓ set")
            continue
        # Already set? The card keeps them across formatpicc, stored parity-adjusted.
        out = run(base + f"--oldkey {stored_2tdea(key)} --newalgo 2tdea --newkey {key} --newver 00")
        if looks_failed(out):
            print("✗ failed (card master key not default, or DAM keys set to other values)")
            sys.exit(1)
        print("✓ already set")
    print("\nCard ready for delegated applications (write_test_card.py --dam SLOT ...).\n"
          "Note: formatpicc deletes applications but keeps the DAM keys.")


if __name__ == "__main__":
    main()
