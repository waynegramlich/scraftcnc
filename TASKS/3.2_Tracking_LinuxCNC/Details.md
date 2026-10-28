# 3.2 Tracking LinuxCNC

Drive LinuxCNC from Python and follow what it does, so `scraftcnc`
has a CNC controller to talk to:

* A LinuxCNC configuration that matches the example shop's mill
  (`lcnc_sim/shop_mill.ini`).
* Start-up: estop reset, machine on, homing, the work origin (G54),
  the shop machine's tool table.
* Load and run a program (e.g. the demo's G-code), with a feed
  override, and stop it cleanly (errors, Ctrl-C).
* Poll the tool's position (work coordinates), the G-code line being
  run and the tool in the spindle, at about 20 Hz.

## Done When

* `sim_linuxcnc.py` runs the demo's G-code from start to finish and
  reports where the tool was, with no errors.
