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

## Next: Phase 1 bring-up

1. Detect the card, print the 7-byte UID, compare with the Proxmark3.
2. ISO-DEP layer-4 transceive (`GetVersion 0x60`, `SelectApplication 0x5A`).
3. Implement `IDesfireTransport` on it, run `authenticateAes()`.
4. Cross-check with Proxmark3 `hf mfdes auth`.
