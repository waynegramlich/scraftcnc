# LLM Agent Context Log

## 2026-10-25: README steps 1 and 2 done

* `solidcraftcnc.py` (library, no EZPkg bootstrap): `SCLine`, `SCArc`,
  `SCCorner`, `SCRoundPoly` (computes its own line/tangent-arc
  outline; `sketch()` draws it into a `PySolidCraft` sketch), `SCCNC`
  (RS-274 commands as dicts; mm, G90, G17, G94, I/J relative; no
  cutter compensation yet; `contour()` follows an outline at one Z).
* `solidcraftcnc_demo.py` (program, with the bootstrap): G-code to
  stdout; with `PORT` or `headless` also sketches and extrudes in
  SolidCraft.  Headless verified: 1 closed profile.
* Why the split: EZPkg's bootstrap stops any run whose `__main__` has
  no bootstrap, so a module with the bootstrap cannot be imported by
  tests.  `pysolidcraft.py` is a symlink next to the program because
  EZPkg only accepts local modules beside the script.
* `mypy --strict` reports 4 errors, all in the bootstrap's untyped
  `g()`; plain `mypy` and every other checker is clean.
* Tests: `python3 -m unittest -v` (11 pass).
* Not done yet: self-intersection check; tool radius offset.

## 2026-10-25: Crossings, tool offset, climb milling, Z and speeds

User decisions:
* `mypy --strict` errors in the EZPkg bootstrap are being fixed in
  EZPkg itself; not our problem.
* Tool: 0.25 inch end mill.  Climb milling: the material being cut is
  to the right of the cutter (outside profiles go clockwise, inside
  ones counter-clockwise).
* Z: `z_top` is the material's top; `z_safe` is above all hold down
  tooling.  Rapid (`G0`, 1 in/s = 60 in/min) is for above the work;
  work speed (`G1`/`G2`/`G3`, 0.2 in/s = 12 in/min) is for anywhere
  the cutter may be removing material.  Spindle `M3 S1200`.

Done:
* `SCRoundPoly` now refuses outlines that cross or touch themselves
  (line/line, line/arc and arc/arc checks of every segment pair),
  and has `reversed()` and `offset(distance)` (radii grow on convex
  corners, shrink on concave ones, clamped to sharp; an edge that
  turns around raises `ValueError`).
* `SCCNC` works in inches (`G20`); settings `z_top`, `z_safe`,
  `tool_diameter`, `rapid_speed`, `work_speed`, `spindle_rpm`;
  `profile(poly, bottom, step, inside)` offsets by the tool radius,
  picks the climb direction, rapids at `z_safe` and down to `z_top`,
  then passes of at most `step`; `minutes` estimates the run time.
* SolidCraft sketch coordinates are always mm (unit-less extrude
  distances follow the design units), so `sketch()` takes
  `mm_per_unit`; the demo models a 3 x 2 x 0.5 in plate with a hole,
  verified headless by STEP extents (Z -0.5 to 0).
