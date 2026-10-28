"""3D models of the tools in a shop's tools files, for SolidCraft.

Each tool is drawn as a profile: its radius at each height, from its
tip (at 0) up its shank, as a closed outline of `(r, z)` points
(inches) that starts at the tip on the axis, goes out and up the
tool's side, and comes back down the axis.  Revolving it about the
axis gives the tool.  The sizes come from the tools files (`Shops.md`):
a drill gets a cone at its tip from its `point_angle`, a ball end mill
a rounded end, a chamfer mill a cone down to its `tip_diameter`, a
corner rounding mill its hollow quarter circle, and a double angle
cutter its head on a neck.  Holders are not drawn.

Arcs are drawn as short straight lines, which is plenty for a picture.
"""

# `profile()` names each size it reads, with a type hint, which runs
# past `pylint`'s limit on local variables.
# pylint: disable=too-many-locals

import math
from collections.abc import Sequence

from scraftpybind import JSON, SolidCraftPyBind
from shops import ANGLE, LENGTH, measure

# A profile: `(r, z)` points, in inches.
Profile = list[tuple[float, float]]

# SolidCraft's coordinates are millimeters.
MM_PER_INCH: float = 25.4

# How many straight lines draw a quarter circle.
ARC_STEPS: int = 8


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


# Function `model()`:
def model(
    solidcraft: SolidCraftPyBind,
    name: str,
    outline: Sequence[tuple[float, float]],
) -> str:
    """Model a tool in SolidCraft, standing on its tip at the origin.

    Its profile is sketched on the XZ plane (whose sketch Y is world
    -Z) and revolved about Z.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `name` (`str`): The name for its body and sketch.
    * `outline` (`Sequence[tuple[float, float]]`): Its profile.

    Returns:
    * (`str`): The body's name (SolidCraft may change it, if the
      name is taken).
    """
    # Sketch the profile.
    solidcraft.sketch.create(plane="XZ", name=f"{name} profile")
    drawn: JSON = solidcraft.sketch.line(
        points=[[r * MM_PER_INCH, -z * MM_PER_INCH] for r, z in outline],
        closed=True,
    )
    solidcraft.sketch.finish()
    assert isinstance(drawn, dict)

    # Revolve it.
    revolved: JSON = solidcraft.solid.revolve(
        axis="Z", profiles=[{"curves": drawn["curves"]}], body_name=name
    )
    assert isinstance(revolved, dict)
    bodies: JSON = revolved["created_bodies"]
    assert isinstance(bodies, list) and isinstance(bodies[0], str)
    return bodies[0]
