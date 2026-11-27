"""DESFire EV2/EV3 Delegated Application Management (DAM) — the card owner's part.

The card OWNER (who holds the card master key) sets three DAM keys at card
level once (0x10 auth, 0x11 MAC, 0x12 ENC). To let a SITE create its own
application, the owner computes a GRANT for exactly that application:

  part1  = AID (3, LE) | DAM slot (2, LE) | slot version | quota (2, LE, in
           32-byte blocks) | key settings 1 | key settings 2
  EncK   = 2TDEA-CBC(DAM ENC key, IV 0,
                     7 random bytes | initial app key (16) | key version | 0-pad to 32)
  DAMMAC = CMAC(DAM MAC key, 0xC9 | part1 | EncK)        (8 bytes for 2TDEA)

The site sends CreateDelegatedApplication (0xC9: part1, then 0xAF: EncK |
DAMMAC) after authenticating with the DAM auth key, then immediately replaces
the initial app key with its own keys — the owner never learns them. The card
checks the DAMMAC, so the site can create only that AID, in that slot, with at
most that quota.

Verified against the Proxmark3 implementation (`hf mfdes createdelegateapp`
trace: same DAMMAC) and accepted by a real DESFire EV3.

  python3 dam.py            # self-test against the recorded Proxmark trace
"""

import os
import struct
import warnings

from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.cmac import CMAC

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:  # older cryptography
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

CMD_CREATE_DELEGATED_APP = 0xC9

# ==== PUBLIC DEV TEST DAM KEYS (card owner) — bench only. ====
DAM_AUTH_KEY = "D0D1D2D3D4D5D6D7D8D9DADBDCDDDEDF"   # key 0x10
DAM_MAC_KEY = "E0E1E2E3E4E5E6E7E8E9EAEBECEDEEEF"    # key 0x11
DAM_ENC_KEY = "F0F1F2F3F4F5F6F7F8F9FAFBFCFDFEFF"    # key 0x12


def _tdes(key):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return TripleDES(key)


def part1(aid_wire: bytes, slot: int, slot_version: int, quota_blocks: int, ks1: int, ks2: int) -> bytes:
    return aid_wire + struct.pack("<HBHBB", slot, slot_version, quota_blocks, ks1, ks2)


def enck(enc_key: bytes, initial_key: bytes, key_version: int = 0, prefix: bytes = None) -> bytes:
    prefix = os.urandom(7) if prefix is None else prefix
    plain = prefix + initial_key + bytes([key_version])
    plain += bytes(32 - len(plain))
    e = Cipher(_tdes(enc_key), modes.CBC(bytes(8))).encryptor()
    return e.update(plain) + e.finalize()


def dammac(mac_key: bytes, p1: bytes, cryptogram: bytes) -> bytes:
    c = CMAC(_tdes(mac_key))
    c.update(bytes([CMD_CREATE_DELEGATED_APP]) + p1 + cryptogram)
    return c.finalize()


def grant(aid_wire, slot, quota_blocks, ks1, ks2, initial_key, key_version=0, slot_version=0,
          enc_key=bytes.fromhex(DAM_ENC_KEY), mac_key=bytes.fromhex(DAM_MAC_KEY)):
    """Everything a site needs (besides the DAM auth key) to create its app."""
    p1 = part1(aid_wire, slot, slot_version, quota_blocks, ks1, ks2)
    k = enck(enc_key, initial_key, key_version)
    return {"part1": p1.hex().upper(), "enck": k.hex().upper(),
            "dammac": dammac(mac_key, p1, k).hex().upper()}


def self_test() -> bool:
    # Recorded from a Proxmark3 createdelegateapp run (verbose trace).
    p1 = bytes.fromhex("32434F00010000100B83")
    crypt = bytes.fromhex("070ACF7E7F6B05677B85001977459C8521CE7BA1A730CFBC53AFEF5497203CAA")
    if dammac(bytes.fromhex(DAM_MAC_KEY), p1, crypt) != bytes.fromhex("190FB9838E8A8880"):
        return False
    d = Cipher(_tdes(bytes.fromhex(DAM_ENC_KEY)), modes.CBC(bytes(8))).decryptor()
    plain = d.update(crypt) + d.finalize()
    if plain[7:24] != bytes(17) or plain[24:] != bytes(8):
        return False
    # Round trip of our own EncK
    k = enck(bytes.fromhex(DAM_ENC_KEY), bytes(range(16)), 3, prefix=bytes(7))
    d = Cipher(_tdes(bytes.fromhex(DAM_ENC_KEY)), modes.CBC(bytes(8))).decryptor()
    return (d.update(k) + d.finalize())[7:24] == bytes(range(16)) + b"\x03"


if __name__ == "__main__":
    print("DAM self-test (Proxmark trace):", "PASS" if self_test() else "FAIL")
