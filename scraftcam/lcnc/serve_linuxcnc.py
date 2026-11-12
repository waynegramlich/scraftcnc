#!/usr/bin/env python3
"""Run LinuxCNC's simulator, serving JSON on a port, until it is stopped.

This stays in the foreground on this computer (Linux or Windows), with
LinuxCNC in the target that `install_linuxcnc.py` made.  Other programs
reach it through `lcnc_bridge.py`'s port, and it stops when one sends
`shutdown` or the user types Control-C:

```
serve_linuxcnc                  # The `lcnc` box, or WSL's Debian.
serve_linuxcnc --box lcnc-test  # Another box.
```

No display is used: `DISPLAY` is unset, standard input is empty, and
`DISPLAY` in the INI file names the bridge, which has no window.  So
the `linuxcnc` script does not try to open its error windows, and
writes its messages to two files in the target, shown after a failure.
"""

import argparse
import os
import shlex
import signal
import socket
import sys
from pathlib import Path
from types import FrameType

from . import install_linuxcnc
from .install_linuxcnc import (
    INI_FILE,
    InstallTarget,
    capture,
    run,
    sim_directory,
    stamp,
)
from .lcnc_bridge import PORT

# Where the `linuxcnc` script writes when it has no terminal.
LOGS: tuple[str, ...] = ("linuxcnc_print.txt", "linuxcnc_debug.txt")


# Function `serving()`:
def serving(port: int = PORT) -> bool:
    """Tell whether something already answers on the port.

    Arguments:
    * `port` (`int`): The port.

    Returns:
    * (`bool`): True if a connection was accepted.
    """
    try:
        with socket.create_connection(("localhost", port), 2.0):
            return True
    except OSError:
        return False


# Function `start_command()`:
def start_command(target: InstallTarget) -> list[str]:
    """Return the command that runs LinuxCNC in the target.

    A command run by `wsl.exe --exec` or `podman exec` may have no
    `HOME`, which LinuxCNC needs, and WSL sets `DISPLAY`.

    Arguments:
    * `target` (`InstallTarget`): The target.

    Returns:
    * (`list[str]`): The command to run here.
    """
    where: str = shlex.quote(sim_directory(target))
    return target.command(
        ["env", "-u", "DISPLAY", f"HOME={target.home}", "sh", "-c",
         f"cd {where} && exec linuxcnc {INI_FILE}"]
    )  # fmt: skip


# Function `show_logs()`:
def show_logs(target: InstallTarget) -> None:
    """Print what the `linuxcnc` script wrote to its files.

    Arguments:
    * `target` (`InstallTarget`): The target.
    """
    for log in LOGS:
        path: str = f"{target.home}/{log}"
        _, text = capture(target.command(["cat", path]))
        print(f"{stamp()} --- {path}:\n{text}", flush=True)


# Function `stop_in_target()`:
def stop_in_target(target: InstallTarget) -> None:
    """Make sure that LinuxCNC is gone from the target.

    A signal stops the command here, which may not stop what it
    started in the target.

    Arguments:
    * `target` (`InstallTarget`): The target.
    """
    script: str = f"{sim_directory(target)}/stop_linuxcnc.py"
    run(target.command(["python3", script]))


# Function `serve()`:
def serve(target: InstallTarget) -> int:
    """Run LinuxCNC until it stops.

    Arguments:
    * `target` (`InstallTarget`): The target.

    Returns:
    * (`int`): The exit status.
    """
    # A second LinuxCNC would take the first one's lock and stop it.
    if serving():
        print(f"{stamp()} Port {PORT} is in use already.", file=sys.stderr)
        return 1

    # Run it, with nothing on standard input, so that it has no
    # terminal to ask questions on.
    print(f"{stamp()} Serving on localhost:{PORT}.", flush=True)
    good: bool = False
    try:
        good = run(start_command(target), source=Path(os.devnull))
    except KeyboardInterrupt:
        good = True
        print(f"\n{stamp()} Stopping.", flush=True)
    finally:
        stop_in_target(target)
    if not good:
        show_logs(target)
    return 0 if good else 1


# Function `interrupted()`:
def interrupted(_number: int, _frame: FrameType | None) -> None:
    """Treat a `SIGTERM` like Control-C, so that LinuxCNC gets stopped.

    Raises:
    * `KeyboardInterrupt`: Always.
    """
    raise KeyboardInterrupt


# Function `main()`:
def main() -> int:
    """Run LinuxCNC, as the command line asks.

    Returns:
    * (`int`): The exit status.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run LinuxCNC's simulator, serving JSON on a port."
    )
    install_linuxcnc.add_target_arguments(parser)
    options = install_linuxcnc.target_options(parser.parse_args())
    target, _ = install_linuxcnc.steps(options)
    signal.signal(signal.SIGTERM, interrupted)
    return serve(target)


if __name__ == "__main__":
    sys.exit(main())
