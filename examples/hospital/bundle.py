"""Signed management bundle — spec/admin-card.md §2 (file 1).

  header (27 bytes) | TLV payload | ECDSA P-256 signature (r || s, 64 bytes)

Implementation: ocmanager.protocol.bundle (shared with the manager). Needs the
`cryptography` package.
"""

import _protocol  # noqa: F401
from ocmanager.protocol.bundle import (  # noqa: F401  (re-exported for the scripts)
    BUNDLE_VERSION, DAY_BITS, T_BLACKLIST_ADD, T_BLACKLIST_REMOVE, T_BLACKLIST_REPLACE,
    T_DECOMMISSION, T_LOCK_ASSIGNMENT, T_TIME_PROFILES, T_TZ_RULE, blacklist_value, build_bundle,
    load_signing_key_pem, profiles_value, public_key_raw, sign, tlv)


def load_signing_key(path):
    with open(path, "rb") as f:
        return load_signing_key_pem(f.read())
