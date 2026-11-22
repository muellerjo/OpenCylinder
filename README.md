# OpenCylinder

Open source smart lock — hardware, firmware and software — for an electronic
Euro-profile cylinder that **you** own end to end: your cards, your keys, your
commissioning. Fully offline, no radio, no cloud, no vendor.

> **Status: early development.** Nothing here is secure for a real door yet.
> See [Security status](#security-status).

## Why

Commercial electronic cylinders open (at best) the *read* side — how a lock
reads a card — but never the *provisioning* side: injecting keys into the
lock's secure storage. That step stays locked to the vendor's tool, cards and
credentials. OpenCylinder owns that step: your own admin card, your own
management/encoder tool, your own site key
([`docs/commissioning.md`](docs/commissioning.md)).

## How it works

```
 DESFire card ──► ST25R3916 NFC frontend ──► MCU
                                             │ desfire_auth: AES mutual auth
                                             │   (a cloned UID opens nothing)
                                             │ read access record (data-on-card)
                                             │ valid? this door? not blacklisted?
                                             ▼
                                   motor + worm → dog clutch → outer knob drives cam
```

- **Cards:** MIFARE DESFire with an OpenCylinder application and AES key
  ([`spec/card-format.md`](spec/card-format.md)).
- **Offline by design:** blacklist updates, time sync and commissioning travel
  on the admin card — no radio means no remote attack surface
  ([`docs/lifecycle-and-security.md`](docs/lifecycle-and-security.md)).
- **Mechanics:** outer knob freewheels by default; the clutch couples it to the
  cam only after a valid card. Inner knob is always coupled (free egress)
  ([`hardware/mechanics/clutch-design.md`](hardware/mechanics/clutch-design.md)).

## Repository layout

| Path        | Content | Version |
|-------------|---------|---------|
| `firmware/` | lock firmware (PlatformIO; ESP32-C3 for development) | [`firmware/VERSION`](firmware/VERSION) |
| `tools/`    | desktop encoder / management tools (Python, Elatec TWN4) | [`tools/VERSION`](tools/VERSION) |
| `hardware/` | electronics and mechanics | [`hardware/VERSION`](hardware/VERSION) |
| `spec/`     | card format — the contract between firmware and tools | `format_version` in the spec |
| `docs/`     | commissioning, lifecycle & security, versioning | — |

Components are versioned independently — see
[`docs/versioning.md`](docs/versioning.md) and [`CHANGELOG.md`](CHANGELOG.md).

## Hardware path

| Stage | MCU | NFC |
|-------|-----|-----|
| Development | ESP32-C3 (SuperMini / Seeed XIAO) | ST25R3916 (M5Stack Unit NFC) |
| Battery device | nRF52 (radio off) or STM32L5/U5 — decided at port time | ST25R3916 |

Firmware is layered (e.g. `IDesfireTransport`, portable mbedTLS) so the port
swaps transport and crypto backends, not the logic.

## Roadmap

- **Phase 1 — bring-up:** detect card, ISO-DEP, DESFire AES auth against a real
  card, cross-checked with a Proxmark3.
- **Phase 2 — decision logic:** access record, door mask, validity, blacklist;
  actuator + fail-safe.
- **Phase 3 — tools:** card personalisation and lock commissioning.
- **Phase 4 — hardening:** hardware key storage, battery + low power, clutch
  prototype, enclosure.

## Security status

Not production-secure until at least:

1. **Keys are not in plain flash** — hardware key storage on the production MCU
   (or ESP32 flash encryption + secure boot during development).
2. **The AES auth is validated against a reference** — Proxmark3 `hf mfdes` on
   a real card.
3. **A mechanical override exists** — a dead battery or hung MCU must never
   lock anyone out.
4. **The mechanics resist force** — the electronics are only as strong as the
   cylinder body and clutch they sit in.

## License

[MIT](LICENSE)
