# LLM Agent Context Log

## 2026-11-02: Compressed from `Details.md` and the log to 2026-11-01

At the user's word.  The long forms (dated log, draft plan, line numbers) are in `hg`.

### Where things stand

* Done: the `SC` rename (here and in `scraftpybind`), the generator following the rules, and the
  checker for prisms and flat zones.  `python3 sckeepout.py`: demo 0 violations; tooling plate 38
  keep out reports (all T1, from the second pass, Z-0.22; long edges only), on purpose, until the
  user says how to fix it (`test_tooling_plate_fails_as_predicted`).
* Last whole suite: 350 of 351; the failure, `test_drilled_pocket`, was a test's count, since
  fixed.  Run the whole suite first when this resumes.
* Next, the user's choice: violations shown in the tool path viewer and SolidCraft, or the fixed
  jaw as the work origin, which the user will explain.  Then the rest of the plan below.

### The user's decisions

* 2.5D: a line never has Z with X or Y, except ramps.  Only code `scraftcnc` generates is checked.
  Commands are not combined: a canned cycle is `G0 X Y`, then the cycle with no X or Y, then `G80`.
* Cutters are vertical cylinders reaching up forever, at their widest radius.  The tool holder's
  zone comes much later.
* All comparisons are in XY; Z belongs to the layers.  Grow or shrink each RP (the user's short name
  for `SCRoundedPolygon`) by R, then track only the tip.  Ramps and helixes are just lines and arcs
  in XY, tested over their Z range (question 9's answer).
* Grow by R + e.  Only the exterior contour is needed, so inside a zone's outline is solid: false
  alarms possible, misses not.  A tool exactly touching a grown zone reads as entering.  A pocket is
  the same issue, inverted.
* Rapids belong at Zsafe, so rapids into material are not dealt with.  Rising rapids are always OK.
  A drill may rapid down if out of rapid by Ztop; `G83` is exempted, since it rapids back into its
  hole between pecks.  Rapids from Zsafe to Ztop may be allowed later, if run times matter.
* Every violation is reported, with its G-code line and zone, rather than stopping at the first.
* MDI: a line moving Z with X or Y is rejected, and the operator told to split it.
* Home belongs at Zsafe; its `G0 Z0` (`lcnc_panel.py`) is a bug, to fix with the panel step.
* Bad user data gets some consistency checks only: `SCSetup` is to check that each item rests on the
  one below (not done).
* Work origin: the center of the material's top, for now; `SCPlacedWork.work_origin()` computes it.
* Turned parts: `SCCNC.remap(turns, dx, dy)`, clockwise quarter turns then a move, on finished
  commands.  `X`/`Y` turn and move, `I`/`J` only turn, `G2`/`G3` stay.  Settled for now.
* Layers, an RP: `z_start`, `z_end`, `children`, in absolute heights.  Going up is material, going
  down a hole; equal heights always raise, so no RP is flat.  A root goes up (checked where a root is
  used, as a child is built first).  A child starts exactly at its parent's `z_end`; it may touch but
  not cross its parent's wall; siblings may touch but not overlap.  Exact float matches also show what
  shares a cycle: siblings with the same two heights share one cut.  `SCHole` is a subclass going down.
  These replaced `regions` and `holes`.
* Question 5 (finished features as keep outs on a later setup): the user does not yet understand it
  and is letting it slide.  Do not press it.

### What exists

* `scgeometry.py`: `SCRoundedPolygon` with `circle()`, `enters()` (line, arc or point; outline only;
  raises on a whole turn arc), `leaves()`, `grown()` (one RP, at `radius + SLOP`, 1e-4), `shrunk()`
  (a list: none if the tool does not fit, several if a neck splits it), `hits(move, z, radius)` (walks
  the tree), `bound`, `box`, `overlaps()`, `SCLoop.polygon()`.  `grown()` and `shrunk()` retry at
  `2 * SLOP`, for a slot or neck fitting the first exactly, and cache by radius.
* `sckeepout.py`: `prism_zone()`, `cylinder_zone()`, `work_zones()`, `arc_segments()`,
  `check_program()`, `report()`; report kinds `keep out`, `rapid`, `unchecked`.  Each zone is an
  unmerged root, in work coordinates.  A move is tested at its lowest Z, so a `G0` rising out of a zone
  is reported too.
* `SCTool.widest`, `widest_radius()`.  `examples/setup/demo_plate.json`.
* The generator: descents from `z_safe` to `z_top + clearance` are `plunge()`s, sideways moves in a
  pocket `linear()`s; demo run time 9.9 to 11.7 minutes.  `drill_cycle = "moves"` still rapids back
  into its hole (`_peck()`), and is reported; no example shop uses it.

### Insights and traps

* Do not merge zones: a move is bad if it enters any, and overlapping ones (the vise's) are tested one
  at a time.  `SCRoundedPolygon` refuses outlines that cross.
* A hole too small for the tool, or a notch closing as it grows, is a normal result, not an error.
* Anything the checker does not understand is reported as `unchecked`, so a clean report means that
  everything was really checked.  It guards against the checker and generator drifting apart.
* The checker reads the finished `SCCNC.commands`, independent of how the path was made.
* Tool paths and the checker share `scgeometry.py`, so tests also measure random moves by plain
  distances, with no offsets.
* The rapid rule catches rapids into material with no knowledge of the material.
* A nest of RPs is a height field, since nothing can overhang; a tip at Z is blocked where the surface
  is above Z.  A move across two touching holes is a false alarm, as it leaves each one's `shrunk()`.
* A cusp is an RP corner of radius 0, so growing can return an RP.  A slot of exactly 2R leaves a slit
  an RP refuses; R + e closes it.  The constructor takes arcs fitting an edge within `TOUCH` as exact,
  and a line under `TOUCH` between arcs is no line.  It still refuses a very small arc on a nearly
  straight corner.
* The quick `bound` test saved little in Python (14 against 25 us far away, 90 against 75 us through).
  `bound` is empty when its lines cross.  200 holes in a plate: `SCHole` builds in 0.01 s, one
  `enters()` 1.4 ms; circle RPs 0.17 s, 5.4 ms.  Rounds read about 1 % low in headless volumes.
* `signed_area` of `circle()` is the sharp square's (4 r^2); `SCLoop.signed_area()` is the true area.
* `rs274 -t shop_mill.tbl -g FILE` in `lcnc_sim/` runs a program; with no tool table it stops quietly
  at the first `M6`.
* Keep-outs in work Z, tooling plate (chunk top 0): jaws to -0.14, parallels to -0.375, vise base to
  -1.875, table to -4.515; plate bottom -0.5.
* Numbers still estimates: the Mikini table's thickness, slot spacing, whether its Y travel is centered.
* The panel's guard is only as good as the work origin, tool length and vise position, and only guards
  moves through this panel.  Say so on the screen.  It must let a tool inside a zone move back out.
* Seen once: a `mcp --headless` process left after a suite, parent `systemd`.  Check `pgrep` after one.

### What is left

Numbers are the plan's, kept.

* 7, seeing it: violations marked in the viewer, zones modeled in SolidCraft (as `SCKeepOut.model()`
  does for prisms).  There is already a command line report.
* 8, nested depths in programs: `SCCNC` ignores RP heights, and `SCCNC.pocket()` takes a `bottom` and
  a flat list of `islands`.  May also bring a finer vise than three cuboids.
* 9, `SCMount`: the same treatment.
* 10, panel: `lcnc_panel.py` loads a setup; opening a generated program runs the check before Start;
  each jog, MDI line and move to the origin (`SCPanelMachine.jog()`, `.mdi()`) is checked before being
  sent, and refused with the zone's name, but a move leading out is allowed.  A program not generated
  by `scraftcnc` reports that it is unchecked.  Each check must be quick.
* Later: the tool holder's zone (the tool becomes a small stack of height range and radius).
