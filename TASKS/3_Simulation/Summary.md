# Summary of `T.s2` Simulation

LinuxCNC's simulator is the CNC controller that `scraftcnc` talks to
(2026-10-27 to 2026-10-30).  Decided and done, in its sub-tasks:

* `T.il~3.1`: installed and shown running a program on Linux and on
  Windows through WSL 2; macOS dropped.
* `T.tl~3.2`: `sim_linuxcnc.py` drives LinuxCNC from Python and follows
  the tool's position, G-code line and tool.
* `T.rlg~3.3`: the tool and its path shown in SolidCraft as a program
  runs.  Replacing AXIS was not this task's goal; the work drifted that
  way, and was split off.
* `T.mlcp~3.4`: `lcnc_panel.py`, a small `tkinter` panel in place of
  AXIS, with a command port.

Left open, as `I.phpsa~1`: a display bug seen in the user's run with the new speeds and
feeds (`T.msaf~2.1`): near the end, the roughing mill's (T8) path
became visible again (`sim_solidcraft.py`'s `PathRack`).  Not looked
into; the user judged the run "very good" otherwise.
