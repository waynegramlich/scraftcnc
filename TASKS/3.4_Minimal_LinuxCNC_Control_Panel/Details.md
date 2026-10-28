# 3.4 Minimal LinuxCNC Control Panel

Replace LinuxCNC's own GUI (AXIS) entirely, and replace it with a
really small one of our own that talks to the LinuxCNC back end
through LinuxCNC's Python API (`linuxcnc.command()`,
`linuxcnc.stat()`, `linuxcnc.error_channel()`, as `sim_linuxcnc.py`
uses).  SolidCraft shows the part, the tool and its path
(`T.rlg~3.3`); this panel only controls the machine.  (The user's
idea, 2026-10-28.)

## The Panel

* A speed slider: the feed override (`command.feedrate()`), up to
  the INI file's `MAX_FEED_OVERRIDE`.
* Six jog buttons: +X, -X, +Y, -Y, +Z, -Z (`command.jog()`).
* Set origin: the current position becomes the program's zero
  (G54, e.g. MDI `G10 L20 P1 X0 Y0 Z0`).  On a real machine this
  is a big deal, so it should be hard to press by accident.
* Stop: stop at once (`command.abort()`).
* A text entry that runs one manual (MDI) command
  (`command.mode(MODE_MDI)`, `command.mdi(...)`), with LinuxCNC's
  messages shown.

## Layout (the user's, 2026-10-28)

`tkinter` (standard library, and in the `lcnc` box, since AXIS uses
Tk).  A first sketch:

```
+--------------------------------------------------+
| [ read only: the G-code already executed       ] |
| [ editable: 2 or 3 lines of G-code, run when   ] |
| [ the machine is paused                        ] |
| [ read only: the G-code coming next            ] |
|                                                  |
|                       [+Y]              [+Z]     |
|     [-X]  [+X]                                   |
|                 [-Y]                    [-Z]     |
|                                                  |
| [Run]  [Pause]  [Stop]          [Set Origin]     |
|                                                  |
| speed  |----------o----------------------|       |
+--------------------------------------------------+
```

* X buttons side by side; Y buttons diagonal from one another, to
  the right of the X buttons; Z buttons one above the other.
* Run, Pause, Stop (`command.auto(AUTO_RUN|AUTO_PAUSE|AUTO_RESUME)`,
  `command.abort()`) and Set Origin buttons.
* The speed slider is horizontal, under all of the buttons.
* Three text windows, one above another, all G-code: the top one
  read only, what has been executed; the middle one two or three
  lines, editable, run (as MDI) when the machine is paused; the
  bottom one read only, what comes next.

## Questions to Settle

* Decided (the user, 2026-10-28): Run resumes after Pause, and
  Run and Pause grey each other out (only one can be pressed).
  LinuxCNC starts the panel as the INI file's `[DISPLAY] DISPLAY`
  (in place of `axis`), so `linuxcnc lcnc_sim/shop_mill.ini`
  brings it up.
* Decided (the user, 2026-10-28): a program is chosen by any of a
  command line argument, an Open button, or a command from Claude
  on an open port (the port set on the command line).
* What else it shows: at least the position (work coordinates) and
  the tool in the spindle.
* It must not grab the keyboard focus when it starts (AXIS's popups
  did).
* Closing it should close LinuxCNC quietly (`stop_linuxcnc.py`).

## Done When

* `linuxcnc lcnc_sim/shop_mill.ini` comes up with the panel instead
  of AXIS, and the demo's G-code can be set up (origin), run at a
  chosen speed and stopped from it.
