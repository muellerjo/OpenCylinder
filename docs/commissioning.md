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
A blank lock must accept its first owner, and the site keys it receives must
be readable by **that lock only**. So (details: [`spec/admin-card.md`](../spec/admin-card.md) §5):
- Every lock has its own **device key pair**, created once by the lock
  itself. The private key never leaves the lock; the **public key is not
  secret** and is engraved as a QR code on the electronics module.
- The commissioning card carries the site keys **encrypted to that lock's
  public key** and **signed** by the site. A stolen commissioning card is
  useless; on any other lock it does nothing.
- Once OWNED, the lock only changes owner via a **signed, targeted
  decommission** from its site, or a **physical reset** (internal reset pads,
  only reachable with the cylinder removed — see `lifecycle-and-security.md`
  §2.6). A reset returns the lock to blank — it **opens nothing** until
  re-commissioned. Reset is denial, never entry.
- Anyone may commission a lock that *is* blank — by design (lost keys,
  second-hand locks). What protects a lock is that getting it back to blank
  needs the owner's signature or the door open and the cylinder removed.

In the picture: each lock has its own mailbox. Anyone can drop a letter in,
only the lock can open it. The commissioning card is a sealed letter for one
mailbox; the decommission card is a note signed by the owner saying "forget
me".

## Commission a new cylinder (blank -> owned)
1. Scan the lock's **QR code** (device ID + public key) — or tap an
   **identify card** if there is no QR.
2. In your tool, define the door: assign a unique **door ID** and the
   **zones** it belongs to.
3. The tool writes a **commissioning card** for exactly this lock: site read
   key, UID key, admin read key, the site's signature public key, door ID,
   zones — encrypted to the lock, signed by the site. (Never the issuer key,
   which stays in the encoder.)
4. Tap it on the blank cylinder: the lock decrypts, checks the signature,
   stores everything → OWNED. It takes its time from the bundle.
5. Verify: tap an authorised user card -> it opens.

## Lock without paperwork
Tap an **identify card**: the lock writes its device ID, public key, state
and door onto it. Then decommission / re-commission, or just reassign door
and zones with a targeted maintenance bundle (no decommission needed).

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
