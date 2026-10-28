# LLM Agent Context Log

## 2026-10-28: A first `lcnc_panel.py`

* `lcnc_panel.py` (tkinter): the user's layout, three G-code windows,
  jog buttons, Run/Pause (grey each other out; Run resumes), Stop,
  Set Origin (asks yes/no), and a speed slider (feed override).
* LinuxCNC calls are in `Machine`, which imports `linuxcnc` lazily;
  `--dry-run` builds the window with no LinuxCNC and only logs.
* Stubs (TODO): program from the command line, Open button, `--port`
  command port, MDI of the edit lines when paused, position and tool,
  `-ini` from `[DISPLAY]`, closing LinuxCNC on exit.
* Checkers clean; a dry-run smoke check works.  Not yet run against
  LinuxCNC, and `shop_mill.ini` not changed.

## 2026-10-28: The TODOs done; first live run

* `lcnc_panel.py`: the machine is taken out of E-stop, turned on and
  homed at start (`sim_linuxcnc.Simulator`, imported lazily); a
  program from the command line, an Open button, or the command port
  (`--port`, 127.0.0.1, one line in, one back: `ping`, `open FILE`,
  `run`, `pause`, `stop`, `speed X`, `status`, `quit`); the work
  position and tool shown; LinuxCNC's errors in a red line; the
  slider's top from `MAX_FEED_OVERRIDE`; Run Lines (enabled when
  paused) runs the edit window's lines as MDI; Set Origin asks with
  No as the default; `split_ini()` takes off `-- -ini FILE`.
* `lcnc_sim/shop_mill.ini`: `DISPLAY = ../lcnc_panel.py --port 5007`
  (LinuxCNC runs it from `lcnc_sim/`, so relative program paths are
  from there; `open` refuses a missing file).  `stop_linuxcnc.py`
  sends the panel `SIGTERM` (it closes as its window would, and
  LinuxCNC shuts down quietly: "closed", nothing left), then tries
  `axis-remote --quit`.
* Live (12:28-12:32): starts in about 4 s; open, speed 10, run,
  pause, resume and stop all work through the port; status showed
  the line, position and T4.
* Found: LinuxCNC 2.9 will not switch to MDI while a program is
  paused (`mode(MODE_MDI)` leaves it in AUTO, with no error), so Run
  Lines does nothing while paused.  To settle with the user.
* Now broken by the switch from AXIS: `demo_linuxcnc.py`'s
  `axis-remote --ping` wait (`T.il~3.1`, suspended); the panel's
  `ping` can replace it.
* The panel does not set the G54 origin or load the tool table
  (`sim_linuxcnc.py` does); work Z read -5 to -7.5 with no origin set.
