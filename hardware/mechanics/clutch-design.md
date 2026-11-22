# Clutch / actuator design — concept + idea pool

The clutch is the hard part of OpenCylinder: the crypto is easy, this is where
the real engineering (and the burglar-resistance) lives. This doc is (1) a
curated patent/reference pool to mine for ideas — open the numbers on Google
Patents to see the exploded drawings — and (2) the recommended concept.

All descriptions below are from patents (real prior art), not marketing. Study
the figures; most have exploded and cut-away views.

> **Note:** the quoted summaries are paraphrases collected during early
> research, not verbatim patent text. Check each number on Google Patents
> before relying on it.

## Idea pool — by actuation principle

### A. Motor + worm gear + axially-sliding dog clutch (the mainstream)
The default commercial approach and the one I recommend as the base.
- **US11655653 / US12352075 — "Electronically operated lock cylinder"** (euro
  direct replacement). Coaxial shafts; a motor + worm gear shifts a **slider**
  axially; a **clutch spline engages cam recesses** to couple knob→cam.
  Has exploded + cut-away figures. *The reference to start from.*
  _"clutch axially translatable along a control rod; clutch spline engages cam recesses; motor + worm gear"_
- **US7231791B2 — "Electric cylinder for actuating a door lock"**. Full exploded
  view (FIG. 1) of an electric cylinder for an existing door lock.

### B. Solenoid + plunger/blocking shuttle (simpler, watch holding current)
- **US5507162 — "Eurocylinder-type assembly for electronic lock"**. _"a cavity accommodating a solenoid; a solenoid plunger slidable within a bore in the plug, along the solenoid axis."_
- **US10533345 — "Electronic locking device"** (euro). _"a plug with annular channels; a solenoid with a shuttle; a cam rotatable with the plug; blocking elements."_
- Trade-off: a plain solenoid needs holding current (bad for battery) unless you
  use a **bistable/latching** solenoid. Motor+worm (A) holds position with no
  current — usually the better battery choice.

### C. Low-consumption / energy-storing clutch (battery optimisation)
- **US10145147 + CA2958710 — "Low-consumption clutch actuating mechanism"**.
  _"stores energy supplied by the motor and returns that energy to the clutch, to reduce electrical consumption and prolong battery life."_
  Mine this for the power budget once the basic clutch works.

### D. Freewheel / anti-force (the burglar-resistance requirement)
- **US6058751 — "Free-wheeling lock"**. _"a clutch couples driver to cylinder normally, but on an over-torque condition it decouples, letting the cylinder rotate freely while the driver stays locked."_ This is how you defeat "just crank the knob hard."
- **US7966854 — "Clutch mechanism for electromechanical cylinders"**. _"when the clutch pins are withdrawn the mechanism is disengaged and the door cannot be opened since the knob turns freely."_

### E. Key / mechanical override integrated (your fail-safe requirement)
- **US20160145900 — "Electromechanical cylinder lock with key override"**.
  _"a clutch in the cylinder body selectively engages the cam with either the actuator or a manual element; a key-operated override."_
- **US6845642 — "Clutch mechanism for electronic locks"**. Clear two-shaft
  description: _"outer escutcheon holds the reader and outer knob; inner escutcheon holds the control circuit, batteries, clutch and inner knob; two concentric shafts; the inner knob always operates the lock; on a valid key the motor makes the shafts integral for a few seconds so the outer knob opens the lock."_

### F. Gear-hub / direct-ish drive (higher power, less common for battery)
- **TR202407558U3 — euro barrel**. _"a hub rotated by a gear system connected to an electric motor, with a fixed connection point independent of rotation."_ More motor work per cycle → worse battery; note but probably not your path.

### Commercial references (for understanding, not drawings)
- **SimonsVoss Digital Cylinder AX**: _"encapsulated actuator electronics with an integrated SecureElement, protected in the cylinder core."_ Confirms: secure element in the core, encapsulated actuator, free-wheeling thumb-turn.
- **ABUS**: drill-protection in the body, and a defined "open the door when the battery is flat" procedure — both things you must design for.
- **iLOQ security analysis (Marc Tobias / Security Labs, 2012)**: a real third-party teardown/critique — read it for *how these fail*, not how they're sold.

## Recommended concept for OpenCylinder

Base = **principle A**, with D and E designed in from the start:

```
 outer knob ──► [coaxial outer shaft] ──► DOG CLUTCH ──► [central cam shaft] ──► cam ──► bolt
                                           ▲ splined, axially sliding
                                           │ moved by: small DC motor → worm gear → slider/finger
                                           │ DEFAULT = disengaged (outer knob freewheels)
 inner knob ──────────────────────────────┴──► permanently coupled to cam (free egress + override)
```

- **Coupling:** splined dog clutch slides axially on the central shaft. Worm gear
  so the clutch **holds position with zero current** (self-locking) — motor only
  pulses to engage/disengage. This is the battery win.
- **Default state:** disengaged → outer knob freewheels → no torque reaches the
  cam (principle D). Add an **over-torque decoupler** so forcing the knob can't
  jam it into engagement.
- **Inner side:** permanently coupled → always opens from inside (egress) and
  serves as the mechanical override (principle E). Decide if the outer side also
  needs a mechanical key override — for a front door, probably yes.
- **Energy:** motor moves only the clutch, user supplies turning torque; later,
  mine principle C to cut the engage energy further.

## Open design parameters (what the prototype must pin down)
- Engage **travel** (mm) and **force** of the dog clutch.
- Motor choice: tiny geared DC + worm vs. a latching solenoid (measure both).
- Spline/dog **tooth geometry**: must engage reliably even if knob and cam are
  at an arbitrary relative angle (lead-in chamfers, or a short free-turn to find
  the tooth).
- **Anti-force**: prove that N·m on a disengaged knob transmits ~0 to the cam.
- Wear / durability (3D-printed for geometry trials; metal for the real thing).

## First test rig (3D-printable)
Build the coaxial shafts + dog clutch + worm/slider oversized (2–3×), not in a
cylinder body, so you can:
1. measure engage force/travel and motor current per cycle,
2. verify freewheel + anti-force,
3. iterate tooth geometry cheaply,
before shrinking to the 17 mm body. Geometry first, size last.
