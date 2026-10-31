# Summary of `T.il` Installing LinuxCNC

LinuxCNC's simulator is installed and shown running a program on Linux
and on Windows through WSL 2 (2026-10-30, probe run 41157277075,
e992757).  Decided and done:

* `install_linuxcnc.py`: step by step, each step checked first and
  skipped when done; a step needing the user shows the command and
  waits (`--yes` runs it, for runners).  Routes: a `distrobox` box on
  Linux, WSL 2's Debian on Windows.  Only what LinuxCNC needs
  (`--no-install-recommends`): 454 and 589 packages.
* `demo_linuxcnc.py`: copies the project in when the target does not
  share it, starts LinuxCNC (`lcnc_panel.py`, on `Xvfb` with no
  screen), waits for the panel's `ping`, runs `sim_linuxcnc.py` to the
  end and closes everything.  Both runners: about 1545 samples in
  77.4 s, 0 errors, 0 delay messages, nothing left running.  `Xvfb`
  uses TCP where it can not write `/tmp/.X11-unix` (the WSL runner).
* `lcnc_panel.py` gained a `messages` port command, since the panel
  and `sim_linuxcnc.py` share LinuxCNC's error channel.
* macOS was dropped (the user's decision): testing it credibly needs
  Apple's hardware.  Its `podman machine`, `colima` and QEMU routes
  were removed; they had installed LinuxCNC on GitHub's runners (run
  40734286264), and the code is in the history.

Not done: a backend only install without the GUI packages (about 195
MB against 2.4 GB; researched in `Context.md`, not tried).  No
workflow runs this on its own: `probe_linuxcnc.yml` is started by hand.
