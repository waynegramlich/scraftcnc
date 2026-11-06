#!/usr/bin/env python3
"""Bring up the whole chain, for showing it off, in one command.

On Linux, this starts LinuxCNC's simulator (`serve_linuxcnc`, from
`scraftcnc/lcnc/`, in its `lcnc` box), a SolidCraft window, the
watcher that moves the tool in SolidCraft (`sim_linuxcnc --watch`, in
the box), and last the HMI (`lcnc_hmi.py`), stopped, with the
demonstration's program open.  The HMI draws the program's setup
(table, vise, parallels, grid plate, stock and the plate) in
SolidCraft from its `(SCC: ...)` lines alone:

```
./show_demo.py
```

Press Start in the HMI; the tool cuts the plate in SolidCraft.  The
HMI's slider starts at `SPEED`.  The HMI's Quit button (or closing
the HMI or SolidCraft, or Control-C here) closes everything.
What each program prints goes to
`~/.cache/scraftcnc/show/`, and the end of it is shown after a failure.

It will not disturb what is already running: a port in use stops it,
with a message.  SolidCraft has no command to quit, so it gets a
`SIGTERM`, and the recovery files that may leave are removed, so that
the next start does not ask about them.  Only this show's SolidCraft's
files are removed; their names hold its process ID.
"""

# The show, GUI and headless, and its report, are one script.
# pylint: disable=too-many-lines

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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, cast

# Run as `./show_demo.py` (from any directory): the repository root
# goes on the path, so that the `scraftcnc` package can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scraftcnc.lcnc.lcnc_client import PORT as LINUXCNC_PORT
from scraftcnc.lcnc.lcnc_client import BridgeClient, BridgeError
from scraftcnc.pybind.scraftpybind import PyBind, connect

# Where everything is.
PROJECT: Path = Path(__file__).resolve().parent
SERVER_PROJECT: Path = PROJECT
SOLIDCRAFT_BESIDE: Path = (
    PROJECT.parent / "solidcraft" / "solidcraft-linux-x86_64.AppImage"
)
WORK: Path = Path.home() / ".cache" / "scraftcnc" / "show"
SOLIDCRAFT_DATA: Path = Path.home() / ".local" / "share" / "solidcraft"

# The `distrobox` box that LinuxCNC is in.
BOX: str = "lcnc"

# The usual ports, of SolidCraft and of the HMI's commands.
SOLIDCRAFT_PORT: int = 8080
HMI_PORT: int = 5007

# The HMI's speed to start with: a whole run in about 75 seconds.
SPEED: float = 10.0

# How long each thing may take to come up, and to close (seconds).
BOX_SECONDS: float = 300.0
INSTALL_SECONDS: float = 300.0
START_SECONDS: float = 120.0
CLOSE_SECONDS: float = 15.0

# How often to look at what is running (seconds).
POLL: float = 0.25

# How long a headless run may show no change (seconds): while it cuts,
# and while the setup is drawn (tooling not in the cache is built).
STALL_SECONDS: float = 60.0
DRAW_SECONDS: float = 400.0

# How much of a log to show after a failure (lines).
LOG_LINES: int = 15


