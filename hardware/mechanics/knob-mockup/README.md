# Knob mock-up

Parametric OpenSCAD model of the outer knob (option A in
[`../../knob-electronics.md`](../../knob-electronics.md)): Ø 34 × 42 mm shell,
plastic cap, Ø 28 mm antenna PCB + ferrite + main PCB, CR2 battery off-centre
with a Ø 6 mm micro gear motor beside it, clutch zone and shaft at the rear.

Length budget (z from the cap): cap 2.5 · antenna PCB 0.8 · ferrite 0.3 ·
main PCB envelope 3.4 · battery contacts 1.8 · battery 27 · clutch 4 · rear wall 2.2 = 42 mm.
The model asserts that everything fits (rear wall ≥ 1.5 mm, battery and motor
inside the wall and not colliding, battery and motor clear of the tabs).

Assembly from the front: battery + motor, main PCB (rests on three tabs
behind it), spacer ring, ferrite, antenna PCB, cap (clamps the stack).
Main-PCB components stay inside r = 13 mm (tabs and ring at the rim).

```
sudo apt install openscad
openscad knob_mockup.scad                                    # preview (cutaway)
openscad -o shell.stl -D 'part="shell"' knob_mockup.scad     # print
openscad -o cap.stl   -D 'part="cap"'   knob_mockup.scad
openscad -o spacer.stl -D 'part="spacer"' knob_mockup.scad
```

Preview checked in OpenSCAD (2026-11-27); not printed yet. Uses: verify the stack-up with real parts, hold the antenna
test boards for range tests with the ST25R3916, try battery access options.
