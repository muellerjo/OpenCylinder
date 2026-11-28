"""NXP AN10922 AES-128 key diversification. M = UID (7) || AID (3, wire order)."""

from __future__ import annotations

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
    if len(uid) != 7 or len(aid_wire) != 3:
        raise ValueError("need a 7-byte UID and a 3-byte AID")
    return uid + aid_wire


def aid_wire(aid_hex: str) -> bytes:
    """AID as written in docs (MSB first, e.g. 4F4331) -> wire order (LSB first)."""
    return bytes.fromhex(aid_hex)[::-1]
