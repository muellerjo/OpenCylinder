"""Puts manager/src on the import path.

The OpenCylinder wire formats (card files, signed bundles, AN10922,
commissioning, lock decision, Proxmark3 plans) exist ONCE, in
manager/src/ocmanager/protocol/. These example scripts and the manager web GUI
both use that package, so they cannot drift apart. Importing it needs no web
packages: card/decision are standard library only, the rest needs
`cryptography`.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "manager" / "src"
if not (SRC / "ocmanager" / "protocol").is_dir():
    sys.exit(f"shared protocol package not found at {SRC} — run from a full OpenCylinder checkout")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
