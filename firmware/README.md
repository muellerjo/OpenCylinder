# Firmware

PlatformIO project. Version: see `VERSION` (stamped into every build, printed
at boot — see `../docs/versioning.md`).

## Targets

| Env            | Board                    | I2C to ST25R3916 unit |
|----------------|--------------------------|-----------------------|
| `c3-supermini` | ESP32-C3 SuperMini       | SDA GPIO6, SCL GPIO7  |
| `xiao-c3`      | Seeed Studio XIAO ESP32C3 | SDA D4 (GPIO6), SCL D5 (GPIO7) |

ST25R3916 unit (M5Stack Unit NFC, Grove): black → GND, red → 5V,
yellow → SDA, white → SCL.

```
pio run -e c3-supermini -t upload -t monitor
pio run -e xiao-c3      -t upload -t monitor
```

The ESP32-C3 boards are for development only. The battery-powered device moves
to nRF52 or STM32L5/U5; hardware-specific code stays behind interfaces so the
port swaps the transport and crypto backends, not the logic.

## Layout

- `lib/desfire_auth/` — portable DESFire AES auth (mbedTLS), no hardware deps.
- `include/version.h` — build version macros, supported card format version.
- `scripts/version.py` — pre-build version stamping.
- `src/main.cpp` — dev skeleton (boot banner, I2C init).

- `src/platform/esp32/` — `M5DesfireTransport` (`IDesfireTransport` on the
  M5Unit-NFC ISO-DEP layer, native DESFire frames).

## Phase 1 bring-up ✅ (verified 2026-11-22)

On every DESFire card tap the firmware prints:

1. UID / type / ATQA / SAK — compare with Proxmark3 `hf 14a info`.
2. `GetVersion` (HW / SW / UID / batch / production date) — compare with the
   `raw` lines of `hf mfdes info`.
3. AES authentication on application `F51001`, key 0 — tries the zero key,
   then the dev test key `00112233445566778899AABBCCDDEEFF`.

**Prepare a test card** (Proxmark3, factory-default card master key —
`hf mfdes formatpicc` wipes all applications first if needed):

```
hf mfdes createapp --aid F51001 --dstalgo aes --numkeys 1
hf mfdes auth --aid F51001 -n 0 -t aes -k 00000000000000000000000000000000
hf mfdes changekey --aid F51001 -t aes -k 00000000000000000000000000000000 \
  --newkey 00112233445566778899AABBCCDDEEFF --newver 01
hf mfdes auth --aid F51001 -n 0 -t aes -k 00112233445566778899AABBCCDDEEFF
```

Expected after the key change: `zero key : failed`, `dev test key : OK`.

The dev test key is public and for bench testing only — real site keys never
appear in source code or in this repository.
