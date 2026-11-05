#!/usr/bin/env python3
"""A minimal LinuxCNC HMI, in place of AXIS (`T.mlcp~3.4`).

A small `tkinter` window that drives the LinuxCNC back end through its
Python API.  On top, on every tab, are the work position and the tool
in the spindle, LinuxCNC's last message, and how much of the setup is
drawn; under the tabs, Open and Quit.  The tabs, one for each task:

* Run: the G-code already run, the G-code coming next, one line of
  G-code to run as MDI (Execute, while stopped; green when it reads
  as RS-274, red when not), a run line (-Tool and +Tool, which move
  the line Start runs from to the previous or next tool change;
  Start, Pause and Reset) and a speed slider (the feed override).
* Setup: Next Step (the setup's items, one at a time), Set Origin,
  Home to the work origin, Set X, Set Y and Set Z (the current
  position on one axis made to read the number typed), six jog
  buttons and the jog step (1 to .0001 in).
* Tools: the tools' speeds and feeds, for a material chosen.
* View: toggles that show or hide, in SolidCraft, the keep-outs, the
  stock outline, SolidCraft's origin and the tools' holders
  (`TOGGLES`).

The LinuxCNC calls are kept in `HMIMachine`, a client (through
`scraftcnc.lcnc.lcnc_client`) of `serve_linuxcnc` from
`scraftcnc/lcnc/`, which runs LinuxCNC in its `lcnc` box, or in WSL on
Windows.  So this runs outside the box, and needs only `tkinter`.
Closing it leaves LinuxCNC running, for another HMI.  When it starts,
the machine is taken out of E-stop, turned on and homed if it needs to
be, it is sent the shop's tool table, and the INI file's
`MAX_FEED_OVERRIDE` limits the slider.  Each program opened sends the
tool table again (while LinuxCNC is idle), for the material its setup
comments name (the part's, else the stock's), or `MATERIAL` when they
name none the shop knows; the position line shows the machine and
material in use.  A program whose setup names another shop or machine is
refused.  A program may not start until its origin is set: from its
setup (the shop's table place less the setup's table location), or by
the operator with Set Origin:

```
python3 -m scraftcnc.lcnc.serve_linuxcnc &
python3 -m scraftcnc.hmi.lcnc_hmi demo.ngc
# The window alone:
python3 -m scraftcnc.hmi.lcnc_hmi --dry-run demo.ngc
# No window, for tests:
python3 -m scraftcnc.hmi.lcnc_hmi --headless --port 5007
```

With `--headless`, the HMI is built from `lcnc_hmi_headless.py` in
place of `tkinter`, so it needs no display and no `tkinter`, and
otherwise runs the same code, with its buttons pressed through the
command port.

A program is opened from the command line, with Open, or through the
command port
(`--port PORT`, on 127.0.0.1), which takes one line per connection and
answers one line: `ping`, `open FILE`, `start` (or `run`), `pause`,
`reset` (or `stop`), `tool+`, `tool-` (the start line to the next or
previous tool change), `speed X`, `press LABEL` (presses a button on
any tab, as a person would; refused when it is greyed out), `tab
NAME` (shows a tab, as a person clicking it would), `origin AXIS
NUMBER` (types into Set X, Y or Z's entry), `type LINE` (into
the MDI line), `show` (all that the window shows, as JSON), `answer
VALUE` (with `--headless`, the answer to the next question: `yes`, a
file or a setup origin's name), `status`, `messages` (every message
LinuxCNC has sent, as `messages: A | B`), `log` (every command sent,
as `log: A | B`) or `quit`:

```
echo "open demo.ngc" | nc -q 1 127.0.0.1 5007
```
"""

# Half of the module is docstrings, which the type hints and the
# argument lists make long, so it passes 1000 lines.
# pylint: disable=too-many-lines

import argparse
import functools
import itertools
import json
import math
import queue
import re
import signal
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from .. import shops
from ..assembly import Assembly, AssemblyItem, millimeters
from ..geometry import LineSegment, RoundedPolygon
from ..keepout import assembly_zones
from ..lcnc.lcnc_client import PORT, BridgeClient, BridgeError, constant
from ..model_cache import ModelCache
from ..plot import PathMove, command_moves, read_gcode
from ..pybind.scraftpybind import PyBind, connect
from ..setup_comments import read_file
from ..setup_view import SetupView, named_origins
from ..tooling.shop_registries import use_shop
from ..tooling.tools import Point
from . import lcnc_hmi_headless

# A computer with no `tkinter` can still run `--headless`.
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    # pylint: disable=reimported,ungrouped-imports
    from . import lcnc_hmi_headless as filedialog  # type: ignore[no-redef]
    from . import lcnc_hmi_headless as messagebox  # type: ignore[no-redef]
    from . import lcnc_hmi_headless as tk  # type: ignore[no-redef]
    from . import lcnc_hmi_headless as ttk  # type: ignore[no-redef]

# The protocol of `serve_linuxcnc` that this needs, at least.
PROTOCOL: int = 2

# How long a new LinuxCNC gets to turn on and to home (seconds).
START_SECONDS: float = 60.0

# The steps a jog button can move (inches), the one chosen at start,
# and how fast a jog moves (inches per second).
JOG_STEPS: tuple[str, ...] = ("1", ".1", ".01", ".001", ".0001")
JOG_STEP: str = ".0001"
JOG_SPEED: float = 1.0

# The background of the jog step chosen.
STEP_CHOSEN: str = "#a8c8f0"

# How close to the work origin counts as there (inches).
AT_ORIGIN: float = 0.00005

# How often the HMI polls LinuxCNC and the command port
# (milliseconds).
POLL_MS: int = 100

# The speed slider's range (feed override, on a logarithmic scale; 0
# is left out, since Pause stops), its top limited by the INI file's
# `MAX_FEED_OVERRIDE`.
MIN_SPEED: float = 0.01
MAX_SPEED: float = 10.0

# The axes whose origin can be set one at a time.
AXES: tuple[str, ...] = ("X", "Y", "Z")

# The rapid speed (inches per minute) when LinuxCNC does not say, as
# the example shop's mill.
RAPID_SPEED: float = 60.0

# How many lines the executed and coming windows show.
SHOWN: int = 6

# A tool change line (`M6`, outside a comment).
TOOL_CHANGE: re.Pattern[str] = re.compile(r"\bM0*6\b", re.IGNORECASE)

# A line that leads up to a tool change: the operator's message
# (`(MSG, ...)`) and the pause (`M0` or `M1`).
CHANGE_LEAD: re.Pattern[str] = re.compile(
    r"^\s*(\(MSG,[^()]*\)|M0*[01])\s*$", re.IGNORECASE
)

# A units word: `G20` (inches) or `G21` (millimeters).
UNITS: re.Pattern[str] = re.compile(r"\bG(2[01])\b", re.IGNORECASE)

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
BUTTONS: tuple[str, ...] = ("TButton", "Radiobutton", "TCheckbutton")

# The View tab's toggles: each label, and what it shows (of
# `setup_view.HIDEABLE`), and whether it starts shown.
TOGGLES: tuple[tuple[str, str, bool], ...] = (
    ("Keep-outs", "keep_out", False),
    ("Stock outline", "stock", True),
    ("Origin", "origin", True),
    ("Holders", "holder", True),
)

# The HMI's tabs, one for each task, in their order.
TABS: tuple[str, ...] = ("Run", "Setup", "Tools", "View")

# The MDI line's backgrounds: empty, RS-274, and not.
BLANK: str = "white"
GOOD: str = "#d8f5d0"
BAD: str = "#f8d0d0"


# Function `use_headless()`:
def use_headless() -> None:
    """Build every window from now on with `lcnc_hmi_headless`."""
    # The window code stays the same, by using the same names.
    # pylint: disable-next=global-statement
    global tk, ttk, filedialog, messagebox
    tk = ttk = filedialog = messagebox = lcnc_hmi_headless


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


# Function `setup_material()`:
def setup_material(assembly: Assembly, names: list[str]) -> str:
    """Return the material a setup says is cut, as the shop names it.

    The part's `material` is looked at first, then the stock's (the
    setup comments carry no shop or machine, `T.hs~5.1.5` S4).

    Arguments:
    * `assembly` (`Assembly`): The setup.
    * `names` (`list[str]`): The shop's material names.

    Returns:
    * (`str`): The material, or `""` when no item names one of the
      shop's.
    """
    item: AssemblyItem
    for item in reversed(assembly.items):
        material: object = item.args.get("material")
        if isinstance(material, str) and material in names:
            return material
    return ""


# Function `shop_name()`:
def shop_name() -> str:
    """Return the name of the HMI's shop (`SHOP_FILE`).

    Returns:
    * (`str`): Its name, or `""` when it can not be read.
    """
    try:
        return str(shops.read(SHOP_FILE).get("name", ""))
    except ValueError:
        return ""


