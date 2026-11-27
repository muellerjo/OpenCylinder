"""Per-site DEV TEST keys for the example scripts.

Each example site's site.json may carry a "dev_keys" block (public bench test
keys — never real keys). Missing entries fall back to the values the
fictional hospital has always used, so existing dev cards keep working.

  "dev_keys": {
    "issuer_master":       "<16 bytes hex>",   # user app key 0 (diversified per card)
    "read_master":         "<16 bytes hex>",   # user app key 1 (diversified per card)
    "uid_key":             "<16 bytes hex>",   # user app key 2 (site-wide)
    "admin_issuer_master": "<16 bytes hex>",   # admin app key 0 (diversified)
    "admin_read_master":   "<16 bytes hex>",   # admin app key 1 (diversified)
    "management_key_file": "dev_management_key.pem"   # ECDSA P-256 signing key, relative to site.json
  }
"""

from pathlib import Path

HOSPITAL_DEFAULTS = {
    "issuer_master": "0F0E0D0C0B0A09080706050403020100",
    "read_master": "00112233445566778899AABBCCDDEEFF",
    "uid_key": "A0A1A2A3A4A5A6A7A8A9AAABACADAEAF",
    "admin_issuer_master": "1F1E1D1C1B1A19181716151413121110",
    "admin_read_master": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
    "management_key_file": "dev_management_key.pem",
}


def site_keys(site: dict, site_path: Path) -> dict:
    keys = dict(HOSPITAL_DEFAULTS)
    keys.update(site.get("dev_keys", {}))
    keys["management_key_path"] = (Path(site_path).resolve().parent / keys["management_key_file"])
    return keys
