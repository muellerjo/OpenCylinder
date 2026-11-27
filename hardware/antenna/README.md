# Knob antenna

13.56 MHz spiral coil for the ST25R3916 on a Ø 28 mm antenna PCB in the
outer knob — concept in [`../knob-electronics.md`](../knob-electronics.md).

```
python3 gen_coil.py --sweep                      # inductance table
python3 gen_coil.py --out Coil_NFC_D24mm_5T.kicad_mod   # default: Ø24 mm, 5 turns, ~1.0 µH
```

`Coil_NFC_D24mm_5T.kicad_mod` is generated, **not yet checked in KiCad** —
open it in the footprint editor and run DRC before ordering. Inductance is an
air-core estimate (modified Wheeler); measure L and Q with a VNA on the real
board, in the knob, with the ferrite sheet.
