# Admin card — DRAFT for review

**Status: draft, not implemented.** Open decisions are marked **[decide]**.
Context: [`docs/commissioning.md`](../docs/commissioning.md),
[`docs/lifecycle-and-security.md`](../docs/lifecycle-and-security.md).

OpenCylinder has no radio, so every management action travels on a card. The
admin card is that card: it commissions locks, sets their clock, delivers
blacklist updates, time profiles and the time-zone rule, and decommissions
locks. It is the most sensitive object in the system.

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

### File 1 — payload (TLV records)

`type (1) | length (2, LE) | value`, in any order, unknown types skipped.

| Type | Record | Value |
|---:|---|---|
| `0x01` | sequence number | `uint32` — monotonic per site, see §4 |
| `0x10` | blacklist add | n × (`credential_id` u32, `until` u32) — entry expires at `until` |
| `0x11` | blacklist remove | n × `credential_id` u32 |
| `0x12` | blacklist replace | full list (as 0x10) — replaces the lock's list |
| `0x20` | time profiles | n × 10-byte profile ([`time-profiles.md`](time-profiles.md)) — replaces the table |
| `0x21` | time-zone rule | POSIX TZ string, ≤ 47 bytes |
| `0x30` | commissioning block | §5 |
| `0x31` | lock assignment | door ID (u16), zone count (u8), zone IDs (u16 each) — for one target lock, §5 |

## 3. Time sync

On every admin tap the lock adopts `issued_at` as its time **if** the
rollback rule allows it (not more than 5 min before the high-water mark,
`lifecycle-and-security.md` §2.5). The card has no clock, so the time is as
old as the walk to the lock: the encoder writes `issued_at` immediately before
the admin leaves, and admin cards are refreshed daily.

**[decide]** Also adopt time when it is *earlier* than the lock's running time
but within the tolerance (corrects a fast-running lock), or only ever move
forward?

## 4. Anti-replay

A copied or old admin card must not undo a newer blacklist. Each site keeps a
monotonic **sequence number**; the lock stores the last one it applied (NVS)
and applies blacklist / profile / TZ records only if `sequence > last`. Time
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

**[decide]** Lock-unique transport key (recommended) vs. one default transport
key for all blank locks (simpler, but then anyone holding a commissioning
admin card plus the default key could read site keys). **[decide]** One admin
card per lock to commission, or one admin card with assignments for several
locks (record 0x31 repeated with a target device ID)?

## 6. Logging back to the card

Later version: the lock appends its event log (taps, denials, resets) to a
file on the admin card (write rights for the admin read key on a dedicated
log file), so the admin collects logs while syncing. **[decide]** in v1 or
later?

## 7. What the lock does on an admin tap

```
select admin AID; authenticate admin read key (diversified)
read file 0: format, valid_until (needs known time OR card time), admin_id
read file 1: TLV payload
apply in this order:
  1. time        (rollback rule)
  2. sequence    (stop applying 3–4 if not newer)
  3. blacklist / profiles / TZ
  4. commission / decommission (state machine, §5)
log the admin tap (admin_id, actions, result)
```

Admin cards never open the door.
