# Summary of `T.tl` Tracking LinuxCNC

`sim_linuxcnc.py` drives LinuxCNC's simulator (in the `lcnc` box,
`T.il~3.1`) from Python and follows what it does, so `scraftcnc` has
a CNC controller to talk to.  Decided and done (2026-10-27 to
2026-10-28):

* `lcnc_sim/shop_mill.ini`: the example shop mill (travel, feeds,
  acceleration), homing at once, no manual tool change window,
  `MAX_FEED_OVERRIDE = 10`.  `examples/shop/linuxcnc.toml` writes
  real tool changes: `T{n} M6 G43 H{n}`.
* Start-up: E-stop reset, machine on, homing skipped when already
  homed (homing a homed sim machine trapped it), the shop machine's
  tool table written and reloaded (`--shop`, `--machine`; each
  tool's catalog `overall_length` as its length), G54 set by MDI
  (`--origin`, default 4 3 -6 machine inches).
* Runs a program at a feed override (`--speed`, default 10), polls
  at 20 Hz (work position = machine less `g5x_offset`,
  `g92_offset`, `tool_offset`; G-code line; tool in the spindle),
  writes samples to `--out`, and hands each to listeners; a failing
  listener, `OSError` or Ctrl-C stops the program.  The SolidCraft
  display is such a listener, in `sim_solidcraft.py` (`T.rlg~3.3`).
* Checked: the demo runs through (5895 samples in 295 s at 10x, no
  errors); every sample lies within 0.001 in of the G-code's path;
  tool tips read work Z0 at `G0 Z0` for tools of different lengths;
  G92 reads right.
* `stop_linuxcnc.py` closes LinuxCNC quietly (`axis-remote --quit`;
  `kill -9` plus cleanup of shared memory and the lock as a
  fallback); a plain kill made the next start ask "still running?".

Left open: with real lengths a longer tool's tip sits lower at the
tool change height (work Z2); `G53 G0 Z0` was declined, since machine
Z0 depends on setup and `z_safe` may not be known.  Not done (the
user's choice): starting partway through a program.  No unit tests
for `sim_linuxcnc.py`, which needs LinuxCNC.
