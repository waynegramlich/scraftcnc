# LLM Agent Context Log

## 2026-10-30: `tools.py`, starting with Tormach's mill tables

The user widened this task: model the tooling in SolidCraft, from the
bottom up, starting with the tables of Tormach's three entry level
mills (`T.m~2.3` lists what comes on top of them).

* `tools.py`: `MillTable` (numbers, in mm), `MILL_TABLES`, and
  `Tormach.mill_tables()`, which models all three side by side.  Run
  `python3 tools.py 8080`, with the GUI started as
  `solidcraft/solidcraft-linux-x86_64.AppImage --control 8080`.
* Checked: headless volumes match `MillTable.volume()` exactly
  (`test_tools.py`), and seen in the GUI.
* Source: Tormach's drawing, "T-Slot Spacing on Tormach Mills", at
  `tormach.atlassian.net/wiki/rest/api/content/4011819206/child/attachment/att4011819222/download`.
* Conflicts, decided in the drawing's favor:
  * 770 slot spacing: drawing 50 mm (and to scale), PCNC 770 spec 2 in,
    770M knowledge base 2-3/8 in, which looks copied from the 1100M.
  * 440 slot width: drawing and manual 10 mm, spec sheets 3/8 in.
  * Sizes: drawing 460 x 160, 660 x 205, 860 x 240 mm; spec sheets 18 x
    6.3, 26 x 8, 34 x 9.5 in.
* Scaled from the drawing, not dimensioned: plate thickness, pocket
  size.  Assumed: pockets as deep as the slots, with square corners.
* Left out: the ways under the table, the coolant grooves, the 440's
  corner holes, the 1100's T-slot in its front edge.

## 2026-10-30: `KeepOut`, prisms first

* `tools.py`: `Prism` (`low`, `high`, `grown()`), `KeepOut` (`prisms`,
  `add_prism(prism, "1/8 in")`, `model()`), `MillTable.prism()`,
  `Tormach.mill_table_keep_out()`.  Cylinders are to come.
* Shown as new bodies, `#e03c31` at opacity 0.25; SolidCraft stores it
  (`appearance.list`), and volumes match with the tables unchanged.
* With the tables hidden, a screen capture shows see-through boxes with
  black edges, but little red.  `xwd` captures have colored vertical
  stripes, so they can not judge color; the user's eye decides.
* `browser.visibility(items=[...], visible=False)` hides bodies.

## 2026-10-30: Generic `Drill`, and keep-out cylinders

* `tools.py`: `Drill` (`diameter`, `overall_length`, `flutes`,
  `shank_length`, `shank_diameter`, `point_angle`), `Cylinder`,
  `KeepOut.add_cylinder()`, `SAMPLE_DRILLS`, `sample_drills()`.  The
  drills stand in a row at Y = -100 mm, tips at Z = 0.
* Grooves dropped at the user's word ("not important").  Straight
  grooves cut fine through a flat tip, but on a coned tip SolidCraft
  0.25.1's boolean failed after about 70 s: "not supported yet ... takes
  planar faces only, and the target has 9 curved faces".  Start heights
  were not tried; the user stopped that.  `flutes` is kept as data.
* `inspect.center_of_mass` reports round bodies about 1.1 % low, as if
  measured on facets (cause not confirmed).

## 2026-10-30: Drill grooves work, the user's way

Supersedes "grooves dropped" above.  `Drill.model()` extrudes the
grooved outline (`section()`, lines, not arcs) whole, joins the shank,
then cuts an inverse cone (`point_cutter()`) with `solid.revolve`: the
user's suggestion, about 3 s a drill.  Cutting circles from a revolved
drill, and intersecting with a cone, both fail in SolidCraft 0.25.1.

## 2026-10-30: True arcs and colors; where things stand

* SolidCraft has no switch to hide edges (`view.*` has none), so the
  lines along the drills came from drawing arcs as short lines.
  `Drill.section()` now returns true arcs; the extrude, shank join and
  cone cut all still work, faster.
* Each sample drill has its own color (`SAMPLE_DRILL_COLORS`); the
  aim is only that a person can count the flutes.
* The user's view: end mills and drills are all variations of a
  grooved cylinder, so they can share this routine.  Fly cutters look
  different, and wait until much later.
* Next: the user's choice.  End mills are the natural next tool, then
  what `T.m~2.3` lists on top of the tables (vises, clamps).

## 2026-10-30: `Vise`, bottom layer

