# Knob electronics — concept (draft for review)

**Status: concept, decisions taken 2026-11-27 (§5).** Goal: a small PCB with the NFC antenna that
fits into the outer knob of a Euro-profile cylinder, **together with the
mechanics** (knob shaft, clutch, bearings). Nothing here is measured yet;
all numbers are design targets to be verified with a prototype and a VNA.

## 1. The constraint that decides everything: the knob rotates

When the clutch is engaged the outer knob turns with the cam — often more
than one full turn per locking cycle. **A cable from the knob into the
cylinder body would twist** (or need slip rings, which are fragile and a weak
point). So the question is not "how big is the PCB" but **which parts rotate
together**.

### Option A — everything in the outer knob (rotates as one unit)

```
 outer knob (rotates when coupled)                cylinder body        inner knob
 ┌───────────────────────────────┐            ┌──────────────┐     ┌──────────┐
 │ cap │ antenna PCB │ main PCB  │ battery │ motor+clutch ─┼──shaft──► cam ◄─┼── always coupled
 └───────────────────────────────┘            └──────────────┘     └──────────┘
```

- Antenna, reader, MCU (nRF54L15), battery and the clutch motor all sit in
  the outer knob; the clutch couples **knob → shaft**. No rotating wiring.
- This is the arrangement most commercial electronic knob cylinders use.
- Security: the knob is on the attack side. Keys live in the nRF54L15
  hardware key storage (not readable even with the knob opened); the clutch
  must be built so that **opening the knob does not give access to engage
  it** (clutch and its actuator inside a hardened sleeve, not reachable from
  the cap; knob fixed against pulling).

### Option B — antenna in the knob, everything else inside (inductive relay)

A passive coil in the outer knob, coupled through the cylinder to a reader
coil inside. No rotating wire, electronics on the protected side — but the
relay costs range and is hard to tune; the cylinder core is mostly metal.
Not recommended for a first prototype.

### Option C — antenna in a fixed (non-rotating) ring at the knob base

Coil in a stationary bezel/escutcheon around the knob, wired to the
electronics in the cylinder or on the inside. No rotation problem, but the
coil sits behind a metal knob/escutcheon (shielding) and must leave room for
the knob; the card is held against the bezel, not the knob face.

**Decision: Option A** (2026-11-27) — recommended for the first knob prototype — it is the only
option without rotating wiring or an RF relay, and it matches the mechanics
concept (motor + worm + dog clutch, outer knob freewheels by default).
This changes one earlier assumption: the electronics move from "inside" into
the outer knob, so `docs/lifecycle-and-security.md` §2.6 (reset pads,
"electronics on the inside") needs an update once this is decided.

## 2. Dimension budget (targets for Option A)

Typical electronic knob cylinders have knobs of **Ø 30–36 mm** and
**35–45 mm** length (larger than a mechanical thumb-turn).

| Part | Size (target) | Notes |
|---|---|---|
| knob outer Ø | 38 mm | inner Ø ~34 mm with 2 mm wall |
| front cap | 2–3 mm, **plastic / glass** | the face must not be metal (shields the field) |
| antenna PCB | **Ø 32 mm disc, 0.8 mm** | Ø 24 mm coil on the front, pads at the rim, ferrite sheet behind it |
| ferrite sheet | Ø 32 mm, 0.1–0.3 mm | decouples the coil from metal behind it (battery, motor, knob body) |
| main PCB | Ø 32 mm, 1.0 mm, components on both sides | ST25R3916, nRF54L15, motor driver, power |
| battery | CR2 (Ø 15.6 × 27 mm) or CR123A (Ø 17 × 34.5 mm) | centred, along the axis |
| clutch + motor | Ø ≤ 16 mm sleeve at the rear | motor + worm + dog clutch, see `mechanics/clutch-design.md` |

