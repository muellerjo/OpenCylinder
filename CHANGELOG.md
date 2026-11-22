# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Components are versioned independently (see `docs/versioning.md`); entries are
prefixed with the component: `fw`, `tools`, `hw`, `spec`, `docs`.

## [Unreleased]

### Added
- repo: monorepo layout (`firmware/`, `tools/`, `hardware/`, `spec/`, `docs/`)
  and per-component versioning, all starting at `0.1.0`.
- fw: PlatformIO project for ESP32-C3 SuperMini and Seeed XIAO ESP32C3 dev
  boards; build-time version stamping (`FW_VERSION`, `FW_GIT`) and boot banner.
- fw: `desfire_auth` library — DESFire EV1 AES authentication behind the
  `IDesfireTransport` interface; verified on a real DESFire EV1 against
  Proxmark3 `hf mfdes auth`, incl. rejection of a wrong key.
- fw: phase 1 bring-up on XIAO ESP32C3 + ST25R3916 (M5Unit-NFC 0.1.2):
  card detection, `M5DesfireTransport` (native DESFire over ISO-DEP),
  `GetVersion`, AES auth on application `F51001`.
- docs: README comparison with OSS Standard Offline.
- spec: card format version 1, including the `format_version` byte.
- tools: Elatec TWN4 encoder driver and card inspection script.
- docs: commissioning, lifecycle & security (incl. reset policy), versioning.
- hw: clutch / actuator concept and prior-art pool.
