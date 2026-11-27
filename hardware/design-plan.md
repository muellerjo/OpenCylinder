# Hardware design plan — housing, mechanics, components, PCB

**Status: plan, decisions of 2026-11-27 included (§1).** Builds on
[`knob-electronics.md`](knob-electronics.md) (option A, **Ø 38 × 42 mm** knob,
1 × CR2), the commercial reference in
[`mechanics/prior-art/uhlmann-zacher-clex.md`](mechanics/prior-art/uhlmann-zacher-clex.md), [`mechanics/clutch-design.md`](mechanics/clutch-design.md) (motor +
self-locking drive + dog clutch, disengaged by default) and
[`../docs/production-path.md`](../docs/production-path.md) (nRF54L15,
milestones M1–M7). All part numbers are **candidates** — check datasheets,
availability and price before a layout. Nothing here is measured yet.

---

## 1. Decisions

**Decided (2026-11-27):**

| # | Decision | Notes |
|---|---|---|
| S1 | **Knob Ø 38 × 42 mm, 1 × CR2** | market reference U&Z CX6122: Ø 40 × 42.7 mm, 2 × CR2. Ø 38 gives Ø 32 mm boards (+30 % area vs. Ø 28) and stays compact |
| S2 | **Snap-in knob, released only by the motor with a disassembly right** (§3.4) | anti-pull: the knob cannot be taken off without an authorised card; same principle as U&Z ("Demontage nur mit Demontageberechtigung") |
| D4 | **Battery cover locked from inside, released by the motor with a battery-change right** (§4.2) — no special tool | U&Z pattern ("Batteriewechsel nur mit Batteriewechselberechtigung") |
| D5 | **Emergency power is mandatory** (§4.3) | with a motor-locked cover a flat battery would otherwise lock everyone out |

**Still open (recommendation in bold):**

| # | Question | Recommendation | Why |
|---|---|---|---|
| D1 | Where does the clutch sit? | (a) in the knob module (U&Z-like, body stays passive/modular) or **(b) in the body next to the cam**, driven by a control rod (§3.2, drawing `mechanics/d1-clutch-in-body.svg`). Decide after the clutch test rig (H3). | With S2 the knob can't be *removed* without a card, but it can still be *broken off*. With (a) a torque-transmitting interface on the body side is then exposed; with (b) the stub freewheels. (b) = defence in depth, (a) = simpler. |
| D2 | Engage direction of the control rod (only for D1 b) | **Pull to engage**, spring disengages | a broken-off rod stub can't be gripped and pulled |
| D3 | Protection against hot-wiring the motor | rev A/B: none (prototype). **Production: encapsulated actuator** — motor + driver + tiny MCU potted in a steel sleeve, acts only on an authenticated command | otherwise: break the cap open, put 3 V on the motor wires → clutch, cover and knob release all follow the motor |
| D6 | nRF54L15: chip or module | **Bare chip (QFN48 6 × 6 mm)** | board space; offline needs no RF; online variant later with a chip antenna behind the plastic cap |
| D7 | First custom PCB | **rev A = flat bench board**, **rev B = Ø 32 mm knob board** | debug where you can probe, then shrink |
| D8 | Body dimensions first | **Euro profile, 30/30 mm** | most common size; other lengths = longer centre parts only |

---

## 2. Overall architecture

```
  OUTSIDE (attack side)                       DOOR                          INSIDE
 ┌─────────────── outer knob (rotates) ─────────────┐ ┌──── cylinder body (fixed, Euro profile) ────┐ ┌── thumbturn ──┐
 │ cap │ antenna │ferrite│ main PCB │ CR2 + motor │yoke│ │ bearing │ knob shaft (hollow) ─► CLUTCH ◄─ cam ─ cam shaft ─────┼─► always coupled
 │     │  board  │       │          │  leadscrew ─┼─►─┼─┼─────────┼── control rod ──────►┘  │             │ │ (free egress)  │
 └──────────────────────────────────────────────────┘ └──────────────────────────────────────────────┘ └────────────────┘
```

