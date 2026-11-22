"""NXP AN10922 AES-128 key diversification (per-card keys).

OpenCylinder input (spec/card-format.md): M = card UID (7 bytes) || AID (3
bytes, wire order = LSB first). Needs the `cryptography` package.

  python3 an10922.py      # runs the AN10922 known-answer test
"""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _aes_ecb(key: bytes, block: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(block) + enc.finalize()


def _dbl(block: bytes) -> bytes:
    v = int.from_bytes(block, "big") << 1
    if block[0] & 0x80:
        v ^= 0x87
    return (v & ((1 << 128) - 1)).to_bytes(16, "big")


def diversify(master_key: bytes, m: bytes) -> bytes:
    """Per-card AES key from `master_key` and diversification input `m` (1..31 bytes)."""
    if not 1 <= len(m) <= 31:
        raise ValueError("diversification input must be 1..31 bytes")
    k1 = _dbl(_aes_ecb(master_key, bytes(16)))
    k2 = _dbl(k1)
    d = bytes([0x01]) + m
    padded = len(d) < 32
    if padded:
        d = d + b"\x80" + bytes(31 - len(d))
    last = bytes(a ^ b for a, b in zip(d[16:], k2 if padded else k1))
    x = _aes_ecb(master_key, d[:16])
    return _aes_ecb(master_key, bytes(a ^ b for a, b in zip(x, last)))


def opencylinder_input(uid: bytes, aid_wire: bytes) -> bytes:
    """M = UID (7 bytes) || AID (3 bytes, LSB first as sent on the wire)."""
    if len(uid) != 7 or len(aid_wire) != 3:
        raise ValueError("need a 7-byte UID and a 3-byte AID")
    return uid + aid_wire


def self_test() -> bool:
    # AN10922 §2.2.1 AES-128 example.
    mk = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    m = bytes.fromhex("04782E21801D80" "3042F5" "4E585020416275")
    return diversify(mk, m) == bytes.fromhex("A8DD63A3B89D54B37CA802473FDA9175")


if __name__ == "__main__":
    print("AN10922 known-answer test:", "PASS" if self_test() else "FAIL")
