# Firmware — Zephyr / nRF Connect SDK (production path)

Target: **nRF54L15** ([`../docs/production-path.md`](../docs/production-path.md)).
Bench board: **Seeed XIAO nRF54L15** (on-board SAMD11 debugger → flashing and
serial console over USB-C; D4 = SDA, D5 = SCL, so the ST25R3916 Grove wiring
from the ESP32-C3 bench stays the same). The ESP32 bench firmware in
[`../firmware/`](../firmware/) stays the reference until this port catches up.

## Status: milestone M1 skeleton — **untested**

- banner with version and variant (`offline`: `CONFIG_BT=n`, compile guard)
- ST25R3916 detection on I2C (reads the IC identity register)
- next: ST RFAL port (card detection), then the portable libraries
  (`../firmware/lib/*`) and PSA Crypto with hardware key storage (M2, M3)

## Toolchain (once)

1. nRF Connect SDK ≥ 3.0.1 (Seeed's requirement for this board), e.g. via
   `nrfutil` (`nrfutil sdk-manager` / toolchain manager) — several GB.
2. Seeed's board definitions (board root): the `platform-seeedboards`
   repository, see the Seeed wiki "XIAO nRF54L15 getting started".
3. OpenOCD (flashing through the on-board SAMD11).

## Build & flash

```
west build -b xiao_nrf54l15/nrf54l15/cpuapp -- -DBOARD_ROOT=<path to platform-seeedboards/zephyr>
west flash
```

Exact board name and node labels are to be confirmed against Seeed's board
definition on the first build (TODO markers in the overlay).
