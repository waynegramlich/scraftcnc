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

## 2026-10-28: One line of buttons; -Tool and +Tool

* The user: jog buttons, -Tool/+Tool, Start/Pause/Reset all on one
  line; Open, Run Lines and Set Origin went to the speed slider's
  line.  -Tool/+Tool move the start line to the previous or next
  `M6` line (`tool_changes()`), only while stopped; Start runs from
  it (`AUTO_RUN` with the line, counted from 1: starting at 25, the
  `T08 M6` line, ran T8); Reset aborts and goes back to line 0.  Port
  commands `start`, `reset`, `tool+`, `tool-` added.
* Screenshot looked right; left running for the user to look at.

## 2026-10-28: Resume; mode changes only when stopped

* The user saw "Must be in MDI mode to issue a MDI command" (Set
  Origin) and "Cant switch mode while mode is in AUTO and interpreter
  is not IDLE" (a jog): both pressed while paused.  LinuxCNC 2.9
  changes modes only when the interpreter is idle; after Reset (idle)
  MDI works.  So the jog buttons, -Tool/+Tool, Run Lines and Set
  Origin are greyed while a program runs or is paused, and
  `Machine.mdi()` raises "Reset the program first" if the switch did
  not happen.  The buttons now follow LinuxCNC's state each poll
  (`Status.state`), so a program that ends frees them.  Start reads
  Resume while paused.  Checked live (screenshot while paused).

## 2026-10-28: One MDI line with Execute

* The user: the middle window became one line with Execute at its
  right, checked on every keystroke (`line_kind()`: comments in
  parentheses or after `;` left out, then letters each followed by a
  number, `WORDS`): light green when good, light red when bad, white
  when empty.  Execute only when paused and the line is good (the
  user's rule, though LinuxCNC 2.9 refuses MDI while paused: expect
  "Reset the program first").  Run Lines is gone.  The speed control
  was checked: the override follows, and at 0.5 an F4 drill feed ran
  at 2.0 in/min.  The tool's name now ends each `T` line (a `note`
  in `SCCNC`, read back by `scplot.read_gcode()`).
* LinuxCNC 2.9's `milltask` refuses a change of mode while a program
  runs or is paused ("Can't switch mode while mode is AUTO and
  interpreter is not IDLE"), so MDI (Execute, Set Origin) and jogs
  work only when stopped.  The user is fine with that (jogging makes
  no sense once a program starts).  After Reset, a 0.1 in X jog
  moved exactly 0.1 in.  Execute is now active when stopped and the
  line is good.

## 2026-10-28: Jog line, steps and Home

* Jog line: Set Origin, Home, -X..+Z, then the step (1, .1, .01,
  .001, .0001 in; `ttk.Radiobutton`s in the `Toolbutton` style, .0001
  at start), all grey while a program runs or is paused.  Set Origin
  and Home are also grey within `AT_ORIGIN` (0.00005 in) of the work
  origin.  Home (`Machine.go_origin()`): `G20 G90 G0 Z max(z, 0)`,
  `G0 X0 Y0`, `G0 Z0`, so it never moves sideways below Z0.  Run
  line: -Tool, +Tool, Start, Pause, Reset; Open beside the slider.
  Screenshot looked right; Home not yet pressed live.

## 2026-10-28: MDI line moved; step buttons; scrolling

* The MDI line and Execute moved to just above the jog line; the
  step choices are `tk.Radiobutton`s with `indicatoron=False` (real
  buttons, the chosen one light blue).
* The two G-code windows have scroll bars; while paused they hold the
  whole program (put in once, so the user's scrolling stays), the
  executed one scrolled to its end.
* A run failed at once with "invalid params in linear command": G54
  had become 0, 0, 0 (machine Z top), so the demo's `G0 Z1` was above
  Z travel.  Put back to 4, 3, -6 (`G10 L2 P1`), and it ran.  The
  red message now clears on Start and Reset.
* "invalid params in linear command" again: the user's Set Origin
  with T4 in (tool length 3.875 in, the overall length standing in)
  left G54 Z at -3.625, so work Z could reach only -0.25 and the
  demo's Z1 and Z2 were out of travel.  A failed move leaves LinuxCNC
  paused (Execute and Set Origin grey until Reset).  The message now
  adds "work Z can reach only N with this origin and tool"
  (`Machine.top_z()`).  The user: done tweaking the panel after this.

## 2026-10-28: A faster simulated mill; G54 set at start

* G54 is not kept from one LinuxCNC start to the next (it came back
  0, 0, 0, and with T4's 3.875 in the tip could reach only work Z
  -3.875), so the panel now sets `sim_linuxcnc.ORIGIN` (4, 3, -6)
  when it starts.  The demo then ran past the tool changes.
* The user: the slider "did not seem to work"; the real wish is a
  simulator that runs far faster (saving time, machining nothing).
  `lcnc_sim/shop_mill.ini`: 20 in/s on every axis (was 1.833 for X
  and Y, 1.5 for Z), 200 in/s^2 (was 10), `MAX_FEED_OVERRIDE` 100
  (was 10).  At 100x the demo reached line 224 in 44 s (at 10x on
  the old limits, line 140 at 90 s); the user then paused it.
* The user: no speed 0 (Pause does that); a logarithmic slider from
  0.01x to 10x (`MIN_SPEED`, `MAX_SPEED`, the top also limited by
  the INI file).  The slider holds log10 of the override; the label
  shows it (`.2g`, e.g. "3x"); the port's `speed` is clamped
  (50 -> 10, 0.001 -> 0.01), checked against LinuxCNC's `feedrate`.
* Window title "SolidCraft LinuxCNC".  The panel comes up stopped;
  the user starts and stops runs (Claude only opens the program).
* Suspended at the user's word (2026-10-28): "pretty workable".
  Open: the slider's top (10x, or 100x, which the faster mill allows);
  `demo_linuxcnc.py` still waits for AXIS (`T.il~3.1`).
