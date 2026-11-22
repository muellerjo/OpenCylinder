# Hardware

Electronics (PCB, antenna) and mechanics (cylinder body, clutch) of
OpenCylinder. Version: see `VERSION`; each manufactured PCB additionally
carries a board revision (`rev A`, `rev B`, …) on the silkscreen
(see `../docs/versioning.md`).

- `mechanics/clutch-design.md` — clutch / actuator concept and prior-art pool.

## Current bench setup

- MCU (dev): ESP32-C3 SuperMini or Seeed XIAO ESP32C3
- NFC frontend: ST25R3916 (M5Stack Unit NFC, I2C over Grove)
- Production MCU (later): nRF52 (radio off) or STM32L5/U5

Large binary files (STEP, STL, renders, photos) are stored with Git LFS —
see `../.gitattributes`.
