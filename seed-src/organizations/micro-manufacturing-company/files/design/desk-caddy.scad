// Original Stackline desk-only design study. SYNTHETIC planning inputs.
// No toolpaths, process settings, material qualification, or fabrication claim.
part = "assembly";
width = 180;
depth = 100;
height = 32;
wall = 3;
floor = 3;
clearance = 1.5;
insert_height = 20;
rib = 2;

assert(width > 2*wall + 2*clearance + 6*rib && width <= 400);
assert(depth > 2*wall + 2*clearance + 2*rib && depth <= 300);
assert(wall >= 2 && floor >= 2 && clearance >= 0.5);
assert(height > floor && height <= 100);
assert(insert_height > 0 && insert_height <= height-floor && rib >= 1);
assert(part == "assembly" || part == "tray" || part == "insert");

iw = width - 2*wall - 2*clearance;
id = depth - 2*wall - 2*clearance;

module tray() {
    difference() {
        cube([width, depth, height]);
        translate([wall, wall, floor])
            cube([width-2*wall, depth-2*wall, height]);
    }
}

module insert() {
    union() {
        cube([iw, rib, insert_height]);
        translate([0, id-rib, 0]) cube([iw, rib, insert_height]);
        for (fraction = [1/3, 2/3])
            translate([iw*fraction-rib/2, rib, 0])
                cube([rib, id-2*rib, insert_height]);
    }
}

if (part == "tray") tray();
if (part == "insert") insert();
if (part == "assembly") {
    color([0.75, 0.79, 0.80]) tray();
    color([0.23, 0.49, 0.48])
        translate([wall+clearance, wall+clearance, floor]) insert();
}
