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
