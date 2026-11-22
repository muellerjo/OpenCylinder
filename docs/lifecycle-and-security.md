# Lifecycle & security — OpenCylinder

Fully offline. No radio. Every management action travels on a card (data-mule).
This document defines the trust model, the lifecycle processes, and what
"burglar-proof" does and does not mean here.

## 1. Trust model — keys and cards

Two separate keys, never mixed:

- **Site read key** (AES-128) — authenticates and reads *user* cards. Held in
  the secure element of each lock and in the encoder. Diversified per card
  (NXP AN10922, input card UID ‖ AID) so one cracked card ≠ all cards.
- **Issuer key** (AES-128) — the only key that can write or change user cards.
  Held by the encoder only, **never by a lock**, so a lock compromised in the
  field cannot be used to rewrite genuine cards. Also diversified per card.
- **UID key** (AES-128, site-wide) — only lets locks and encoder read the real
  UID of a random-UID card (`GetCardUID`); no file rights.
- **Card master key** — owned by the cardholder or issuing organisation,
  diversified per card from one master secret; never left at the factory
  default on real cards (`spec/card-format.md`).
- **Admin key** (AES-128) — authorises *management* actions on a lock
  (commission, blacklist, time, decommission). Distinct from the site key, so a
  normal user card can never perform admin operations.

Keys live in: the lock's **secure element** (ST secure storage / ATECC608A),
the admin's **encoder**, and (derived) on cards. **Never in plain flash.**
All keys are backed up off-site (institutional escrow) — losing them is the
only unrecoverable failure.

Card types:
- **User card** — your DESFire app: header `{format_version, credential_id,
  valid_until, issued_at}` plus an access list of door and zone entries
  (`spec/card-format.md`).
- **Admin card** — privileged, carries blacklist deltas, current time, and
  commissioning data. The single most sensitive object in the system: guard it
  like the master key it effectively is.

## 2. Lifecycle processes

### 2.1 Card personalisation (at the encoder, never at the lock)
Factory-blank DESFire → auth card-master-key (and replace it with a
site-owned one) → create app → set issuer key + site read key (diversified) →
write header and access list. Verify with Proxmark. You own the format, so you own this step — no NDA, no vendor.

### 2.2 Lock commissioning (initialising a new lock)
A fresh cylinder ships **blank** (factory/transport state, opens nothing).
Commissioning, done by tapping the **admin card** to the new lock:
1. installs the **site key** (so it can authenticate user cards),
2. assigns its **door ID** (16-bit, unique per site) and the **zones** it
   belongs to (e.g. "Ward 3", "Maintenance"),
3. sets the **admin key** (from now on only your admin card can manage it),
4. sets the initial **time** (RTC).

After this the lock is "owned": it only accepts admin ops under the admin key,
and only opens for user cards that pass auth + authorisation + not-revoked.

**Attack to defend against:** someone resets your lock and re-commissions it with
*their* key. Mitigations: the blank→owned transition needs the factory/transport
secret (which you change on first commission) *and* physical access; re-commission
of an owned lock needs the admin key or a protected physical reset (§2.6).

### 2.3 Normal unlock (data-on-card, fully local)
```
card tap -> LPCD wakes MCU -> field on -> select app
         -> AES mutual auth        (proves card holds site key; no UID cloning)
         -> read header {format_version, credential_id, valid_until, issued_at}
         -> format_version known ?          else reject
         -> valid_until == 0, or (time known and valid_until >= RTC) ?
                                            else reject   (see §2.5)
         -> credential_id NOT in blacklist? else reject
         -> read access list: an entry for THIS door ID or one of THIS lock's
            zones, whose time profile allows now ?   else reject
         -> engage clutch; user turns knob; log event locally; sleep
```
No network, no central anything. The decision is made in the lock.

### 2.4 Revocation / blacklist update (offline)
Lost/revoked card → admin adds `credential_id` (+ its `valid_until`) to the
blacklist in the management software → admin walks to each lock, taps the
**admin card** → lock authenticates admin key → merges the blacklist delta into
local flash. Entries auto-expire at their `valid_until`, so the list stays
bounded. Short `valid_until` on user cards is the backstop: a lost card you have
not yet blacklisted dies on its own.

### 2.5 Time sync
The admin card carries current time; every admin tap sets the lock's RTC.
Offline clocks drift — syncing on admin visits is how validity/expiry stays
correct without a network.

Time rules:

1. **UTC only** — Unix time in seconds, never local time (no DST/time-zone
   errors in the lock). Stored and compared as **unsigned 32-bit**
   (`uint32_t`, valid until 2106) — never via a signed 32-bit `time_t` or the
   C library time functions, which overflow in 2038 on some embedded targets.
2. **Only authenticated admin cards set the clock.** (Dev boards additionally
   accept a serial `time` command; production firmware does not.)
