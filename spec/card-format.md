# Card format — OpenCylinder DESFire application

**Current format version: 1** (not yet issued on any card)

This is the OpenCylinder-owned card layout. Nothing external depends on it, so
it can evolve — but every change that alters how a record is interpreted must
bump `format_version` (see [Versioning rules](#versioning-rules)).

Design goal: scale from a single front door to sites with thousands of doors
(e.g. a hospital) **without** the card growing with the size of the site. The
card carries a short **access list** of doors and zones; each lock knows its
own door ID and the zones it belongs to.

## Application

- **One application per site.** Every site (a home, a hospital, an EMS
  station, a workshop …) has its own DESFire application with its own keys;
  see [Multiple sites on one card](#multiple-sites-on-one-card).
- **AID (site AID):** freely chosen by each site at setup — 3 bytes, sent to
  the card LSB-first. Rules:
  - first nibble **not `F`** — AIDs `Fxxxxx` are reserved for NXP MAD-mapped
    application codes (AN10787 §3.10) that are assigned by a registration
    office; e.g. `F51001` would decode to MAD code `0x5100`, cluster
    "access control & security";
  - not `000000` (card master level), not `FFFFFF` (MAD3 issuer info);
  - recommended: choose it at random from `000001`–`EFFFFF` (~15.7 million
    values). The encoder checks the card's application list before creating
    the app and refuses on a collision.
- **Test site:** `4F 43 31` ("OC1" in ASCII) is reserved for development and
  bench tests — never for a real site.
- **Keys:** 3 AES-128 application keys with separated roles (the number of
  keys is fixed when the application is created, so all three exist from
  format 1 on):

  | Key | Name | Held by | Used for | Per card? |
  |----:|------|---------|----------|-----------|
  | 0 | **issuer key** (application master key) | encoder / management tool only | creating, writing and changing the card | diversified |
  | 1 | **site read key** | every lock (secure storage) and the encoder | authenticating and reading at the door | diversified |
  | 2 | **UID key** | every lock and the encoder | only `GetCardUID` on random-UID cards; **no** file rights | site-wide, not diversified |

  A lock never holds the key that can **modify** a genuine card. Keys 0 and 1
  are **diversified per card** with NXP AN10922 (AES-128), so a key
  extracted from one card does not open the rest of the population.
  Diversification input, exactly: **M = UID (7 bytes) ‖ AID (3 bytes, LSB
  first as on the wire)**, no system identifier. Example: UID
  `04 37 94 DA BB 75 80`, AID `4F4331` → M = `04 37 94 DA BB 75 80 31 43 4F`
  (same as Proxmark3 `--kdf AN10922 -i 043794DABB758031434F`).
  Key 2 cannot be diversified (it is needed *before* the real UID is known),
  so it is given no rights at all: leaking it reveals card UIDs, nothing more.
  The master keys are generated and held by the site admin and backed up
  off-site (escrow) — losing them means re-keying every card and lock.

### Getting the real UID (fixed or random UID)

Diversification needs the card's **real** 7-byte UID.

- **Fixed UID** (default): the UID seen during anticollision is the real one.
- **Random UID** (optional, for privacy, irreversible on the card): the card
  presents a new random 4-byte ID (first byte `0x08`) on every activation.
  The real UID is only available via `GetCardUID` after an authentication
  with any key — hence key 2:

  ```
  select application SITE_AID
  authenticateAes(key 2, SITE_UID_KEY)     # site-wide, opens nothing
  uid = GetCardUID()                       # real UID, sent encrypted
  authenticateAes(key 1, diversify(SITE_READ_KEY, uid, aid))
  ```

  Costs one extra authentication (tens of ms), only on random-UID cards.
  Only holders of the UID key can link a random-UID card to its real UID.

## Files

All multi-byte integers are **little-endian** (the DESFire wire convention).
Both files are StandardDataFiles with communication mode **full** (encrypted +
MAC'd) and access rights: read = key 1, write = key 0, read&write = key 0,
change access rights = key 0.

### File 0 — header (16 bytes)

| Offset | Bytes | Field | Notes |
|-------:|------:|-------|-------|
| 0 | 1 | `format_version` | layout version; currently `1`. `0` is invalid |
| 1 | 1 | `entry_count` | number of valid entries in file 1 (0…`file 1 size / 4`) |
| 2 | 2 | reserved | must be zero in format 1 |
| 4 | 4 | `credential_id` | unique per card; what is logged / blacklisted |
| 8 | 4 | `valid_until` | **unsigned** Unix time (UTC, s) — valid until 2106-02-07; `0` = no expiry |
| 12 | 4 | `issued_at` | **unsigned** Unix time (UTC, s) when the encoder last wrote this card |

16 bytes = one AES block. `format_version` comes first so a reader can reject
an unknown layout before interpreting anything else. A card with all-zero
header (blank or half-personalised) is rejected because `format_version = 0`.

`issued_at` serves audit and ordering; whether locks may also use it as a
lower bound for their clock ("it is at least this late") is decided with the
time-sync implementation — see `docs/lifecycle-and-security.md` §2.5.

**No year-2038 problem:** `valid_until` and `issued_at` are *unsigned* 32-bit
and run until 2106. Implementations must not pass them through a signed 32-bit
`time_t` (as on some embedded C libraries, e.g. the Arduino ESP32-C3 build) —
keep them as `uint32_t` end to end.

### File 1 — access list (4 bytes per entry)

File size is a multiple of 4, fixed at personalisation (default **128 bytes =
32 entries**, maximum 256 bytes = 64 entries). Only the first `entry_count`
entries are valid; the rest must be zero.

| Offset in entry | Bytes | Field | Notes |
|----------------:|------:|-------|-------|
| 0 | 1 | `type` | `0x01` = door, `0x02` = zone; any other value: entry ignored |
| 1 | 2 | `target_id` | door ID or zone ID, 1…65535 (`0` is invalid) |
| 3 | 1 | `time_profile` | `0` = always; `1…255` = profile defined in the lock |

- **Door entry:** opens exactly the lock with that door ID.
- **Zone entry:** opens every lock that is a member of that zone (e.g.
  "Ward 3", "Maintenance", "All exterior doors"). A new lock added to a zone
  works immediately for all cards carrying the zone — no card update needed.
- **Time profiles** (e.g. "Mon–Fri 07:00–19:00") are defined in the lock and
  delivered by admin card; the card only references them by number. Profile
  definitions and the site time zone: [`time-profiles.md`](time-profiles.md).
  Firmware that does not know a profile treats the entry as **not matching**
  (fail closed).

Address space: 65 535 doors and 65 535 zones. The card size depends only on how
many rights one person has, not on how big the site is.

## Lock-side data (for reference)

Not stored on the card, set during commissioning / by admin card:
`site_aid`, `door_id` (16-bit), the list of `zone_id`s the lock belongs to
(up to 16), time-profile definitions, blacklist.

## Multiple sites on one card

One card can carry the applications of several independent sites — e.g. your
home, the hospital you work at, the EMS station you volunteer for and your
workshop:

```
DESFire card
├── App 4F4331  test site (bench)       own keys
├── App 3A7C19  home                    own keys (you)
├── App 91E2B0  hospital                own keys (hospital IT)
├── App 4D0866  EMS station             own keys (EMS admin)
└── App C61572  workshop                own keys (you)
```

- **Independent:** each site's admins hold only their own issuer and read
  keys. A site cannot read or change another site's application — DESFire
  enforces this per application.
- **Locks see only their site:** a lock is commissioned with its `site_aid`
  and selects only that application.
- **Within one site,** buildings, wards and departments are **zones** in the
  site's single application — not separate applications.
- **Capacity:** DESFire EV1 holds up to 28 applications; one OpenCylinder
  application with the default access list needs a few hundred bytes, so a 4K
  card holds well over ten sites.
- **Other systems** (canteen, time recording, …) can share the card as well.

### Who owns the card (card master key)

The holder of the **card master key** cannot read any site's data, but can
**delete applications or format the whole card**, take the card over by
changing the master key, fill its memory, and change **irreversible** card
settings (e.g. switch on random UID). A card left with the **factory default
master key is therefore not acceptable for real use** — anyone with a
Proxmark or a phone app could do all of the above.

The card owner (the cardholder, or the issuing organisation) keeps **one
master secret** and derives a **per-card master key** from it (NXP AN10922,
input: real card UID). A key extracted from one card is useless for all others;
the encoder can always recompute it. For other sites to add their
application, the card must allow it:

| Card | Mechanism | Trade-off |
|------|-----------|-----------|
| DESFire EV1 | card master key setting "create application without master key" | simple, but anyone can then create applications (memory-filling DoS — no access) |
| DESFire EV2 / EV3 | **Delegated Application Management (DAM)**: the card owner authorises each site to create one application, with a memory quota | clean multi-site model; nobody else can create applications |

**Recommendation:** DESFire **EV2/EV3 with DAM** for cards that carry several
sites; EV1 for development and single-site use.

### DAM in practice (implemented in the examples, verified on a DESFire EV3)

1. **Card owner, once per card:** set the three DAM keys at card level —
   `0x10` auth, `0x11` MAC, `0x12` ENC (2TDEA), authenticated with the card
   master key. A factory-fresh EV3 has **no usable DAM keys**; `formatpicc`
   deletes applications but **keeps** the DAM keys.
2. **Card owner, per site — the grant:** for one AID, DAM slot and quota
   (blocks of 32 bytes) the owner computes
   `part1 = AID(3, LE) | slot(2, LE) | slot version | quota(2, LE) | KS1 | KS2`,
   `EncK = 2TDEA-CBC(DAM ENC key, IV 0, 7 random | initial app key(16) | key version | 0-pad to 32)`,
   `DAMMAC = CMAC(DAM MAC key, 0xC9 | part1 | EncK)` and hands
   `part1, EncK, DAMMAC` plus the DAM auth key to the site. The DAM MAC and
   ENC keys never leave the owner.
3. **Site:** authenticates with the DAM auth key, sends
   `CreateDelegatedApplication` (`0xC9 part1`, then `0xAF EncK | DAMMAC`) and
   immediately replaces the initial app key with its **own** keys (issuer,
   read, UID key as in [Application](#application)). The card verifies the
   DAMMAC: the site can create only that AID, in that slot, within that
   quota. One OpenCylinder application needs 10 blocks (application 5, files
   5); the examples grant 16.
4. **Locks need nothing new:** a lock selects its own site AID and never sees
   how an application was created.

Bench note: the Proxmark3 `hf mfdes createdelegateapp` computes the grant
itself from the DAM MAC/ENC keys, i.e. it plays owner and site at once;
`examples/hospital/dam.py` is the owner's computation alone (verified to give
the same DAMMAC as the Proxmark, which the card accepted).

### Privacy

- If the application list is readable without authentication, any reader can
  see which sites a card belongs to. The card owner can require the card
  master key for listing (trade-off: tools must then know which AID to try).
- The fixed 7-byte UID makes a card trackable. DESFire EV1 and later support a
  **random UID**, which this format supports via key 2 (see
  [Getting the real UID](#getting-the-real-uid-fixed-or-random-uid)).
  A random-UID card must carry **at least one application whose UID key the
  card owner knows** — otherwise even the owner cannot recover the real UID
  and so cannot derive the card master key.

## How a cylinder decides (pseudocode)

```
select application SITE_AID
uid = real UID   (random-UID card: via key 2 + GetCardUID, see above)
if not authenticateAes(key 1, diversify(SITE_READ_KEY, uid, aid)): reject  # wrong/cloned card
read file 0 (16 bytes, full mode)
if format_version != SUPPORTED_FORMAT_VERSION:  reject   # unknown layout: never guess
if entry_count > MAX_ENTRIES:                   reject   # malformed
if valid_until != 0 and time_unknown:           reject   # can't check expiry: fail safe
if valid_until != 0 and now > valid_until:      reject   # expired
if credential_id in local_blacklist:            reject   # revoked
read file 1 (entry_count * 4 bytes, full mode)
for each entry:
    matches_target = (type == DOOR and target_id == THIS_DOOR_ID)
                  or (type == ZONE and target_id in THIS_LOCK_ZONES)
    if matches_target and profile_allows(time_profile, now):
        accept -> engage clutch
reject                                                  # no matching entry
```

`profile_allows(0, now)` is always true. For any other profile it requires a
known time and a known profile definition.

## Versioning rules

- Changing the meaning, size or position of any field → **new
  `format_version`**, and this document gets a section for the new layout.
- Firmware states the format versions it supports (`kCardFormatVersion` in
  `firmware/include/version.h`) and **denies** any other version — for a lock,
  failing closed is the only safe default.
- A migration path (firmware accepting both N and N+1 during a card re-issue)
  must be explicit and documented, never implicit.

## Security notes

- **Why not UID-only:** the card must *prove* it holds the (diversified) site
  read key without ever sending it. A copied UID, or a "magic" card faking the
  UID, cannot pass `authenticateAes`.
- **Key separation:** a lock compromised in the field leaks at most the read
  key — it cannot be used to rewrite genuine cards (that needs the issuer key).
- **Known limit:** with symmetric keys, someone who extracts the master site
  read key *from a lock* could build a forged card. Mitigations: hardware key
  storage in the lock (`docs/lifecycle-and-security.md`), per-card
  diversification. A later format may add an issuer **signature** over the
  record (asymmetric: locks hold only a public key) to close this completely.

## Personalisation

Done at the encoder (desktop reader + management tool), never at the lock:

1. **Random UID must still be off** — the real UID is visible.
2. Card owner: authenticate to the card master key and replace the factory
   key with the **per-card master key** derived from the owner's master
   secret; forbid create/delete without it (EV1) or set up DAM (EV2/EV3).
   (Skipped by a site that adds its application to a card owned by someone
   else — it then uses free create or its DAM permission.)
3. Check the card's application list for a collision with the site AID,
   then create the site application with **3 AES keys**: key 0 (issuer) and
   key 1 (site read) diversified, key 2 (UID key) site-wide.
4. Create file 0 (16 bytes) and file 1 (default 128 bytes), communication mode
   full, access rights as above (key 2 has no file rights).
5. Write the header (`format_version = 1`, `issued_at = now`) and the access
   list.
6. Verify with the Proxmark3.
7. *Optional, irreversible:* switch on random UID — only after steps 1–6, and
   only if the owner's own application (with a known UID key) is on the card.
   The encoder must require an explicit confirmation.

No NDA, no vendor tool.
