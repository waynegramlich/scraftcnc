# LLM Agent Context Log

Moved from `T.s2~3`'s `Context.md` on 2026-10-28, when it was split.

## 2026-10-27: Step 3 done: driving LinuxCNC from Python

* In the box, `linuxcnc.command()`: `state(STATE_ESTOP_RESET)`,
  `state(STATE_ON)`, `mode(MODE_MANUAL)`, `teleop_enable(False)`,
  `home(-1)` (all joints, by `HOME_SEQUENCE`; wait on
  `stat.homed`), `mode(MODE_AUTO)`, `program_open(PATH)`,
  `auto(AUTO_RUN, 0)`; call `wait_complete()` after each.  Messages
  come from `linuxcnc.error_channel().poll()`.
* Polling `linuxcnc.stat()` at 20 Hz: `actual_position[:3]`,
  `motion_line` (the G-code line being run) and `interp_state`
  (`INTERP_IDLE` at the end).  The sample `axis.ngc` ran in 129.5 s,
  2579 samples (19.9 Hz), positions in inches.
* `actual_position` is in machine coordinates; the work position
  needs `g5x_offset`, `g92_offset` and `tool_offset` taken off (all
  zero in the sample sim, not yet checked against our G-code).

## 2026-10-27: The scripts, saved

* `sim_linuxcnc.py` (step 3; runs in the box: `distrobox enter
  lcnc -- ./sim_linuxcnc.py [PROGRAM] [--out FILE]`).  Checkers
  clean; no unit tests (it needs LinuxCNC).  Not named
  `*_test.py`, which would make it a test suite under the Python
  Coding Rules.  (`sim_move.py`, saved at the same time, is
  `T.rlg~3.3`'s.)
* Homing trap: `home(-1)` on an already homed sim machine unhomes it
  first, and then X and Z (`HOME_IS_SHARED`) refuse with "Cannot
  home while shared home switch is closed" wherever the last program
  left them; only restarting LinuxCNC cleared it.  `sim_linuxcnc.py`
  now skips homing when every joint is homed (checked: two runs in a
  row, 129 s each).
* Closing LinuxCNC from a script (Claude's `pkill -TERM` of the
  `axis` process) pops up a close window on the user's screen, which
  the user has to dismiss.  Avoid it: leave LinuxCNC running (the
  scripts no longer need a restart), or find a quiet way to close it
  (`axis-remote --quit` in the box is a guess, not yet tried).

## 2026-10-27: Step 4 begins: the demo's G-code in LinuxCNC

* `command.program_open(PATH)` and `auto(AUTO_RUN, 0)` run any file
  (`sim_linuxcnc.py PROGRAM` already does).  The demo's G-code
  already has feeds and speeds (per tool `F`/`S` from the tools
  files), so `T.msaf~2.4` is not in the way.
* Two things it needed (tried with a scratch script first; added to
  `sim_linuxcnc.py` the same evening, see below):
  * A work offset: the program goes to Z2, above the sim's Z soft
    limit (+0.12, machine).  MDI `G20 G10 L2 P1 X0 Y0 Z-2.5`
    (`mode(MODE_MDI)`, `mdi(...)`); without the `G20` it was taken
    as millimeters.  Work position = `actual_position` minus
    `g5x_offset` (and `g92_offset`, `tool_offset`).
  * Its tools in the tool table: "Requested tool 8 not found in the
    tool table" stopped it.  `~/linuxcnc/configs/sim/axis/sim.tbl`
    now lists the shop mill's T1-T9 (Z0, diameters from
    `tools.toml`; the original is `sim.tbl.orig`), and
    `command.load_tool_table()` reloads it without a restart.
* Then 90 s ran cleanly: the G83 pecks at 4 in/min, then T8
  roughing at 12 in/min, Z at work -0.1.  The run is real time
  (about 19.6 minutes in all).
* Our `tool_change` (`T{number:02d}`) writes `T08` with no `M6`, so
  LinuxCNC only prepares the tool (`pocket_prepped`) and
  `tool_in_spindle` stays 0: no tool change, no length offset
  (`G43`).  A LinuxCNC post would write `T8 M6` (and `G43 H8`), but
  in this sim `M6` opens AXIS's manual tool change window, unless
  the HAL wires `iocontrol.0.tool-change` straight to
  `tool-changed`.

## 2026-10-27: The demo runs in the shop mill simulator

