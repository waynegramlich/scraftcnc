"""Plot an `SCCNC` program's tool path as a page that can be turned.

`plot_html()` returns a self-contained page (the template
`scplot_template.html`, with the path filled in) that draws every move
in 3D: rapids dashed, cuts shaded by depth, with the part's outlines
and the tool.  It can be turned, zoomed, and played through, with the
G-code beside it.  `write_plot()` saves it to a file.

`sketch_path()` draws the same moves into SolidCraft instead, as 3D
sketches beside the part (two for each operation: its cuts and its
rapids, which can be shown and hidden separately).  SolidCraft cannot
color sketch lines, so `tube_path()` draws each move as a thin tube (a
body), which can be: rapids one color and cuts another, see-through.

`read_gcode()` reads the G-code text an `SCCNC` writes back into its
commands, and `command_moves()` finds their moves, so a program can be
drawn from its file (`draw_moves()` draws moves into an open 3D
sketch).
"""

import html
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, TypedDict

from scgeometry import SCRoundPoly, point_at
from solidcraftcnc import RS274, SCCNC

if TYPE_CHECKING:
    from scraftpybind import JSON, SolidCraftPyBind

# The page the path is filled into.
TEMPLATE: Path = Path(__file__).resolve().parent / "scplot_template.html"

# Arcs are drawn as lines, one per this many radians of their sweep.
ARC_STEP: float = math.radians(5.0)

# A point in 3D, `[x, y, z]`.
SpacePoint: TypeAlias = list[float]

# One step of an `engine.batch` request: `{"command": ..., "params":
# {...}}`.
Step: TypeAlias = "dict[str, JSON]"

# The most points `sketch.line3d` takes in one call.
MAX_POINTS: int = 500

# Points closer than this (millimeters) are the same point.
SAME: float = 1e-6


# Class `Move`:
class Move(TypedDict):
    """One move of a program, as `path_moves()` finds it.

    Attributes:
    * `g` (`int`): Its `G` code (0 to 3; a drilling cycle is drawn as
      rapids and a `G1` down each hole).
    * `line` (`int`): Its index in the G-code's lines.
    * `pts` (`list[SpacePoint]`): Where it goes (an arc as short lines).
    * `f` (`float`): The feed in effect (0 before the first).
    * `tool` (`int`): The tool in the spindle (0 before the first).
    """

    g: int
    line: int
    pts: list[SpacePoint]
    f: float
    tool: int


# Function `read_gcode()`:
def read_gcode(text: str) -> list[RS274]:
    """Read G-code text, as `SCCNC.gcode()` writes it, into commands.

    Each line is one command: a comment (a line in parentheses), or
    words, each a letter and a number (an `int` when it has no point
    or exponent, like `G0` or `T08`, else a `float`).  It reads only
    what `SCCNC` writes: a letter used twice on a line keeps its last
    value, and comments within a line are not looked for.

    Arguments:
    * `text` (`str`): The G-code.

    Returns:
    * (`list[RS274]`): One command per line, in order.
    """
    commands: list[RS274] = []
    line: str
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("(") and line.endswith(")"):
            commands.append({"comment": line[1:-1]})
            continue
        command: RS274 = {}
        word: str
        for word in line.split():
            number: str = word[1:]
            command[word[0].upper()] = (
                float(number)
                if any(mark in number for mark in ".eE")
                else int(number)
            )
        commands.append(command)
    return commands


# Function `path_moves()`:
def path_moves(cnc: SCCNC) -> list[Move]:
    """Return the program's moves as lines through 3D points.

    Arguments:
    * `cnc` (`SCCNC`): The program.

    Returns:
    * (`list[Move]`): Each move's `G` code, line, points, feed and tool
      (see `command_moves()`).
    """
    return command_moves(cnc.commands)


# Function `command_moves()`:
def command_moves(commands: Sequence[RS274]) -> list[Move]:
    """Return the moves of a program's commands as lines through points.

    Moves before every axis has a position are left out, since where
    they start is not known.  A canned drilling cycle (`G81`, `G73`,
    `G83`, until `G80`) is drawn as a rapid over each hole and down to
    its `R`, one `G1` to its bottom (leaving out the pecks), and a
    rapid back up to where the cycle started (`G98`).

    Arguments:
    * `commands` (`Sequence[RS274]`): The program's commands.

    Returns:
    * (`list[Move]`): Each move's `G` code, line, points, feed and tool.
    """
    moves: list[Move] = []
    state: _State = _State()
    line: int
    for line, command in enumerate(commands):
        # Follow the modal words: the feed, the tool, the cycle.
        feed: float | int | str | None = command.get("F")
        if isinstance(feed, (int, float)):
            state.feed = float(feed)
        tool: float | int | str | None = command.get("T")
        if tool is not None:
            state.tool = int(tool)
        code: float | int | str | None = command.get("G")
        if code == 80:
            state.cycle = None
            continue
        if code in (73, 81, 83):
            state.start_cycle(command)

        # A hole of a cycle, or an ordinary move.
        if state.cycle is not None and ("X" in command or "Y" in command):
            moves += state.hole(command, line)
        elif code in (0, 1, 2, 3):
            assert isinstance(code, int)
            move: Move | None = state.move(command, code, line)
            if move is not None:
                moves.append(move)
    return moves


