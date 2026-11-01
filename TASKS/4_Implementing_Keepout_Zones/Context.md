# LLM Agent Context Log

## 2026-10-31: Created; the plan is in `Details.md`

* The user asked for a plan and no code yet, and will read `Details.md`.
  The user also has more to say about stacked zones before that design
  is settled.  Next: the user's reactions and its open questions.
* The demo's G-code has only 2 lines with Z beside X or Y, both `G83`,
  since its pockets are drilled, not ramped.

## 2026-10-31: The user's answers; `Details.md` updated

* Settled: no combined commands (so canned cycles get their own `G0 X Y`);
  only generated code is checked; all classes start with `SC`; cutters are
  vertical cylinders; rapids belong at Zsafe.
* Open in `Details.md`: the user's stacked zones talk, and questions 5 and
  7-12.  Still no code.

## 2026-10-31: Second round of answers

* Settled: rising rapids always fine, descending ones not; a drill out of rapid
  mode by Ztop; widest radius; rename this directory first (`scraftpybind` a
  separate task); combined MDI lines rejected.
* Open in `Details.md`: the user's stacked zones talk, and questions 5, 9, 13,
  14, 15.  Still no code.  The user is tired, so keep new issues to what matters.

## 2026-10-31: `Details.md` wrapped up for now

* The user: the questions were getting into implementation, so stop here and
  commit.  `G83` exempted; consistency checks only for bad data; Home belongs at
  Zsafe, so its `G0 Z0` is a bug to fix in step 10.
* Next session: the user's talk about stacked zones (step 1), and questions 5
  and 9, which are still open.  Then step 11, the `SC` rename.  No code yet.

## 2026-11-01: `SCRoundedPolygon.circle()`

* The user (who abbreviates `SCRoundedPolygon` as RP): an RP must be able to be a
  simple circle, likely for keep out zones.  `SCRoundedPolygon.circle(name, x, y,
  radius)`: a counter-clockwise square with corner radii half its side, so four
  quarter arcs.  This settles step 2's "to be tested".
* Checked: `offset()` and `inset()` both ways, as a region; a headless extrude reads
  1568.26 against 1570.80 mm^3 (rounds read low), centered where it should be.
* `signed_area` stays the sharp square's (4 r^2), as documented; `SCLoop.signed_area()`
  gives the true area.

## 2026-11-01: `SCRoundedPolygon.line_enters()`

* The user's idea: test the sharp polygon first, since a line that stays out of it can
  not enter the rounded one; then work out which side of the rounded corner it is on.
* That holds only for corners bulging outward; rounding a corner that turns inward adds
  material outside the sharp polygon (`notched()`'s (40, 30)).  So the first test is
  `bound`: sharp corners, with a chord across each rounded inward corner.  `bound` is
  empty when its lines cross (a sharp corner with a large radius reaching over its own
  arm, `tip_over_strip()`), as parity in `SCLoop.contains()` then reads wrongly.
* The second test: cut the line at every edge of every level and test points on each
  piece.  Touching or following an edge is clear, within `TOUCH`; a line with no length is
  a point.  Holes and regions count (a line within a hole or opening is clear).
* The quick test saved little in Python: 18 against 31 us for a far line, 99 against 86
  us for a line through the polygon (the 7 corner `notched()`).
* Only lines; arcs are not done yet.  Each piece's cost is `distance_to()` on all edges.

## 2026-11-01: `SCRoundedPolygon.enters()`, lines and arcs

* `line_enters()` became `enters(segment)`, taking an `SCLine` or an `SCArc`, so a checker
  walking a program has one call; nothing else called the old name.  Same two tests.
* An arc over one whole turn raises `ValueError`, since `fraction_of()` can not place
  points on it and a piece would go untested.  An RS-274 arc is at most one turn here.
* Still flat, in XY.  Helical arcs and the Z range are for the checker (question 9).
* Timing on `notched()`: 14 against 25 us far away, 90 against 75 us through it.

## 2026-11-01: The user on circular ramps and tool radius

* The user: comparisons are all in XY, so a circular ramp or helix is just arcs forming
  a circle; and for a tool of radius R, grow or shrink each RP in the zone by R, then
  track only the tip.  Claude agrees; this answers question 9 (`Details.md` not edited).

## 2026-11-01: Only the exterior contour

* The user: Z is where the layered keep out zones come in.  Growing a zone by the tool
  radius may lose internal holes and slots; only the exterior contour is needed.  Inside a
  zone's outline therefore counts as solid: false alarms possible, misses not.

## 2026-11-01: A cusp is an RP corner of radius 0

* Claude said a grown outline's cusp could not be an RP; the user was right that it can.
  At a cusp, each arc's edge is used up exactly, leaving a radius 0 corner between them.
  So growing can return an RP, and `SCLoop` needs no `enters()`.
* A throwaway script (not in version control) turned `inset()`'s loops back into RPs: each
  arc's corner is where its end tangents meet, at its own radius (arcs over 90 degrees are
  split first); each joint that is not tangent is a radius 0 corner.  All 17 of 18 cases
  built, with the same length and the same answers at about 4000 random points each.