* `lcnc_sim/shop_mill.ini` (in the project): the example shop mill's
  travel (X 0-18, Y 0-9, Z -16-0 in, machine), feeds (110 in/min, Z
  90) and acceleration (10 in/s^2); homing at once wherever it is
  (`HOME_SEARCH_VEL = 0`, no simulated home switches, so no homing
  trap); no `axis_manualtoolchange.hal` (`core_sim.hal` already loops
  `iocontrol.0.tool-change` to `tool-changed`, so `M6` needs no
  click); `MAX_FEED_OVERRIDE = 10`; no position file.  Started with
  `distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini`.
* `examples/shop/linuxcnc.toml`: `tool_change = "T{number:02d} M6
  G43 H{number:02d}"` (the user agreed to real tool changes);
  `test_shops.py` and `test_scmachine.py` updated.
* `sim_linuxcnc.py`: writes the shop machine's tool table over the
  INI file's `TOOL_TABLE` and reloads it (`--shop`, `--machine`;
  lengths Z0); sets G54 by MDI (`--origin X Y Z`, default 4 3 -6,
  machine inches); feed override (`--speed`); samples are in work
  coordinates (machine less `g5x_offset`, `g92_offset`,
  `tool_offset`).  The user stressed that setting the origin is a
  big deal on a real machine.
* `./solidcraftcnc_demo.py > demo.ngc`, then `distrobox enter lcnc
  -- ./sim_linuxcnc.py demo.ngc --speed 5`: 362.8 s (vs 19.6 min at
  1x; rapids stay at 110 in/min), 7231 samples, no errors.
* The user: the run does the peck drilling first, which is boring to
  watch.  Ideas for later: start at a later line (LinuxCNC's run
  from line, `auto(AUTO_RUN, LINE)`), or a higher `--speed` for the
  drilling.


## 2026-10-28: Split, real tool lengths (a forked agent)

* The user's #5: `sim_linuxcnc.py` only drives and polls LinuxCNC;
  each poll is a `Sample` (time, line, position, tool) handed to
  `Listener`s (`sample()`, `finish()`); any exception from one is
  `ListenerFailed` and stops the program (as SolidCraft going away
  did).  `ToolModel`, `ToolRack`, `RevealTrace` moved to
  `sim_solidcraft.py` (`T.rlg~3.3`), whose `SolidCraftDisplay` is a
  listener; `add_arguments()` adds `--solidcraft`/`--no-trace`, so
  the command line is unchanged; `--solidcraft headless` now works
  (extracted `solidcraft-cli`).  It needs no `linuxcnc` module.
  Host check, headless, fake samples: 558 trace sketches in 6.5 s.
* The user's #8: the tool table's Z is each tool's `overall_length`
  (gauge length really depends on holder and stick out; not in the
  shop files yet).  Longest is the 15/64 drill, 3-7/8 in: at the
  default origin Z -6, work Z2 is machine Z -0.125, just inside.
* Live, no SolidCraft: `./sim_linuxcnc.py demo.ngc --speed 10`
  (split code, real lengths) ran through: 5895 samples in 294.9 s,
  no errors; the table had Z2.5000 for T1 ... Z3.8750 for T4.
* The user's #6, checked: every sample after line 14 lies within
  0.001 in of `command_moves()`'s path for its line (5573 samples),
  except at tool changes: `motion_line` stays on the `G0 Z2` before
  `T.. M6 G43 H..`, and the tip's work Z jumps by the length
  difference (T4 -> T8: Z 3.375 = 2 + 3.875 - 2.5; T8 -> T5: +1.0),
  which is right: the spindle stays put, the tool is shorter.  Line
  14 (the first G83 hole) is off since `command_moves()` skips moves
  before X and Y are known.  So `tool_offset` is taken off right.
* MDI probe (scratchpad `offset_probe.py`): tip at `G0 Z0` reads
  work Z 0 for T1 (machine -3.5), T4 (-2.125) and T5 (-4.5): machine
  = -6 + length.  `G92 X0 Y0 Z0` at X1 Y1 Z1 then `G0 X0.5 Y0.25
  Z0.5` reads 0.5 0.25 0.5 (g92_offset 1 1 1); `G92.1` clears it.
  Our G-code never uses G92.