# Class `_State`:
@dataclass(slots=True)
class _State:
    """Where a program is, and its modal words, while it is read.

    Attributes:
    * `position` (`list[float | None]`): Where the tool is (X, Y, Z).
    * `feed` (`float`): The feed in effect.
    * `tool` (`int`): The tool in the spindle.
    * `cycle` (`tuple[float, float, float] | None`):
      The canned cycle in effect: its starting Z, its `R` and its
      bottom (`None` when there is none).

    Constructor:
    * `_State()`
    """

    # The program's state (alphabetized):
    cycle: tuple[float, float, float] | None = field(init=False, default=None)
    feed: float = field(init=False, default=0.0)
    position: list[float | None] = field(
        init=False, default_factory=lambda: [None, None, None]
    )
    tool: int = field(init=False, default=0)

    # Method `_State.start_cycle()`:
    def start_cycle(self, command: RS274) -> None:
        """Start a canned cycle.

        Arguments:
        * `command` (`RS274`): The cycle's first line.
        """
        bottom: float | int | str = command.get("Z", 0.0)
        retract: float | int | str = command.get("R", 0.0)
        assert isinstance(bottom, (int, float))
        assert isinstance(retract, (int, float))
        self.cycle = (
            float(self.position[2] or 0.0),
            float(retract),
            float(bottom),
        )

    # Method `_State.hole()`:
    def hole(self, command: RS274, line: int) -> list[Move]:
        """Return the moves that drill one hole of a canned cycle.

        Arguments:
        * `command` (`RS274`): The hole's line.
        * `line` (`int`): Its index in the G-code's lines.

        Returns:
        * (`list[Move]`): Over, down to `R`, down to the bottom, up.
        """
        assert self.cycle is not None
        start: float
        retract: float
        bottom: float
        start, retract, bottom = self.cycle
        old: list[float | None] = list(self.position)
        x: float | int | str = command.get("X", old[0] or 0.0)
        y: float | int | str = command.get("Y", old[1] or 0.0)
        assert isinstance(x, (int, float)) and isinstance(y, (int, float))
        self.position = [float(x), float(y), start]
        if None in old:
            return []
        points: list[SpacePoint] = [
            [float(old[0] or 0.0), float(old[1] or 0.0), start],
            [float(x), float(y), start],
            [float(x), float(y), retract],
            [float(x), float(y), bottom],
            [float(x), float(y), start],
        ]
        codes: tuple[int, ...] = (0, 0, 1, 0)
        return [
            {
                "g": codes[index],
                "line": line,
                "pts": points[index : index + 2],
                "f": self.feed,
                "tool": self.tool,
            }
            for index in range(4)
        ]

    # Method `_State.move()`:
    def move(self, command: RS274, code: int, line: int) -> Move | None:
        """Return an ordinary move (`G0` to `G3`).

        Arguments:
        * `command` (`RS274`): The move's line.
        * `code` (`int`): Its `G` code.
        * `line` (`int`): Its index in the G-code's lines.

        Returns:
        * (`Move | None`): The move, or `None` when where it starts is
          not known yet.
        """
        # Where the move ends.
        old: list[float | None] = list(self.position)
        axis: int
        letter: str
        for axis, letter in enumerate("XYZ"):
            value: float | int | str | None = command.get(letter)
            if isinstance(value, (int, float)):
                self.position[axis] = float(value)
        if None in old or None in self.position:
            return None
        start: SpacePoint = [float(value or 0.0) for value in old]
        end: SpacePoint = [float(value or 0.0) for value in self.position]

        # Lines go straight; arcs (and helices) are broken up.
        points: list[SpacePoint] = [start, end]
        if code in (2, 3):
            i: float | int | str = command.get("I", 0.0)
            j: float | int | str = command.get("J", 0.0)
            assert isinstance(i, (int, float)) and isinstance(j, (int, float))
            points = _arc_points(
                start, end, (start[0] + i, start[1] + j), code
            )
        return {
            "g": code,
            "line": line,
            "pts": points,
            "f": self.feed,
            "tool": self.tool,
        }