# Function `setup_warning()`:
def setup_warning(assembly: Assembly, shop: str) -> str:
    """Return why a setup for another shop or machine is refused.

    Arguments:
    * `assembly` (`Assembly`): The setup.
    * `shop` (`str`): The name of the HMI's shop.

    Returns:
    * (`str`): The reason, or `""` when the setup names neither, or
      this shop and `SHOP_MACHINE`.
    """
    if assembly.machine and assembly.machine != SHOP_MACHINE:
        return (
            f"Not opened: the program is for {assembly.machine}, "
            f"not {SHOP_MACHINE}"
        )
    if assembly.shop and shop and assembly.shop != shop:
        return f"Not opened: the program is for {assembly.shop}, not {shop}"
    return ""


# Function `setup_origin()`:
def setup_origin(
    assembly: Assembly, shop: dict[str, object], machine: str
) -> tuple[float, float, float] | None:
    """Return the work origin (G54) a setup gives on a machine.

    It is where the machine's table sits (its `table`'s `x`, `y` and
    `z`, in machine coordinates) less where the setup puts the table
    (its bottom item, which names a `table`), as the setup frame is
    the work frame.

    Arguments:
    * `assembly` (`Assembly`): The setup.
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.
    * `machine` (`str`): The machine's name.

    Returns:
    * (`tuple[float, float, float] | None`): The origin (inches), or
      `None` when the machine's table has no place or the setup's
      bottom item is not a table.
    """
    # Where the machine's table sits, if the shop says.
    machines: list[Any] = cast(list[Any], shop.get("machines", []))
    table: dict[str, Any] = next(
        (
            cast(dict[str, Any], entry.get("table", {}))
            for entry in machines
            if entry.get("name") == machine
        ),
        {},
    )
    axes: tuple[str, ...] = ("x", "y", "z")
    if not assembly.items or not all(axis in table for axis in axes):
        return None
    bottom: AssemblyItem = assembly.items[0]
    if "table" not in bottom.args:
        return None

    # The table's place, less its place in the setup.
    x, y, z = (
        (millimeters(table[axis], f"table {axis}") - at) / 25.4
        for axis, at in zip(axes, bottom.location, strict=True)
    )
    return (x, y, z)


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
    """Return the lines that start each tool change (`change_spans()`).

    Arguments:
    * `lines` (`list[str]`): The program's lines.

    Returns:
    * (`list[int]`): Their numbers, counted from 1, in order.
    """
    return [start for start, _ in change_spans(lines)]


# Function `change_spans()`:
def change_spans(lines: list[str]) -> list[tuple[int, int]]:
    """Return the lines that start each tool change.

    A change starts at its message and pause (`CHANGE_LEAD`) when it
    has them, so that a run started there tells the operator first.

    Arguments:
    * `lines` (`list[str]`): The program's lines.

    Returns:
    * (`list[tuple[int, int]]`): Each change's first line and its `M6`
      line, counted from 1, in order.
    """
    spans: list[tuple[int, int]] = []
    number: int
    line: str
    for number, line in enumerate(lines, 1):
        if TOOL_CHANGE.search(COMMENT.sub("", line)):
            start: int = number
            while start > 1 and CHANGE_LEAD.match(lines[start - 2]):
                start -= 1
            spans.append((start, number))
    return spans


# Function `line_minutes()`:
def line_minutes(lines: list[str], rapid_speed: float) -> list[float]:
    """Return how long each line of a program takes, roughly.

    The moves are read as the tool path viewer reads them
    (`plot.command_moves()`): rapids at `rapid_speed`, feeds at the `F`
    in effect, arcs by their length, and a canned drilling cycle as a
    rapid over each hole and one feed down (its pecks left out).
    Acceleration is ignored, so a program of many short moves takes
    longer than this.  Units are as the program's (inches here); a
    line that can not be read takes no time.

    Arguments:
    * `lines` (`list[str]`): The program's lines.
    * `rapid_speed` (`float`): How fast a rapid goes, per minute.

    Returns:
    * (`list[float]`): Minutes, one per line.
    """
    # Read each line by itself, so that one odd line costs nothing.
    commands: list[dict[str, Any]] = []
    line: str
    for line in lines:
        try:
            commands.append(cast(dict[str, Any], read_gcode(line)[0]))
        except (ValueError, IndexError):
            commands.append({})

    # Add up each move's length over its speed.
    minutes: list[float] = [0.0] * len(lines)
    move: PathMove
    for move in command_moves(cast(Any, commands)):
        speed: float = rapid_speed if move["g"] == 0 else move["f"]
        if speed > 0.0:
            length: float = sum(
                math.dist(start, end)
                for start, end in itertools.pairwise(move["pts"])
            )
            minutes[move["line"]] += length / speed
    return minutes


# Function `jog_hit()`:
def jog_hit(
    zones: list[RoundedPolygon],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
) -> str:
    """Return the keep-out a straight jog would enter, if any.

    The tool is checked as `keepout.py` checks a program's moves: a
    vertical cylinder of the tool's widest radius reaching up forever,
    at the move's lowest tip height.  So a jog up (+Z) never enters
    anything, and one that starts inside a keep-out, other than up,
    is refused (raise Z first).

    Arguments:
    * `zones` (`list[RoundedPolygon]`): The keep-outs, work inches.
    * `start` (`tuple[float, float, float]`): Where the tip is.
    * `end` (`tuple[float, float, float]`): Where the jog takes it.
    * `radius` (`float`): The tool's widest radius (0 for none).

    Returns:
    * (`str`): The keep-out's name, or `""` when the jog is clear.
    """
    if end[2] > start[2] and end[:2] == start[:2]:
        return ""
    move: LineSegment = LineSegment(start[:2], end[:2])
    low: float = min(start[2], end[2])
    zone: RoundedPolygon
    for zone in zones:
        if zone.hits(move, low, radius):
            return zone.name
    return ""


# Function `clock()`:
def clock(minutes: float) -> str:
    """Return minutes as `M:SS`.

    Arguments:
    * `minutes` (`float`): The time.

    Returns:
    * (`str`): E.g. `3:42`.
    """
    seconds: int = round(minutes * 60.0)
    return f"{seconds // 60}:{seconds % 60:02d}"


# Function `change_tool_label()`:
def change_tool_label(lines: list[str], span: tuple[int, int]) -> str:
    """Return the tool a change puts in, with its description.

    Arguments:
    * `lines` (`list[str]`): The program's lines.
    * `span` (`tuple[int, int]`): The change's first and `M6` lines.

    Returns:
    * (`str`): E.g. `T05 1/8 in 90 deg carbide chamfer mill`, from its
      `MSG` line, else its `M6` line and comment.
    """
    start, change = span
    message: re.Match[str] | None = re.match(
        r"^\s*\(MSG,\s*Insert\s+(T\d+):\s*([^()]*)\)", lines[start - 1]
    )
    if message is not None:
        return f"{message.group(1)} {message.group(2).strip()}"
    tool: re.Match[str] | None = re.search(r"\bT\d+", lines[change - 1])
    note: re.Match[str] | None = re.search(r"\(([^()]*)\)", lines[change - 1])
    return " ".join(
        found.group(index)
        for found, index in ((tool, 0), (note, 1))
        if found is not None
    )


# Function `next_tool_text()`:
def next_tool_text(
    lines: list[str],
    sums: list[float],
    spans: list[tuple[int, int]],
    line: int,
    override: float,
) -> str:
    """Return the next tool, and the time left until it.

    Arguments:
    * `lines` (`list[str]`): The program's lines.
    * `sums` (`list[float]`): Minutes up to each line: `sums[n]` is
      the time of lines 1 to `n` (so `len(lines) + 1` of them).
    * `spans` (`list[tuple[int, int]]`): The tool changes
      (`change_spans()`).
    * `line` (`int`): The line being run, or run from (from 1).
    * `override` (`float`): The feed override.

    Returns:
    * (`str`): E.g. `Next: T05 ... in 3:42`, `Now: T05 ..., cut 3:42`
      at a change (as at its prompt), or `Last tool: 2:10 to the
      end`; `""` for no program.
    """
    if not lines:
        return ""
    line = min(max(line, 1), len(lines))
    rate: float = max(override, 1e-6)
    index: int
    span: tuple[int, int]
    for index, span in enumerate(spans):
        start, change = span
        end: int = (
            spans[index + 1][0] if index + 1 < len(spans) else len(lines) + 1
        )
        if start <= line <= change:
            cut: float = (sums[end - 1] - sums[change]) / rate
            return f"Now: {change_tool_label(lines, span)}, cut {clock(cut)}"
        if start > line:
            left: float = (sums[start - 1] - sums[line - 1]) / rate
            return f"Next: {change_tool_label(lines, span)} in {clock(left)}"
    left = (sums[len(lines)] - sums[line - 1]) / rate
    return f"Last tool: {clock(left)} to the end"


