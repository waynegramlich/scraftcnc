#!/usr/bin/env python3
"""3D models of the tools in a shop's tools files, for SolidCraft.

Each tool is drawn as a profile: its radius at each height, from its
tip (at 0) up its shank, as a closed outline of `(r, z)` points
(inches) that starts at the tip on the axis, goes out and up the
tool's side, and comes back down the axis.  Revolving it about the
axis gives the tool.  The sizes come from the tools files (`Shops.md`):
a drill gets a cone at its tip from its `point_angle`, a ball end mill
a rounded end, a chamfer mill a cone down to its `tip_diameter`, a
corner rounding mill its hollow quarter circle, and a double angle
cutter its head on a neck.

A tool's holder is not a picture of a holder.  It is a truncated cone,
sliced into one band per digit of the tool's `unique_id`, colored by
the electrical resistor color code, so that a tool can be read off the
screen.  Every tool has as many bands as the longest number in the
shop, with leading zeros, and the first digit is at the holder's base.

A tool's flutes are not cut.  They are lines drawn on its surface, in
a 3D sketch (`flute_steps()`): a helix up the side of an end mill or a
drill, and straight along the profile for the rest, with none on the
tip's end.  `model_tool()` is the one way to model a shop's tool: its
body and its lines, in one component, which then moves as one.

Arcs are drawn as short straight lines, which is plenty for a picture.
Run this to see every tool of the example shop in SolidCraft:

```
./sctoolmodel.py 8080
```
"""

# `profile()` names each size it reads, with a type hint, which runs
# past `pylint`'s limit on local variables.
# pylint: disable=too-many-locals

import itertools
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from scplot import SCStep, SpacePoint, send_batch, sketch_steps
from scraftpybind import JSON, SCPyBind, connect
from shops import ANGLE, CNC_KINDS, LENGTH, measure, read

# A profile: `(r, z)` points, in inches.
Profile = list[tuple[float, float]]

# A line along a flute: the 3D sketch command that draws it, and its
# points, with the tool's axis at X = Y = 0.
FluteRun = tuple[str, list[SpacePoint]]

# SolidCraft's coordinates are millimeters.
MM_PER_INCH: float = 25.4

# How many straight lines draw a quarter circle.
ARC_STEPS: int = 8

# The electrical resistor color code, by digit.
RESISTOR_COLORS: tuple[str, ...] = (
    "#000000",  # 0: black.
    "#8b4513",  # 1: brown.
    "#ff0000",  # 2: red.
    "#ff8c00",  # 3: orange.
    "#ffff00",  # 4: yellow.
    "#008000",  # 5: green.
    "#0000ff",  # 6: blue.
    "#8a2be2",  # 7: violet.
    "#808080",  # 8: gray.
    "#ffffff",  # 9: white.
)

# The rough size of every holder, whatever its kind (inches).
HOLDER_LENGTH: float = 2.5
HOLDER_BASE_DIAMETER: float = 1.75

# How much wider a holder's tool end is than its bore (inches).
HOLDER_WALL: float = 0.5

# How see-through a holder is, so that the tool shows inside it.
HOLDER_OPACITY: float = 0.4

# The share of a tool's overall length that is inside its holder.
HOLDER_GRIP: float = 1 / 3

# How far apart the tools stand along X (inches).
TOOL_SPACING: float = 2.5

# The helix angle of the kinds of tool that have one (degrees).  The
# catalog gives none for drills, and the tools files have no key for
# it, so 30 degrees is a typical value, from memory.
HELIX_ANGLES: dict[str, float] = {"end_mills": 30.0, "drills": 30.0}

# How many flutes a tool has when its tools file does not say.
DEFAULT_FLUTES: int = 2

# How far either side of its center a helical flute's edges lie.
FLUTE_HALF_WIDTH: float = math.radians(15.0)

# How far the lines stand off the surface, as a share of the radius,
# since a round body is drawn as facets that cut inside the circle.
FLUTE_LIFT: float = 0.01

# How many points a spline has per turn of its helix.
HELIX_POINTS_PER_TURN: int = 12

# The example shop.
EXAMPLE_SHOP: Path = (
    Path(__file__).resolve().parent / "examples/shop/home_shop.toml"
)


# Function `_size()`:
def _size(tool: dict[str, object], key: str, default: float) -> float:
    """Return one of a tool's lengths, in inches.

    Arguments:
    * `tool` (`dict[str, object]`): The tool, from `shops.read()`.
    * `key` (`str`): The length's key (such as `"shank"`).
    * `default` (`float`): Its value when the tool does not give it.

    Returns:
    * (`float`): The length (inches).
    """
    return measure(tool[key], LENGTH) if key in tool else default


