# Firmware

PlatformIO project. Version: see `VERSION` (stamped into every build, printed
at boot — see `../docs/versioning.md`).

## Targets

| Env             | Board                     | I2C to ST25R3916 unit |
|-----------------|---------------------------|-----------------------|
| `c3-supermini`  | ESP32-C3 SuperMini        | SDA GPIO6, SCL GPIO7  |
| `xiao-c3`       | Seeed Studio XIAO ESP32C3 | SDA D4 (GPIO6), SCL D5 (GPIO7) |
| `xiao-c3-debug` | as `xiao-c3`, plus M5 NFC library error/warning logs (ISO-DEP timeouts etc.) | |
| `xiao-c3-prod` | as `xiao-c3`, **without** bench serial commands (production-style) | |

ST25R3916 unit (M5Stack Unit NFC, Grove): black → GND, red → 5V,
yellow → SDA, white → SCL.

```
pio run -e xiao-c3 -t upload -t monitor
```

**Stable serial port (Linux):** the ESP32-C3's native USB re-enumerates on
every reset and often comes back as a *new* `/dev/ttyACMx`, so the monitor
cannot reconnect. Put the board's stable name into a git-ignored
`platformio_local.ini` (picked up via `extra_configs`):

```ini
[env]
upload_port  = /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_<MAC>-if00
monitor_port = /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_<MAC>-if00
```

(`ls /dev/serial/by-id/` shows the exact name.)

The ESP32-C3 boards are for development only. The battery-powered device moves
to nRF52 or STM32L5/U5; hardware-specific code stays behind interfaces so the
port swaps the transport and crypto backends, not the logic.

## Layout

- `lib/desfire_auth/` — portable DESFire EV1 session: select, AES
  authentication, encrypted `ReadData` (EV1 secure messaging: CMAC-chained IV,
  CRC32), crypto self-test (RFC 4493 vectors). mbedTLS only.
- `lib/access_decision/` — portable card record parsing and the lock decision
  per `spec/card-format.md`; mirrors `examples/hospital/check_access.py`.
  Also `IClock` and a Y2038-safe UTC date helper.
- `src/platform/esp32/` — `M5DesfireTransport` (`IDesfireTransport` on the
  M5Unit-NFC ISO-DEP layer, native DESFire frames), `Esp32Clock`.
- `src/main.cpp` — Phase 2 bench lock.
- `include/version.h`, `scripts/version.py` — build version stamping.
- `test/host/` — host tests (plain g++, no hardware): `test_access_decision`
  (decision logic, time profiles, time zone vs. Python `zoneinfo`, rollback
  rule), `test_management` (bundles), `test_eventlog` (ring buffer) — each
  file's header has its g++ command, e.g.:
  ```
  cd test/host && g++ -std=c++11 -Wall -Wextra -I../../lib/access_decision/src \
    test_access_decision.cpp ../../lib/access_decision/src/*.cpp -o t && ./t
  ```

## Phase 2 bench lock ✅ (verified 2026-11-23)

The XIAO plays **door 4 "Ward 1 – ward door" (zones 3, 4)** of the fictional
hospital in [`examples/hospital/`](../examples/hospital/). On every tap:

1. select site application `4F4331`, AES authentication with the site read key
   (key 1, diversified per card from the public dev test master key with
   AN10922, M = UID ‖ AID);
2. encrypted read of file 0 (header) and file 1 (access list);
3. decision → `OPEN via zone 4 (53 ms)` or `DENY  <reason>`.

Communication failures (the card browns out during the AES computation when
it sits at a bad angle or is still moving into the field) are retried up to
3 times; real refusals are final at once.

**Admin card (maintenance bundle):** a card with the admin application
`4F4341` is an admin card — the lock verifies the signed bundle (site,
target, expiry, ECDSA P-256 signature, sequence), syncs its time (rollback
rule), applies blacklist / profiles / TZ, stores them in NVS, shows blue and
never opens. Signature check ≈ 350 ms on the ESP32-C3 (software ECC; the
nRF52 CryptoCell does it in hardware). Write one with
[`examples/hospital/write_admin_card.py`](../examples/hospital/write_admin_card.py).

**Identity & state** ([`spec/admin-card.md`](../spec/admin-card.md) §5):
on its first boot the lock generates its permanent ECDH P-256 device key pair
(NVS on the dev board) and prints its QR text. Because the offline build has
no WiFi/BT, `setup()` enables the SAR-ADC entropy source
(`bootloader_random_enable()`), otherwise the ESP32's RNG would only be
pseudo-random. States: **FACTORY** (opens nothing) and **OWNED**.

**The firmware contains no keys.** A freshly flashed lock is FACTORY; it gets
its site keys, door, zones, profiles, TZ and blacklist only by commissioning.

**Bench quick start** (repo root, Proxmark3 on the encoder side):

1. `cd firmware && pio run -e xiao-c3 -t upload -t monitor` — the banner shows
   `Lock state: FACTORY` and the QR text `OC1:<device ID>:<public key>`.
