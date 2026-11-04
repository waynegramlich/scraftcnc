#!/usr/bin/env python3
"""A minimal LinuxCNC control panel, in place of AXIS (`T.mlcp~3.4`).

A small `tkinter` window that drives the LinuxCNC back end through its
Python API: the G-code already run, one line of G-code to run as MDI
(Execute, while stopped; green when it reads as RS-274, red when
not), the G-code coming next, a jog line (Set Origin, Home to the
work origin, six jog buttons and the jog step: 1 to .0001 in), a run
line (-Tool and +Tool, which move the line Start runs from to the
previous or next tool change; Start, Pause and Reset), a speed slider
(the feed override) with Open, and the work
position and tool in the spindle.  The LinuxCNC calls are kept in
`SCPanelMachine`, a client (through `scraftcnc.lcnc.lcnc_client`) of
`serve_linuxcnc` from `scraftcnc/lcnc/`, which runs LinuxCNC in its
`lcnc` box, or in WSL on Windows.  So this runs outside the box, and
needs only `tkinter`.  Closing it leaves LinuxCNC running, for another
panel.  When it starts, the machine is taken out of E-stop, turned on
and homed if it needs to be (G54 is then set to `ORIGIN`), it is sent
the shop's tool table, and the INI file's `MAX_FEED_OVERRIDE` limits
the slider:

```
python3 -m scraftcnc.lcnc.serve_linuxcnc &
python3 -m scraftcnc.hmi.lcnc_panel demo.ngc
# The window alone:
python3 -m scraftcnc.hmi.lcnc_panel --dry-run demo.ngc
# No window, for tests:
python3 -m scraftcnc.hmi.lcnc_panel --headless --port 5007
```

With `--headless`, the panel is built from `lcnc_headless.py` in place
of `tkinter`, so it needs no display and no `tkinter`, and otherwise
runs the same code, with its buttons pressed through the command port.

A program is opened from the command line, with Open, or through the
command port
(`--port PORT`, on 127.0.0.1), which takes one line per connection and
answers one line: `ping`, `open FILE`, `start` (or `run`), `pause`,
`reset` (or `stop`), `tool+`, `tool-` (the start line to the next or
previous tool change), `speed X`, `press LABEL` (presses a button,
as a person would; refused when it is greyed out), `type LINE` (into
the MDI line), `show` (all that the window shows, as JSON), `answer
VALUE` (with `--headless`, the answer to the next question: `yes` or a
file), `status`, `messages` (every message
LinuxCNC has sent, as `messages: A | B`) or `quit`:

```
echo "open demo.ngc" | nc -q 1 127.0.0.1 5007
```
"""

# Half of the module is docstrings, which the type hints and the
# argument lists make long, so it passes 1000 lines.
# pylint: disable=too-many-lines

import argparse
import functools
import json
import math
import re
import signal
import socket
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from .. import shops
from ..lcnc.lcnc_client import PORT, SCBridgeError, SCClient, constant
from . import lcnc_headless

# A computer with no `tkinter` can still run `--headless`.
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    # pylint: disable=reimported,ungrouped-imports
    from . import lcnc_headless as filedialog  # type: ignore[no-redef]
    from . import lcnc_headless as messagebox  # type: ignore[no-redef]
    from . import lcnc_headless as tk  # type: ignore[no-redef]
    from . import lcnc_headless as ttk  # type: ignore[no-redef]

# The protocol of `serve_linuxcnc` that this needs, at least.
PROTOCOL: int = 2

# How long a new LinuxCNC gets to turn on and to home (seconds).
START_SECONDS: float = 60.0

# The machine coordinates (inches) of the program's zero, on a new
# LinuxCNC, as `sim_linuxcnc.ORIGIN` (which can not be imported, as it
# needs the `linuxcnc` module).
ORIGIN: tuple[float, float, float] = (4.0, 3.0, -6.0)

# The steps a jog button can move (inches), the one chosen at start,
# and how fast a jog moves (inches per second).
JOG_STEPS: tuple[str, ...] = ("1", ".1", ".01", ".001", ".0001")
JOG_STEP: str = ".0001"
JOG_SPEED: float = 1.0

# The background of the jog step chosen.
STEP_CHOSEN: str = "#a8c8f0"

# How close to the work origin counts as there (inches).
AT_ORIGIN: float = 0.00005

# How often the panel polls LinuxCNC and the command port
# (milliseconds).
POLL_MS: int = 100

# The speed slider's range (feed override, on a logarithmic scale; 0
# is left out, since Pause stops), its top limited by the INI file's
# `MAX_FEED_OVERRIDE`.
MIN_SPEED: float = 0.01
MAX_SPEED: float = 10.0

# How many lines the executed and coming windows show.
SHOWN: int = 6

# A tool change line (`M6`, outside a comment).
TOOL_CHANGE: re.Pattern[str] = re.compile(r"\bM0*6\b", re.IGNORECASE)

# Comments: in parentheses, or from `;` to the end of the line.
COMMENT: re.Pattern[str] = re.compile(r"\([^)]*\)|;.*")

# A line of RS-274 words, simply: letters, each followed by a number.
WORDS: re.Pattern[str] = re.compile(
    r"\s*([A-Za-z]\s*[-+]?(\d+\.?\d*|\.\d+)\s*)+"
)

# The shop and machine whose tools the Tools window lists, and the
# material it starts with.
SHOP_FILE: Path = (
    Path(__file__).resolve().parents[2] / "examples/shop/home_shop.toml"
)
SHOP_MACHINE: str = "Shop mill"
MATERIAL: str = "6061 aluminum"

# The classes of the widgets that `press` can press.
BUTTONS: tuple[str, ...] = ("TButton", "Radiobutton")

# The MDI line's backgrounds: empty, RS-274, and not.
BLANK: str = "white"
GOOD: str = "#d8f5d0"
BAD: str = "#f8d0d0"


# Function `use_headless()`:
def use_headless() -> None:
    """Build every window from now on with `lcnc_headless`."""
    # The window code stays the same, by using the same names.
    # pylint: disable-next=global-statement
    global tk, ttk, filedialog, messagebox
    tk = ttk = filedialog = messagebox = lcnc_headless


