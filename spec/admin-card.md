# Admin card — DRAFT

**Status: draft, not implemented. Design decisions taken 2026-11-23**
(marked **Decision**).
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

**Bootstrap:** a blank lock has no public key yet. A commissioning bundle's
record `0x30` is encrypted and MAC'd under the lock's transport key (§5) and
contains the site's public key; the lock decrypts it, then verifies the bundle
signature with the key it just received, and only then stores anything.

#### TLV payload

`type (1) | length (2, LE) | value`, in any order, unknown types skipped.

| Type | Record | Value |
|---:|---|---|
| `0x10` | blacklist add | n × (`credential_id` u32, `until` u32) — entry expires at `until` |
| `0x11` | blacklist remove | n × `credential_id` u32 |
| `0x12` | blacklist replace | full list (as 0x10) — replaces the lock's list |
| `0x20` | time profiles | n × 10-byte profile ([`time-profiles.md`](time-profiles.md)) — replaces the table |
| `0x21` | time-zone rule | POSIX TZ string, ≤ 47 bytes |
| `0x30` | commissioning block | §5 — encrypted for the target lock; includes the site management public key |
| `0x31` | lock assignment | door ID (u16), zone count (u8), zone IDs (u16 each) — for one target lock, §5 |

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

## 5. Commissioning (bootstrap) — the critical part

A blank lock must accept its **first** owner and nobody else. The
commissioning block carries the lock's site configuration: site AID, site read
key (master, for diversification), admin AID, admin read key (master), UID key,
plus the lock assignment (record 0x31).

These keys must not be readable by anyone who merely holds the admin card.
Proposal:

- Every lock ships with a **lock-unique transport key** (random per device,
  printed as QR code / label inside the housing, never shared between locks).
- The encoder encrypts the commissioning block **for that lock**:
  AES-CBC + CMAC under keys derived from the lock's transport key, bound to the
  lock's device ID (so a block for lock A is useless on lock B).
- The blank lock decrypts it, stores the keys in secure storage, **erases its
  transport key**, and from then on accepts only admin cards of that site
  (state OWNED).
- Re-commissioning an owned lock needs a valid admin card of the owning site
  with action *decommission*, or the physical reset (§2.6 of the security
  doc).

**Decision: lock-unique transport key.** One shared default key is ruled
out: the firmware is open source, so a shared key would be public and a
stolen commissioning card would expose all site keys. The flash tool
generates the key per device and prints it as a QR label for the inside of
the housing; the encoder scans it.

**Decision: one admin card per lock for commissioning.** A commissioning
card carries exactly one commissioning block (0x30) and one lock assignment
(0x31) for one target device; the encoder rewrites the card for the next
lock. Maintenance actions (time, blacklist, profiles, TZ) are not bound to a
device: one maintenance admin card serves all locks of the site.

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
  (blank lock: decrypt record 0x30 with the transport key first, §5)
apply in this order:
  1. time        (rollback rule, §3)
  2. sequence    (stop applying 3–4 if not newer, §4)
  3. blacklist / profiles / TZ
  4. commission / decommission (state machine, §5)
log the admin tap (admin_id, sequence, result)
```

Admin cards never open the door. Other carriers (update points, network,
radio) skip the DESFire steps and enter at "verify the bundle".