Stack front to back: cap → antenna PCB → ferrite → main PCB → battery →
clutch/motor sleeve → shaft into the cylinder. Antenna and main PCB can be
**one** 4-layer board (coil on top, components on the bottom, ferrite
between is then not possible) — two boards are easier to tune; the first
prototype uses two.

## 3. Antenna (13.56 MHz, ST25R3916)

- Circular spiral coil on the front of a Ø 32 mm PCB (larger coils, Ø 26–28 mm, now possible — H2 compares).
- Target inductance **≈ 1 µH** (ST25R3916 works well with roughly 0.5–2 µH).
  Estimate (modified Wheeler, circular): **Ø 24 mm outer, 5 turns, 0.3 mm
  track, 0.3 mm gap → ≈ 1.0 µH** in air (`antenna/gen_coil.py`, footprint
  `antenna/Coil_NFC_D24mm_5T.kicad_mod`); the pads sit 1 mm outside the coil
  at r ≈ 12.9 mm, inside the board. The ferrite sheet will raise L —
  re-measure and adjust turns if needed.
- Differential drive (RFO1/RFO2), EMC low-pass filter + matching network
  (series/parallel capacitors) on the main PCB next to the reader. Resonance
  needs ≈ 139 pF total at 0.99 µH (1 / ((2π·13.56 MHz)² · L)); real values come
  from tuning **in the final housing** with a VNA and ST's antenna matching
  tool.
- No copper pours or components inside the coil area on the antenna board.
- Bench lesson: DESFire browns out at bad angles during AES — the knob
  antenna is small, so field strength and matching margin matter; test with
  cards **and** key fobs.

## 4. Electrical split between the two boards (Option A)

| Antenna board (front) | Main board (behind the ferrite) |
|---|---|
| coil, two pads to the main board | ST25R3916 + 27.12 MHz crystal, EMC filter, matching |
| nothing else | nRF54L15 (+ 32 MHz / 32.768 kHz crystals) |
| | motor driver (H-bridge), status LED (light guide to the cap) |
| | power: battery input, reverse protection, buck/LDO |
| | reset pads (only reachable with the knob dismounted) |
| | test pads: SWD, UART |

## 5. Decisions (2026-11-27)

1. **Option A** — everything (antenna, reader, nRF54L15, battery, clutch
   motor) in the outer knob, rotating as one unit.
2. **Knob Ø 38 × 42 mm**, boards Ø 32 mm (Ø 34 → 38 after comparing with the
   U&Z CX6122, Ø 40 × 42.7 mm; 40 mm length was too short once the CR2 contacts,
   ~1.8 mm, are counted; mock-up in `mechanics/knob-mockup/`).
3. **Battery 1 × CR2** (Ø 15.6 × 27 mm). Battery access: the outer shell is
   locked from inside and released by the motor only for a card with the
   battery-change right; the knob snaps onto the cylinder and is released
   only with a disassembly right (`design-plan.md` §1, §3.4, §4.2).
4. First prototype with **two boards** (antenna board + main board).

Security consequences of option A:

- The outer knob is on the attack side: keys only in the nRF54L15 hardware
  key storage; nothing secret readable from the boards.
- The clutch and its actuator sit in a hardened sleeve, not reachable through
  the cap — opening the knob must not allow engaging the clutch.
- Reset pads on the **back** of the main board (shaft side); the knob cannot
  be detached from outside while the cylinder is mounted
  (`docs/lifecycle-and-security.md` §2.6).

## 6. Next steps

1. Generate and check the coil footprint (`antenna/gen_coil.py`), order a
   few antenna boards, measure inductance and Q, tune on the bench with the
   ST25R3916 (M5 unit or ST evaluation board).
2. Schematic + layout of the main board (KiCad) — after the nRF54L15 DK
   milestone M1/M2 in `docs/production-path.md` has proven the firmware port.
3. 3D-printed knob mock-up with both boards, battery and the clutch test rig
   to check the stack-up.