Drawn for **D1 (b)** (clutch in the body); with D1 (a) the clutch sits in the
rear zone of the knob and the body only carries a passive transmission.

- The **knob** holds everything electrical (option A, no rotating wires) plus
  the motor. The motor moves a **yoke** that pulls the **control rod**.
- The **knob shaft** is fixed to the knob and turns freely in the body. The
  **clutch** couples it to the **cam** — inside the body, next to the cam,
  behind the anti-drill zone.
- The **thumbturn** on the inside drives the cam directly (free egress,
  mechanical override from inside).

This follows the reference patent family US11655653 / US12352075 ("clutch
axially translatable along a control rod; motor + worm gear") in
`mechanics/clutch-design.md`.

---

## 3. Mechanics

### 3.1 Cylinder body

| Item | Plan |
|---|---|
| Profile | Euro profile (DIN 18252 / EN 1303 outline): Ø 17 mm round part, 33 mm total height, M5 fixing-screw hole in the web below the cam. **Verify exact dimensions against the standard and a real cylinder before drawing.** |
| Length | 30/30 first (A = outside face → screw centre, B = inside). Further lengths in 5 mm steps by longer shaft/rod parts only. |
| Halves | Outer half + inner half, joined by a hardened steel connecting bar in the web (cast/brass bodies: pinned). Cam rotates in the gap between the halves. |
| Material | Prototype: 3D print (geometry), then aluminium (CNC). Production: brass body, **hardened steel inserts** (anti-drill pins across the shaft bore, anti-snap: predetermined break line *outside* the screw hole so a snapped body leaves the clutch inside the door). |
| Bores | Outer half: knob shaft bearing (Ø 8 mm shaft) + clutch chamber near the cam. Inner half: thumbturn shaft. |

### 3.2 Option D1 (b): clutch in the body — why and how

With the clutch in the knob (current mock-up), the shaft between knob and cam
is permanently coupled to the cam. Attack: pull or break the knob off → the
shaft end sticks out → turn it with pliers → open. Commercial knob cylinders
avoid this by keeping the coupling in the protected core.

New split:

| Part | Rotates with | Notes |
|---|---|---|
| knob shaft (hollow, Ø 8 / Ø 3 bore) | knob | **predetermined break point just inside the body front**: a ripped-off knob leaves a flush, freewheeling stub |
| control rod (Ø 2.5 mm, steel) | knob (axially moved) | pulled by the motor yoke; breaks with the knob shaft — the stub sits below the surface |
| clutch slider (dog ring) | knob shaft (splined, slides axially) | sits on the knob shaft **beyond** the cam (inside half); spring pushes it away from the cam = disengaged; the rod head pulls it **towards** the cam = engaged (§3.3) |
| cam hub + cam | cam | rides on the knob shaft, dog teeth on its inner face; thumbturn coupled permanently via a ring around the slider |

### 3.3 Clutch (in the body)

```
 outside                                   cam                                      inside
 knob ══ knob shaft (hollow) ═════════[ cam hub ]═══ spline ═══[ slider ]═══ rod head
           ║  control rod inside ═════════════════════════════════════════════╝
           ║                           teeth ◁▷ teeth
           ║                                       ▲ engage spring   ▲ return spring
 rod pulled towards the knob → rod head pulls the slider onto the cam hub = ENGAGED
 rod released → return spring pushes the slider away from the cam      = DISENGAGED
 thumbturn ══ ring around the slider ══ cam hub   (always coupled)
```

The knob shaft runs **through** the cam hub (which turns freely on it) and
carries the slider on a spline on the inside half. This geometry is what makes
"pull to engage" possible; it costs a few mm in the inside half — check on
the test rig whether 30/30 still fits or the body starts at 30/35.

- **Engage:** motor pulls the rod (≈ 1.5–2 mm travel). The rod head
  compresses an **engage spring** that pushes the slider onto the cam hub. If the teeth
  meet tip-to-tip, the spring waits; the first few degrees of turning the
  knob snap them in. → The motor never has to find a tooth position.
- **Disengage:** motor releases the rod; the **return spring** pulls the slider
  back. If the user is still holding torque, the teeth may stay loaded —
  the firmware retries until the end position is reached (Hall sensor, §3.6).
- **Self-locking drive:** leadscrew (or worm) on the motor → the rod holds
  both positions with **zero current**.
- **Anti-force:** disengaged, the knob shaft spins freely in the body; no
  torque reaches the cam. Over-torque on an engaged knob: teeth with a
  slight back-angle so they don't ratchet out, but the knob shaft is the
  designed weak point (break point) — never the cam side.
- **Tooth geometry:** 6–8 dogs, 20–30° lead-in chamfers on both sides,
  ≥ 1 mm engagement depth. To be found on the test rig.
- **Pull-to-engage (D2):** a broken-off rod stub can't be gripped and
  pulled; pushing it only presses against the return direction.

### 3.4 Knob attachment and anti-pull — snap-in, motor-released (S2)

- **Mounting:** the knob module is pushed onto the body's front stub and
  **snaps in** — spring-loaded **locking balls** (or a latch ring) drop into
  a groove of the body stub. No tool, no card needed to *mount*.
- **Locked state:** a **locking sleeve** driven by the motor sits behind the
  balls and keeps them in the groove; pulling on the knob loads the balls
  against the hardened groove.
- **Removal:** only after an authorised card with the **disassembly right**:
  the motor moves to the *release-knob* position, the sleeve uncovers the
  balls, the knob can be pulled off. Logged as an event.
- Alternative to the ball lock (U&Z app manual): a **bayonet** — in the
  release position the knob comes off by turning while pulling. Compare both
  on the test rig (H3).
- **Design load:** the retention must outlast the pull test of EN 15684 (to
  be looked up) and a slide hammer; the predetermined break point (D1 b)
  sits *behind* the retention, inside the body.
- Between knob and body: **bearing bush** (POM or sintered bronze) on a short
  stub of the body front, plus a **lip seal / O-ring** (IP rating, §4.4).
- Knob shell in production: **metal** (stainless or brass) around a plastic
  front cap — the sidewall must be strong enough that pulling deforms the
  break point first, not the clutch.

### 3.5 Inside: thumbturn

Mechanical thumbturn on the inner half, permanently coupled to the cam
(always open from inside). Optional later: a "both sides electronic" body.

### 3.6 One motor, four positions

Drawing: [`mechanics/knob-yoke-positions.svg`](mechanics/knob-yoke-positions.svg).

The motor's leadscrew drives one **yoke** in the rear zone of the knob (the
4 mm "clutch zone" of the mock-up). Along its travel:

