# Summary of `T.tl` Tracking LinuxCNC

`sim_linuxcnc.py` drives the simulator and follows it at 20 Hz (work position = machine less `g5x_offset`, `g92_offset`, `tool_offset`), handing
samples to listeners; every sample lay within 0.001 in of the path.  Homing a homed sim machine traps it, so it is skipped.  Left open: a longer
tool's tip sits lower at the tool change height (`G53 G0 Z0` declined).  Not done (the user): starting partway.  No unit tests.