* The user's design: three stacked base blocks (bottom, middle, top =
  the bed), a large hole through the bed that the moving jaw slides
  along, fixed and moving jaws on the bed, the screw a plain cylinder
  that sticks out over the end.  Built with `SCRoundPoly`.
* `tools.py`: `ViseBlock` (`outline()`, `volume()`, `model()`), `Vise`
  (every parameter, and fit checks), `KURT_D688`.  `Vise.model()` makes
  only the bottom block so far; the screw runs along X, the handle end
  at +X, the fixed jaw at -X.
* `KURT_D688` numbers from used machinery listings: 6 in jaw width,
  1.735 in jaw height, 8.8 in opening, 16.75 x 8.25 x 4.375 in overall.
  Taken to be: the height includes the jaws, the length includes 1 in
  of screw, and the 8.25 in width is the bottom's.  Everything else is
  an estimate.
* Not settled: whether the hole goes through only the bed or the middle
  too; the screw needs room at `screw_height`.
* Checked: headless volume and center; shown in the open GUI at
  Y = -250 mm with no `file.new`.

## 2026-10-30: Bottom layer's notches

* The user: the side openings are rectangular notches, rounded at all
  four corners; some Kurts have two per side; they all line up.  So
  `ViseNotches` (`centers` X1, X2, ..., `width`, `depth`, `inner_radius`,
  `outer_radius`), held once by `Vise` so every layer can share it.
  `KURT_D688`: two per side at X = +/-4 in, 7/8 x 7/8 in, radii 1/4 and
  1/8 in, bottom corners 1/2 in; all estimates.
* Next, as its own step (the user's order): the middle layer, with
  rounded outer corners, the notches, and a hole in one end for the
  screw.  At 6 in wide it is out of reach of 7/8 in notches, so what
  "line up" means for it needs settling then.
* Checked: GUI volume 1557644 against 1557683 mm^3 worked out (rounds
  are measured a little low).  The GUI window was covered, so `xwd` could
  not capture it; the user's eye decides.
* To swap a body in the GUI without `file.new`:
  `timeline.delete(features=[sketch name])` takes its extrude too.

## 2026-10-30: Middle layer

* The user: the middle layer has notches too, bigger, so that a box
  wrench can tighten the hold down; it is usually two or three times
  as high as the bottom.  `Vise` now has `bottom_notches` and
  `middle_notches`, refused unless their `centers` match and the middle's
  clear the bottom's.
* `KURT_D688`, all estimates: bottom 0.5 in, middle 1.25 in, bed 0.89 in
  high (same 2.64 in total); the middle is 8.25 in wide (was 6) with
  1-3/4 x 1-3/8 in notches, radii 3/8 and 1/8 in.
* The screw's hole (`screw_hole_diameter`, 1-1/8 in) is a blind bore from
  the +X end, as deep as the screw reaches (11 in), centered in the
  middle's height at 1.125 in.  Whether the middle is hollowed out for
  the screw and the moving jaw's nut is not settled.
* Checked: headless and GUI volumes within 0.06 % of the hand figures;
  the window was covered again, so no picture.

## 2026-10-30: Rails, end blocks and the screw

* The user: not a perfect model, one where you say "I know what that
  is!"  The middle layer is sometimes thinner than the outer layers
  (left as a number, `KURT_D688` unchanged).
* Replaces the solid bed and its hole: `rail_width`, `rail_height`,
  `rail_gap`, `end_block_length`; two rails the whole length, a block
  between them at each end, all sharp cornered, each its own body.
* The user did not answer whether the middle is hollow.  Claude's
  choice: a pocket through the middle under the opening, so the screw
  shows; the hole for the screw goes through the +X end wall only.
* The screw: a cylinder from the pocket's -X end to 1/4 in past the +X
  end, joined to an extruded hexagon, 3/4 in across the flats (Shars
  page 317: 3/4 in handles for Kurt vises, 7/8 in for 8 in ones) and
  3/4 in long.  `screw_length` is gone.
* Checked: GUI volumes match the hand figures (the screw 0.7 % low, as
  round parts are); window covered, so no picture.  Next: the jaws.

## 2026-10-30: Jaws and slider

* The user: the third layer is as wide as the lower two (`rail_width`
  2-7/8 in, which roofs the notches; a box wrench goes in from the
  side).  Fourth layer: two blocks of one width, 2-3 times the rails'
  height; the fixed jaw at the end away from the hexagon; the moving jaw
  3-4 times its length.  Under the moving jaw, a slider between the
  rails, as long as the moving jaw less an end block.  Raised, to see it.
* `Vise.slider()`, `Vise.moving_face()`, `_model_jaws()`;
  `model(solidcraft, center, opening, lift)`.  The slider starts at the
  jaw's clamping face (Claude's reading), so the jaw reaches the base's
  +X end just as the slider meets the end block.  Separate bodies, not
  joined.