| Yoke position | Effect | Right needed |
|---|---|---|
| E — pulled | clutch **engaged** (via rod, D1 b; or directly, D1 a) | user access |
| R — rest | clutch open, cover locked, knob locked | — |
| C — pushed 1 | **cover latches released** (battery change) | battery-change right |
| K — pushed 2 | cover **and knob retention** released (dismount) | disassembly right |

The clutch spring keeps the clutch open in C and K. Each end position is
confirmed by the Hall sensor (magnet on the yoke, 2 thresholds or 2 sensors)
plus motor stall current. Self-locking leadscrew → every position holds
without current (also **office mode**, §5.4). Lesson from U&Z (dirt jams the
release bolt): seal the yoke zone, strong return springs, retry + log.

### 3.7 Mechanical test rig (before shrinking)

As in `clutch-design.md`: **2× scale**, 3D-printed, flat on the bench —
knob shaft, rod, slider, cam hub, springs, real motor with leadscrew. Measure:
engage/disengage time, motor current per cycle, tip-to-tip behaviour,
disengage under torque, freewheel torque, force on the rod stub after a
simulated break.

---

## 4. Knob housing

### 4.1 Shell and cap

| Part | Prototype | Production |
|---|---|---|
| shell | PETG / SLA resin (mock-up `knob_mockup.scad`) | stainless 1.4404 or brass, turned; grip flutes; ~2 mm wall |
| front cap | 2.5 mm PC, printed | PC or PMMA, UV-stabilised, **never metal** (would shield the field); light-guide ring for the LED; card target symbol |
| spacer / board carrier | printed (`part="spacer"`) | POM or glass-filled PA, one piece with the board tabs |

