# Encoder tools

Desktop side of OpenCylinder: reads and (later) personalises cards through an
**Elatec TWN4** reader running the Simple Protocol firmware (USB serial).
Version: see `../VERSION`.

- `twn4.py` — minimal TWN4 Simple Protocol driver (search tag, ATQA/SAK/ATS,
  DESFire GetVersion / application IDs, Ultralight reads).
- `read_cards.py` — prints UID, chip family and DESFire applications of each
  card held to the reader.

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 read_cards.py --port /dev/ttyACM0
```

Planned: card personalisation per `../../spec/card-format.md` and lock
commissioning per `../../docs/commissioning.md`.
