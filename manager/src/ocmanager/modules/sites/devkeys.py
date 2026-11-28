"""PUBLIC DEV TEST KEYS of the fictional example hospital (examples/hospital/sitekeys.py).

Bench only — they are published in the repository and protect nothing. A site
imported with them is flagged `dev_keys` and shown with a warning everywhere.
"""

HOSPITAL_DEFAULTS = {
    "issuer_master": "0F0E0D0C0B0A09080706050403020100",
    "read_master": "00112233445566778899AABBCCDDEEFF",
    "uid_key": "A0A1A2A3A4A5A6A7A8A9AAABACADAEAF",
    "admin_issuer_master": "1F1E1D1C1B1A19181716151413121110",
    "admin_read_master": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
}