# Function `material_names()`:
def material_names(shop: dict[str, object]) -> list[str]:
    """Return the names of a shop's materials.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.

    Returns:
    * (`list[str]`): The names, in the shop's order.
    """
    materials: dict[str, Any] = cast(dict[str, Any], shop.get("materials", {}))
    return [str(entry["name"]) for entry in materials.get("materials", [])]


# Function `tool_speeds()`:
def tool_speeds(shop: dict[str, object], machine: str, material: str) -> str:
    """Return a table of a machine's tools' speeds and feeds.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.
    * `machine` (`str`): The machine's name.
    * `material` (`str`): The material being cut.

    Returns:
    * (`str`):
      One line per loaded tool (T number, RPM, feed, plunge, name),
      or the problem, if they can not be worked out.
    """
    # Work them out, as the G-code would.
    try:
        tools = shops.cnc_machine(shop, machine, material).tools
    except ValueError as error:
        return str(error)
    lines: list[str] = [
        f"Feeds in in/min, cutting {material}:",
        "  T    RPM  Feed  Plunge  Tool",
    ]
    lines.extend(
        f"{tool.number:3d} {tool.rpm:6.0f} {tool.feed:5.1f} "
        f"{tool.plunge:7.1f}  {tool.name}"
        for tool in tools
    )
    return "\n".join(lines)


# Function `line_kind()`:
def line_kind(line: str) -> str:
    """Return whether a line reads as RS-274 words, with comments left out.

    Arguments:
    * `line` (`str`): The line.

    Returns:
    * (`str`): `empty` (nothing but comments or spaces), `good` or
      `bad`.
    """
    words: str = COMMENT.sub("", line).strip()
    if not words:
        return "empty"
    return "good" if WORDS.fullmatch(words) else "bad"


# Function `tool_changes()`:
def tool_changes(lines: list[str]) -> list[int]:
    """Return the lines that change the tool.

    Arguments:
    * `lines` (`list[str]`): The program's lines.

    Returns:
    * (`list[int]`): Their numbers, counted from 1, in order.
    """
    return [
        number
        for number, line in enumerate(lines, 1)
        if TOOL_CHANGE.search(COMMENT.sub("", line))
    ]


# Class `SCStatus`:
@dataclass(slots=True)
class SCStatus:
    """What the panel shows of the machine, from one poll.

    Attributes:
    * `file` (`str`): The open program ("" for none).
    * `line` (`int`): The line being run (counted from 1; 0 for none).
    * `position` (`tuple[float, float, float]`): X, Y and Z, in work
      coordinates (inches).
    * `tool` (`int`): The T number in the spindle (0 for none).
    * `messages` (`list[str]`): LinuxCNC's new error messages.
    * `state` (`str`): `idle`, `running` or `paused` (`""` for a dry
      run, where the panel's own idea of it stands).

    Constructor:
    * `SCStatus(file, line, position, tool, messages, state)`
    """

    # Constructor arguments:
    file: str = field(init=True)
    line: int = field(init=True)
    position: tuple[float, float, float] = field(init=True)
    tool: int = field(init=True)
    messages: list[str] = field(init=True)
    state: str = field(init=True)


