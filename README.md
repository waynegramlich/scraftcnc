# `scraftlinuxcnc`: The LinuxCNC Simulator for `scraftcnc`

`scraftlinuxcnc` runs the G-code that
[`scraftcnc`](https://github.com/waynegramlich/scraftcnc) writes in
LinuxCNC's simulator, so that a program can be watched and tested
before it goes near a mill.  It is a separate package because many
`scraftcnc` users have no interest in LinuxCNC, and they need not
install any of this.

It is meant to hold:

* `install_linuxcnc.py`: installs LinuxCNC's simulator on Linux (in a
  `distrobox` box) or on Windows (in WSL 2).
* `lcnc_panel.py`: a small `tkinter` control panel, in place of
  LinuxCNC's own screens.
* `sim_linuxcnc.py` and `sim_solidcraft.py`: run a program, follow the
  tool, and show it in [SolidCraft](https://github.com/tangency-labs/solidcraft).
* `demo_linuxcnc.py`: runs a demonstration program from start to
  finish, as a test.

## Status

**Nothing is here yet.**  The code still lives in `scraftcnc`, and is
being moved here.  It will stay there until it works from here.

Only the simulator is a goal.  This package does not set up LinuxCNC
to drive a real mill: that needs a realtime kernel and hardware
drivers, which the installer deliberately leaves out.

## Why the Installation Is Small

LinuxCNC's package depends on all of its screens, whether or not they
are used.  The installer replaces that list with only what the
simulator and the panel need, so a new dependency of those screens is
never installed.  One measurement, in a `distrobox` box on Ubuntu
24.04, of LinuxCNC 2.9.10:

| | Trimmed | LinuxCNC's own list |
|---|---|---|
| Time to install LinuxCNC | 18 s | 145 s |
| Packages added | 25 | 454 |
| Downloaded | 11.3 MB | 338 MB |
| Installed size added | 130 MB | 1421 MB |

(Both leave out LinuxCNC's recommended packages.)

## Plans

* The panel gets a `--headless` option, so that tests can run it with
  no display.
* GitHub Actions run the install and the demonstration on Linux and on
  Windows through WSL 2.

## License

MIT No Attribution (`LICENSE`).