# Function `_quarter()`:
def _quarter(
    center: tuple[float, float], radius: float, start: float, end: float
) -> Profile:
    """Return the points of an arc, after its first.

    Arguments:
    * `center` (`tuple[float, float]`): Its center, `(r, z)`.
    * `radius` (`float`): Its radius.
    * `start` (`float`): The angle it starts at (degrees).
    * `end` (`float`): The angle it ends at (degrees).

    Returns:
    * (`Profile`): Its points, `ARC_STEPS` of them.
    """
    points: Profile = []
    for step in range(1, ARC_STEPS + 1):
        angle: float = math.radians(start + (end - start) * step / ARC_STEPS)
        points.append(
            (
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle),
            )
        )
    return points


# Function `_tidy()`:
def _tidy(points: Profile) -> Profile:
    """Drop the points that repeat the one before them.

    Arguments:
    * `points` (`Profile`): The points.

    Returns:
    * (`Profile`): The points, with no two in a row the same.
    """
    tidy: Profile = []
    for r, z in points:
        point: tuple[float, float] = (round(r, 9), round(z, 9))
        if not tidy or point != tidy[-1]:
            tidy.append(point)
    return tidy


# Function `profile()`:
def profile(key: str, tool: dict[str, object]) -> Profile:
    """Return a tool's profile.

    Arguments:
    * `key` (`str`):
      The list the tool is in, in its tools file (`"end_mills"`,
      `"drills"`, `"chamfer_mills"`, `"corner_rounding_mills"` or
      `"double_angle_cutters"`); any other is drawn as a plain
      cylinder.
    * `tool` (`dict[str, object]`): The tool, from `shops.read()`.

    Returns:
    * (`Profile`): Its outline, from the tip on the axis, out and up
      its side to its top, and back to the axis there.

    Raises:
    * `ValueError`: If one of its sizes is not a measurement.
    """
    # The sizes that most tools have.
    diameter: float = _size(tool, "diameter", 0.25)
    radius: float = diameter / 2
    shank: float = _size(tool, "shank", diameter) / 2
    length: float = _size(tool, "overall_length", 2.0)
    angle: float = measure(tool["angle"], ANGLE) if "angle" in tool else 90.0
    tip: float = _size(tool, "tip_diameter", 0.0) / 2
    side: Profile

    # The side, from the tip up to where the shank starts.
    if key == "end_mills":
        cut: float = _size(tool, "length_of_cut", length / 2)
        if tool.get("end") == "ball":
            side = [(0.0, 0.0), *_quarter((0.0, radius), radius, -90, 0)]
        else:
            side = [(0.0, 0.0), (radius, 0.0)]
        side += [(radius, cut), (shank, cut)]
    elif key == "drills":
        point: float = (
            measure(tool["point_angle"], ANGLE)
            if "point_angle" in tool
            else 118.0
        )
        side = [
            (0.0, 0.0),
            (radius, radius / math.tan(math.radians(point / 2))),
        ]
    elif key == "chamfer_mills":
        rise: float = (radius - tip) / math.tan(math.radians(angle / 2))
        side = [(0.0, 0.0), (tip, 0.0), (radius, rise), (shank, rise)]
    elif key == "corner_rounding_mills":
        round_over: float = _size(tool, "radius", 0.0625)
        side = [
            (0.0, 0.0),
            (tip, 0.0),
            *_quarter((tip + round_over, 0.0), round_over, 180, 90),
            (shank, round_over),
        ]
    elif key == "double_angle_cutters":
        half: float = _size(tool, "width", radius) / 2
        edge: float = radius - half * math.tan(math.radians(angle / 2))
        neck: float = _size(tool, "neck_diameter", 2 * edge) / 2
        top: float = 2 * half + _size(tool, "neck_length", 0.0)
        side = [
            (0.0, 0.0),
            (edge, 0.0),
            (radius, half),
            (edge, 2 * half),
            (neck, 2 * half),
            (neck, top),
            (shank, top),
        ]
    else:
        side = [(0.0, 0.0), (radius, 0.0)]
    end: tuple[float, float] = side[-1]

    # Up the shank to the top, and back to the axis.
    return _tidy([*side, (end[0], length), (0.0, length)])