# Class `DemoShowFailed`:
class DemoShowFailed(Exception):
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
    * `DemoShowFailed`: If there is none.
    """
    if named:
        found: str | None = shutil.which(named)
    else:
        found = shutil.which("solidcraft")
        if found is None and SOLIDCRAFT_BESIDE.is_file():
            found = str(SOLIDCRAFT_BESIDE)
    if found is None:
        raise DemoShowFailed(
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
    * `DemoShowFailed`: If something is missing, or a port is in use.
    """
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise DemoShowFailed("There is no display to show this on.")
    if not (SERVER_PROJECT / "scraftcnc" / "lcnc").is_dir():
        raise DemoShowFailed(f"{SERVER_PROJECT} is not there.")
    if shutil.which("podman") is None:
        raise DemoShowFailed("`podman` is not installed.")
    for name, port in ports.items():
        if port_open(port):
            raise DemoShowFailed(
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


# A bounding box: the low corner, then the high one (millimeters).
Box = tuple[tuple[float, float, float], tuple[float, float, float]]


# Function `wire_box()`:
def wire_box(sketch: dict[str, Any]) -> Box | None:
    """Return the bounding box of a sketch's wires (from `sketch.inspect`).

    Each straight wire's ends bound it; an arc's ends do not quite,
    which is close enough for a report.

    Arguments:
    * `sketch` (`dict[str, Any]`): The sketch, as inspected.

    Returns:
    * (`Box | None`): The box, or `None` with no wires.
    """
    points: list[list[float]] = [
        point
        for wire in sketch.get("wires", [])
        for point in (wire["start"], wire["end"])
    ]
    if not points:
        return None
    low: tuple[float, float, float] = (
        min(point[0] for point in points),
        min(point[1] for point in points),
        min(point[2] for point in points),
    )
    high: tuple[float, float, float] = (
        max(point[0] for point in points),
        max(point[1] for point in points),
        max(point[2] for point in points),
    )
    return low, high


# Function `edge_box()`:
def edge_box(edges: list[dict[str, Any]]) -> Box | None:
    """Return the bounding box of a body's edges (from `model.edges`).

    `document.inspect`'s `bbox` is in the body's own component frame,
    so a body inserted from a STEP file with a placement matrix shows
    unplaced there; `model.edges` gives world points.  Each edge's
    ends and middle bound it (an arc's not quite).

    Arguments:
    * `edges` (`list[dict[str, Any]]`): The edges.

    Returns:
    * (`Box | None`): The box, or `None` with no edges.
    """
    return wire_box(
        {
            "wires": [
                {"start": edge["start"], "end": edge[key]}
                for edge in edges
                for key in ("mid", "end")
            ]
        }
    )


# Function `box_text()`:
def box_text(box: Box | None) -> str:
    """Return a bounding box as text, in millimeters.

    Arguments:
    * `box` (`Box | None`): The box, or `None`.

    Returns:
    * (`str`): `[x y z] .. [x y z]`, or `empty`.
    """
    if box is None:
        return "empty"
    low: str = " ".join(f"{value:.2f}" for value in box[0])
    high: str = " ".join(f"{value:.2f}" for value in box[1])
    return f"[{low}] .. [{high}]"


# Function `union()`:
def union(boxes: list[Box]) -> Box | None:
    """Return the box around several boxes.

    Arguments:
    * `boxes` (`list[Box]`): The boxes.

    Returns:
    * (`Box | None`): The box around them, or `None` with none.
    """
    if not boxes:
        return None
    low: tuple[float, float, float] = (
        min(box[0][0] for box in boxes),
        min(box[0][1] for box in boxes),
        min(box[0][2] for box in boxes),
    )
    high: tuple[float, float, float] = (
        max(box[1][0] for box in boxes),
        max(box[1][1] for box in boxes),
        max(box[1][2] for box in boxes),
    )
    return low, high


# Function `session_report()`:
def session_report(
    bodies: list[dict[str, Any]], sketches: list[dict[str, Any]]
) -> list[str]:
    """Return the report of what a session holds.

    Every body with its bounding box, every sketch with its wires and
    their bounding box, then how the tool path (the watcher's sketches
    named `T.. path`) lines up with the plate in X and Y.

    Arguments:
    * `bodies` (`list[dict[str, Any]]`): `document.inspect`'s bodies.
    * `sketches` (`list[dict[str, Any]]`): Each sketch, from
      `sketch.inspect`.

    Returns:
    * (`list[str]`): The lines.
    """
    lines: list[str] = [f"{len(bodies)} bodies:"]
    plate: Box | None = None
    body: dict[str, Any]
    for body in bodies:
        bbox: dict[str, list[float]] = body["bbox"]
        box: Box = (
            (bbox["min"][0], bbox["min"][1], bbox["min"][2]),
            (bbox["max"][0], bbox["max"][1], bbox["max"][2]),
        )
        if body["name"] == "Plate":
            plate = box
        lines.append(f"  {body['name']}: {box_text(box)}")

    # The sketches, and the tool path's box.
    lines.append(f"{len(sketches)} sketches:")
    path: list[Box] = []
    sketch: dict[str, Any]
    for sketch in sketches:
        found: Box | None = wire_box(sketch)
        wires: int = len(sketch.get("wires", []))
        lines.append(f"  {sketch['name']}: {wires} wires, {box_text(found)}")
        if found is not None and str(sketch["name"]).endswith(" path"):
            path.append(found)

    # How the path's middle sits from the plate's middle (#78).
    whole: Box | None = union(path)
    lines.append(f"Plate: {box_text(plate)}")
    lines.append(f"Tool path: {box_text(whole)}")
    if plate is not None and whole is not None:
        offset: list[float] = [
            (whole[0][axis] + whole[1][axis] - plate[0][axis] - plate[1][axis])
            / 2.0
            for axis in range(2)
        ]
        lines.append(
            f"Path middle - plate middle: X {offset[0]:.2f} mm, "
            f"Y {offset[1]:.2f} mm"
        )
    return lines


# Class `DemoShow`:
# One method per step of the show, GUI and headless, so many of them.
@dataclass(slots=True)
class DemoShow:  # pylint: disable=too-many-public-methods
    """The programs of one show, and what it takes to close them.

    Attributes:
    * `options` (`argparse.Namespace`): The command line.
    * `logs` (`dict[str, Path]`): Each program's output, by name.
    * `program` (`Path`): The G-code file.
    * `running` (`dict[str, subprocess.Popen[bytes]]`): What is running,
      by name, in the order it started.

    Constructor:
    * `DemoShow(options)`
    """

    # Constructor arguments:
    options: argparse.Namespace = field(init=True)

    # Remaining attributes (alphabetized):
    logs: dict[str, Path] = field(init=False, default_factory=dict)
    program: Path = field(init=False, default=WORK / "demo.ngc")
    running: dict[str, subprocess.Popen[bytes]] = field(
        init=False, default_factory=dict
    )

    # Method `DemoShow.log_end()`:
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

    # Method `DemoShow.start()`:
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

    # Method `DemoShow.check_alive()`:
    def check_alive(self, name: str) -> None:
        """Check that a program has not stopped while coming up.

        Arguments:
        * `name` (`str`): The program.

        Raises:
        * `DemoShowFailed`: If it has stopped.
        """
        status: int | None = self.running[name].poll()
        if status is not None:
            raise DemoShowFailed(
                f"{name} stopped, with status {status}.\n{self.log_end(name)}"
            )

    # Method `DemoShow.wait_for_port()`:
    def wait_for_port(self, name: str, port: int, hint: str = "") -> None:
        """Wait until a program answers on its port.

        Arguments:
        * `name` (`str`): The program.
        * `port` (`int`): The port.
        * `hint` (`str`): What to say if it is slow.

        Raises:
        * `DemoShowFailed`: If it stops, or takes too long.
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
                raise DemoShowFailed(
                    f"{name} did not open port {port}.\n{self.log_end(name)}"
                )
            time.sleep(POLL)

    # Method `DemoShow.start_box()`:
    def start_box(self) -> None:
        """Make sure that the box is running, as after a reboot it is not.

        Raises:
        * `DemoShowFailed`: If it will not start.
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
            raise DemoShowFailed(f"The {BOX} box did not start.") from error
        if done.returncode != 0:
            raise DemoShowFailed(
                f"The {BOX} box did not start.\n{done.stdout}{done.stderr}"
            )

    # Method `DemoShow.update_linuxcnc()`:
    def update_linuxcnc(self) -> None:
        """Run the installer, which checks all and updates the bridge.

        Raises:
        * `DemoShowFailed`: If it fails.
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
            raise DemoShowFailed(
                "The LinuxCNC installation is not right; run "
                "`python3 -m scraftcnc.lcnc.install_linuxcnc` in "
                f"{SERVER_PROJECT}.\n{self.log_end('install_linuxcnc')}"
            )

    # Method `DemoShow.start_solidcraft()`:
    def start_solidcraft(self) -> None:
        """Start SolidCraft, clearing only what a dead one left behind.

        Raises:
        * `DemoShowFailed`: If it does not come up.
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
                raise DemoShowFailed(f"SolidCraft never wrote {token}.")
            time.sleep(POLL)

    # Method `DemoShow.write_program()`:
    def write_program(self) -> None:
        """Write the program, with its setup as `(SCC: ...)` lines.

        Raises:
        * `DemoShowFailed`: If it fails.
        """
        say("Writing the program.")
        self.logs["program"] = WORK / "program.log"
        with (
            self.program.open("wb") as program,
            self.logs["program"].open("wb") as log,
        ):
            done = subprocess.run(
                [sys.executable, "-m", "scraftcnc.demo"],
                cwd=PROJECT,
                stdin=subprocess.DEVNULL,
                stdout=program,
                stderr=log,
                check=False,
            )
        if done.returncode != 0:
            raise DemoShowFailed(
                f"Writing the program failed.\n{self.log_end('program')}"
            )

    # Method `DemoShow.start_watcher()`:
    def start_watcher(self) -> None:
        """Start the watcher, and wait until the tools are modeled.

        Raises:
        * `DemoShowFailed`: If it stops, or takes too long.
        """
        say("Modeling the tools and their paths in SolidCraft.")
        self.start(
            "watcher",
            ["podman", "exec", "-u", getpass.getuser(), "-w", str(PROJECT),
             BOX, "python3", "-u", "-m", "scraftcnc.lcnc.sim_linuxcnc",
             "--watch",
             str(self.program),
             "--solidcraft", str(self.options.solidcraft_port)],
        )  # fmt: skip
        log: Path = self.logs["watcher"]
        end: float = time.monotonic() + START_SECONDS
        while b"watching" not in log.read_bytes():
            self.check_alive("watcher")
            if time.monotonic() > end:
                raise DemoShowFailed(
                    "The watcher never got ready.\n" + self.log_end("watcher")
                )
            time.sleep(POLL)

    # Method `DemoShow.start_hmi()`:
    def start_hmi(self) -> None:
        """Start the HMI, stopped, with the program open.

        The HMI draws the program's setup in SolidCraft.

        Raises:
        * `DemoShowFailed`: If it does not come up.
        """
        port: int = self.options.port
        say("Starting the HMI.")
        self.start(
            "hmi",
            [sys.executable, "-m", "scraftcnc.hmi.lcnc_hmi",
             "--port", str(port),
             "--solidcraft", str(self.options.solidcraft_port),
             *(["--headless"] if self.options.headless else []),
             str(self.program)],
        )  # fmt: skip
        self.wait_for_port("hmi", port)
        with socket.create_connection(("127.0.0.1", port), 5.0) as hmi:
            hmi.sendall(f"speed {self.options.speed}\n".encode())
            hmi.makefile().readline()

    # Method `DemoShow.bring_up()`:
    def bring_up(self) -> None:
        """Bring up the whole chain, in order.

        The HMI comes last, so that Start can not be pressed until
        SolidCraft can show the run.

        Raises:
        * `DemoShowFailed`: If any part of it fails.
        """
        check_ready(
            {
                "LinuxCNC": LINUXCNC_PORT,
                "SolidCraft": self.options.solidcraft_port,
                "the HMI": self.options.port,
            }
        )
        if not self.options.headless:
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
        if self.options.headless:
            self.start_headless_solidcraft()
        else:
            self.start_solidcraft()
        self.write_program()
        self.start_watcher()
        self.start_hmi()

    # Method `DemoShow.start_headless_solidcraft()`:
    def start_headless_solidcraft(self) -> None:
        """Serve a headless SolidCraft session on the control port.

        Raises:
        * `DemoShowFailed`: If it does not come up.
        """
        port: int = self.options.solidcraft_port
        say("Starting a headless SolidCraft.")
        self.start(
            "solidcraft_headless",
            [sys.executable, "-u", "-m", "scraftcnc.pybind.headless_server",
             str(port)],
        )  # fmt: skip
        self.wait_for_port("solidcraft_headless", port)

    # Method `DemoShow.ask()`:
    def ask(self, line: str) -> str:
        """Send one line to the HMI's port, and return its answer.

        Arguments:
        * `line` (`str`): The command.

        Returns:
        * (`str`): The answer.
        """
        address: tuple[str, int] = ("127.0.0.1", self.options.port)
        with socket.create_connection(address, 30.0) as hmi:
            hmi.sendall(f"{line}\n".encode())
            return hmi.makefile().readline().strip()

    # Method `DemoShow.watch()`:
    def watch(
        self,
        what: str,
        done: Callable[[dict[str, str]], bool],
        stall: float = STALL_SECONDS,
    ) -> None:
        """Poll the HMI until something is done, printing messages.

        Arguments:
        * `what` (`str`): What is waited for, for the messages.
        * `done` (`Callable[[dict[str, str]], bool]`): Given the
          HMI's status words and its `message` and `drawing`,
          whether it is done.
        * `stall` (`float`): How long nothing may change (seconds).

        Raises:
        * `DemoShowFailed`: If nothing changes for `stall` seconds.
        """
        message: str = ""
        last: str = ""
        moved: float = time.monotonic()
        while True:
            for name in self.running:
                self.check_alive(name)
            shown: dict[str, Any] = json.loads(self.ask("show"))
            words: dict[str, str] = dict(
                word.split("=", 1)
                for word in self.ask("status").split()
                if "=" in word
            )
            words["message"] = str(shown["message"])
            words["drawing"] = str(shown["drawing"])
            if words["message"] and words["message"] != message:
                say(f"HMI: {words['message']}")
            message = words["message"]
            if done(words):
                return
            now: str = json.dumps(words, sort_keys=True)
            if now != last:
                last, moved = now, time.monotonic()
            elif time.monotonic() - moved > stall:
                raise DemoShowFailed(f"Stalled waiting for {what}: {now}")
            time.sleep(POLL)

    # Method `DemoShow.report()`:
    def report(self) -> None:
        """Print every body and sketch in the headless session."""
        with connect(str(self.options.solidcraft_port)) as transport:
            solidcraft: PyBind = PyBind(transport)
            document: Any = solidcraft.document.inspect(measure=True)

            # World boxes, from each body's edges (see `edge_box()`).
            body: dict[str, Any]
            for body in document["bodies"]:
                edges: Any = solidcraft.model.edges(body=body["name"])
                box: Box | None = edge_box(edges["edges"])
                if box is not None:
                    body["bbox"] = {"min": box[0], "max": box[1]}
            sketches: list[dict[str, Any]] = [
                cast(dict[str, Any], solidcraft.sketch.inspect(sketch=key))
                for key in (sketch["id"] for sketch in document["sketches"])
            ]
        line: str
        for line in session_report(document["bodies"], sketches):
            say(line)

    # Method `DemoShow.step_through()`:
    def step_through(self) -> None:
        """Press Next Step through every setup item, and once more.

        Raises:
        * `DemoShowFailed`: If the HMI refuses, or it stalls.
        """
        count: int = -1
        while count != 0:
            answer: str = self.ask("press Next Step")
            if answer != "ok":
                raise DemoShowFailed(f"Next Step: {answer}")
            time.sleep(0.5)
            self.watch(
                "a step", lambda words: words["drawing"] == "False", 120.0
            )
            shown: dict[str, Any] = json.loads(self.ask("show"))
            count = int(shown["setup_step"])
            say(f"Step shown: {shown['message']}")

    # Method `DemoShow.set_origin()`:
    def set_origin(self, name: str) -> None:
        """Press Set Origin, pick a named origin, and say what it did.

        Arguments:
        * `name` (`str`): The origin the tool tip is taken to be at.

        Raises:
        * `DemoShowFailed`: If the HMI refuses, or it stalls.
        """
        # Move the tool tip there first, as an operator would jog it.
        shown: dict[str, Any] = json.loads(self.ask("show"))
        if name not in shown["origins"]:
            raise DemoShowFailed(f"No origin {name!r}: {shown['origins']}")
        x, y, z = shown["origins"][name]
        move: str
        for move in (f"G21 G0 X{x:.3f} Y{y:.3f}", f"G0 Z{z:.3f}"):
            self.ask(f"type {move}")
            self.ask("press Execute")
            self.watch(move, lambda words: words.get("state") == "idle")
        say(f"Before Set Origin: {self.ask('status')}")
        self.ask(f"answer {name}")
        self.ask("answer yes")
        answer: str = self.ask("press Set Origin")
        if answer != "ok":
            raise DemoShowFailed(f"Set Origin: {answer}")
        self.watch("Set Origin", lambda words: words.get("state") == "idle")
        mdi: list[str] = [
            line
            for line in self.ask("log").removeprefix("log: ").split(" | ")
            if "G10" in line
        ]
        say(f"Set Origin ran: {mdi[-1] if mdi else 'nothing'}")
        say(f"After Set Origin: {self.ask('status')}")

    # Method `DemoShow.drive()`:
    def drive(self) -> None:
        """Run the demo through the HMI's port, then press Quit.

        Raises:
        * `DemoShowFailed`: If it stalls, or a program stops.
        """
        begun: float = time.monotonic()
        say("Waiting for the setup to be drawn.")
        time.sleep(1.0)
        self.watch(
            "the setup",
            lambda words: words["drawing"] == "False",
            DRAW_SECONDS,
        )
        say(f"Setup drawn after {time.monotonic() - begun:.0f} s.")
        if self.options.steps:
            self.step_through()
        if self.options.keep_outs:
            say(f"Keep-outs: {self.ask('press Keep-outs')}")
            time.sleep(0.5)
            self.watch(
                "keep-outs", lambda words: words["drawing"] == "False", 120.0
            )
            say(f"HMI: {json.loads(self.ask('show'))['message']}")
        if self.options.origin:
            self.set_origin(self.options.origin)
        say("Pressing Start.")
        self.ask("press Start")
        self.watch("the run", lambda words: words.get("state") != "idle")
        self.watch("the end", lambda words: words.get("state") == "idle")
        say(f"Program ended after {time.monotonic() - begun:.0f} s.")
        self.report()
        say("Pressing Quit.")
        self.ask("press Quit")
        self.running["hmi"].wait(timeout=CLOSE_SECONDS)
        say(f"Total {time.monotonic() - begun:.0f} s.")

    # Method `DemoShow.wait_until_closed()`:
    def wait_until_closed(self) -> None:
        """Wait until any one of the programs stops.

        A program that closes with status 0 was closed by the person
        showing this, so only another status is reported.
        """
        say("Ready.  Press Start in the HMI.")
        say("Press Quit in the HMI to end the show.")
        while True:
            for name, program in self.running.items():
                status: int | None = program.poll()
                if status is not None:
                    if status != 0:
                        say(f"{name} stopped, with status {status}.")
                        print(self.log_end(name), flush=True)
                    return
            time.sleep(POLL)

    # Method `DemoShow.close_one()`:
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

    # Method `DemoShow.close_watcher()`:
    def close_watcher(self) -> None:
        """Stop the watcher, which runs in the box.

        A signal to `podman exec` may not reach it, but the box shares
        this computer's processes, so it can be signaled from here.
        """
        if "watcher" in self.running:
            subprocess.run(
                ["pkill", "-INT", "-f",
                 f"scraftcnc.lcnc.sim_linuxcnc --watch {self.program}"],
                check=False,
            )  # fmt: skip
            self.close_one("watcher")

    # Method `DemoShow.close_linuxcnc()`:
    def close_linuxcnc(self) -> None:
        """Ask LinuxCNC to shut down, or else signal it."""
        program: subprocess.Popen[bytes] | None = self.running.get("linuxcnc")
        if program is None or program.poll() is not None:
            return
        try:
            with BridgeClient(timeout=10.0) as lcnc:
                lcnc.call("shutdown")
            program.wait(timeout=60.0)
        except (OSError, BridgeError, subprocess.TimeoutExpired):
            self.close_one("linuxcnc")

    # Method `DemoShow.remove_leftovers()`:
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

    # Method `DemoShow.close()`:
    def close(self) -> None:
        """Close everything, the last started first."""
        say("Closing.")
        self.close_one("hmi")
        self.close_watcher()
        self.close_linuxcnc()
        self.close_one("solidcraft")
        self.close_one("solidcraft_headless")
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
        description="Bring up SolidCraft, LinuxCNC and the HMI, connected."
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
        "--port",
        type=int,
        default=HMI_PORT,
        help="the HMI's command port (default: %(default)s)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=SPEED,
        help="the HMI's speed to start with (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="no windows: run the demo through the HMI's port, and report",
    )
    parser.add_argument(
        "--origin",
        default="",
        help="with --headless: the setup origin to pick at Set Origin "
        "before Start (e.g. 'stock: top left outer')",
    )
    parser.add_argument(
        "--steps",
        action="store_true",
        help="with --headless: press Next Step through the setup first",
    )
    parser.add_argument(
        "--keep-outs",
        action="store_true",
        help="with --headless: show the setup's keep-outs",
    )
    show: DemoShow = DemoShow(parser.parse_args())
    signal.signal(signal.SIGTERM, interrupted)
    status: int = 0
    try:
        show.bring_up()
        if show.options.headless:
            show.drive()
        else:
            show.wait_until_closed()
    except DemoShowFailed as error:
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
