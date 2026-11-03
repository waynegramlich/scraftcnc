# LLM Agent Context Log

## 2026-11-02: Squeezed; where things stand

The user widened this task to model all tooling in SolidCraft, from the table up.  `sctoolmodel.model_tool()` (returns `SCModeledTool`:
plain body, color, flute lines as a 3D sketch, one component) is the one way to model a shop's tool.  Still outside it, until
`T.ctfs~5.1` gives them kinds: `SCDrill.model()` (real grooves) and `SCDoubleEndCountersink`.  `python3 tools.py 8080` shows the tables,
drills, vise, parallels and keep-outs; with `countersinks`, `largest` or an order number (`421-0261`), countersinks.

### Choices to keep

* Tormach tables follow Tormach's drawing, "T-Slot Spacing on Tormach Mills", over conflicting spec sheets (770 slots 50 mm, 440 slots
  10 mm; 460 x 160, 660 x 205, 860 x 240 mm).  Plate thickness and pockets are scaled or assumed.
* Keep-outs: new bodies, `#e03c31`, opacity 0.25.  `SCMachineVise.keep_out()` gives three prisms, grown 1/8 in, overlapping where they meet.
* Flutes are lines (the user: end mills and drills are variations of a grooved cylinder; fly cutters much later).  They stand 1 % of
  the radius off the surface; `sketch.spline3d`, 12 points a turn; none on the tips (the user).  From memory, as the tools files have no
  such keys: 30 degree helix for end mills and drills, others straight; 2 flutes for drills and countersink ends.
* `SCDrill` grooves, if they matter again: `section()` extruded whole, shank joined, then `point_cutter()`, an inverse cone, cut with
  `solid.revolve`.  Cutting circles from a revolved drill or cones on a tip fail in SolidCraft 0.25.1.
* Double end countersinks (Shars page 24): 44 by order number.  The user: each tip a flat 5 % of the small drill across and a 90 degree
  point; the radius type a straight 60 degree cone, `radius` and `left_hand` data only.  The small drill's length is from memory.
* `KURT_D688`: the user's aim is "I know what that is!", and it is met ("That looks like a Kurt vise").  All Kurt vises are 6 in wide
  (the user).  Plates, hex and jaw height have sources (`tools.py`'s comment); the rest is estimates.  The pocket under the opening and the
  slider's start are Claude's readings.  `lift` raises the jaws to see inside.  Left out: jaw block holes, plate screws.
* Parallels: 1/2 to 2 in by 1/8 in, 1/8 in thick, 6 in long; a pair of each height (26) is Claude's reading of "a whole set".

### SolidCraft 0.25.1 findings

* A covered window is slow: about 109 ms a move, against 13 ms in front.  No `wmctrl` or `xdotool`: send `_NET_ACTIVE_WINDOW` with
  `ctypes` and `libX11`.  `xwd -root` piped through Pillow (`BGRX`) captures it; its stripes can hide colors, so the user's eye decides.
* A component with a body and its sketch moves as one (`component.from_bodies`, `component.move_sketches`); unground it first.  One
  `engine.batch` a frame moved eight tools at 20 Hz.
* Sketch lines have no color command.  There is no switch to hide edges, so draw arcs as true arcs.
* Round bodies measure about 1.1 % low in volume.  A revolve coming to a point on its axis shows errors in the GUI.
* `browser.visibility(items=[...], visible=False)` hides bodies.  `timeline.delete(features=[sketch name])` removes a sketch and its
  extrude.

## 2026-11-02: Vise terms and jaw plates

`SCVise` is now `SCMachineVise`: base, body, bed (rails and end blocks), fixed and movable jaws, lead screw, hex; `bed_top()` was `base_height()`.  Jaw plates are their own part, `SCJawPlate` (`KURT_JAW_PLATE`), with counterbored holes cut from the clamping face; each plate in the vise faces the other.  Pages for both are in `Tool_Models.md` (`T.dtm~2.5.2`).
