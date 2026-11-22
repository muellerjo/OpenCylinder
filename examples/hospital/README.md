# Example: a fictional hospital

A small, made-up site that shows how the OpenCylinder card format
([`spec/card-format.md`](../../spec/card-format.md), format v1) models a real
building: **doors**, **zones**, **time profiles**, **roles** and **users**.
All names are invented. The site uses the reserved test-site AID `4F4331` and
is not a real configuration.

```
python3 check_access.py                          # who opens what, right now
python3 check_access.py --at "2026-11-24 03:00"  # ... at 3 a.m. (site-local time)
python3 check_access.py --door 4                 # explain every decision at one door
python3 check_access.py --card 2001              # the actual card bytes of one user
python3 check_access.py --time-unknown           # a lock that lost its clock
```

Standard-library Python 3.9+, no installation. Edit [`site.json`](site.json)
and run it again.

## The structure in four ideas

**1. Locks know where they are; cards know who may go where.**
A lock stores only its own door ID and the zones it belongs to. A card stores
a short list of *door* or *zone* entries. The lock opens if one entry matches.

**2. Zones group doors.** A door can be in several zones:

| Door | | Zones |
|---:|---|---|
| 1 | Main entrance | Entrances |
| 2 | Emergency room entrance | Emergency department |
| 3 | Canteen | Staff areas |
| 4 | Ward 1 – ward door | All wards, Ward 1 |
| 5 | Ward 1 – medication room | Ward 1, Medication rooms |
| 6 | Ward 2 – ward door | All wards, Ward 2 |
| 7 | Ward 2 – medication room | Ward 2, Medication rooms |
| 8 | ICU entrance | Intensive care unit |
| 9 | Pharmacy | Pharmacy |
| 10 | Boiler room | Technical rooms |
| 11 | Server room | — (individual access only) |
| 12 | Changing rooms | Staff areas |
| 13 | Chief physician's office | — (individual access only) |

So "Ward 1" opens the ward door *and* its medication room, while "All wards"
opens every ward door but no medication room. A new lock added to a zone works
at once for every card that carries the zone — no card needs updating.

**3. Roles are templates; users are cards.** A role is a list of entries, a
user gets the entries of their roles plus individual extras:

| Role | Entries on the card |
|---|---|
| Doctor (Arzt/Ärztin) | Entrances, Emergency dept., All wards, ICU, Staff areas, Medication rooms |
| Nurse ward 1 (Pflegekraft) | Entrances, Ward 1, Staff areas |
| Caretaker (Hausmeister/in) | Entrances, All wards *(day shift)*, Staff areas, Technical rooms |
| Cleaner (Reinigungskraft) | Entrances, All wards, Staff areas — all *(cleaning shift)* |
| Pharmacist (Apotheker/in) | Entrances, Staff areas, Pharmacy, Medication rooms *(day shift)* |
| IT administrator | Entrances *(office hours)*, Staff areas, door 11 Server room |
| Paramedic, external EMS | door 2 Emergency room entrance only |

Roles exist only in the management data — the card carries the resolved
entries (Sara, nurse ward 1, has 3 entries = 12 bytes).

**4. Time profiles restrict an entry, not a card.** The card stores only a
profile number per entry (`0` = always); the lock holds the definitions:

| Profile | Name | When (site-local time) |
|---:|---|---|
| 1 | Day shift | daily 06:00–20:00 |
| 2 | Cleaning shift | Mon–Sat 05:00–11:00 |
| 3 | Office hours | Mon–Fri 07:00–18:00 |

## What the example demonstrates

At **10:00 on a Tuesday** almost everyone can work normally. At **03:00** the
same cards behave differently:

```
                   1  2  3  4  5  6  7  8  9 10 11 12 13
Dr. Lena Koch      ✓  ✓  ✓  ✓  ✓  ✓  ✓  ✓  ·  ·  ·  ✓  ✓
Sara Yilmaz        ✓  ·  ✓  ✓  ✓  ·  ·  ·  ·  ·  ·  ✓  ·
Eva Brandt         B  B  B  B  B  B  B  B  B  B  B  B  B
Peter Lang         ✓  ·  ✓  t  ·  t  ·  ·  ·  ✓  ·  ✓  ·
Olga Novak         t  ·  t  t  ·  t  ·  ·  ·  ·  ·  t  ·
Ben Fischer        E  E  E  E  E  E  E  E  E  E  E  E  E
EMS crew North     ·  ✓  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·

✓ open   · no right   t not at this time   E expired   B blacklisted   ? time unknown
```

