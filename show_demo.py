#!/usr/bin/env python3
"""Bring up the whole chain, for showing it off, in one command.

On Linux, this starts LinuxCNC's simulator (`serve_linuxcnc`, from
`scraftcnc/lcnc/`, in its `lcnc` box), a SolidCraft window with the
demonstration's plate in it, standing on the table, vise, parallels and
grid plate of `examples/setup/demo_stack.json`, the watcher that
moves the tool in SolidCraft (`sim_linuxcnc.py --watch`, in the box),
and last the panel (`lcnc_panel.py`), stopped, with the demonstration's
program open:

```
./show_demo.py
```

Press Start in the panel; the tool cuts the plate in SolidCraft.  The
panel's slider starts at `SPEED`.  The panel's Quit button (or closing
the panel or SolidCraft, or Control-C here) closes everything.
What each program prints goes to
`~/.cache/scraftcnc/show/`, and the end of it is shown after a failure.

It will not disturb what is already running: a port in use stops it,
with a message.  SolidCraft has no command to quit, so it gets a
`SIGTERM`, and the recovery files that may leave are removed, so that
the next start does not ask about them.  Only this show's SolidCraft's
files are removed; their names hold its process ID.
"""

import argparse
import getpass
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

from scraftcnc.lcnc.lcnc_client import PORT as LINUXCNC_PORT
from scraftcnc.lcnc.lcnc_client import SCBridgeError, SCClient
from scraftcnc.pybind.scraftpybind import SCPyBind, SCSolidCraftError, connect
from scraftcnc.scmodelcache import SCModelCache
from scraftcnc.scsetup import SCSetup

# Where everything is.
PROJECT: Path = Path(__file__).resolve().parent
SERVER_PROJECT: Path = PROJECT
SOLIDCRAFT_BESIDE: Path = (
    PROJECT.parent / "solidcraft" / "solidcraft-linux-x86_64.AppImage"
)
STACK: Path = PROJECT / "examples" / "setup" / "demo_stack.json"
WORK: Path = Path.home() / ".cache" / "scraftcnc" / "show"
SOLIDCRAFT_DATA: Path = Path.home() / ".local" / "share" / "solidcraft"

# The `distrobox` box that LinuxCNC is in.
BOX: str = "lcnc"

# The usual ports, of SolidCraft and of the panel's commands.
SOLIDCRAFT_PORT: int = 8080
PANEL_PORT: int = 5007

# The panel's speed to start with: a whole run in about 75 seconds.
SPEED: float = 10.0

# How long each thing may take to come up, and to close (seconds).
BOX_SECONDS: float = 300.0
INSTALL_SECONDS: float = 300.0
START_SECONDS: float = 120.0
CLOSE_SECONDS: float = 15.0

# How often to look at what is running (seconds).
POLL: float = 0.25

# How much of a log to show after a failure (lines).
LOG_LINES: int = 15


# Class `SCShowFailed`:
class SCShowFailed(Exception):
    """Something could not be brought up; its message says what."""