# Function `flute_path()`:
def flute_path(key: str, tool: dict[str, object]) -> Profile:
    """Return the part of a tool's profile that its flutes run along.

    Arguments:
    * `key` (`str`): The list the tool is in, in its tools file.
    * `tool` (`dict[str, object]`): The tool, from `shops.read()`.

    Returns:
    * (`Profile`): The points from the tip to the flutes' end; empty
      for a kind of tool with no known flutes.  The flat on a tip is
      left out, except for an end mill's, which `flute_runs()` needs to
      find its shoulder and skips.
    """
    # How far up the tool the flutes reach.
    length: float = _size(tool, "overall_length", 2.0)
    cut: float
    if key in HELIX_ANGLES:
        cut = _size(tool, "length_of_cut", length / 2)
    elif key == "chamfer_mills":
        radius: float = _size(tool, "diameter", 0.25) / 2
        tip: float = _size(tool, "tip_diameter", 0.0) / 2
        half: float = math.radians(measure(tool["angle"], ANGLE) / 2)
        cut = (radius - tip) / math.tan(half)
    elif key == "corner_rounding_mills":
        cut = _size(tool, "radius", 0.0625)
    elif key == "double_angle_cutters":
        cut = _size(tool, "width", _size(tool, "diameter", 0.25) / 2)
    else:
        return []

    # Follow the profile to that height.
    outline: Profile = profile(key, tool)
    path: Profile = [outline[0]]
    for r, z in outline[1:]:
        if z >= cut:
            last_r, last_z = path[-1]
            share: float = (cut - last_z) / (z - last_z) if z > last_z else 1.0
            path.append((last_r + share * (r - last_r), cut))
            break
        path.append((r, z))
    path = _tidy(path)

    # No line crosses the flat on the end of a straight fluted tool.
    if key not in HELIX_ANGLES and path[0][1] == path[1][1]:
        return path[1:]
    return path


# Function `_lifted()`:
def _lifted(path: Profile) -> Profile:
    """Return a path moved off the tool's surface.

    Each piece moves along its outward normal, by `FLUTE_LIFT` of the
    widest radius, and each corner to where its moved pieces meet.  With
    the path running out from the tip and up the side, outward is to the
    right of its direction.

    Arguments:
    * `path` (`Profile`): The points on the surface.

    Returns:
    * (`Profile`): The points just outside it.
    """
    # The outward normal of each piece of the path.
    normals: list[tuple[float, float]] = []
    for (r0, z0), (r1, z1) in itertools.pairwise(path):
        along: float = math.hypot(r1 - r0, z1 - z0)
        normals.append(((z1 - z0) / along, (r0 - r1) / along))

    # Each point moves by the normals of the pieces either side of it.
    lift: float = FLUTE_LIFT * max(r for r, _ in path)
    lifted: Profile = []
    for index, (r, z) in enumerate(path):
        before: tuple[float, float] = normals[max(index - 1, 0)]
        after: tuple[float, float] = normals[min(index, len(normals) - 1)]
        meet: float = 1.0 + before[0] * after[0] + before[1] * after[1]
        lifted.append(
            (
                r + lift * (before[0] + after[0]) / meet,
                z + lift * (before[1] + after[1]) / meet,
            )
        )
    return lifted


# Function `_on_surface()`:
def _on_surface(r: float, angle: float, z: float) -> SpacePoint:
    """Return the 3D point at a radius, a direction and a height.

    Arguments:
    * `r` (`float`): How far from the axis.
    * `angle` (`float`): Its direction (radians).
    * `z` (`float`): Its height.

    Returns:
    * (`SpacePoint`): The point, with the axis at X = Y = 0.
    """
    return [r * math.cos(angle), r * math.sin(angle), z]


# Function `_helix()`:
def _helix(
    start: tuple[float, float],
    end_z: float,
    angle: float,
    width: float,
    helix: float,
) -> list[SpacePoint]:
    """Return points along one edge of a helical flute, going up.

    The right handed helix climbs at a constant radius.  Over the last
    tool diameter, the edge closes in on the flute's center, where the
    flute runs out.

    Arguments:
    * `start` (`tuple[float, float]`): Its first `(r, z)`.
    * `end_z` (`float`): The height it climbs to.
    * `angle` (`float`): The flute's center at `start` (radians).
    * `width` (`float`): The edge's angle from that center (radians).
    * `helix` (`float`): The helix angle (degrees).

    Returns:
    * (`list[SpacePoint]`): The points, from `start` up.
    """
    r, start_z = start
    rise: float = end_z - start_z
    lead: float = 2.0 * math.pi * r / math.tan(math.radians(helix))
    pieces: int = max(3, math.ceil(rise / lead * HELIX_POINTS_PER_TURN))
    points: list[SpacePoint] = []
    for piece in range(pieces + 1):
        climbed: float = rise * piece / pieces
        closing: float = min(1.0, (rise - climbed) / (2.0 * r))
        points.append(
            _on_surface(
                r,
                angle + 2.0 * math.pi * climbed / lead + width * closing,
                start_z + climbed,
            )
        )
    return points


