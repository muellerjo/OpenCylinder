"""OpenCylinder wire formats — pure functions, no web, no database.

Byte-for-byte the same encoding as the reference scripts in
examples/hospital/ (checked by tests/test_protocol_equivalence.py):

- card.py          user card files 0/1 (spec/card-format.md)
- bundle.py        signed management bundles (spec/admin-card.md §2)
- an10922.py       per-card AES key diversification
- commissioning.py commissioning record 0x30, encrypted to one lock (§5.3)
- decision.py      the lock's access decision, for the access matrix
- encoder.py       Proxmark3 command plans for the dev encoder
"""
