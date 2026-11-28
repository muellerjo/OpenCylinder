# Hardware

Electronics (PCB, antenna) and mechanics (cylinder body, clutch) of
OpenCylinder. Version: see `VERSION`; each manufactured PCB additionally
carries a board revision (`rev A`, `rev B`, …) on the silkscreen
(see `../docs/versioning.md`).

**Licence:** the hardware design files in this folder (PCB, antenna,
mechanics, OpenSCAD models, drawings) are licensed under
[CERN-OHL-P-2.0](LICENSE), the permissive CERN Open Hardware Licence.
Scripts (e.g. `antenna/gen_coil.py`) stay MIT like the rest of the repository.
Third-party reference photos in `mechanics/prior-art/images-local/` are not
part of the repository and not covered by any of these licences.

- `mechanics/clutch-design.md` — clutch / actuator concept and prior-art pool.
- `knob-electronics.md` — knob electronics concept (architecture, dimension budget, antenna).
- `design-plan.md` — detailed plan: housing, mechanics (clutch in the body), components, PCB, sequence H1–H8.
- `mechanics/knob-mockup/` — OpenSCAD knob mock-up (Ø 38 × 42 mm).
- `antenna/` — parametric NFC coil generator and KiCad footprint.

## Current bench setup

- MCU (dev): ESP32-C3 SuperMini or Seeed XIAO ESP32C3
- NFC frontend: ST25R3916 (M5Stack Unit NFC, I2C over Grove)
- Production MCU: **nRF54L15** (plan: [`../docs/production-path.md`](../docs/production-path.md))

## Antenna & RF — first bench observation (2026-11-23)

DESFire needs noticeably more power during AES computation than during
select. On the bench (M5Stack Unit NFC, ST25R3916, DESFire EV1 card) a card
held at a deliberately bad angle answers *select* but browns out during
authentication (no response, card resets). Flat placement works reliably
(~53 ms for select + auth + 2 encrypted reads); the firmware retries
communication failures.

Consequences for the production antenna (small coil in the knob): field
strength, coil size, matching/tuning in the final housing, ferrite behind the
coil against metal, and a range test with cards **and** key fobs (smaller
antennas) are first-class design parameters.

Large binary files (STEP, STL, renders, photos) are stored with Git LFS —
see `../.gitattributes`.
