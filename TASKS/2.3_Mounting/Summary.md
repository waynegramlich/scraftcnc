# Summary of `T.m` Mounting

Stacks of tooling and material that hold work on a machine, with their
keep-outs (2026-10-30 to 2026-11-01).  Closed at the user's word on
2026-11-02, with the items below still undone.  Decided and done:

* `mount.py`: `Layer` (a `Protocol`), `TableLayer`, `ViseLayer` (with
  `turned`), `ParallelPair`, `Plate`, `Mount`, with `FIRST_MOUNT`,
  `GARAGE_MOUNT` and `PLATE_MOUNT`.
* `scsetup.py`: `Setup(setup_json)` places all tooling, material and
  parts outright from JSON, reporting every problem at once.
  `examples/setup/tooling_plate.json` and `demo_stack.json` (the
  demonstration plate, for `show_demo.py`, in the program's coordinates;
  `T.hlp~3.3.1`).  A setup's bare numbers are millimeters, so use
  `document.units(units="mm")` around it.
* `tools.py`: `MIKINI_1610L`, the user's garage mill (table as the user
  measured it: 30 x 10-1/2 in, 5 slots), `ToolingPlate` and `SCREW_FITS`
  (the user's chart).  Vises are held by two bolts, so holes need not
  line up with slots.
* `scgeometry.py`: `SCRoundedPolygon` (renamed from `SCRoundPoly`), with
  `SCHole` and nested regions.  One extrude of an outline with 200 holes
  takes 0.19 s, against 3.1 s to extrude and cut.
* `SharsMD/` (a link to `../catxtract/SharsMD`, in neither version
  control) is a partial conversion of the 2026 Shars catalog.  Work
  holding pages are 310-331, the index 451-455.  Traps: thousands commas
  read as periods, and lettered dimensions are only in the pictures.

To measure on the user's mill: the table's thickness (2-1/2 in is an
estimate; the user's 1 in can not be right with slots 1 in deep), its
slot spacing (2 in is an estimate), whether the 9.35 in Y travel is
centered on the table, and column clearance.  The tooling plate's 1/2 in
thickness is also an estimate.

Not done: toe clamps and other clamps, a `Mill` layer, merging G-code
files, parts turned over between setups, and raw material that is not
flat.  `Setup` does not check that each item rests on the one below
(`T.ikz~4` question 14 asks for it), and visual mounting instructions do
not exist.  `SCCNC` does not cut `SCRoundedPolygon`'s holes and regions.
In the tooling plate's setup its long edges are 1/8 in from the jaws'
keep-outs, too close to cut through.  In `demo_stack.json` the through
cuts go 0.05 in into the tooling plate, and nothing fastens the plate to
it; the user: these "will all be worked out", later.  Giving setup tools
kinds in the shop files is `T.ctfs~5.1`.