# Function `say()`:
def say(text: str) -> None:
    """Print one line of progress, with the time.

    Arguments:
    * `text` (`str`): The line.
    """
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# Function `port_open()`:
def port_open(port: int) -> bool:
    """Tell whether something is listening on a local port.

    Arguments:
    * `port` (`int`): The port.

    Returns:
    * (`bool`): True if a connection was accepted.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), 1.0):
            return True
    except OSError:
        return False


# Function `find_solidcraft()`:
def find_solidcraft(named: str) -> str:
    """Find the SolidCraft program to run.

    Arguments:
    * `named` (`str`): The one on the command line ("" for none).

    Returns:
    * (`str`): It, or `solidcraft` on the `PATH`, or the AppImage in
      `../solidcraft`.

    Raises:
    * `SCShowFailed`: If there is none.
    """
    if named:
        found: str | None = shutil.which(named)
    else:
        found = shutil.which("solidcraft")
        if found is None and SOLIDCRAFT_BESIDE.is_file():
            found = str(SOLIDCRAFT_BESIDE)
    if found is None:
        raise SCShowFailed(
            "No SolidCraft found: put `solidcraft` on the PATH, "
            f"or use --solidcraft (looked for {SOLIDCRAFT_BESIDE})."
        )
    return found


# Function `check_ready()`:
def check_ready(ports: dict[str, int]) -> None:
    """Check what must be true before anything is started.

    Arguments:
    * `ports` (`dict[str, int]`): The ports that must be free, by the
      program that wants each.

    Raises:
    * `SCShowFailed`: If something is missing, or a port is in use.
    """
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise SCShowFailed("There is no display to show this on.")
    if not (SERVER_PROJECT / "scraftcnc" / "lcnc").is_dir():
        raise SCShowFailed(f"{SERVER_PROJECT} is not there.")
    if shutil.which("podman") is None:
        raise SCShowFailed("`podman` is not installed.")
    for name, port in ports.items():
        if port_open(port):
            raise SCShowFailed(
                f"Port {port}, for {name}, is in use: close what is on it "
                "(an earlier SolidCraft or LinuxCNC, say)."
            )


# Function `stale_pid_files()`:
def stale_pid_files(control: Path, port: int) -> list[Path]:
    """Return a port's control files left by a SolidCraft that has gone.

    A killed SolidCraft leaves them, and they can get in the way of the
    next one.  A file of a process still running is never returned.

    Arguments:
    * `control` (`Path`): SolidCraft's control directory.
    * `port` (`int`): The port.

    Returns:
    * (`list[Path]`): The files to remove.
    """
    stale: list[Path] = []
    pid_file: Path = control / f"{port}.pid"
    if pid_file.is_file():
        words: list[str] = pid_file.read_text(encoding="utf-8").split()
        if not words or not Path(f"/proc/{words[0]}").exists():
            stale.append(pid_file)
    return stale


# Function `recovery_files()`:
def recovery_files(recovery: Path, pid: int) -> list[Path]:
    """Return the recovery files of one SolidCraft.

    Each is named `TIME-PID-NUMBER`, with an extension.

    Arguments:
    * `recovery` (`Path`): SolidCraft's recovery directory.
    * `pid` (`int`): The process ID of that SolidCraft.

    Returns:
    * (`list[Path]`): Its files.
    """
    if not recovery.is_dir():
        return []
    return [
        path
        for path in recovery.iterdir()
        if path.is_file() and path.stem.split("-")[1:2] == [str(pid)]
    ]


# Class `SCShow`:
@dataclass(slots=True)
class SCShow:
    """The programs of one show, and what it takes to close them.

    Attributes:
    * `options` (`argparse.Namespace`): The command line.
    * `logs` (`dict[str, Path]`): Each program's output, by name.
    * `program` (`Path`): The G-code file.
    * `running` (`dict[str, subprocess.Popen[bytes]]`): What is running,
      by name, in the order it started.

    Constructor:
    * `SCShow(options)`
    """

    # Constructor arguments:
    options: argparse.Namespace = field(init=True)

    # Remaining attributes (alphabetized):
    logs: dict[str, Path] = field(init=False, default_factory=dict)
    program: Path = field(init=False, default=WORK / "demo.ngc")
    running: dict[str, subprocess.Popen[bytes]] = field(
        init=False, default_factory=dict
    )

    # Method `SCShow.log_end()`:
    def log_end(self, name: str) -> str:
        """Return the end of a program's output, to show after a failure.

        Arguments:
        * `name` (`str`): The program.

        Returns:
        * (`str`): Its last lines, with where the rest is.
        """
        path: Path | None = self.logs.get(name)
        if path is None or not path.is_file():
            return ""
        lines: list[str] = path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        tail: str = "\n".join(lines[-LOG_LINES:])
        return f"--- The end of {path}:\n{tail}"

    # Method `SCShow.start()`:
    def start(
        self, name: str, command: list[str], directory: Path = PROJECT
    ) -> None:
        """Start a program, in its own session, with its output in a log.

        Its own session keeps a Control-C here from reaching it, so that
        everything closes in order, and lets a signal reach its children.

        Arguments:
        * `name` (`str`): What to call it.
        * `command` (`list[str]`): The command.
        * `directory` (`Path`): Where to run it.
        """
        path: Path = WORK / f"{name}.log"
        self.logs[name] = path
        with path.open("wb") as log:
            # It runs until `close()`, past any `with` block here.
            # pylint: disable-next=consider-using-with
            self.running[name] = subprocess.Popen(
                command,
                cwd=directory,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    # Method `SCShow.check_alive()`:
    def check_alive(self, name: str) -> None:
        """Check that a program has not stopped while coming up.

        Arguments:
        * `name` (`str`): The program.

        Raises:
        * `SCShowFailed`: If it has stopped.
        """
        status: int | None = self.running[name].poll()
        if status is not None:
            raise SCShowFailed(
                f"{name} stopped, with status {status}.\n{self.log_end(name)}"
            )

    # Method `SCShow.wait_for_port()`:
    def wait_for_port(self, name: str, port: int, hint: str = "") -> None:
        """Wait until a program answers on its port.

        Arguments:
        * `name` (`str`): The program.
        * `port` (`int`): The port.
        * `hint` (`str`): What to say if it is slow.

        Raises:
        * `SCShowFailed`: If it stops, or takes too long.
        """
        end: float = time.monotonic() + START_SECONDS
        warned: bool = False
        started: float = time.monotonic()
        while not port_open(port):
            self.check_alive(name)
            if hint and not warned and time.monotonic() - started > 15.0:
                say(hint)
                warned = True
            if time.monotonic() > end:
                raise SCShowFailed(
                    f"{name} did not open port {port}.\n{self.log_end(name)}"
                )
            time.sleep(POLL)

    # Method `SCShow.start_box()`:
    def start_box(self) -> None:
        """Make sure that the box is running, as after a reboot it is not.

        Raises:
        * `SCShowFailed`: If it will not start.
        """
        state: subprocess.CompletedProcess[str] = subprocess.run(
            ["podman", "inspect", "-f", "{{.State.Running}}", BOX],
            capture_output=True,
            text=True,
            check=False,
        )
        if state.stdout.strip() == "true":
            return

        # Its first `distrobox enter` sets it up; only one at a time.
        say(f"Starting the {BOX} box (a minute or so after a reboot).")
        try:
            done = subprocess.run(
                ["distrobox", "enter", BOX, "--", "true"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=BOX_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise SCShowFailed(f"The {BOX} box did not start.") from error
        if done.returncode != 0:
            raise SCShowFailed(
                f"The {BOX} box did not start.\n{done.stdout}{done.stderr}"
            )

    # Method `SCShow.update_linuxcnc()`:
    def update_linuxcnc(self) -> None:
        """Run the installer, which checks all and updates the bridge.

        Raises:
        * `SCShowFailed`: If it fails.
        """
        say("Checking the LinuxCNC installation.")
        self.logs["install_linuxcnc"] = WORK / "install_linuxcnc.log"
        with self.logs["install_linuxcnc"].open("wb") as log:
            done = subprocess.run(
                [sys.executable, "-u", "-m", "scraftcnc.lcnc.install_linuxcnc",
                 "--box", BOX],
                cwd=SERVER_PROJECT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=INSTALL_SECONDS,
            )  # fmt: skip
        if done.returncode != 0:
            raise SCShowFailed(
                "The LinuxCNC installation is not right; run "
                "`python3 -m scraftcnc.lcnc.install_linuxcnc` in "
                f"{SERVER_PROJECT}.\n{self.log_end('install_linuxcnc')}"
            )

    # Method `SCShow.start_solidcraft()`:
    def start_solidcraft(self) -> None:
        """Start SolidCraft, clearing only what a dead one left behind.

        Raises:
        * `SCShowFailed`: If it does not come up.
        """
        port: int = self.options.solidcraft_port
        for stale in stale_pid_files(SOLIDCRAFT_DATA / "control", port):
            stale.unlink()
        say("Starting SolidCraft.")
        self.start(
            "solidcraft",
            [find_solidcraft(self.options.solidcraft), "--control", str(port)],
        )
        self.wait_for_port(
            "solidcraft",
            port,
            "If SolidCraft asks about recovering a design, answer it.",
        )

        # The token file comes with the port, or just after it.
        token: Path = SOLIDCRAFT_DATA / "control" / f"{port}.token"
        end: float = time.monotonic() + START_SECONDS
        while not token.is_file():
            self.check_alive("solidcraft")
            if time.monotonic() > end:
                raise SCShowFailed(f"SolidCraft never wrote {token}.")
            time.sleep(POLL)

    # Method `SCShow.model_part()`:
    def model_part(self) -> None:
        """Write the program, and model the plate in SolidCraft.

        Raises:
        * `SCShowFailed`: If it fails.
        """
        say("Modeling the plate in SolidCraft.")
        self.logs["model"] = WORK / "model.log"
        with (
            self.program.open("wb") as program,
            self.logs["model"].open("wb") as log,
        ):
            done = subprocess.run(
                [sys.executable, "-m", "scraftcnc.solidcraftcnc_demo",
                 "--no-path", "--opaque", str(self.options.solidcraft_port)],
                cwd=PROJECT,
                stdin=subprocess.DEVNULL,
                stdout=program,
                stderr=log,
                check=False,
            )  # fmt: skip
        if done.returncode != 0:
            raise SCShowFailed(
                f"Modeling the plate failed.\n{self.log_end('model')}"
            )

    # Method `SCShow.model_stack()`:
    def model_stack(self) -> None:
        """Model what the plate stands on, in the plate's coordinates.

        It comes after the plate, so that the plate's pocket can not cut
        anything else, and the view is set again to take it all in.

        Raises:
        * `SCShowFailed`: If it fails.
        """
        say("Modeling the table, vise, parallels and grid plate.")
        try:
            setup: SCSetup = SCSetup(
                json.loads(STACK.read_text(encoding="utf-8"))
            )
            with connect(str(self.options.solidcraft_port)) as transport:
                solidcraft: SCPyBind = SCPyBind(transport)

                # The plate leaves the design in inches.
                setup.model(solidcraft, SCModelCache(), "in")
                solidcraft.view.apply(view="iso")
        except (OSError, ValueError, SCSolidCraftError) as error:
            raise SCShowFailed(
                f"Modeling the stack failed: {error}"
            ) from error

    # Method `SCShow.start_watcher()`:
    def start_watcher(self) -> None:
        """Start the watcher, and wait until the tools are modeled.

        Raises:
        * `SCShowFailed`: If it stops, or takes too long.
        """
        say("Modeling the tools and their paths in SolidCraft.")
        self.start(
            "watcher",
            ["podman", "exec", "-u", getpass.getuser(), "-w", str(PROJECT),
             BOX, "python3", "-u", "-m", "scraftcnc.lcnc.sim_linuxcnc", "--watch",
             str(self.program),
             "--solidcraft", str(self.options.solidcraft_port)],
        )  # fmt: skip
        log: Path = self.logs["watcher"]
        end: float = time.monotonic() + START_SECONDS
        while b"watching" not in log.read_bytes():
            self.check_alive("watcher")
            if time.monotonic() > end:
                raise SCShowFailed(
                    "The watcher never got ready.\n" + self.log_end("watcher")
                )
            time.sleep(POLL)

    # Method `SCShow.start_panel()`:
    def start_panel(self) -> None:
        """Start the panel, stopped, with the program open.

        Raises:
        * `SCShowFailed`: If it does not come up.
        """
        port: int = self.options.panel_port
        say("Starting the panel.")
        self.start(
            "panel",
            [sys.executable, "-m", "scraftcnc.hmi.lcnc_panel",
             "--port", str(port), str(self.program)],
        )  # fmt: skip
        self.wait_for_port("panel", port)
        with socket.create_connection(("127.0.0.1", port), 5.0) as panel:
            panel.sendall(f"speed {self.options.speed}\n".encode())
            panel.makefile().readline()

    # Method `SCShow.bring_up()`:
    def bring_up(self) -> None:
        """Bring up the whole chain, in order.

        The panel comes last, so that Start can not be pressed until
        SolidCraft can show the run.

        Raises:
        * `SCShowFailed`: If any part of it fails.
        """
        check_ready(
            {
                "LinuxCNC": LINUXCNC_PORT,
                "SolidCraft": self.options.solidcraft_port,
                "the panel": self.options.panel_port,
            }
        )
        find_solidcraft(self.options.solidcraft)
        WORK.mkdir(parents=True, exist_ok=True)
        self.start_box()
        self.update_linuxcnc()
        say("Starting LinuxCNC.")
        self.start(
            "linuxcnc",
            [sys.executable, "-u", "-m", "scraftcnc.lcnc.serve_linuxcnc",
             "--box", BOX],
            SERVER_PROJECT,
        )  # fmt: skip
        self.wait_for_port("linuxcnc", LINUXCNC_PORT)
        self.start_solidcraft()
        self.model_part()
        self.model_stack()
        self.start_watcher()
        self.start_panel()

    # Method `SCShow.wait_until_closed()`:
    def wait_until_closed(self) -> None:
        """Wait until any one of the programs stops.

        A program that closes with status 0 was closed by the person
        showing this, so only another status is reported.
        """
        say("Ready.  Press Start in the panel.")
        say("Press Quit in the panel to end the show.")
        while True:
            for name, program in self.running.items():
                status: int | None = program.poll()
                if status is not None:
                    if status != 0:
                        say(f"{name} stopped, with status {status}.")
                        print(self.log_end(name), flush=True)
                    return
            time.sleep(POLL)

    # Method `SCShow.close_one()`:
    def close_one(self, name: str) -> None:
        """Close one program by `SIGTERM`, or kill it if it will not go.

        Arguments:
        * `name` (`str`): The program.
        """
        program: subprocess.Popen[bytes] | None = self.running.get(name)
        if program is None:
            return
        try:
            if program.poll() is None:
                os.killpg(program.pid, signal.SIGTERM)
            program.wait(timeout=CLOSE_SECONDS)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            say(f"{name} would not close, so it was killed.")
            try:
                os.killpg(program.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            program.wait()

    # Method `SCShow.close_watcher()`:
    def close_watcher(self) -> None:
        """Stop the watcher, which runs in the box.

        A signal to `podman exec` may not reach it, but the box shares
        this computer's processes, so it can be signaled from here.
        """
        if "watcher" in self.running:
            subprocess.run(
                ["pkill", "-INT", "-f",
                 f"sim_linuxcnc.py --watch {self.program}"],
                check=False,
            )  # fmt: skip
            self.close_one("watcher")

    # Method `SCShow.close_linuxcnc()`:
    def close_linuxcnc(self) -> None:
        """Ask LinuxCNC to shut down, or else signal it."""
        program: subprocess.Popen[bytes] | None = self.running.get("linuxcnc")
        if program is None or program.poll() is not None:
            return
        try:
            with SCClient(timeout=10.0) as lcnc:
                lcnc.call("shutdown")
            program.wait(timeout=60.0)
        except (OSError, SCBridgeError, subprocess.TimeoutExpired):
            self.close_one("linuxcnc")

    # Method `SCShow.remove_leftovers()`:
    def remove_leftovers(self) -> None:
        """Remove what the `SIGTERM` left of this show's SolidCraft."""
        if "solidcraft" not in self.running:
            return
        port: int = self.options.solidcraft_port
        control: Path = SOLIDCRAFT_DATA / "control"
        pid_file: Path = control / f"{port}.pid"
        words: list[str] = (
            pid_file.read_text(encoding="utf-8").split()
            if pid_file.is_file()
            else []
        )
        pid_file.unlink(missing_ok=True)
        (control / f"{port}.token").unlink(missing_ok=True)
        if words:
            for path in recovery_files(
                SOLIDCRAFT_DATA / "recovery", int(words[0])
            ):
                path.unlink()

    # Method `SCShow.close()`:
    def close(self) -> None:
        """Close everything, the last started first."""
        say("Closing.")
        self.close_one("panel")
        self.close_watcher()
        self.close_linuxcnc()
        self.close_one("solidcraft")
        self.remove_leftovers()
        say("Closed.")