# Class `SCPanelMachine`:
class SCPanelMachine:
    """The LinuxCNC back end, as the panel sees it.

    It is a client of `scraftcnc.lcnc`'s `serve_linuxcnc`, which runs
    LinuxCNC wherever that is installed.  With `dry_run`, nothing is
    sent anywhere and every call only records what it would have done,
    so the window can be built and tested without LinuxCNC.

    Nothing here waits for a move, so the window stays alive and Reset
    works during one: `status()` starts the next line of a run of MDI
    lines (such as Home's) when the one before it has finished.

    Attributes:
    * `constants` (`dict[str, Any]`): The `linuxcnc` module's constants.
    * `dry_run` (`bool`): True when no LinuxCNC is used.
    * `file` (`str`): The program opened: where it is on the server,
      or its own path for a dry run.
    * `lcnc` (`SCClient | None`): The connection, or `None`.
    * `log` (`list[str]`): What was asked of the machine, in order.
    * `mdi_lines` (`list[str]`): The MDI lines waiting to be run.
    * `messages` (`list[str]`): Every message LinuxCNC has sent.
    """

    # Method `SCPanelMachine.__init__()`:
    def __init__(self, dry_run: bool, port: int = PORT) -> None:
        """Connect to `serve_linuxcnc`, unless `dry_run`.

        Arguments:
        * `dry_run` (`bool`):
          True to use no LinuxCNC at all.
        * `port` (`int`):
          The port that `serve_linuxcnc` is on.

        Raises:
        * `RuntimeError`: If it does not answer, or is out of date.
        """
        self.constants: dict[str, Any] = {}
        self.dry_run: bool = dry_run
        self.file: str = ""
        self.lcnc: SCClient | None = None
        self.log: list[str] = []
        self.mdi_lines: list[str] = []
        self.messages: list[str] = []
        if dry_run:
            return

        # Connect, and check that it knows the calls used here.
        try:
            self.lcnc = SCClient(port=port)
        except OSError as error:
            raise RuntimeError(
                f"No LinuxCNC on port {port} ({error}); "
                "start it with serve_linuxcnc."
            ) from error
        protocol: int = self.lcnc.call("ping")["protocol"]
        if protocol < PROTOCOL:
            raise RuntimeError(
                f"serve_linuxcnc speaks protocol {protocol}, not {PROTOCOL}; "
                "stop it, run install_linuxcnc, and start it again."
            )
        self.constants = self.lcnc.call("constants")

    # Method `SCPanelMachine._mode()`:
    def _mode(self, name: str) -> None:
        """Switch LinuxCNC to a mode (`MODE_AUTO`, `MODE_MDI`, ...).

        Arguments:
        * `name` (`str`):
          The name of the mode constant in `linuxcnc`.
        """
        if self.lcnc is not None:
            self.lcnc.call("command.mode", constant(name))
            self.lcnc.call("command.wait_complete")

    # Method `SCPanelMachine._wait_for()`:
    def _wait_for(self, what: str, test: Callable[[], bool]) -> None:
        """Wait, as LinuxCNC starts up, until something is true.

        Arguments:
        * `what` (`str`): What is waited for, for the error message.
        * `test` (`Callable[[], bool]`): Tells whether it is true yet.

        Raises:
        * `TimeoutError`: If it is not true in `START_SECONDS`.
        """
        end: float = time.monotonic() + START_SECONDS
        while not test():
            if time.monotonic() > end:
                raise TimeoutError(f"Timed out waiting for {what}.")
            time.sleep(POLL_MS / 1000.0)

    # Method `SCPanelMachine._home()`:
    def _home(self) -> bool:
        """Take it out of E-stop, turn it on, and home every joint.

        A machine already on and homed is left alone, since it may be
        running a program for a panel that has since closed.

        Returns:
        * (`bool`): True if it had to be homed, as a new LinuxCNC does.
        """
        lcnc: SCClient = cast(SCClient, self.lcnc)
        state_on: int = self.constants["STATE_ON"]

        def homed() -> bool:
            stat: dict[str, Any] = lcnc.stat("homed", "joints")
            return all(stat["homed"][: stat["joints"]])

        # Out of E-stop, and on.
        if lcnc.stat("task_state")["task_state"] != state_on:
            lcnc.call("command.state", constant("STATE_ESTOP_RESET"))
            lcnc.call("command.state", constant("STATE_ON"))
            self._wait_for(
                "the machine to turn on",
                lambda: lcnc.stat("task_state")["task_state"] == state_on,
            )

        # Home in joint mode, in the configuration's `HOME_SEQUENCE`.
        if homed():
            return False
        self._mode("MODE_MANUAL")
        lcnc.call("command.teleop_enable", False)
        lcnc.call("command.wait_complete")
        lcnc.call("command.home", -1)
        self._wait_for("homing", homed)
        return True

    # Method `SCPanelMachine.start()`:
    def start(self) -> None:
        """Get LinuxCNC ready, keeping what it has if already running.

        It is turned on and homed if it needs to be, and then has
        just started, so G54 is set to `ORIGIN`, whatever LinuxCNC kept
        from its last run or another client set.  `serve_linuxcnc`
        outlives the panel, so a panel opened later keeps the origin.
        The shop's tool table is sent unless a program is running.

        Raises:
        * `ValueError`: If the shop can not give a tool table.
        """
        self.log.append("start")
        if self.lcnc is None:
            return
        started: bool = self._home()
        interp_state: int = self.lcnc.stat("interp_state")["interp_state"]
        if interp_state != self.constants["INTERP_IDLE"]:
            return

        # The tool table, from the shop.
        self.lcnc.call(
            "tool_table.write",
            shops.tool_table_text(
                shops.read(SHOP_FILE), SHOP_MACHINE, MATERIAL
            ),
        )
        self.lcnc.call("command.load_tool_table")
        self.lcnc.call("command.wait_complete")

        # The origin.  `G20` first: otherwise the numbers may be read
        # as millimeters.
        if started:
            x, y, z = ORIGIN
            self._mode("MODE_MDI")
            self.lcnc.call("command.mdi", f"G20 G10 L2 P1 X{x} Y{y} Z{z}")
            self.lcnc.call("command.wait_complete")

    # Method `SCPanelMachine.max_speed()`:
    def max_speed(self) -> float:
        """Return the highest feed override the INI file allows.

        Returns:
        * (`float`): Its `[DISPLAY] MAX_FEED_OVERRIDE`, or
          `MAX_SPEED` when there is none.
        """
        if self.lcnc is None:
            return MAX_SPEED
        found: str | None = self.lcnc.call(
            "ini.find", "DISPLAY", "MAX_FEED_OVERRIDE"
        )
        return float(found) if found else MAX_SPEED

    # Method `SCPanelMachine.open()`:
    def open(self, path: str) -> None:
        """Send a program to LinuxCNC, ready to run from its start.

        Arguments:
        * `path` (`str`): The G-code file, here (a relative path is
          from the panel's directory).

        Raises:
        * `FileNotFoundError`: If there is no such file.
        """
        if not Path(path).is_file():
            raise FileNotFoundError(f"no file {path}")
        local: Path = Path(path).resolve()
        self.file = str(local)
        self.log.append(f"open {self.file}")
        if self.lcnc is not None:
            self._mode("MODE_AUTO")
            self.file = self.lcnc.call(
                "program.write", local.name, local.read_text(encoding="utf-8")
            )
            self.lcnc.call("command.program_open", self.file)
            self.lcnc.call("command.wait_complete")

    # Method `SCPanelMachine.program_lines()`:
    def program_lines(self, file: str) -> list[str]:
        """Return the lines of the program that LinuxCNC has open.

        Arguments:
        * `file` (`str`): Its file, from `status()`.

        Returns:
        * (`list[str]`): Its lines, or none if it can not be read.
        """
        try:
            text: str = (
                Path(file).read_text(encoding="utf-8")
                if self.lcnc is None
                else self.lcnc.call("program.read", file)
            )
        except (OSError, SCBridgeError):
            return []
        return text.splitlines()

    # Method `SCPanelMachine.run()`:
    def run(self, start: int) -> None:
        """Run the open program from a line.

        Arguments:
        * `start` (`int`): The line to start at (counted from 1, as
          `motion_line` is; 0 for the program's start).  The lines
          before it are read, not run, so their modes still hold.
        """
        self.log.append(f"run {start}")
        if self.lcnc is not None:
            self._mode("MODE_AUTO")
            self.lcnc.call("command.auto", constant("AUTO_RUN"), start)

    # Method `SCPanelMachine.pause()`:
    def pause(self) -> None:
        """Pause the running program."""
        self.log.append("pause")
        if self.lcnc is not None:
            self.lcnc.call("command.auto", constant("AUTO_PAUSE"))

    # Method `SCPanelMachine.resume()`:
    def resume(self) -> None:
        """Resume a paused program.

        It is in `MODE_AUTO` already; setting that again can end the
        program, with no message, so the mode is left alone.
        """
        self.log.append("resume")
        if self.lcnc is not None:
            self.lcnc.call("command.auto", constant("AUTO_RESUME"))

    # Method `SCPanelMachine.stop()`:
    def stop(self) -> None:
        """Stop at once (`command.abort()`), with any MDI lines waiting."""
        self.log.append("stop")
        self.mdi_lines.clear()
        if self.lcnc is not None:
            self.lcnc.call("command.abort")
            self.lcnc.call("command.wait_complete")

    # Method `SCPanelMachine.mdi()`:
    def mdi(self, *lines: str) -> None:
        """Start lines of G-code as manual (MDI) commands, one at a time.

        This returns as the first starts; `status()` starts the others.

        Arguments:
        * `lines` (`str`):
          The G-code lines.

        Raises:
        * `RuntimeError`: If LinuxCNC will not switch to MDI, as while
          a program runs or is paused (LinuxCNC 2.9 does not allow
          MDI then, and says nothing).
        """
        self.log.extend(f"mdi {line}" for line in lines)
        if self.lcnc is not None:
            self._mode("MODE_MDI")
            task_mode: int = self.lcnc.stat("task_mode")["task_mode"]
            if task_mode != self.constants["MODE_MDI"]:
                raise RuntimeError("Reset the program first")
            self.mdi_lines = list(lines[1:])
            self.lcnc.call("command.mdi", lines[0])

    # Method `SCPanelMachine.set_origin()`:
    def set_origin(self) -> None:
        """Make the current position the program's zero (G54)."""
        self.mdi("G10 L20 P1 X0 Y0 Z0")

    # Method `SCPanelMachine.jog()`:
    def jog(self, axis: int, direction: int, step: float) -> None:
        """Jog one axis by one step.

        Arguments:
        * `axis` (`int`):
          The axis: 0 for X, 1 for Y, 2 for Z.
        * `direction` (`int`):
          +1 or -1.
        * `step` (`float`):
          How far (inches).
        """
        self.log.append(f"jog {'XYZ'[axis]} {direction:+d}")
        if self.lcnc is not None:
            self._mode("MODE_MANUAL")
            self.lcnc.call("command.teleop_enable", True)
            self.lcnc.call(
                "command.jog",
                constant("JOG_INCREMENT"),
                False,
                axis,
                JOG_SPEED,
                direction * step,
            )

    # Method `SCPanelMachine.go_origin()`:
    def go_origin(self, z: float) -> None:
        """Rapid to the work origin, never moving sideways below Z0.

        Arguments:
        * `z` (`float`): The work Z now (inches).
        """
        self.mdi(f"G20 G90 G0 Z{max(z, 0.0):.4f}", "G0 X0 Y0", "G0 Z0")

    # Method `SCPanelMachine.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override.

        Arguments:
        * `speed` (`float`):
          The feed override (1.0 is the programmed feed).
        """
        self.log.append(f"speed {speed:.2f}")
        if self.lcnc is not None:
            self.lcnc.call("command.feedrate", speed)

    # Method `SCPanelMachine.top_z()`:
    def top_z(self) -> float:
        """Return the highest work Z the tool's tip can reach.

        Returns:
        * (`float`): Z's upper travel limit less the G5x, G92 and tool
          length offsets (inches).
        """
        stat: dict[str, Any] = cast(SCClient, self.lcnc).stat(
            "axis", "g5x_offset", "g92_offset", "tool_offset"
        )
        return float(
            stat["axis"][2]["max_position_limit"]
            - stat["g5x_offset"][2]
            - stat["g92_offset"][2]
            - stat["tool_offset"][2]
        )

    # Method `SCPanelMachine._read_messages()`:
    def _read_messages(self) -> list[str]:
        """Read LinuxCNC's new messages, and keep them.

        Returns:
        * (`list[str]`): The new messages.
        """
        lcnc: SCClient = cast(SCClient, self.lcnc)
        messages: list[str] = []
        error: Any = lcnc.call("error_channel.poll")
        while error:
            messages.append(str(error[1]))
            error = lcnc.call("error_channel.poll")

        # LinuxCNC's message for a move outside the travel says
        # nothing of why; say how high work Z can go (the usual cause
        # is an origin set too high for the tool's length).
        messages = [
            f"{message}: work Z can reach only {self.top_z():.4f} "
            "with this origin and tool"
            if "invalid params in linear command" in message
            else message
            for message in messages
        ]
        self.messages += messages
        return messages

    # Method `SCPanelMachine._next_mdi()`:
    def _next_mdi(self, idle: bool, messages: list[str]) -> bool:
        """Start the next MDI line waiting, if its time has come.

        A message means that something went wrong, so the lines still
        waiting (which assumed otherwise) are dropped.

        Arguments:
        * `idle` (`bool`): True if the interpreter is idle.
        * `messages` (`list[str]`): LinuxCNC's new messages.

        Returns:
        * (`bool`): True if lines are still to be finished.
        """
        lcnc: SCClient = cast(SCClient, self.lcnc)
        if messages:
            self.mdi_lines.clear()
        if not self.mdi_lines:
            return False
        if idle and lcnc.call("command.wait_complete", 0) != -1:
            lcnc.call("command.mdi", self.mdi_lines.pop(0))
        return True

    # Method `SCPanelMachine.status()`:
    def status(self) -> SCStatus:
        """Poll LinuxCNC, and start the next MDI line when it is time.

        Returns:
        * (`SCStatus`): The program, line, position, tool and messages.
        """
        if self.lcnc is None:
            return SCStatus(self.file, 0, (0.0, 0.0, 0.0), 0, [], "")
        stat: dict[str, Any] = self.lcnc.stat(
            "actual_position",
            "file",
            "g5x_offset",
            "g92_offset",
            "interp_state",
            "motion_line",
            "paused",
            "tool_in_spindle",
            "tool_offset",
        )
        messages: list[str] = self._read_messages()
        idle: bool = stat["interp_state"] == self.constants["INTERP_IDLE"]
        busy: bool = self._next_mdi(idle, messages)

        # The position in work (program) coordinates: the machine's
        # less the G54 (or other G5x), G92 and tool length offsets.
        x, y, z = (
            stat["actual_position"][axis]
            - stat["g5x_offset"][axis]
            - stat["g92_offset"][axis]
            - stat["tool_offset"][axis]
            for axis in range(3)
        )
        return SCStatus(
            str(stat["file"]),
            int(stat["motion_line"]),
            (x, y, z),
            int(stat["tool_in_spindle"]),
            messages,
            "idle"
            if idle and not busy
            else "paused"
            if stat["paused"]
            else "running",
        )


# Class `SCCommandPort`:
class SCCommandPort:  # pylint: disable=too-few-public-methods
    """A command port on 127.0.0.1: one line in, one line back.

    Attributes:
    * `server` (`socket.socket`): The listening socket (not blocking).
    """

    # Method `SCCommandPort.__init__()`:
    def __init__(self, port: int) -> None:
        """Listen on a port.

        Arguments:
        * `port` (`int`): The port.
        """
        self.server: socket.socket = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", port))
        self.server.listen()
        self.server.setblocking(False)

    # Method `SCCommandPort.poll()`:
    def poll(self, handle: Any) -> None:
        """Answer each waiting connection.

        Arguments:
        * `handle` (`Callable[[str], str]`): Answers a command line.
        """
        while True:
            try:
                connection: socket.socket = self.server.accept()[0]
            except BlockingIOError:
                return
            with connection:
                connection.settimeout(1.0)
                try:
                    data: bytes = b""
                    while b"\n" not in data:
                        chunk: bytes = connection.recv(1024)
                        if not chunk:
                            break
                        data += chunk
                    line: str = data.decode(errors="replace").strip()
                    connection.sendall((handle(line) + "\n").encode())
                except OSError:
                    pass


# Class `SCPanel`:
# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class SCPanel:
    """The control panel window, laid out as in `T.mlcp~3.4`.

    Attributes:
    * `coming` (`tk.Text`): The G-code coming next (read only).
    * `execute_button` (`ttk.Button`): Runs the MDI line.
    * `executed` (`tk.Text`): The G-code already run (read only).
    * `home_button` (`ttk.Button`): Rapids to the work origin.
    * `jog_buttons` (`list[ttk.Button | tk.Radiobutton]`): -X, +X,
      -Y, +Y, -Z, +Z, and the step buttons.
    * `lines` (`list[str]`): The open program's lines.
    * `lines_file` (`str`): The file `lines` was read from.
    * `machine` (`SCPanelMachine`): The LinuxCNC back end.
    * `mdi` (`tk.StringVar`): The MDI line's text.
    * `mdi_entry` (`tk.Entry`): The MDI line, colored as it is typed.
    * `message` (`ttk.Label`): LinuxCNC's last error message.
    * `origin_button` (`ttk.Button`): The Set Origin button.
    * `paused` (`bool`): True while the program is paused.
    * `pause_button` (`ttk.Button`): The Pause button.
    * `port` (`SCCommandPort | None`): The command port, if any.
    * `position` (`ttk.Label`): The work position and the tool.
    * `root` (`tk.Tk`): The window.
    * `run_button` (`ttk.Button`): The Start button (Resume while
      paused).
    * `running` (`bool`): True while a program runs (or is paused).
    * `scrolling` (`bool`): True once the whole program is in the two
      G-code windows, to scroll while paused.
    * `speed` (`tk.DoubleVar`): The speed slider's value: the base 10
      logarithm of the feed override.
    * `speed_text` (`tk.StringVar`): The feed override, shown.
    * `top_speed` (`float`): The slider's highest feed override.
    * `step` (`tk.StringVar`): The jog step chosen (inches).
    * `start` (`int`): The line Start runs from (counted from 1; 0
      for the program's start), chosen with -Tool and +Tool.
    * `tool_buttons` (`list[ttk.Button]`): -Tool and +Tool.
    """

    # Method `SCPanel.__init__()`:
    # pylint: disable-next=too-many-locals,too-many-statements
    def __init__(
        self,
        root: tk.Tk,
        machine: SCPanelMachine,
        max_speed: float,
        port: SCCommandPort | None,
    ) -> None:
        """Build the window.

        It lays the whole window out in one place, so it has many
        locals and statements.

        Arguments:
        * `root` (`tk.Tk`):
          The window to build in.
        * `machine` (`SCPanelMachine`):
          The LinuxCNC back end.
        * `max_speed` (`float`):
          The speed slider's highest setting.
        * `port` (`SCCommandPort | None`):
          The command port, if any.
        """
        self.root: tk.Tk = root
        self.machine: SCPanelMachine = machine
        self.port: SCCommandPort | None = port
        self.paused: bool = False
        self.running: bool = False
        self.start: int = 0
        self.lines: list[str] = []
        self.lines_file: str = ""
        self.scrolling: bool = False
        root.title("SolidCraft LinuxCNC")

        # The G-code run and coming, and below them (above the jog
        # line) the MDI line and Execute.
        self.executed: tk.Text = self.scrolled_text(root, 0)
        self.coming: tk.Text = self.scrolled_text(root, 1)
        mdi: ttk.Frame = ttk.Frame(root)
        mdi.grid(row=4, column=0, padx=4, pady=2, sticky="ew")
        self.mdi: tk.StringVar = tk.StringVar()
        self.mdi_entry: tk.Entry = tk.Entry(
            mdi, textvariable=self.mdi, font="TkFixedFont", background=BLANK
        )
        self.mdi_entry.pack(side="left", fill="x", expand=True)
        self.execute_button: ttk.Button = ttk.Button(
            mdi, text="Execute", command=self.on_execute, state="disabled"
        )
        self.execute_button.pack(side="left", padx=(4, 0))
        self.mdi.trace_add("write", lambda *_: self.check_mdi())

        # The work position and the tool, and LinuxCNC's messages.
        self.position: ttk.Label = ttk.Label(root, font="TkFixedFont")
        self.position.grid(row=2, column=0, padx=4, sticky="w")
        self.message: ttk.Label = ttk.Label(root, foreground="red")
        self.message.grid(row=3, column=0, padx=4, sticky="w")

        # The jog line: Set Origin, Home, the jog buttons and their
        # step (one chosen at a time).
        jog_line: ttk.Frame = ttk.Frame(root)
        jog_line.grid(row=5, column=0, pady=(6, 2))
        self.origin_button: ttk.Button = ttk.Button(
            jog_line, text="Set Origin", command=self.on_set_origin
        )
        self.home_button: ttk.Button = ttk.Button(
            jog_line, text="Home", width=5, command=self.on_home
        )
        self.origin_button.pack(side="left", padx=1)
        self.home_button.pack(side="left", padx=(1, 12))
        jogs: tuple[tuple[str, int, int], ...] = (
            ("-X", 0, -1),
            ("+X", 0, +1),
            ("-Y", 1, -1),
            ("+Y", 1, +1),
            ("-Z", 2, -1),
            ("+Z", 2, +1),
        )
        self.jog_buttons: list[ttk.Button | tk.Radiobutton] = [
            ttk.Button(
                jog_line,
                text=label,
                width=3,
                command=functools.partial(self.on_jog, axis, direction),
            )
            for label, axis, direction in jogs
        ]
        self.step: tk.StringVar = tk.StringVar(value=JOG_STEP)
        self.jog_buttons += [
            tk.Radiobutton(
                jog_line,
                text=step,
                value=step,
                variable=self.step,
                indicatoron=False,
                selectcolor=STEP_CHOSEN,
                width=len(step) + 1,
                pady=3,
            )
            for step in JOG_STEPS
        ]
        for index, button in enumerate(self.jog_buttons):
            button.pack(side="left", padx=(12 if index == 6 else 1, 1))

        # The run line: -Tool and +Tool, Start, Pause and Reset.
        buttons: ttk.Frame = ttk.Frame(root)
        buttons.grid(row=6, column=0, pady=(2, 6))
        self.tool_buttons: list[ttk.Button] = [
            ttk.Button(
                buttons,
                text=label,
                width=6,
                command=functools.partial(self.on_tool, step),
            )
            for label, step in (("-Tool", -1), ("+Tool", +1))
        ]
        self.run_button: ttk.Button = ttk.Button(
            buttons, text="Start", width=7, command=self.on_run
        )
        self.pause_button: ttk.Button = ttk.Button(
            buttons,
            text="Pause",
            width=6,
            command=self.on_pause,
            state="disabled",
        )
        reset: ttk.Button = ttk.Button(
            buttons, text="Reset", width=6, command=self.on_stop
        )
        for index, button in enumerate(
            (*self.tool_buttons, self.run_button, self.pause_button, reset)
        ):
            button.pack(side="left", padx=(12 if index in (0, 2) else 1, 1))

        # The speed slider (logarithmic), with Open at its right.
        self.speed: tk.DoubleVar = tk.DoubleVar(value=0.0)
        self.speed_text: tk.StringVar = tk.StringVar(value="1x")
        self.top_speed: float = min(max_speed, MAX_SPEED)
        slider: ttk.Frame = ttk.Frame(root)
        slider.grid(row=7, column=0, pady=4, sticky="ew")
        ttk.Label(slider, text="speed").pack(side="left", padx=4)
        ttk.Scale(
            slider,
            from_=math.log10(MIN_SPEED),
            to=math.log10(self.top_speed),
            orient="horizontal",
            variable=self.speed,
            command=lambda _value: self.set_speed(10 ** self.speed.get()),
        ).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(slider, textvariable=self.speed_text, width=6).pack(
            side="left"
        )
        ttk.Button(slider, text="Open", command=self.on_open).pack(
            side="left", padx=(12, 1)
        )
        ttk.Button(slider, text="Tools", command=self.on_tools).pack(
            side="left", padx=1
        )
        ttk.Button(slider, text="Quit", command=root.destroy).pack(
            side="left", padx=(12, 1)
        )
        root.after(POLL_MS, self.poll)

    # Method `SCPanel.scrolled_text()`:
    @staticmethod
    def scrolled_text(root: tk.Tk, row: int) -> tk.Text:
        """Make a read only text window with a scroll bar.

        Arguments:
        * `root` (`tk.Tk`): The window to put it in.
        * `row` (`int`): Its row in `root`'s grid.

        Returns:
        * (`tk.Text`): The text window.
        """
        frame: ttk.Frame = ttk.Frame(root)
        frame.grid(row=row, column=0, padx=4, pady=2, sticky="ew")
        text: tk.Text = tk.Text(frame, height=SHOWN, width=50)
        scroll: ttk.Scrollbar = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set, state="disabled")
        text.pack(side="left", fill="x", expand=True)
        scroll.pack(side="left", fill="y")
        return text

    # Method `SCPanel.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override, the slider and the number shown.

        Arguments:
        * `speed` (`float`): The feed override, kept within the
          slider's range.
        """
        speed = min(max(speed, MIN_SPEED), self.top_speed)
        self.speed.set(math.log10(speed))
        self.speed_text.set(f"{speed:.2g}x")
        self.machine.set_speed(speed)

    # Method `SCPanel.set_text()`:
    @staticmethod
    def set_text(text: tk.Text, lines: list[str]) -> None:
        """Replace the contents of a read only text window.

        Arguments:
        * `text` (`tk.Text`):
          The text window.
        * `lines` (`list[str]`):
          Its new lines.
        """
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    # Method `SCPanel.set_running()`:
    def set_running(self, running: bool, paused: bool) -> None:
        """Grey out the buttons that can not be pressed now.

        Arguments:
        * `running` (`bool`): True while a program runs (or is paused).
        * `paused` (`bool`): True while it is paused.
        """
        self.paused = paused
        self.running = running
        for button in self.tool_buttons:
            button.configure(state="disabled" if running else "normal")
        self.run_button.configure(
            text="Resume" if paused else "Start",
            state="disabled" if running and not paused else "normal",
        )
        self.pause_button.configure(
            state="normal" if running and not paused else "disabled"
        )

        # Jogs only while stopped: LinuxCNC 2.9 will not change modes
        # while a program runs or is paused.  (`poll()` sets Set Origin
        # and Home, which also depend on the position.)
        widget: ttk.Button | tk.Radiobutton
        for widget in self.jog_buttons:
            widget.configure(state="disabled" if running else "normal")
        self.check_mdi()

    # Method `SCPanel.check_mdi()`:
    def check_mdi(self) -> None:
        """Color the MDI line; allow Execute when stopped and good.

        LinuxCNC 2.9 runs MDI only when no program is running or
        paused (its task refuses the change of mode).
        """
        kind: str = line_kind(self.mdi.get())
        self.mdi_entry.configure(
            background={"empty": BLANK, "good": GOOD, "bad": BAD}[kind]
        )
        self.execute_button.configure(
            state="normal"
            if not self.running and kind == "good"
            else "disabled"
        )

    # Method `SCPanel.open()`:
    def open(self, path: str) -> None:
        """Open a program.

        Arguments:
        * `path` (`str`): The G-code file.
        """
        self.machine.open(path)
        self.start = 0
        self.lines_file = ""  # Read it again, even when the same file.
        self.set_running(False, False)

    # Method `SCPanel.on_open()`:
    def on_open(self) -> None:
        """Choose a program with a file window, and open it."""
        path: str = filedialog.askopenfilename(
            title="Open G-code",
            filetypes=[("G-code", "*.ngc *.nc *.gcode"), ("All", "*")],
        )
        if path:
            self.open(path)

    # Method `SCPanel.on_tools()`:
    def on_tools(self) -> None:
        """Show the tools' speeds and feeds for a material chosen."""
        # The shop is read again each time, so edits to it show.
        try:
            shop: dict[str, object] = shops.read(SHOP_FILE)
        except ValueError as error:
            messagebox.showerror("Tools", str(error))
            return
        window: tk.Toplevel = tk.Toplevel(self.root)
        window.title(f"Tools: {SHOP_MACHINE}")
        material: tk.StringVar = tk.StringVar(value=MATERIAL)
        chooser: ttk.Combobox = ttk.Combobox(
            window,
            textvariable=material,
            values=material_names(shop),
            state="readonly",
            width=30,
        )
        chooser.pack(anchor="w", padx=4, pady=4)
        table: tk.Text = tk.Text(
            window, width=72, height=12, font="TkFixedFont"
        )
        table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Fill the table now, and again when another material is chosen.
        def show(_event: object = None) -> None:
            table.configure(state="normal")
            table.delete("1.0", "end")
            table.insert(
                "1.0", tool_speeds(shop, SHOP_MACHINE, material.get())
            )
            table.configure(state="disabled")

        chooser.bind("<<ComboboxSelected>>", show)
        show()

    # Method `SCPanel.on_run()`:
    def on_run(self) -> None:
        """Run the program, or resume it after a pause."""
        self.message.configure(text="")
        if self.paused:
            self.machine.resume()
        else:
            self.machine.run(self.start)
        self.set_running(True, False)

    # Method `SCPanel.on_pause()`:
    def on_pause(self) -> None:
        """Pause the program; the editable lines may then be run."""
        self.machine.pause()
        self.set_running(True, True)

    # Method `SCPanel.on_tool()`:
    def on_tool(self, step: int) -> None:
        """Move the start line to the next or previous tool change.

        Arguments:
        * `step` (`int`): +1 for the next, -1 for the previous.
        """
        changes: list[int] = [0, *tool_changes(self.lines)]
        if step > 0:
            later: list[int] = [line for line in changes if line > self.start]
            self.start = later[0] if later else self.start
        else:
            earlier: list[int] = [
                line for line in changes if line < self.start
            ]
            self.start = earlier[-1] if earlier else 0

    # Method `SCPanel.on_execute()`:
    def on_execute(self) -> None:
        """Run the MDI line."""
        try:
            self.machine.mdi(self.mdi.get().strip())
        except RuntimeError as error:
            self.message.configure(text=str(error))

    # Method `SCPanel.on_stop()`:
    def on_stop(self) -> None:
        """Stop at once, ready to run again from the program's start."""
        self.message.configure(text="")
        self.machine.stop()
        self.start = 0
        self.set_running(False, False)

    # Method `SCPanel.on_jog()`:
    def on_jog(self, axis: int, direction: int) -> None:
        """Jog one axis by the chosen step.

        Arguments:
        * `axis` (`int`): The axis: 0 for X, 1 for Y, 2 for Z.
        * `direction` (`int`): +1 or -1.
        """
        self.machine.jog(axis, direction, float(self.step.get()))

    # Method `SCPanel.on_home()`:
    def on_home(self) -> None:
        """Rapid to the work origin."""
        try:
            self.machine.go_origin(self.machine.status().position[2])
        except RuntimeError as error:
            self.message.configure(text=str(error))

    # Method `SCPanel.on_set_origin()`:
    def on_set_origin(self) -> None:
        """Make the current position zero, after asking (No first)."""
        if messagebox.askyesno(
            "Set Origin",
            "Make the current position the program's zero?",
            default="no",
        ):
            try:
                self.machine.set_origin()
            except RuntimeError as error:
                self.message.configure(text=str(error))

    # Method `SCPanel.widgets()`:
    def widgets(self, parent: Any = None) -> Iterator[Any]:
        """Walk every widget, top windows and their insides.

        Arguments:
        * `parent` (`Any`): Where to start (`None` for the root).

        Yields:
        * (`Any`): Each widget inside it.
        """
        for widget in (parent or self.root).winfo_children():
            yield widget
            yield from self.widgets(widget)

    # Method `SCPanel.press()`:
    def press(self, label: str) -> str:
        """Press a button, as a person would.

        Arguments:
        * `label` (`str`): The text on it.

        Returns:
        * (`str`): `ok`, or `error: ...` when there is no such button
          or it is greyed out.
        """
        for widget in self.widgets():
            if (
                widget.winfo_class() in BUTTONS
                and str(widget.cget("text")) == label
            ):
                if str(widget.cget("state")) == "disabled":
                    return f"error: {label} is greyed out"
                widget.invoke()
                return "ok"
        return f"error: no button {label}"

    # Method `SCPanel.show()`:
    def show(self) -> dict[str, Any]:
        """Return what the window shows.

        Returns:
        * (`dict[str, Any]`): `executed` and `coming` (the G-code
          windows), `position`, `message`, `mdi` and `mdi_color` (the
          MDI line), `step` and `speed` (those shown), `buttons` (each
          button's state, by its text) and `texts` (the contents of
          every text window, such as Tools).
        """
        widgets: list[Any] = list(self.widgets())
        return {
            "executed": self.executed.get("1.0", "end-1c"),
            "coming": self.coming.get("1.0", "end-1c"),
            "position": str(self.position.cget("text")),
            "message": str(self.message.cget("text")),
            "mdi": self.mdi.get(),
            "mdi_color": str(self.mdi_entry.cget("background")),
            "step": self.step.get(),
            "speed": self.speed_text.get(),
            "buttons": {
                str(widget.cget("text")): str(widget.cget("state") or "normal")
                for widget in widgets
                if widget.winfo_class() in BUTTONS
            },
            "texts": [
                widget.get("1.0", "end-1c")
                for widget in widgets
                if widget.winfo_class() == "Text"
            ],
        }

    # Method `SCPanel.handle()`:
    # A flat list of commands reads best, so it has many returns.
    # pylint: disable-next=too-many-return-statements
    def handle(self, line: str) -> str:
        """Answer one command from the command port.

        Arguments:
        * `line` (`str`): The command.

        Returns:
        * (`str`): The answer: `ok`, the status, or `error: ...`.
        """
        word, _, rest = line.partition(" ")
        actions: dict[str, Any] = {
            "ping": lambda: None,
            "run": self.on_run,
            "start": self.on_run,
            "pause": self.on_pause,
            "stop": self.on_stop,
            "reset": self.on_stop,
            "tool+": functools.partial(self.on_tool, +1),
            "tool-": functools.partial(self.on_tool, -1),
            "quit": self.root.destroy,
        }
        try:
            if word in actions:
                actions[word]()
            elif word == "press" and rest:
                return self.press(rest.strip())
            elif word == "type":
                self.mdi.set(rest)
            elif word == "show":
                return json.dumps(self.show())
            elif word == "answer" and tk is lcnc_headless:
                lcnc_headless.ANSWERS.append(rest.strip())
            elif word == "open" and rest:
                self.open(rest.strip())
            elif word == "speed" and rest:
                self.set_speed(float(rest))
            elif word == "status":
                status: SCStatus = self.machine.status()
                x, y, z = status.position
                return (
                    f"file={status.file} line={status.line} "
                    f"x={x:.4f} y={y:.4f} z={z:.4f} tool={status.tool} "
                    f"start={self.start} state={status.state}"
                )
            elif word == "messages":
                return f"messages: {' | '.join(self.machine.messages)}"
            else:
                return f"error: unknown command {line!r}"
        except (ValueError, OSError, SCBridgeError) as error:
            return f"error: {error}"
        return "ok"

    # Method `SCPanel.poll()`:
    def poll(self) -> None:
        """Show the machine's state, answer the port, then poll again."""
        # A LinuxCNC that has gone is reported, while the port still
        # answers, and the window stays up to be read.
        try:
            status: SCStatus = self.machine.status()
        except (OSError, SCBridgeError) as error:
            self.message.configure(text=f"LinuxCNC is not answering: {error}")
            if self.port is not None:
                self.port.poll(self.handle)
            self.root.after(POLL_MS, self.poll)
            return

        # The program around the line being run, read once per file.
        if status.file != self.lines_file:
            self.lines_file = status.file
            self.lines = self.machine.program_lines(status.file)
        # The buttons follow LinuxCNC's state (a program may end, or be
        # stopped, without the panel).
        if status.state and (
            (status.state != "idle", status.state == "paused")
            != (self.running, self.paused)
        ):
            self.set_running(status.state != "idle", status.state == "paused")

        # Before a run, the lines from the start line on are coming.
        # While paused, the whole program is in the two windows, put
        # there once so that they can be scrolled.
        current: int = status.line if self.running else max(0, self.start - 1)
        if self.paused and not self.scrolling:
            self.set_text(self.executed, self.lines[:current])
            self.set_text(self.coming, self.lines[current:])
            self.executed.see("end")
            self.coming.yview_moveto(0.0)
            self.scrolling = True
        elif not self.paused:
            self.scrolling = False
            self.set_text(
                self.executed, self.lines[max(0, current - SHOWN) : current]
            )
            self.set_text(self.coming, self.lines[current : current + SHOWN])

        # Set Origin and Home only while stopped, away from the origin.
        x, y, z = status.position
        away: bool = max(abs(x), abs(y), abs(z)) > AT_ORIGIN
        for button in (self.origin_button, self.home_button):
            button.configure(
                state="normal" if away and not self.running else "disabled"
            )

        # The position, the tool and any message.
        self.position.configure(
            text=f"X {x:9.4f}  Y {y:9.4f}  Z {z:9.4f}  T{status.tool:02d}"
            f"  start line {self.start}"
        )
        if status.messages:
            self.message.configure(text=status.messages[-1])

        # Commands from the port.
        if self.port is not None:
            self.port.poll(self.handle)
        self.root.after(POLL_MS, self.poll)


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Show the panel until its window is closed.

    Arguments:
    * `arguments` (`list[str]`):
      The command line arguments, less the program name.

    Returns:
    * (`int`): The exit status.
    """
    # The command line.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("program", nargs="?", help="G-code to open")
    parser.add_argument("--port", type=int, help="a command port on 127.0.0.1")
    parser.add_argument(
        "--lcnc-port",
        type=int,
        default=PORT,
        help="the port of serve_linuxcnc (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="use no LinuxCNC"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="use no display or tkinter, for tests through --port",
    )
    options: argparse.Namespace = parser.parse_args(arguments)
    if options.headless:
        use_headless()
    elif tk is lcnc_headless:
        print("lcnc_panel.py: tkinter is not installed.", file=sys.stderr)
        return 1

    # The machine, on and homed, and the command port.
    try:
        machine: SCPanelMachine = SCPanelMachine(
            options.dry_run, options.lcnc_port
        )
        machine.start()
        top_speed: float = machine.max_speed()
    except (OSError, RuntimeError, ValueError, SCBridgeError) as error:
        print(f"lcnc_panel.py: {error}", file=sys.stderr)
        return 1
    port: SCCommandPort | None = (
        SCCommandPort(options.port) if options.port else None
    )

    # The window.  A `SIGTERM` closes it as its close button does.  An
    # earlier panel may have left another speed, and the slider starts
    # at the programmed feed.
    root: tk.Tk = tk.Tk()
    panel: SCPanel = SCPanel(root, machine, top_speed, port)
    panel.set_speed(1.0)
    signal.signal(signal.SIGTERM, lambda *_: root.destroy())
    if options.program:
        panel.open(options.program)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
