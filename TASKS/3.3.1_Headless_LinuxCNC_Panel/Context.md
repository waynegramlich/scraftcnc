# LLM Agent Context Log

## 2026-11-02: Squeezed; where things stand

Works: `lcnc_panel.py --headless`, `test_lcnc_end_to_end.py` (`SCRAFTCNC_LINUXCNC=1`, 10 tests, about 2 minutes), `lcnc_panel.py` as a
client on the host, and `./show_demo.py` (Linux; needs nothing else on port 8080; ended by the panel's Quit; the user: "good enough to
show").  Never shown: a real reboot (only a stopped box), anything on WSL since protocol 2.  The user commits `scraftlinuxcnc` before
this repository, as `lcnc_client.py` links into it.

* The aim of `--headless`: tests exercise the whole path with no display, so no `Xvfb`.  `SCPanel` is unchanged, built on
  `lcnc_headless.py`, which stands in for the `tkinter` parts used (`use_headless()`); a slider's command and layout are not exercised.
* Command port: `press LABEL`, `type LINE`, `show` (JSON), `answer VALUE` (headless only).  On a real window, `press Set Origin` waits for
  a person.  The path test allows a vertical line through each tool change, as `G43` changes the reading there.
* `command.mode(MODE_AUTO)` while paused ends the program, silently, so `resume()` does not set the mode.
* SolidCraft has no quit command.  `SIGTERM` closes it, leaving `PORT.pid`, `PORT.token` and maybe recovery files named
  `TIME-PID-N.{json,lock,sc}`; those of its PID are removed.  `setsid` on the AppImage forks, so its PID is not the group to signal.
* `SCPathRack` shows the first tool's path from the start; an empty spindle changes nothing.
* `examples/setup/demo_stack.json` is in the program's coordinates: Mikini table, Kurt D688 along Y closed on the tooling plate (5-1/2 in),
  1-1/2 in parallels, tooling plate.  The through cuts reach 0.05 in into the tooling plate (`sckeepout`: 64 moves), nothing fastens the
  plate, the vise passes the table, and the Mikini table is under a Shop mill program; the user: these "will all be worked out", later.

### Issues the user put on hold, keeping their numbers

2. `sim_linuxcnc.py` stays, as `show_demo.py` runs it.  Claude recommends moving it to `lcnc_client`, to run on the host, and removing the
   second `ORIGIN` in `lcnc_panel.py`.
3. Tool change height: a longer tool's tip sits lower there (`T.tl~3.2`), and the end to end test allows any Z above a tool change.
   Claude recommends leaving it until the shop files have gauge lengths.
4. Rebuild the `lcnc` box with the trimmed install: the user said yes.  Check `sim_linuxcnc.py` on the trimmed box.

Also: the WSL probe comes near the end (the user).  One repository or two is undecided; the aim is isolating the LinuxCNC download.