# Function `flute_runs()`:
def flute_runs(
    path: Profile, flutes: int, helix: float = 0.0
) -> list[FluteRun]:
    """Return the lines that stand for a tool's flutes.

    With no helix, each flute is one line along the path: its cutting
    edge.  With a helix, each flute has two edges, each a spline up the
    side from where the tool reaches its full radius (its shoulder);
    nothing is drawn on the tip below that.

    Arguments:
    * `path` (`Profile`): The profile's part with flutes, from the tip
      (`flute_path()`), in any one length unit.
    * `flutes` (`int`): How many flutes.
    * `helix` (`float`): The helix angle (degrees), or 0 for straight.

    Returns:
    * (`list[FluteRun]`): The lines, in the path's unit.
    """
    lifted: Profile = _lifted(path)
    widest: float = max(r for r, _ in path)
    shoulder: int = next(
        index for index, (r, _) in enumerate(path) if r == widest
    )
    runs: list[FluteRun] = []
    for flute in range(flutes):
        center: float = 2.0 * math.pi * flute / flutes
        if helix == 0.0:
            runs.append(
                (
                    "sketch.line3d",
                    [_on_surface(r, center, z) for r, z in lifted],
                )
            )
            continue
        width: float
        for width in (-FLUTE_HALF_WIDTH, FLUTE_HALF_WIDTH):
            runs.append(
                (
                    "sketch.spline3d",
                    _helix(
                        lifted[shoulder],
                        lifted[-1][1],
                        center,
                        width,
                        helix,
                    ),
                )
            )
    return runs


# Function `tool_flute_runs()`:
def tool_flute_runs(key: str, tool: dict[str, object]) -> list[FluteRun]:
    """Return the lines that stand for a shop tool's flutes.

    Arguments:
    * `key` (`str`): The list the tool is in, in its tools file.
    * `tool` (`dict[str, object]`): The tool, from `shops.read()`.

    Returns:
    * (`list[FluteRun]`): The lines (inches); none for a kind of tool
      with no known flutes.
    """
    path: Profile = flute_path(key, tool)
    if not path:
        return []
    flutes: int = cast(int, tool.get("flutes", DEFAULT_FLUTES))
    return flute_runs(path, flutes, HELIX_ANGLES.get(key, 0.0))


# Function `flute_steps()`:
def flute_steps(
    name: str,
    runs: Sequence[FluteRun],
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
    mm_per_unit: float = MM_PER_INCH,
) -> list[SCStep]:
    """Return the steps that draw flute lines as a whole 3D sketch.

    Arguments:
    * `name` (`str`): The sketch's name.
    * `runs` (`Sequence[FluteRun]`): The lines.
    * `at` (`tuple[float, float, float]`):
      Where the lines' origin goes, in their unit.
    * `mm_per_unit` (`float`): The scale to millimeters.

    Returns:
    * (`list[SCStep]`): The steps, for `send_batch()`.
    """
    drawing: list[SCStep] = [
        {
            "command": command,
            "params": {
                "points": [
                    [
                        (value + place) * mm_per_unit
                        for value, place in zip(point, at, strict=True)
                    ]
                    for point in points
                ]
            },
        }
        for command, points in runs
    ]
    return sketch_steps(name, drawing)


# Function `as_component()`:
def as_component(solidcraft: SCPyBind, body: str, sketch: str) -> str:
    """Put a body and its sketch in a new component, free to move.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `body` (`str`): The body's name.
    * `sketch` (`str`): The sketch's name.

    Returns:
    * (`str`): The name of the component's occurrence, for
      `occurrence.move`.
    """
    # Make the component, and move the sketch into it.
    made: JSON = solidcraft.component.from_bodies(bodies=[body])
    assert isinstance(made, dict) and isinstance(made["components"], list)
    entry: JSON = made["components"][0]
    assert isinstance(entry, dict)
    solidcraft.component.move_sketches(
        sketches=[sketch], component=entry["component"]
    )

    # Find its occurrence, and unground it (a design's first component
    # is grounded, and can not move).
    listed: JSON = solidcraft.component.list(compact=True)
    assert isinstance(listed, dict) and isinstance(listed["components"], list)
    occurrence: str = next(
        str(found["name"])
        for component in listed["components"]
        if isinstance(component, dict)
        and component["id"] == entry["component"]
        and isinstance(component["occurrences"], list)
        for found in component["occurrences"]
        if isinstance(found, dict)
    )
    solidcraft.occurrence.ground(occurrence=occurrence, grounded=False)
    return occurrence


