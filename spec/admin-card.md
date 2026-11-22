# Admin card — DRAFT

**Status: draft. Implemented: maintenance bundles (time, blacklist, profiles,
TZ, sequence, ECDSA P-256 signature) — firmware `lib/management`, encoder
`examples/hospital/bundle.py` / `write_admin_card.py`, verified on the bench.
Local event log (§6, v1), device key pair, lock states, identify card and
commissioning (§5.1–5.3, §5.5) implemented. Not yet: reassignment,
decommissioning (§5.4), log read-out via card.** Design decisions
taken 2026-11-23 (marked **Decision**).
Context: [`docs/commissioning.md`](../docs/commissioning.md),
[`docs/lifecycle-and-security.md`](../docs/lifecycle-and-security.md).

The cylinder has no radio by default, so management data travels on a card.
The admin card is that card: it commissions locks, sets their clock, delivers
blacklist updates, time profiles and the time-zone rule, and decommissions
locks. It is the most sensitive object in the system.

All management data is a **signed management bundle** (§2). The admin card is
one carrier; update points, online doors and radio variants carry the same
bundle ([`docs/online-architecture.md`](../docs/online-architecture.md)).

## 1. Separation from user cards

The admin card uses its **own application per site** (the *admin
application*), never the site's user application:

| | User application | Admin application |
|---|---|---|
| AID | site AID | site **admin AID** (freely chosen, first nibble ≠ `F`, ≠ site AID) |
| Read key (held by locks) | site read key | **admin read key** (different key) |
| Issuer key (encoder only) | site issuer key | admin issuer key |

A user card can therefore never act as an admin card, and a lock that leaks
its site read key leaks nothing about admin cards. Both admin keys are
diversified per card (AN10922, M = UID ‖ admin AID).

## 2. Files of the admin application

All files: communication mode **full** (encrypted + CRC), read = admin read
key, write = admin issuer key.

### File 0 — admin header (16 bytes)

| Offset | Bytes | Field | Notes |
|---:|---:|---|---|
| 0 | 1 | `format_version` | admin format, `1` |
| 1 | 1 | `actions` | bit mask: 0 time · 1 blacklist · 2 profiles/TZ · 3 commission · 4 decommission |
| 2 | 2 | reserved | 0 |
| 4 | 4 | `admin_id` | which admin card (logged in the lock) |
| 8 | 4 | `valid_until` | unsigned Unix UTC; admin cards should expire quickly (days) |
| 12 | 4 | `issued_at` | unsigned Unix UTC — **the time the lock adopts** |

### File 1 — management bundle

File 1 holds one **management bundle** (file size up to 1024 bytes). The
bundle authenticates itself, independent of the carrier:

| Offset | Bytes | Field | Notes |
|---:|---:|---|---|
| 0 | 1 | `bundle_version` | `1` |
| 1 | 1 | flags | reserved, 0 |
| 2 | 3 | `site_aid` | user-application AID of the site (wire order) — binds the bundle to one site |
| 5 | 8 | `target_device` | device ID of one lock, or all zero = every lock of the site |
| 13 | 4 | `sequence` | monotonic per site (§4) |
| 17 | 4 | `issued_at` | unsigned Unix UTC — **the time the lock adopts** (§3) |
| 21 | 4 | `valid_until` | unsigned Unix UTC — bundle expiry (days) |
| 25 | 2 | `payload_len` | length of the TLV payload |
| 27 | n | payload | TLV records, below |
| 27+n | 64 | signature | ECDSA P-256 (r ‖ s) over SHA-256 of bytes 0 … 26+n |

The site's **management signing key** stays in the encoder (offline,
escrowed). Locks hold only its **public key**: a compromised lock cannot
forge bundles. ECDSA P-256 is supported by mbedTLS on ESP32, by the nRF52
CryptoCell and by STM32 crypto hardware.

On an admin card the bundle is additionally protected by the admin
application's DESFire authentication and encrypted read (defence in depth).

**Bootstrap:** a blank lock does not know the site's public key yet. A
commissioning bundle's record `0x30` is encrypted to the lock's own device
public key (§5.3) and contains the site's public key; the lock decrypts it,
then verifies the bundle signature with the key it just received, and only
then stores anything.

#### TLV payload

`type (1) | length (2, LE) | value`, in any order, unknown types skipped.

