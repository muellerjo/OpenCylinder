# Online components & firmware variants

**Status: architecture, not implemented.** The cylinder stays offline by
default; online parts are additions that never weaken an offline door.

## 1. What "online" can mean

| | What | Gain | Risk |
|---|---|---|---|
| **Update points** (online readers at main/staff entrances; Ethernet/PoE or WiFi, mains-powered, inside the building) | write fresh `valid_until`, blacklist bundles (and later collect logs) **onto user cards** | revocation and updates reach every offline cylinder via the users' own cards — the "virtual network" | low: cylinders stay radio-free |
| **Online doors** (wired doors, e.g. main entrance with an electric strike) | same decision logic; bundles arrive instantly over the network | instant revocation where it matters most | moderate: secure channel; must keep working offline |
| **Radio in the cylinder** (BLE, Thread, 868 MHz, …) | bundles over the air; later perhaps phone-as-key | convenience | highest: remote attack surface, battery, complexity |

**Order:** update points → online doors → radio in the cylinder (if ever).

## 2. Principles

1. **One trust model, many carriers.** All management data travels as a
   **signed management bundle** ([`spec/admin-card.md`](../spec/admin-card.md)):
   signed by the site, sequence-numbered, verified by the lock. Whether it
   arrives on an admin card, a user card from an update point, Ethernet, BLE or
   868 MHz does not matter — the transport is never trusted.
2. **Offline always works.** A network outage never locks anyone out and never
   opens anything; online doors fall back to their last valid state.
3. **Remote unlock is a separate feature**: own compile switch, off by default
   even in online builds, enabled per door, always logged. It is the most
   dangerous function of any online system.
4. **The decision stays in the door.** Servers distribute bundles; they do not
   decide or open.

## 3. Firmware variants: board × variant

```
                 core — identical on every board
   desfire_auth · access_decision · card format · bundle verification
                               │
     ┌─────────────────────────┼──────────────────────────┐
  platform ESP32-C3        platform nRF52           platform STM32L5 …
  (NFC transport, clock,   (CryptoCell/KMU,         (TrustZone, no radio)
   NVS, GPIO, RGB)          BLE/Thread on chip)
     │
  variant: offline | online-wifi | online-ble | online-ethernet | online-868 …
```

- **Offline builds contain no radio code at all** — not "radio disabled", but
  not compiled in. Verifiable from source; smaller attack surface. The radio
  hardware of an ESP32/nRF52 is still physically present; for the highest
  assurance an offline door can use an MCU without radio (e.g. STM32L5).
- **Online variants add one carrier** (`IManagementChannel`) that delivers
  bundles into the same verification path as an admin card.
- **Remote unlock** (`OC_FEATURE_REMOTE_UNLOCK`) is never part of a variant's
  default.
- **The variant is always visible:** boot banner, version string with SemVer
  build metadata (`0.2.0+xiao-c3.offline`), and the file name of every release
  artifact (`opencylinder-fw-0.2.0-xiao-c3-offline.bin`).

PlatformIO environments follow the same naming: `<board>-<variant>`
(today: `xiao-c3`, `c3-supermini` = offline).

## 4. Hardware

- Production PCB: reserve a connector / module footprint for an optional
  radio module; cylinder v1 ships without.
- Update points and online doors are separate, mains-powered devices; they can
  reuse the same core and card format on a board with Ethernet (e.g. an
  ESP32 + PoE module).
