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

## OpenCylinder vs. OSS Standard Offline

[OSS Standard Offline (OSS-SO)](https://www.oss-association.com/oss-standards/standard-offline-by-oss/)
is the established industry standard for offline, data-on-card access
control: it defines the card data layout so that locks of different brands
read and interpret the same card. It solves a different problem than
OpenCylinder — **interoperability between vendors** rather than **owning
the whole system** — so neither is better across the board.

| | OSS-SO | OpenCylinder |
|---|---|---|
| Specification | members-only (membership 650–5,000 €/year) or on request | public, MIT, in this repo ([`spec/`](spec/card-format.md)) |
| Key management | separate OSS key-management standard: operator-generated keys (per BSI-TL 03424), loaded via a key transport card; spec members-only | public; every step — key generation, card personalisation, lock commissioning — runs with open tools ([`docs/commissioning.md`](docs/commissioning.md)) |
| Lock commissioning / card tooling | vendor software | open tools in this repo; no membership, licence or vendor software |
| Multiple independent sites on one card | card data can be split into "sites" (details not public) | one DESFire application **per site** with its **own keys** — home, hospital, EMS station, workshop on one card, cryptographically separated; any admin can set up a site ([`spec/card-format.md`](spec/card-format.md#multiple-sites-on-one-card)) |
| Firmware | closed, vendor-specific | open source, auditable, reproducible builds |
| Recovery if the vendor disappears | depends on the vendor | nothing to depend on — escrowed keys + open tools |
| Multi-vendor interoperability | **yes — the main purpose** | no — OpenCylinder cards work with OpenCylinder locks only |
| Certified products | **yes** — certification programme (2026), commercial cylinders with EN-rated mechanics | no — DIY, uncertified |
| Maturity | deployed industry standard | early development |

**Where OpenCylinder is the better choice:** you want to own every layer —
read *and* provisioning side — audit the code, and never depend on a vendor
tool, licence or NDA. OSS-SO opens how a lock *reads* a card and is working
towards operator-held keys, but its specifications and tooling stay with
members and vendors. With OpenCylinder, every operator — a household, a
hospital, a volunteer EMS station — can run their **own** site with their
**own** keys, side by side on the same card, without asking anyone.

**Where OSS-SO is the better choice:** you need certified hardware, mixed
brands on one site, or a system an installer can support today.

*OSS-SO facts as published by the OSS Association on its
[OSS-SO](https://www.oss-association.com/oss-standards/standard-offline-by-oss/) and
[key management](https://www.oss-association.com/oss-standards/standard-key-management-by-oss/)
pages (checked 2026-11); the specifications themselves are not public, so
details beyond the public pages are not compared here.*

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
| `examples/` | worked examples, e.g. a [fictional hospital](examples/hospital/) to play with the card format | — |

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

- **Phase 1 — bring-up: ✅ done.** Card detection, native DESFire over ISO-DEP,
  AES authentication against a real DESFire EV1 — all cross-checked with a
  Proxmark3.
- **Phase 2 — decision logic:** access record, door mask, validity, blacklist;
  actuator + fail-safe.
- **Phase 3 — tools:** card personalisation and lock commissioning.
- **Phase 4 — hardening:** hardware key storage, battery + low power, clutch
  prototype, enclosure.

## Security status

Not production-secure until at least:

1. **Keys are not in plain flash** — hardware key storage on the production MCU
   (or ESP32 flash encryption + secure boot during development).
2. ~~**The AES auth is validated against a reference**~~ — ✅ done: verified on
   a real DESFire EV1 against Proxmark3 `hf mfdes auth`, including rejection of
   a wrong key.
3. **A mechanical override exists** — a dead battery or hung MCU must never
   lock anyone out.
4. **The mechanics resist force** — the electronics are only as strong as the
   cylinder body and clutch they sit in.

## License

[MIT](LICENSE)