3. **No rollback.** The lock keeps a *high-water mark* in non-volatile storage:
   the latest time it has ever accepted. A new time earlier than the mark
   (beyond a few minutes' tolerance) is rejected — otherwise an old admin card
   could turn the clock back and revive expired cards.
4. **Time unknown** (e.g. battery changed without RTC backup, or never set):
   - cards **with** an expiry (`valid_until != 0`) are **rejected**;
   - cards **without** expiry (`valid_until == 0`) are still accepted
     (door mask + blacklist checks apply as usual);
   - the next admin tap sets the time and normal operation resumes.
   This fails safe for time-limited cards while keeping permanent cards
   (owner, admin) working — so a battery change never locks the owner out.
   Consequence: permanent cards are the ones to keep few and guard well.
5. **Drift budget:** day-granularity expiry tolerates minutes of drift; an RTC
   of ±20 ppm (≈ 1 min/month) synced on admin visits is sufficient.

Hardware (decided with the production PCB): MCU-internal RTC with a
32.768 kHz crystal, or an external low-power RTC (e.g. RV-3028-C7, ~45 nA),
ideally with backup so a battery change keeps the time.

### 2.6 Decommission / reset
- **Soft (with admin key):** admin card decommissions the lock — wipes config,
  back to blank, ready to re-commission. Authenticated → safe.
- **Hard (admin key lost):** a physical reset that wipes the secure element to
  factory. **Must require physical disassembly** (internal contact/jumper), so it
  can't be triggered from the outside. Critical property: **reset returns the
  lock to blank — it opens nothing until re-commissioned.** A reset is *denial*,
  never *entry*. A burglar who resets your lock has locked you out, not gotten in.
- **Recovery without reset:** because the site key and admin key are escrowed,
  you re-provision rather than factory-reset. Escrow is what makes the hard case
  rare.

#### Reset policy (hardware requirements)

A Euro-profile cylinder can only be removed with the door **open**: the fixing
screw sits in the door edge, covered by the frame when the door is closed.
The reset hangs off that property.

1. **Internal reset pads on the inner PCB**, only reachable with the cylinder
   removed. **No externally visible reset hole** — a router-style pinhole would
   invite DoS (anyone bricks the lock with a paper clip). Electronics and reset
   live on the inside, never in the outer knob.
2. **Defence in depth:** normally a reset requires the admin key *and* physical
   access. Only on genuine admin-key loss does it fall back to a purely physical
   wipe. Since reset = denial, the residual risk is DoS/vandalism, not entry.
3. **Anti-pull protection is mandatory.** The "only when removed" gate holds
   only if the cylinder cannot be pulled or unscrewed from outside — install
   with a security escutcheon / anti-pull fitting. The reset protection is only
   as strong as the removal protection.
4. **Must work with a flat battery** — that is often exactly when a reset is
   needed. It must not depend on a charged cell (e.g. reset on power-up).
5. **Deliberate service procedure, not a single button:** e.g. bridge two pads,
   or hold a button while inserting the battery, so it cannot happen by
   accident or in passing.
6. **Log every reset locally** (timestamp, that it happened); readable via the
   admin card.
7. **Deferred past v1:** a tamper switch that zeroises the keys when the
   housing is opened without authorisation (against key extraction). If added,
   legitimate service with admin auth (e.g. battery change) must not trigger it.

Priority: the reset is the smaller security lever because it only ever denies.
The bootstrap / transport-key handling in commissioning
([`commissioning.md`](commissioning.md)) decides whether someone can take a
lock over — that is where most of the care belongs.

## 3. No radio, no Bluetooth — on purpose

Bluetooth would add: a wireless attack surface (BLE stack bugs, pairing/relay
attacks, a lock that is remotely probeable), continuous power draw, and
complexity. Everything BT would provide — config, logs, blacklist — is already
handled by the **admin card** with **zero remote attack surface**. For a
burglar-proof device, the absence of a radio is a *feature*, not a limitation.
If a config/log convenience is ever wanted, a passive NFC port (ST25DV,
field-powered) or an internal wired service port (only reachable with the unit
open) beats BT on security.

## 4. Security properties ("einbruchsicher")

| Property | How it's achieved |
|---|---|
| No card cloning | AES mutual auth, not UID matching |
| No key extraction | Keys in secure element, never plain flash; optional tamper-wipe |
| No record spoofing | Authenticated read of the on-card record |
| No remote attack | No radio at all |
| Reset ≠ entry | Reset returns lock to blank; opens nothing until re-commissioned |
| No forced turn | Clutch resists torque when decoupled (mechanical, see §5) |
| Fail-safe | Mechanical override key; dead battery never locks you out |

## 5. The honest weak point: mechanics, not crypto

The crypto here is strong and the easy part. **The real burglar-proofing is
mechanical**, and it's where DIY is genuinely hard:
- The **clutch** must resist being forced when decoupled — otherwise someone
  just cranks the knob and drives the cam. This is precision mechanical design.
- The **cylinder body** must resist drilling, bumping, pulling and snapping.
  Certified commercial cylinders (EN 1303 / EN 15684) exist precisely because
  this is hard to get right.

**Your electronics are only as strong as the mechanical lock they sit in.** A
perfect AES implementation behind a cylinder that snaps in 30 seconds is not
secure. For interior / garden / workshop doors this is fine. For a real front
door or other exterior doors, either house the mechatronics in a
**certified mechanical cylinder body**, or accept that the DIY unit is a
convenience layer and keep a rated mechanical lock as the actual security.
Be honest with yourself about which door you're protecting.