Metal shell around the antenna: the coil sits behind the plastic cap,
ferrite behind the coil; the metal wall still detunes it → **tune in the final
metal shell** (§6.3).

### 4.2 Battery access (D4) — two-part knob

Following the U&Z construction (prior-art notes): the knob is a **carrier**
(boards, battery, motor, yoke — mounted on the body stub) plus an **outer
shell** with the plastic face, slid over the carrier.

- The shell is held on the carrier by **2–3 latch pins**, blocked from inside
  by the yoke; position C releases them → the shell slides off forwards, the
  battery is accessible from the side/front of the carrier.
- The card with the battery-change right is presented, the LED confirms, the
  user pulls the shell; after the change the shell is pushed on and the motor
  returns to R (shell locked again) — detected via a contact/Hall on the shell.
- The board stack stays in the carrier during a battery change.
- Like the market reference (CX212x manual): the released latch pins are
  pressed in with a **simple two-pin tool** (both at once) — the card unlocks,
  the tool prevents accidental removal.
- **Low-battery phases** (last ~1,000 actuations): 1 warning; 2 warning +
  delayed engagement; 3 the lock moves to C (shell released) — policy for
  access in phase 3 to be decided (U&Z: no access until the battery is
  changed; with our emergency power we could still grant access).
- Battery: CR2 3 V Li-MnO₂, ~800 mAh (CR2 is pulse-capable, but loses
  capacity and voltage in the cold).

### 4.3 Emergency power (D5 — mandatory)

Two stainless contact studs on the cap edge (flush). An external 9 V block
or USB-C adapter powers the lock through a protection circuit (diode-OR,
TVS, current limit); the card check runs normally — also a card with the
battery-change right, so the cover can be opened with a dead battery.
Contacts carry no data.

### 4.4 Sealing and environment

- Target **IP65 indoor / IP66 outdoor** like the market reference; −25 … +65 °C
  outdoor, storage −40 … +65 °C.
- O-ring cap/shell, lip seal knob/body, conformal coating on the main board.
- Condensation: small vent membrane (ePTFE) in the cap edge — check later.

### 4.5 Assembly order (front, cylinder removed)

Factory: carrier with motor, yoke, battery contacts, main board (on tabs),
spacer, ferrite, antenna board; shell with cap slid on (yoke in C) → R.
Door: cylinder body in, fixing screw → knob module pushed onto the body stub,
snaps in (S2). Dismount: card with disassembly right → K → pull.

---

## 5. Electronics — components

### 5.1 Block diagram

```
 CR2 3 V ──┬─ reverse-protection (P-FET) ──┬─ buck-boost 3.3 V ──► ST25R3916 (VDD, VDD_RF) ◄─SPI─┐
           │                               ├─ nRF54L15 (VDD, internal DC/DC) ◄─────────────────┤
           │                               └─ DRV8837 H-bridge ──► motor (leadscrew)           │
 emergency │                                  RV-3028 RTC (backup cap) ◄─I2C─────────────────┤
 power ────┘ (diode-OR)                       Hall sensor(s) (yoke pos.)  ─GPIO─────────────┤
                                              RGB LED, piezo, battery ADC, reset/test pads ───┘
 antenna board: coil ──2 pins──► EMC filter + matching (on the main board, next to the ST25R3916)
```

### 5.2 Parts (candidates)

