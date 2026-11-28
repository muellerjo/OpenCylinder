"""Envelope encryption for site secrets (AES-256-GCM under a key-encryption key).

The KEK never lives in the database: it comes from OCM_MASTER_KEY or the file
data_dir/master.key (created with mode 0600 on first start). A database dump
alone does not reveal any site key. Each ciphertext is bound to its owner and
purpose through the AAD (e.g. "site:12:read_master"), so blobs cannot be
swapped between sites.

Production note: replace the file KEK by an HSM / TPM / OS keyring — the Vault
interface stays the same.
"""

import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"\x01"


class Vault:
    def __init__(self, kek: bytes):
        if len(kek) != 32:
            raise ValueError("master key must be 32 bytes")
        self._aead = AESGCM(kek)

    @classmethod
    def from_settings(cls, master_key_hex: str | None, data_dir: Path) -> "Vault":
        if master_key_hex:
            return cls(bytes.fromhex(master_key_hex))
        return cls(load_or_create_key_file(data_dir / "master.key", 32))

    def seal(self, plaintext: bytes, aad: str) -> bytes:
        nonce = os.urandom(12)
        return VERSION + nonce + self._aead.encrypt(nonce, plaintext, aad.encode())

    def open(self, blob: bytes, aad: str) -> bytes:
        if blob[:1] != VERSION:
            raise ValueError("unknown vault blob version")
        return self._aead.decrypt(blob[1:13], blob[13:], aad.encode())


def load_or_create_key_file(path: Path, n: int) -> bytes:
    if path.exists():
        return bytes.fromhex(path.read_text().strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(n)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
    return key