# Function `shop_tools()`:
def shop_tools(
    shop: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Return every tool of a shop, loaded or not, by `unique_id`.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.

    Returns:
    * (`list[tuple[str, dict[str, object]]]`):
      Each tool's list in the tools files (a key of `CNC_KINDS`), and
      its description.
    """
    found: list[tuple[str, dict[str, object]]] = []
    for tools_file in cast(list[dict[str, object]], shop.get("tools", [])):
        for key in CNC_KINDS:
            for tool in cast(list[dict[str, object]], tools_file.get(key, [])):
                found.append((key, tool))
    return sorted(found, key=lambda item: cast(int, item[1]["unique_id"]))


# Function `unique_id_digits()`:
def unique_id_digits(tools: Sequence[tuple[str, dict[str, object]]]) -> int:
    """Return how many digits the longest `unique_id` has.

    Arguments:
    * `tools` (`Sequence[tuple[str, dict[str, object]]]`):
      The tools, from `shop_tools()`.

    Returns:
    * (`int`): The number of digits (at least 1).
    """
    return max((len(str(tool["unique_id"])) for _, tool in tools), default=1)


# Function `holder_bands()`:
def holder_bands(
    tool: dict[str, object], digits: int
) -> list[tuple[str, Profile]]:
    """Return the bands of a tool's holder, from its base to the tool.

    Arguments:
    * `tool` (`dict[str, object]`):
      The tool, with a `holder`, from `shops.read()`.
    * `digits` (`int`): How many bands (from `unique_id_digits()`).

    Returns:
    * (`list[tuple[str, Profile]]`):
      Each band's color, and its profile, with the holder's tool end
      at 0 and its base at `HOLDER_LENGTH`.
    """
    # The cone, whose tool end clears the bore.
    holder: list[str] = cast(list[str], tool["holder"])
    tool_end: float = (measure(holder[-1], LENGTH) + HOLDER_WALL) / 2
    base: float = max(HOLDER_BASE_DIAMETER / 2, tool_end)

    # One slice of it per digit, starting from the base.
    number: str = f"{tool['unique_id']:0{digits}d}"
    bands: list[tuple[str, Profile]] = []
    for index, digit in enumerate(number):
        top: float = 1 - index / digits
        bottom: float = 1 - (index + 1) / digits
        bands.append(
            (
                RESISTOR_COLORS[int(digit)],
                [
                    (0.0, bottom * HOLDER_LENGTH),
                    (
                        tool_end + bottom * (base - tool_end),
                        bottom * HOLDER_LENGTH,
                    ),
                    (tool_end + top * (base - tool_end), top * HOLDER_LENGTH),
                    (0.0, top * HOLDER_LENGTH),
                ],
            )
        )
    return bands


# Function `model()`:
def model(
    solidcraft: SCPyBind,
    name: str,
    outline: Sequence[tuple[float, float]],
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> str:
    """Model a tool in SolidCraft, standing on its tip.

    Its profile is sketched on a plane with sketch X along world X and
    sketch Y along world Z, and revolved about the vertical line at
    `at`.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `name` (`str`): The name for its body and sketch.
    * `outline` (`Sequence[tuple[float, float]]`): Its profile.
    * `at` (`tuple[float, float, float]`):
      Where its profile's `(0, 0)` goes (inches).

    Returns:
    * (`str`): The body's name (SolidCraft may change it, if the
      name is taken).
    """
    # Sketch the profile.
    origin: list[float] = [value * MM_PER_INCH for value in at]
    solidcraft.sketch.create(
        plane={
            "origin": origin,
            "x_dir": [1.0, 0.0, 0.0],
            "y_dir": [0.0, 0.0, 1.0],
        },
        name=f"{name} profile",
    )
    drawn: JSON = solidcraft.sketch.line(
        points=[[r * MM_PER_INCH, z * MM_PER_INCH] for r, z in outline],
        closed=True,
    )
    solidcraft.sketch.finish()
    assert isinstance(drawn, dict)

    # Revolve it.
    revolved: JSON = solidcraft.solid.revolve(
        axis={"origin": origin, "dir": [0.0, 0.0, 1.0]},
        profiles=[{"curves": drawn["curves"]}],
        body_name=name,
    )
    assert isinstance(revolved, dict)
    bodies: JSON = revolved["created_bodies"]
    assert isinstance(bodies, list) and isinstance(bodies[0], str)
    return bodies[0]


# Class `SCModeledTool`:
@dataclass(frozen=True, slots=True)
class SCModeledTool:
    """A tool in SolidCraft: a component with its body and flute lines.

    Attributes:
    * `body` (`str`): Its body's name.
    * `sketch` (`str`): The name of its flute lines' sketch.
    * `occurrence` (`str`): Its component's occurrence, for moving it.

    Constructor:
    * `SCModeledTool(body, sketch, occurrence)`
    """

    # Constructor arguments:
    body: str = field(init=True)
    sketch: str = field(init=True)
    occurrence: str = field(init=True)

    # Method `SCModeledTool.items()`:
    def items(self) -> list[str]:
        """Return what `browser.visibility` shows or hides for the tool.

        Returns:
        * (`list[str]`): The names of its body and its sketch.
        """
        return [self.body, self.sketch]


# Function `model_tool()`:
def model_tool(
    solidcraft: SCPyBind,
    name: str,
    tool: tuple[str, dict[str, object]],
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
    color: str = "",
) -> SCModeledTool:
    """Model a shop's tool: its body and flute lines, in a component.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `name` (`str`): The name for its body, and to start its sketches'.
    * `tool` (`tuple[str, dict[str, object]]`):
      The list it is in, in its tools file, and its description.
    * `at` (`tuple[float, float, float]`):
      Where its tip goes (inches).
    * `color` (`str`): Its color, as `"#rrggbb"`, or `""` for the default.

    Returns:
    * (`SCModeledTool`): What was made, free to move.
    """
    body: str = model(solidcraft, name, profile(*tool), at)
    if color:
        solidcraft.appearance.assign(bodies=[body], color=color)
    sketch: str = f"{name} flutes"
    send_batch(solidcraft, flute_steps(sketch, tool_flute_runs(*tool), at))
    return SCModeledTool(body, sketch, as_component(solidcraft, body, sketch))


# Function `model_holder()`:
def model_holder(
    solidcraft: SCPyBind,
    tool: dict[str, object],
    digits: int,
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[str]:
    """Model a tool's holder in SolidCraft, one body per band.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `tool` (`dict[str, object]`): The tool, with a `holder`.
    * `digits` (`int`): How many bands (from `unique_id_digits()`).
    * `at` (`tuple[float, float, float]`):
      Where the holder's tool end is (inches).

    Returns:
    * (`list[str]`): The bands' body names, from the holder's base.
    """
    bodies: list[str] = []
    for index, (color, outline) in enumerate(holder_bands(tool, digits)):
        body: str = model(
            solidcraft,
            f"Holder {tool['unique_id']} band {index + 1}",
            outline,
            at,
        )
        solidcraft.appearance.assign(
            bodies=[body], color=color, opacity=HOLDER_OPACITY
        )
        bodies.append(body)
    return bodies


# Function `model_shop_tools()`:
def model_shop_tools(solidcraft: SCPyBind, shop: dict[str, object]) -> None:
    """Model every tool of a shop and its holder, in a row along X.

    The tools stand on their tips at Z = 0, with `HOLDER_GRIP` of each
    inside its holder.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.
    """
    tools: list[tuple[str, dict[str, object]]] = shop_tools(shop)
    digits: int = unique_id_digits(tools)
    for index, (key, tool) in enumerate(tools):
        x: float = index * TOOL_SPACING
        model_tool(
            solidcraft,
            f"Tool {tool['unique_id']}",
            (key, tool),
            (x, 0.0, 0.0),
        )
        if "holder" in tool:
            length: float = measure(tool["overall_length"], LENGTH)
            model_holder(
                solidcraft,
                tool,
                digits,
                (x, 0.0, length * (1 - HOLDER_GRIP)),
            )


# Function `main()`:
def main() -> None:
    """Show the example shop's tools in the SolidCraft at a port."""
    target: str = sys.argv[1] if len(sys.argv) > 1 else "8080"
    with connect(target) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.file.new()
        model_shop_tools(solidcraft, read(EXAMPLE_SHOP))


if __name__ == "__main__":
    main()
