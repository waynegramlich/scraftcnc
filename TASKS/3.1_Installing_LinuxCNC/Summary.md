# Summary of `T.il` Installing LinuxCNC

LinuxCNC's simulator is installed and shown running a program on Linux
and on Windows through WSL 2 (2026-10-27 to 2026-11-01; last probe run
41349899125, 1090b54).  Closed at the user's word on 2026-11-02, with
the items below still undone.  Decided and done:

* The installer and its probe now live only in `../scraftlinuxcnc`
  (`T.mcfs~1` there), which isolates the LinuxCNC package download.
  `install_linuxcnc.py`, `demo_linuxcnc.py`, `stop_linuxcnc.py`, their
  tests, `probe_linuxcnc.yml` and `lcnc_sim/` were removed from here.
* Routes: a `distrobox` box (`lcnc`, Debian Trixie on `podman`) on
  Linux, WSL 2's Debian on Windows.  macOS was dropped (the user's
  decision); its routes are in the history.
* The trimmed install: the `.deb`'s `Depends` replaced by an allow list,
  so upstream GUI dependencies are ignored.  25 packages and 130 MB
  against 454 and 1421 MB.  `libxinerama1` is on the list since a plain
  container lacks it.  Both runners passed the demo: about 1737 samples
  in 87 s, 0 errors, 0 delay messages, nothing left running.
* `rtapi_app` must not be setuid in a rootless box
  (`chmod u-s /usr/bin/rtapi_app`); a package upgrade restores the bit.
  After a reboot, enter the box once and wait: two `distrobox enter`s at
  the same time both hang.
* `lcnc_panel.py` is a client of `serve_linuxcnc` (protocol 2), on the
  host, through `lcnc_client.py`, a link into `../scraftlinuxcnc`.
  `scraftlinuxcnc` takes only the pain of getting LinuxCNC, with no
  dependency on `scraftcnc`.  Headless work is `T.hlp~3.3.1`.
* LinuxCNC keeps G54 in its `.var` file.

Not done: the `lcnc` box still has its full install (941 packages, 2412
MB; the rebuild is on hold in `T.hlp~3.3.1`).  `newest_package()` has no
retry.  WSL has not been run since protocol 2; the user wants that probe
near the end.  `pyproject.toml` for `scraftcnc` was not started, and the
trial found that plain top level modules fail: data files beside them
are lost on install, and `tools`, `mount` and `shops` are taken on PyPI.
The user has not decided on one repository or two.  A real mill needs
realtime, which this install undoes; only the simulator was in scope.