* Found: the tool change height is work Z2, so with real lengths the
  new tool's tip lands lower by its extra length.  The first change
  (no tool, then T4 at 3-7/8 in) puts the tip at work Z -1.875,
  below the part top (here off to the side, at machine X0 Y0).  A
  real post would go to machine Z0 first (`G53 G0 Z0`) before
  `T.. M6`.  Not changed (a `SCCNC`/`tool_change` question).
* At the user's word (through the coordinator), `--speed` now
  defaults to 10 (`SPEED`, the INI file's `MAX_FEED_OVERRIDE`).
* `--solidcraft headless` from the `lcnc` box: the `solidcraft-cli`
  on the `PATH` is the AppImage's wrapper (`~/.local/bin`, written
  2026-10-27 20:19), which needs FUSE: "No suitable fusermount binary
  found" (the box has none), seen as a JSON error.  So
  `sim_solidcraft.transport()` now always prefers the extracted
  `solidcraft/squashfs-root/usr/bin/solidcraft-cli`.  Then: trace
  558 sketches in 6.5 s, 751 samples in about 38 s (Ctrl-C by
  `timeout -s INT 45` in the box: "interrupted: the program is
  stopped").  Killing the `solidcraft-cli` mid-run: "SolidCraftDisplay
  failed (ConnectionError: ...): the program is stopped".  Nothing
  left running either time.
* The user's #9 (quiet close).  The box shares the host's process
  and IPC namespaces (its processes and `ipcs -m` show on the host).
  Running LinuxCNC is: `linuxcnc` (the bash script, parent of
  `axis`), `linuxcncsvr`, `io`, `halui`, `rtapi_app`, `milltask`,
  `axis`; 8 shared memory segments of its own; `/tmp/linuxcnc.lock`.
* Why yesterday's `pkill -TERM axis` popped a window: the script runs
  the display in the foreground, then `Cleanup`; its `EXIT` trap
  (`ErrorCheck`) shows `show_errors.tcl` (a wish window) whenever the
  display exits non-zero (and AXIS's own close button asks "Do you
  really want to close LinuxCNC?").
* `distrobox enter lcnc -- axis-remote --quit` (AXIS's remote
  `destroy`, no question): in under 2 s every process gone, its 8
  segments removed (2 others, not LinuxCNC's, stay), lock removed,
  no window, `linuxcnc` exit 0.  Quiet and clean.
* `kill -9` of all seven at once: no window (the script's trap
  can not run), but it leaves `/tmp/linuxcnc.lock` and LinuxCNC's 8
  segments (nattch 0).  The next `linuxcnc` (no tty, `DISPLAY` set)
  then pops up a wish dialog "LinuxCNC is still running.  Restart
  it?" (seen at 10:14; the user answered it: Yes, and it cleaned up
  and started).  So `kill -9` alone is not quiet.
* `kill -9`, then `halrun -U` (in the box; "Waited 3 seconds for
  master.  giving up.", 2.6 s) removes the HAL segments (keys
  0x48414c32, 0x48484c34) but not 0x64 nor the NML ones (1001-1005,
  `B ... SHMEM` lines of `/usr/share/linuxcnc/linuxcnc.nml`); after
  `ipcrm -M` of those and removing the lock, `linuxcnc
  lcnc_sim/shop_mill.ini` started cleanly, no dialog.
* `stop_linuxcnc.py` (in the box: `distrobox enter lcnc --
  ./stop_linuxcnc.py`): `axis-remote --quit`, then waits for every
  LinuxCNC program to go; if that fails (or `--kill`), `SIGKILL` to
  them all, `halrun -U`, `ipcrm -M` of keys 100 and 1001-1005, and
  the lock removed.  With nothing running it cleans up a stale lock.
  Checked: `--kill` 3.6 s, then a clean start (no dialog) and a 20 s
  run; the gentle way "closed" in 1.9 s, no window; a second call
  "not running".  LinuxCNC is left stopped cleanly (10:17).
* `T.tl~3.2` now looks done: the demo runs through with real tool
  lengths and right work positions, the SolidCraft side is a
  listener in `sim_solidcraft.py`, and LinuxCNC closes quietly.
  Left as a finding for later: the tool change height (above).

## 2026-10-28: Tool change height left alone (the user's call)

* With real tool lengths, a change at work Z2 leaves a longer tool's
  tip lower (T4: work Z -1.875).  `G53 G0 Z0` before `T.. M6` was
  suggested; the user declined: machine Z0 depends on where it was
  set, `z_safe` is the only sound height but may not be known.
  Nothing changed for now.
