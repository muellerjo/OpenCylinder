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
- docs: README comparison with OSS Standard Offline (incl. key management
  and multi-site cards).
- spec: card format version 1 — 16-byte header (`format_version` first,
  `credential_id`, `valid_until`, `issued_at`) plus an access list of door and
  zone entries with time-profile references (scales to 65 535 doors / zones);
  separate issuer key and site read key (diversified per card) plus a UID
  key for random-UID cards; per-card diversified card master key;
  one application per site with a freely chosen AID (first nibble not `F`,
  per NXP AN10787), multi-site cards (EV2/EV3 DAM recommended); test site
  AID `4F4331`.
- examples: fictional hospital (doors, zones, time profiles, roles, users)
  with `check_access.py`, which encodes cards per format v1 and runs the
  lock decision logic.
- tools: Elatec TWN4 encoder driver and card inspection script.
- docs: commissioning, lifecycle & security (incl. reset policy), versioning.
- hw: clutch / actuator concept and prior-art pool.
