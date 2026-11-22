# Firmware

PlatformIO project. Version: see `VERSION` (stamped into every build, printed
at boot — see `../docs/versioning.md`).

## Targets

| Env             | Board                     | I2C to ST25R3916 unit |
|-----------------|---------------------------|-----------------------|
| `c3-supermini`  | ESP32-C3 SuperMini        | SDA GPIO6, SCL GPIO7  |
| `xiao-c3`       | Seeed Studio XIAO ESP32C3 | SDA D4 (GPIO6), SCL D5 (GPIO7) |
| `xiao-c3-debug` | as `xiao-c3`, plus M5 NFC library error/warning logs (ISO-DEP timeouts etc.) | |

ST25R3916 unit (M5Stack Unit NFC, Grove): black → GND, red → 5V,
yellow → SDA, white → SCL.

```
pio run -e xiao-c3 -t upload -t monitor
```

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
- `test/host/` — host tests (plain g++, no hardware):
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

**Serial commands** (dev only — production gets the time from admin cards):
`time`, `time <unix-utc-seconds>`, `help`. After a reset the time is unknown.

**Test cards:** write any example user onto a DESFire dev card with
[`examples/hospital/write_test_card.py`](../examples/hospital/write_test_card.py).

| Card | Expected |
|---|---|
| Sara (2001), ward 1 | `OPEN via zone 4` |
| Max (2002), ward 2 | `DENY no matching door/zone entry` |
| Eva (2003), blacklisted | `DENY credential blacklisted` |
| Ben (4002), time unknown | `DENY time unknown and card has an expiry` |
| Ben (4002), after `time 1795510800` | `DENY card expired` |
| Olga (4001), cleaning shift | `DENY right exists, but not at this time` (time profiles not implemented yet → fail closed) |

## Phase 1 bring-up ✅ (2026-11-22)

Card detection (UID / ATQA / SAK vs. Proxmark3 `hf 14a info`), native DESFire
over ISO-DEP (`GetVersion` vs. `hf mfdes info`), AES authentication vs.
`hf mfdes auth` — see git history (`10a087c`, `3044e42`).

The dev test keys are public and for bench testing only — real site keys
never appear in source code or in this repository.