* The one failure: a slot exactly 2R wide leaves a slit of no width, which an RP refuses
  ("turns back on itself").  The plan is to treat it as closed: a false alarm, not a miss.
* The user: do not run the test suite until more of these issues are worked through.

## 2026-11-01: The 2R slit: remove its lines

* The user: "turns back on itself" is solved by removing the line segment.  Tried in a
  throwaway script: the slit is two lines of equal length, out and back, and removing them
  leaves the two arcs meeting at the slot's mouth, (11, 20) for a 2 in slot at R = 1.
* Those arcs are tangent with opposite directions, so that joint alone still reads "turns
  back on itself".  With the check relaxed for a radius 0 corner, the RP builds, and agrees
  with the loop at 5997 random points; a line from (11, 22) to (11, 20) is clear, and one
  on to (11, 19.99) enters.
* Claude's plan: allow the reversal only at a radius 0 corner whose two edges are entirely
  used up by arcs, so a real spike of lines is still refused.  `bound` comes out empty
  there (safe, just no quick test).  `offset()` would divide by zero at such a corner, so
  it needs a `ValueError`.
* Not solved yet: within about 1e-7 of 2R, `inset()` leaves slits that are not exact (at 2R
  less 1e-7 the RP was refused: "segments 5 and 8 cross"), so slits must be found within a
  tolerance; not yet tried.

## 2026-11-01: Grow by R + e

* The user: grow by R + e, with e a small number.  Tried in a throwaway script with e of
  1e-5, 1e-4 and 1e-3: a slot of exactly 2R, or anywhere near it, now closes to an ordinary
  cusp.  So the slit, removing its lines, relaxing "turns back on itself" and a guard in
  `offset()` are all no longer needed.  Five shapes at R = 1, e = 1e-4 agree with the true
  distance to the original at about 4000 random points each.
* The trouble only moves: a slot within about 1e-6 of 2(R + e) is still refused
  (`ValueError`).  Such a width is unlikely, as R + e is not a round number.  Claude's plan:
  retry once with 2e, then report the zone as unchecked.  The retry is not tried yet.
* A tool exactly touching a zone now reads as entering, by up to e.
* The user: run the test suite once the issues are whittled down.

## 2026-11-01: `grown()`, `shrunk()`, `leaves()`, `SCLoop.polygon()`

* The user: layers come after the other issues; a pocket is the same issue, with the path
  wanted inside rather than outside; e and exact touching are fine; run the whole suite.
* `SCRoundedPolygon.grown(radius)` returns one RP, the exterior at `radius + SLOP`
  (`SLOP` = 1e-4).  `shrunk(radius)` returns a list of RPs, none when the tool does not
  fit, several when a neck splits it; the tool must not `leaves()` one of them.  Each tries
  `SLOP`, then `2 * SLOP`, for a slot or neck that fits the first exactly.