# Function `_arc_points()`:
def _arc_points(
    start: SpacePoint, end: SpacePoint, center: tuple[float, float], code: int
) -> list[SpacePoint]:
    """Return points along an arc (rising or falling evenly in Z).

    Arguments:
    * `start` (`SpacePoint`): Where the arc starts.
    * `end` (`SpacePoint`): Where it ends.
    * `center` (`tuple[float, float]`): Its center in XY.
    * `code` (`int`): 2 for clockwise, 3 for counter-clockwise.

    Returns:
    * (`list[SpacePoint]`): Points from `start` to `end`.
    """
    # The sweep, the way the arc goes (a whole turn when it ends where
    # it starts).
    radius: float = math.hypot(start[0] - center[0], start[1] - center[1])
    first: float = math.atan2(start[1] - center[1], start[0] - center[0])
    last: float = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep: float = (last - first) % (2.0 * math.pi)
    if code == 2:
        sweep -= 2.0 * math.pi
    if abs(sweep) < 1e-9 or abs(abs(sweep) - 2.0 * math.pi) < 1e-9:
        sweep = 2.0 * math.pi if code == 3 else -2.0 * math.pi

    # Even steps around it.
    steps: int = max(2, math.ceil(abs(sweep) / ARC_STEP))
    points: list[SpacePoint] = []
    step: int
    for step in range(steps + 1):
        fraction: float = step / steps
        angle: float = first + sweep * fraction
        points.append(
            [
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle),
                start[2] + (end[2] - start[2]) * fraction,
            ]
        )
    points[-1] = list(end)
    return points


# Function `plot_html()`:
def plot_html(
    cnc: SCCNC,
    outlines: Sequence[tuple[SCRoundPoly, float]],
    title: str,
) -> str:
    """Return a page that plots a program's tool path.

    Arguments:
    * `cnc` (`SCCNC`): The program.
    * `outlines` (`Sequence[tuple[SCRoundPoly, float]]`):
      Outlines of the part to draw faintly, each with its Z.
    * `title` (`str`): The page's title.

    Returns:
    * (`str`): The page (for an Artifact, or to open in a browser).
    """
    # Round the numbers, so the page stays small.
    data: dict[str, object] = {
        "z_top": cnc.z_top,
        "z_safe": cnc.z_safe,
        "rapid_speed": cnc.machine.rapid_speed,
        "tools": {
            str(tool.number): {"name": tool.name, "diameter": tool.diameter}
            for tool in cnc.machine.tools
        },
        "lines": cnc.gcode().splitlines(),
        "moves": [
            {
                "g": move["g"],
                "line": move["line"],
                "f": move["f"],
                "tool": move["tool"],
                "pts": [
                    [round(value, 5) for value in point]
                    for point in move["pts"]
                ],
            }
            for move in path_moves(cnc)
        ],
        "outlines": [
            {
                "name": poly.name,
                "z": z,
                "pts": [
                    [round(value, 5) for value in point_at(segment, step / 8)]
                    for segment in poly.segments
                    for step in range(8)
                ],
            }
            for poly, z in outlines
        ],
    }

    # A `</` in the data would end its `<script>` early.
    text: str = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page: str = TEMPLATE.read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(title)).replace(
        "__DATA__", text
    )


# Function `write_plot()`:
def write_plot(
    path: Path,
    cnc: SCCNC,
    outlines: Sequence[tuple[SCRoundPoly, float]],
    title: str,
) -> None:
    """Save a plot of a program's tool path.

    Arguments:
    * `path` (`Path`): The page's file (`.html`).
    * `cnc` (`SCCNC`): The program.
    * `outlines` (`Sequence[tuple[SCRoundPoly, float]]`):
      Outlines of the part to draw faintly, each with its Z.
    * `title` (`str`): The page's title.
    """
    path.write_text(plot_html(cnc, outlines, title), encoding="utf-8")


