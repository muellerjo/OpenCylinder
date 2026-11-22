# Commissioning — your own, no vendor in the loop

This replaces the vendor triad (Concept Card + Servicekey + Keyvi/ClexSCT) with
three things you own: your **admin card**, your **management tool**, your
**site key**. See [`lifecycle-and-security.md`](lifecycle-and-security.md) for the trust model; this doc is
the concrete procedure.

## What you need
- **Management tool** (your software) holding the **site key** and **admin key**,
  in a secure store. Runs on your PC — no cloud, no vendor account.
- **Encoder** (desktop reader) to personalise cards and write the admin card.
- Each **blank cylinder** in factory/transport state.

## Lock states
```
FACTORY/TRANSPORT ──commission──► OWNED ──decommission (admin)──► FACTORY/TRANSPORT
                                    │
                                    └─ hard reset (physical) ──► FACTORY (opens nothing)
```

## Bootstrap security — the one thing to get right
A blank lock must accept its first owner, but nobody else must be able to
re-own it. So:
- The blank lock ships with a **transport key** (a known bootstrap secret).
- **First commission:** your tool authenticates with the transport key, injects
  your keys, and **immediately replaces the transport key** so the lock is now
  bound to *your* admin key.
- After that, re-commissioning requires **your admin key**, or a **physical
  reset** (internal reset pads, only reachable with the cylinder removed — see `lifecycle-and-security.md` §2.6) that wipes to factory. A reset
  returns the lock to blank — it **opens nothing** until re-commissioned. Reset
  is denial, never entry.

If you ever buy pre-made secure elements, the transport key is what you change
on first use — treat it like a default password.

## Commission a new cylinder (blank -> owned)
1. In your tool, define the door: assign a unique **door ID** and the
   **zones** it belongs to.
2. Tap the **admin card** (or connect the encoder) to the blank cylinder.
3. The tool, over that channel, writes into the cylinder's secure element:
   - your **site read key** (so it can authenticate your user cards —
     never the issuer key, which stays in the encoder),
   - your **admin key** (so only you can manage it henceforth),
   - the **door ID** and its **zone memberships**,
   - the current **time** (RTC).
4. The transport key is overwritten; the lock is now OWNED.
5. Verify: tap an authorised user card -> it opens. Cross-check with your
   Proxmark that the on-card app authenticates.

## Fit a new lock into an existing card population
Because this is data-on-card (your own format, [`spec/card-format.md`](../spec/card-format.md)):
- **Usual case — zones:** commission the new lock into the zones it belongs
  to (e.g. "Ward 3"). Every card that carries a zone entry for "Ward 3" opens
  it immediately — **no card update needed**.
- **Individual access:** for people who should open only this door, add a
  **door entry** with the new door ID to their access list at the encoder (or
  via an admin-card-carried update). Until updated, their card won't open it.
- Trade-off: broad zones mean fewer card updates, but a lost card opens more.
  Short `valid_until` and the blacklist limit that risk.

## Decommission / re-key
- **Soft (admin card):** authenticate admin key -> wipe config -> back to
  transport state, ready to re-commission. Authenticated, safe.
- **Hard (admin key lost):** physical reset -> factory. Then re-provision from
  your escrowed site/admin keys. This is why escrow matters: it makes the hard
  path rare and keeps the vendor permanently out of your recovery.

## Why no product does this for you
The injection step (3) is exactly what commercial vendors keep closed: it puts a
key into a secure element, and exposing that interface would break the
tamper-resistance they sell and remove their business hold. Owning step (3) — and
the transport-key handling in bootstrap — is the whole reason OpenCylinder has to
be self-built. It is also the part to treat most carefully: the transport-key
discipline is your commissioning security.
