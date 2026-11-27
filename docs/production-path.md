# Production path — nRF54L15

**Status: plan for review (2026-11-27).** Decision: the production lock is
based on the **Nordic nRF54L15**. The ESP32-C3 stays the development bench.

## 1. Why nRF54L15

| | |
|---|---|
| Core | Arm Cortex-M33 with TrustZone |
| Radio | BLE + 802.15.4 (Thread / Zigbee) on chip — **unused in the offline variant** |
| Security | hardware crypto (AES, ECC P-256, SHA-2) and **hardware key storage** (keys usable without being readable), secure boot with an immutable bootloader |
| Power | very low sleep current, suited to years on a battery |
| Memory | 1.5 MB non-volatile (RRAM), 256 KB RAM |
| Ecosystem | Zephyr RTOS / nRF Connect SDK, PSA Crypto API |

One board design, two firmware variants (see [`online-architecture.md`](online-architecture.md)):
**offline** (no radio code compiled in) and later **online** (Thread or BLE,
signed bundles over the air; remote unlock separate and off by default).

## 2. What changes and what stays

The portable core is unchanged: `desfire_auth`, `access_decision`,
`management` (bundles, commissioning), `eventlog`, card format and specs.
The platform layer is rewritten:

| Bench (ESP32-C3, Arduino) | Production (nRF54L15, Zephyr) |
|---|---|
| M5Unit-NFC library (ST25R3916 over I2C) | **ST RFAL** (ST's NFC library for the ST25R3916) on Zephyr SPI/I2C — the largest porting task |
| mbedTLS with keys in RAM / NVS | **PSA Crypto** with keys in hardware key storage: AES (DESFire auth, CMAC), ECDH and ECDSA by key handle — secrets never in readable memory |
| device key pair in NVS | generated **inside** the key storage, private key not exportable, permanent |
| `Preferences` (NVS) | Zephyr settings / NVS on RRAM |
| `esp_timer` clock | low-power RTC with a 32.768 kHz crystal (later: external RV-3028 with backup, see [`lifecycle-and-security.md`](lifecycle-and-security.md) §2.5) |
| GPIO actuator | motor driver (H-bridge) for the clutch, fail-safe (disengaged without power) |
| plain RGB LED | low-current LED(s), PWM |
| — | **low-power card detection** of the ST25R3916 wakes the MCU only when a card approaches |

To check before committing to it: **RFAL licence** compatibility with this
MIT project (RFAL is distributed by ST under its own licence terms).

## 3. Milestones

| # | Milestone | Done when |
|---|---|---|
| M1 | Zephyr skeleton on the nRF54L15 DK, ST25R3916 via RFAL | card detected, UID matches the Proxmark |
| M2 | port the portable libraries; DESFire auth + encrypted read | the bench test cards (Sara, Max, …) give the same decisions as on the ESP32 |
| M3 | PSA Crypto + hardware key storage | site keys and device key pair live only in key storage; commissioning works |
| M4 | low power: LPCD wake-up, MCU sleep | measured sleep current and energy per tap |
| M5 | custom PCB rev A (reader, MCU, power, actuator driver, reset pads) | runs the M2–M4 firmware |
| M6 | knob antenna + clutch prototype | reliable reads through the knob; clutch engages within the power budget |
| M7 | (optional) online variant — Thread | signed bundles over Thread; offline behaviour unchanged |

## 4. Power budget (estimate — to be measured in M4)

| State | Rough figure |
|---|---|
| sleep (MCU + reader in card-detection mode) | a few µA |
| one tap (field on, select, AES auth, 2 encrypted reads ≈ 60–80 ms) | some tens of mA during the tap |
| clutch pulse (motor ~100–200 ms) | the largest single consumer |

With a few dozen taps a day this points to **multi-year** battery life; the
measurement in M4 (current profiler) replaces these guesses.

## 5. Antenna & mechanics

- Small coil in the knob, ferrite behind it, matching in the final housing.
  Bench data point: DESFire browns out at bad angles during AES
  (`hardware/README.md`) — the knob antenna must give margin, test with cards
  and key fobs.
- Clutch per [`hardware/mechanics/clutch-design.md`](../hardware/mechanics/clutch-design.md):
  motor + worm + dog clutch, disengaged by default.
- Hard-reset pads reachable only with the cylinder removed; anti-pull
  protection (`lifecycle-and-security.md` §2.6).

## 6. Shopping list for M1–M4

- **nRF54L15 DK** (Nordic development kit)
- reader: keep the **M5Stack Unit NFC** (ST25R3916) for M1, or an ST
  evaluation board with the ST25R3916 (e.g. X-NUCLEO-NFC06A1) for SPI and a
  better antenna
- **current profiler** (e.g. Nordic Power Profiler Kit II) for M4
- the existing Proxmark3 and DESFire EV1/EV3 cards
