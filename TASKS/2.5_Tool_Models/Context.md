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

## 2026-10-31: Double end countersinks, from Shars page 24

* The user: model double end countersinks from `SharsMD/page_024/page_024.md`,
  four tables: 421-0130 (60), 421-0141 (82 and 90), 421-0388 (60), 421-0138 (60).
  Asked whether SolidCraft revolves sketches: yes, `solid.revolve`.
* 421-0138's table (left hand) was first only in the picture `page_024_7.png`.  The
  user then extracted it into the `.md`, which also stops at size 7.  A one-off
  script compared all 44 rows of the page against the code (not a test, as
  `SharsMD` is in neither version control).
* A plain outline once dropped its upper tip, so its closing line cut through the
  tool; the volume check caught it (plain cylinders read 98.9 % here, it read 92-94
  %).  Revolves measure low on small tools, so compare with that in mind.
* `tools.py`: `DoubleEndCountersink`, `DOUBLE_END_COUNTERSINKS` (44, by order
  number), `countersink_rows()`; `python3 tools.py 8080 countersinks`.  Outline on a
  plane with sketch X out and Y up, with true arcs; `solid.revolve` with an axis
  at the tip.  `sctoolmodel.model()` uses short lines, so it was not reused.
* Not from the catalog, Claude's readings: the small drill reaches its own
  diameter from the tip (the usual proportion, from memory); the
  radius type's arc is tangent to the body, reaching the drill (its 60 degrees is
  kept as data but does not shape it: 83-88 degrees where the arc meets the drill).
  Flutes left out.  `left_hand` is data only, without flutes.

## 2026-10-31: Countersink tips

* The user saw errors at the tips in the GUI, where the revolve comes to a point on
  its axis.  The user's first idea, flat ends and one 90 degree cut for both caps, was
  tried: 44 of them did not finish in 2 minutes headless (about 3 s before), and the
  user stopped it before finding out why.  The user: give up on a perfect point; "just
  good enough".
* Now each tip has a flat 5 % of the small drill's diameter across
  (`COUNTERSINK_TIP_FLAT`), a 90 degree point (`COUNTERSINK_POINT_ANGLE`), all in one
  revolve.  `largest_countersinks()`; `python3 tools.py 8080 largest`.

## 2026-10-31: The radius type is now a plain cone

* The user, looking at the largest (421-0261): the larger section should be a pure
  cone, not curved.  So the arc from the catalog's Radius column is gone from all of
  the radius type, each with a straight 60 degree cone; `radius` stays as data only.
  Earlier entries' arc tangent to the body no longer applies.  With no arcs, all 44
  are one closed line and one revolve.  `python3 tools.py 8080 421-0261` shows one.

## 2026-10-31: Where things stand

* The user on all 44 countersinks: "They look great."  Next tool: the user's choice.
  Drills and end mills could share a grooved cylinder routine; countersinks have no
  flutes.  The small drill's length is still from memory, not the catalog.

## 2026-11-02: Holders

`sctoolmodel.py` draws a rough holder for each tool of the shop, in the resistor color code of its `unique_id`,
under `T.ctfs~5.1`, which has the details.

## 2026-11-02: Drills as plain bodies with lines for flutes (experiment)

* The user: simplify the drills by drawing lines or arcs on the surface in place of flutes; three examples, 2 and
  3 flutes.  `probe_helix.py` (nothing else changed): a plain cylinder with `SCDrill`'s cone cut, and a 3D sketch of
  each flute edge: a right hand helix from shoulder to shank, closing to the flute's center over the last diameter,
  then a straight lip to the tip.  1/4 x 4 with one line per flute; 1/2 x 6 and 3/4 x 8 (3 flute) with two.
* `sketch.spline3d` and `sketch.arc3d` exist in SolidCraft 0.25.1, so a helix need not be short lines: `--spline`
  (12 points a turn, `sketch.spline3d`) looks smoother in a capture than 48 lines a turn, in the same time.
* Lines stand 1 % of the radius off the surface (`LIFT`), since facets cut inside the circle.  Body about 0.5 s, the
  lines about 0.01 s a drill (grooved drills were about 3 s, as noted above).  The lines are sketches, not on the body:
  moving a drill means moving its sketch too (not tried), and `SCDrill.model()` is unchanged.
* Helix angle: 30 degrees, from memory.  No drill page of `SharsMD` converted so far gives one: "helix", "spiral" and
  "parabolic" do not appear on pages 1-33, where the index (pages 451-455) puts the twist drills.  They give flute
  length, overall length and point angle (118, 135).  End mill pages often do give a helix (30, 32, 45).
* Seen in captures, from above only: helices on all three.  The tips and the run-outs were not in view.

## 2026-11-02: Sub-assemblies: components, nested

* SolidCraft has components with occurrences, nested with `parent`.  Tried on the open drills (`probe_helix.py --spline`):
  `component.from_bodies` plus `component.move_sketches` on the 1/2 x 6, moved -50 mm; `component.create` of `T1 assembly`
  with child `T1 drill`, `component.move_bodies` and `component.move_sketches` into the child, the parent's occurrence moved
  -100 mm.  `occurrence.ground(grounded=False)` first where the occurrence is grounded (`from_bodies`' first one was; a
  created one is not).  `component.list` shows each component owning its body and sketch.
