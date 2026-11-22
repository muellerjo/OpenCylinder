#!/usr/bin/env python3
"""Show UID, chip family and (for DESFire) the applications on each card."""

import argparse
import time

from twn4 import TWN4, TWN4Error

# Rough chip family from SAK (NXP AN10833). Good enough for a first look;
# the Proxmark3 ("hf 14a info") identifies chips much more precisely.
SAK_FAMILY = {
    0x00: "MIFARE Ultralight / NTAG",
    0x08: "MIFARE Classic 1K (or Plus SL1)",
    0x09: "MIFARE Mini",
    0x10: "MIFARE Plus SL2",
    0x11: "MIFARE Plus SL2",
    0x18: "MIFARE Classic 4K (or Plus SL1)",
    0x20: "ISO14443-4: DESFire / Plus SL3 / smartcard",
    0x28: "MIFARE Classic 1K emulation + ISO14443-4",
    0x38: "MIFARE Classic 4K emulation + ISO14443-4",
}

# DESFire GetVersion: hardware major version -> generation
DESFIRE_GENERATION = {0x00: "MF3ICD40 (original)", 0x01: "EV1", 0x12: "EV2", 0x33: "EV3"}

MISSES_BEFORE_RESET = 3   # card must be gone this many polls before it counts as removed


def describe_card(reader, uid):
    lines = [f"UID   {uid.hex().upper()}  ({len(uid)} bytes)"]

    sak = reader.sak()
    atqa = reader.atqa()
    family = SAK_FAMILY.get(sak, "unknown")
    lines.append(f"SAK   {sak:02X}   ATQA {atqa.hex().upper() if atqa else '-'}   -> {family}")

    if sak is not None and sak & 0x20:          # ISO14443-4 capable
        ats = reader.ats()
        lines.append(f"ATS   {ats.hex().upper() if ats else '-'}")
        lines.append(f"Chip  {format_desfire_version(reader)}")
        lines.append(f"Apps  {format_apps(reader)}")
    elif sak == 0x00:                           # Ultralight / NTAG
        lines.append(format_ultralight_dump(reader))

    return "\n".join(lines)


def format_desfire_version(reader):
    """Decode the TWN4's 34-byte GetVersion block.

    Layout (TWN4 widens the storage field to a UInt32 in bytes):
      0..9   hardware: vendor, type, subtype, major, minor, storage(4, LE), protocol
      10..19 software: same layout
      20..26 UID, 27..31 batch number, 32 production week, 33 year (both BCD)
    """
    v = reader.desfire_version()
    if v is None or len(v) < 34:
        return "GetVersion failed (not a DESFire, or a DESFire-like chip)"

    vendor, hw_major = v[0], v[3]
    storage = int.from_bytes(v[5:9], "little")
    sw_major, sw_minor = v[13], v[14]
    week, year = v[32], v[33]

    gen = DESFIRE_GENERATION.get(hw_major, f"unknown (hw major 0x{hw_major:02X})")
    maker = "NXP" if vendor == 0x04 else f"vendor 0x{vendor:02X}"
    return (f"DESFire {gen}, {storage // 1024} KB, {maker}, "
            f"software {sw_major}.{sw_minor}, produced week {week:X}/20{year:02X}")


def format_ultralight_dump(reader, pages=16):
    """Hex + ASCII dump of the first pages (user data / NDEF starts at page 4)."""
    rows = []
    for page in range(0, pages, 4):
        data = reader.ultralight_read(page)
        if data is None:
            rows.append(f"  page {page:02d}: read failed (protected or end of memory)")
            break
        for i in range(4):
            chunk = data[4 * i:4 * i + 4]
            text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            rows.append(f"  page {page + i:02d}: {chunk.hex(' ').upper()}  {text}")
    return "Data\n" + "\n".join(rows)


def format_apps(reader):
    try:
        aids = reader.desfire_app_ids()
    except TWN4Error as e:
        return f"error ({e})"
    if aids is None:
        return "not readable (not DESFire, or listing needs a key)"
    if not aids:
        return "none"
    return ", ".join(f"{aid:06X}" for aid in aids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--interval", type=float, default=0.3, help="poll interval in s")
    args = parser.parse_args()

    reader = TWN4(args.port)
    print("Reader:", reader.version())
    print("Hold a card to the reader (Ctrl+C to quit)\n")

    current_uid, misses = None, 0
    while True:
        tag = reader.search_tag()
        if tag:
            _tag_type, uid = tag
            misses = 0
            if uid != current_uid:
                current_uid = uid
                print(describe_card(reader, uid), "\n")
        else:
            misses += 1
            if misses >= MISSES_BEFORE_RESET:
                current_uid = None
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
