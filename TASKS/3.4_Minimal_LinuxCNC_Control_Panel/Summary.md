# Summary of `T.mlcp` Minimal LinuxCNC Control Panel

`lcnc_panel.py`, a small `tkinter` panel in place of AXIS, with a command port on 127.0.0.1.  It comes up stopped; the user starts runs.
LinuxCNC 2.9 changes mode only when stopped, so MDI, Set Origin and jogs are grey during a run.  Left open: the slider's top (10x or 100x).