* `inspect.center_of_mass` reads exactly -50.000 and -100.000 mm, so bodies follow, nested too.  Whether the sketch lines
  follow on screen: not seen by Claude, the window was covered; there is no command that captures a window.
* The moves are `pending` (`capture=False`), as `SCToolModel.move_to()` has them.

## 2026-11-02: Moving the drills live; line colors

* The user watched two occurrences (body and flute sketch in one component, one nested) moved by `occurrence.move`, asked
  for up to 20 Hz each; about 45 s, until SolidCraft closed.  Per move: about 109 ms for the first 200, 62 ms for the next
  200, then about 14 ms, by which point the 20 Hz was met.  Why it sped up is not known.  The last move timed out as
  SolidCraft closed.  Whether the lines followed: waiting on the user's word.
* Sketch lines have no color in 0.25.1: none of `engine.commands`' 493 entries sets one.  Why they look white here, against
  the black noted for tool paths, is not known.

## 2026-11-02: The lines follow; a covered window is what was slow

* The user: the lines "are beautiful and move in sync", so a component holding a body and its flute sketch moves as one.
* Rerun with the window raised from the start: 757 moves in 19 s, 13.3 ms each, worst 21 ms, the full 20 Hz from the first
  move (two occurrences).  Covered, it was about 109 ms.  So the slowness was the covered window, as the user thought.
* No `wmctrl` or `xdotool` here: Claude raises the window by sending `_NET_ACTIVE_WINDOW` through `libX11` with `ctypes`.

## 2026-11-02: Every tool's flutes as lines

* The user: lines in place of grooves on the other tools, and an example of each moving.  Only `SCDrill` ever had grooves; the others
  were plain revolves.  `sctoolmodel.py`: `flute_path()`, `flute_runs()`, `tool_flute_runs()`, `flute_steps()`, `as_component()`;
  `SCDoubleEndCountersink.flute_runs()` in `tools.py`.  `model_shop_tools()` and the countersinks' `model()` now draw them.
* Claude's choices: two edges a flute for a helix, one line for straight flutes; helix 30 degrees for end mills and drills, others
  straight; 2 flutes for drills and countersink ends (all from memory; the tools files have no helix key, and drills no `flutes`).
* `probe_flutes.py` (replaces `probe_helix.py`): one of each kind as a component, moved by one `engine.batch` a frame.  Eight tools at
  20 Hz, about 16 ms a frame, window in front.  Whether the lines look right on the small tools: the user's eye.
* Not changed: `SCDrill.model()` (grooved), `SCToolModel` in `sim_solidcraft.py` (no lines).

## 2026-11-02: No lines on the tips

* The user: the tip ends "didn't look so good", so they are gone.  Helical flutes start at the shoulder (the end of a square end mill, a
  ball's and a drill's point are bare); straight fluted tools start past the flat on the tip, so the V or hollow keeps its line; a
  countersink's lines start where its small drill's point ends.

## 2026-11-02: One way to model a shop's tool

* The user asked why the fix needed two places.  `sctoolmodel.model_tool()` (returns `SCModeledTool`: `body`, `sketch`, `occurrence`,
  `items()`) is now the one path: body, color, lines, component.  `SCToolModel`, `model_shop_tools()` and `probe_flutes.py` all call it, so
  `show_demo.py`'s tool has lines, hidden and shown with its body.  `SCDrill` (grooved) and `SCDoubleEndCountersink` remain outside it: they
  are not read from the shop files, the very thing `T.ctfs~5.1` is to change.
* Checked: `SCToolRack` built all 8 tools in the GUI; T1, T2, T1 in turn; a capture shows T1 with its lines.  `show_demo.py` came up with the
  panel stopped.  A whole run with lines has not been seen by Claude.  Tests not run (the user's word: not on each small change).

## 2026-11-02: Where things stand; saved for the user's commit and a `/clear`

The user ran `./show_demo.py` with Start: "It was very good."  Done: `sctoolmodel.model_tool()` models a shop's tool as a plain body with flute
lines, in one component, used by `show_demo.py` (`SCToolModel`), `./sctoolmodel.py 8080` and `./probe_flutes.py 8080`.  No lines on tips (the user's
word).  Whole suite: 401 tests pass, 10 skipped (the `SCRAFTCNC_LINUXCNC` ones; so `test_lcnc_end_to_end` was not run).

Still to do: `SCDrill.model()` cuts real grooves (`./tools.py 8080`), and `SCDoubleEndCountersink` builds its own body; both wait on `T.ctfs~5.1`.
The helix angle (30 degrees), and 2 flutes for drills and countersink ends, are from memory; the tools files have no helix key.  Not known: why sketch
lines look white here, against the black noted for tool paths; SolidCraft has no command to color a sketch line (0.25.1), and its release notes to
0.30.1 mention none.  SolidCraft 0.30.1 is out; 0.25.1 is what runs here.

Claude's ways, for next time: a covered SolidCraft window is slow (about 109 ms a move against 13 ms), so raise it.  There is no `wmctrl` or `xdotool`:
send `_NET_ACTIVE_WINDOW` with `ctypes` and `libX11`.  `xwd -root` piped through Pillow captures it once it is in front.
