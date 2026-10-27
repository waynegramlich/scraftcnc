# 2 Document a Shop

Describe a shop well enough that `solidcraftcnc` can plan a part for
it: which machines can make the part, how it is held, what stock it
starts from, which tools cut it, and at what feeds and speeds.  This
is the top level task; each section below is expected to become a
sub-task.

## Goals

* One shop description, kept in files (TOML today) that people can
  read and edit, with a unit on every number (as `machine.toml`
  already insists), so metric and imperial values never get mixed up.
* A program can load it, check it (every problem reported with the
  file and the entry) and ask it questions: "which drill is the
  largest one smaller than this end mill?", "does this part fit in
  that vise?", "what RPM and feed for this bit in 6061 aluminum?".
* More than one shop (a home shop, a maker space), each with more than
  one machine.  A design should not change when it moves to another
  shop; only the G-code does.
* Built from what was learned in `../Fab/` (see `Context.md`), without
  FreeCAD's tool file formats.

## Sections (Future Sub-Tasks)

1. **Shop and location**: name, where it is (as much or as little as
   the owner wants), units it prefers.
2. **Machines**: a CNC mill first (router, lathe, laser and 3D printer
   later).  Per axis: letter, travel, maximum feed, acceleration,
   limit switches.  Spindle: taper (e.g. R8), RPM range, reversible,
   coolant (flood, mist, air).  Controller: name, which G-code dialect
   (the post processor), canned cycles it supports, how a tool change
   is written (`tool_change` today), tool length offsets.  Table:
   size, T-slots.
3. **Work holding**: vises (jaw width, opening, height), parallels,
   tooling plates (size, grid of screw holes, thread), hold downs and
   clamps (where they sit, how tall they are, so `z_safe` and tab
   placement can be checked).  Ties in with `T.cuwp~1` #23 (tooling
   holes and tabs).
4. **Stock**: materials on hand and the standard sizes and thicknesses
   they come in, plus a minimum cut around the outside, so the stock
   for a part can be chosen (Fab's `FabStock.enclose()`).
5. **Tool library**: every bit owned, described by family (flat,
   ball nose, bull nose, chamfer/V-bit, drill, corner rounding,
   dovetail, roughing, ...) with its dimensions: cutting diameter,
   flutes, length of cut, overall length, shank diameter, center
   cutting, coating, material (HSS, carbide).  Each bit's profile can
   be revolved into a 3D model (`T.cuwp~1` #25).  Real bits come from
   catalogs such as the Shars catalog.
6. **Tool changer / tool table per machine**: which bit is in which
   pocket (T number), with its holder and stick out (gauge length).
   Separate from the library, so one bit can move between machines
   (`T.cuwp~1` #26).
7. **Materials and cutting data**: per material (e.g. 6061 aluminum,
   mild steel, brass, acrylic, wood) the surface speed and chip load
   per tool material and diameter; RPM = surface speed / (pi x
   diameter), feed = RPM x flutes x chip load, limited by the
   spindle and axes.  Per tool overrides (`T.cuwp~1` #28).
8. **Preferences**: what `machine.toml` holds now that is not a
   machine fact (clearance, stepover, ramp angle, drilling style,
   through cut overcut), and where it belongs (shop, machine or job).

## Not in This Task

* Choosing machines, tools and setups for a given part (planning);
  this task only describes what is available.
* Multi-setup parts (Fab's mounts); later.

## Done When

* The sections above exist as sub-tasks, each closed or deliberately
  deferred.
* `machine.toml` is replaced (or split) by the new shop files, and the
  demo runs from them.
