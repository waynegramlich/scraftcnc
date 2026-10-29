# LLM Agent Context Log

## 2026-10-28: Split into sub-tasks

* The user: we got side-tracked into replacing LinuxCNC's GUI, which
  is not this project's goal; LinuxCNC was brought up to give us a
  CNC controller to talk to.  The work was split, and this log with
  it:
  * `T.il~3.1` Installing LinuxCNC (the `lcnc` distrobox).
  * `T.tl~3.2` Tracking LinuxCNC (`sim_linuxcnc.py`, the shop mill
    configuration, running the demo's G-code).
  * `T.rlg~3.3` Replace LinuxCNC GUI (the tool and the trace in
    SolidCraft: `ToolRack`, `RevealTrace`, `probe_reveal.py`, the
    SolidCraft timings and the `engine.batch` findings).

## 2026-10-28: `T.rlg~3.3` and `T.mlcp~3.4` closed

* The panel (`lcnc_panel.py`) drives LinuxCNC and SolidCraft follows
  through `sim_linuxcnc.py --watch`; the user: "It was perfect."
  Both closed; their summaries say what was done.
* To bring it all up again (the `lcnc` box entered once first):

  ```
  solidcraft --control 8080 &
  ./solidcraftcnc_demo.py --no-path --opaque 8080 > demo.ngc
  distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
  echo "open $PWD/demo.ngc" | nc -q 1 127.0.0.1 5007
  distrobox enter lcnc -- ./sim_linuxcnc.py --watch demo.ngc \
      --solidcraft 8080
  ```

  A second run wants a fresh design (`file.new`), or the sketch
  names clash.  Started from Claude's background shell, the windows
  were hard for the user to find.
* Left: `T.il~3.1` (Suspended): `demo_linuxcnc.py` still waits for
  AXIS, and the other platforms.  `T.s2` stays Open until it is
  settled.
* Session start check (2026-10-28): flake8 7.4.1 (7.5.0 out) and
  mypy 2.4.0 (2.4.1 out); not updated, the user not yet asked.

## 2026-10-28: A display bug seen in the user's run

* With the new speeds and feeds (`T.msaf~2.1`), the user's panel run
  "was very good", but near the end the roughing mill's (T8) path
  became visible again (`sim_solidcraft.py`'s `PathRack`).  Not yet
  looked into.  SolidCraft is not on Claude's `PATH`: start
  `../solidcraft/solidcraft-linux-x86_64.AppImage --control 8080`.