| Type | Record | Value |
|---:|---|---|
| `0x10` | blacklist add | n × (`credential_id` u32, `until` u32) — entry expires at `until` |
| `0x11` | blacklist remove | n × `credential_id` u32 |
| `0x12` | blacklist replace | full list (as 0x10) — replaces the lock's list |
| `0x20` | time profiles | n × 10-byte profile ([`time-profiles.md`](time-profiles.md)) — replaces the table |
| `0x21` | time-zone rule | POSIX TZ string, ≤ 47 bytes |
| `0x30` | commissioning block | §5.3 — ECIES-encrypted for the target lock; includes the site management public key |
| `0x31` | lock assignment | door ID (u16), zone count (u8), zone IDs (u16 each) — targeted bundles only, §5.3/§5.4 |
| `0x40` | decommission | no value — targeted bundles only, §5.4 |

## 3. Time sync

On every bundle (admin tap or other carrier) the lock adopts the bundle's
`issued_at` as its time **if** the
rollback rule allows it (not more than 5 min before the high-water mark,
`lifecycle-and-security.md` §2.5). The card has no clock, so the time is as
old as the walk to the lock: the encoder writes `issued_at` immediately before
the admin leaves, and admin cards are refreshed daily.

**Decision:** the lock also adopts a time that is *earlier* than its running
time, as long as it is within the rollback tolerance (≤ 5 min below the
high-water mark). This corrects fast-running locks; an old admin card gains
an attacker at most 5 minutes, anything older is refused.

## 4. Anti-replay

A copied or old admin card must not undo a newer blacklist. Each site keeps a
monotonic bundle **sequence number**; the lock stores the last one it applied
(NVS) and applies blacklist / profile / TZ records only if `sequence > last`. Time
sync still follows the rollback rule independently.

## 5. Lock identity, commissioning and decommissioning

### 5.1 Lock states

| State | Meaning | Accepts |
|---|---|---|
| **FACTORY** | blank, belongs to nobody — **opens nothing** | commissioning bundle for *this* device; identify card |
| **OWNED** | belongs to one site | user cards of that site; signed bundles of that site; identify card |

```
FACTORY ──commission──▶ OWNED ──decommission (signed)──▶ FACTORY
                          │
                          └──hard reset (internal pads, cylinder removed)──▶ FACTORY
```

Both transitions back to FACTORY wipe all **site** data (site keys, admin
keys, signature public key, door ID, zones, blacklist, profiles, TZ, last
sequence). The event log is kept. The lock's **device key pair is never
wiped** (§5.2).

### 5.2 Device key pair (the lock's identity)

**Decision (2026-11-23, replaces the earlier per-lock transport key):** every
lock has its own **ECDH P-256 key pair**.

- Generated **once**, by the lock itself, on its very first boot; the private
  key **never leaves the lock** (production: secure element / MCU key
  storage, not exportable).
- **Permanent:** not changed by hard reset, decommissioning or firmware
  updates. (Dev board: kept in NVS — a full `erase_flash` would lose it; the
  identify card, §5.5, catches that.)
- The **public key is not secret**: it is printed / engraved as a QR code on
  the **electronics module** (not on the mechanical cylinder), so key and QR
  always travel together. A replaced board brings its own QR.
- **Device ID:** 8 bytes; on the ESP32 dev board `00 00` + the 6-byte MAC.

Why not a secret transport key: a secret label must be protected and
destroyed, and whoever reads it can decrypt the commissioning data. With a
key pair the label holds nothing secret.

**QR content** (alphanumeric mode, uppercase hex):

```
OC1:<device ID, 16 hex>:<public key, compressed, 66 hex>
OC1:0000AC276EFB0250:03A1B2…   (≈ 88 characters, QR version 4, ~ 15–20 mm engraved)
```

### 5.3 Commissioning (FACTORY → OWNED)

**Decision: one commissioning card per lock.** The encoder:

1. gets the lock's device ID + public key (QR, site database §5.6, or
   identify card §5.5);
2. builds a **commissioning bundle**: `target_device` = that device ID,
   record `0x30` (commissioning block, incl. door ID and zones) plus the
   site's maintenance records (time profiles, TZ, blacklist) so the lock is
   complete after one tap;
3. encrypts the commissioning block **to the lock's public key** (ECIES,
   below) and **signs** the bundle with the site management key;
4. writes it onto a **commissioning card**: a DESFire card with the
   **commissioning application** (AID `4F434B`), one file with **free read**
   access (a blank lock has no keys to authenticate with — the content
   protects itself: secrets encrypted to the lock, everything signed). The
   card reveals only the target device ID and timestamps.

The lock (only in FACTORY):

1. checks `target_device` == own device ID;
2. decrypts record `0x30` with its **private key** — fails on every other lock;
3. verifies the bundle signature with the site management public key **from
   the decrypted block** (binds the bundle to the site that owns that key);