# Class `HMIStatus`:
@dataclass(slots=True)
class HMIStatus:
    """What the HMI shows of the machine, from one poll.

    Attributes:
    * `file` (`str`): The open program ("" for none).
    * `line` (`int`): The line being run (counted from 1; 0 for none).
    * `position` (`tuple[float, float, float]`): X, Y and Z, in work
      coordinates (inches).
    * `tool` (`int`): The T number in the spindle (0 for none).
    * `messages` (`list[str]`): LinuxCNC's new error messages.
    * `state` (`str`): `idle`, `running` or `paused` (`""` for a dry
      run, where the HMI's own idea of it stands).

    Constructor:
    * `HMIStatus(file, line, position, tool, messages, state)`
    """

    # Constructor arguments:
    file: str = field(init=True)
    line: int = field(init=True)
    position: tuple[float, float, float] = field(init=True)
    tool: int = field(init=True)
    messages: list[str] = field(init=True)
    state: str = field(init=True)


# Class `HMIMachine`:
class HMIMachine:
    """The LinuxCNC back end, as the HMI sees it.

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
    * `lcnc` (`BridgeClient | None`): The connection, or `None`.
    * `log` (`list[str]`): What was asked of the machine, in order.
    * `mdi_lines` (`list[str]`): The MDI lines waiting to be run.
    * `messages` (`list[str]`): Every message LinuxCNC has sent.
    """

    # Method `HMIMachine.__init__()`:
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
        self.lcnc: BridgeClient | None = None
        self.log: list[str] = []
        self.mdi_lines: list[str] = []
        self.messages: list[str] = []
        if dry_run:
            return

        # Connect, and check that it knows the calls used here.
        try:
            self.lcnc = BridgeClient(port=port)
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

    # Method `HMIMachine._mode()`:
    def _mode(self, name: str) -> None:
        """Switch LinuxCNC to a mode (`MODE_AUTO`, `MODE_MDI`, ...).

        Arguments:
        * `name` (`str`):
          The name of the mode constant in `linuxcnc`.
        """
        if self.lcnc is not None:
            self.lcnc.call("command.mode", constant(name))
            self.lcnc.call("command.wait_complete")

    # Method `HMIMachine._wait_for()`:
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

    # Method `HMIMachine._home()`:
    def _home(self) -> bool:
        """Take it out of E-stop, turn it on, and home every joint.

        A machine already on and homed is left alone, since it may be
        running a program for an HMI that has since closed.

        Returns:
        * (`bool`): True if it had to be homed, as a new LinuxCNC does.
        """
        lcnc: BridgeClient = cast(BridgeClient, self.lcnc)
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

    # Method `HMIMachine.start()`:
    def start(self) -> None:
        """Get LinuxCNC ready, keeping what it has if already running.

        It is turned on and homed if it needs to be.  G54 is left as
        LinuxCNC has it: each program gets its own origin, from its
        setup or from the operator (`HMI.mark_origin_set()`).
        The shop's tool table is sent unless a program is running.

        Raises:
        * `ValueError`: If the shop can not give a tool table.
        """
        self.log.append("start")
        if self.lcnc is None:
            return
        self._home()
        interp_state: int = self.lcnc.stat("interp_state")["interp_state"]
        if interp_state != self.constants["INTERP_IDLE"]:
            return

        # The tool table, from the shop.
        self.write_tool_table(MATERIAL)

    # Method `HMIMachine.set_work_origin()`:
    def set_work_origin(self, origin: tuple[float, float, float]) -> bool:
        """Set G54 to a point in machine coordinates, unless running.

        Arguments:
        * `origin` (`tuple[float, float, float]`): The point (inches).

        Returns:
        * (`bool`): `True` when it was set (always, with no LinuxCNC);
          `False` when a program is running.
        """
        x, y, z = (round(value, 4) for value in origin)
        self.log.append(f"origin {x} {y} {z}")
        if self.lcnc is None:
            return True
        interp_state: int = self.lcnc.stat("interp_state")["interp_state"]
        if interp_state != self.constants["INTERP_IDLE"]:
            return False

        # `G20` first: otherwise the numbers may be read as millimeters.
        self._mode("MODE_MDI")
        self.lcnc.call("command.mdi", f"G20 G10 L2 P1 X{x} Y{y} Z{z}")
        self.lcnc.call("command.wait_complete")
        return True

    # Method `HMIMachine.write_tool_table()`:
    def write_tool_table(self, material: str) -> bool:
        """Send LinuxCNC the shop's tool table, unless it is running.

        Arguments:
        * `material` (`str`): The material being cut (the shop's
          name for it), for the drills.

        Returns:
        * (`bool`): `True` when the table was sent (always, with no
          LinuxCNC); `False` when a program is running.

        Raises:
        * `ValueError`: If the shop can not give a tool table.
        """
        text: str = shops.tool_table_text(
            shops.read(SHOP_FILE), SHOP_MACHINE, material
        )
        self.log.append(f"tool table {material}")
        if self.lcnc is None:
            return True
        interp_state: int = self.lcnc.stat("interp_state")["interp_state"]
        if interp_state != self.constants["INTERP_IDLE"]:
            return False
        self.lcnc.call("tool_table.write", text)
        self.lcnc.call("command.load_tool_table")
        self.lcnc.call("command.wait_complete")
        return True

    # Method `HMIMachine.rapid_speed()`:
    def rapid_speed(self) -> float:
        """Return how fast a rapid goes, from the INI file.

        Returns:
        * (`float`): Its `[TRAJ] MAX_LINEAR_VELOCITY` (or
          `MAX_VELOCITY`), per minute, or `RAPID_SPEED`.
        """
        if self.lcnc is None:
            return RAPID_SPEED
        key: str
        for key in ("MAX_LINEAR_VELOCITY", "MAX_VELOCITY"):
            found: str | None = self.lcnc.call("ini.find", "TRAJ", key)
            if found:
                return float(found) * 60.0
        return RAPID_SPEED

    # Method `HMIMachine.max_speed()`:
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

    # Method `HMIMachine.open()`:
    def open(self, path: str) -> None:
        """Send a program to LinuxCNC, ready to run from its start.

        Arguments:
        * `path` (`str`): The G-code file, here (a relative path is
          from the HMI's directory).

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

    # Method `HMIMachine.program_lines()`:
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
        except (OSError, BridgeError):
            return []
        return text.splitlines()

    # Method `HMIMachine.run()`:
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

    # Method `HMIMachine.pause()`:
    def pause(self) -> None:
        """Pause the running program."""
        self.log.append("pause")
        if self.lcnc is not None:
            self.lcnc.call("command.auto", constant("AUTO_PAUSE"))

    # Method `HMIMachine.resume()`:
    def resume(self) -> None:
        """Resume a paused program.

        It is in `MODE_AUTO` already; setting that again can end the
        program, with no message, so the mode is left alone.
        """
        self.log.append("resume")
        if self.lcnc is not None:
            self.lcnc.call("command.auto", constant("AUTO_RESUME"))

    # Method `HMIMachine.stop()`:
    def stop(self) -> None:
        """Stop at once (`command.abort()`), with any MDI lines waiting."""
        self.log.append("stop")
        self.mdi_lines.clear()
        if self.lcnc is not None:
            self.lcnc.call("command.abort")
            self.lcnc.call("command.wait_complete")

    # Method `HMIMachine.mdi()`:
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

    # Method `HMIMachine.set_origin()`:
    def set_origin(self) -> None:
        """Make the current position the program's zero (G54)."""
        self.mdi("G10 L20 P1 X0 Y0 Z0")

    # Method `HMIMachine.jog()`:
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

    # Method `HMIMachine.go_origin()`:
    def go_origin(self, z: float) -> None:
        """Rapid to the work origin, never moving sideways below Z0.

        Arguments:
        * `z` (`float`): The work Z now (inches).
        """
        self.mdi(f"G20 G90 G0 Z{max(z, 0.0):.4f}", "G0 X0 Y0", "G0 Z0")

    # Method `HMIMachine.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override.

        Arguments:
        * `speed` (`float`):
          The feed override (1.0 is the programmed feed).
        """
        self.log.append(f"speed {speed:.2f}")
        if self.lcnc is not None:
            self.lcnc.call("command.feedrate", speed)

    # Method `HMIMachine.top_z()`:
    def top_z(self) -> float:
        """Return the highest work Z the tool's tip can reach.

        Returns:
        * (`float`): Z's upper travel limit less the G5x, G92 and tool
          length offsets (inches).
        """
        stat: dict[str, Any] = cast(BridgeClient, self.lcnc).stat(
            "axis", "g5x_offset", "g92_offset", "tool_offset"
        )
        return float(
            stat["axis"][2]["max_position_limit"]
            - stat["g5x_offset"][2]
            - stat["g92_offset"][2]
            - stat["tool_offset"][2]
        )

    # Method `HMIMachine._read_messages()`:
    def _read_messages(self) -> list[str]:
        """Read LinuxCNC's new messages, and keep them.

        Returns:
        * (`list[str]`): The new messages.
        """
        lcnc: BridgeClient = cast(BridgeClient, self.lcnc)
        messages: list[str] = []
        error: Any = lcnc.call("error_channel.poll")
        while error:
            # An `(MSG, ...)` comes with the space after its comma.
            messages.append(str(error[1]).strip())
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

    # Method `HMIMachine._next_mdi()`:
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
        lcnc: BridgeClient = cast(BridgeClient, self.lcnc)
        if messages:
            self.mdi_lines.clear()
        if not self.mdi_lines:
            return False
        if idle and lcnc.call("command.wait_complete", 0) != -1:
            lcnc.call("command.mdi", self.mdi_lines.pop(0))
        return True

    # Method `HMIMachine.status()`:
    def status(self) -> HMIStatus:
        """Poll LinuxCNC, and start the next MDI line when it is time.

        Returns:
        * (`HMIStatus`): The program, line, position, tool and messages.
        """
        if self.lcnc is None:
            return HMIStatus(self.file, 0, (0.0, 0.0, 0.0), 0, [], "")
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
        return HMIStatus(
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


# Class `CommandPort`:
class CommandPort:  # pylint: disable=too-few-public-methods
    """A command port on 127.0.0.1: one line in, one line back.

    Attributes:
    * `server` (`socket.socket`): The listening socket (not blocking).
    """

    # Method `CommandPort.__init__()`:
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

    # Method `CommandPort.poll()`:
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


# Function `program_inches()`:
def program_inches(lines: list[str]) -> bool:
    """Return whether a program works in inches (its first `G20`/`G21`).

    Arguments:
    * `lines` (`list[str]`): The program.

    Returns:
    * (`bool`): True for `G20` first, False for `G21` or neither.
    """
    line: str
    for line in lines:
        found: re.Match[str] | None = UNITS.search(COMMENT.sub("", line))
        if found is not None:
            return found.group(1) == "20"
    return False


# Function `origin_lines()`:
def origin_lines(point: Point, inches: bool) -> list[str]:
    """Return the MDI lines that make the tool tip read a point.

    Arguments:
    * `point` (`Point`): Where the tool tip is, in work coordinates
      (millimeters).
    * `inches` (`bool`): True for a program in inches.

    Returns:
    * (`list[str]`): The units word, then `G10 L20 P1` for G54.
    """
    scale: float = 1.0 / 25.4 if inches else 1.0
    places: int = 4 if inches else 3
    x, y, z = (round(value * scale, places) + 0.0 for value in point)
    return [
        "G20" if inches else "G21",
        f"G10 L20 P1 X{x:.{places}f} Y{y:.{places}f} Z{z:.{places}f}",
    ]


# Function `ask_choice()`:
def ask_choice(
    root: tk.Tk, title: str, message: str, choices: list[str]
) -> str:
    """Ask the operator to pick one of a list, in a window of its own.

    Arguments:
    * `root` (`tk.Tk`): The HMI's window.
    * `title` (`str`): The window's title.
    * `message` (`str`): The question.
    * `choices` (`list[str]`): What may be picked.

    Returns:
    * (`str`): The choice, or `""` for Cancel.
    """
    if tk is lcnc_hmi_headless:
        return lcnc_hmi_headless.askchoice(title, message, choices)

    # A small window: the question, the list, OK and Cancel.
    window: tk.Toplevel = tk.Toplevel(root)
    window.title(title)
    ttk.Label(window, text=message).pack(padx=8, pady=4)
    chosen: tk.StringVar = tk.StringVar(value="")
    picker: ttk.Combobox = ttk.Combobox(
        window, values=choices, state="readonly", width=40
    )
    picker.pack(padx=8, pady=4)
    buttons: ttk.Frame = ttk.Frame(window)
    buttons.pack(pady=4)

    def done() -> None:
        """Keep the choice, and close the window."""
        chosen.set(picker.get())
        window.destroy()

    ttk.Button(buttons, text="OK", command=done).pack(side="left")
    ttk.Button(buttons, text="Cancel", command=window.destroy).pack(
        side="left"
    )
    window.transient(root)
    window.grab_set()
    root.wait_window(window)
    return chosen.get()


# Class `View`:
class View(Protocol):  # pylint: disable=too-few-public-methods
    """What shows an assembly (`setup_view.SetupView`, or a fake).

    Attributes:
    * `hidden` (`set[str]`): What to hide (`setup_view.HIDEABLE`).
    * `keep_outs` (`bool`): True to show the items' keep-outs too.
    * `progress` (`tuple[int, int]`): Changes done, of how many.
    """

    hidden: set[str]
    keep_outs: bool
    progress: tuple[int, int]

    # Method `View.show()`:
    def show(self, assembly: Assembly) -> None:
        """Show an assembly.

        Arguments:
        * `assembly` (`Assembly`): The items, bottom first.
        """


# Class `SetupDrawer`:
@dataclass(slots=True)
class SetupDrawer:
    """Draws setups one at a time, on a thread, the newest first.

    A setup handed in while another is drawn waits; a newer one
    replaces it, so only the newest is drawn next.  Tk is not thread
    safe, so errors wait in `errors` for the HMI's poll.

    Attributes:
    * `view` (`View`): What draws an assembly; kept for the whole
      run, so a new setup changes only what differs (`T.emsagc~5.2`
      #68).
    * `busy` (`bool`): True while the thread is drawing.
    * `hidden` (`set[str]`): What the next drawing hides (it draws
      the keep-outs always, so they can be shown without a redraw).
    * `errors` (`queue.SimpleQueue[str]`): Messages for the HMI.
    * `lock` (`threading.Lock`): Guards `busy`, `pending`, `thread`.
    * `pending` (`Assembly | None`): The next setup to draw.
    * `thread` (`threading.Thread | None`): The drawing thread.

    Constructor:
    * `SetupDrawer(view)`
    """

    # Constructor arguments:
    view: View = field(init=True)

    # Remaining attributes (alphabetized):
    busy: bool = field(init=False, default=False)
    hidden: set[str] = field(
        init=False,
        default_factory=lambda: {
            kind for _, kind, shown in TOGGLES if not shown
        },
    )
    errors: "queue.SimpleQueue[str]" = field(
        init=False, default_factory=queue.SimpleQueue
    )
    lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    pending: Assembly | None = field(init=False, default=None)
    thread: threading.Thread | None = field(init=False, default=None)

    # Method `SetupDrawer.draw()`:
    def draw(self, assembly: Assembly) -> None:
        """Draw a setup when the thread is free, dropping older ones.

        Arguments:
        * `assembly` (`Assembly`): The setup to draw.
        """
        with self.lock:
            self.pending = assembly
            if not self.busy:
                self.busy = True
                self.thread = threading.Thread(
                    target=self.work, name="setup drawer", daemon=True
                )
                self.thread.start()

    # Method `SetupDrawer.work()`:
    def work(self) -> None:
        """Draw the pending setups until there are none (the thread)."""
        while True:
            # Take the newest setup, or stop when there is none.
            assembly: Assembly | None
            with self.lock:
                assembly = self.pending
                self.pending = None
                if assembly is None:
                    self.busy = False
                    return

            # Draw it; any error goes to the HMI.
            try:
                self.view.keep_outs = True
                self.view.hidden = set(self.hidden)
                self.view.show(assembly)
            # pylint: disable-next=broad-exception-caught
            except Exception as error:  # noqa: BLE001
                self.errors.put(f"Setup not drawn: {error}")

    # Method `SetupDrawer.wait()`:
    def wait(self) -> None:
        """Wait until every setup handed in is drawn (for tests)."""
        while True:
            thread: threading.Thread | None
            with self.lock:
                thread = self.thread if self.busy else None
            if thread is None:
                return
            thread.join()

    # Method `SetupDrawer.message()`:
    def message(self) -> str:
        """Return the newest error message, or "" when there is none.

        Returns:
        * (`str`): The message.
        """
        text: str = ""
        while not self.errors.empty():
            text = self.errors.get()
        return text


# Class `HMI`:
# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class HMI:
    """The HMI window, laid out as in `T.mlcp~3.4`.

    Attributes:
    * `coming` (`tk.Text`): The G-code coming next (read only).
    * `inches` (`bool`): True when the open program is in inches.
    * `assembly` (`Assembly | None`): The open program's setup.
    * `next_step_button` (`ttk.Button`): Shows the setup's next item.
    * `note` (`str`): The setup step shown, kept ahead of any error.
    * `drawing` (`bool`): True while a setup is drawn (Start is
      greyed out).
    * `progress` (`ttk.Progressbar`): How much of the setup is drawn.
    * `drawn` (`Assembly | None`): The setup (or the steps of it)
      last handed to `drawer`.
    * `toggles` (`dict[str, tk.BooleanVar]`): The View tab's check
      buttons' states, by label (`TOGGLES`).
    * `setup_step` (`int`): How many of the setup's items Next Step
      has shown (0: the whole setup).
    * `origins` (`list[tuple[str, Point]]`): The open program's
      setup's named origins (work millimeters), or none.
    * `drawer` (`SetupDrawer | None`): What draws an opened
      program's setup in SolidCraft, or `None` to draw nothing.
    * `execute_button` (`ttk.Button`): Runs the MDI line.
    * `executed` (`tk.Text`): The G-code already run (read only).
    * `home_button` (`ttk.Button`): Rapids to the work origin.
    * `jog_buttons` (`list[ttk.Button | tk.Radiobutton]`): -X, +X,
      -Y, +Y, -Z, +Z, and the step buttons.
    * `lines` (`list[str]`): The open program's lines.
    * `lines_file` (`str`): The file `lines` was read from.
    * `machine` (`HMIMachine`): The LinuxCNC back end.
    * `mdi` (`tk.StringVar`): The MDI line's text.
    * `mdi_entry` (`tk.Entry`): The MDI line, colored as it is typed.
    * `message` (`ttk.Label`): LinuxCNC's last error message.
    * `origin_button` (`ttk.Button`): The Set Origin button.
    * `paused` (`bool`): True while the program is paused.
    * `pause_button` (`ttk.Button`): The Pause button.
    * `port` (`CommandPort | None`): The command port, if any.
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
    * `material` (`tk.StringVar`): The material the Tools tab shows.
    * `material_chooser` (`ttk.Combobox`): Chooses that material.
    * `next_tool` (`ttk.Label`): Room for the next tool and the time
      left to it (`T.hs~5.1.5` S6).
    * `notebook` (`ttk.Notebook`): The tabs.
    * `operator_paused` (`bool`): True while paused by Pause (not by
      the program's own `M0`).
    * `axes_set` (`set[str]`): The axes whose origin is set since the
      program was opened.
    * `axis_buttons` (`dict[str, ttk.Button]`): Set X, Set Y, Set Z.
    * `axis_entries` (`dict[str, tk.Entry]`): Their numbers' entries.
    * `axis_texts` (`dict[str, tk.StringVar]`): The numbers typed.
    * `jog_note` (`str`): Why jogs are not checked, once said.
    * `last_tool` (`int`): The tool in the spindle at the last poll.
    * `jog_refusal` (`str`): Why the last jog was refused (`""` when
      it was not).
    * `tool_radii` (`dict[int, float]`): Each tool's widest radius,
      by its number.
    * `zones` (`list[RoundedPolygon] | None`): The setup's keep-outs
      (work inches), `None` without a setup.
    * `override` (`float`): The feed override (the speed slider).
    * `rapid` (`float`): How fast a rapid goes (inches per minute).
    * `spans` (`list[tuple[int, int]]`): The program's tool changes
      (`change_spans()`).
    * `sums` (`list[float]`): Minutes up to each line of the program
      (`time_program()`).
    * `origin_set` (`bool`): True once the open program's origin is
      set (`mark_origin_set()`); Start waits for it.
    * `program_machine` (`str`): The machine the program is for.
    * `program_material` (`str`): The material it cuts.
    * `tabs` (`dict[str, ttk.Frame]`): Each tab, by its name.
    * `tools_table` (`tk.Text`): The tools' speeds and feeds.
    """

    # Method `HMI.__init__()`:
    # pylint: disable-next=too-many-locals,too-many-statements
    def __init__(
        self,
        root: tk.Tk,
        machine: HMIMachine,
        max_speed: float,
        port: CommandPort | None,
    ) -> None:
        """Build the window.

        It lays the whole window out in one place, so it has many
        locals and statements.

        Arguments:
        * `root` (`tk.Tk`):
          The window to build in.
        * `machine` (`HMIMachine`):
          The LinuxCNC back end.
        * `max_speed` (`float`):
          The speed slider's highest setting.
        * `port` (`CommandPort | None`):
          The command port, if any.
        """
        self.root: tk.Tk = root
        self.machine: HMIMachine = machine
        self.port: CommandPort | None = port
        self.paused: bool = False
        self.running: bool = False
        self.start: int = 0
        self.lines: list[str] = []
        self.lines_file: str = ""
        self.scrolling: bool = False
        self.drawer: SetupDrawer | None = None
        self.origins: list[tuple[str, Point]] = []
        self.inches: bool = False
        self.assembly: Assembly | None = None
        self.setup_step: int = 0
        self.note: str = ""
        self.drawn: Assembly | None = None
        self.drawing: bool = False
        self.program_material: str = MATERIAL
        self.program_machine: str = SHOP_MACHINE
        self.origin_set: bool = False
        self.operator_paused: bool = False
        self.override: float = 1.0
        self.zones: list[RoundedPolygon] | None = None
        self.tool_radii: dict[int, float] = {}
        self.jog_note: str = ""
        self.last_tool: int = 0
        self.jog_refusal: str = ""
        self.rapid: float = machine.rapid_speed()
        self.sums: list[float] = [0.0]
        self.spans: list[tuple[int, int]] = []
        root.title("SolidCraft LinuxCNC")

        # Above the tabs, on every tab: the work position and the tool,
        # LinuxCNC's messages, and how much of the setup is drawn.
        self.position: ttk.Label = ttk.Label(root, font="TkFixedFont")
        self.position.grid(row=0, column=0, padx=4, sticky="w")
        self.message: ttk.Label = ttk.Label(root, foreground="red")
        self.message.grid(row=1, column=0, padx=4, sticky="w")
        self.progress: ttk.Progressbar = ttk.Progressbar(
            root, length=120, maximum=1, value=0
        )
        self.progress.grid(row=1, column=0, padx=4, sticky="e")

        # The tabs, one for each task, in the order of `TABS`.
        self.notebook: ttk.Notebook = ttk.Notebook(root)
        self.notebook.grid(row=2, column=0, padx=4, pady=2, sticky="nsew")
        self.tabs: dict[str, ttk.Frame] = {}
        for name in TABS:
            self.tabs[name] = ttk.Frame(self.notebook)
            self.notebook.add(self.tabs[name], text=name)
        self.notebook.bind(
            "<<NotebookTabChanged>>", lambda _event: self.on_tab_changed()
        )
        run_tab: ttk.Frame = self.tabs["Run"]

        # Run: the G-code run and coming, and below them the MDI line
        # and Execute.
        self.executed: tk.Text = self.scrolled_text(run_tab)
        self.coming: tk.Text = self.scrolled_text(run_tab)
        mdi: ttk.Frame = ttk.Frame(run_tab)
        mdi.pack(fill="x", padx=4, pady=2)
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

        # Run: the run line, -Tool and +Tool, Start, Pause and Reset.
        buttons: ttk.Frame = ttk.Frame(run_tab)
        buttons.pack(pady=(6, 2))
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

        # Run: the speed slider (logarithmic), and room for the next
        # tool and the time left (`T.hs~5.1.5` S6).
        self.speed: tk.DoubleVar = tk.DoubleVar(value=0.0)
        self.speed_text: tk.StringVar = tk.StringVar(value="1x")
        self.top_speed: float = min(max_speed, MAX_SPEED)
        slider: ttk.Frame = ttk.Frame(run_tab)
        slider.pack(fill="x", pady=4)
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
        self.next_tool: ttk.Label = ttk.Label(run_tab, text="")
        self.next_tool.pack(anchor="w", padx=4)

        # Setup: Next Step, Set Origin and Home.
        setup_tab: ttk.Frame = self.tabs["Setup"]
        setup_line: ttk.Frame = ttk.Frame(setup_tab)
        setup_line.pack(pady=(6, 2))
        self.next_step_button: ttk.Button = ttk.Button(
            setup_line, text="Next Step", command=self.on_next_step
        )
        self.next_step_button.pack(side="left", padx=(1, 12))
        self.origin_button: ttk.Button = ttk.Button(
            setup_line, text="Set Origin", command=self.on_set_origin
        )
        self.home_button: ttk.Button = ttk.Button(
            setup_line, text="Home", width=5, command=self.on_home
        )
        self.origin_button.pack(side="left", padx=1)
        self.home_button.pack(side="left", padx=1)

        # Setup: each axis of the origin set by hand, to a number.
        axis_line: ttk.Frame = ttk.Frame(setup_tab)
        axis_line.pack(pady=2)
        self.axis_texts: dict[str, tk.StringVar] = {}
        self.axis_entries: dict[str, tk.Entry] = {}
        self.axis_buttons: dict[str, ttk.Button] = {}
        self.axes_set: set[str] = set()
        axis: str
        for axis in AXES:
            self.axis_texts[axis] = tk.StringVar()
            self.axis_entries[axis] = tk.Entry(
                axis_line,
                textvariable=self.axis_texts[axis],
                width=9,
                font="TkFixedFont",
                background=BLANK,
            )
            self.axis_entries[axis].pack(side="left", padx=(8, 1))
            self.axis_buttons[axis] = ttk.Button(
                axis_line,
                text=f"Set {axis}",
                width=6,
                state="disabled",
                command=functools.partial(self.on_set_axis, axis),
            )
            self.axis_buttons[axis].pack(side="left", padx=1)
            self.axis_texts[axis].trace_add(
                "write", lambda *_: self.check_axes()
            )

        # Setup: the jog buttons and their step (one chosen at a time).
        jog_line: ttk.Frame = ttk.Frame(setup_tab)
        jog_line.pack(pady=(2, 6))
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
        for index, jog in enumerate(self.jog_buttons):
            jog.pack(side="left", padx=(12 if index == 6 else 1, 1))

        # Tools: a material, and the tools' speeds and feeds for it
        # (filled each time the tab is shown).
        tools_tab: ttk.Frame = self.tabs["Tools"]
        self.material: tk.StringVar = tk.StringVar(value=MATERIAL)
        self.material_chooser: ttk.Combobox = ttk.Combobox(
            tools_tab, textvariable=self.material, state="readonly", width=30
        )
        self.material_chooser.pack(anchor="w", padx=4, pady=4)
        self.material_chooser.bind(
            "<<ComboboxSelected>>", lambda _event: self.show_tools()
        )
        self.tools_table: tk.Text = tk.Text(
            tools_tab, width=72, height=12, font="TkFixedFont"
        )
        self.tools_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # View: what SolidCraft shows.
        self.toggles: dict[str, tk.BooleanVar] = {}
        label: str
        shown: bool
        for label, _, shown in TOGGLES:
            self.toggles[label] = tk.BooleanVar(value=shown)
            ttk.Checkbutton(
                self.tabs["View"],
                text=label,
                variable=self.toggles[label],
                command=self.on_toggle,
            ).pack(anchor="w", padx=4, pady=2)

        # Under the tabs, for every task: Open and Quit.
        bottom: ttk.Frame = ttk.Frame(root)
        bottom.grid(row=3, column=0, pady=4, sticky="e")
        ttk.Button(bottom, text="Open", command=self.on_open).pack(
            side="left", padx=1
        )
        ttk.Button(bottom, text="Quit", command=root.destroy).pack(
            side="left", padx=(12, 4)
        )
        root.after(POLL_MS, self.poll)

    # Method `HMI.scrolled_text()`:
    @staticmethod
    def scrolled_text(parent: ttk.Frame) -> tk.Text:
        """Make a read only text window with a scroll bar.

        Arguments:
        * `parent` (`ttk.Frame`): The tab to put it in, under what
          is there already.

        Returns:
        * (`tk.Text`): The text window.
        """
        frame: ttk.Frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=4, pady=2)
        text: tk.Text = tk.Text(frame, height=SHOWN, width=50)
        scroll: ttk.Scrollbar = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set, state="disabled")
        text.pack(side="left", fill="x", expand=True)
        scroll.pack(side="left", fill="y")
        return text

    # Method `HMI.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override, the slider and the number shown.

        Arguments:
        * `speed` (`float`): The feed override, kept within the
          slider's range.
        """
        speed = min(max(speed, MIN_SPEED), self.top_speed)
        self.override = speed
        self.speed.set(math.log10(speed))
        self.speed_text.set(f"{speed:.2g}x")
        self.machine.set_speed(speed)

    # Method `HMI.set_text()`:
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

    # Method `HMI.set_running()`:
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
            state="disabled"
            if (running and not paused) or self.drawing or not self.origin_set
            else "normal",
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
        self.check_axes()

    # Method `HMI.check_mdi()`:
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

    # Method `HMI.open()`:
    def open(self, path: str) -> None:
        """Open a program.

        Arguments:
        * `path` (`str`): The G-code file.

        Raises:
        * `ValueError`: If its setup is for another shop or machine.
        * `FileNotFoundError`: If there is no such file.
        """
        # A program for another shop or machine is refused, and the
        # one open before stays open.
        try:
            assembly: Assembly | None = read_file(path)
        except (OSError, ValueError):
            assembly = None  # `open_setup()` reports it.
        if assembly is not None:
            refusal: str = setup_warning(assembly, shop_name())
            if refusal:
                self.message.configure(text=refusal)
                raise ValueError(refusal)

        # Open it; it may not run until its origin is set.
        self.machine.open(path)
        self.start = 0
        self.lines_file = ""  # Read it again, even when the same file.
        self.message.configure(text="")
        self.origin_set = False
        self.zones = None
        self.jog_note = ""
        self.set_running(False, False)
        self.open_setup(path)
        self.mark_origin_set(self.origin_set)

    # Method `HMI.time_program()`:
    def time_program(self) -> None:
        """Time the program's lines, once per program read."""
        self.spans = change_spans(self.lines)
        self.sums = [0.0]
        minutes: float
        for minutes in line_minutes(self.lines, self.rapid):
            self.sums.append(self.sums[-1] + minutes)

    # Method `HMI.mark_origin_set()`:
    def mark_origin_set(self, origin_set: bool = True) -> None:
        """Mark whether the open program's origin is set.

        The one place the mark is set: Start stays greyed out until it
        is, and the message line says so.

        Arguments:
        * `origin_set` (`bool`): True once G54 is set for the program.
        """
        self.origin_set = origin_set
        self.axes_set = set(AXES) if origin_set else set()
        first: str = "Set the origin first"
        if not origin_set and not str(self.message.cget("text")):
            self.message.configure(text=first)
        elif origin_set and str(self.message.cget("text")).startswith(
            (first, "Origin still to set")
        ):
            self.message.configure(text="")
        self.set_running(self.running, self.paused)

    # Method `HMI.check_axes()`:
    def check_axes(self) -> None:
        """Color each axis entry, and grey out its button unless usable.

        A button can be pressed only while stopped, with a number in
        its entry.
        """
        axis: str
        for axis in AXES:
            text: str = self.axis_texts[axis].get().strip()
            number: bool = True
            try:
                float(text)
            except ValueError:
                number = False
            self.axis_entries[axis].configure(
                background=BLANK if not text else GOOD if number else BAD
            )
            self.axis_buttons[axis].configure(
                state="normal" if number and not self.running else "disabled"
            )

    # Method `HMI.on_set_axis()`:
    def on_set_axis(self, axis: str) -> None:
        """Make the current position on one axis read the number typed.

        It asks first (No is the default), as setting the origin on a
        real machine is a big deal.

        Arguments:
        * `axis` (`str`): `X`, `Y` or `Z`.
        """
        if self.running:
            return
        try:
            value: float = float(self.axis_texts[axis].get())
        except ValueError:
            return
        lines: list[str] = [
            "G20" if self.inches else "G21",
            f"G10 L20 P1 {axis}{value:g}",
        ]
        if not messagebox.askyesno(
            f"Set {axis}",
            f"Make the current {axis} read {value:g}: run {lines[-1]}?",
            default="no",
        ):
            return
        try:
            self.machine.mdi(*lines)
        except RuntimeError as error:
            self.message.configure(text=str(error))
            return

        # All three axes set, one by one, make the origin set.
        self.axes_set.add(axis)
        if self.axes_set == set(AXES):
            self.mark_origin_set()
        else:
            left: str = " ".join(a for a in AXES if a not in self.axes_set)
            self.message.configure(text=f"Origin still to set: {left}")

    # Method `HMI.use_setup()`:
    def use_setup(self, assembly: Assembly) -> None:
        """Take a setup's material, origins, and drawing.

        Arguments:
        * `assembly` (`Assembly`): The program's setup.
        """
        # The shop, so that its machine and materials can be checked.
        try:
            shop: dict[str, object] = shops.read(SHOP_FILE)
        except ValueError as error:
            self.message.configure(text=f"Shop not read: {error}")
            shop = {}
        self.program_material = (
            setup_material(assembly, material_names(shop)) or MATERIAL
        )

        # Its origin, when the shop places the machine's table (`open()`
        # has refused a program for another shop or machine).
        self.program_machine = assembly.machine or SHOP_MACHINE
        origin: tuple[float, float, float] | None = setup_origin(
            assembly, shop, SHOP_MACHINE
        )
        if origin is not None:
            if self.machine.set_work_origin(origin):
                self.origin_set = True
            else:
                self.message.configure(
                    text="Origin not set: a program is running"
                )

        # Its keep-outs and its tools' radii, for checking jogs.
        try:
            self.zones = assembly_zones(assembly)
            self.tool_radii = {
                tool.number: tool.widest_radius()
                for tool in shops.cnc_machine(
                    shop, SHOP_MACHINE, self.program_material
                ).tools
            }
        except (ValueError, KeyError) as error:
            self.zones = None
            self.message.configure(text=f"Setup keep-outs: {error}")

        # Its origins, for Set Origin, then its drawing.
        try:
            self.origins = named_origins(assembly)
        except ValueError as error:
            self.message.configure(text=f"Setup origins: {error}")
        if self.drawer is not None:
            self.drawn = assembly
            self.drawer.draw(assembly)
            self.drawing = True
            self.set_running(self.running, self.paused)

    # Method `HMI.load_tools()`:
    def load_tools(self) -> None:
        """Send the tool table for the program's material, if idle."""
        self.material.set(self.program_material)
        try:
            if not self.machine.write_tool_table(self.program_material):
                self.message.configure(
                    text="Tool table not sent: a program is running"
                )
        except (ValueError, RuntimeError, BridgeError) as error:
            self.message.configure(text=f"Tool table: {error}")

    # Method `HMI.open_setup()`:
    def open_setup(self, path: str) -> None:
        """Take a program's setup (its `SCC:` lines), if it has one.

        A program with no setup is run as is (`T.emsagc~5.2` #17); a
        wrong setup is reported, and the program is still open.  Either
        way the tool table is sent again, for the setup's material, or
        `MATERIAL` without one.

        Arguments:
        * `path` (`str`): The G-code file.
        """
        self.origins = []
        self.assembly = None
        self.setup_step = 0
        self.note = ""
        self.program_material = MATERIAL
        self.program_machine = SHOP_MACHINE
        try:
            assembly: Assembly | None = read_file(path)
            text: str = Path(path).read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            self.load_tools()
            self.message.configure(text=f"Setup not read: {error}")
            return
        self.inches = program_inches(text.splitlines())
        if assembly is not None:
            self.assembly = assembly
            self.use_setup(assembly)
        self.load_tools()

    # Method `HMI.on_open()`:
    def on_open(self) -> None:
        """Choose a program with a file window, and open it."""
        path: str = filedialog.askopenfilename(
            title="Open G-code",
            filetypes=[("G-code", "*.ngc *.nc *.gcode"), ("All", "*")],
        )
        if path:
            try:
                self.open(path)
            except (ValueError, OSError) as error:
                self.message.configure(text=str(error))

    # Method `HMI.show_tools()`:
    def show_tools(self) -> None:
        """Fill the Tools tab: the tools' speeds and feeds."""
        # The shop is read again each time, so edits to it show.
        text: str
        try:
            shop: dict[str, object] = shops.read(SHOP_FILE)
        except ValueError as error:
            text = f"The shop could not be read:\n{error}"
        else:
            self.material_chooser.configure(values=material_names(shop))
            text = tool_speeds(shop, SHOP_MACHINE, self.material.get())
        self.tools_table.configure(state="normal")
        self.tools_table.delete("1.0", "end")
        self.tools_table.insert("1.0", text)
        self.tools_table.configure(state="disabled")

    # Method `HMI.tab()`:
    def tab(self) -> str:
        """Return the name of the tab shown.

        Returns:
        * (`str`): One of `TABS`.
        """
        # `typeshed` leaves `Notebook.index()` untyped.
        current: int = self.notebook.index(  # type: ignore[no-untyped-call]
            "current"
        )
        return TABS[current]

    # Method `HMI.select_tab()`:
    def select_tab(self, name: str) -> None:
        """Show a tab, as a person clicking it would.

        Arguments:
        * `name` (`str`): One of `TABS`.

        Raises:
        * `ValueError`: When there is no such tab.
        """
        if name not in self.tabs:
            raise ValueError(f"no tab {name} (tabs: {', '.join(TABS)})")
        # `typeshed` leaves `Notebook.select()` untyped.
        self.notebook.select(  # type: ignore[no-untyped-call]
            self.tabs[name]
        )
        if tk is lcnc_hmi_headless:
            self.on_tab_changed()

    # Method `HMI.on_tab_changed()`:
    def on_tab_changed(self) -> None:
        """Bring the tab just shown up to date."""
        if self.tab() == "Tools":
            self.show_tools()

    # Method `HMI.on_run()`:
    def on_run(self) -> None:
        """Run the program, or resume it after a pause."""
        self.message.configure(text="")
        self.operator_paused = False
        if self.paused:
            self.machine.resume()
        else:
            self.machine.run(self.start)
        self.set_running(True, False)

    # Method `HMI.on_pause()`:
    def on_pause(self) -> None:
        """Pause the program; the editable lines may then be run."""
        self.operator_paused = True
        self.machine.pause()
        self.set_running(True, True)

    # Method `HMI.on_tool()`:
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

    # Method `HMI.on_execute()`:
    def on_execute(self) -> None:
        """Run the MDI line."""
        try:
            self.machine.mdi(self.mdi.get().strip())
        except RuntimeError as error:
            self.message.configure(text=str(error))

    # Method `HMI.on_stop()`:
    def on_stop(self) -> None:
        """Stop at once, ready to run again from the program's start."""
        self.message.configure(text="")
        self.operator_paused = False
        self.machine.stop()
        self.start = 0
        self.set_running(False, False)

    # Method `HMI.on_jog()`:
    def on_jog(self, axis: int, direction: int) -> None:
        """Jog one axis by the chosen step.

        Arguments:
        * `axis` (`int`): The axis: 0 for X, 1 for Y, 2 for Z.
        * `direction` (`int`): +1 or -1.
        """
        step: float = float(self.step.get())
        self.jog_refusal = ""

        # Keep-outs mean something only with a setup and its origin.
        unchecked: str = (
            "no setup"
            if self.zones is None
            else "origin not set"
            if not self.origin_set
            else ""
        )
        if unchecked:
            if unchecked != self.jog_note:
                self.jog_note = unchecked
                self.message.configure(text=f"Jogs not checked: {unchecked}")
            self.machine.jog(axis, direction, step)
            return

        # A jog that would enter a keep-out is refused, not shortened.
        status: HMIStatus = self.machine.status()
        start: tuple[float, float, float] = status.position
        end: list[float] = list(start)
        end[axis] += direction * step
        x, y, z = end
        hit: str = jog_hit(
            self.zones or [],
            start,
            (x, y, z),
            self.tool_radii.get(status.tool, 0.0),
        )
        if hit:
            self.jog_refusal = (
                f"Jog refused: it would enter {hit}; choose a smaller "
                "step and try again"
            )
            self.message.configure(text=self.jog_refusal)
            return
        self.machine.jog(axis, direction, step)

    # Method `HMI.on_home()`:
    def on_home(self) -> None:
        """Rapid to the work origin."""
        try:
            self.machine.go_origin(self.machine.status().position[2])
        except RuntimeError as error:
            self.message.configure(text=str(error))

    # Method `HMI.on_set_origin()`:
    def on_set_origin(self) -> None:
        """Make the current position zero, after asking (No first).

        With a setup, the operator first picks which of its origins the
        tool tip is at, and the position is made to read that point.
        """
        if self.origins:
            self.set_named_origin()
            return
        if messagebox.askyesno(
            "Set Origin",
            "Make the current position the program's zero?",
            default="no",
        ):
            try:
                self.machine.set_origin()
            except RuntimeError as error:
                self.message.configure(text=str(error))
            else:
                self.mark_origin_set()

    # Method `HMI.on_next_step()`:
    def on_next_step(self) -> None:
        """Show the setup's next item, with its note (`T.emsagc~5.2` #14).

        Step N draws items 1 to N only, so each step adds one item;
        the step after the last shows the whole setup again.
        """
        if self.assembly is None:
            self.message.configure(text="This program has no setup.")
            return
        items: list[AssemblyItem] = self.assembly.items
        self.setup_step += 1
        shown: Assembly
        if self.setup_step > len(items):
            self.setup_step = 0
            shown = self.assembly
            text: str = f"Setup: all {len(items)} items."
        else:
            item: AssemblyItem = items[self.setup_step - 1]
            shown = Assembly(items[: self.setup_step])
            text = (
                f"Step {self.setup_step}/{len(items)}, "
                f"{item.name.replace('_', ' ')}: {item.note}"
            )
        self.note = text
        self.message.configure(text=text)
        if self.drawer is not None:
            self.drawn = shown
            self.drawer.draw(shown)

    # Method `HMI.on_toggle()`:
    def on_toggle(self) -> None:
        """Show or hide what the View tab's toggles say.

        Only visibility changes (`SetupView.apply_hidden()`); the
        setup is not drawn again, as nothing in it differs.  A drawing
        made later (Next Step, a new open) keeps the same choices.
        """
        if self.drawer is None:
            self.message.configure(text="No SolidCraft to show them in.")
            return
        self.drawer.hidden = {
            kind
            for label, kind, _ in TOGGLES
            if not bool(self.toggles[label].get())
        }
        if self.drawn is not None:
            self.drawer.draw(self.drawn)

    # Method `HMI.set_named_origin()`:
    def set_named_origin(self) -> None:
        """Pick the origin the tool tip is at, confirm, and set G54."""
        names: list[str] = [name for name, _ in self.origins]
        picked: str = ask_choice(
            self.root, "Set Origin", "Where is the tool tip now?", names
        )
        if not picked:
            return
        point: Point = dict(self.origins)[picked]
        lines: list[str] = origin_lines(point, self.inches)
        if messagebox.askyesno(
            "Set Origin",
            f"The tool tip is at {picked}: run {lines[-1]}?",
            default="no",
        ):
            try:
                self.machine.mdi(*lines)
            except RuntimeError as error:
                self.message.configure(text=str(error))
            else:
                self.mark_origin_set()

    # Method `HMI.widgets()`:
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

    # Method `HMI.press()`:
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
                self.jog_refusal = ""
                widget.invoke()
                return (
                    f"error: {self.jog_refusal}" if self.jog_refusal else "ok"
                )
        return f"error: no button {label}"

    # Method `HMI.show()`:
    def show(self) -> dict[str, Any]:
        """Return what the window shows.

        Returns:
        * (`dict[str, Any]`): `executed` and `coming` (the G-code
          windows), `position`, `message`, `mdi` and `mdi_color` (the
          MDI line), `step` and `speed` (those shown), `buttons` (each
          button's state, by its text) and `texts` (the contents of
          every text window, such as Tools), and `drawing` (True while
          a setup is being drawn in SolidCraft) and `origins` (the
          setup's named origins, work millimeters) and `setup_step`
          (how many setup items Next Step shows; 0 for all),
          `origin_set` (True once the program's origin is set),
          `toggles` (each View toggle, True when shown), `axes_set`
          (the axes set one by one, or all), `axis_entries`
          (the numbers typed for them),
          `next_tool` (the next tool and the time left until it), and
          `tab` (the name of the tab shown).
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
            "drawing": self.drawer is not None and self.drawer.busy,
            "origins": dict(self.origins),
            "setup_step": self.setup_step,
            "origin_set": self.origin_set,
            "toggles": {
                label: bool(self.toggles[label].get())
                for label, _, _ in TOGGLES
            },
            "axes_set": sorted(self.axes_set),
            "axis_entries": {
                axis: self.axis_texts[axis].get() for axis in AXES
            },
            "next_tool": str(self.next_tool.cget("text")),
            "tab": self.tab(),
            "setup_progress": [
                int(float(self.progress.cget("value"))),
                int(float(self.progress.cget("maximum"))),
            ],
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

    # Method `HMI.handle()`:
    # A flat list of commands reads best, so it has many returns and
    # branches.
    # pylint: disable-next=too-many-return-statements,too-many-branches
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
            elif word == "origin" and rest:
                axis, _, value = rest.strip().partition(" ")
                if axis.upper() not in AXES:
                    return f"error: no axis {axis}"
                self.axis_texts[axis.upper()].set(value.strip())
            elif word == "tab" and rest:
                self.select_tab(rest.strip())
            elif word == "type":
                self.mdi.set(rest)
            elif word == "show":
                return json.dumps(self.show())
            elif word == "answer" and tk is lcnc_hmi_headless:
                lcnc_hmi_headless.ANSWERS.append(rest.strip())
            elif word == "open" and rest:
                self.open(rest.strip())
            elif word == "speed" and rest:
                self.set_speed(float(rest))
            elif word == "status":
                status: HMIStatus = self.machine.status()
                x, y, z = status.position
                return (
                    f"file={status.file} line={status.line} "
                    f"x={x:.4f} y={y:.4f} z={z:.4f} tool={status.tool} "
                    f"start={self.start} state={status.state}"
                )
            elif word == "messages":
                return f"messages: {' | '.join(self.machine.messages)}"
            elif word == "log":
                return f"log: {' | '.join(self.machine.log)}"
            else:
                return f"error: unknown command {line!r}"
        except (ValueError, OSError, BridgeError) as error:
            return f"error: {error}"
        return "ok"

    # Method `HMI.follow_tool()`:
    def follow_tool(self, tool: int) -> None:
        """Hide a newly drawn tool's holder, when holders are hidden.

        `sim_solidcraft.py` draws a tool when it is changed to, so on
        a change the setup goes to the drawer again, which changes
        nothing but the visibility (`SetupView.apply_hidden()`).

        Arguments:
        * `tool` (`int`): The tool in the spindle now.
        """
        if tool == self.last_tool:
            return
        self.last_tool = tool
        if (
            self.drawer is not None
            and self.drawn is not None
            and "holder" in self.drawer.hidden
        ):
            self.drawer.draw(self.drawn)

    # Method `HMI.poll()`:
    # One pass over everything the window shows, so many branches.
    def poll(self) -> None:  # pylint: disable=too-many-branches
        """Show the machine's state, answer the port, then poll again."""
        # While a setup is drawn, Start waits, and the bar shows how far.
        if self.drawer is not None:
            done, total = self.drawer.view.progress
            self.progress.configure(maximum=max(total, 1), value=done)
            if self.drawer.busy != self.drawing:
                self.drawing = self.drawer.busy
                self.set_running(self.running, self.paused)

        # A setup that could not be drawn (from the drawing thread).
        if self.drawer is not None:
            problem: str = self.drawer.message()
            if problem:
                # A step's note stays first, the error after it.
                self.message.configure(
                    text=f"{self.note} ({problem})" if self.note else problem
                )

        # A LinuxCNC that has gone is reported, while the port still
        # answers, and the window stays up to be read.
        try:
            status: HMIStatus = self.machine.status()
        except (OSError, BridgeError) as error:
            self.message.configure(text=f"LinuxCNC is not answering: {error}")
            if self.port is not None:
                self.port.poll(self.handle)
            self.root.after(POLL_MS, self.poll)
            return

        # The program around the line being run, read once per file.
        if status.file != self.lines_file:
            self.lines_file = status.file
            self.lines = self.machine.program_lines(status.file)
            self.time_program()
        # The buttons follow LinuxCNC's state (a program may end, or be
        # stopped, without the HMI).
        if status.state and (
            (status.state != "idle", status.state == "paused")
            != (self.running, self.paused)
        ):
            self.set_running(status.state != "idle", status.state == "paused")

        # A pause no one asked for is the program's (`M0`, at a tool
        # change; its `MSG` is on the message line).  A person presses
        # Start (Resume); with no one there (headless), it goes on.
        if (
            status.state == "paused"
            and not self.operator_paused
            and tk is lcnc_hmi_headless
        ):
            self.machine.resume()
            self.set_running(True, False)

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

        # Home only while stopped, away from the origin; Set Origin
        # also while this program's origin is not set yet.
        x, y, z = status.position
        away: bool = max(abs(x), abs(y), abs(z)) > AT_ORIGIN
        self.home_button.configure(
            state="normal" if away and not self.running else "disabled"
        )
        self.origin_button.configure(
            state="normal"
            if (away or not self.origin_set) and not self.running
            else "disabled"
        )

        # A tool drawn since (a tool change) follows the Holders toggle.
        self.follow_tool(status.tool)

        # The next tool, and the time left until it (cheap: the line
        # times are added up once per program).
        self.next_tool.configure(
            text=next_tool_text(
                self.lines,
                self.sums,
                self.spans,
                status.line if self.running else self.start,
                self.override,
            )
        )

        # The position, the tool and any message.
        self.position.configure(
            text=f"X {x:9.4f}  Y {y:9.4f}  Z {z:9.4f}  T{status.tool:02d}"
            f"  start line {self.start}  "
            f"{self.program_machine}, {self.program_material}"
        )
        if status.messages:
            self.message.configure(text=status.messages[-1])

        # Commands from the port.
        if self.port is not None:
            self.port.poll(self.handle)
        self.root.after(POLL_MS, self.poll)


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Show the HMI until its window is closed.

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
        "--solidcraft",
        type=int,
        help="a SolidCraft control port, to draw each program's setup",
    )
    parser.add_argument(
        "--shop",
        type=Path,
        default=SHOP_FILE,
        help="the shop's file (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="use no display or tkinter, for tests through --port",
    )
    options: argparse.Namespace = parser.parse_args(arguments)
    if options.headless:
        use_headless()
    elif tk is lcnc_hmi_headless:
        print("lcnc_hmi.py: tkinter is not installed.", file=sys.stderr)
        return 1

    # The machine, on and homed, and the command port.
    try:
        machine: HMIMachine = HMIMachine(options.dry_run, options.lcnc_port)
        machine.start()
        top_speed: float = machine.max_speed()
    except (OSError, RuntimeError, ValueError, BridgeError) as error:
        print(f"lcnc_hmi.py: {error}", file=sys.stderr)
        return 1
    port: CommandPort | None = (
        CommandPort(options.port) if options.port else None
    )

    # The shop that names the tooling (`T.emsagc~5.2` #63), and the
    # SolidCraft the setups are drawn in, if any.
    try:
        use_shop(shops.read(options.shop))
    except shops.ShopError as error:
        print(f"lcnc_hmi.py: {error}", file=sys.stderr)
        return 1
    drawer: SetupDrawer | None = (
        SetupDrawer(
            SetupView(PyBind(connect(str(options.solidcraft))), ModelCache())
        )
        if options.solidcraft
        else None
    )

    # The window.  A `SIGTERM` closes it as its close button does.  An
    # earlier HMI may have left another speed, and the slider starts
    # at the programmed feed.
    root: tk.Tk = tk.Tk()
    panel: HMI = HMI(root, machine, top_speed, port)
    panel.set_speed(1.0)
    panel.drawer = drawer
    signal.signal(signal.SIGTERM, lambda *_: root.destroy())
    if options.program:
        try:
            panel.open(options.program)
        except (ValueError, OSError) as error:
            panel.message.configure(text=str(error))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
