#!/usr/bin/env python3
"""Close a running LinuxCNC quietly, leaving nothing behind.

It runs in the target, where LinuxCNC is.  This asks the display to
quit (`lcnc_bridge.py`, or another with the same habits, by `SIGTERM`),
after which the `linuxcnc` script shuts the rest down in order:

```
python3 -m scraftcam.lcnc.stop_linuxcnc
```

When that does not work in time (or with `--kill`), every LinuxCNC
process is killed (`SIGKILL`), and what they leave is cleaned up: the
HAL shared memory (`halrun -U`), the other shared memory segments, and
`/tmp/linuxcnc.lock`, which the next `linuxcnc` would ask about.  (A
`distrobox` box shares the host's processes and shared memory.)
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# The programs of a running LinuxCNC (2.9, uspace), by name: the
# `linuxcnc` script, its server, task, I/O, HAL user interface, realtime
# and the displays, which include `scraftcam`'s HMI and, in a box with
# LinuxCNC's whole package, AXIS.
PROGRAMS: frozenset[str] = frozenset(
    {
        "linuxcnc",
        "linuxcncsvr",
        "milltask",
        "io",
        "iov2",
        "halui",
        "rtapi_app",
        "axis",
        "lcnc_bridge.py",
    }
)

# The displays that quit on `SIGTERM`.
DISPLAYS: tuple[bytes, ...] = (b"lcnc_bridge.py",)

# The lock file `linuxcnc` makes, and looks for when it starts.
LOCK: Path = Path("/tmp/linuxcnc.lock")

# The shared memory keys that `halrun -U` leaves after a kill: the
# RTAPI segment (100), and the NML buffers (`B ... SHMEM` lines of
# `/usr/share/linuxcnc/linuxcnc.nml`: 1001 to 1005).
KEYS: tuple[int, ...] = (100, 1001, 1002, 1003, 1004, 1005)

# How long to wait for a gentle quit (seconds).
WAIT: float = 10.0


# Function `running()`:
def running() -> list[int]:
    """Return the process ids of LinuxCNC's programs.

    A program is matched by its name (`/proc/PID/comm`), or for the
    `linuxcnc` script and `axis` (run by `bash` and `python3`) by its
    command line; `io` must also be given an INI file, since the name
    is a common one.

    Returns:
    * (`list[int]`): The process ids, sorted.
    """
    found: list[int] = []
    entry: Path
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name: str = (entry / "comm").read_text().strip()
            words: list[str] = [
                word.decode(errors="replace")
                for word in (entry / "cmdline").read_bytes().split(b"\0")
                if word
            ]
        except OSError:
            continue
        programs: set[str] = {name} | {Path(word).name for word in words[:2]}
        if programs & PROGRAMS and (name != "io" or "-ini" in words):
            found.append(int(entry.name))
    return sorted(found)


# Function `wait_gone()`:
def wait_gone(timeout: float) -> bool:
    """Wait for every LinuxCNC program to exit.

    Arguments:
    * `timeout` (`float`): How long to wait (seconds).

    Returns:
    * (`bool`): True when none is left.
    """
    end: float = time.monotonic() + timeout
    while running():
        if time.monotonic() > end:
            return False
        time.sleep(0.2)
    return True


# Function `quit_display()`:
def quit_display() -> bool:
    """Ask the display to quit, and wait for LinuxCNC to shut down.

    Returns:
    * (`bool`): True when there was a display and LinuxCNC is gone.
    """
    pid: int
    found: bool = False
    for pid in running():
        words: list[bytes] = (
            Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        )
        if any(word.endswith(DISPLAYS) for word in words[:2]):
            os.kill(pid, signal.SIGTERM)
            found = True
    return found and wait_gone(WAIT)


# Function `kill_and_clean()`:
def kill_and_clean() -> None:
    """Kill every LinuxCNC program, and remove what they leave."""
    # Kill them all at once, so that no script is left to show a
    # window, then wait for them to go.
    pid: int
    for pid in running():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if not wait_gone(WAIT):
        print(f"still running: {running()}", file=sys.stderr)

    # The HAL shared memory, then the rest, then the lock.
    subprocess.run(
        ["halrun", "-U"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    key: int
    for key in KEYS:
        subprocess.run(
            ["ipcrm", "-M", str(key)],
            check=False,
            stderr=subprocess.DEVNULL,
        )
    LOCK.unlink(missing_ok=True)


# Function `main()`:
def main() -> int:
    """Close LinuxCNC quietly.

    Returns:
    * (`int`): The exit status (0 when LinuxCNC is gone).
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Close a running LinuxCNC quietly."
    )
    parser.add_argument(
        "--kill",
        action="store_true",
        help="kill it and clean up, without asking its display to quit",
    )
    options: argparse.Namespace = parser.parse_args()

    # Nothing running: clean up after a past kill, if anything is left.
    if not running():
        if LOCK.exists():
            print("not running; cleaning up after it")
            kill_and_clean()
        else:
            print("not running")
        return 0

    # Gently first, unless told not to.
    if not options.kill and quit_display():
        print("closed")
        return 0
    kill_and_clean()
    left: list[int] = running()
    print("killed and cleaned up" if not left else f"still running: {left}")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
