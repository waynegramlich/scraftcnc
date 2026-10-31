# 3.1 Installing LinuxCNC

Install `linuxcnc-uspace`, LinuxCNC's non-realtime simulator, where
our scripts can reach it.  LinuxCNC offers packages only for Debian
13 Trixie, so it runs in a Debian Trixie `distrobox` (`lcnc`, on
`podman`) on the user's Ubuntu 24.04 machine.  That was done by hand.

## Automate It

A Python program that does the installation step by step, and when a
step needs the user (installing a package with `sudo`, a password, a
choice), says exactly what to do, waits, and checks that it was done
before going on (as Claude Code does).  Standard library only, like
the rest of `scraftcnc`.

The steps done by hand (see `Context.md`): `distrobox` and `podman`,
the box, the `.deb` for the machine's architecture, the `rtapi_app`
setuid fix, the sample configurations, a check that `import linuxcnc`
works in the box.

## Operating Systems

* Ubuntu Linux: a `distrobox` box.
* Windows: through WSL 2.

macOS is not a goal (the user's decision, 2026-10-30), and its routes
were removed from `install_linuxcnc.py`.

## Done When

* LinuxCNC runs a program on Linux and on Windows through WSL, or it
  is known why it can not on one.
