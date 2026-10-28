# Summary of `T.mlcp` Minimal LinuxCNC Control Panel

`lcnc_panel.py`, a small `tkinter` panel ("SolidCraft LinuxCNC") in
place of AXIS, through LinuxCNC's Python API (2026-10-28).
`lcnc_sim/shop_mill.ini` starts it (`DISPLAY = ../lcnc_panel.py
--port 5007`); closing it, or `stop_linuxcnc.py`'s `SIGTERM`, closes
LinuxCNC quietly.  Decided and done:

* At start: out of E-stop, on, homed, G54 set to
  `sim_linuxcnc.ORIGIN` (LinuxCNC does not keep it); it comes up
  stopped, and the user starts runs.
* Windows: the G-code executed and coming (whole and scrollable
  while paused), one MDI line with Execute (green when it reads as
  RS-274, red when not), the work position and tool, LinuxCNC's
  messages (a travel error says how high work Z can reach).
* Jog line: Set Origin (asks, No by default), Home (up, over, down),
  -X..+Z, steps 1 to .0001 in.  Run line: -Tool, +Tool (start from
  the previous or next `M6`), Start (Resume while paused), Pause,
  Reset.  A logarithmic speed slider, 0.01x to 10x (and the INI
  file's `MAX_FEED_OVERRIDE`), and Open.
* LinuxCNC 2.9 changes mode only when stopped, so MDI, Set Origin and
  jogs are grey while a program runs or is paused (the user agreed).
* A command port on 127.0.0.1 (`ping`, `open`, `start`, `pause`,
  `reset`, `tool+`, `tool-`, `speed`, `status`, `quit`), so Claude can
  open programs and look at the state.
* `shop_mill.ini` made a faster mill (20 in/s, 200 in/s^2,
  `MAX_FEED_OVERRIDE` 100).
* With `sim_linuxcnc.py --watch` (`T.rlg~3.3`) it drove the demo in
  SolidCraft: "It was perfect."

Left open: the slider's top (10x, or the 100x the mill allows);
`demo_linuxcnc.py` still waits for AXIS (`T.il~3.1`).