2. Commissioning card for door 4:
   `python3 examples/hospital/write_commissioning_card.py --qr "OC1:…" --door 4`
   (afterwards `--qr` can be omitted: the lock is in `locks.local.json`).
3. Tap it → `commissioned -> OWNED`. User cards from `write_test_card.py`
   now work as listed below.

**Commissioning card:** a FACTORY lock accepts a commissioning card
(application `4F434B`, free-read file): it decrypts record `0x30` with its
device private key (ECIES: ECDH P-256, HKDF-SHA256, AES-128-GCM), verifies
the signature with the site key it just received, stores the site
configuration and becomes OWNED; an OWNED lock ignores commissioning cards.
Write one with [`examples/hospital/write_commissioning_card.py`](../examples/hospital/write_commissioning_card.py).

**Reassign / decommission:** signed bundles targeted at this lock's device
ID — record `0x31` gives a new door / zones (stays OWNED), record `0x40`
wipes the site data → FACTORY (device key pair, event log and the sequence
floor are kept; a later commissioning bundle must be newer than the floor).

**Card check order:** identify → commissioning → admin → user application;
one card, one role.

**Identify card:** a card with the identify application (`4F4349`) is
checked first, in every state: the lock writes its public identity (state,
device ID, public key, firmware version, site AID, door) into the card's
free-access file and never opens. Set up / read with
[`examples/hospital/write_identify_card.py`](../examples/hospital/write_identify_card.py).

**Event log:** every boot, opening, refusal (with reason code), admin tap
and time change is recorded locally — 16-byte records in a ring buffer
(64 entries in NVS on the dev board; `lib/eventlog`). It contains
credential IDs, i.e. who opened which door when: access and retention follow
the site's privacy rules. Read-out via admin card comes later
([`spec/admin-card.md`](../spec/admin-card.md) §6).

**Time profiles** of the example (day shift, cleaning shift, office hours)
and the site time zone `CET-1CEST,M3.5.0,M10.5.0/3` are the factory defaults
(replaced by admin bundles)
([`spec/time-profiles.md`](../spec/time-profiles.md)).

**Clock & rollback:** the time is RAM only (reset → unknown); the high-water
mark (latest accepted time) is kept in NVS flash, and `time` refuses anything
more than 5 minutes earlier than it.

**Actuator:** GPIO4 (XIAO D2) is high for 3 s after `OPEN` — an LED with a
330 Ω resistor to GND, or a 3.3 V relay module. Forced low at boot
(disengaged by default).

**Status LED:** plain RGB LED (common cathode), D1 = red, D3 = green,
D10 = blue, one 330 Ω resistor per colour, common leg to GND. Green = open
(while the clutch is engaged), red = denied, yellow = retrying / blinking =
hold the card flat, short blue flash every 2 s = time unknown, fast red blink
= hardware or self-test error, off = idle. Pins and polarity are set in
`platformio.ini` (`OC_LED_*`).

**Serial commands** — read-only ones always; the *bench* ones only with
`OC_BENCH_COMMANDS` (set for the dev envs, **not** in `xiao-c3-prod`): they
bypass the signed-bundle path and must never be in a production build.

| Command | |
|---|---|
| `time` | UTC + local time, high-water mark |
| `id` | lock state and identity QR text `OC1:<device ID>:<public key>` |
| `log` | local event log (last 64 events: boot, open, deny + reason, admin, commission, time set) |
| `mgmt` | managed configuration (bundle sequence, blacklist, profiles, TZ) |
| `help` | |
| *bench:* `time <unix-utc-seconds>` | set the time (rollback rule applies) |
| *bench:* `time reset-hwm` | forget the high-water mark and the time |
| *bench:* `state factory` | unsigned decommission: wipe site data → FACTORY (device key pair kept); commission again |
| *bench:* `log clear` / `mgmt reset` | clear the log / empty managed configuration |
| *bench:* `uidmode key2` / `uidmode auto` | force the random-UID path (key 2 + `GetCardUID`) on fixed-UID cards / back to normal |

**Test cards:** write any example user onto a DESFire dev card with
[`examples/hospital/write_test_card.py`](../examples/hospital/write_test_card.py).

| Card | Expected |
|---|---|
| Sara (2001), ward 1 | `OPEN via zone 4` |
| Max (2002), ward 2 | `DENY no matching door/zone entry` |
| Eva (2003), blacklisted | `DENY credential blacklisted` |
| Ben (4002), time unknown | `DENY time unknown and card has an expiry` |
| Ben (4002), after `time 1795510800` | `DENY card expired` |
| Olga (4001), at `time 1795510800` (Tue 10:00 local) | `OPEN via zone 3, time profile 2` |
| Olga (4001), at `time 1795572000` (Wed 03:00 local) | `DENY right exists, but not at this time` |

## Phase 1 bring-up ✅ (2026-11-22)

Card detection (UID / ATQA / SAK vs. Proxmark3 `hf 14a info`), native DESFire
over ISO-DEP (`GetVersion` vs. `hf mfdes info`), AES authentication vs.
`hf mfdes auth` — see git history (`10a087c`, `3044e42`).

The dev test keys are public and for bench testing only — real site keys
never appear in source code or in this repository.
