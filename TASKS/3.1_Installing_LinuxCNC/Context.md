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

## 2026-10-28: Throwaway box test

* `./install_linuxcnc.py --box lcnc-test < /dev/null` from no box
  (07:51-07:59): exit 0 in 7 min 52 s, nothing asked of the user.
  [1/6] already done (host tools); [2/6] box made and set up, about
  2 min; [3/6] newest `linuxcnc-uspace` 1:2.9.10 for amd64, 25 MB
  `.deb` downloaded to `~/.cache/scraftcnc/`, 614 packages, about
  6 min; [4/6] `chmod u-s` done; [5/6] already done (the box shares
  the real home, where the `lcnc` samples are); [6/6] already done
  (only a check; passes once 3 is in).
* So on this machine only steps 2-4 could be shown "done"; steps 1
  and 5 doing their work is not yet tested from nothing.
* Harmless noise in the apt output: `fchownat() of /dev/...`,
  `apparmor_parser ... Access denied`, `invoke-rc.d` refusals, and
  an initramfs for the RT kernel in the box's `/boot`.
* Second run: all six "already done", exit 0, 0.9 s.  In the box
  `import linuxcnc` worked (Python 3.13) and `rtapi_app` was 0755.
* No fixes needed.  Load peak 2.12 (1 minute average, sampled every
  30 s).
* `distrobox rm --force lcnc-test` (it removes a home only with
  `--rm-home`): gone (`podman container exists` false); only `lcnc`
  left.  The `.deb` and the `debian:trixie` image kept.  No
  leftover processes.

## 2026-10-28: Runner probes

* `.github/workflows/probe_linuxcnc.yml` (by hand only) with
  `lcnc_sim/probe_install.sh` (runs as root in Debian: the newest
  `linuxcnc-uspace` from the `binary-ARCH/Packages` index, SHA256
  checked, `apt-get install ./FILE`, `import linuxcnc`, `halrun`).
