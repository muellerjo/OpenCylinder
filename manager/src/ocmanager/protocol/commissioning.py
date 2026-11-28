"""Commissioning bundle for one lock (spec/admin-card.md §5.3).

Record 0x30 = ECIES to the lock's device key: ECDH P-256 + HKDF-SHA256 +
AES-128-GCM with the 27-byte bundle header as AAD.
"""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .bundle import HEADER_LEN, T_COMMISSIONING, build_bundle, public_key_raw, sign, tlv

AID = "4F434B"
HKDF_INFO = b"OpenCylinder commissioning v1"
QR_RE = re.compile(r"OC1:([0-9A-Fa-f]{16}):([0-9A-Fa-f]{66})")


@dataclass(frozen=True)
class LockIdentity:
    device_id: bytes     # 8 bytes
    public_key: bytes    # 33 bytes, compressed P-256

    @property
    def qr(self) -> str:
        return f"OC1:{self.device_id.hex().upper()}:{self.public_key.hex().upper()}"


def parse_qr(text: str) -> LockIdentity:
    m = QR_RE.fullmatch(text.strip())
    if not m:
        raise ValueError("expected OC1:<16 hex device ID>:<66 hex compressed public key>")
    pub = bytes.fromhex(m.group(2))
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub)  # must be on the curve
    return LockIdentity(bytes.fromhex(m.group(1)), pub)


@dataclass(frozen=True)
class SiteSecrets:
    """What a lock receives (never the issuer keys — those stay in the encoder)."""
    site_aid_wire: bytes
    admin_aid_wire: bytes
    read_master: bytes
    uid_key: bytes
    admin_read_master: bytes


def commissioning_bundle(lock: LockIdentity, secrets: SiteSecrets, signing_key, door: int,
                         zones: list[int], maintenance_records: bytes, sequence: int,
                         now: int, valid_until: int) -> bytes:
    plain = (secrets.site_aid_wire + secrets.admin_aid_wire + secrets.read_master +
             secrets.uid_key + secrets.admin_read_master + public_key_raw(signing_key) +
             struct.pack("<HB", door, len(zones)) + b"".join(struct.pack("<H", z) for z in zones))
    rec_len = 65 + 12 + len(plain) + 16
    payload_len = 3 + rec_len + len(maintenance_records)
    header = build_bundle(secrets.site_aid_wire, sequence, now, valid_until, bytes(payload_len),
                          target_device=lock.device_id)[:HEADER_LEN]

    lock_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), lock.public_key)
    eph = ec.generate_private_key(ec.SECP256R1())
    aes_key = HKDF(hashes.SHA256(), 16, salt=lock.device_id, info=HKDF_INFO).derive(
        eph.exchange(ec.ECDH(), lock_pub))
    nonce = os.urandom(12)
    record = (eph.public_key().public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.UncompressedPoint)
              + nonce + AESGCM(aes_key).encrypt(nonce, plain, header))
    assert len(record) == rec_len
    return sign(header + tlv(T_COMMISSIONING, record) + maintenance_records, signing_key)