* `inset()` works to `JOIN` (1e-5), and the RP constructor was exact to 1e-9, so random
  shapes failed about 1 % of the time, where an inward corner's radius about matches the
  tool's or a corner is nearly straight.  Two causes, both fixed outside `inset()`, which
  tool paths use:
  * `SCLoop.polygon()` drops segments under `SLOP`, and lines lying back along their
    neighbors (`inset()` overshoots near straight corners, and comes back).
  * The constructor now takes a fit of arcs on an edge within `TOUCH` as exact, and
    `_closed()` makes every joint shared.  This changes shared code; a line under
    `TOUCH` between two arcs is now no line.
* Checked: about 69000 random builds, 550000 points against the distance to the
  original: none refused, none wrong.  A headless extrude of a grown slot, with its cusp:
  2415.40 against 2415.53 mm^3.
* Left as it was: the constructor refuses a very small arc on a nearly straight corner
  (neighbors within `TOUCH`).
* Layers (step 1) are next.

## 2026-11-01: Where things stand

* Done (step 3 and the XY half of step 4, ahead of the plan's order): in `scgeometry.py`,
  `SCRoundedPolygon.circle()`, `enters()` (lines, arcs, points), `leaves()`, `grown()`,
  `shrunk()`, `bound`, `SLOP`, `SCLoop.polygon()`.  Last whole suite: 315 passed.  Nothing
  outside the tests calls them yet: no checker, no stack, no renames (step 11).
* A keep out zone is `poly.grown(R).enters(move)`.  A pocket is fine when `place.leaves(move)`
  is False for one of `poly.shrunk(R)` (the user: the same issue, inverted).
* Decided by the user, not yet in `Details.md`, which only the user edits or asks to have
  edited: XY only, Z belongs to the layers; helixes and circular ramps are arcs in XY, which
  answers question 9; only the exterior contour is needed when growing; grow by R + e; a tool
  exactly touching a grown zone reads as entering, which changes "touching counts as clear" in
  step 4 for grown zones.
* Next: layered zones (steps 1 and 2).  The user will explain stacked zones first, and may want
  `Details.md` brought up to date.
* Question 5 (finished features as keep outs): the user does not yet understand it and is
  letting it slide for now.  Do not press it.

## 2026-11-01: The user's layering, first reading

* The user: an RP is recursive, with a list of child RPs, using absolute `(Zstart, Zend, [RPs])`.
  Zstart < Zend extrudes material up; Zstart > Zend extrudes a hole down.  A child's Zstart must
  EXACTLY match its parent's Zend, and it must be entirely enclosed by its parent.  (The user
  wrote "SCRoundedPocket"; taken to mean `SCRoundedPolygon`, not yet confirmed.)
* Claude's reading: since each child starts on its parent's surface and stays within it, nothing
  can overhang, so the shape is a height field: the surface at (x, y) is the Zend of the innermost
  RP there.  A tip at Z is blocked where that surface is above Z.
* Checking a move at Z, a recursion with no merging: a blocked RP must not be entered once
  `grown(R)`, unless the move stays inside a `shrunk(R)` of an unblocked child, which is then
  checked the same way among its own children.  Not coded, not tried.
* Questions put to the user: the form of the tuple; flush walls, which "entirely enclosed" may
  forbid, and which `leaves()` could check; what replaces `regions` and `SCHole`.  No code yet.

## 2026-11-01: Layering, second round

* The user confirmed: it is `SCRoundedPolygon`; the first RP must go up; zero height is refused; an
  RP literally holds `z_start: float`, `z_end: float`, `children: Sequence[RP]`; a child may touch
  but not cross its parent's wall; `SCHole` is a subclass of RP, with a shortcut for speed.
* `regions` are RPs inside an RP, whose levels swap solid and open.  Only `test_mount.py` and
  `scgeometry.py` use them, so children replace them outright.
* Claude overstated the cost of circles.  Measured with 200 in a plate: SCHole builds in 0.01 s, one
  `enters()` 1.4 ms; circle RPs 0.17 s and 5.4 ms.
* Found: a child is built before its parent, so "the first must go up" can not be checked by the
  constructor, only where a root is used.  One sketch and extrude no longer fits children of
  other depths.  `SCCNC` still takes flat outlines.
* Open with the user: what `z_start` and `z_end` are on flat outlines (37 constructor calls).

