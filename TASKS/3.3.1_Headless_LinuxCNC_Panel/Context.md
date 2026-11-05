# LLM Agent Context Log

## 2026-11-02: Squeezed; where things stand

Works: `lcnc_panel.py --headless`, `test_lcnc_end_to_end.py` (`SCRAFTCNC_LINUXCNC=1`, 10 tests, about 2 minutes), `lcnc_panel.py` as a
client on the host, and `./show_demo.py` (Linux; needs nothing else on port 8080; ended by the panel's Quit; the user: "good enough to
show").  Never shown: a real reboot (only a stopped box), anything on WSL since protocol 2.  The user commits `scraftlinuxcnc` before
this repository, as `lcnc_client.py` links into it.

* The aim of `--headless`: tests exercise the whole path with no display, so no `Xvfb`.  `SCPanel` is unchanged, built on
  `lcnc_headless.py`, which stands in for the `tkinter` parts used (`use_headless()`); a slider's command and layout are not exercised.
* Command port: `press LABEL`, `type LINE`, `show` (JSON), `answer VALUE` (headless only).  On a real window, `press Set Origin` waits for
  a person.  The path test allows a vertical line through each tool change, as `G43` changes the reading there.
* `command.mode(MODE_AUTO)` while paused ends the program, silently, so `resume()` does not set the mode.
* SolidCraft has no quit command.  `SIGTERM` closes it, leaving `PORT.pid`, `PORT.token` and maybe recovery files named
  `TIME-PID-N.{json,lock,sc}`; those of its PID are removed.  `setsid` on the AppImage forks, so its PID is not the group to signal.
* `SCPathRack` shows the first tool's path from the start; an empty spindle changes nothing.
* `examples/setup/demo_stack.json` is in the program's coordinates: Mikini table, Kurt D688 along Y closed on the tooling plate (5-1/2 in),
  1-1/2 in parallels, tooling plate.  The through cuts reach 0.05 in into the tooling plate (`sckeepout`: 64 moves), nothing fastens the
  plate, the vise passes the table, and the Mikini table is under a Shop mill program; the user: these "will all be worked out", later.

### Issues the user put on hold, keeping their numbers

2. `sim_linuxcnc.py` stays, as `show_demo.py` runs it.  Claude recommends moving it to `lcnc_client`, to run on the host, and removing the
   second `ORIGIN` in `lcnc_panel.py`.
3. Tool change height: a longer tool's tip sits lower there (`T.tl~3.2`), and the end to end test allows any Z above a tool change.
   Claude recommends leaving it until the shop files have gauge lengths.
4. Rebuild the `lcnc` box with the trimmed install: the user said yes.  Check `sim_linuxcnc.py` on the trimmed box.

Also: the WSL probe comes near the end (the user).  One repository or two is undecided; the aim is isolating the LinuxCNC download.

## 2026-11-04: Reopened: a headless `show_demo`

Reopened by the user, from `T.emsagc~5.2` (#79): the GUI run of
`./show_demo.py` failed with a chamfer clash only the whole system
showed, which Claude could not see.  Goal: `./show_demo.py
--headless`: `solidcraft-cli` with a control port, the LinuxCNC
simulator, the watcher (`sim_linuxcnc --watch`), and the headless panel
with `--solidcraft`; then scripted presses (open the `.nc`, wait for
the setup drawing, Start, wait for the end, Quit) through the command
port, as `tests/test_lcnc_end_to_end.py` does.  At the end a report:
every body and sketch with its bounding box, every panel message, the
run time; maybe the session saved as STEP.  Also checks `T.emsagc~5.2`
#78 (part vs tool path).  Close this task when it works, with a
summary.  Two agent steps: (1) the run and the presses; (2) the
report.

## 2026-11-04: Step 1, `./show_demo.py --headless` runs

* `solidcraft-cli` has no control port (`mcp --headless` is stdio
  only), so new `scraftcnc/pybind/headless_server.py` (`python3 -m
  scraftcnc.pybind.headless_server PORT`) serves one
  `SCHeadlessTransport` on the GUI's control protocol (JSON lines,
  token in `control_dir()/PORT.token`, removed on exit), a thread per
  connection, one request at a time.  `engine.batch` goes to the MCP
  `batch` tool (as `plot.send_batch()`); the watcher needs it.
* `show_demo.py --headless`: starts that server instead of the GUI,
  the panel with `--headless --solidcraft PORT`, then `drive()`:
  waits for `show`'s new `drawing` flag (`lcnc_hmi.py`
  `SCPanel.show()`) to go false (`DRAW_SECONDS` 400), presses Start,
  waits for state not idle then idle (`STALL_SECONDS` 60 with no
  change in `status`/`show`), presses Quit, closes all.  Prints each
  new panel message ("Panel: ...") and times.
