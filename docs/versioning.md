# Versioning

OpenCylinder is one repository with independently versioned components.
Hardware, firmware and tools move at different speeds, so each has its own
version line. Compatibility between them is expressed through the **card
format version**, not by keeping component versions in lockstep.

## Components

| Component | Source of truth      | Git tag          | Scheme |
|-----------|----------------------|------------------|--------|
| Firmware  | `firmware/VERSION`   | `fw-vX.Y.Z`      | SemVer |
| Tools     | `tools/VERSION`      | `tools-vX.Y.Z`   | SemVer |
| Hardware  | `hardware/VERSION`   | `hw-vX.Y.Z`      | SemVer + board revision (`rev A`, `rev B`, …) silkscreened on the PCB |
| Card format | `spec/card-format.md` (`format_version` byte) | — | integer, `1, 2, 3…` |

All components start at `0.1.0`. While the major version is `0`, anything may
change; `1.0.0` is the first release meant to be installed on a real door.

## SemVer meaning here

- **MAJOR** — breaks compatibility (e.g. firmware drops a card format, a tool
  writes cards older firmware rejects, a PCB revision needs different firmware).
- **MINOR** — new capability, backwards compatible.
- **PATCH** — fixes only.

## Firmware variants

Firmware is built per **board × variant** (`docs/online-architecture.md`),
e.g. `xiao-c3-offline`, `nrf52-online-ble`. The variant is part of every
version string as SemVer build metadata and of every release file name:

```
0.2.0+xiao-c3.offline        ->  opencylinder-fw-0.2.0-xiao-c3-offline.bin
```

All variants of one release share the `fw-vX.Y.Z` tag; offline builds contain
no radio code at all.

## Firmware build stamping

`firmware/scripts/version.py` runs before every PlatformIO build and injects:

- `FW_VERSION` — contents of `firmware/VERSION`
- `FW_GIT` — `git describe --tags --match "fw-v*" --always --dirty`
  (e.g. `fw-v0.1.0-3-g1a2b3c4-dirty`; `-dirty` = uncommitted tracked changes)

The firmware prints both at boot, so every board can tell exactly which source
it runs. A `-dirty` build is never installed on a real door.

## Card format compatibility

The card record carries a `format_version` byte (`spec/card-format.md`).
Firmware declares the versions it supports (`kCardFormatVersion` in
`firmware/include/version.h`) and **rejects everything else** — a lock fails
closed. The encoder tool writes exactly one format version per release.

The same rule will apply to the configuration a lock stores during
commissioning (site read key, admin key, door ID, zones, …): it gets its own layout version
when that storage is implemented.

## Releasing a component

1. Update `<component>/VERSION`.
2. Move the entries under `## [Unreleased]` in `CHANGELOG.md` to a new
   version heading for that component.
3. Commit, then tag: `git tag -a fw-v0.2.0 -m "Firmware 0.2.0"`.
4. Push the tag explicitly: `git push origin fw-v0.2.0`.

Nothing is tagged until a component is deliberately released.
