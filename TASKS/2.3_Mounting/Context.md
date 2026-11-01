# LLM Agent Context Log

## 2026-10-30: The Shars catalog as `SharsMD/`

`SharsMD/page_NNN/page_NNN.md` (a link to `../catxtract/SharsMD`, in
neither version control) is a partial conversion of the 2026 catalog,
with each page's pictures beside it as PNG files.

* Pages converted: 1-202, 210, 250, 251, 300, 310-345, 450-456.
* The index is pages 451-455 (the user's "249-255" did not match), with
  links to the pages that exist.
* Work holding pages, from the index:
  * Vises: 310-311 (5-axis, Kurt), 312-313 (quick change jaws), 314
    (aluminum, soft jaws), 316 (Tite-lock, machined jaws), 317-319.
  * Sub plates: 315 (500 x 300 mm plain, 2 in grid of 5/8-11, T-slot).
  * Clamps: 324-329 (cantilever, fixture, ID, low profile, Pitbull,
    compact toe); 330-331 (52 piece kits, T-nuts, flange nuts, studs,
    serrated end clamps, hold-downs, T-slot bolts).
  * Stops: 320-321.  Rotary tables and dividing heads: 333-334.
* Not converted yet: vises 304-309, chuck pages other than 250-251
  (jaws 259-261), jacks 262, V-blocks 407-408, parallels 409-411.
* Conversion traps: thousands commas read as periods (page 328's
  "1.500" is 1,500 lb, "1.300.0" is 1,300.0); page 330's T-nut table
  came out as one line of text.  Lettered dimensions (`A`, `B`, ...)
  are defined only by the pictures (`page_328_8.png`).
* Step block heights are not in page 330's text; not looked for in its
  pictures beyond `page_330_3.png` (the studs).

## 2026-10-31: `Mount`, the first stack

* The user: a mount builds a stack of tools and materials; e.g. Mill,
  Table, Vise, Jaws, Parallels, or Table, sacrificial material, material,
  toe clamps (2 phases).  Each tool has a keep-out.  First stack: Tormach
  770 table, Kurt vise at a 6 in gap, 1.5 in parallels, a 12 x 5.5 in
  aluminum plate, its 12 in along Y (the user's word).
* `mount.py`: `Layer` (a `Protocol`: `name`, `seat()`, `model()`,
  `keep_out()`), `TableLayer`, `ViseLayer`, `ParallelPair`, `Plate`,
  `Mount` (`places()`, `report()`, `model()`, `keep_out()`, `notes`),
  `vise_mount()`, `vise_notes()`, `FIRST_MOUNT`.  `seat()` is an offset,
  not a height, since work centers on the vise's gap, which is off the
  base's center (`Vise.gap_center()`).  The table's top is Z = 0.
* Claude's choices: plate 1/2 in thick (none given); parallels flush with
  the plate's X edges, not against the jaws, since 5.5 in of plate
  centered in a 6 in gap would fall between parallels on the jaws; vise
  centered on the table, screw along X; the jaws stay part of the vise
  layer, not a layer of their own; no Mill layer yet.
* Stack: table -2.362 to 0, vise to 2.640, parallels to 4.140, plate to
  4.640 in.  Notes it prints: not clamped (1/2 in short of the gap), 0.235
  in of grip, top 0.140 in above the jaws' keep-outs, 3 in past the jaws
  and 1.965 in past the table at each Y end.
* Checked: `inspect.interference` finds no overlaps among the 16 bodies
  headless; built in the GUI in about 5 s.  Not seen by Claude; the
  user's eye decides.
* Found, not modeled: the 770's outer slots (Y = +/-50 mm) sit under the
  vise's bottom notches' inner end (Y = +/-54 mm, an estimate), so a hold
  down bolt there would not clear the notch.

## 2026-10-31: The user's own mill: Mikini 1610L, vise along Y

* The user's garage mill; specifications pasted by the user (source not
  given): table 30 x 9.5 in (also 760 x 240 mm; Claude used the inches),
  X travel 16.75, Y travel 9.35 in, three 5/8 in slots with 1 in feet on
  2.50 in centers.  The table runs along X; the vise along Y, as on nearly
  all mills (the user).
* `tools.py`: `MIKINI_1610L` (thickness 2-1/2 in, throat 1/2 in deep, slot 1
  in deep are estimates; slots taken to run the whole length, no pockets),
  `MIKINI_X_TRAVEL`, `MIKINI_Y_TRAVEL`, `Prism.quarter_turned()`.  Not in
  `MILL_TABLES` (Tormach's).
* `mount.py`: `ViseLayer(turned=True)`, hexagon toward -Y (the operator),
  fixed jaw toward +Y (Claude's choice, the usual way).  `solid.move` turns
  about the world origin (checked), so the vise is built there, turned,
  then moved.  `turned_vise_notes()`, `GARAGE_MOUNT`; `mount.py 8080
  [garage|first]`.
* Result with the vise centered, 6 in gap: base 3.125 in past each edge of
  the table (hex 4.125 in); the fixed jaw's end of the gap is 1.475 in out
  of Y reach, if the travel is centered on the table (assumed; the column's
  clearance is not known).  Moving the vise 1.475 in toward -Y brings the
  whole 8.8 in opening into reach (rear 1.65, front 4.6, hex 5.6 in past),
  and by the estimated notches puts the rear notches at Y = 2.525 in, on the
  rear slot, with the front ones off the table.  Not modeled yet.

## 2026-10-31: The Mikini table, as the user measured it

* The user: 30 x 10-1/2 x 1 in high, 5 slots 1 in deep, 11/16 in throat,
  15/16 in foot, each 1/2 in high.  This replaces the pasted specifications'
  table (their travels stay).
* Not settled, the user to measure: the 1 in height can not be the plate's
  with slots 1 in deep (2-1/2 in kept, an estimate); no slot spacing was given
  and 2-1/2 in does not fit (outer feet past the edges), so 2 in, an
  estimate.  `MillTable.__post_init__()` now refuses both.
* Result, vise centered, 6 in gap: base 2.625 in past each edge, hex 3.625
  in; outer slots at Y = +/-4 in lie under the notches at +/-4 in, though
  both are estimates; the gap still reaches 1.475 in past the Y travel.

## 2026-10-31: Tooling plate; two bolts hold a vise

* The user: most vises are held down with 2 bolts only, and the smaller
  Kurts have just 2 holes, so bolt holes need not line up with slots.  The
  `NO SLOT` note is gone from `turned_vise_notes()`; the vise is free to
  move along Y for reach.
* The user: a tooling plate, 5-1/2 x 10-1/2 in, holes on 1/2 in centers
  reaching 1/2 in from all four sides (200 holes), starting with a #6 close
  fit from a chart that did not arrive in the message: 0.144 in (#27 drill)
  is Claude's stand-in, until the chart comes.  Thickness 1/2 in is an
  estimate.
* `tools.py`: `ToolingPlate`, a `Layer` itself, `TOOLING_PLATE`.
  `mount.py`: `PLATE_MOUNT` (Claude's choice: on the Mikini table, 5-1/2 in
  along X, 10-1/2 in across it, as it matches the width).
* Checked: `model.faces` shows all 200 holes where they belong, with the
  exact radius, as two half cylinders each.  SolidCraft's `center_of_mass`
  and face areas read low on them (a wall 90 % of its true area; the cut
  97 % of its true volume, against 99 % for one hole), so hole counts are
  checked by faces, not volume.  The 200 hole cut takes about 3 s headless.

## 2026-10-31: `Setup`, from JSON

* The user: `Setup` gives the location, orientation and height of all of the
  tooling, plus the material(s); a tooling plate can hold several chunks, each
  a different part, for few tool changes.  First: Mikini table, vise, 1-1/2 in
  parallels next to each jaw, a 6 x 10 x 0.5 in chunk as a translucent white
  box, the finished tooling plate inside.  All of it in JSON, fed to
  `Setup.__init__(self, setup_json)`.
* `scsetup.py` (so as not to look like a packaging `setup.py`): `Setup`,
  `Placement`, `PlacedTool`, `PlacedWork`, `_Reader` (every problem at once,
  with its entry; unknown keys refused; units required).
  `examples/setup/tooling_plate.json`.  Everything is placed outright (no
  `on: vise`), as the user asked; `solid.move` turns each item about the origin.
* Claude's choices: the chunk's 10 in along X, since 10 in will not go in the
  vise's 8.8 in opening; so 6 in between the jaws, which clamps it.  Vise at Y
  = -3.15 in, which centers the gap on the table and the Y travel: its base
  stops 0.525 in short of the rear edge (no overhang toward the column) and the
  hexagon is 6.775 in past the front.  Fixed jaw at the rear.
* Not resolved, the user's to decide: the 10-1/2 in plate does not fit the 10 in
  chunk (1/4 in out at each X end); `Setup` reports it, and 11 in in the JSON's
  `size` clears it.  The plate's 5-1/2 in leaves 1/4 in to each jaw, 1/8 in from
  the keep-outs, so its long edges can not be cut through in this setup.
* The part and chunk share a top and a bottom (both 1/2 in thick), so those faces
  may flicker on screen.
* Checked: `inspect.interference` clean on everything but the part, which
  overlaps its chunk on purpose; jaw, parallel and hole places read back.

## 2026-10-31: Plate from `SCRoundPoly`; chunk 1/2 in past both ends

* The user: the raw material is 1/2 in past the plate at both ends (taken as
  the plate's long ends, so 6 x 11-1/2 x 1/2 in; the 1/4 in at each long side is
  unchanged), which clears the misfit in the last entry.  The plate comes from
  the polygon class (`SCRoundPoly`, the name the user asked for), with 1/4 in
  corners and no holes for now.  `SCRoundPoly` gets improvements next.
* `ToolingPlate.outline()`, `corner_radius`, `drilled` (`TOOLING_PLATE` has it
  False; the grid and its cut remain, covered by `test_tooling_plate`).

## 2026-10-31: `SCRoundedPolygon`, with holes and regions; plate in one extrude

* The user: `SCRoundPoly` is renamed `SCRoundedPolygon` (done in code and the
  README; older log entries keep the old name).  It gets simple round holes and
  rounded polygons as internal regions; islands can have holes too.  The plate is
  one sketch, outline and all holes, made by a single extrude.
* `scgeometry.py`: `SCHole`, `SCRoundedPolygon(name, corners, holes, regions)`.
  Levels alternate: a region in a solid is an opening, one in that an island.
  `sketch()` draws it all; clearance checked at each level, on construction.
* SolidCraft's plain `solid.extrude` handles the nesting by itself.  Found: outline
  plus 200 holes takes 0.19 s, against 3.1 s to extrude and then cut.  An island
  comes out as its own body (`created_bodies` has 2), as nothing holds it.
* `ToolingPlate`: `drilled` is gone; holes are in `outline()`, so they are back on.

## 2026-10-31: The user's chart of screw holes

* The chart arrived: `tools.SCREW_FITS`, #2 to #12, close and loose (free) fits
  with their drills.  `TOOLING_PLATE` takes `SCREW_FITS["#6"].close`, #27, 0.1440
  in: the same as the stand-in, so the plate does not change.

## 2026-10-31: Where things stand

* Works: `Setup(setup_json)` in `scsetup.py`, read from
  `examples/setup/tooling_plate.json`: Mikini table, vise, parallels, a 6 x 11-1/2 x
  1/2 in chunk, the tooling plate inside it.  `python3 scsetup.py 8080` shows it.
* To measure on the user's mill: the table's thickness (2-1/2 in is an estimate; the
  user's 1 in can not be right with slots 1 in deep), its slot spacing (2 in is an
  estimate), and whether the 9.35 in Y travel is centered on the table.  Column
  clearance is unknown.
* The tooling plate's thickness (1/2 in) is an estimate.  In this setup its long edges
  are 1/8 in from the jaws' keep-outs, too close to cut through.
* Heights in the JSON are typed by hand; `Setup` does not check that each item rests
  on the one below (`test_scsetup.py` does, for this example).  Toe clamps and a
  `Mill` layer are not modeled.  `SCCNC` does not yet cut `SCRoundedPolygon`'s holes
  and regions.
* Last whole test suite: 251 passed, before the conical radius type; `test_tools.py`
  passed after it (55 tests).  The user: run the suite at most once in 10 minutes.
