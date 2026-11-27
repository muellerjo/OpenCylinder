# Prior art: Uhlmann & Zacher Clex electronic knob module

Commercial reference for option A (everything in the outer knob). Sources are
public; the photo is third-party (ITler.NET) and kept **locally only**
(`images-local/`, git-ignored) — do not commit or redistribute it.

Sources:
- ITler.NET, "Uhlmann & Zacher Schließzylinder – Batteriewechsel funktioniert
  nicht" (blog article, Clex prime CX6122 knob module; photo
  `images-local/uz-clex-knob-module-itler.png`)
- U&Z product material: electronics **and batteries in the knob module**; the
  knob module is **plugged onto** a mechanical U&Z Euro-profile double
  cylinder housing, which takes electronic and mechanical knobs alike;
  housings with core-pull protection ("Kernziehschutz", e.g. CX6710)
  — [Clex prime flyer 2022-10](https://cdn.shopify.com/s/files/1/0421/7071/2214/files/Clex-prime_Flyer_2022-10-DE_web.pdf),
  [CX2120 manual](https://manualmachine.com/uhlmannzacher/clexprivatecx2120/22144957-operating-and-assembly-manual),
  [CX6162/CX6166 manual](https://manualmachine.com/uhlmannzacher/cx6166/22144962-operating-and-assembly-manual),
  [CX6710 housing](https://shop-en.allnet.de/U-Z-Cylinder-housing-CX6710-Core-pull-protection-60-40-Outside-60-Inside-40/192895).

- Video "Einbau elektronischer Kompaktknaufzylinder CX6162 / CX2162 / CX8162"
  (installation): https://www.youtube.com/watch?v=aF-4-7K9Sv8 — frames
  supplied by the user, see "Installation video" below (frame stored locally:
  `images-local/uz-cx6162-video-mech-knob.png`).

## What the article says (battery change)

1. Present a **battery-change card** → the motor runs audibly.
2. A **central bolt in the middle of the knob** moves inwards into the housing.
3. Only in its end position does it release **two small bolts** that fix the
   housing (battery compartment); they can then be pressed in and the knob
   opened.
4. Known fault: dirt keeps the central bolt from reaching its end position →
   the two bolts stay locked → fix: dismount, work the bolt against its
   spring a few times, clean, oil.

## What the photo shows (my reading — not verified)

Knob module, detached, standing on its front; the shaft side points up.

| Feature | Observation | Interpretation |
|---|---|---|
| shell | turned stainless steel, ~Ø 30–35 mm, plain cylinder | metal shell, as planned for production (design-plan §4.1) |
| black ring at the bottom | rubber ring at the front edge | seal / bumper at the cap |
| two thin radial pins at the rear rim (left + right, wires hooked on) | small pins sticking out of the shell | probably the **two housing/battery bolts** from the article |
| radial hole in the side | plain hole, lower middle | access/vent or a fixing — unknown |
| stub on the rear | stepped tube coming out of the knob's rear face, a slot along it | the plug-on interface to the cylinder housing |
| sleeve on the stub (double red arrow) | marked as moving axially | the **central bolt** of the article — an axially moving actuator element that reaches into the housing |
| small ball / pin in the stub wall (single red arrow) | radial element | most likely a **ball lock**: balls held outwards by the inner bolt/sleeve, free to retract when it moves (like a quick-release pin) |
| brass spring + brass tip at the end | coil spring at the stub end | return spring of the axial element |

## Installation video — frame "Mechanischen Knauf aufsetzen" (my reading)

Door edge with mortise lock, lever handles on both sides, cylinder mounted.

| Feature | Observation | Interpretation |
|---|---|---|
| electronic knob (left side) | metal can with **longitudinal slots**, **black (plastic) front section ~10 mm long** that also covers the sides | the reading face is plastic; the long black front may hold the antenna (planar behind the face, or a coil wound around the front ring — reads from face and side). **Slots in the metal shell** may be there to break eddy-current loops around the antenna (otherwise shielding) — or just grip |
| size | scaled against the lever (Ø ~19 mm): knob ≈ **Ø 33 mm × ~49 mm** (rough, perspective) | our Ø 34 × 42 mm is in the same range |
| other side: escutcheon rose with a **brass shaft stub**, stepped (thicker base, thin tip) | the cylinder's shaft end sticks out of the rose | mechanical knob is a **plug-on part** too; the housing is the same for both sides |
| mechanical knob in the hand | short round knob with a flat, central bore with a fitting feature (pin / flat) | pushed onto the stub, retained by a grub screw or snap (not visible) |

**Correction after the second frame (below):** the "electronic knob" in this
frame is most likely the **inner electronics carrier without its cover** — the
slots are windows of the carrier, the dark front is its front board. The
"slots break eddy currents" idea is therefore unsupported.

## Installation video — second frame, electronic side (my reading)

Stored locally: `images-local/uz-cx6162-video-electronic-chassis.png`.

| Feature | Observation | Interpretation |
|---|---|---|
| front | **dark green PCB disc**, a few small parts / screw heads, flush with the carrier | front board (antenna and/or electronics) directly behind where the cover's face will be |
| carrier | metal cylinder with **large side windows**, ≈ Ø 25–28 mm × ~40 mm (rough, vs. the lever) | inner chassis holding board(s) and battery; a shiny cylinder inside along the axis — probably the **battery** |
| near the rose | stepped collar / ring | the interface knob ↔ cylinder housing (bearing / mounting ring) |
| missing | the outer cover | slid over the carrier afterwards; it is what the two "battery bolts" from the article lock |

Consequence: **two-part knob** — (1) an electronics carrier mounted on the
cylinder's shaft, (2) an outer cover with the plastic face slid over it and
locked by motor-released bolts. Carrier Ø ≈ 26–28 mm inside a cover of
Ø ≈ 33 mm matches our Ø 28 mm boards in a Ø 34 mm knob.

Consequence: the U&Z housing ends in plain shaft stubs on both sides; knob
modules (electronic or mechanical) are pushed on. Whether the outside stub is
coupled to the cam permanently (clutch in the knob) is still open — the
outside stub would answer it.

## System overview (product diagram, my reading)

Stored locally: `images-local/uz-system-overview.png`.

- **Knob modules**: electronic (outdoor / indoor variants) and several
  mechanical knobs. **Bodies**: Euro double cylinder, round profile,
  Scandinavian oval, half cylinder (Euro + round), anti-panic cylinder, a round
  rim/mortise insert. Every knob plugs into every body (dashed lines).
- **Electronic knob modules have a long, thin, stepped stub with a spring at
  the tip** (the stub from the photo). It is long enough to reach from the
  body face to the cam. Mechanical knobs have short stubs.
- So the **bodies are passive**: bore + cam (+ a socket in the cam). The
  coupling decision lives in the knob module's stub.

Inference (not verified): since the same body takes a mechanical knob, the
**clutch is part of the electronic knob module — located at the tip of its
long stub, i.e. physically inside the body next to the cam**. The axially
moving element in the stub (photo, article) would be the clutch actuator.
That is D1's location (protected, at the cam) packaged as part of the knob.

## Datasheet CX6122 (Clex prime, catalogue pages 40–47, `SO_UZ_CX6122_PRUE2021_008507.pdf`, supplied by the user)

Facts as stated by the manufacturer:

| Item | CX6122 |
|---|---|
| electronic knob module | **Ø 40.0 × 42.7 mm** (indoor, IP65); **Ø 45.0 × 44.75 mm** (outdoor, IP66) |
| mechanical knob | Ø 29 or Ø 34 mm × 20 mm; "firmly coupled" (standard) or "freely rotating"; blind core; anti-panic versions (EN 179 / EN 1125) |
| cylinder lengths | 26/26 or 30/30 … 200/200 mm in 5 mm steps; on renovation **only the centre piece is exchanged** — the same knob module fits all lengths |
| battery | **2 × CR2**; up to 80,000 actuations or 4.6 years (MIFARE, 868 MHz radio); low battery signalled **acoustically**; battery change in the mounted state |
| external power | "low-power opening at any time with an external power source" |
| battery change | opening the shell **only with a battery-change authorisation** |
| mounting | knob module **snaps into the cylinder**; **removal only with a disassembly authorisation** |
| materials | cylinder body, knob housing and shell **nickel-plated brass**; **hard plastic cover over the antenna area** |
| environment | indoor +5…+55 °C; outdoor −25…+65 °C; storage −40…+65 °C; IP65 / IP66 |
| clutch | engagement time programmable **1–15 s**; **permanent engagement (toggle) without extra current** → self-locking actuator |
| features | 25,000 (60,000) authorisations, 512 events, 32 holidays, automatic DST, 20 time switches for day access (automatic permanent engagement), expiry date on transponders |
| transponders | MIFARE Classic / DESFire, LEGIC, EM/HITAG; radio 868 MHz or BLE |
| standards | DIN EN 15684:2013 (certified), DIN 18252, DIN EN 1303, EN 179, EN 1125, EN 1634-1 (fire, T90 housing), EN 60529 |

Consequences for the earlier inferences:

- **"Clutch at the tip of the stub, next to the cam" is weakened.** One knob
  module fits sides from 26 to 200 mm, so its stub cannot reach the cam in
  every length — the body's length-specific centre piece must carry the
  transmission from the face to the cam. Where the coupling happens (knob or
  inside the centre piece, with an axial transmission) remains open; the
  "mechanical knob freely rotating" option suggests that coupling is decided
  per knob, i.e. on the knob side.
- **Anti-pull = motor-released snap-in.** The knob snaps in and can only be
  removed with a disassembly authorisation → the ball / bolt on the stub
  (photo) is most likely the **retention, released by the motor**. Same
  principle as the battery cover. Three motor-driven functions: couple,
  release cover, release knob — two separate authorisations (battery change,
  disassembly).

## Parts kit photo (source unknown, supplied by the user; my reading)

Stored locally: `images-local/uz-parts-kit.png`. Five loose parts:
a **castellated (crown) ring** with 4–6 notches, two **compression springs**
of different length, a small **brass nut**, and a **tube with a flat blade**
(angled tip) extending from one side.

Interpretation (unverified): the internals of the knob module's stub.
Crown ring = **dog clutch** element (axial teeth/notches); springs = engage
and return springs (cf. the spring at the stub tip in the module photo);
brass nut = the brass tip seen on the stub; tube with blade = the **driver**
whose flat blade engages a slot in the cylinder's core / cam, like a key
blade. If correct, the clutch is a simple crown ring sliding on the stub
— very close to our §3.3 concept, and small enough for the stub.

## Keyng app manual (Clex private, doc 0ED2 v1.6, 2023; supplied by the user)

**Note:** the manual states that it must not be reproduced or used to
manufacture components without U&Z's consent. We therefore keep only
high-level, factual observations here — no text, figures or procedures
copied — and our design stays independent.

Observations:
- **Admin model:** a "service key" card puts the lock into programming mode;
  management via a BLE smartphone app. In the factory state the **first card
  presented within 15 s after wake-up becomes the service key**
  (trust-on-first-use; wake-up also by turning the knob several times).
  OpenCylinder instead binds commissioning to the lock's device key (QR,
  ECIES) — no TOFU window.
- **Keys identified by UID** in the learn/delete mode (the app shows a numeric
  UID for an unknown key) — OpenCylinder authenticates with diversified AES
  keys and never trusts the UID.
- **Service functions of the knob module** (through the app in programming
  mode): service opening, **dismount position**, **battery position**,
  engagement time (seconds, max 15), reset. The knob's **gear moves into
  special positions** for battery change and dismounting; an authorised
  transponder returns it to the standard position. → confirms our four yoke
  positions (design plan §3.6).
- **Dismounting:** in the dismount position the knob module is removed by
  **turning it while pulling lightly** → a bayonet / rotate-to-release
  retention, not a straight pull.
- **Time is lost on a battery change** — the app has to be connected once to
  set the clock. OpenCylinder: RTC with backup capacitor (plan §5.2).
- **Smartphone keys:** invitation split over two channels (e-mail + SMS /
  messenger, QR codes) plus a reply QR; validity from/to per lock.
- **Revocation carried by other users:** a "block order" can be sent to other
  users' phones, which deliver it to the lock when they use it — decision is
  always made in the lock. Same idea as signed bundles carried by any card or
  phone that visits the lock.
- **Firmware update over BLE**, recommended with the door open; an
  interrupted update leaves the unit in a bootloader state (MCU named as
  "AVR" — an 8-bit AVR in the module).

## Operating & assembly manual CX2122/24/26 (Clex private, v1.03, 2018; supplied by the user)

Same copyright notice as the app manual → facts in our own words only.
The cover confirms **U&Z is part of ASSA ABLOY**.

Construction (from the exploded views and parts lists):
- Parts: cylinder housing + fixing screw, **electronic knob (carrier)**,
  **knob shell**, **two shell-locking pins** (opposite sides of the carrier),
  2 × CR2, mechanical knob. → the **two-part knob is confirmed**.
- Reader, communication electronics, **mechanics and power supply are all in
  the knob module**.
- Knob module alone (CX2120): Ø 40 × 42.7 mm (outdoor Ø 45 × 44.8), **stub
  Ø 14 × 23.5 mm** protruding towards the door.
- Two sealing rings (O-rings) on the carrier under the shell (one at each end;
  the outdoor version has one at the door side).
- The cylinder body may protrude only 1–3 mm from the escutcheon.

Procedures (summarised):
- **Mounting:** the knob module is pushed into the cylinder housing **while
  turning** (bayonet-like). **Dismounting:** dismount card (or software) →
  dismount position → turn while pulling lightly; possible in **one angular
  position only**.
- **Battery change:** battery-change card → battery position → the shell pins
  are now unlocked but still have to be **pressed in with a small tool, both at
  once**, then the shell slides off. Afterwards the module stays in the battery
  position until the battery-change card or an authorised key is presented.
  Without a battery the clutch cannot engage (change with the door open).
- **Low battery, three phases over the last ~1,000 actuations:** (1) warning
  (5 red flashes + 5 beeps) on access; (2) warning + **5 s delay** before
  engaging; (3) **no access any more — the module moves to the battery
  position** instead, so the shell can be opened directly.
- **Clock:** written to non-volatile memory every 30 min; without power it
  stops and later continues from the last saved value → check the time after
  every battery change.
- **Wake-up:** normally automatic when a card approaches; after **24 wake-ups
  without a card** (e.g. metal nearby) auto-wake is disabled and the knob has to
  be **turned a few times** to wake it (sensitivity = number of turns,
  configurable). → the knob has a **rotation/motion wake-up sensor**.
- **Roles as separate cards:** service key (taught by trust-on-first-use),
  battery-change card, dismount card; keys may get a toggle right.
- Features: up to 1,000 keys, 128 events (**log can be switched off per lock for
  privacy**), 15 weekly schedules, 32 holidays, automatic DST, engagement time
  1–15 s (**default 5 s**). Error beep codes for memory, **clutch**, **RTC** and
  internal errors.
- Battery life: up to 74,500 actuations or 10 years (2 × CR2); −20…+65 °C
  indoor version.

## Market comparison U&Z vs. Tapkey/DOM (AI-generated summary, **unverified**)

Source: a Gemini chat answer pasted by the user (2026-11-27). Treat every
point as a lead to check against manufacturer documents, not as a fact.

| Claim | U&Z Clex | DOM Tapkey (Pro V2 etc.) | Check against |
|---|---|---|---|
| where the mechatronics sits | "motor, gear, clutch protected inside the cylinder core" — **conflicts** with the CX6122 datasheet ("Mechatronik … im Knaufmodul"); both could be true if the stub of the knob module reaches into the core (parts-kit reading) | — | housing teardown, patents |
| knob mounting / battery | no special tool; battery change and dismounting released by an authorised transponder | **special tool set** for the knob sleeve (knob tool, holding fork, Torx TX6) | DOM installation manual |
| battery life | up to 80,000 actuations (2 × CR2) | CR2, ~25,000–35,000 cycles (~3 years) | DOM datasheet |
| protection | up to IP66; compact knob cylinder optionally **VdS BZ+** | IP65, drill protection, optional core-pull protection | VdS certificate lists |
| other | T90, EN 179 / EN 1125 | T90, EN 179 / EN 1125; double-knob variant with a **mechanical key on the inside** | — |
| management | local (app / PC), no cloud required | cloud-first, user licences above 5 phones; offline opening possible | — |

What it adds for OpenCylinder:
- Two market answers to "how is the knob protected against removal": **tool**
  (DOM) vs. **authorised card + motor** (U&Z) — we chose the card (S2).
- Battery benchmark: our estimate (~11 µAh per opening, 1 × CR2) gives
  roughly 40,000–50,000 openings before sleep current — between DOM and U&Z;
  M4 measurements decide.
- **VdS BZ+** (German insurer class for cylinders: drilling, pulling) as a
  further target next to EN 15684.
- Inside mechanical key variant (DOM) — an option for the inner side later.

## Takeaways for OpenCylinder

1. **Axial actuator through the knob/housing interface.** The motor in the knob
   moves an element axially *into* the cylinder housing — the same pattern
   as D1/D2 (control rod into the body). Whether U&Z couple the knob to the
   cam inside the housing (as D1) or in the knob is **not visible**; a
   housing teardown or the patent claims would tell.
2. **Battery cover locked by the motor** (third actuator position) instead of a
   tool → adopted as a proposal for D4 in `../../design-plan.md`.
3. **Ball-lock interlock**: cheap, compact way to let one axial bolt lock or
   release several radial elements (cap latches, knob retention).
4. **Plug-on knob module** on a mechanical housing: electronics as one sealed,
   exchangeable unit; the housing (lengths 30/30, 30/35, …) stays mechanical.
5. **Dirt is the failure mode** of the interlock: seal it, strong return
   springs, generous play, end-position sensing (Hall) with retry + log.
6. **Two-part knob**: electronics carrier (boards + battery, mounted on the
   shaft) + outer cover (plastic face, motor-locked) — simplifies assembly and
   battery change; candidate for mock-up v2.
7. Antenna variants for H2: planar coil behind the face vs. a coil around a
   plastic front ring; metal cover with and without a slot (unverified idea).
8. **Clutch at the tip of the knob's stub** (system overview): body stays
   passive and modular (Euro, half cylinder, Scandinavian oval, anti-panic),
   the clutch still sits next to the cam. → refinement of D1 in the design plan.

9. **Size check:** the market reference is Ø 40 × 42.7 mm with 2 × CR2; ours is
   Ø 34 × 42 with 1 × CR2 — tighter than U&Z. Consider Ø 38–40 mm if the
   board / battery space gets tight; Ø 40 fits normal doors (U&Z sells it).
10. **Firmware features worth copying:** programmable engagement time (1–15 s),
   office mode (permanent engagement, also by time profile), holidays,
   acoustic low-battery warning (→ piezo buzzer in the BOM), separate
   battery-change and disassembly rights.
11. **Standards to aim for:** EN 15684 (mechatronic cylinders), EN 1303 / DIN
   18252 (mechanics), later EN 179 / EN 1125 (panic) and EN 1634-1 (fire).

12. **Dismount by rotate-while-pulling** (bayonet) in the release position —
    simpler than a ball lock for S2; compare both on the test rig.
13. **Revocation via user media:** let user cards (and later phones) carry
    signed blacklist bundles to the locks they visit — fast offline
    revocation without walking the admin card around (backlog, needs card
    space + spec).

14. **Low-battery phase 3 → battery position:** the shell opens without
    emergency power (but nobody gets in until the battery is changed). Combine
    with our emergency-power contacts; decide the phase-3 policy.
15. **Card + tool for the shell:** motor unlocks the pins, a simple two-pin
    tool presses them — prevents the shell from being pulled off by accident
    during the release window.
16. **Wake-up by turning the knob** + false-wake limit for LPCD (metal near the
    door) — needs a motion/rotation sensor.

## Open questions (to check)

- Where is the coupling — knob side or housing side? What happens to the
  stub if the knob is torn off?
- How is the knob module retained on the housing (the ball lock?) and how is
  it released for mounting (special tool, or card + motor)?
- Patents: search Espacenet for applicant "Uhlmann & Zacher GmbH" + Kupplung /
  Knauf / Batteriewechsel.
