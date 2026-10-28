# LLM Agent Context Log

Moved from `T.s2~3`'s `Context.md` on 2026-10-28, when it was split.

## 2026-10-27: Step 1 done: moving an object in SolidCraft

* Make the moving body a component (`component.from_bodies`; a body
  `Cube` gives occurrence `Cube:1`) and move it with
  `occurrence.move(occurrence=..., space="world", translate=[...],
  capture=False)`: no timeline features, the placement stays a
  pending move.  `solid.move` adds a timeline feature per call (21
  after 20 moves), so it is ruled out.
* `occurrence.properties(occurrence=...)["total"]["bbox"]` reads the
  placement back (world coordinates, pending moves included).
* Timing: headless about 0.8 ms per move.  In the GUI, a move
  answers in 2-7 ms when moves are 1 s apart, but back to back each
  takes about 50 ms: about 20 updates a second (probably one per
  redraw).  1 mm steps of a 20 mm cube looked smooth.
* So the simulation should update on time (poll the position, move
  the tool there) at about 20 Hz, not step by fixed distances.  Not
  yet checked: whether `matrix` gives an absolute placement, which
  would keep errors from adding up.
* A first run "moved the origin, not the cube": with no fixed
  reference, the view could not tell which moved.  A second, fixed
  `Reference` cube and `view.apply(view="iso")` settled it.
* `solidcraft` and `solidcraft-cli` are not on the `PATH`: the GUI is
  `../solidcraft/solidcraft` (the AppImage), and `solidcraft-cli` is
  in `../solidcraft/squashfs-root/usr/bin/`.

## 2026-10-27: Moved here from `T.tl~3.2` (2026-10-28)

