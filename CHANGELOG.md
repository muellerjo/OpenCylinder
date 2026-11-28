# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Components are versioned independently (see `docs/versioning.md`); entries are
prefixed with the component: `fw`, `fwz`, `tools`, `hw`, `manager`, `spec`, `docs`, `ci`.

## [Unreleased]

### Added
- ci: GitHub Actions per component with path filters — `firmware` (host
  tests + PlatformIO builds), `manager` (pytest, Python 3.11/3.13),
  `examples` (Python 3.9 standard library + dry-runs), `hardware` (OpenSCAD
  fit checks, coil footprint reproducible); `firmware/test/host/run_all.sh`.
- hw: licence CERN-OHL-P-2.0 for the hardware design files (`hardware/LICENSE`);
  software stays MIT.
- manager: version in `manager/VERSION` (tag `manager-vX.Y.Z`).
- docs: README "Progress — done and open" checklist; versioning lists the
  manager and Zephyr firmware tags and the CI workflows.

## 2026-11-28 — first tagged baseline: `fw-v0.1.0`, `tools-v0.1.0`, `hw-v0.1.0`, `manager-v0.1.0`

Everything below was developed before the first tags and is contained in
them.

### Changed
- examples + manager: one implementation of the wire formats. The example
  scripts now import `manager/src/ocmanager/protocol` (via `_protocol.py`)
  instead of their own copies; output is unchanged (checked against
  recorded dry-runs). Manager tests pin the bytes with known-answer values
  recorded from the original scripts (`manager/tests/golden/`).

### Added
- manager: offline, multi-tenant web GUI — `python3 manager/app.py`, first-start
  setup in the browser (optional example hospital), sites/zones/doors/time
  profiles, people + roles + cards, blacklist, lock registry, user /
  maintenance / commissioning / reassign / decommission cards with Proxmark3
  plans, access matrix, audit log, API tokens; `--reset-password USER`;
  README with screenshots (`manager/docs/screenshots/`).
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
- fw: phase 2 bench lock (door 4 of the example hospital): site app
  `4F4331`, AES auth with the read key, encrypted `ReadData` (EV1 secure
  messaging, CMAC-chained IV, CRC32), card format v1 decision
  (`access_decision` lib), `IClock` + serial `time` command, retry on
  communication failures; boot self-test of AES-CMAC (RFC 4493) and CRC32.
  Verified on a DESFire EV1 for all bench cases (Sara open; Max no right;
  Eva blacklisted; Ben time-unknown and expired; Olga not at this time);
  host tests for the decision logic. Debug env `xiao-c3-debug` with NFC library logs.
- fw: time profiles (weekday mask, 2 intervals, past-midnight wrap) and site
  time zone as POSIX TZ rule incl. DST — verified against Python zoneinfo;
  spec/time-profiles.md.
- fw: rollback protection — high-water mark in NVS, time updates more than
  5 min earlier are refused.
- fw: random-UID support — key 2 + encrypted GetCardUID, testable on
  fixed-UID cards via `uidmode key2`.
- fw: bench actuator (GPIO, disengaged by default, 3 s window, hard limit).
- fw: RGB status LED (plain RGB, no standby current; open/deny/retry/
  time-unknown/error patterns, non-blocking PWM).
- spec: admin-card.md draft (separate admin application, TLV payload,
  anti-replay sequence, lock-unique transport key) — open decisions marked.
- examples + tools: clean DAM role separation — the card owner writes a grant
  file (`dam_setup.py --grant --out`), the site creates its application with
  only the grant and the DAM auth key (`write_test_card.py --dam SLOT
  --grant FILE`); Proxmark3 client patch `tools/proxmark3/` adds
  `--enck/--dammac` to `createdelegateapp`. Verified on a DESFire EV3.
- hw: knob electronics concept (`hardware/knob-electronics.md`) — the
  rotating knob decides the architecture (options A/B/C, recommendation A:
  everything in the outer knob), dimension budget (Ø 34 × 40 mm knob, Ø 28 mm
  boards, CR2/CR123A, clutch sleeve), antenna and board split; parametric
  13.56 MHz coil generator `hardware/antenna/gen_coil.py` (modified Wheeler)
  with a Ø 24 mm / 5-turn / ~1.0 µH KiCad footprint (not yet checked in KiCad).
- docs: production path — nRF54L15 decided; milestones M1–M7, platform
  port (RFAL, PSA Crypto + hardware key storage, Zephyr), power budget,
  shopping list (`docs/production-path.md`).
