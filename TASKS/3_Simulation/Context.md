# LLM Agent Context Log

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

## 2026-10-27: Step 2 (the user's): installing LinuxCNC

* https://linuxcnc.org/downloads/ offers only Debian 13 Trixie (ISO
  and `.deb` files under `dists/trixie/2.9-uspace/`); nothing for
  Ubuntu, and Ubuntu 24.04 has no `linuxcnc-uspace` package here.
* Chosen: Debian Trixie in a `distrobox` (the user's choice over a
  source build; a VM avoided; the Trixie `.deb` can not go on Ubuntu,
  since it needs Python 3.13).  The user installed `distrobox` 1.7.0
  and `podman` 4.9.3 from Ubuntu.
* `distrobox create --yes --name lcnc --image
  docker.io/library/debian:trixie`; `sudo` in the box needs no
  password.  `linuxcnc-uspace_2.9.10_amd64.deb` (from
  `dists/trixie/2.9-uspace/binary-amd64/`) installed with `sudo
  apt-get install -y ./FILE` (614 packages, including an RT kernel
  that only lands in the box's `/boot`).
* First start failed: `rtapi_shmem_new failed due to shmget(...):
  Permission denied`.  `rtapi_app` is setuid root, and the box's root
  is not the user in rootless podman, so it can not open the shared
  memory made by the rest of LinuxCNC.  Fixed (in the box only) with
  `sudo chmod u-s /usr/bin/rtapi_app`; a simulator needs no realtime
  priority.  A package upgrade in the box would restore the bit.
* Sample configs copied to `~/linuxcnc/configs/sim/`; started with
  `distrobox enter lcnc -- linuxcnc
  ~/linuxcnc/configs/sim/axis/axis.ini` (inch mill, AXIS screen).
* `import linuxcnc` (Python 3.13.5 in the box) and `stat().poll()`
  work: estop on, not homed, `linear_units` 1/25.4, position zero.
  The module exists only in the box, so the bridge script runs there
  (`scraftpybind` is standard library only, and the box shares the
  host network, so port 8080 is reachable).

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

* `sim_move.py` (steps 1's two scratch scripts in one: `--method
  pending|captured|solid`, `--step`, `--interval`, `--trips`,
  `--report`) and `sim_linuxcnc.py` (step 3; runs in the box:
  `distrobox enter lcnc -- ./sim_linuxcnc.py [PROGRAM] [--out
  FILE]`).  Checkers clean; no unit tests (both need SolidCraft or
  LinuxCNC).  Not named `*_test.py`, which would make them test
  suites under the Python Coding Rules.
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
* Two things it needed (tried with a scratch script; not yet in
  `sim_linuxcnc.py`):
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
* Next: the SolidCraft side (a tool stand-in moved to each sample).
* The user: the run does the peck drilling first, which is boring to
  watch.  Ideas for later: start at a later line (LinuxCNC's run
  from line, `auto(AUTO_RUN, LINE)`), or a higher `--speed` for the
  drilling.
