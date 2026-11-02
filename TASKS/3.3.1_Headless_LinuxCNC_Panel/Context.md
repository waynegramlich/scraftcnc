# LLM Agent Context Log

## 2026-11-01: Created

* The user moved `lcnc_panel.py --headless` here from `scraftlinuxcnc`, since the panel
  stays in `scraftcnc`.  Nothing is done yet.
* The aim: tests run the panel with no display, so with no `Xvfb` (225 MB on WSL).  Not
  confirmed: the `linuxcnc` script accepting a `DISPLAY` program with no window.
* The installer in `scraftlinuxcnc` will drop `python3-tk`, the user's decision, so
  `scraftcnc` must install it for the panel, as `demo_linuxcnc.py` does `xvfb`.
* Asked of the user: whether this belongs at 3.3.1 or under `T.il~3.1`.

## 2026-11-01: `--headless`, and the end to end suite

The user: `--headless` exists so that a test suite can exercise the whole path with no
display.

* Claude's design: `SCPanel` is unchanged, and is built on `lcnc_headless.py`, which stands in
  for the parts of `tkinter`, `ttk`, `filedialog` and `messagebox` used (`use_headless()`
  rebinds the names).  So tests run the real window code, and `tkinter` is not needed.  A
  disabled button or `Text` behaves as the real one does.  The slider's own command is not
  exercised (`speed X` calls what it calls), and neither is layout.
* Command port: `press LABEL`, `type LINE`, `show` (JSON), `answer VALUE` (headless only).
  `press`, `type` and `show` were also tried on a real window on `:0`, in dry run, through
  the port.  On a real window, `press Set Origin` would wait for a person to answer.
* `test_lcnc_panel.py`: offline, 34 tests.  `test_lcnc_end_to_end.py`: `SCRAFTCNC_LINUXCNC=1`,
  10 tests, 127 s, all pass.  The path test checks every sample of the demo within 0.001 in of
  the G-code's path, and the tools in order; a vertical line through each tool change is allowed
  for, since `G43` changes the reading there (`T.tl~3.2`'s known tool length behavior).
* Found by the suite: `command.mode(MODE_AUTO)` while paused ends the program, silently, so
  `resume()` no longer sets the mode.  This bug predates the bridge.  An earlier pause of the
  demo survived it, for a reason not looked into.

## 2026-11-01: `show_demo.py`, for showing the user's friend tomorrow

* The user: one program that brings up SolidCraft and `lcnc_panel.py`, connected; Linux only
  tonight.  The five issues last listed are on hold, at the user's word.
* `show_demo.py`: the box if stopped, the installer's check, `serve_linuxcnc`, SolidCraft, the
  plate, the watcher in the box, last the panel, stopped, at 10x.  The first to stop closes the
  rest.  A port in use stops it, with no disturbance.
* SolidCraft has no quit command.  `SIGTERM` closes it within a second, leaving `PORT.pid` and
  `PORT.token`, and maybe recovery files named `TIME-PID-N.{json,lock,sc}`; those of its own PID
  are removed.  With another SolidCraft open, `current.port` and `current.pid` end up pointing
  at the show's.  `setsid` on the AppImage forks, so its PID is not the group to signal.

## 2026-11-01: Quit, and the first path before a run

* The user asked for a Quit button, and saw no tool paths.  `sketch.inspect` and a screen capture
  of a run paused with T8 showed the paths working: `SCPathRack` showed none until a tool was in
  the spindle.  Taken as the cause, not confirmed with the user.  It now shows the first tool's
  path from the start, and an empty spindle changes nothing.
* Quit closes the panel; with `show_demo.py` that closes everything, and alone LinuxCNC stays up.
* `xwd -root` piped through Pillow (`BGRX`, from the header) gives a usable picture, when the
  windows are not covered.

## 2026-11-01: Saved for the user's commits and a `/clear`; start here

The user: "This demo is good enough to show."  `./show_demo.py` is for showing a friend on
2026-11-02, on Linux; it needs no other SolidCraft on port 8080.  The way to end it is the panel's
Quit button.  The user commits and pushes both repositories, `scraftlinuxcnc` first, since
`lcnc_client.py` here links into it.

Works: `show_demo.py` (the whole chain), `lcnc_panel.py` as a client on the host, `--headless`,
`test_lcnc_end_to_end.py` (`SCRAFTCNC_LINUXCNC=1`, 10 tests, about 2 minutes).

Never shown: a run through to the program's end with SolidCraft attached, unless the user's own
rehearsal did; `show_demo.py` on its default ports, unless the same; a real reboot (only a stopped
box); anything on WSL since protocol 2.

Issues the user put on hold, keeping their numbers:

2. `sim_linuxcnc.py`: the user doubted it was still needed, but `show_demo.py` now runs it for the
   tool in SolidCraft, so it stays.  Claude recommends moving it to `lcnc_client`, so that it runs on
   the host, not in the box, and removing the second `ORIGIN` in `lcnc_panel.py`.
3. Tool change height: a longer tool's tip sits lower there (`T.tl~3.2`), and
   `test_lcnc_end_to_end.py` allows any Z above a tool change for it.  Claude recommends leaving it
   until the shop files have gauge lengths.
4. Rebuild the `lcnc` box with the trimmed install: the user said yes; the panel no longer needs
   `python3-tk` there.  Check `sim_linuxcnc.py` on the trimmed box.  Not with a demo pending.

Also: the WSL probe is to come near the end (the user's word).  The user has not decided on one
repository or two; the aim is isolating the LinuxCNC package download.  `I.phpsa~1` (a hidden path
showing again near the end of a run) is not fixed.

## 2026-11-01: `show_demo.py` stands the plate on a stack

* The user asked for the table, vise, parallels, tooling plate and demonstration plate, stacked.  New:
  `examples/setup/demo_stack.json`, in the program's coordinates (SolidCraft's are the same), so nothing is
  moved afterward: Mikini table, Kurt D688 turned along Y and closed on the tooling plate (5-1/2 in), 1-1/2 in
  parallels, tooling plate, all centered under the plate at X 2, Y 1.5.  `scsetup.py` takes the kind
  `tooling_plate`.  `SCShow.model_stack()` models it after the plate.
* Found: the plate leaves the design in inches, and a setup's bare numbers are millimeters, so without
  `document.units(units="mm")` around it the stack comes out 25.4 times too big.
* Shown: no overlaps, a whole run with no messages, Quit closes all (the user pressed it).  It adds about 17 s.
* The through cuts go to Z-0.55, 0.05 in into the tooling plate: `sckeepout` gives 64 moves in its keep-out and
  none in the jaws'.  Nothing fastens the plate to the tooling plate in the model.  Not changed.
* A run's length was a non-issue: the user had slowed it with the slider.

## 2026-11-01: Saved for the user's commit and a `/clear`; start here

The user: the stack is the eye candy wanted for the showing on 2026-11-02, and the issues in the last entry
(through cuts into the tooling plate, no hold-down, the vise past the table, the Mikini table under a Shop mill
program) "will all be worked out", later.  So leave `show_demo.py` alone unless the user asks.  The issues on hold
in "Saved for the user's commits and a `/clear`" above still stand, with their numbers.  Nothing is running.
