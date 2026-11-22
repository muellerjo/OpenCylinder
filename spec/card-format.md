# Card format — OpenCylinder DESFire application

**Current format version: 1**

This is the OpenCylinder-owned card layout. Nothing external depends on it, so
it can evolve — but every change that alters how a record is interpreted must
bump `format_version` (see [Versioning rules](#versioning-rules)).

## Application

- **AID:** `0xF5 0x10 0x01`, sent to the card LSB-first: `01 10 F5`. Chosen to
  be unlikely to collide. (`000000` is the card master level — never use it.)
- **Keys:** 1 AES-128 application key, key number `0` = the **site key**.
  Ideally diversified per card (per-card key = f(site key, card UID)) so one
  extracted card key does not unlock the whole population. The site key is
  generated and held by the site admin and backed up off-site (escrow) —
  losing it means re-keying every card and cylinder.

## File 0 — access record (StandardDataFile)

Fixed-length 16-byte record that the cylinder reads after authentication.
All multi-byte integers are **little-endian** (the DESFire wire convention).

| Offset | Bytes | Field            | Notes |
|-------:|------:|------------------|-------|
| 0      | 4     | `credential_id`  | unique per card; what is logged / blacklisted |
| 4      | 4     | `valid_until`    | unix time (UTC, seconds); `0` = no expiry |
| 8      | 2     | `door_mask`      | bitmask of the doors this card may open |
| 10     | 1     | `format_version` | layout version of this record; currently `1` |
| 11     | 5     | reserved         | must be zero in format 1 |

Total: 16 bytes = one AES block, convenient for encrypted reads later.

`format_version = 0` is deliberately invalid: a card written before this field
existed (reserved bytes all zero) or a half-personalised card is rejected.

## How a cylinder decides (pseudocode)

```
select application F51001
if not authenticateAes(key 0, SITE_KEY):        reject   # wrong/cloned card -> stop
read file 0
if format_version != SUPPORTED_FORMAT_VERSION:  reject   # unknown layout: never guess
if valid_until != 0 and now > valid_until:      reject   # expired
if (door_mask & THIS_DOOR_BIT) == 0:            reject   # not authorised here
if credential_id in local_blacklist:            reject   # revoked
accept -> engage clutch
```

## Versioning rules

- Changing the meaning, size or position of any field → **new
  `format_version`**, and this document gets a section for the new layout.
- Firmware states the format versions it supports (`kCardFormatVersion` in
  `firmware/include/version.h`) and **denies** any other version — for a lock,
  failing closed is the only safe default.
- A migration path (firmware accepting both N and N+1 during a card re-issue)
  must be explicit and documented, never implicit.

## Why this beats UID-only

The `authenticateAes` step is the whole game: the card must *prove* it knows
the site key without ever sending it. A copied UID, or a "magic" card that
fakes the UID, cannot pass it. That is the line between real access control and
a toy.

## Personalisation

Done at the encoder (desktop reader + management tool), never at the lock:
take a factory-blank DESFire, authenticate to the card master key, create
application `F51001`, set key 0 to the (diversified) site key, create file 0,
write the record with `format_version = 1`. Verify with the Proxmark3. No NDA,
no vendor tool.
