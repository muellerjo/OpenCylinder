# Time profiles and site time zone

**Status: draft v1** — implemented in `firmware/lib/access_decision` and
`examples/hospital/check_access.py`; the delivery to locks (admin card) is
specified separately.

A card's access entry references a time profile by number
([`card-format.md`](card-format.md), file 1, `time_profile`). The lock holds
the profile definitions and the site's time zone; the card never does.

## Rules

- **Profile 0 = always.** It needs no definition and works even when the
  lock's time is unknown.
- Any other profile **needs a known time and a known definition**; otherwise
  the entry does not match (**fail closed**).
- Profiles are evaluated in the site's **local wall time** (people think in
  "Mon–Fri 07:00–18:00"); the lock keeps **UTC** and converts with the site
  time-zone rule, including daylight saving time.

## Profile definition

| Field | Size | Meaning |
|---|---:|---|
| `id` | 1 | 1…255 |
| `days` | 1 | bit 0 = Monday … bit 6 = Sunday; bit 7 reserved (0) |
| `interval[0].from` | 2 | minute of day 0…1439 (little-endian) |
| `interval[0].to` | 2 | minute of day 1…1440, exclusive |
| `interval[1].from` | 2 | second interval, same encoding |
| `interval[1].to` | 2 | `from == to` → interval unused |

10 bytes per profile; a lock holds at least 32 profiles.

- An interval is active on the days in `days`, from `from` (inclusive) to
  `to` (exclusive).
- **Past midnight:** if `from > to` the interval wraps and belongs to the day
  it **starts** on. Example: `days = Mon`, 22:00–06:00 covers Monday 22:00 to
  Tuesday 06:00 — but not Tuesday 22:00.
- Two intervals cover split shifts (e.g. 06:00–10:00 and 16:00–20:00).
- Holidays are not part of v1.

## Site time zone

A **POSIX TZ rule** (the format of the `TZ` environment variable), at most 47
ASCII characters. Supported subset:

```
STD offset [DST [offset] ,Mm.w.d[/time] ,Mm.w.d[/time]]
```

| Site | Rule |
|---|---|
| Germany / Central Europe | `CET-1CEST,M3.5.0,M10.5.0/3` |
| UK | `GMT0BST,M3.5.0/1,M10.5.0` |
| US Eastern | `EST5EDT,M3.2.0,M11.1.0` |
| no DST | `UTC0` |

- Offsets are **west** of UTC, as in POSIX (`CET-1` = UTC+1).
- `Mm.w.d`: month *m*, week *w* (1–5, 5 = last), weekday *d* (0 = Sunday);
  `/time` = local wall time of the switch, default `02:00`.
- Not supported: the `Jn` / `n` day-of-year forms (fail → rule rejected).

Why a rule instead of a time-zone database: it is a few bytes, needs no
updates for decades as long as the country keeps its DST rule, and every
embedded C library understands the format. If a country changes its rules,
an admin card delivers the new rule.

**Verified:** the firmware's conversion matches Python `zoneinfo`
("Europe/Berlin") at the DST switches of 2026, 2027 and 2040, the 2038
boundary, a leap day and new year 2100 (`firmware/test/host`).

## Example (fictional hospital)

| id | Name | days | intervals |
|---:|---|---|---|
| 1 | Day shift | Mon–Sun | 06:00–20:00 |
| 2 | Cleaning shift | Mon–Sat | 05:00–11:00 |
| 3 | Office hours | Mon–Fri | 07:00–18:00 |

Encoded profile 2: `02 3F 2C 01 94 02 00 00 00 00`
(id 2, days 0x3F = Mon–Sat, 300 = 05:00, 660 = 11:00, second interval unused).