* 19 tests pass; all checkers clean (bar the bootstrap's 4 `mypy
  --strict` errors).

Open: lead-in/lead-out (the tool currently plunges on the path),
whether to rapid to `z_top` or a little above it.

## 2026-10-25: Lead-in/lead-out and rapid clearance

User decisions:
* #4: lead-in is a half arc (semicircle) whose diameter equals the
  tool diameter.  Implemented with a matching half-circle lead-out,
  both on the cutter's left (the waste side), counter-clockwise,
  together one circle; the lead-out ends where the lead-in starts, so
  each pass plunges there.  The loop starts in the middle of the
  path's longest segment (always smooth there).  A lead that would
  cross the path raises `ValueError`.
* #5: rapids down stop `clearance` (default 0.05 in) above `z_top`;
  the rest of the way is at work speed.

19 tests pass; checkers clean.  Demo estimate: about 5.0 minutes.

## 2026-10-25: Pockets (README step 4)

User decisions: pockets are cleared by smaller and smaller rings, each
edge moved in by `stepover` (default 0.9) of the tool diameter; the
rings come apart into a tree, cut smallest to largest.  #7: compute
the rings with the classic offset (move segments, split at crossings,
drop pieces too close to the edge, chain the rest).  Everything will
eventually be parameters.

Done:
* `scgeometry.py` (new): the geometry moved out of `solidcraftcnc.py`
  (helpers now public), plus `SCLoop` (closed loop of lines/arcs that
  may meet at angles) and `inset(loops, distance, name)` (the classic
  offset; region on the left of each loop, so islands for step 5 are
  clockwise loops in the same call).  Verified against brute-force
  areas (dumbbell splitting, L shape, rounded squares).
* `solidcraftcnc.py`: `SCRing` tree, `plan_pocket()` (wall ring a tool
  radius in; children `stepover` in; last rings = `inset(ring,
  radius)` where the middle would be left uncut; spurs out from sharp
  convex corners, found by walking the bisector until another ring's
  cut is reached), `cut_order()`, `SCCNC.pocket()`.
* Defaults chosen by Claude (user said "crank on it"):
  * #8 corner cusps: spurs (a coverage test showed 90% stepover leaves
    cusps at 90 degree corners without them).
  * #9 middle: last rings follow the uncut region's outline.
  * #10 entry: ramp along the smallest ring itself at no more than
    `ramp_angle` (default 3 degrees), whole laps, helical `G2`/`G3`
    with Z.  Rings shorter than `SMALL_RING` (2) tool diameters are
    cut after their parent (entered sideways at depth), and the
    parent is ramped instead.
  * #11 moves between rings: stay down when the straight move crosses
    no wall ring (rise to the last cleared depth first when going to
    a ring to ramp); otherwise retract to `z_safe`.  Above the
    material (first depth, `z_top + clearance`) the move is a rapid.
  * #12 order: every ring at each depth before going deeper.
* Demo: 4 x 3 in plate with a dumbbell pocket 0.25 deep, hole, and
  outside profile; headless model checked by STEP (pocket floor at Z
  -0.25 over 0.4..2.6 x 0.4..1.9).  About 10.4 minutes.
* Tests: `test_scgeometry.py` and `test_solidcraftcnc.py`, 31 pass,
  including a brute-force coverage test (no uncut points at stepover
  0.5, 0.9 and 1.0 for a dumbbell, triangle and square).

Open: islands (step 5); profiles still plunge straight down at the
lead-in start (no ramp); off-bisector cusps are not checked (the
coverage test found none).

## 2026-10-25: Tool path plot (README step 6)

* `scplot.py` + `scplot_template.html`: `plot_html(cnc, outlines,
  title)` / `write_plot()` make a self-contained page (vanilla canvas,
  no libraries): 3D view (turn, pan, zoom; Iso/Top/Front; Z
  exaggeration), rapids dashed orange, cuts shaded by depth, tool
  circle, play/scrub by estimated time, G-code listing in step.
* `./solidcraftcnc_demo.py --plot FILE.html`.
* Demo plot published: https://claude.ai/artifact/4JmpGaAtAvyDds8W7r8ia8
* User decision (entry): pre-drill each plunge point with a drill and
  let the end mill drop into the hole (easier on the end mill) -- to do.
* 33 tests pass.

## 2026-10-25: Tool path in the SolidCraft GUI

* SolidCraft 3D sketches: `sketch.create(plane="XY")`, then
  `sketch.options(sketch_3d=True)`; `sketch.line3d(points=[...])`
  (one wire per segment) and `sketch.spline3d(points=[...])`; no 3D
  arc command, so arcs/helices are splines through 5 degree points.
  World coordinates are mm.  `browser.visibility(items=[name])` shows
  and hides sketches; `appearance.assign(bodies, color, opacity)`.
* `scplot.sketch_path(solidcraft, cnc, mm_per_unit)`: two 3D sketches
  per operation (named after its comment): "<op> cuts", "<op> rapids".
* Demo `model()` draws the path and makes the plate 35% opaque.
  Headless: pocket cuts sketch has 198 wires; whole demo under 2 s.
* EZPkg trap: a script whose local module is not beside it (e.g.
  `scplot`) gets an unrelated PyPI package of that name (PyPI has
  `scplot`).  Only seen in scratch probes; the project's own files win.
* 34 tests pass.

## 2026-10-25: Seeing it in the GUI

* The user likes to see results in the SolidCraft GUI: start it with
  `solidcraft/solidcraft --control 8080` (in the background; it opens
  on the user's display), then `./solidcraftcnc_demo.py 8080`.  The
  demo took 18 s against the GUI.  The user called the result "a work
  of art".
* For Claude to see a picture: `solidcraft-cli mcp --connect
  127.0.0.1:PORT` gives the MCP `screenshot` tool of the running app
  (plain `solidcraft-cli mcp` is its own headless session, whose
  screenshot is an empty design); `solidcraft-cli snapshot` renders a
  design or script to PNG headless (with `--body NAME:opacity=...`).
  Not tried yet.

## 2026-10-25: Colored path (tried, set aside)

* SolidCraft cannot color sketch lines; only bodies and faces take
  `color`/`opacity` (`appearance.assign`).
* `scplot.tube_path()`: each move as a thin `solid.pipe` body along a
  3D sketch of straight pieces (pipes along splines are ~20x slower),
  rapids translucent green, cuts translucent red.  Works headless (47
  s for the demo's 330 moves) but the GUI was far slower (one pipe hit
  the GUI's one minute request limit).  User: "way too
  computationally intensive.  Lines will do for now."  The demo is
  back on `sketch_path()` (about 2 s).
* If revisited: build headless, `file.save` a `.solidcraft`, and open
  it with `solidcraft design.solidcraft`; or fewer, longer pipes.
* The tubes were 0.5 in across, not 0.5 mm: SolidCraft takes a bare
  number as the design's units (inches in the demo), so `tube_path()`
  now sends `diameter` as `"0.5 mm"` (checked headless by STEP: 0.502
  mm; bare 0.5 gave 12.74 mm).  Watch for this with every size
  parameter (extrude distances already pass units).

## 2026-10-25: Tool table, machine preferences, drilled entries (#14)

User decisions: tool change is `T02` alone (some machines will not
rise to a tool change height on their own); the drilling style is a
machine preference, like the tool table; the entry drill is the
largest drill smaller than the end mill (from the tool table); the
table lives in a TOML file for now (Python users can write the TOML).

Done:
* `scmachine.py`: `SCTool`, `SCMachine`, `load_machine()` (tomllib;
  every problem a `ValueError` naming the file), `change_words()` from
  the `tool_change` template (`"T{number:02d}"`), `drill_for()`.
* `machine.toml`: preferences (z_safe, clearance, tool_change_z,
  tool_change, rapid_speed, drill_cycle G81/G73/G83/moves, stepover,
  ramp_angle) and tools: T01 1/4 end mill, T02 1/8, T03 7/32, T04
  15/64 drills.
* `SCCNC(name, machine, z_top)`: `change_tool()` (rise to
  tool_change_z, M5, template words, M3 S rpm), `plunge()` at the
  tool's plunge feed, `drill(points, bottom)` (G98 + canned cycle +
  G80, or pecks as moves), `pocket_entries()`, `profile_entry()`,
  `pocket(..., drilled=True)` plunges at the entries instead of
  ramping.  Settings moved to the machine; feeds per tool.
* `scplot`: moves carry feed and tool; canned cycles drawn (over, down
  to R, G1 to bottom, up); viewer uses per-move feed and tool size.
* Demo: T04 drills 4 entries (2 pocket, 2 profile), T01 mills.  Plot
  republished (version 2).  41 tests pass.