| Function | Candidate | Package | Notes / to check |
|---|---|---|---|
| MCU | **nRF54L15** (bare chip, D6) | QFN48 6 × 6 | + 32 MHz crystal (2016), 32.768 kHz crystal (1610), DC/DC inductor; hardware key storage (M3) |
| NFC reader | **ST25R3916** (bench-proven) or ST25R3916B | QFN32 5 × 5 | **SPI** in production (RFAL default, faster than I2C); 27.12 MHz crystal (2016); low-power card detection (LPCD) |
| EMC filter + matching | 2× L (EMC), ~8 C (C0G, 1 %) | 0402 | values from ST's matching tool, tuned in the metal knob with a VNA |
| Supply | **TPS63900** (TI buck-boost, ~75 nA Iq) | WSON / WCSP | 3.3 V from a falling CR2 (3.0 → ~2.0 V under load). Reader at a stable 3.3 V = constant field strength |
| Bulk capacitor | 2× 100 µF ceramic or a small low-ESR tantalum | 0805 / 1206 | buffers tap + motor pulses, especially in the cold |
| Reverse protection | P-MOSFET ideal diode | SOT-23 / DFN | |
| Motor driver | **DRV8837** (TI) or DRV8210 | WSON-8 2 × 2 | ~nA sleep; current sensing via shunt → ADC for stall detection |
| Motor | **Ø 6 mm micro gear motor with leadscrew output**, 3 V | Ø 6 × ~20 mm | self-locking; check stall current and force at 2.0 V |
| Yoke position | **DRV5032** (TI nano-power Hall, ~0.5 µA) ×2, magnet on the yoke | SOT-23 / X2SON | confirms E / R / C / K (§3.6); stall current as a second signal |
| Shell present | reed/Hall or contact | — | knows the shell is back on before returning to R |
| Buzzer | small SMD piezo transducer, driven by PWM | ~9 × 9 mm or smaller | acoustic feedback + **low-battery warning** (U&Z does this acoustically) |
| Motion wake-up | low-power accelerometer (~1 µA class) or vibration/tilt switch | small LGA / SMD | wake by turning the knob; fallback when LPCD is disabled after repeated false wake-ups (metal near the door) |
| RTC | **RV-3028-C7** (Micro Crystal, ~45 nA) | 3.2 × 1.5 | keeps the time across a battery change on a ~22–100 µF backup capacitor (≈ minutes) — closes the "time unknown after battery change" case of `lifecycle-and-security.md` §2.5 |
| Status LED | RGB, 1.6 × 1.6 mm, low current | SMD | light guide ring in the cap |
| Battery measurement | divider switched by a FET (no standing current) → nRF ADC | — | measure **under load** (during the field-on phase) |
| Emergency power | Schottky diode-OR + TVS + PTC | SOD-323 etc. | |
| Reset / test | pads on the **back** of the main board: SWD (pogo), UART, reset pads | — | `lifecycle-and-security.md` §2.6 |
| Antenna | Ø 24 mm coil, 5 turns (`antenna/gen_coil.py`); with the Ø 32 mm board also Ø 26–28 mm variants | antenna board | |
| Ferrite | flexible ferrite sheet (e.g. Würth WE-FSFS family), 0.1–0.3 mm | Ø 32 mm, 2 holes for the pins | |
| Production add-on (D3) | small MCU with AES (or software AES) in the actuator sleeve | tiny QFN / WLCSP | later revision |

### 5.3 Power budget (estimate — replaced by M4 measurements)

| Item | Assumption | Per day (30 openings) |
|---|---|---|
| tap (field on, select, auth, 2 reads) | ~100 mA × 80 ms ≈ 2.2 µAh | 0.07 mAh |
| motor (engage + release) | ~100 mA × 2 × 150 ms ≈ 8.3 µAh | 0.25 mAh |
| MCU active | ~5 mA × 200 ms ≈ 0.3 µAh | 0.01 mAh |
| sleep: nRF54L15 + RTC + Hall + LPCD | ~5–10 µA | 0.12–0.24 mAh |
| **total** | | **≈ 0.45–0.6 mAh/day ≈ 165–220 mAh/year** |