- **Dr. Koch** (chief physician) has the doctor role plus her office as an
  individual door entry (13).
- **Eva Brandt** reported her card lost: her credential is on the blacklist.
- **Peter Lang** (caretaker) keeps the boiler room at night, but the wards only
  during the day shift.
- **Olga Novak** (cleaner) works only in the cleaning shift.
- **Ben Fischer**'s contract ended: his card expired by itself — no blacklist
  entry needed. Short `valid_until` is the cheapest revocation.
- **EMS crew North** belongs to an external organisation: the hospital gives it
  exactly one door. Their own EMS station can keep its *own* site application
  on the same card ([multiple sites](../../spec/card-format.md#multiple-sites-on-one-card)).

With `--time-unknown` (e.g. after a battery change without RTC backup), cards
**with** an expiry date and entries **with** a time profile are refused;
permanent rights still work — the fail-safe rule from
[`docs/lifecycle-and-security.md`](../../docs/lifecycle-and-security.md) §2.5.

## On the bench

The Phase 2 bench lock plays **door 4 (Ward 1 – ward door, zones 3 and 4)**.
A dev card written with Sara's record opens it; Max's (ward 2) does not.

Write a user onto a **DESFire dev card** (factory-default card master key)
with a Proxmark3 — application `4F4331` with 3 AES keys, both files, the
user's record, then read-back and key-separation checks:

```
python3 write_test_card.py --dry-run     # show the Proxmark commands only
python3 write_test_card.py               # Sara (2001); asks before formatting the card
python3 write_test_card.py --user 2002   # Max
```

Uses the public dev test **master** keys (issuer `0F0E…0100`, read
`0011…EEFF`, UID `A0A1…AEAF`). Issuer and read key are **diversified per
card** (NXP AN10922, [`an10922.py`](an10922.py), M = UID ‖ AID); the script
verifies this with the Proxmark's own `--kdf AN10922`. Needs the Python
`cryptography` package.

## Admin card (maintenance bundle)

Put the site's **admin application** (`4F4341`) with a **signed maintenance
bundle** onto a DESFire card ([`spec/admin-card.md`](../../spec/admin-card.md)):
time, blacklist, time profiles and time-zone rule, signed with the public dev
key [`dev_management_key.pem`](dev_management_key.pem) (bench only). A lock that
finds the admin application applies the bundle and never opens.

```
python3 write_admin_card.py                          # full bundle from site.json
python3 write_admin_card.py --blacklist-add 2001     # blacklist Sara
python3 write_admin_card.py --blacklist-remove 2001  # and back
python3 write_admin_card.py --tamper                 # manipulated -> lock: bad signature
python3 write_admin_card.py --sequence 5             # old sequence -> lock: stale
python3 write_admin_card.py --remove                 # delete the admin application
```

The script reuses an existing admin application and only rewrites its files:
**DESFire does not free memory when an application is deleted** — only
`hf mfdes formatpicc` does. Recreating it on every run fills a 4K card after a
few runs (`--recreate` forces it anyway).

## Identify card

A card with the identify application (`4F4349`, one free-access file) makes
any lock write its public identity onto it — state, device ID, public key,
firmware version, site and door. Use a separate card (an identify card never
opens a door).

```
python3 write_identify_card.py                      # set up / clear
python3 write_identify_card.py --read               # after tapping a lock
python3 write_identify_card.py --read --qr "OC1:…"  # compare with the engraved QR
```

## Commissioning card

Commission a **FACTORY** lock for one door: the bundle is encrypted to that
lock's public key (from its QR text — banner, engraving or identify card) and
signed; it also carries the site's profiles, TZ and blacklist.

```
python3 write_commissioning_card.py --qr "OC1:<device ID>:<public key>" --door 4
```

The lock is recorded in the git-ignored site database `locks.local.json`.

## Not covered (yet)

- Time profiles here are written informally (`days`, `from`, `to`); the
  on-lock format and the site time-zone rule are in
  [`spec/time-profiles.md`](../../spec/time-profiles.md). How they reach the
  lock (admin card) is a draft: [`spec/admin-card.md`](../../spec/admin-card.md).
- Authentication and key diversification are assumed to have succeeded; this
  example is about the *data*, not the crypto.