# Function `sketch_path()`:
def sketch_path(
    solidcraft: "SolidCraftPyBind", cnc: SCCNC, mm_per_unit: float = 1.0
) -> list[str]:
    """Draw a program's tool path into SolidCraft as 3D sketches.

    Each operation (the moves after each of the program's comments)
    gets two sketches, named after the comment: its cuts (`G1`, `G2`,
    `G3`) and its rapids (`G0`).  Straight moves that follow on from
    each other (arcs included, as points along them) are drawn as one
    3D line.  Each sketch is built with one `engine.batch` request
    (`send_batch()`), which the GUI runs in one frame, so it is fast
    and sketch mode never shows.  The path is the tool's center.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): Where to draw it.
    * `cnc` (`SCCNC`): The program.
    * `mm_per_unit` (`float`):
      SolidCraft's world coordinates are millimeters, so this scales
      the program's units to them (25.4 for inches).

    Returns:
    * (`list[str]`): The names of the sketches made.
    """
    # Sort the moves by operation, and into cuts and rapids.
    titles: dict[int, str] = {
        line: str(command["comment"])
        for line, command in enumerate(cnc.commands)
        if "comment" in command
    }
    groups: dict[str, list[Move]] = {}
    title: str = cnc.name
    move: Move
    for move in path_moves(cnc):
        title = max(
            (
                (line, name)
                for line, name in titles.items()
                if line < move["line"]
            ),
            default=(0, title),
        )[1]
        kind: str = "rapids" if move["g"] == 0 else "cuts"
        groups.setdefault(f"{title} {kind}", []).append(move)

    # Draw each group in its own 3D sketch, with one request.
    name: str
    moves: list[Move]
    for name, moves in groups.items():
        send_batch(
            solidcraft, sketch_steps(name, path_steps(moves, mm_per_unit))
        )
    return list(groups)


# Function `path_steps()`:
def path_steps(moves: Sequence[Move], mm_per_unit: float) -> list[Step]:
    """Return the `sketch.line3d` steps that draw moves.

    Moves that follow on from each other make one polyline, broken
    into calls of at most `MAX_POINTS` points that share their ends; a
    jump starts a new one.  Points that repeat the one before are left
    out.

    Arguments:
    * `moves` (`Sequence[Move]`): The moves, in order.
    * `mm_per_unit` (`float`): The scale to millimeters.

    Returns:
    * (`list[Step]`): The steps, for an open 3D sketch.
    """
    steps: list[Step] = []
    run: list[SpacePoint] = []

    # Function `flush()`:
    def flush() -> None:
        """Add steps for the polyline so far, and start a new one."""
        start: int = 0
        while start < len(run) - 1:
            piece: list[SpacePoint] = run[start : start + MAX_POINTS]
            steps.append(
                {"command": "sketch.line3d", "params": {"points": piece}}
            )
            start += MAX_POINTS - 1
        run.clear()

    # Add each move to the polyline, or start a new one where it jumps.
    move: Move
    for move in moves:
        points: list[SpacePoint] = [
            [value * mm_per_unit for value in point] for point in move["pts"]
        ]
        if run and math.dist(run[-1], points[0]) >= SAME:
            flush()
        point: SpacePoint
        for point in points:
            if not run or math.dist(run[-1], point) >= SAME:
                run.append(point)
    flush()
    return steps


# Function `sketch_steps()`:
def sketch_steps(name: str, drawing: list[Step]) -> list[Step]:
    """Return the steps of one batch: a whole 3D sketch.

    Arguments:
    * `name` (`str`): The sketch's name.
    * `drawing` (`list[Step]`): Its drawing steps (`path_steps()`).

    Returns:
    * (`list[Step]`): Create, options (3D; points, profile,
      constraints and dimensions not shown), the drawing, finish.
    """
    return [
        {"command": "sketch.create", "params": {"plane": "XY", "name": name}},
        {
            "command": "sketch.options",
            "params": {
                "sketch_3d": True,
                "show_points": False,
                "show_profile": False,
                "show_constraints": False,
                "show_dimensions": False,
            },
        },
        *drawing,
        {"command": "sketch.finish", "params": {}},
    ]


