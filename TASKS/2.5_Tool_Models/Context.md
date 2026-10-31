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