* `sim_move.py` (step 1's two scratch scripts in one: `--method
  pending|captured|solid`, `--step`, `--interval`, `--trips`,
  `--report`).  Checkers clean; no unit tests (it needs
  SolidCraft).
* After the demo first ran in the shop mill simulator, the next step
  was the SolidCraft side: a tool stand-in moved to each sample.

## 2026-10-27: Step 4: the tool follows in SolidCraft

* `occurrence.move` with `matrix` is relative too (two identical
  matrices moved the cube twice), so `ToolModel` keeps the last
  position it sent and sends the difference (mm); no move when the
  tool has not moved.
* `sim_linuxcnc.py --solidcraft PORT`: a 1/4 x 1.5 in orange
  cylinder (`solid.cylinder`, made a component, its occurrence found
  through `component.list`), tip at the program's zero; polls keep a
  fixed 20 Hz schedule.  Run as in its docstring, after
  `./solidcraftcnc_demo.py 8080 > demo.ngc` modeled the plate (38 s).
  The user: "It worked perfectly" (watched about 55 s at `--speed
  5`, 20 samples a second, largest gap 0.09 s).
* The user closed SolidCraft expecting the run to stop; it did not
  (the move in flight got `SolidCraftError` "timeout ... still
  running in the app", and LinuxCNC carried on).  Now SolidCraft
  going away (`SolidCraftError`, `OSError`) or Ctrl-C stops the
  program (`Simulator.stop()`: `command.abort()`).  Ctrl-C checked;
  the SolidCraft path not yet checked live.
* Testing trap: a background job in a non-interactive `bash` ignores
  SIGINT; `set -m` first.

## 2026-10-27: The real tools in SolidCraft

* The user asked for real tool shapes (sizes from the tool table, a
  cone at a drill's tip from its `point_angle`).  This does much of
  `T.tm~2.5` (Tool Models) early.
* `shops.loaded_tools(shop, machine)`: T number -> (tools file list,
  description); `cnc_machine()` uses it (and `_machine()`).
* `sctoolmodel.py`: `profile(key, tool)` gives `(r, z)` points
  (inches, tip at 0, closed down the axis) for end mills (square or
  ball), drills (cone from `point_angle`), chamfer mills (cone to
  `tip_diameter`), corner rounding mills (hollow quarter circle),
  double angle cutters (head, neck, shank), anything else a cylinder;
  arcs as 8 lines.  `model()` sketches it on XZ (sketch Y is world
  -Z, found by a probe) and revolves it about Z.
  `test_sctoolmodel.py`: 8 profile tests and a headless model test.
* `sim_linuxcnc.py`: `ToolRack` models every loaded tool (`T1`...,
  orange, each a hidden component) and shows the one in
  `stat.tool_in_spindle` (`browser.visibility`), moving it into place
  before showing it.  Headless: 8 tools in 0.16 s.  In the GUI the
  demo ran through at `--speed 5`: 355.3 s, 7044 samples, no errors.
* The user, after watching: "a work of art", "a win"; on par with
  LinuxCNC's view, and better in one way: the tool and the solid are
  both there, so they can be seen touching at the surface.  The
  118 deg drill points looked flat at plate scale (the cone is only
  0.070 in tall); up close they are cones, with three line
  artifacts 120 deg apart (taken as SolidCraft's).
* What LinuxCNC still has: the path traced in real time, and XYZ
  axes at the work origin.  SolidCraft's own origin axes already sit
  at the program's zero (work coordinates are SolidCraft's).  No
  command colors sketch lines (only bodies: `appearance.assign`,
  `material`), so a colored live trace would need thin bodies, or an
  uncolored one sketch lines; not done.

## 2026-10-27: The live trace (in progress, struggling)

* The user wants the path drawn as the tool goes (stretching the
  last line), and the planned path kept, to see problems beforehand.
  No automated plunge check (the user: it would not find anything).
* `sketch.line3d` makes a 3D wire (`w1`, id in `"curves"`);
  `sketch.move3d(wire, index=1, to=[x, y, z])` stretches it;
  `sketch.construction` refuses 3D wires ("unknown curve"), so no
  dashed lines.  No command colors sketch lines.  `file.new(name=)`
  starts a fresh design without closing the window.
* Speed: headless a stretch costs 0.4 ms (2 ms at 600 segments), and
  a component moves fine while the sketch is open.  In the GUI every
  command takes about 50 ms (one per frame), but two connections in
  parallel threads each get 20 a second.  So `LiveTrace` has its own
  connection and thread; new segment on a new G-code line or a turn
  of more than `TURN` (5 deg, measured from the last step, not the
  segment start, which hid turns); a backlog skips stretches, never
  corners.  Headless check: square + quarter circle = 15 segments.
* GUI runs at `--speed 5` both fell from about 17 to 1.3 samples a
  second (each command about 600 ms), first at about 15 s (pecking,
  line 15, recovered), then for good at the first tool change (line
  25, `T08 M6`, about 45-60 s), until a command failed and the
  program was stopped.  The runs without the trace went through every
  tool change.
* Tried (did not help): the user's idea, grab squares at every point
  overwhelming SolidCraft: `sketch.options` with `show_points`,
  `show_profile`, `show_constraints`, `show_dimensions` off, and a new
  sketch every `SEGMENTS_PER_SKETCH` (50) segments.
* Suspect: `browser.visibility` (the tool change) while the trace's
  sketch is open.  Probe written (scratch `vis_probe.py`: time
  stretches and moves before and after hiding a body with a sketch
  open, then after finishing it), not yet run: the user closed
  SolidCraft both times.  The run now prints SolidCraft's error text.
* `sketch.options` reports `show_points: false` after it is set, but
  the user still saw grab squares (3D sketch points ignore it?).
* With `SEGMENTS_PER_SKETCH` 5 it was worse: 7.6 samples a second in
  the first 15 s, then about 1 a second from the start of the
  pecking; the user had it killed (SIGINT to `sim_linuxcnc.py`, which
  stopped the program; SolidCraft terminated).  So more, smaller
  sketches cost more, not less: the slowness seems to grow with the
  number of sketches (timeline features) and segments in a design as
  heavy as the demo's, not with what the open sketch shows.  The
  earlier 300 segment GUI probe, in a nearly empty design, stayed at
  50 ms a command.
* SolidCraft's source (shallow clone of tangency-labs/solidcraft,
  9fb41f8, 2026-10-28, newer than the user's 2026-10-22 AppImage;
  a few minutes' look, the user's 10 minute cap):
  * `Session::execute` (`crates/engine/src/lib.rs`): a command that
    changes the document gets `refresh_from()` -> `refresh()`:
    `model.evaluate_shared()` (skips only when the geometry inputs
    are the same, which a sketch edit is not), then
    `pin_body_names()` over every feature.  Only appearance or
    visibility changes take the cheap `refresh_render` /
    `refresh_display`.  Each change also pushes an undo snapshot.
  * `sketch.move3d` / `line3d` go through `edit_solved()`
    (`cmd/sketch.rs`), which clones the whole `Document` and solves
    the sketch.
  * The display's `WorldCache` matches only the same `Document` Arc
    and the same `pending_moves` (`lib.rs` `matches()`), so every
    stretch and every tool move misses it; with pending moves,
    `world_state()` clones the document again to place them.
  * So each trace stretch is a full model refresh and world rebuild,
    and the cost grows with the design (the plate, the ~600 segment
    planned path, the tools, each trace sketch a feature): fits the
    collapse, and 5 segment sketches being worse.
* At the user's word, SolidCraft updated to v0.25.1 (released
  2026-10-28 01:45Z, just after the commit read), SHA-256 checked
  against the release's `SHA256SUMS.txt`:
  `../solidcraft/solidcraft-linux-x86_64.AppImage` (the `solidcraft`
  link), re-extracted to `squashfs-root/` (`solidcraft-cli 0.25.1`);
  the old one kept as `solidcraft-0.20.0-linux-x86_64.AppImage`
  (untracked there), the old `squashfs-root` removed.  All tests pass
  (scraftcnc 89, scraftpybind 32); every command the simulation uses
  is still there (407 -> 493 commands, none gone); `scraftpybind` is
  still generated from 0.20.0.  Not reported to SolidCraft yet (the
  user's choice).  Next: with 0.25.1, a trace that adds finished
  segments only (no stretching).
* `LiveTrace` rewritten (no stretching): segments are found as
  before (new line, or a turn of more than `TURN` from the last
  step), but only finished ones are drawn, every `FLUSH` (0.5 s), as
  one `sketch.line3d` through their corners; the segment the tool is
  on waits until it is finished (the last at `close()`);
  `SEGMENTS_PER_SKETCH` 100.  Headless on 0.25.1: the square and
  quarter circle are always 15 segments (1 command unpaced, 8 at 20
  samples a second, 4 sketches at 4 a sketch).  Not yet run in the
  GUI.
* First 0.25.1 GUI try: modeling the plate timed out after 2 1/4
  minutes in `scplot.py`'s `sketch.line3d` ("still running in the
  app").  Likely not 0.25.1: a killed SolidCraft leaves crash
  recovery in `~/.local/share/solidcraft/recovery/` (`ID.json`,
  `.lock`, `.solidcraft` or `.sc`) and a stale `control/current.pid`;
  the next start prompts to recover or discard (the user: "always
  prompting me to discard the failure"), and the control port
  probably waits behind that prompt.  One left was the killed 5
  segment trace run, 95 features.  Removed both sets and the pid
  file (no SolidCraft running; `app.ron`, the settings, kept).  Clear
  them before starting a GUI after a kill.

## 2026-10-27 (evening): Reboot

* The user rebooted at about 20:30: the load average was over 27,
  from test processes that did not die (which ones is not known; the
  notes stop before it).  After the reboot: no SolidCraft, LinuxCNC
  or `sim_linuxcnc.py` processes, the recovery folder empty, stale
  `control/8080.pid` and `current.pid` (20:24) to clear before a GUI
  start.  The `lcnc` box must be entered again.
* The SolidCraft source clone (9fb41f8) was in `/tmp` and is gone;
  only the findings above survive.  Re-clone into a lasting place
  (not `/tmp`) if more reading is needed: `git clone --depth 1
  https://github.com/tangency-labs/solidcraft`.
* Still to do, in order: make every exit path (a failed command,
  SolidCraft gone, Ctrl-C) stop the `LiveTrace` thread and close its
  connection and any headless `solidcraft-cli`, checked with `pgrep`
  after each run; a plain GUI run on 0.25.1 (no trace); then the
  batched trace in the GUI.
* New rule (the user's): check the load average is under 5 before
  any test, and `pgrep` for leftovers after.
* The user's idea: a pool of short segments made beforehand, parked
  out of view, moved into place to draw the trace.  As sketch lines
  (`sketch.move3d`) it is no better: each edit is a full refresh.  As
  bodies moved by `occurrence.move` it may work: that is how the tool
  moves, at 20 Hz with no trouble.  Unknowns: whether the cost of a
  move grows with the number of moved components (`world_state()`
  places every pending move), and whether `matrix` can scale.  To be
  probed headless, then in the GUI, with 0, 100 and 500 parked beads.
* The user's #4 (2026-10-27 evening): draw the planned path beforehand
  as small hidden 3D sketches, and show each (`browser.visibility`,
  "not an undo step") as the tool reaches it; no edits during the
  run.  `probe_reveal.py` (kept in the project) times it: N sketches
  of 5 segments, hidden, then shown one by one while a cylinder
  component moves at 20 Hz; it exits itself if a command takes over
  `--slow` (2 s) or the reveal passes `--limit`.
* Trap: a design's first component is grounded, and
  `occurrence.move` refuses it ("is grounded: unground it first");
  `occurrence.ground(occurrence=..., grounded=False)`.  The sim never
  saw it, since the plate came first.
* Headless (0.25.1): 100 sketches built in 0.2 s; show 2.4 ms, move
  0.9 ms, flat through the reveal.  500 sketches built in 3.5 s; show
  5.3 ms (grows a little with the sketch count), move 0.4 ms, flat.
  Next: the same in the GUI, empty design, then with the plate.
* GUI (0.25.1, started by Claude after clearing the stale pid files),
  empty design, 100 sketches: built in 8.5 s; show 15-17 ms, move
  16-18 ms, flat to the end; load 1.3.  Next: with the demo's plate.
* GUI with the demo's plate (modeled in 15 s on 0.25.1, vs 38 s on
  0.20.0) plus 300 hidden sketches (built in 25.0 s): show 4-8 ms,
  move 11-16 ms (max 27 ms), 1200 moves at 20 Hz with no slowdown;
  load peaked at 2.6.  So #4 works: the reveal costs nothing like an
  edit.  The SolidCraft GUI is still running (the user's screen).
* Plan: `RevealTrace` in `sim_linuxcnc.py` in place of `LiveTrace`:
  each move of the planned path (`scplot.path_moves()`, which knows
  its G-code line) its own hidden 3D sketch, built before the run
  (the demo's ~330 moves, about 30 s), shown when `stat.motion_line`
  reaches its line.  No second connection or thread needed.
* The user watched the probe: "refreshed blindingly fast"; glad the
  GUI did not start full screen.  Go-ahead for `RevealTrace`.
* `RevealTrace` written (`LiveTrace`, its thread, second connection,
  `TURN`, `FLUSH` and `SEGMENTS_PER_SKETCH` gone): hides the
  `sketches` folder, then one hidden 3D sketch per G-code line that
  moves ("Trace 27"), shown when `motion_line` (taken as counting
  from 1; not yet checked) reaches it; all shown at the end.  It reads
  the `.ngc` itself: `scplot.read_gcode()` (text to commands, one per
  line) and `scplot.command_moves()` (what `path_moves()` now calls);
  `scplot._draw()` is now `draw_moves()`.  `test_read_gcode`: a
  program's G-code reads back into the same moves.  90 tests pass.
  Next: a live run.
* Trap: after a reboot, the first `distrobox enter lcnc` sets the box
  up; a second one at the same time left both stuck at "Setting up
  read-write mounts" (the box's log said `container_setup_done`).
  Killing them and entering once worked.  Enter once, wait, then
  start LinuxCNC.
* First live `RevealTrace` run (21:01, `--speed 5`, GUI 0.25.1, plate
  modeled first): 558 trace sketches built in 47.5 s; then 19.96
  samples a second, largest gap 0.07 s, through the first tool change
  (line 25) where `LiveTrace` collapsed; load about 2.5.
* That run stopped at 215 s (line ~330), at the change to T1:
  `occurrence.move` refused "T1:1 is grounded" (0.25.1 grounds a
  design's first component, here T1, the plate being a plain body).
  Up to then: 20 samples a second, load at most 3.7.  The stop path
  worked (program stopped, nothing left running).  Fix: `ToolModel`
  ungrounds its component; the message said "SolidCraft stopped
  answering" for a refused command, so reword it.
* Rerun with the tools ungrounded (21:06): the whole demo ran
  through, 7134 samples in 356.9 s (19.99 a second), largest gap
  0.079 s, every tool change passed, load at most 3.0; trace build
  47.6 s.  Nothing left running.  Not yet known: how it looked to
  the user (does the trace keep with the tool, i.e. is `motion_line`
  counted from 1?).
* The user watched it: the trace kept with the tool ("pleasant to
  watch"), so `motion_line` counting from 1 is right.  Bothersome: a
  long move shows all at once ("suspect fixable").  During the 48 s
  build, each sketch flashed up and vanished, with the whole screen
  flashing and a popup each time ("not THAT annoying").  "Huge
  progress."
* Screenshots (`spectacle -b -n -f -o FILE.png` works, X11): an open
  sketch switches the toolbar to the Sketch tab, opens the sketch
  palette on the right (the "popup"), hides the view cube and labels
  the sketch; `finish` switches back.  The view does not move.  So
  every sketch flashes; no option avoids it.
* `component.insert_design` brings in solid bodies only, and the
  paste commands are within a session, so the trace can not be
  built headless and brought in.
* Next idea: each piece of the path a thin `solid.cylinder` (base,
  axis, height: one command, no sketch mode), colorable, and short
  pieces fix the long-move problem.  Risk: each is a feature
  (a full refresh).  Probing.
* `probe_reveal.py --cylinders`: headless 500 in 4.1 s (4 ms each at
  first, ~12 ms by 500); GUI on top of the plate and the 558 trace
  sketches, 300 in 16.2 s (54 ms each, flat: one a frame); shows
  5-12 ms; but moves grew 16 -> 28 -> 33 ms as more cylinders were
  shown (drawing the bodies costs).
* The demo's path is 4388 pieces (arcs at 5 deg), 318.6 in long
  (cuts 195.6 in); 558 lines that move, the longest 5.6 in.  So
  cylinders for the whole path (about 4 min to build, moves past
  50 ms) are out.  Sketches split by length: at most 1 in 690
  sketches, 0.5 in 946, 0.25 in 1560, 0.1 in 3433.  Better: pieces
  of about L of path each (long lines split, short ones merged):
  about 318.6 / L sketches (0.5 in: ~640, about the build time now).
  Shown when the tool has passed a piece's end (distance along its
  line), so the trace trails the tool by at most L.  Asked the user.
* The user: a whole line showing at once is more pleasant; no
  splitting by length.  `RevealTrace` stays one sketch per line.
  The user asked why the segments can not just be made as needed.
* `probe_reveal.py --live` (a fork of the session, 21:28): makes a
  3D sketch (create, options, line3d, finish) after every `--every`
  moves of a 20 Hz tool run, nothing built beforehand.  GUI, fresh
  "Live probe" design with the demo's plate, 300 sketches, every 12
  moves (about 1.7 a second, the demo's average): a sketch took 73,
  80, then 85 ms (by thirds, max 107 ms: slow growth); moves 9-12 ms
  (max 25 ms); largest gap between move starts 95-119 ms (the tool
  misses one poll per sketch); load at most 2.4; nothing left
  running.  A screenshot mid-run caught the Model tab between
  sketches, the spiral drawn beside the plate.
* Same, fresh "Live probe 4" design with the plate, every 4 moves
  (about 5 sketches a second, a burst like the drilling): a sketch
  took 73, 77, then 82 ms (max 95 ms); moves 11-14 ms (max 24 ms);
  largest gap 95-104 ms; load at most 1.9; nothing left running.
  So on 0.25.1 a sketch made as the tool goes costs about 75-85 ms,
  growing slowly (about 10 ms per 300 sketches), and stalls the tool
  for one poll each (a gap of about 100 ms instead of 50 ms); bursts
  of 5 a second keep up.  No collapse like 0.20.0's.  Live creation
  looks workable at 20 Hz on one connection; the demo's 558 sketches
  would end near 100 ms each.
* The user: probably neither reveal nor live as they are; ask the
  SolidCraft developers to skip the refresh on every change.  Kept
  for the request (not yet written; the user posts, or says to):
  1. A display-only polyline overlay (not in the model, colored):
     the real fit for a tool path trace.
  2. One command for a finished 3D sketch (no edit mode, so no flash;
     1 command instead of 4).
  3. Batching: many commands, one refresh, undo snapshot and redraw.
  4. Colors for sketch lines.
  Lead with the numbers (0.20.0 collapse at 600 ms; 0.25.1: moves
  16 ms, sketches 85 ms, shows 4 ms; the sketch panel screenshot);
  re-clone the source to name current functions.  Keep `RevealTrace`
  until then.
* The user's idea: a `no_refresh` option in the JSON request
  (thought to be under 20 lines).  Note from the timings: headless a
  sketch is about 7 ms (500 in 3.5 s) but 85 ms in the GUI, and a
  GUI show is 16 ms against 2.4 ms headless, so in 0.25.1's GUI most
  of the cost looks like one frame per command (about 16 ms, 60 Hz),
  not the refresh.  Then `no_refresh` alone may save little in the
  GUI; several commands in one request (handled in one frame) would.
  Not checked in the source.
* SolidCraft source re-cloned (shallow, b0c8c46, 2026-10-28T04:16Z)
  to `../solidcraft_src/` (lasting; not `/tmp`).  The user would
  rather send a pull request than open an issue.
* Found: `engine.batch` already exists in the control port
  (`crates/ui-egui/src/control.rs` `batch()`: "the steps in one
  request, so in one frame (#743)"; params `commands` [{command,
  params}], `rollback` (default true: a checkpoint), `timings`,
  `profile`, `coalesce_parameters`; at most 10000 steps; refuses file
  loads; reply `completed`, `results`, `failed`, `undone`).  So the
  GUI does take one request a frame.  `ControlTransport.request(
  "engine.batch", {...})` sends it; headless has only
  `engine.execute`.
* One sketch (create, options, line3d, finish, hide) as one batch,
  `rollback: False`, on the "Live probe 4" design: 45 ms a request
  (vs 85 ms as 5 commands); steps 9 / 12 / 12 / 3.5 / 1.3 ms.  With
  `profile`: 7 / 10 / 7 / 2 / 1 ms (28 ms), all "other" (no boolean,
  no tessellation): refresh, document copies and undo.
* `Session::execute` (`crates/engine/src/lib.rs` ~1195-1250) picks
  the refresh in one `match` (`refresh_live` for sketch edits,
  `refresh_render`, `refresh_display`, else `refresh_from`), then
  `pin_body_names()` for the outermost command.  A `defer_refresh`
  for `engine.batch` (skip both per step, one `refresh()` and pin at
  the end) looks like 20-30 lines; risk: a step that reads the model
  sees it stale.  Not yet built or tried.

## 2026-10-27 (late): Where things stand, for the morning

* Working now: `sim_linuxcnc.py --solidcraft 8080` with `RevealTrace`
  (one hidden sketch per G-code line, built before the run, shown as
  `motion_line` reaches it): the whole demo at `--speed 5`, 20
  samples a second.  Its costs: a 48 s build, with every sketch
  flashing sketch mode.
* Live creation (`probe_reveal.py --live`) also works on 0.25.1, at
  the price of a flash and a ~0.1 s tool pause per new line.  The
  user: probably neither as they are.
* Next, in order (the user's to choose):
  1. Build `RevealTrace`'s sketches with `engine.batch` (one request
     per sketch, or many per request): about 15-20 s instead of
     48 s.  Ask the user whether the 23 batched sketches at 21:43
     (each created and hidden in one request) flashed; if not,
     batching also ends the flash.
  2. Maybe a live trace with one batch per new line (45 ms).
  3. Maybe a pull request to SolidCraft: `defer_refresh` for
     `engine.batch` (see above), measured first with a local build
     of `../solidcraft_src/` (a big Rust build: a background agent,
     with the load kept under 5).  Needs a fork on the user's GitHub
     (ask first).
* Left running at the end of the session: the SolidCraft GUI (port
  8080, design "Live probe 4", unsaved test geometry) and LinuxCNC
  in the `lcnc` box.  A killed SolidCraft leaves recovery files and
  pid files (see above) to clear before the next start; closing
  LinuxCNC pops up a window.

## 2026-10-28: Exploring STEP wire import

Research only (no builds).  `../solidcraft_src/` fetched to `c1dee61`
(2026-10-28T16:59Z, about 50 commits past `b0c8c46`; upstream had
force-pushed `main`); none touch STEP or 3D sketch wires.  Line
numbers below are at `c1dee61`.

* Blocker: STEP import is in `crates/kernel/`, and kernel work is
  paused (`CONTRIBUTING.md:20-27`, pinned issue #3992, 2026-10-21):
  "please don't open new issues, pull requests or discussions about
  ... STEP/IGES import and export, or anything else that changes
  `crates/kernel/`" (they go to `solidcore`, a new kernel).  The
  Part 21 parser and curve reader are `pub(crate)`
  (`step_in/mod.rs:11-12`), so a curve import can not live in
  `crates/io` without a kernel change.  So: no STEP PR for now.
* Upstream search (`gh`): no issue or PR on GEOMETRIC_CURVE_SET,
  wireframe STEP or tool path import.  Related: #7832 (3D lines as
  model geometry, triage: use 3D sketch lines), #7831 (free 3D
  splines), #8040/#8035 (3D sketch buttons), CAM RFC #1153 and its
  PRs (#5751 CAM core, #2881 `cam.*` commands, #4158, #2627 stock
  simulation; none shows a path in the viewport yet).  No sketch
  line colour issue.
* Contribution rules: issue first for anything bigger than a bug
  fix, claim it with a draft PR (`claim: #N`, lowest PR wins), one
  topic, `cargo xtask ci` before every push, a `Changes a default:`
  line, real screenshots (agents capture them), design format
  changes as one file in `crates/doc/src/format/pending/`, new UI
  strings in `assets/locales/pending/`, regression tests in the
  area's existing test file.  Licence MIT OR Apache-2.0 (no CLA or
  sign-off).  AI help is welcome ("much of SolidCraft ... was
  written by AI coding agents (Claude)"); `AGENTS.md` routes agents
  to `skills/`.  No GPL code may be read for it (FreeCAD, ...).
* How STEP import works:
  * Commands: `file.insert_step` (`path`, `name?`, `up?: z|y`,
    `names?: auto|solid|product|instance`, `matrix?`, `tolerance?`;
    `crates/engine/src/cmd/file.rs:31-34`, `insert_step()`
    250-271) and `doc.open` of a `.step` (a new design, 273-).
  * `add_step()` (`file.rs:144-164`) -> `read_step()` (119-122) ->
    `solidcraft_io::step_import_feature_named()`
    (`crates/io/src/lib.rs:227-261`): size check, IGES / native CAD
    restated as STEP, `kernel::step_import_shared()`, names; makes
    `FeatureKind::Import { file, step: Arc<str>, components, skip }`
    (`crates/doc/src/document.rs:1743-1757`), put in a new
    component by `add_in_component()` (`cmd/file_import.rs:237`).
  * The STEP text is the feature: saved compressed in the design
    (`io/src/design.rs:260-264`), re-read on every evaluation
    (`doc/src/eval.rs:7897-7912`, through a 4 entry cache keyed by
    the text, `step_in/mod.rs:1168-1200`).
  * Kernel: `StepReading::with_workers()` (`mod.rs:1236-1290`)
    collects only MANIFOLD_SOLID_BREP, BREP_WITH_VOIDS,
    FACETED_BREP, SHELL_BASED_SURFACE_MODEL (1249, 1272, and
    `rep_bodies()` 683); any other item is skipped silently
    (`_ => {}`, ~736), so curves give no warning.  A file with no
    solids fails: "STEP import: no bodies (the file has no
    solids)" (1316-1322).  Warnings that do exist come back in the
    command's `warnings` and the first 3 as the feature's warning.
  * `step_in/geom.rs:354-420` reads LINE, CIRCLE, B-splines,
    POLYLINE (403) and TRIMMED_CURVE (419, basis only, trims
    ignored), but only as edge geometry for faces.
* 3D sketch wires: `Sketch.wires: Vec<Wire>`
  (`crates/sketch/src/model.rs:731-732`); `Wire` (`wire.rs:49-66`):
  `id`, `pts` (polyline), `space` (World/Component), `link`, `fit`
  (drawn points: 1 point, 2 line, more a spline), `arc` (exact
  `WireArc`).  Reference geometry: not in profiles or the solver.
  Limits: 500 points a `sketch.line3d`/`spline3d` call
  (`MAX_FIT_POINTS`, wire.rs:68), 100,000 points a wire, 20,000
  wires and 1,000,000 points a sketch (`wire_budget()`, 223-234).
  `sketch.line3d` makes one wire per segment of its points
  (`cmd/sketch_3d.rs:103-111`); `sketch.arc3d` an exact arc
  (start, through, end; 125-140).  Both in our 0.25.1.
* No other wire object: `FeatureKind` has no curve or wire body;
  construction axes and points only.  Motion traces
  (`doc/src/motion.rs:21-29`) write a wire into a sketch too.  DXF
  import is 2D only (`io/src/dxf.rs:223-238` keeps X, Y of a
  POLYLINE's VERTEX; Z dropped), into a planar sketch.
  `component.insert_design` brings solid bodies only
  (`cmd/component_link.rs:32-36`); `sketch.paste` is a session
  clipboard.
* Colour and visibility: appearances are by body, face and
  component only (`doc/src/appearance.rs:117-126`).  A wire's colour
  is fixed by state (`engine/src/view.rs:388-398`): drawn and
  active `sketch`, drawn and finished `sketch_done` (black),
  included `sketch_projected` (purple).  `SketchView` has no colour
  (`sketch/src/model.rs`).  Hiding is per sketch
  (`browser.visibility`, `view.rs:812`), not per wire.  The viewport
  passes a colour that is not a theme token straight through
  (`ui-egui/src/viewport.rs:501-519`, `rgba(c)`), so a per sketch
  colour would be easy to draw.
* If the kernel pause ends, the smallest STEP design: in
  `StepReading`, collect GEOMETRIC_CURVE_SET / GEOMETRIC_SET items
  (and wireframe reps) as polylines (sampled with
  `geom::curve()`), returned in `StepImport.wires`; the Import
  feature turns them into a 3D sketch per curve set (no new body
  kind, so no render, pick or export change).  About 200-400 lines
  plus tests (`step_in/tests.rs`, an engine test); risks: a curve
  only file must stop being an error, a sketch made by an import is
  a second feature (undo, delete, reorder), STEP export does not
  write wires back.  A wire body kind instead would touch render,
  selection, export and the format: far bigger.
* Quicker route, no PR: one `engine.batch` per tool: `sketch.create`
  (XY), `sketch.options` (`sketch_3d: true`, points off), a
  `sketch.line3d` per run of up to 500 points (and `sketch.arc3d`
  for exact arcs), `sketch.finish`, maybe `browser.visibility`.  The
  demo's whole path (4388 pieces) is about 10 `line3d` steps; one
  request a tool, so likely well under a second each (earlier: 45
  ms for a one line sketch in a batch).  Same result as a STEP
  import, today.  Colour per tool is the one gap: a small non
  kernel PR (a `color` sketch option: `SketchView`, `sketch.options`
  params and schema, `view.rs` wire colour, a format pending file,
  an engine test, a screenshot; perhaps 80-150 lines) would give it.

## 2026-10-28: The planned path as one batch per tool sketch

* `probe_batch.py` (with `test_probe_batch.py`, 6 tests): reads the
  G-code (`read_gcode()`, `command_moves()`), groups moves by tool
  (`T08 cuts`, `T08 rapids`; `--mixed` keeps them together), and
  builds each group's 3D sketch with ONE batch: create, options
  (3D, points/profile/constraints/dimensions off), a `line3d` per
  continuous polyline of at most 500 points (split points shared),
  finish, `--hide` a visibility step.  `--arcs`: planar arcs as
  `sketch.arc3d` (start, middle point, end; a circle as two),
  helices as points.  `--plate` models the demo plate in the same
  session (the demo's `main()` with its `sketch_path` and `connect`
  swapped out), `--toggle` times hiding and showing each sketch.
* Headless has no `engine.batch` method, but `solidcraft-cli`'s MCP
  server has a `batch` tool (`tools/call`, name `batch`, same
  `commands`/`rollback`/`timings`); it runs the steps one by one
  in its process.  Reply: `ok`, `completed`, `results`, `timings`,
  `total_ms`.  `sketch.arc3d` takes `start`, `through`, `end`.
* Headless (0.25.1), with the plate: 10 sketches, 68 `line3d`
  steps, 4456 points, 4388 wires (= the demo's 4388 pieces) in
  0.25 s; biggest, T08 cuts (12 steps, 2246 points): 70 ms.
  `--mixed`: 5 sketches, 12 steps, 0.14 s.  `--arcs`: 429 steps,
  567 wires, 0.45 s: each step costs about 1 ms, so many points
  in few `line3d` steps are cheaper than exact arcs.
* GUI (0.25.1, fresh design, plate first: 5.8 s): the same 10
  sketches, 4388 wires, in 0.27 s; a batch 5-68 ms (T08 cuts, 2246
  points, 68 ms, 41 ms inside SolidCraft).  `--toggle`: hiding a
  sketch 13.5 ms (max 18), showing 13.1 ms (max 17).  Against
  `RevealTrace`'s 558 sketches in 48 s, about 180 times faster.
  The user closed the GUI after (it looked idle); screenshots of
  that run failed (a shell variable lost in a background job).
* GUI restarted (10:25): the plate and the 10 sketches again, 0.26
  s; hide 13.9 ms, show 13.7 ms.  Flash check: 12 builds in a row
  (`--keep --hide`, a "Flash test" design) with 33 screenshots
  meanwhile: the toolbar stayed on the Model tab in all 33, no
  sketch palette (a batch runs in one frame, so sketch mode is
  never drawn).  But each repeat took longer (0.25, 0.52, ... 2.3
  s by the 12th, 120 sketches and 52,656 wires in the design): the
  per step refresh grows with the wires already there.  Duplicate
  sketch names: `browser.visibility` by name hit only the first.
* Left running: the GUI on 8080, design "Batch probe" (plate and
  the 10 tool sketches, shown).  Screenshots in the session
  scratchpad (`shots/after_build.png`, `flash_*.png`, `final.png`).