# Function `send_batch()`:
def send_batch(solidcraft: "SolidCraftPyBind", steps: list[Step]) -> None:
    """Run steps in SolidCraft as one batch, with no rollback.

    A GUI takes `engine.batch` and runs the steps in one frame; a
    headless `solidcraft-cli` has no `engine.batch`, but its MCP server
    has a `batch` tool that takes the same steps.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `steps` (`list[Step]`): The steps.

    Raises:
    * `SolidCraftError`: If a step failed (or the batch was refused).
    """
    # Imported here, so the viewer needs no `scraftpybind`.
    # pylint: disable-next=import-outside-toplevel
    from scraftpybind import HeadlessTransport, SolidCraftError

    # The GUI's `engine.batch`, or the headless MCP `batch` tool.
    params: dict[str, JSON] = {"commands": steps, "rollback": False}
    transport = solidcraft.transport
    reply: object
    if isinstance(transport, HeadlessTransport):
        if transport.process is None:
            transport.start()
        result = transport.call(
            "tools/call", {"name": "batch", "arguments": params}
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert isinstance(content, list) and isinstance(content[0], dict)
        reply = json.loads(str(content[0]["text"]))
    else:
        reply = transport.request("engine.batch", params)

    # Every step must have run.
    if (
        not isinstance(reply, dict)
        or "failed" in reply
        or reply.get("completed") != len(steps)
    ):
        raise SolidCraftError("engine.batch", str(reply)[:2000], False, False)


# Function `tube_path()`:
def tube_path(
    solidcraft: "SolidCraftPyBind",
    cnc: SCCNC,
    mm_per_unit: float = 1.0,
    *,
    diameter: float = 0.5,
    looks: tuple[tuple[str, float], tuple[str, float]] = (
        ("#22b14c", 0.45),
        ("#e0301e", 0.45),
    ),
) -> tuple[list[str], list[str]]:
    """Draw a program's tool path into SolidCraft as thin colored tubes.

    Each move becomes a pipe (`solid.pipe`) along a 3D sketch of it, an
    arc as straight pieces (`ARC_STEP` apart), since a pipe along a
    spline is about twenty times slower.  Each move is its own body,
    since one pipe along several could cross itself (a spur goes out
    and back along one line).  The sketch is hidden afterwards, leaving
    the tubes.

    It is slow: the demonstration's 330 moves take about 47 seconds
    headless, and far longer in the GUI (where one pipe ran past the
    GUI's one minute request limit), so `sketch_path()` is the usual
    way to see a path.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): Where to draw it.
    * `cnc` (`SCCNC`): The program.
    * `mm_per_unit` (`float`):
      SolidCraft's world coordinates are millimeters, so this scales
      the program's units to them (25.4 for inches).
    * `diameter` (`float`):
      The tubes' diameter (mm; sent with its unit, since a bare number
      would be taken in the design's units, such as inches).
    * `looks` (`tuple[tuple[str, float], tuple[str, float]]`):
      The color (`#rrggbb`) and opacity (0 to 1) of the rapids' tubes,
      then of the cuts' tubes.

    Returns:
    * (`tuple[list[str], list[str]]`): The names of the rapids' bodies,
      and of the cuts' bodies.
    """
    # Sketch every move as straight pieces.
    sketch: str = f"{cnc.name} tool path"
    wires: list[tuple[int, list[str]]] = _sketch_moves(
        solidcraft, cnc, mm_per_unit, sketch
    )

    # A tube along each, then color the two kinds, and hide the sketch.
    bodies: tuple[list[str], list[str]] = ([], [])
    code: int
    path: list[str]
    for code, path in wires:
        kind: list[str] = bodies[0] if code == 0 else bodies[1]
        name: str = f"{'Rapid' if code == 0 else 'Cut'} {len(kind) + 1}"
        solidcraft.solid.pipe(
            path_sketch=sketch,
            path=path,
            diameter=f"{diameter} mm",
            body_name=name,
        )
        kind.append(name)
    names: list[str]
    look: tuple[str, float]
    for names, look in zip(bodies, looks):
        if names:
            solidcraft.appearance.assign(
                bodies=names, color=look[0], opacity=look[1]
            )
    solidcraft.browser.visibility(visible=False, items=[sketch])
    return bodies


# Function `_sketch_moves()`:
def _sketch_moves(
    solidcraft: "SolidCraftPyBind", cnc: SCCNC, mm_per_unit: float, sketch: str
) -> list[tuple[int, list[str]]]:
    """Sketch each move of a program as 3D straight pieces.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): Where to sketch them.
    * `cnc` (`SCCNC`): The program.
    * `mm_per_unit` (`float`): The scale to millimeters.
    * `sketch` (`str`): The new 3D sketch's name.

    Returns:
    * (`list[tuple[int, list[str]]]`): Each move's `G` code and the ids
      of its pieces, in order (moves that go nowhere are left out).
    """
    solidcraft.sketch.create(plane="XY", name=sketch)
    solidcraft.sketch.options(sketch_3d=True)
    wires: list[tuple[int, list[str]]] = []
    move: Move
    for move in path_moves(cnc):
        points: list[SpacePoint] = [
            [value * mm_per_unit for value in point] for point in move["pts"]
        ]
        if len(points) == 2 and math.dist(points[0], points[1]) < 1e-6:
            continue
        created: object = solidcraft.sketch.line3d(points=points)
        assert isinstance(created, dict)
        curves: object = created["curves"]
        assert isinstance(curves, list)
        wires.append((move["g"], [str(curve) for curve in curves]))
    solidcraft.sketch.finish()
    return wires