- examples: several independent sites on one card via DESFire EV2/EV3 DAM —
  `dam.py` (owner's grant: EncK, DAMMAC; verified against the Proxmark trace),
  `dam_setup.py` (DAM keys, grant), `write_test_card.py --dam SLOT`
  (delegated creation, no format), per-site dev keys in `site.json`
  (`sitekeys.py`), second example site `examples/ems-station/`. Verified on a
  DESFire EV3: one card with hospital + EMS applications; the lock reads only
  the application of the site it is commissioned for.
- fw: "no application for this site" shows the configured site AID.
- fw: rollback rule compares against the later of the high-water mark and
  the running clock (the mark is only written every 10 min, so old bundles
  could turn the clock back by up to 15 min); stale bundles may only move the
  clock forward. Verified on the bench.
- fw: **no keys in the firmware any more** — built-in dev site removed
  (`OC_DEV_BUILTIN_SITE`); a flashed lock starts FACTORY and gets site keys,
  door, zones and managed configuration only by commissioning; empty managed
  defaults (UTC, no profiles, no blacklist).
- fw: bench serial commands (time set, state factory, mgmt reset, log clear,
  uidmode) only with `OC_BENCH_COMMANDS`; new `xiao-c3-prod` env without
  them; `state owned` removed (OWNED only via commissioning).
- fw + examples: reassignment and decommissioning — targeted signed
  bundles with records 0x31 (new door / zones, stays OWNED) and 0x40
  (wipe site data -> FACTORY; device key pair, event log kept); records
  refused in untargeted bundles; sequence floor kept across decommission so
  old commissioning / decommission cards cannot be replayed; DECOM / REASS
  log events; `write_admin_card.py --reassign --door N` / `--decommission`;
  scripts take the lock from the site database (`--qr` optional). Verified on
  the bench incl. both replay refusals; firmware works unchanged on
  DESFire EV3 8K.
- docs: one card, one role — card check order documented.
- fw + examples: commissioning — FACTORY lock decrypts the ECIES record
  (ECDH P-256, HKDF-SHA256 per RFC 5869 with boot self-test, AES-128-GCM)
  with its device private key, verifies the bundle with the received site
  key, stores the site configuration (NVS) and applies the bundle's
  maintenance records → OWNED; built-in site constants replaced by the
  stored site configuration (dev site only as bench fallback);
  `write_commissioning_card.py` (commissioning application 4F434B, free
  read; site database locks.local.json, git-ignored).
- fw + examples: identify card — the lock writes its public identity into a
  free-access file (any state; never opens); chunked plain WriteData;
  `write_identify_card.py` sets up, reads and cross-checks against an
  engraved QR. Verified on the bench (OWNED and FACTORY, mismatch warning).
- fw: device identity — permanent ECDH P-256 device key pair generated on
  first boot (NVS), QR text `OC1:<device ID>:<compressed key>` in the banner
  and via `id`; lock states FACTORY (opens nothing) / OWNED; bench lock
  starts OWNED with the built-in dev site (`OC_DEV_BUILTIN_SITE`), `state
  factory|owned` to switch; SAR-ADC entropy source enabled so the RNG is
  truly random in the radio-less offline build.
- spec: commissioning redesigned — per-lock ECDH P-256 device key pair
  (permanent, public key as QR on the electronics module) replaces the
  secret transport key; ECIES commissioning record (AES-128-GCM, HKDF);
  lock states FACTORY/OWNED; targeted reassignment and decommission records;
  identify card; site database; recovery without paperwork.
- fw: device ID now in MAC byte order (matches esptool / USB serial);
  serial input ignores ANSI escape sequences (arrow keys); optional,
  git-ignored `platformio_local.ini` for a stable `/dev/serial/by-id/` port
  so the monitor reconnects after a reset.
- fw: local event log — 16-byte records (time, event number, type, reason
  code, door/zone or admin ID, credential or sequence) in a 64-entry NVS ring
  buffer; boot, open, deny (with reason), admin, time set, bench actions;
  serial `log` / `log clear`; `lib/eventlog` with host tests.
- fw + examples: maintenance admin card — signed management bundles
  (ECDSA P-256 over SHA-256, mbedTLS) with time sync, blacklist add/remove/
  replace (with expiry), time profiles and TZ, anti-replay sequence; state in
  NVS; `management` lib with host tests; `bundle.py`, `write_admin_card.py`
  (reuses the admin app — DESFire does not free memory on delete). Verified on
  the bench: apply, stale replay, blacklist + un-blacklist, bad signature,
  persistence across reset. Card errors with a status are refused at once
  (only no-response is retried).
- docs: online-architecture.md — update points, online doors, radio; firmware
  as board × variant, offline builds without radio code, remote unlock off by
  default.
- spec: admin card payload is a signed management bundle (ECDSA P-256, site
  key in the encoder, public key in locks), carrier-independent; admin-card
  design decisions recorded.
- fw: variant marking (`OC_VARIANT_*`), banner `0.1.0+<board>.<variant>`,
  compile guard against remote unlock in offline builds.
- fw + examples: per-card keys — read/issuer keys diversified with NXP
  AN10922 (M = UID || AID), boot self-test with the AN10922 example vector;
  `an10922.py` and `write_test_card.py` write diversified keys and verify
  them against the Proxmark's own `--kdf AN10922`.
- hw: first RF observation (brownout during AES at bad card angles).
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
  lock decision logic; `write_test_card.py` sets up a DESFire dev card via
  Proxmark3 (app `4F4331`, 3 keys, files, record) and checks read-back and
  key separation — verified on a DESFire EV1.
- tools: Elatec TWN4 encoder driver and card inspection script.
- docs: commissioning, lifecycle & security (incl. reset policy), versioning.
- hw: clutch / actuator concept and prior-art pool.
