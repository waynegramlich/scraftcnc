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

For now, only find out where each stands; solve the problems later:

* Ubuntu Linux: done by hand.
* macOS (Apple Silicon and Intel): to be found out.
* Windows: through WSL (not a concern for now).

## Done When

* The program installs LinuxCNC on Ubuntu from nothing, and the
  status on macOS and Windows is written down.
