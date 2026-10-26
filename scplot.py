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
"""

import html
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, TypedDict

from scgeometry import SCRoundPoly, point_at
from solidcraftcnc import SCCNC

if TYPE_CHECKING:
    from pysolidcraft import PySolidCraft

# The page the path is filled into.
TEMPLATE: Path = Path(__file__).resolve().parent / "scplot_template.html"

# Arcs are drawn as lines, one per this many radians of their sweep.
ARC_STEP: float = math.radians(5.0)

# A point in 3D, `[x, y, z]`.
SpacePoint: TypeAlias = list[float]


# Class `Move`:
class Move(TypedDict):
    """One move of a program, as `path_moves()` finds it.

    Attributes:
    * `g` (`int`): Its `G` code (0 to 3).
    * `line` (`int`): Its index in the G-code's lines.
    * `pts` (`list[SpacePoint]`): Where it goes (an arc as short lines).
    """

    g: int
    line: int
    pts: list[SpacePoint]


# Function `path_moves()`:
def path_moves(cnc: SCCNC) -> list[Move]:
    """Return the program's moves as lines through 3D points.

    Moves before every axis has a position are left out, since where
    they start is not known.

    Arguments:
    * `cnc` (`SCCNC`): The program.

    Returns:
    * (`list[Move]`): Each move's `g` (0 to 3), `line` (its index in
      the G-code's lines) and `pts` (where it goes, arcs as many short
      lines).
    """
    moves: list[Move] = []
    position: list[float | None] = [None, None, None]
    line: int
    for line, command in enumerate(cnc.commands):
        code: float | int | str | None = command.get("G")
        if code not in (0, 1, 2, 3):
            continue
        assert isinstance(code, int)

        # Where the move ends.
        old: list[float | None] = list(position)
        axis: int
        letter: str
        for axis, letter in enumerate("XYZ"):
            value: float | int | str | None = command.get(letter)
            if isinstance(value, (int, float)):
                position[axis] = float(value)
        if None in old or None in position:
            continue
        start: SpacePoint = [float(value or 0.0) for value in old]
        end: SpacePoint = [float(value or 0.0) for value in position]

        # Lines go straight; arcs (and helices) are broken up.
        points: list[SpacePoint] = [start, end]
        if code in (2, 3):
            i: float | int | str = command.get("I", 0.0)
            j: float | int | str = command.get("J", 0.0)
            assert isinstance(i, (int, float)) and isinstance(j, (int, float))
            points = _arc_points(
                start, end, (start[0] + i, start[1] + j), code
            )
        moves.append({"g": code, "line": line, "pts": points})
    return moves


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
        "tool_diameter": cnc.tool_diameter,
        "rapid_speed": cnc.rapid_speed,
        "work_speed": cnc.work_speed,
        "spindle_rpm": cnc.spindle_rpm,
        "lines": cnc.gcode().splitlines(),
        "moves": [
            {
                "g": move["g"],
                "line": move["line"],
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
    solidcraft: "PySolidCraft", cnc: SCCNC, mm_per_unit: float = 1.0
) -> list[str]:
    """Draw a program's tool path into SolidCraft as 3D sketches.

    Each operation (the moves after each of the program's comments)
    gets two sketches, named after the comment: its cuts (`G1`, `G2`,
    `G3`) and its rapids (`G0`).  Straight moves that follow on from
    each other are drawn as one 3D line; each arc (or helix) is a 3D
    spline through points along it.  The path is the tool's center.

    Arguments:
    * `solidcraft` (`PySolidCraft`): Where to draw it.
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

    # Draw each group in its own 3D sketch.
    names: list[str] = []
    name: str
    moves: list[Move]
    for name, moves in groups.items():
        solidcraft.sketch.create(plane="XY", name=name)
        solidcraft.sketch.options(sketch_3d=True)
        _draw(solidcraft, moves, mm_per_unit)
        solidcraft.sketch.finish()
        names.append(name)
    return names


# Function `_draw()`:
def _draw(
    solidcraft: "PySolidCraft", moves: list[Move], mm_per_unit: float
) -> None:
    """Draw moves into the open 3D sketch.

    Arguments:
    * `solidcraft` (`PySolidCraft`): Where to draw them.
    * `moves` (`list[Move]`): The moves, in order.
    * `mm_per_unit` (`float`): The scale to millimeters.
    """

    # Function `mm()`:
    def mm(point: SpacePoint) -> SpacePoint:
        """Return a point in millimeters.

        Arguments:
        * `point` (`SpacePoint`): The point in the program's units.

        Returns:
        * (`SpacePoint`): The point in millimeters.
        """
        return [value * mm_per_unit for value in point]

    # Gather straight moves that follow on from each other into one
    # line; draw each arc as a spline.
    run: list[SpacePoint] = []
    move: Move
    for move in moves:
        if move["g"] in (0, 1) and (not run or run[-1] == move["pts"][0]):
            run += move["pts"][1:] if run else move["pts"]
            continue
        if len(run) >= 2:
            solidcraft.sketch.line3d(points=[mm(point) for point in run])
        run = []
        if move["g"] in (0, 1):
            run = list(move["pts"])
        else:
            solidcraft.sketch.spline3d(
                points=[mm(point) for point in move["pts"]]
            )
    if len(run) >= 2:
        solidcraft.sketch.line3d(points=[mm(point) for point in run])


# Function `tube_path()`:
def tube_path(
    solidcraft: "PySolidCraft",
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
    * `solidcraft` (`PySolidCraft`): Where to draw it.
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
    solidcraft: "PySolidCraft", cnc: SCCNC, mm_per_unit: float, sketch: str
) -> list[tuple[int, list[str]]]:
    """Sketch each move of a program as 3D straight pieces.

    Arguments:
    * `solidcraft` (`PySolidCraft`): Where to sketch them.
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