CR2 ~800 mAh, ~70 % usable in cold and at end-of-life → **≈ 2.5–3.5 years**.
The motor and the LPCD interval are the big levers. Low-battery warning
(LED pattern + event log + admin card readout) weeks before the cut-off.

### 5.4 Firmware consequences (from the plan and the market reference)

| Feature | Notes |
|---|---|
| **rights** `battery-change`, `disassembly` | new permissions on admin cards (or separate service-card roles, "one card, one role"); every use logged |
| engagement time | programmable 1–15 s (U&Z), per lock via admin bundle |
| **office mode** | permanent engagement by card toggle or by time profile (automatic day release); zero current thanks to the self-locking drive |
| holidays | list of dates for the time profiles (U&Z: 32) |
| low battery | three phases (warning → delayed engagement → shell released), piezo + LED, event + admin readout |
| LPCD false wake-ups | count wake-ups without a card; above a limit disable LPCD until the knob is turned (motion sensor) or a valid card was read |
| privacy | event log can be switched off per lock (admin bundle) |
| error codes | beep/LED codes for memory, clutch, RTC and internal errors |
| actuator health | end positions not reached → retry, then deny safely (clutch open), log |
| return to standard | after battery change / dismount the yoke returns to R on the next authorised card (or a timeout), like the market reference |
| revocation via user media (later) | user cards carry signed blacklist bundles to the locks they visit (prior-art notes, takeaway 13) |

---

## 6. PCB

### 6.1 rev A — flat bench board (D7)

- ~50 × 50 mm, 4 layers, all parts of §5.2, **same circuit** as the knob board.
- Every rail with a **current-measuring jumper** (for the Power Profiler, M4).
- Antenna boards plug on (2-pin, short) → compare coils on the bench.
- Motor connector, Hall sensor on a flying lead, emergency-power input.
- SWD header (10-pin Cortex), UART header, reset pads.
- Goal: M2–M4 firmware runs on it; LPCD, power, matching are understood.

### 6.2 rev B — Ø 32 mm main board (knob)

| | Front (towards the ferrite) | Back (towards the battery) |
|---|---|---|
| side | **RF side:** ST25R3916, 27.12 MHz crystal, EMC filter, matching, antenna pins | **digital/power side:** nRF54L15 + crystals, TPS63900 + inductor, DRV8837, RTC, battery contact (+), Hall (if near the yoke), test/reset pads |
| rules | component height ≤ 1.2 mm (envelope 3.4 mm); short, symmetric differential RF traces; solid ground under the reader | keep-out at the battery spring; reset pads **not** reachable from the cap side |

- 4 layers, 1.0 mm, ENIG. Usable area per side ≈ Ø 30 mm ≈ 700 mm² minus
  keep-outs (QFN48 36 mm² + QFN32 25 mm² + passives + piezo).
- **Keep-out r > 15 mm** on both sides (tabs behind, spacer ring in front —
  from the mock-up).
- Motor and battery (−) via a small flex or two wires to the yoke zone.
- Fab: JLCPCB/PCBWay class (0.1 mm track/space, 0.2 mm vias) — no HDI.

### 6.3 Antenna board

- 2 layers, 0.8 mm, Ø 32 mm, ENIG. Coil on top, crossover on the bottom
  (`antenna/Coil_NFC_D24mm_5T.kicad_mod`). Nothing else on it.
- **Order 3–4 variants at once** (4/5/6 turns, Ø 24/26/28 mm) — cheap, and the
  measurement decides. Measure L and Q with a VNA (e.g. NanoVNA) bare, with
  ferrite, and in the metal shell; tune with ST's antenna matching tool.
- Connection to the main board: 2 low-profile pins (e.g. spring-loaded
  pogo pins on the main board pressing on pads), through holes in the ferrite.

### 6.4 Tools and files

KiCad (≥ 8) under `hardware/pcb/rev-a/` and `hardware/pcb/rev-b/`; symbols and
footprints that KiCad lacks in `hardware/pcb/lib/`. Mechanics: OpenSCAD for
the mock-ups and test rig (parametric, text-diffable); a STEP export of the
Ø 32 mm board outline from KiCad back into the mock-up for fit checks.

