# LLM Agent Context Log

## 2026-11-02: Squeezed; the log to here, by topic

Older entries were merged and what they superseded was dropped; `hg` and `git` history have the
originals.  The user widened this task to model all tooling in SolidCraft, from the table up.

### Where things stand

* `sctoolmodel.model_tool()` (returns `SCModeledTool`) is the one way to model a shop's tool: a plain
  body, its color, flute lines as a 3D sketch, all in one component.  `SCToolModel` (`show_demo.py`),
  `./sctoolmodel.py 8080` and `./probe_flutes.py 8080` use it.  The user ran `./show_demo.py` with
  Start: "It was very good."
* Still outside it, as they are not read from the shop files, until `T.ctfs~5.1` changes that:
  `SCDrill.model()` (real grooves; `./tools.py 8080`) and `SCDoubleEndCountersink` (its own revolve).
* Next: the user's choice.  Whole suite when last run: 401 pass, 10 skipped (`test_lcnc_end_to_end`
  not run).

### `tools.py` commands

`python3 tools.py 8080` shows the tables, drills, vise, parallels and keep-outs; with `countersinks`,
`largest` or an order number (`421-0261`), countersinks instead.

### Tormach tables

Source: Tormach's drawing, "T-Slot Spacing on Tormach Mills", at
`tormach.atlassian.net/wiki/rest/api/content/4011819206/child/attachment/att4011819222/download`.
Conflicts, decided in the drawing's favor:
* 770 slot spacing: drawing 50 mm (and to scale), PCNC 770 spec 2 in, 770M knowledge base 2-3/8 in.
* 440 slot width: drawing and manual 10 mm, spec sheets 3/8 in.
* Sizes: drawing 460 x 160, 660 x 205, 860 x 240 mm; spec sheets 18 x 6.3, 26 x 8, 34 x 9.5 in.

Scaled from the drawing: plate thickness, pocket size.  Assumed: pockets as deep as the slots, with
square corners.  Left out: the ways, coolant grooves, the 440's corner holes, the 1100's edge T-slot.

### Keep-outs

Shown as new bodies, `#e03c31` at opacity 0.25.  `SCVise.keep_out()` gives three prisms (the base with
the hex, and each jaw, holding its plate), grown 1/8 in, overlapping where they meet.  The moving jaw's
reaches the end of the hex.

### Flutes

* The user: end mills and drills are all variations of a grooved cylinder; fly cutters wait until much
  later.  Flutes then became lines on a plain body, about 0.5 s a body against 3 s for a grooved drill.
* The lines stand 1 % of the radius off the surface, since facets cut inside the circle.
  `sketch.spline3d` (12 points a turn) looks smoother than 48 lines a turn, in the same time.
* No lines on the tips (the user: they "didn't look so good").  Helical flutes start at the shoulder;
  straight ones past the flat on the tip; a countersink's where its small drill's point ends.
* Claude's choices, from memory; the tools files have no helix key, and drills no `flutes`: two edges
  a flute for a helix, one line for straight flutes; helix 30 degrees for end mills and drills, others
  straight; 2 flutes for drills and countersink ends.  `SharsMD` pages 1-33 give no drill helix; end
  mill pages often do (30, 32, 45).
* `SCDrill` grooves, if they matter again: `section()` (true arcs) extruded whole, the shank joined,
  then `point_cutter()`, an inverse cone, cut with `solid.revolve`.  Cutting circles from a revolved
  drill, intersecting with a cone, and grooves cut through a coned tip all fail in SolidCraft 0.25.1.

### Double end countersinks (Shars page 24)

* 44 by order number (`SharsMD/page_024/page_024.md`, tables 421-0130, 421-0141, 421-0388, 421-0138),
  checked once against the page by a one-off script (`SharsMD` is in neither version control).  The
  user: "They look great."
* The user's calls: each tip has a flat 5 % of the small drill's diameter across and a 90 degree point
  ("just good enough"; a true point showed errors in the GUI, and separate cuts did not finish in 2
  minutes); the radius type is a straight 60 degree cone, with `radius` kept as data only.
* Not from the catalog: the small drill's length (it reaches its own diameter from the tip, from
  memory).  `left_hand` is data only.

### `KURT_D688` and parallels

* The user's aim: not a perfect model, one where you say "I know what that is!"  Their verdict: "That
  looks like a Kurt vise."
* From used machinery listings: 1.735 in jaw height, 8.8 in opening, 16.75 x 8.25 x 4.375 in overall.
  The user: all Kurt vises are 6 in wide, so the 8.25 in is not used.  The user's pasted notes, source
  not given, for plates: 3.875 in hole centers, 1/2-13 or M12, hole centers 0.940 to 1.625 in up, 6.0
  in long, about 0.725 in thick.  Shars page 317: 3/4 in handles for Kurt vises.  Everything else in
  the numbers is an estimate.
* Claude's readings, not the user's: a pocket through the middle layer under the opening (the user did
  not answer whether it is hollow), and the slider starting at the jaw's clamping face.  `lift` is
  there to raise the jaws and see inside.
* Left out: holes in the jaw blocks, the plate screws, joining the slider to the moving jaw.
* Parallels: 1/2 to 2 in by 1/8 in, 1/8 in thick, 6 in long; a pair of each height (26) is Claude's
  reading of "a whole set".

### SolidCraft 0.25.1 findings

* A covered window is slow: about 109 ms a move, against 13 ms in front.  There is no `wmctrl` or
  `xdotool`: send `_NET_ACTIVE_WINDOW` with `ctypes` and `libX11`.  `xwd -root` piped through Pillow
  then captures it; its colored stripes can hide colors, so the user's eye decides those.
* A component with a body and its flute sketch moves as one, nested too (`component.from_bodies`,
  `component.create`, `component.move_bodies`, `component.move_sketches`); the user saw the lines move
  in sync.  `occurrence.ground(grounded=False)` first where it is grounded (`from_bodies`' first one
  is).  One `engine.batch` a frame moved eight tools at 20 Hz, about 16 ms a frame.
* Sketch lines have no color command (none of `engine.commands`' 493; release notes to 0.30.1 mention
  none).  Why they look white here, against the black noted for tool paths, is not known.  SolidCraft
  has no switch to hide edges, so draw arcs as true arcs: short lines show as lines along a body.
* Round bodies measure low (plain cylinders about 98.9 %; `inspect.center_of_mass` about 1.1 % low),
  so compare volumes with that in mind.  A volume check once caught an outline that lost its tip.
* A revolve coming to a point on its axis shows errors in the GUI.
* `browser.visibility(items=[...], visible=False)` hides bodies.  `timeline.delete(features=[sketch
  name])` removes a sketch and its extrude, to swap a body with no `file.new`.
