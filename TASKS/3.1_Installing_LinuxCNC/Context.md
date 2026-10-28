# LLM Agent Context Log

Moved from `T.s2~3`'s `Context.md` on 2026-10-28, when it was split.

## 2026-10-27: Step 2 (the user's): installing LinuxCNC

* https://linuxcnc.org/downloads/ offers only Debian 13 Trixie (ISO
  and `.deb` files under `dists/trixie/2.9-uspace/`); nothing for
  Ubuntu, and Ubuntu 24.04 has no `linuxcnc-uspace` package here.
* Chosen: Debian Trixie in a `distrobox` (the user's choice over a
  source build; a VM avoided; the Trixie `.deb` can not go on Ubuntu,
  since it needs Python 3.13).  The user installed `distrobox` 1.7.0
  and `podman` 4.9.3 from Ubuntu.
* `distrobox create --yes --name lcnc --image
  docker.io/library/debian:trixie`; `sudo` in the box needs no
  password.  `linuxcnc-uspace_2.9.10_amd64.deb` (from
  `dists/trixie/2.9-uspace/binary-amd64/`) installed with `sudo
  apt-get install -y ./FILE` (614 packages, including an RT kernel
  that only lands in the box's `/boot`).
* First start failed: `rtapi_shmem_new failed due to shmget(...):
  Permission denied`.  `rtapi_app` is setuid root, and the box's root
  is not the user in rootless podman, so it can not open the shared
  memory made by the rest of LinuxCNC.  Fixed (in the box only) with
  `sudo chmod u-s /usr/bin/rtapi_app`; a simulator needs no realtime
  priority.  A package upgrade in the box would restore the bit.
* Sample configs copied to `~/linuxcnc/configs/sim/`; started with
  `distrobox enter lcnc -- linuxcnc
  ~/linuxcnc/configs/sim/axis/axis.ini` (inch mill, AXIS screen).
* `import linuxcnc` (Python 3.13.5 in the box) and `stat().poll()`
  work: estop on, not homed, `linear_units` 1/25.4, position zero.
  The module exists only in the box, so the bridge script runs there
  (`scraftpybind` is standard library only, and the box shares the
  host network, so port 8080 is reachable).

## 2026-10-27 (evening): Entering the box after a reboot

* After a reboot the `lcnc` box must be entered again.  The first
  `distrobox enter lcnc` sets the box up; a second one at the same
  time left both stuck at "Setting up read-write mounts" (the box's
  log said `container_setup_done`).  Killing them and entering once
  worked.  Enter once, wait, then start LinuxCNC.

## 2026-10-28: Automating it; the operating systems

* The user wants a Python program that does the installation and
  prompts the user for the steps that need a person.  First, only
  the status of each operating system.
* The container tool is `podman` (the user remembered "pacman", which
  is Arch Linux's package manager), with `distrobox` on top.
* linuxcnc.org's `dists/trixie/2.9-uspace/` has `binary-amd64`,
  `binary-arm64`, `binary-armhf` and `binary-i386`, so Apple Silicon
  (arm64) has a package too.
* macOS, first look (not yet tried): `podman` runs there, but its
  containers live in a Linux VM (`podman machine`).  `distrobox` is
  meant for Linux hosts, so on a Mac the box would be made with
  `podman` directly (or a VM such as UTM or Lima).  AXIS needs an X
  server (XQuartz).  The `rtapi_app` fix should be the same.
* Windows: WSL can run Debian Trixie itself, so the `.deb` could go in
  directly, with no box; WSLg shows the GUI.

## 2026-10-28: Decisions on the installer and the probes

* The installer prints each command for the user and also puts it on
  the clipboard (`pbcopy`, `wl-copy`/`xclip`, `clip.exe`, else the
  OSC 52 terminal escape).  It lives in `scraftcnc` for now.
* The user reaches macOS and Windows only through GitHub Actions.
  First a probe workflow asks each runner (`macos-latest`,
  `macos-15-intel`, `windows-latest`) whether `podman machine` or
  WSL2 with Debian Trixie starts (nested virtualization) and whether
  `linuxcnc` installs; packaging for test.pypi.org (`scraftcnc` and
  `scraftpybind`, both names free on both indexes 2026-10-28) comes
  after.  Neither repository has `.github/` yet; `scraftcnc` has no
  `pyproject.toml`.
* Commits: Claude does the `git add` (after an `hg` checkpoint) and
  asks; the user commits; Claude pushes and runs the workflow.
* Packaging: the user develops with `ezpkg` (on pypi.org), which will
  generate the `uv` package.

## 2026-10-28: `install_linuxcnc.py` written

* `install_linuxcnc.py [--box NAME]` (default `lcnc`): six steps,
  each checked first and skipped when done: `podman` and `distrobox`
  (the user runs `sudo apt-get install -y podman distrobox`, shown
  and put on the clipboard; it waits for Enter, then checks), the box
  (`distrobox create`, then one `enter` to set it up), the newest
  `linuxcnc-uspace` for the box's architecture (read from the
  `Packages` index, SHA-256 checked, kept in `~/.cache/scraftcnc/`,
  `apt-get install` in the box), the `rtapi_app` setuid fix, the
  sample configurations in `~/linuxcnc/configs/sim`, `import
  linuxcnc`.  Linux only.  `lcnc_sim/shop_mill.ini` gets its HAL
  files from LinuxCNC's library, so it needs no sample config.
* Against the existing `lcnc` box: all six "already done", exit 0.
  `test_install_linuxcnc.py`: 5 offline tests; all 95 pass.
* Next: a background agent runs it on a throwaway `lcnc-test` box
  (removed after).
