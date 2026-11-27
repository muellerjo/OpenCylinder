// OpenCylinder — outer knob mock-up (option A: all electronics in the knob).
// Parametric, printable. Checks the stack-up of hardware/knob-electronics.md
// and later carries the antenna test boards for range tests.
//
//   openscad -o shell.stl -D 'part="shell"' knob_mockup.scad
//   openscad -o cap.stl   -D 'part="cap"'   knob_mockup.scad
//   openscad -o spacer.stl -D 'part="spacer"' knob_mockup.scad
//   openscad                                knob_mockup.scad   (preview: assembly / cutaway)
//
// z = 0 is the outer face (cap), z grows towards the cylinder body.
// Preview checked in OpenSCAD; not printed yet.

part = "cutaway";        // "assembly", "cutaway", "shell", "cap", "spacer"

$fn = 96;

// --- knob ------------------------------------------------------------------
knob_d     = 34;
knob_l     = 42;
wall       = 2;
inner_d    = knob_d - 2 * wall;      // 30
cap_t      = 2.5;                    // plastic / translucent, never metal
cap_lip    = 1.0;                    // ledge the cap sits on

// --- boards & ferrite ------------------------------------------------------
board_d    = 28;
ant_t      = 0.8;                    // antenna PCB
ferrite_t  = 0.3;
main_t     = 1.0;                    // main PCB
main_env   = 3.4;                    // main PCB + components both sides (envelope)
coil_d     = 24;                     // antenna coil outer diameter (drawn on the board)

// --- battery CR2 + motor beside it ------------------------------------------
bat_d      = 15.6;
bat_l      = 27;
bat_contact = 1.8;                   // spring + flat contact (CR2 holder)
bat_off    = 5.5;                    // battery off-centre (+y)
mot_d      = 6;                      // micro gear motor
mot_l      = 20;
mot_off    = 10;                     // motor on the other side (-y)

// --- clutch zone + shaft ----------------------------------------------------
clutch_l   = 4;
clutch_d   = 14;
rear_t     = knob_l - (cap_t + ant_t + ferrite_t + main_env + bat_contact + bat_l + clutch_l);
shaft_d    = 8;

// z positions
z_ant      = cap_t;
z_ferrite  = z_ant + ant_t;
z_main     = z_ferrite + ferrite_t;
z_bat      = z_main + main_env;
z_clutch   = z_bat + bat_contact + bat_l;
z_rear     = z_clutch + clutch_l;
z_pcb_back = z_main + (main_env + main_t) / 2;  // rear face of the main PCB
spacer_h   = (main_env - main_t) / 2;           // main PCB front face -> ferrite
tab_r      = board_d / 2 - 1;                   // tabs reach in to r = 13 mm

echo(str("rear wall thickness = ", rear_t, " mm (should be >= 1.5)"));
assert(rear_t >= 1.5, "stack-up does not fit into knob_l");
assert(bat_off + bat_d / 2 <= inner_d / 2, "battery hits the knob wall");
// battery and motor are inserted from the front past the tabs (0/120/240 deg)
function reach(off, d, a) = off * sin(a) + d / 2;   // radial extent towards angle a
assert(max([for (a = [0, 120, 240]) reach(bat_off, bat_d, a)]) < tab_r, "battery hits the tabs");
assert(max([for (a = [0, 120, 240]) reach(-mot_off, mot_d, a)]) < tab_r, "motor hits the tabs");
assert(mot_off + mot_d / 2 <= inner_d / 2, "motor hits the knob wall");
assert(bat_off + mot_off >= bat_d / 2 + mot_d / 2 + 0.5, "battery and motor collide");

module shell() {
    difference() {
        cylinder(d = knob_d, h = knob_l);
        // main cavity from the front, down to the rear wall
        translate([0, 0, cap_t]) cylinder(d = inner_d, h = z_rear - cap_t);
        // cap recess
        translate([0, 0, -0.01]) cylinder(d = inner_d + 2 * cap_lip, h = cap_t + 0.02);
        // shaft hole through the rear wall
        translate([0, 0, z_rear - 0.01]) cylinder(d = shaft_d + 0.4, h = rear_t + 0.02);
        // grip flutes
        for (a = [0 : 30 : 359])
            rotate([0, 0, a]) translate([knob_d / 2 + 0.6, 0, 6])
                cylinder(d = 3, h = knob_l - 10);
    }
    // Three tabs just behind the main PCB; it rests on them. Assembly from
    // the front: battery + motor (pass the tabs), main PCB, spacer ring,
    // ferrite, antenna PCB, cap (clamps the stack). Keep main-PCB components
    // out of r > 13 mm (tabs behind, spacer ring in front).
    for (a = [0, 120, 240])
        rotate([0, 0, a]) translate([tab_r, -1.5, z_pcb_back])
            cube([inner_d / 2 - tab_r + 0.01, 3, 0.8]);
}

// Ring between the main PCB and the ferrite / antenna PCB.
module spacer() {
    difference() {
        cylinder(d = inner_d - 0.3, h = spacer_h);
        translate([0, 0, -0.01]) cylinder(d = 2 * tab_r, h = spacer_h + 0.02);
    }
}

module cap() {
    cylinder(d = inner_d + 2 * cap_lip - 0.3, h = cap_t);
}

module internals() {
    color("goldenrod") translate([0, 0, z_ant]) difference() {
        cylinder(d = board_d, h = ant_t);
        translate([0, 0, ant_t - 0.05]) difference() {      // coil outline
            cylinder(d = coil_d, h = 0.1);
            cylinder(d = coil_d - 5.4, h = 0.1);
        }
    }
    color("dimgray") translate([0, 0, z_ferrite]) cylinder(d = board_d, h = ferrite_t);
    color("darkgreen") translate([0, 0, z_main + (main_env - main_t) / 2]) cylinder(d = board_d, h = main_t);
    color([0, 0.6, 0, 0.25]) translate([0, 0, z_main]) cylinder(d = board_d, h = main_env);
    color("white") translate([0, 0, z_main]) spacer();
    color("silver") translate([0, bat_off, z_bat + bat_contact / 2]) cylinder(d = bat_d, h = bat_l);
    color("orange") translate([0, -mot_off, z_bat]) cylinder(d = mot_d, h = mot_l);
    color("steelblue") translate([0, 0, z_clutch]) cylinder(d = clutch_d, h = clutch_l);
    color("lightgray") translate([0, 0, z_rear - 2]) cylinder(d = shaft_d, h = rear_t + 12);
}

if (part == "shell") shell();
else if (part == "spacer") spacer();
else if (part == "cap") cap();
else if (part == "assembly") {
    color([0.8, 0.8, 0.85, 0.35]) shell();
    color([1, 1, 1, 0.5]) cap();
    internals();
} else {  // cutaway
    difference() {
        union() {
            color([0.8, 0.8, 0.85]) shell();
            color("white") cap();
        }
        translate([0, -knob_d, -1]) cube([knob_d, 2 * knob_d, knob_l + 20]);
    }
    internals();
}