* `KURT_D688`: fixed jaw 1-1/2 in long, moving 5-1/4 in (3.5 times),
  slider 3-3/4 in, end blocks 1-1/2 in so that the jaws can close, rails
  0.75 in high, middle 1.39 in, jaws still 6 in wide (the listing).
  Shown at `VISE_OPENING` 3 in, `VISE_LIFT` 4 in.

## 2026-10-30: Slider reaches the screw; wide jaws

* The user: layer 4 is as wide as layers 1 and 3; layer 2 is sometimes
  narrower; the block under the moving jaw fits exactly between the
  rails, has a hole for the lead screw, and is shorter so that it misses
  the end block by the hexagon.
* Read as the existing slider, not a second block: now as high as the
  rails plus the middle, standing on the pocket's floor, with a hole of
  `screw_diameter` along X (`_model_slider()`, `slider_volume()`).
* `KURT_D688`: jaws 8.25 in wide (not the listings' 6 in); middle 7-1/2
  in wide, its notches 1 in deep so that they reach as far in as before.
  Rail and jaw widths are now checked against `bottom.width`.

## 2026-10-30: Jaw plates

* The user pasted notes on 6 in vise jaws: holes on 3.875 in centers,
  1/2-13 or M12 screws, hole centers 0.940 to 1.625 in above the bottom,
  plates 6.0 in long, 1.5 to 3 in high, about 0.725 in thick when hard.
  Source not given.  This settles the listings' 6 in against the 8.25 in
  jaws: the 6 in is the plates.
* `Vise.plate`, `plate_hole_spacing`, `plate_hole_diameter` (17/32 in
  clearance, Claude's choice), `plate_hole_height` (0.94 in),
  `_model_plate()`, `plate_volume()`.  Height 1.735 in (the listings),
  flush with the jaw.  Opening is now measured between the plates.
* To make room for 8.8 in between plates, `KURT_D688`: fixed jaw 1 in
  long (was 1-1/2), moving jaw 3-3/4 in (was 5-1/4; 3.75 times), slider 2-1/4 in.
  The jaws have no holes, and no screws are modeled.

## 2026-10-30: Six inches wide

* The user: all Kurt vises are 6 in wide, so follow suit.  `KURT_D688`:
  bottom, rails (1-3/4 in each, 2-1/2 in apart), jaws and plates 6 in;
  middle 5-1/4 in, its notches leaving a 3/8 in wall beside the pocket.
  The listings' 8.25 in overall width is not used.

## 2026-10-30: Vise assembled; where things stand

* The user: good enough for now; drop the jaws down.  `VISE_LIFT` is
  "0 in"; `lift` stays, to raise them again.  `inspect.interference`
  finds no overlaps among the 12 bodies (`test_vise_assembled`, at no
  opening, 3 in and wide open).
* Left out: holes in the jaw blocks, the plate screws, joining the
  slider to the moving jaw, turning the vise, and placing it on a table.

## 2026-10-30: Vise keep-outs

* The user: "That looks like a Kurt vise."  Keep-outs for the base with
  the hex, and each jaw; the moving jaw's reaches the end of the hex.
* `Vise.keep_out(center, opening, margin)`: three prisms, grown
  `VISE_MARGIN` (1/8 in); they overlap by twice that where they meet.
  Each jaw's holds its plate, so the open space between them is the
  opening less two margins.  Shown in the GUI, added to the vise.

## 2026-10-30: Parallels; where things stand

* The user: "Looks beautiful" (the vise's keep-outs).  Parallels from
  1/2 in to 2 in by 1/8 in (the user's own stop at 1-1/2 in; Google says
  2 in is the high end), typically 1/8 in thick and 6 in long.
* `Parallel`, `PARALLEL_HEIGHTS`, `PARALLELS` (a pair of each height, so
  26: Claude's reading of "a whole set"), `parallel_centers()`,
  `parallel_set()`.  They stand on edge, long along Y as they lie in the
  vise, in a row at Y = -450 mm, each with a 1/8 in keep-out.
* In the open GUI, added to the vise and its keep-outs, not saved.
* Next: the user's choice.  `T.m~2.3` lists what else goes on the tables
  (clamps); nothing yet places the vise or parallels on a table, or a
  part in the vise.
