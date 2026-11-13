"""The HMI's link to LinuxCNC, and everything else it does but draw.

`lcnc_hmi.py` is the HMI, in Qt; this is what it uses that needs no
GUI toolkit, so it can be tested with no display:

* `HMIMachine`: the LinuxCNC calls, a client (through
  `scraftcam.lcnc.lcnc_client`) of `serve_linuxcnc` from
  `scraftcam/lcnc/`, which runs LinuxCNC in its `lcnc` box, or in WSL
  on Windows; or, dry run, no LinuxCNC at all.
* `CommandPort`: the HMI's command port, one line in, one line back.
* `SetupDrawer`: draws setups in SolidCraft on a thread of its own.
* The program's tool changes and timing (`tool_changes()`,
  `change_spans()`, `line_minutes()`, `next_tool_text()`), and the
  keep-out checks of jogs and MDI lines (`jog_hit()`,
  `mdi_segments()`).
* The shop, machine, material and origin a setup names
  (`setup_warning()`, `setup_material()`, `setup_origin()`).
"""

# Half of the module is docstrings, which the type hints and the
# argument lists make long, so it passes 1000 lines.
# pylint: disable=too-many-lines

import itertools
import math
import queue
import re
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from .. import shops
from ..assembly import Assembly, AssemblyItem, millimeters
from ..geometry import LineSegment, RoundedPolygon
from ..lcnc.lcnc_client import PORT, BridgeClient, BridgeError, constant
from ..plot import PathMove, command_moves, read_gcode
from ..tooling.tools import Point

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

# The words of a typed line that set the distance mode or the units.
INCREMENTAL: re.Pattern[str] = re.compile(r"\bG0*91(?![.\d])", re.IGNORECASE)
METRIC: re.Pattern[str] = re.compile(r"\bG0*21(?![.\d])", re.IGNORECASE)
INCH: re.Pattern[str] = re.compile(r"\bG0*20(?![.\d])", re.IGNORECASE)

# A word that starts a move, and an axis word: a line with an axis word
# but no move word moves in LinuxCNC's current (modal) motion mode.
MOTION: re.Pattern[str] = re.compile(
    r"\bG0*(?:[0-3]|8[0-9])(?![.\d])", re.IGNORECASE
)
AXIS: re.Pattern[str] = re.compile(r"[XYZ]\s*[-+.\d]", re.IGNORECASE)

# A line of RS-274 words, simply: letters, each followed by a number.
WORDS: re.Pattern[str] = re.compile(
    r"\s*([A-Za-z]\s*[-+]?(\d+\.?\d*|\.\d+)\s*)+"
)

# The shop and machine whose tools the Tools window lists, and the
# material it starts with.
SHOP_FILE: Path = (
    Path(__file__).resolve().parents[2] / "examples/shop/shop.toml"
)
SHOP_MACHINE: str = "Shop mill"
MATERIAL: str = "6061 aluminum"


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


# Function `mdi_segments()`:
def mdi_segments(
    line: str, start: tuple[float, float, float], metric: bool
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Return the straight pieces a typed (MDI) line moves the tip by.

    The line is read by the tool path viewer's reader
    (`plot.read_gcode()`), after a move to where the tip is, in
    absolute (`G90`) mode; arcs come back as short straight pieces.
    A line with axis words but no move word (e.g. `Z-4`) moves in the
    modal motion mode, which the reader does not follow, so it is
    read as a straight `G1` (the user drove through the grid plate
    with `Z-4`).

    Arguments:
    * `line` (`str`): The typed line.
    * `start` (`tuple[float, float, float]`): Where the tip is (work
      inches).
    * `metric` (`bool`): True when the line's numbers are millimeters.

    Returns:
    * (`list[tuple[tuple[float, float, float], tuple[float, float,
      float]]]`): Each piece's start and end (work inches); none for a
      line that does not move.

    Raises:
    * `ValueError`: If the line can not be read, or has axis words
      but reads as no move.
    """
    words: str = COMMENT.sub("", line)
    if re.search(r"\bG0*(?:28|30|53)(?![.\d])", words, re.IGNORECASE):
        raise ValueError("moves by machine coordinates (G28, G30, G53)")
    if AXIS.search(words) and not MOTION.search(words):
        line = f"G1 {line}"
    scale: float = 25.4 if metric else 1.0
    x, y, z = (value * scale for value in start)
    text: str = (
        f"{'G21' if metric else 'G20'} G90\n"
        f"G0 X{x:.6f} Y{y:.6f} Z{z:.6f}\n{line}"
    )
    try:
        moves: list[PathMove] = command_moves(read_gcode(text))
    except (KeyError, IndexError) as error:
        raise ValueError(str(error)) from error
    pieces: list[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ] = []
    move: PathMove
    for move in moves:
        points: list[tuple[float, float, float]] = [
            (point[0] / scale, point[1] / scale, point[2] / scale)
            for point in move["pts"]
        ]
        pieces += itertools.pairwise(points)
    if (
        not pieces
        and AXIS.search(words)
        and not re.search(r"\bG0*(?:10|92|43|5[4-9])\b", words, re.IGNORECASE)
    ):
        raise ValueError(f"no move read from {line!r}")
    return pieces


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
    * `spindle` (`bool`): True while a spindle turns (or is on), so
      that nothing closes until it stops (`T.osiade~5.1.9` #56).

    Constructor:
    * `HMIStatus(file, line, position, tool, messages, state, spindle)`
    """

    # Constructor arguments:
    file: str = field(init=True)
    line: int = field(init=True)
    position: tuple[float, float, float] = field(init=True)
    tool: int = field(init=True)
    messages: list[str] = field(init=True)
    state: str = field(init=True)
    spindle: bool = field(init=True, default=False)


# Function `spindle_on()`:
def spindle_on(spindles: object) -> bool:
    """Tell whether any spindle is on, from `linuxcnc.stat.spindle`.

    Arguments:
    * `spindles` (`object`): The stat's `spindle`: one dictionary a
      spindle, with `enabled` and `speed`.

    Returns:
    * (`bool`): True if any is enabled or turning; True as well when
      it can not be read, as a spindle not known to be off is on.
    """
    if not isinstance(spindles, (list, tuple)):
        return True
    return any(
        not isinstance(spindle, dict)
        or bool(spindle.get("enabled", True))
        or float(spindle.get("speed", 0.0)) != 0.0
        for spindle in spindles
    )


# Class `HMIMachine`:
class HMIMachine:
    """The LinuxCNC back end, as the HMI sees it.

    It is a client of `scraftcam.lcnc`'s `serve_linuxcnc`, which runs
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

    # Method `HMIMachine.modes()`:
    def modes(self) -> tuple[bool, bool]:
        """Return LinuxCNC's distance mode and units, as now set.

        Returns:
        * (`tuple[bool, bool]`): True when incremental (`G91`), and
          True when metric (`G21`); both False without LinuxCNC.
        """
        if self.lcnc is None:
            return (False, False)
        gcodes: list[int] = list(self.lcnc.stat("gcodes")["gcodes"])
        return (910 in gcodes, 210 in gcodes)

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
            "spindle",
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
            spindle_on(stat["spindle"]),
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
    replaces it, so only the newest is drawn next.  Qt is not thread
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
