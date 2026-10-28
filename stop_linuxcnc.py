#!/usr/bin/env python3
"""Close a running LinuxCNC quietly, leaving nothing behind.

Part of the simulation's tracking (`T.tl~3.2`).  Closing LinuxCNC's
AXIS window by hand asks "Do you really want to close LinuxCNC?", and
killing AXIS with a signal makes the `linuxcnc` script show its error
window (its `ErrorCheck`), both on the user's screen.  This asks AXIS
to quit (`axis-remote --quit`), after which the `linuxcnc` script
shuts the rest down in order, with no window:

```
distrobox enter lcnc -- ./stop_linuxcnc.py
```

When that does not work in time (or with `--kill`), every LinuxCNC
process is killed (`SIGKILL`, so the script's traps can not open a
window either), and what they leave is cleaned up: the HAL shared
memory (`halrun -U`), the other shared memory segments, and
`/tmp/linuxcnc.lock`, without which the next `linuxcnc` would ask
"LinuxCNC is still running.  Restart it?".  It runs in the `lcnc`
box, where `axis-remote` and `halrun` are (the box shares the host's
processes and shared memory).
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# The programs of a running LinuxCNC (2.9, uspace, AXIS), by name:
# the `linuxcnc` script, its server, task, I/O, HAL user interface,
# realtime and display.
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
    }
)

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


# Function `quit_axis()`:
def quit_axis() -> bool:
    """Ask AXIS to quit, and wait for LinuxCNC to shut down.

    Returns:
    * (`bool`): True when LinuxCNC is gone.
    """
    try:
        answered: int = subprocess.run(
            ["axis-remote", "--quit"], check=False, timeout=WAIT
        ).returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"axis-remote failed: {error}", file=sys.stderr)
        return False
    return answered == 0 and wait_gone(WAIT)


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
        help="kill it and clean up, without asking AXIS to quit first",
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
    if not options.kill and quit_axis():
        print("closed")
        return 0
    kill_and_clean()
    left: list[int] = running()
    print("killed and cleaned up" if not left else f"still running: {left}")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
