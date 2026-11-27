#!/usr/bin/env python3
"""Parametric 13.56 MHz spiral coil for the knob antenna PCB (ST25R3916).

Estimates the inductance (modified Wheeler formula, circular spiral — Mohan
et al., 1999) and writes a KiCad footprint (.kicad_mod): an Archimedean
spiral on F.Cu from the outer pad inwards, plus a crossover on B.Cu from the
inner end back to a second pad outside the coil.

  python3 gen_coil.py                          # defaults: Ø24 mm, 5 turns, 0.3/0.3 mm
  python3 gen_coil.py --outer 24 --turns 5 --width 0.3 --gap 0.3 --out coil.kicad_mod
  python3 gen_coil.py --sweep                  # inductance table for some variants

Estimates only: the real inductance and Q are measured with a VNA on the
finished board, in the knob, with the ferrite sheet (which raises L).
Standard library only. The footprint is untested in KiCad yet — open it in
the footprint editor and run DRC before ordering.
"""

import argparse
import math

MU0 = 4e-7 * math.pi
F = 13.56e6


def wheeler_circular_uh(d_out_mm, turns, width_mm, gap_mm):
    pitch = width_mm + gap_mm
    d_in = d_out_mm - 2 * turns * pitch + 2 * gap_mm  # track centre to centre approx.
    if d_in <= 0:
        raise ValueError("coil does not fit: inner diameter <= 0")
    d_avg = (d_out_mm + d_in) / 2 / 1000
    rho = (d_out_mm - d_in) / (d_out_mm + d_in)
    c1, c2, c3, c4 = 1.00, 2.46, 0.00, 0.20  # circular spiral
    L = MU0 * turns ** 2 * d_avg * c1 / 2 * (math.log(c2 / rho) + c3 * rho + c4 * rho ** 2)
    return L * 1e6, d_in


def resonance_pf(l_uh):
    return 1 / ((2 * math.pi * F) ** 2 * l_uh * 1e-6) * 1e12


def footprint(name, d_out, turns, width, gap, seg_deg=5.0):
    pitch = width + gap
    r_out = d_out / 2 - width / 2
    lines = []
    pts = []
    # End 30 degrees short of the last full turn, so the crossover (radial, on
    # B.Cu) and pad 2 land away from pad 1 at angle 0.
    end_deg = turns * 360 - 30
    steps = int(end_deg / seg_deg)
    for i in range(steps + 1):
        theta = math.radians(i * seg_deg)
        r = r_out - pitch * theta / (2 * math.pi)
        pts.append((r * math.cos(theta), -r * math.sin(theta)))
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        lines.append(f'  (fp_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f}) '
                     f'(stroke (width {width}) (type solid)) (layer "F.Cu"))')
    (xs, ys), (xe, ye) = pts[0], pts[-1]
    # Crossover on B.Cu from the inner end radially outwards, past the outer edge.
    phi = math.radians(steps * seg_deg)
    r_pad = r_out + 1.0
    xo, yo = r_pad * math.cos(phi), -r_pad * math.sin(phi)
    lines.append(f'  (fp_line (start {xe:.4f} {ye:.4f}) (end {xo:.4f} {yo:.4f}) '
                 f'(stroke (width {width}) (type solid)) (layer "B.Cu"))')
    drill, pad = 0.3, 0.6
    pads = [
        f'  (pad "1" thru_hole circle (at {xs + 1.0:.4f} {ys:.4f}) (size {pad} {pad}) (drill {drill}) '
        f'(layers "*.Cu" "*.Mask"))',
        f'  (pad "2" thru_hole circle (at {xo:.4f} {yo:.4f}) (size {pad} {pad}) (drill {drill}) '
        f'(layers "*.Cu" "*.Mask"))',
        # via at the inner end of the spiral (F.Cu -> B.Cu)
        f'  (pad "2" thru_hole circle (at {xe:.4f} {ye:.4f}) (size {pad} {pad}) (drill {drill}) '
        f'(layers "*.Cu"))',
    ]
    lines.append(f'  (fp_line (start {xs:.4f} {ys:.4f}) (end {xs + 1.0:.4f} {ys:.4f}) '
                 f'(stroke (width {width}) (type solid)) (layer "F.Cu"))')
    head = (f'(footprint "{name}" (version 20221018) (generator "opencylinder_gen_coil") '
            f'(layer "F.Cu")\n'
            f'  (descr "13.56 MHz spiral coil, outer {d_out} mm, {turns} turns, '
            f'track {width} mm, gap {gap} mm")\n'
            f'  (attr smd)\n'
            f'  (fp_text reference "ANT1" (at 0 {d_out / 2 + 1.5:.2f}) (layer "F.SilkS") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'  (fp_text value "{name}" (at 0 {-(d_out / 2 + 1.5):.2f}) (layer "F.Fab") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'  (fp_circle (center 0 0) (end {d_out / 2 + 0.5:.2f} 0) '
            f'(stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))\n')
    return head + "\n".join(lines + pads) + "\n)\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outer", type=float, default=24.0, help="outer diameter, mm")
    ap.add_argument("--turns", type=int, default=5)
    ap.add_argument("--width", type=float, default=0.3, help="track width, mm")
    ap.add_argument("--gap", type=float, default=0.3, help="track gap, mm")
    ap.add_argument("--out", help="write the KiCad footprint to this file")
    ap.add_argument("--sweep", action="store_true", help="print an inductance table")
    args = ap.parse_args()

    if args.sweep:
        print(" outer  turns  width/gap   inner    L (uH)   C_res (pF)")
        for outer in (22, 24, 26, 28):
            for turns in (3, 4, 5, 6, 7):
                try:
                    l, d_in = wheeler_circular_uh(outer, turns, 0.3, 0.3)
                except ValueError:
                    continue
                print(f"  {outer:4.0f}  {turns:5d}   0.3/0.3   {d_in:5.1f}   {l:6.2f}   {resonance_pf(l):7.0f}")
        return

    l, d_in = wheeler_circular_uh(args.outer, args.turns, args.width, args.gap)
    print(f"Coil: outer {args.outer} mm, inner ~{d_in:.1f} mm, {args.turns} turns, "
          f"{args.width}/{args.gap} mm -> L ~ {l:.2f} uH (air, no ferrite); "
          f"resonance needs ~{resonance_pf(l):.0f} pF at 13.56 MHz")
    if args.out:
        name = f"Coil_NFC_D{args.outer:g}mm_{args.turns}T"
        with open(args.out, "w") as f:
            f.write(footprint(name, args.outer, args.turns, args.width, args.gap))
        print(f"Footprint written to {args.out} ({name})")


if __name__ == "__main__":
    main()