4. stores everything, records the bundle sequence → **OWNED**, logs it.

A stolen commissioning card is useless: its keys are readable only by the
target lock. An OWNED lock ignores commissioning bundles.

**Record `0x30` — commissioning block (ECIES):**

| Field | Bytes | |
|---|---:|---|
| ephemeral public key | 65 | P-256, **uncompressed** (mbedTLS 2.28 on the ESP32 cannot read compressed points), fresh per commissioning |
| nonce | 12 | random |
| ciphertext | n | AES-128-GCM of the plaintext below |
| tag | 16 | GCM authentication tag |

Key: ECDH(ephemeral private, lock public) → shared x-coordinate (32 bytes) →
HKDF-SHA256(salt = device ID, info = `"OpenCylinder commissioning v1"`) →
16-byte AES key. Additional authenticated data: the bundle header (27 bytes).

Plaintext:

| Field | Bytes |
|---|---:|
| site AID (wire order) | 3 |
| admin AID (wire order) | 3 |
| site read master key | 16 |
| UID key | 16 |
| admin read master key | 16 |
| site management public key (uncompressed) | 65 |
| door ID | 2 |
| zone count | 1 |
| zone IDs | 2 each, ≤ 16 |

**Record `0x31` — lock assignment:** door ID (u16), zone count (u8),
zone IDs (u16 each, ≤ 16). For **reassignment** of an OWNED lock (§5.4); only
valid in a bundle with `target_device` = this lock. (At commissioning, door
and zones travel encrypted inside `0x30`.)

### 5.4 Reassignment and decommissioning (OWNED)

- **New door / zones, same owner:** a signed maintenance bundle targeted at
  this lock with record `0x31` — the lock stays OWNED, no new keys needed.
- **Decommission** (owner or keys change): a signed bundle targeted at this
  lock (`target_device` must not be zero) with record **`0x40`
  decommission** (no value), sequence newer than the last applied → the lock
  wipes its site data → FACTORY. An old decommission card is refused by the
  sequence rule.
- **Site keys lost:** hard reset via the internal pads
  (`docs/lifecycle-and-security.md` §2.6) → FACTORY, then commission again.

### 5.5 Identify card

A DESFire card with the **identify application** (AID `4F4349`) holding one
StandardDataFile (file 0, 64 bytes, communication mode plain, **free** read
and write access). Tapped on any lock in any state, the lock **writes** its
public identity into it — nothing secret, and the lock never takes
instructions from this card:

| Field | Bytes | |
|---|---:|---|
| format | 1 | `1` |
| state | 1 | `0` FACTORY, `1` OWNED |
| device ID | 8 | |
| device public key (compressed) | 33 | |
| firmware version | 3 | major, minor, patch |
| site AID | 3 | zero in FACTORY |
| door ID | 2 | zero in FACTORY |
| reserved | 13 | zero |

Uses: find out what a lock is without paperwork; cross-check the engraved QR
against the key the lock really holds (guards against a swapped label: the
encoder warns if they differ).

### 5.6 Site database (encoder)

The encoder keeps, per lock: device ID, device public key, door ID, zones,
commissioning date, last bundle sequence. Filled automatically at
commissioning; the QR and the identify card are only needed when this is
missing.

### 5.7 Recovering a lock without paperwork

| Situation | Steps |
|---|---|
| own lock, site keys available | identify card → (decommission → commission) or just reassignment |
| own lock, site keys lost | hard reset → identify card → commission |
| second-hand / unknown owner | hard reset → identify card → commission |

## 6. Logging back to the card

**Decision:** v1 keeps the event log **locally** in the lock (ring buffer in
flash: taps, denials, resets, admin taps — for diagnostics). Read-out via the
admin card (a dedicated log file, written by the lock with its own log-write
key) follows in a later version, once the record format and the privacy
rules are settled — in a hospital these are records of employees'
movements.

## 7. What the lock does on an admin tap

```
select admin AID; authenticate admin read key (diversified)
read file 0: format, valid_until, admin_id
read file 1: management bundle
verify the bundle (same path for every carrier):
  site_aid == this site?  target_device == 0 or this lock?
  signature valid with the site management public key?   else ignore
  (FACTORY lock: decrypt record 0x30 with the device private key first, §5.3)
apply in this order:
  1. time        (rollback rule, §3)
  2. sequence    (stop applying 3–4 if not newer, §4)
  3. blacklist / profiles / TZ
  4. commission / decommission (state machine, §5)
log the admin tap (admin_id, sequence, result)
```

Admin cards never open the door. Other carriers (update points, network,
radio) skip the DESFire steps and enter at "verify the bundle".