* Run once (19:35-19:41): setup drawn after 269 s (the models were
  built in a second `solidcraft-cli` by `create_headless()`: the
  chamfered grid plate under its new item key, now cached), the
  program ran in 88 s at speed 10 to its `M2` (683 lines), total 357
  s, exit 0.  No panel message at all: no "Setup not drawn", no
  chamfer clash (with `_edges()`'s `body=`).  No errors in any log;
  nothing left running (pgrep), token file gone.
* Not done: tests for `headless_server.py`; step 2, the report of
  bodies and sketches (bounding boxes) and #78 (part vs path).

## 2026-11-04: Step 2, the session report; #78 answered

* `show_demo.py --headless` prints, before Quit, every body
  (`document.inspect(measure=True)` bbox) and every sketch
  (`sketch.inspect` by id; bbox from its wires' ends), then the plate
  vs the tool path (sketches named `T.. path`) in X and Y.  Pure
  functions `wire_box()`, `box_text()`, `union()`,
  `session_report()`; opacity and color not reported (not in
  `document.inspect`).  Tests: `tests/test_show_demo.py` `TestReport`
  (2) and `TestHeadlessServer` (token refused / accepted, error
  reply); 10 tests OK.  Checkers clean (C0413s as before).
* Run (19:43-19:45, plate cached): setup drawn in 6 s, program 94 s,
  total 100 s, exit 0, no panel messages, nothing left running.
* Findings:
  1. #78: the plate is `[-50.80 -38.10 -12.70] .. [50.80 38.10 0]`
     (centered on the stock's origin, as `SCDemoPart.model()` moves
     the outline's middle there), but the tool path runs from about
     X 0..101.6, Y 0..76.2 (with lead-ins: X -4.44..106.04, Y
     -10.79..80.64), i.e. the G-code's work zero is the plate's
     lower left corner.  Offset path - plate: X +50.80 mm (2 in), Y
     +38.10 mm (1.5 in) by the part's footprint (the report's middle
     line, 34.93, includes the lead-ins).
  2. Every tooling body sits at its own origin, unplaced: table
     `[-381 -133.35 0] .. [381 133.35 63.5]`, vise base Z 0..12.7
     (inside the table), grid plate Z 0..12.7, parallels Z 0..38.1;
     the stock outline `[-57.15 -44.45 -12.7] .. [57.15 44.45 0]`.
     So `SCSetupView.inserted()`'s `placement_matrix` (or the chained
     `place()` locations) is not taking effect in this session; the
     5g live test only checked the part in the stock.
  3. The watcher's tool bodies `T1`..`T9` and `T.. flutes` sketches
     are parked at the origin (expected).

## 2026-11-04: Step 3, placement checked; setup moved for #78

* "Tooling not placed" was the report, not the placement:
  `document.inspect`'s body `bbox` is in the body's component frame.
  A probe (`file.insert_step` of a cached parallel with
  `placement_matrix(1, (100, 200, 300))` in a headless session) gave
  world face centroids and edges at the placed spot, but the
  unplaced `bbox`.  So the headless server and the GUI path are both
  fine.  `show_demo.py` now takes each body's box from `model.edges`
  (`edge_box()`: ends and middles, world frame).  Test:
  `tests/test_show_demo.py` `TestReport.test_edge_box`.
* #78: `demo.py` `_TOOLING` table location 2, 1.5 in -> 4, 3 in, so
  the whole setup moves by (2, 1.5) in and the plate spans 0..4 x
  0..3 in (the G-code's work zero, its lower left top corner).
  `tests/test_setup_view.py` `test_demo` compares to
  `demo_stack.json` plus that shift (docstring says why).
* Rerun (19:47-19:49): drawn 6 s, program 94 s, total 101 s, exit 0,
  no panel messages, nothing left.  Boxes (mm): table [-279.40
  -57.15 -194.06] .. [482.60 209.55 -130.56]; vise base [25.40
  -210.19 -130.56] .. [177.80 189.86 -117.86] (on the table); grid
  plate [-31.75 6.35 -25.40] .. [234.95 146.05 -12.70]; Plate [0 0
  -12.70] .. [101.60 76.20 0]; stock [-6.35 -6.35 -12.70] ..
  [107.95 82.55 0]; T01 path [-3.17 -10.79 -13.97] .. [104.77 79.38
  50.80].  Path middle - plate middle: X 0.00, Y -3.17 (lead-ins).
* Noticed, unchanged: the plate is not centered on the grid plate
  (grid plate Y 6.35..146.05, its middle 76.2; the plate's 38.1, and
  the plate overhangs it by 6.35 mm at -Y); the grid plate runs
  266.7 mm in X across a 152.4 mm wide vise.  Same relative layout
  as `demo_stack.json`.