---

## 7. Security requirements → design

| Threat | Countermeasure | Where |
|---|---|---|
| pull the knob off | snap-in retention released only by the motor with a disassembly right (S2) | §3.4 |
| break the knob off, turn what is left | D1 (b): clutch in the body, break point, pull-to-engage rod (D2); with D1 (a): no torque-transmitting feature reachable at the body face | §3.2–3.4 |
| break the shell open, power the motor directly | **encapsulated, authenticated actuator** (D3); until then: potting of motor wires | §4.2, §5.2 |
| abuse the battery-change / disassembly function | separate rights on cards, logged; cover release never couples the clutch | §3.6, §5.4 |
| read keys from the boards | nRF54L15 hardware key storage (M3); no key in external flash; SWD locked (APPROTECT) in production | production-path M3 |
| force on the knob | freewheel when disengaged; break point designed weaker than the clutch | §3.3 |
| drill / snap the cylinder | hardened inserts, anti-snap line, clutch behind them | §3.1 |
| magnets | leadscrew motor (no magnetic actuation); Hall sensor only for feedback, never for the decision | §5.2 |
| flat battery | emergency-power contacts (mandatory), acoustic + LED low-battery warning | §4.3, §5.3 |
| reset to lock the owner out | reset pads only with the cylinder removed | `lifecycle-and-security.md` §2.6 |
| relay attack on the NFC link | short timeouts in the DESFire exchange (later: proximity check, EV2/EV3) | firmware |

Reference standard for later: **EN 15684** (mechatronic cylinders: key-related
security, attack resistance) and EN 1303 for the mechanical part.

---

## 8. Sequence (fits M1–M7 of the production path)

| Step | What | Depends on | Done when |
|---|---|---|---|
| H1 | Zephyr M1/M2 on the XIAO nRF54L15 + M5 unit | boards (ordered) | same card decisions as on the ESP32 |
| H2 | antenna boards: 3–4 coil variants, NanoVNA, matching on the M5 unit / X-NUCLEO-NFC06A1 | gen_coil, ~€30 PCB order | read range with card and fob through 2.5 mm PC |
| H3 | clutch test rig 2× scale (§3.7), incl. the 4 yoke positions and the ball-lock retention | motor + leadscrew samples | engage < 300 ms, tip-to-tip handled, < 10 µAh per cycle; **decides D1** |
| H4 | rev A flat board (§6.1) | H1, H2 | M2–M4 firmware runs, sleep current measured |
| H5 | mock-up v2: Ø 38 two-part knob (carrier + shell), snap-in on a body stub, yoke with 4 positions, D1 variant from H3, real motor | H3 | assembles by hand; snap-in holds; knob turns freely |
| H6 | rev B Ø 32 mm boards in the mock-up v2 | H4, H5 | reads through the cap in the (metal) shell, clutch works on battery |
| H7 | metal knob + body prototype (CNC) | H6 | attack tests §7 (pull, force, cap open) |
| H8 | encapsulated actuator (D3) | H7 | cap-open attack fails |

## 9. Risks / open questions

- **Read range** with a Ø 24 mm coil behind a cap in a metal knob — the
  biggest technical risk (bench: DESFire browns out at bad angles). H2 first.
- Motor force at 2.0 V and −20 °C (CR2 voltage sag) — H3.
- Space on the Ø 32 mm board — do a rough placement in KiCad early (H4).
- RFAL licence vs MIT (production-path §2).
- Patents: the control-rod clutch is a known pattern (US11655653 family) —
  check the claims before publishing a design that is too close.
- One motor for four functions: one jammed yoke blocks battery change *and*
  dismounting — emergency mechanical release only with the cylinder removed?
  Decide with H5.
- EN 15684 test requirements (pull, torque, drilling) — get the standard
  before H7; **VdS BZ+** (drilling, pulling) as the stricter German insurer
  class to aim for later.
