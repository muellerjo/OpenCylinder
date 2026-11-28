"""NXP AN10922 AES-128 key diversification (per-card keys).

OpenCylinder input (spec/card-format.md): M = card UID (7 bytes) || AID (3
bytes, wire order = LSB first). Implementation: ocmanager.protocol.an10922
(shared with the manager). Needs the `cryptography` package.

  python3 an10922.py      # runs the AN10922 known-answer test
"""

import _protocol  # noqa: F401  (import path to the shared protocol package)
from ocmanager.protocol.an10922 import diversify, opencylinder_input  # noqa: F401


def self_test() -> bool:
    # AN10922 §2.2.1 AES-128 example.
    mk = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    m = bytes.fromhex("04782E21801D80" "3042F5" "4E585020416275")
    return diversify(mk, m) == bytes.fromhex("A8DD63A3B89D54B37CA802473FDA9175")


if __name__ == "__main__":
    print("AN10922 known-answer test:", "PASS" if self_test() else "FAIL")