## 2026-11-01: Z is required

* The user: `z_start` equal to `z_end` always raises an exception, so there is no flat RP (Claude's
  option A is out).  Every RP has real heights: `circle()`, `SCHole` and `SCLoop.polygon()` take them;
  `offset()`, `reversed()`, `grown()` and `shrunk()` keep their source's.  All 37 constructor calls
  change.
* The user: exact float matches also show what can combine into one cycle: a child hole whose `z_end`
  equals its parent's `z_start` goes in the parent's sketch, and siblings with the same two heights
  share one cut.  Agreed.  Sibling, `grown()`, `enters()` and height decisions stand.  Still no code.

## 2026-11-01: `z_start`, `z_end`, `children`, and `hits()`

* Done, as agreed: an RP holds `z_start`, `z_end`, `children`; equal heights raise; a child starts
  exactly at `z_end`, may touch but not cross the outline, and siblings may touch but not overlap.
  `regions`, `holes`, `_is_solid()` and `_all_edges()` are gone.  `enters()` and `leaves()` are outline
  only.  `SCHole(x, y, diameter, z_start, z_end, children)` subclasses RP, refuses going up, and draws a
  true circle.  `circle()` and `SCLoop.polygon()` take heights.  `grown()` and `shrunk()` keep theirs,
  and cache by radius.
* `hits(move, z, radius)` walks the tree, and refuses a root going down.  `model()` makes one body:
  children running the whole height share the sketch; the rest are grouped by `z_end`, one sketch and
  one join or cut each (a negative `distance` cuts down).  `box` and `overlaps()` are new.
* Checked: 318 tests passed; 9 deliberate breaks caught; the demo's G-code is byte for byte the same;
  random moves against a plain height formula, both ways; a live `model()` to within 1 %.
* The demo's RPs have real heights (top at Z = 0), but `SCCNC` ignores them: still flat.  A move across
  two touching holes is a false alarm, since it leaves each one's `shrunk()`.
* Not started: the checker walking `SCCNC.commands`, `SCPrism` and the vise as roots, renames.

## 2026-11-01: `SC` rename done; testing on Table/Vise/Parallels

* Step 11 is done, and in `scraftpybind` too (`T.rcts` there), since `scraftcnc` links to it: this
  replaces question 11's "separate task".  `SolidCraftPyBind` is `SCPyBind` (the user's choice),
  `Machine` in `lcnc_panel.py` is `SCPanelMachine` (`SCMachine` was taken).  Test classes keep `Test`.
  Done by token, not by word, so body names ("Plate") and `argparse.Namespace` stayed.  The demo's
  G-code is byte for byte the same; 318 tests passed; 126 `mypy` errors in test files were already there.
* The user wants the first test on `examples/setup/tooling_plate.json`.  Keep-outs in work Z (chunk top
  = 0): jaws to -0.14, parallels to -0.375, vise base to -1.875, table to -4.515; plate bottom -0.5.
* Predicted by hand, not run: the 200 holes clean, the short ends clean; the long edges fail below -0.14
  where |X| < 3.125 + R, for any R over 1/16 in.  The user: keep it failing, and figure it out later.
* Test order: deliberate crashes on each zone and move kind; brute force distances; the demo in a 6 in wide
  chunk, 3 in side across the jaws, should be clean; the tooling plate must fail exactly as predicted.
* Decided: the work origin is the center of the material's top (the user will later explain why the fixed
  jaw is better).  Zones are moved into work coordinates; rapid rule reports are kept apart from keep-out
  hits; the checker comes before fixing the other rapids, so that they are seen to fire.
* Turning: the user says a turned part regenerates its G-code, but remapping X/Y and I/J is easy, given
  a point and an amount, with no sine or cosine at 90 and 180 degrees.  Not yet settled.
* Next, none started: `SCTool` widest diameter, canned cycles with their own `G0 X Y`, prisms as root RPs,
  work origin in the JSON, the checker, the tests.
* Seen once: after the suite, a `mcp --headless` process was left, its parent `systemd`.  Killed it.  Not
  looked into; check `pgrep` after the next suite.