* Run 40710822308 (commit 0f544d4), newest package 1:2.9.10:
  * `ubuntu-latest`: works.  podman 5.7.0, distrobox 1.8.2.4, a
    `debian:trixie` box; install and import ok (Python 3.13.5).
  * `windows-latest`: works, on WSL 2 (not only WSL 1).  WSL
    3.0.3.0, kernel 6.18.54.1; `Vampire/setup-wsl@v7` with
    `Debian-13` (already Trixie), the `.deb` straight in, no
    container; install about 5 1/2 min, import ok.
  * `macos-latest` (Apple Silicon): fails, no VM can start.
    `kern.hv_support` is 0 (no nested virtualization): podman
    (Homebrew) `machine init` ok, `machine start` "vfkit exited
    unexpectedly with exit code 1"; `colima` (lima, `vz`) fails too.
  * `macos-15-intel` (Macmini, i7-8700B): `kern.hv_support` 1.
    `brew install podman` fails ("no bottle available": Homebrew
    has no Intel podman for macOS 15, and podman 6.1.4 ships an
    arm64 installer only; 5.8.9 still has `amd64`/`universal`).
    `colima` (lima, `vz`, Ubuntu 24.04 VM, Docker) starts in about
    4 1/2 min, and a `debian:trixie` container installs (about 9
    min, the RT kernel's initramfs included) and imports: works.
  * The `halrun` check was wrong everywhere: as root, `rtapi_app`
    says "Refusing to run as root without fallback UID specified"
    and `halrun` still exits 0.  Fixed (run as `sudo`'s user or a
    new `probe` user, check that the thread exists); the Status step
    also failed when there was no `probe.log` (fixed).  Intel now
    also tries podman 5.8.9's installer.  Waiting for the user's
    commit to rerun.

## 2026-10-28: One program for every OS (the user's decisions)

* No native macOS port and no self-hosted runner.  Goal: all four
  runners green with `install_linuxcnc.py --yes`.
* `install_linuxcnc.py` now picks a route (`choose_route()`;
  `--route` overrides) and builds a `Target` (prefixes that run a
  command in it as root or as the user), then the same 7 steps in
  every target: a user who is not root, Debian Trixie (an older one
  upgraded), `linuxcnc-uspace` (newest, SHA256 checked, sent in
  through standard input unless the home is shared), `rtapi_app`
  not setuid, sample configurations, `import linuxcnc`, and
  `halrun` as that user (thread listed, nothing "failed"; skipped
  when `rtapi_app` is running, since `halrun` would stop it).
  * Linux: the `distrobox` box, as before.  Commands now go in by
    `podman exec` (root, or the user with `-w HOME`):
    `distrobox enter` passes its command through `eval`, which
    broke quoted arguments (`sh -c '...'`).
  * Windows: WSL 2 with `Debian` (`wsl.exe --install -d Debian
    --no-launch --web-download` through `ask_user()`; WSL 1 is
    converted with `--set-version`); commands by `wsl.exe -d Debian
    -u root|lcnc --exec`, with `WSL_UTF8=1`; a `lcnc` user.
  * macOS with `kern.hv_support` 1: Apple Silicon `brew install
    podman`, `podman machine init/start`; Intel `brew install colima
    docker`, `colima start`; then a `debian:trixie` container `lcnc`
    (`sleep infinity`) with a `lcnc` user.
  * macOS with 0: `brew install qemu`; Debian's
    `debian-13-genericcloud-ARCH.qcow2` (SHA512SUMS checked); a 20G
    overlay disk, an ed25519 key and a cloud-init NoCloud seed ISO
    (`hdiutil makehybrid`, label `cidata`) in `~/.cache/scraftcnc/
    vm/`; `qemu-system-aarch64 -accel tcg,thread=multi -cpu
    max,pauth-impdef=on` (`hvf` when there is one), daemonized, `ssh`
    on 127.0.0.1:2222 as `debian`; waits up to 45 min for `ssh`.
    No container: the VM is Debian Trixie itself.
* `--yes` runs what `ask_user()` would ask for.  `run()` prints every
  output line with the time and, every 5 minutes, a progress line
  (minutes, lines, `apt` packages set up), so a 6 hour timeout on
  the emulated job still shows how far it got.
* Checked locally on the `lcnc` box: all 9 steps "already done",
  `halrun` really run (thread listed).  14 offline tests.
* `probe_linuxcnc.yml` now runs `python -u install_linuxcnc.py
  --yes` on the four runners (one matrix, `fail-fast: false`;
  timeouts 60, 60, 90 and 355 minutes for `macos-latest`), and keeps
  the VM's console log as an artifact; `lcnc_sim/probe_install.sh`
  retired.

## 2026-10-28: Only the needed packages

* The user: `apt-get install -y --no-install-recommends` on every
  route.  Left out: the docs, `librsvg2-dev`, `x11-xserver-utils`,
  `hostmot2-firmware-all`, the RT kernel (and its initramfs),
  `python3-pil`, `python3-pil.imagetk`.
* Checked in the `lcnc` box (read only): `/usr/bin/axis` and
  LinuxCNC's Python modules use neither `PIL` nor `xset`; the sample
  configurations and `axis` belong to `linuxcnc-uspace`.  So no
  Recommends is added back.
* New step 8 (of 8 common ones): the AXIS screen's modules import
  with no `DISPLAY` (`tkinter`, `OpenGL.GL/GLU`, `gcode`, `rs274.*`,
  `hershey`, `propertywindow`, `nf`, `bwidget`, `glnav`, `hal`,
  `linuxcnc`); all load in the `lcnc` box.  The installer prints how
  many packages `apt-get` installed (`dpkg-query` before and after).
* Local `lcnc` box: 10/10 "already done".  Tests 15 (all 105 pass);
  checkers clean.

## 2026-10-28: Probe run 40730774714 (561325d, all routes Python)

* `ubuntu-latest` (distrobox): pass, about 2 min; apt installed 454
  packages (`--no-install-recommends`).
* `macos-15-intel` (colima): pass, 15.5 min (colima VM 4 min);
  626 packages.
* `macos-latest` (QEMU, software emulation, `kern.hv_support` 0):
  pass, 13.5 min (VM booted in 1.4 min, install 11 min); 544
  packages.  Far under the 6 hour limit.
* `windows-latest` (WSL 2, Debian): WSL 2 came up, then step 2
  failed: `wsl.exe -u root --exec useradd ...` gave "execvpe(useradd)
  failed: No such file or directory" (`--exec` has no login shell,
  so no `/usr/sbin` on root's `PATH`).  Fixed: every WSL command
  goes through `/usr/bin/env PATH=...` (`WSL_ENV`).
* On every passing runner: `import linuxcnc`, the AXIS modules and
  `halrun` (as a user who is not root) all pass.

## 2026-10-28: Probe run 40734286264 (2d88d02): all four pass

* With the WSL `PATH` fix, all four runners install LinuxCNC and
  pass `import linuxcnc`, the AXIS modules and `halrun`:
  `ubuntu-latest` 1.7 min, `windows-latest` (WSL 2) 5.4 min,
  `macos-latest` (QEMU, software emulation) 13.7 min,
  `macos-15-intel` (colima) 19.5 min.
* Not yet shown: LinuxCNC running a program on each (the user's bar
  for 3.1: "runs on all platforms, or we know why not").

## 2026-10-28: Running a program on every runner

* `demo_linuxcnc.py` (same target arguments as `install_linuxcnc.py`,
  now shared through `add_target_arguments()` and
  `target_options()`): installs `xvfb` in the target if missing
  (`ask_user()`, so `--yes` runs it; only for CI, since a desktop
  has a display: `--display :0`), puts the project in the target
  (a box sees it in place; others get a `tar` copy in
  `~/scraftcnc_demo` through `send_file()`, `\r\n` made `\n`, and a
  Windows checkout's text-file symlink replaced by its file), then
  runs itself with `--inside` there as the non-root user: writes
  `demo.ngc`, `Xvfb -displayfd 1`, `linuxcnc
  lcnc_sim/shop_mill.ini`, waits for `axis-remote --ping`, runs
  `sim_linuxcnc.py demo.ngc --speed 10` (with a time limit), then
  `stop_linuxcnc.py`, and checks nothing is left.  One exec session
  holds it all, so no background process must outlive a `wsl.exe`,
  `docker exec` or `ssh`.  "Unexpected realtime delay" lines are
  counted, not failed.
* Local test on a throwaway `lcnc-demo` box (the `lcnc` box has no
  `xvfb`, and its packages stay as they are).

## 2026-10-28: Parked

* The agent proving the demo runs on every runner was stopped by the
  user (about 20-25 minutes, ~175k tokens; "an error").  Its work is
  on disk, not staged, not run by the checkers since:
  `demo_linuxcnc.py`, `test_demo_linuxcnc.py`, changes to
  `install_linuxcnc.py` (shared target arguments) and
  `probe_linuxcnc.yml`.  Its local test on a throwaway `lcnc-demo`
  box ran the demo to the end; the box is removed.  Parked until at
  least the afternoon (the user's token budget); then 5 minute
  rounds.

## 2026-10-28: Suspended

* The user: good enough for now; back to it in a day or so.  Still
  open: `demo_linuxcnc.py` on the four runners (on disk, unstaged,
  checkers not run since the agent was stopped).

## 2026-10-28: Installing the backend only (research, not tried)

* With `lcnc_panel.py` in place of AXIS, the GUI packages are not
  needed.  Measured in the `lcnc` box: 2412 MB in 941 packages;
  `linuxcnc-uspace`'s hard `Depends` closure is 1850 MB (788
  packages: Qt5 with WebEngine, VTK, OpenCV, GTK2 and 3, Mesa and
  Vulkan, two LLVMs, espeak, gstreamer, GDAL); about 560 MB more came
  from Recommends (the RT kernel, 109 MB; `linuxcnc-doc-en`, 31 MB).
* Backend plus the panel: `linuxcnc-uspace` (91 MB) and the closure
  of `python3`, `libboost-python1.83.0`, `libc6`, `libedit2`,
  `libgcc-s1`, `libgpiod3`, `libmodbus5`, `libpython3.13`,
  `libstdc++6`, `libtirpc3t64`, `libudev1`, `libusb-1.0-0`,
  `tcl8.6`, `python3-tk`, `procps`, `psmisc` (104 MB, 100 packages,
  80 MB of it the Debian base): about 195 MB, about 90% less.
* Options, in order:
  1. `--no-install-recommends` in `install_linuxcnc.py`: free, saves
     about 560 MB.
  2. An `equivs` dummy package that provides the GUI dependencies,
     so apt skips them (cleaner than `dpkg --force-depends`, which
     leaves apt reporting a broken system).  AXIS and the other GUIs
     then do not start, which is fine.
  3. A source build with the GUIs turned off: same size, needs a
     toolchain; only if 2 fails.
* Not checked: whether the `linuxcnc` script, `milltask` or
  `sim_linuxcnc.py` load a dropped package at run time (e.g.
  `numpy`, `blt`, `bwidget`).  The test: a fresh box with 1 and 2
  that starts `lcnc_sim/shop_mill.ini` and runs the demo.  Smaller
  downloads also help the macOS and Windows probe runs.

## 2026-10-30: Reopened; testing the panel on macOS (suggested, not agreed)

* The user's goal: the `tkinter` panel, driven by a test suite over a
  socket, talking to LinuxCNC on Apple Silicon macOS, with no Mac
  bought, so that "tested on macOS" is a credible claim.
* macOS in QEMU on this PC is out: `vmapple` needs an Apple Silicon
  host with HVF (and took only macOS 12 guests when merged), OSX-KVM
  is Intel macOS, and Apple's license ties macOS to Apple hardware.
  `macos-latest` is real Apple Silicon, and free for a public project.
* The catch: `lcnc_panel.py` needs `import linuxcnc`, which is Linux
  only, so today the panel can only run inside the VM.  Suggested: a
  bridge at the `Machine` class (`lcnc_panel.py:217`): the panel native
  on macOS, a bridge in the VM as the INI file's `DISPLAY`, joined by
  `ssh -L`.  Then the VM needs no GUI packages (the backend only entry
  above).
* The runner has no hypervisor (`kern.hv_support` 0), so it tests TCG,
  not the `podman machine` route that real Macs take.  Suggested: one
  rented Mac (or a volunteer) before making the claim.
* Not yet known: whether a hosted runner's GUI session lets a Tk window
  open and `screencapture` work; whether LinuxCNC runs a program under
  TCG (`demo_linuxcnc.py` never ran on the runners).

## 2026-10-30: macOS dropped

* The user's decision: macOS is removed from the test vector; nothing
  is to be spent on testing on Apple's hardware.  The macOS testing
  plan in the entry above is dropped, bridge included.
* Checked: `demo_linuxcnc.py:316-321` still waits on `axis-remote
  --ping`, while `lcnc_sim/shop_mill.ini:32` starts `lcnc_panel.py`, so
  it needs fixing before it can pass.  Last probe run 40734286264
  (2d88d02) covered the install only.  `ruff`, `mypy --strict` and
  `test_demo_linuxcnc` pass on it today.

## 2026-10-30: macOS removed; the demo passes locally with the panel

* Removed: the `podman`, `colima` and QEMU routes, their tests, the
  macOS jobs in `probe_linuxcnc.yml`.  `Details.md` updated, at the
  user's word.
* `demo_linuxcnc.py` waits on the panel's `ping` (port 5007), not AXIS.
  `pack()` gives files with `#!` mode 755, since LinuxCNC runs
  `lcnc_panel.py` directly (first tested for real by a WSL run).  The
  panel reads the error channel too, so its new `messages` port command
  is part of the verdict.
* Fresh throwaway `lcnc-demo` box (removed since): install about 5 min
  (454 packages); demo PASS, 1545 samples in 77.4 s, 0 errors, 0 delay
  messages, nothing left running.
* Left: the probe run on `ubuntu-latest` and `windows-latest` (about 8
  min), which needs these changes committed and pushed by the user;
  then `Summary.md` and close.  `SharsMD` is for the next task.

## 2026-10-30: Probe run 41151300976 (994400c): Ubuntu passes, WSL stops at `Xvfb`

* `ubuntu-latest`: pass, 3.2 min; install 454 packages; demo 1545
  samples in 77.4 s, 0 errors, 0 delay messages, nothing left running.
* `windows-latest`: 7 min; the install passed (589 packages), then
  `Xvfb` as `lcnc` failed before LinuxCNC started: "Mode of
  /tmp/.X11-unix should be set to 1777", "failed to bind listener",
  "Failed to find a socket to listen on".  Probably WSLg's own
  `/tmp/.X11-unix` (from memory; not checked on the runner).  So a
  program under WSL is still not shown.
* Suggested, not done: `Xvfb` on TCP (`start_xvfb()` passes `-nolisten
  tcp`), which needs the user's commit and one more run (about 8 min).
  Not closed: the user was to decide on anything but two passes.

## 2026-10-30: `Xvfb` on TCP where it can not make its socket

* Reproduced in a scratch `debian:trixie` container: a non-root user
  and a root-owned `/tmp/.X11-unix` mode 755 give the runner's errors;
  `-listen tcp -nolisten unix` with `DISPLAY=127.0.0.1:0` starts, and
  Tk opens a window.  `xvfb_listen()` chooses TCP only when the
  directory can not be written.  Waiting for the user's commit, then
  one more probe run.

## 2026-10-30: Probe run 41157277075 (e992757): both pass; closed

* `ubuntu-latest`: 3.1 min; 1545 samples in 77.4 s (`DISPLAY=:0`).
* `windows-latest` (WSL 2): 6.6 min; 1546 samples in 77.4 s
  (`DISPLAY=127.0.0.1:0`, so the TCP route was the one needed).
* Both: 0 errors, 0 delay messages, nothing left running.