# Function `interrupted()`:
def interrupted(_number: int, _frame: FrameType | None) -> None:
    """Treat a `SIGTERM` like Control-C, so that everything is closed.

    Raises:
    * `KeyboardInterrupt`: Always.
    """
    raise KeyboardInterrupt


# Function `main()`:
def main() -> int:
    """Bring up the whole chain, and close it when the show is over.

    Returns:
    * (`int`): The exit status.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Bring up SolidCraft, LinuxCNC and the panel, connected."
    )
    parser.add_argument(
        "--solidcraft", default="", help="the SolidCraft program to run"
    )
    parser.add_argument(
        "--solidcraft-port",
        type=int,
        default=SOLIDCRAFT_PORT,
        help="SolidCraft's control port (default: %(default)s)",
    )
    parser.add_argument(
        "--panel-port",
        type=int,
        default=PANEL_PORT,
        help="the panel's command port (default: %(default)s)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=SPEED,
        help="the panel's speed to start with (default: %(default)s)",
    )
    show: SCShow = SCShow(parser.parse_args())
    signal.signal(signal.SIGTERM, interrupted)
    status: int = 0
    try:
        show.bring_up()
        show.wait_until_closed()
    except SCShowFailed as error:
        print(f"show_demo.py: {error}", file=sys.stderr)
        status = 1
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        # A second Control-C must not leave the rest running.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        show.close()
    return status


if __name__ == "__main__":
    sys.exit(main())
