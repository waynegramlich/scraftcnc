#!/usr/bin/env python3
"""Write `Tool_Models.md` and its sketches, from the code.

Each kind of model has one `ModelPage`: a sample of it, and where the
dimensions go on its sketch.  Everything else comes from elsewhere, so
that the document can not disagree with the code: each size's letter
and meaning from the schema in `shops.py`, and the sketch's outline
from `cutter_models.profile()`.  A test keeps the files in step:

```
python3 -m scraftcam.tooling.tool_models
```
"""

# `sketch()` names each part of its page, with a type hint, which runs
# past `pylint`'s limit on local variables.
# pylint: disable=too-many-locals

# Each kind of model adds its marks here, so it will keep growing.
# pylint: disable=too-many-lines

import ast
import inspect
import json
import math
import textwrap
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TypeAlias

from .. import shops
from ..geometry import ArcSegment, RoundedPolygon, XYSegment
from ..pybind import scraftpybind
from ..shops import (
    ANGLE,
    KINDS,
    LENGTH,
    TableField,
    check_tool,
    markdown_table,
    measure,
)
from . import cutter_models, tools
from .cutter_models import COUNTERSINK_TIP_FLAT, MM_PER_INCH, Profile, profile
from .tools import (
    GRID_PLATE,
    KURT_D688,
    KURT_JAW_PLATE,
    PARALLEL_HEIGHTS,
    PARALLELS,
    GridPlate,
    JawPlate,
    MachineVise,
    Parallel,
    ViseBlock,
    ViseNotches,
)

# Where the files go.
HERE: Path = Path(__file__).resolve().parents[2]
DOCUMENT: Path = HERE / "Tool_Models.md"
SKETCHES: str = "docs/tool_models"

# The size of a sketch, in pixels per inch of the sample, and around it.
SCALE: float = 100.0
MARGIN: float = 0.25

# How large a sketch is shown, as a share of its drawn size.
SHOWN: float = 0.5

# How far dimension lines stand off the tool, and their details (inches).
STAND_OFF: float = 0.3
ARROW_LENGTH: float = 0.09
ARROW_WIDTH: float = 0.03
LETTER_OFF: float = 0.14
CENTER_LINE_PAST: float = 0.12

# The radius of the arc that marks a point angle (inches).
ANGLE_RADIUS: float = 0.26

# How a sketch's parts are drawn.
TOOL_FILL: str = "#dfe4e8"
INK: str = "#222222"
LETTER_SIZE: int = 18


# Class `Dimension`:
@dataclass(frozen=True, slots=True)
class Dimension:
    """One dimension line on a sketch, in the sample's inches.

    Attributes:
    * `key` (`str`): The key of the size, which gives its letter.
    * `across` (`bool`):
      True for a line across the tool (along X), False for one along
      its axis (along Z).
    * `low` (`float`): Where the line starts, along its own direction.
    * `high` (`float`): Where the line ends, along its own direction.
    * `at` (`float`): Where the line sits, in the other direction.
    * `reach` (`tuple[float, float]`):
      Where the extension lines at `low` and at `high` start on the
      tool, in the other direction.  A `reach` equal to `at` means no
      extension lines, with the letter in line with the line.
    * `letter_shift` (`float`): How far along the line to move its letter.

    Constructor:
    * `Dimension(key, across, low, high, at, reach, letter_shift)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    across: bool = field(init=True)
    low: float = field(init=True)
    high: float = field(init=True)
    at: float = field(init=True)
    reach: tuple[float, float] = field(init=True)
    letter_shift: float = field(init=True, default=0.0)


# Class `Angle`:
@dataclass(frozen=True, slots=True)
class Angle:
    """An included angle on a sketch: an arc around its apex.

    Attributes:
    * `key` (`str`): The key of the angle, which gives its letter.
    * `degrees` (`float`): The angle.
    * `radius` (`float`): The arc's radius (inches).
    * `apex` (`tuple[float, float]`): Its apex, as X and Z in inches.
    * `direction` (`float`):
      The direction that splits it evenly (degrees; 90 is up the tool).
    * `letter_shift` (`float`): How far along X to move its letter.

    Constructor:
    * `Angle(key, degrees, radius, apex, direction, letter_shift)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    degrees: float = field(init=True)
    radius: float = field(init=True)
    apex: tuple[float, float] = field(init=True, default=(0.0, 0.0))
    direction: float = field(init=True, default=90.0)
    letter_shift: float = field(init=True, default=0.0)


# Class `Radius`:
@dataclass(frozen=True, slots=True)
class Radius:
    """A radius on a sketch: a line from an arc's center out to the arc.

    Attributes:
    * `key` (`str`): The key of the radius, which gives its letter.
    * `center` (`tuple[float, float]`): The center, as X and Z in inches.
    * `radius` (`float`): The radius (inches).
    * `direction` (`float`): Which way the line goes (degrees).
    * `letter_at` (`tuple[float, float]`):
      Where its letter goes, from the center, as X and Z in inches.

    Constructor:
    * `Radius(key, center, radius, direction, letter_at)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    center: tuple[float, float] = field(init=True)
    radius: float = field(init=True)
    direction: float = field(init=True)
    letter_at: tuple[float, float] = field(init=True, default=(0.1, 0.11))


# What a sketch marks a size with.
Mark: TypeAlias = Dimension | Angle | Radius


# Class `ModelPage`:
@dataclass(frozen=True, slots=True)
class ModelPage:
    """What `Tool_Models.md` says about one kind of model.

    Attributes:
    * `kind` (`str`): Its kind, a key of `shops.KINDS`.
    * `title` (`str`): Its heading.
    * `sample` (`dict[str, object]`):
      A description of one, used for the sketch and the examples.
    * `dimensions` (`Callable[[dict[str, object]], list[Mark]]`):
      Where the dimension lines and angles go, given the sample.
    * `other_keys` (`tuple[str, ...]`):
      The keys to show that are not dimensions.
    * `unused_keys` (`tuple[str, ...]`):
      The lettered keys that mean nothing for this kind.

    Constructor:
    * `ModelPage(kind, title, sample, dimensions, other_keys,
      unused_keys)`
    """

    # Constructor arguments:
    kind: str = field(init=True)
    title: str = field(init=True)
    sample: dict[str, object] = field(init=True)
    dimensions: Callable[[dict[str, object]], list[Mark]] = field(init=True)
    other_keys: tuple[str, ...] = field(init=True)
    unused_keys: tuple[str, ...] = field(init=True, default=())


# Function `_end_mill_dimensions()`:
def _end_mill_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where an end mill's marks go.

    Arguments:
    * `tool` (`dict[str, object]`): The sample, a bull nose.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    radius: float = measure(tool["diameter"], LENGTH) / 2
    shank: float = measure(tool["shank"], LENGTH) / 2
    cut: float = measure(tool["length_of_cut"], LENGTH)
    length: float = measure(tool["overall_length"], LENGTH)
    corner: float = measure(tool["corner_radius"], LENGTH)
    inner: float = radius - corner
    left: float = -radius - STAND_OFF
    right: float = radius + STAND_OFF
    return [
        Dimension(
            "diameter", True, -radius, radius, -STAND_OFF, (corner, corner)
        ),
        Dimension(
            "shank", True, -shank, shank, length + STAND_OFF, (length, length)
        ),
        Dimension("length_of_cut", False, 0.0, cut, left, (-inner, -radius)),
        Dimension("overall_length", False, 0.0, length, right, (inner, shank)),
        Radius("corner_radius", (inner, corner), corner, -45.0, (-0.02, 0.17)),
    ]


# Function `_drill_dimensions()`:
def _drill_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where a drill's dimension lines and point angle go.

    Arguments:
    * `tool` (`dict[str, object]`): The sample, with a step to its shank.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    radius: float = measure(tool["diameter"], LENGTH) / 2
    shank: float = measure(tool["shank"], LENGTH) / 2
    cut: float = measure(tool["length_of_cut"], LENGTH)
    length: float = measure(tool["overall_length"], LENGTH)
    start: float = length - measure(tool["shank_length"], LENGTH)
    point: float = measure(tool["point_angle"], ANGLE)
    rise: float = radius / math.tan(math.radians(point / 2))
    left: float = -radius - STAND_OFF
    right: float = radius + STAND_OFF
    return [
        Dimension("diameter", True, -radius, radius, -STAND_OFF, (rise, rise)),
        Dimension(
            "shank", True, -shank, shank, length + STAND_OFF, (length, length)
        ),
        Dimension("length_of_cut", False, 0.0, cut, left, (0.0, -radius)),
        Dimension(
            "shank_length", False, start, length, left, (-shank, -shank)
        ),
        Dimension("overall_length", False, 0.0, length, right, (0.0, shank)),
        Angle("point_angle", point, ANGLE_RADIUS, letter_shift=LETTER_OFF),
    ]


# Function `_chamfer_mill_dimensions()`:
def _chamfer_mill_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where a chamfer mill's marks go.

    Arguments:
    * `tool` (`dict[str, object]`): The sample.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    radius: float = measure(tool["diameter"], LENGTH) / 2
    shank: float = measure(tool["shank"], LENGTH) / 2
    tip: float = measure(tool["tip_diameter"], LENGTH) / 2
    length: float = measure(tool["overall_length"], LENGTH)
    angle: float = measure(tool["angle"], ANGLE)
    slope: float = math.tan(math.radians(angle / 2))
    rise: float = (radius - tip) / slope
    return [
        Dimension("tip_diameter", True, -tip, tip, -STAND_OFF, (0.0, 0.0)),
        Dimension(
            "diameter", True, -radius, radius, -2 * STAND_OFF, (rise, rise)
        ),
        Dimension(
            "shank", True, -shank, shank, length + STAND_OFF, (length, length)
        ),
        Dimension(
            "overall_length",
            False,
            0.0,
            length,
            radius + STAND_OFF,
            (tip, shank),
        ),
        Angle(
            "angle",
            angle,
            ANGLE_RADIUS,
            (0.0, -tip / slope),
            letter_shift=LETTER_OFF,
        ),
    ]


# Function `_corner_rounding_mill_dimensions()`:
def _corner_rounding_mill_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where a corner rounding mill's marks go.

    Arguments:
    * `tool` (`dict[str, object]`): The sample.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    round_over: float = measure(tool["radius"], LENGTH)
    shank: float = measure(tool["shank"], LENGTH) / 2
    tip: float = measure(tool["tip_diameter"], LENGTH) / 2
    length: float = measure(tool["overall_length"], LENGTH)
    return [
        Dimension("tip_diameter", True, -tip, tip, -STAND_OFF, (0.0, 0.0)),
        Dimension(
            "shank", True, -shank, shank, length + STAND_OFF, (length, length)
        ),
        Dimension(
            "overall_length",
            False,
            0.0,
            length,
            shank + 2 * STAND_OFF,
            (tip, shank),
        ),
        Radius("radius", (tip + round_over, 0.0), round_over, 135.0),
    ]


# Function `_double_angle_cutter_dimensions()`:
def _double_angle_cutter_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where a double angle cutter's marks go.

    Arguments:
    * `tool` (`dict[str, object]`): The sample.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    radius: float = measure(tool["diameter"], LENGTH) / 2
    shank: float = measure(tool["shank"], LENGTH) / 2
    width: float = measure(tool["width"], LENGTH)
    neck: float = measure(tool["neck_diameter"], LENGTH) / 2
    top: float = width + measure(tool["neck_length"], LENGTH)
    length: float = measure(tool["overall_length"], LENGTH)
    angle: float = measure(tool["angle"], ANGLE)
    edge: float = radius - width / 2 / math.tan(math.radians(angle / 2))
    left: float = -radius - STAND_OFF
    middle: float = (width + top) / 2
    return [
        Dimension(
            "diameter",
            True,
            -radius,
            radius,
            -STAND_OFF,
            (width / 2, width / 2),
        ),
        Dimension(
            "shank", True, -shank, shank, length + STAND_OFF, (length, length)
        ),
        Dimension("width", False, 0.0, width, left, (-edge, -edge)),
        Dimension("neck_length", False, width, top, left, (-edge, -neck)),
        Dimension(
            "neck_diameter",
            True,
            -neck,
            neck,
            middle,
            (middle, middle),
            neck + LETTER_OFF,
        ),
        Dimension(
            "overall_length",
            False,
            0.0,
            length,
            radius + STAND_OFF,
            (edge, shank),
        ),
        Angle("angle", angle, ANGLE_RADIUS * 0.75, (radius, width / 2), 180.0),
    ]


# Function `_countersink_dimensions()`:
def _countersink_dimensions(tool: dict[str, object]) -> list[Mark]:
    """Return where a countersink's marks go, at its lower end.

    Arguments:
    * `tool` (`dict[str, object]`): The sample.

    Returns:
    * (`list[Mark]`): Its marks.
    """
    radius: float = measure(tool["diameter"], LENGTH) / 2
    drill: float = measure(tool["drill_diameter"], LENGTH) / 2
    reach: float = measure(tool["drill_length"], LENGTH)
    length: float = measure(tool["overall_length"], LENGTH)
    angle: float = measure(tool["angle"], ANGLE)
    point: float = measure(tool["point_angle"], ANGLE)
    slope: float = math.tan(math.radians(angle / 2))
    body: float = reach + (radius - drill) / slope
    flat: float = COUNTERSINK_TIP_FLAT * drill
    left: float = -radius - STAND_OFF
    marks: list[Mark] = [
        Dimension(
            "drill_diameter", True, -drill, drill, -STAND_OFF, (0.0, 0.0)
        ),
        Dimension(
            "diameter", True, -radius, radius, -2 * STAND_OFF, (body, body)
        ),
        Dimension("drill_length", False, 0.0, reach, left, (0.0, -drill)),
        Dimension(
            "overall_length",
            False,
            0.0,
            length,
            radius + STAND_OFF,
            (flat, flat if "shank" not in tool else radius),
        ),
        Angle(
            "point_angle",
            point,
            drill,
            (0.0, -flat / math.tan(math.radians(point / 2))),
            letter_shift=LETTER_OFF * 0.8,
        ),
        Angle(
            "angle",
            angle,
            (radius - drill / 2) / math.sin(math.radians(angle / 2)),
            (0.0, reach - drill / slope),
            letter_shift=LETTER_OFF,
        ),
    ]
    if "shank" in tool:
        shank: float = measure(tool["shank"], LENGTH) / 2
        marks.append(
            Dimension(
                "shank",
                True,
                -shank,
                shank,
                length + STAND_OFF,
                (length, length),
            )
        )
    return marks


# The kinds of model, in the order of the document.
PAGES: tuple[ModelPage, ...] = (
    ModelPage(
        "end_mill",
        "End Mill",
        {
            "kind": "end_mill",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "1/2 in",
            "shank": "3/8 in",
            "length_of_cut": "1 in",
            "overall_length": "3 in",
            "flutes": 4,
            "end": "bull_nose",
            "corner_radius": "1/8 in",
        },
        _end_mill_dimensions,
        ("flutes", "end", "material", "finish"),
    ),
    ModelPage(
        "drill",
        "Drill",
        {
            "kind": "drill",
            "material": "HSS",
            "finish": "black oxide",
            "diameter": "5/8 in",
            "shank": "1/2 in",
            "shank_length": "1-1/2 in",
            "length_of_cut": "2-1/2 in",
            "overall_length": "4-1/2 in",
            "point_angle": "118 deg",
        },
        _drill_dimensions,
        ("flutes", "material", "finish"),
    ),
    ModelPage(
        "chamfer_mill",
        "Chamfer Mill",
        {
            "kind": "chamfer_mill",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "1/2 in",
            "shank": "1/2 in",
            "tip_diameter": "1/4 in",
            "overall_length": "2 in",
            "angle": "90 deg",
        },
        _chamfer_mill_dimensions,
        ("flutes", "material", "finish"),
    ),
    ModelPage(
        "corner_rounding_mill",
        "Corner Rounding Mill",
        {
            "kind": "corner_rounding_mill",
            "material": "carbide",
            "finish": "uncoated",
            "radius": "1/4 in",
            "tip_diameter": "1/4 in",
            "shank": "3/4 in",
            "overall_length": "2-1/2 in",
        },
        _corner_rounding_mill_dimensions,
        ("flutes", "material", "finish"),
    ),
    ModelPage(
        "double_angle_cutter",
        "Double Angle Cutter",
        {
            "kind": "double_angle_cutter",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "shank": "1/2 in",
            "width": "3/8 in",
            "neck_diameter": "1/4 in",
            "neck_length": "1/2 in",
            "overall_length": "2-1/2 in",
            "angle": "90 deg",
        },
        _double_angle_cutter_dimensions,
        ("flutes", "material", "finish"),
    ),
    ModelPage(
        "single_countersink",
        "Single End Countersink",
        {
            "kind": "single_countersink",
            "material": "HSS",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "shank": "3/4 in",
            "drill_diameter": "3/8 in",
            "drill_length": "1/2 in",
            "overall_length": "2-1/2 in",
            "angle": "60 deg",
            "point_angle": "90 deg",
        },
        _countersink_dimensions,
        ("flutes", "material", "finish"),
    ),
    ModelPage(
        "double_countersink",
        "Double End Countersink",
        {
            "kind": "double_countersink",
            "material": "HSS",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "drill_diameter": "3/8 in",
            "drill_length": "1/2 in",
            "overall_length": "3 in",
            "angle": "60 deg",
            "point_angle": "90 deg",
        },
        _countersink_dimensions,
        ("flutes", "material", "finish"),
        ("shank",),
    ),
)

# What the Python interface is made of, in the order of the document:
# a module and a name in it, and True to give only the first paragraph
# of its docstring (`PyBind` lists every command there is).
INTERFACE: tuple[tuple[ModuleType, str, bool], ...] = (
    (cutter_models, "model_description", False),
    (cutter_models, "ModeledTool", False),
    (shops, "check_tool", False),
    (shops, "ShopError", False),
    (scraftpybind, "connect", False),
    (scraftpybind, "PyBind", True),
    (scraftpybind, "SolidCraftError", False),
)

# The start of the document.
INTRODUCTION: str = """\
# Tool Models

This document is written by `scraftcam/tooling/tool_models.py`
(`python3 -m scraftcam.tooling.tool_models`), from the code; do not
edit it.

Each model below can be made from a description of it, in any of three
forms, which all have the same keys: JSON on a command line, a Python
dictionary, or an entry in a tools file (`Shops.md`).  The letters on
the sketches mean the same size on every sketch.  The tables give no
values: read a catalog for those, or make them up.  The sketches are of
one sample, so their proportions are only a guide.

A size is a string with its unit (`"1/2 in"`, `"12.7 mm"`).  A length
takes {lengths}.

The JSON and Python forms need a SolidCraft to talk to: a port number,
from `solidcraft --control 8080`, or `headless` for `solidcraft-cli`.
They add the model to the design at the origin, standing on its tip.
A description with a problem is refused before SolidCraft is touched:
the JSON form prints every problem and exits with 1, and the Python
form raises `ShopError`.
"""


# Function `sketch()`:
def sketch(page: ModelPage) -> str:
    """Return a model's sketch, as an SVG file.

    Arguments:
    * `page` (`ModelPage`): The model.

    Returns:
    * (`str`): The SVG file's text.
    """
    # The tool's outline, around its axis, and how far it all reaches.
    key: str
    tool: dict[str, object]
    key, tool = check_tool(page.sample)
    half: Profile = profile(key, tool)
    outline: Profile = half + [(-r, z) for r, z in reversed(half)]
    marks: list[Mark] = page.dimensions(tool)
    dimensions: list[Dimension] = [
        mark for mark in marks if isinstance(mark, Dimension)
    ]
    xs: list[float] = [r for r, _ in outline]
    zs: list[float] = [z for _, z in outline]
    _extend(dimensions, xs, zs)

    # The page, then the tool, and its center line.
    root: ET.Element = _root(xs, zs)
    ET.SubElement(
        root,
        "polygon",
        {
            "points": _points(outline),
            "fill": TOOL_FILL,
            "stroke": INK,
            "stroke-width": "2",
            "stroke-linejoin": "round",
        },
    )
    _line(
        root,
        (0.0, min(z for _, z in outline) - CENTER_LINE_PAST),
        (0.0, max(z for _, z in outline) + CENTER_LINE_PAST),
        dashes="12 4 3 4",
    )

    # The dimension lines, with their letters.
    letters: dict[str, str] = _letters(page)
    for mark in marks:
        if isinstance(mark, Dimension):
            _dimension(root, mark, letters[mark.key])
        elif isinstance(mark, Angle):
            _angle(root, mark, letters[mark.key])
        else:
            _radius(root, mark, letters[mark.key])
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


# Function `_extend()`:
def _extend(
    dimensions: list[Dimension], xs: list[float], zs: list[float]
) -> None:
    """Add how far dimension lines and their letters reach.

    Arguments:
    * `dimensions` (`list[Dimension]`): The dimension lines.
    * `xs` (`list[float]`): The X of everything drawn (inches), added to.
    * `zs` (`list[float]`): The Z of everything drawn (inches), added to.
    """
    for dimension in dimensions:
        (xs if dimension.across else zs).extend(
            (dimension.low, dimension.high)
        )
        sign: float = _away(dimension)
        (zs if dimension.across else xs).append(
            dimension.at + sign * LETTER_OFF * 1.5
        )


# Function `_root()`:
def _root(xs: list[float], zs: list[float]) -> ET.Element:
    """Return a new sketch, with a white background for dark themes.

    Arguments:
    * `xs` (`list[float]`): The X of everything drawn on it (inches).
    * `zs` (`list[float]`): The Z of everything drawn on it (inches).

    Returns:
    * (`ET.Element`): The sketch's `svg` element.
    """
    left: float = (min(xs) - MARGIN) * SCALE
    top: float = (-max(zs) - MARGIN) * SCALE
    width: float = (max(xs) - min(xs) + 2 * MARGIN) * SCALE
    height: float = (max(zs) - min(zs) + 2 * MARGIN) * SCALE
    root: ET.Element = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"{left:.1f} {top:.1f} {width:.1f} {height:.1f}",
            "width": f"{width * SHOWN:.0f}",
            "height": f"{height * SHOWN:.0f}",
        },
    )
    ET.SubElement(
        root,
        "rect",
        {
            "x": f"{left:.1f}",
            "y": f"{top:.1f}",
            "width": f"{width:.1f}",
            "height": f"{height:.1f}",
            "fill": "white",
        },
    )
    return root


# Function `_away()`:
def _away(dimension: Dimension) -> float:
    """Return which way a dimension line stands off the tool.

    Arguments:
    * `dimension` (`Dimension`): The dimension line.

    Returns:
    * (`float`): `1.0` toward larger values, or `-1.0`.
    """
    return 1.0 if dimension.at > dimension.reach[0] else -1.0


# Function `_points()`:
def _points(points: Profile) -> str:
    """Return points as an SVG `points` attribute.

    Arguments:
    * `points` (`Profile`): The points, as X and Z in inches.

    Returns:
    * (`str`): Their pixels, with Y pointing down.
    """
    return " ".join(f"{x * SCALE:.1f},{-z * SCALE:.1f}" for x, z in points)


# Function `_line()`:
def _line(
    root: ET.Element,
    start: tuple[float, float],
    end: tuple[float, float],
    dashes: str = "",
) -> None:
    """Add a thin line to a sketch.

    Arguments:
    * `root` (`ET.Element`): The sketch.
    * `start` (`tuple[float, float]`): One end, as X and Z in inches.
    * `end` (`tuple[float, float]`): The other end.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.
    """
    attributes: dict[str, str] = {
        "x1": f"{start[0] * SCALE:.1f}",
        "y1": f"{-start[1] * SCALE:.1f}",
        "x2": f"{end[0] * SCALE:.1f}",
        "y2": f"{-end[1] * SCALE:.1f}",
        "stroke": INK,
        "stroke-width": "1",
    }
    if dashes:
        attributes["stroke-dasharray"] = dashes
    ET.SubElement(root, "line", attributes)


# Function `_dimension()`:
def _dimension(root: ET.Element, dimension: Dimension, letter: str) -> None:
    """Add a dimension line, its arrows and its letter to a sketch.

    Arguments:
    * `root` (`ET.Element`): The sketch.
    * `dimension` (`Dimension`): The dimension line.
    * `letter` (`str`): Its letter.
    """

    # Turn a point along and off the line into X and Z.
    def place(along: float, off: float) -> tuple[float, float]:
        return (along, off) if dimension.across else (off, along)

    # The extension lines from the tool, then the line itself.
    low: float = dimension.low
    high: float = dimension.high
    at: float = dimension.at
    sign: float = _away(dimension)
    past: float = sign * ARROW_LENGTH / 2
    bare: bool = at == dimension.reach[0]
    if not bare:
        _line(root, place(low, dimension.reach[0]), place(low, at + past))
        _line(root, place(high, dimension.reach[1]), place(high, at + past))
    _line(root, place(low, at), place(high, at))

    # An arrow at each end, pointing out along the line.
    for tip, inward in ((low, ARROW_LENGTH), (high, -ARROW_LENGTH)):
        arrow: Profile = [
            place(tip, at),
            place(tip + inward, at + ARROW_WIDTH),
            place(tip + inward, at - ARROW_WIDTH),
        ]
        ET.SubElement(root, "polygon", {"points": _points(arrow), "fill": INK})

    # The letter, beyond the middle of the line.
    x: float
    z: float
    x, z = place(
        (low + high) / 2 + dimension.letter_shift,
        at if bare else at + sign * LETTER_OFF,
    )
    _letter(root, x, z, letter)


# Function `_letter()`:
def _letter(root: ET.Element, x: float, z: float, letter: str) -> None:
    """Add a dimension's letter to a sketch.

    Arguments:
    * `root` (`ET.Element`): The sketch.
    * `x` (`float`): Its center's X, in inches.
    * `z` (`float`): Its center's Z, in inches.
    * `letter` (`str`): The letter.
    """
    text: ET.Element = ET.SubElement(
        root,
        "text",
        {
            "x": f"{x * SCALE:.1f}",
            "y": f"{-z * SCALE + LETTER_SIZE * 0.35:.1f}",
            "font-family": "sans-serif",
            "font-size": str(LETTER_SIZE),
            "font-weight": "bold",
            "text-anchor": "middle",
            "fill": INK,
        },
    )
    text.text = letter


# Function `_angle()`:
def _angle(root: ET.Element, angle: Angle, letter: str) -> None:
    """Add an included angle's arc, arrows and letter to a sketch.

    Arguments:
    * `root` (`ET.Element`): The sketch.
    * `angle` (`Angle`): The angle.
    * `letter` (`str`): Its letter.
    """

    # Turn a direction (radians) and a distance into a point.
    def point(direction: float, distance: float) -> tuple[float, float]:
        return (
            angle.apex[0] + distance * math.cos(direction),
            angle.apex[1] + distance * math.sin(direction),
        )

    # The arc, counterclockwise from one edge to the other.
    middle: float = math.radians(angle.direction)
    half: float = math.radians(angle.degrees / 2)
    start: tuple[float, float] = point(middle - half, angle.radius)
    end: tuple[float, float] = point(middle + half, angle.radius)
    pixels: float = angle.radius * SCALE
    ET.SubElement(
        root,
        "path",
        {
            "d": (
                f"M {start[0] * SCALE:.1f} {-start[1] * SCALE:.1f} "
                f"A {pixels:.1f} {pixels:.1f} 0 0 0 "
                f"{end[0] * SCALE:.1f} {-end[1] * SCALE:.1f}"
            ),
            "fill": "none",
            "stroke": INK,
            "stroke-width": "1",
        },
    )

    # An arrow at each end, pointing along the arc, away from the middle.
    turn: float = ARROW_LENGTH / angle.radius
    wide: float = ARROW_WIDTH
    for tip, base in (
        (middle - half, middle - half + turn),
        (middle + half, middle + half - turn),
    ):
        arrow: Profile = [
            point(tip, angle.radius),
            point(base, angle.radius + wide),
            point(base, angle.radius - wide),
        ]
        ET.SubElement(root, "polygon", {"points": _points(arrow), "fill": INK})

    # The letter, past the middle of the arc, and shifted if asked.
    x: float
    z: float
    x, z = point(middle, angle.radius + LETTER_OFF * 0.8)
    _letter(root, x + angle.letter_shift, z, letter)


# Function `_radius()`:
def _radius(root: ET.Element, radius: Radius, letter: str) -> None:
    """Add a radius's line, arrow and letter to a sketch.

    Arguments:
    * `root` (`ET.Element`): The sketch.
    * `radius` (`Radius`): The radius.
    * `letter` (`str`): Its letter.
    """
    # The line, from the arc's center out to the arc.
    across: float = math.cos(math.radians(radius.direction))
    up: float = math.sin(math.radians(radius.direction))
    x: float = radius.center[0]
    z: float = radius.center[1]
    far: float = radius.radius
    near: float = far - ARROW_LENGTH
    _line(root, (x, z), (x + far * across, z + far * up))
    arrow: Profile = [
        (x + far * across, z + far * up),
        (
            x + near * across - ARROW_WIDTH * up,
            z + near * up + ARROW_WIDTH * across,
        ),
        (
            x + near * across + ARROW_WIDTH * up,
            z + near * up - ARROW_WIDTH * across,
        ),
    ]
    ET.SubElement(root, "polygon", {"points": _points(arrow), "fill": INK})

    # The letter.
    _letter(root, x + radius.letter_at[0], z + radius.letter_at[1], letter)


# Function `_fields()`:
def _fields(kind: str) -> dict[str, TableField]:
    """Return the keys of a kind.

    Arguments:
    * `kind` (`str`): The kind.

    Returns:
    * (`dict[str, TableField]`): Its keys, by name.
    """
    return {schema.key: schema for schema in KINDS[kind].fields}


# Function `_letters()`:
def _letters(page: ModelPage) -> dict[str, str]:
    """Return the letters of a model's sizes.

    Arguments:
    * `page` (`ModelPage`): The model.

    Returns:
    * (`dict[str, str]`): Each lettered key's letter.
    """
    return {
        schema.key: schema.letter
        for schema in KINDS[page.kind].fields
        if schema.letter and schema.key not in page.unused_keys
    }


# Function `_toml()`:
def _toml(page: ModelPage) -> str:
    """Return a model's sample as an entry in a tools file.

    Arguments:
    * `page` (`ModelPage`): The model.

    Returns:
    * (`str`): The TOML, with what a tools file also requires.
    """
    entries: dict[str, object] = {
        "name": f"Sample {page.title.lower()}",
        "unique_id": 1,
        **{k: v for k, v in page.sample.items() if k != "kind"},
    }
    lines: list[str] = [f"[[{page.kind}s]]"]
    lines += [f"{key} = {json.dumps(val)}" for key, val in entries.items()]
    return "\n".join(lines) + "\n"


# Function `_python()`:
def _python(page: ModelPage) -> str:
    """Return a model's sample as a Python program.

    Arguments:
    * `page` (`ModelPage`): The model.

    Returns:
    * (`str`): The program.
    """
    entries: str = "".join(
        f"            {json.dumps(key)}: {json.dumps(val)},\n"
        for key, val in page.sample.items()
    )
    return (
        "from scraftcam.pybind.scraftpybind import PyBind, connect\n"
        "from scraftcam.tooling.cutter_models import model_description\n"
        "\n"
        'with connect("8080") as transport:\n'
        "    model_description(\n"
        "        PyBind(transport),\n"
        "        {\n"
        f"{entries}"
        "        },\n"
        "    )\n"
    )


# Function `_signature()`:
def _signature(shown: str, node: ast.FunctionDef) -> str:
    """Return a function's signature, as its source has it.

    Arguments:
    * `shown` (`str`): The name to give it.
    * `node` (`ast.FunctionDef`): The function.

    Returns:
    * (`str`): The signature, one argument a line if it is long.
    """
    # Each argument, with its type hint and any default.
    arguments: ast.arguments = node.args
    defaults: list[ast.expr | None] = [None] * (
        len(arguments.args) - len(arguments.defaults)
    ) + list(arguments.defaults)
    parts: list[str] = []
    for argument, default in zip(arguments.args, defaults, strict=True):
        if argument.annotation is not None:
            part: str = f"{argument.arg}: {ast.unparse(argument.annotation)}"
            if default is not None:
                part += f" = {ast.unparse(default)}"
            parts.append(part)

    # It all, without the `None` that an `__init__()` returns.
    returns: str = ""
    if node.returns is not None and node.name != "__init__":
        returns = f" -> {ast.unparse(node.returns)}"
    line: str = f"{shown}({', '.join(parts)}){returns}"
    if len(line) <= 79:
        return line
    listed: str = "".join(f"    {part},\n" for part in parts)
    return f"{shown}(\n{listed}){returns}"


# Function `_constructor()`:
def _constructor(shown: str, node: ast.ClassDef) -> str:
    """Return how a class is constructed, as its source has it.

    Arguments:
    * `shown` (`str`): The name to give it.
    * `node` (`ast.ClassDef`): The class.

    Returns:
    * (`str`): Its `__init__()`'s signature, or a dataclass's made from
      its `init=True` fields.
    """
    parts: list[str] = []
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return _signature(shown, item)
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and "init=True" in ast.unparse(item)
        ):
            hint: str = ast.unparse(item.annotation)
            parts.append(f"{item.target.id}: {hint}")
    line: str = f"{shown}({', '.join(parts)})"
    if len(line) <= 79:
        return line
    listed: str = "".join(f"    {part},\n" for part in parts)
    return f"{shown}(\n{listed})"


# Function `_interface_entry()`:
def _interface_entry(module: ModuleType, name: str, brief: bool) -> str:
    """Return one function or class of the Python interface.

    Arguments:
    * `module` (`ModuleType`): Its module.
    * `name` (`str`): Its name.
    * `brief` (`bool`): True for only its docstring's first paragraph.

    Returns:
    * (`str`): Its heading, signatures and docstring, in Markdown.
    """
    # Find its source, and what its docstring says.
    assert module.__file__ is not None
    source: str = Path(module.__file__).read_text(encoding="utf-8")
    shown: str = f"{module.__name__}.{name}"
    node: ast.stmt = next(
        item
        for item in ast.parse(source).body
        if getattr(item, "name", "") == name
    )
    doc: str = inspect.getdoc(getattr(module, name)) or ""
    doc = doc.split("\n\nConstructor:", maxsplit=1)[0]
    if brief:
        doc = doc.split("\n\n", maxsplit=1)[0]

    # The signatures: a class's, then those of its public methods.
    signatures: list[str] = []
    methods: str = ""
    if isinstance(node, ast.FunctionDef):
        signatures.append(_signature(shown, node))
    elif isinstance(node, ast.ClassDef):
        signatures.append(_constructor(shown, node))
        if not brief:
            for item in node.body:
                if isinstance(
                    item, ast.FunctionDef
                ) and not item.name.startswith("_"):
                    method: str = f"{name}.{item.name}"
                    summary: str = (ast.get_docstring(item) or "").split(
                        "\n\n", maxsplit=1
                    )[0]
                    methods += (
                        f"\n\n```python\n{_signature(method, item)}\n```"
                        f"\n\n{summary}"
                    )
    code: str = "\n".join(signatures)
    return f"### `{shown}`\n\n```python\n{code}\n```\n\n{doc}{methods}\n"


# Function `section()`:
def section(page: ModelPage) -> str:
    """Return a model's section of the document.

    Arguments:
    * `page` (`ModelPage`): The model.

    Returns:
    * (`str`): Its Markdown.
    """
    # The dimensions, by letter.
    fields: dict[str, TableField] = _fields(page.kind)
    rows: list[list[str]] = [["Letter", "Units", "Description"]]
    for key, letter in sorted(
        _letters(page).items(), key=lambda item: item[1]
    ):
        schema: TableField = fields[key]
        required: str = "" if schema.required else "Optional.  "
        rows.append(
            [
                f"`{letter}`",
                schema.shown().capitalize(),
                f"`{key}`: {required}{schema.meaning}",
            ]
        )

    # The keys that are not dimensions.
    others: str = "\n".join(
        textwrap.fill(
            f"* `{key}` ({fields[key].shown()}): {fields[key].meaning}",
            72,
            subsequent_indent="  ",
        )
        for key in page.other_keys
    )

    # The whole section.
    summary: str = textwrap.fill(KINDS[page.kind].summary, 72)
    described: str = json.dumps(page.sample, indent=2)
    return (
        f"## {page.title}\n\n"
        f"{summary}\n\n"
        f"![{page.title} sketch]({SKETCHES}/{page.kind}.svg)\n\n"
        f"{markdown_table(rows)}\n\n"
        f"Other keys:\n\n{others}\n\n"
        "JSON:\n\n```\npython3 -m scraftcam.tooling.cutter_models 8080 "
        f"'{described}'\n```\n\n"
        f"Python:\n\n```python\n{_python(page)}```\n\n"
        f"A tools file:\n\n```toml\n{_toml(page)}```\n"
    )


# Class `ViewShape`:
@dataclass(frozen=True, slots=True)
class ViewShape:
    """One shape in a view of a model.

    Attributes:
    * `path` (`str`): Its SVG path, in pixels.
    * `points` (`Profile`):
      Points that reach as far as it does, as X and Z in inches.
    * `fill` (`str`): Its fill color, or `"none"`.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.

    Constructor:
    * `ViewShape(path, points, fill, dashes)`
    """

    # Constructor arguments:
    path: str = field(init=True)
    points: Profile = field(init=True)
    fill: str = field(init=True, default=TOOL_FILL)
    dashes: str = field(init=True, default="")


# Class `View`:
@dataclass(frozen=True, slots=True)
class View:
    """One view of a model of tooling, drawn from its numbers.

    Attributes:
    * `name` (`str`): The view's name, which names its file.
    * `title` (`str`): What the document calls it.
    * `shapes` (`list[ViewShape]`): What is drawn, farthest first.
    * `marks` (`list[Mark]`):
      Its dimension lines and radii, whose keys are paths such as
      `base.length`.

    Constructor:
    * `View(name, title, shapes, marks)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    title: str = field(init=True)
    shapes: list[ViewShape] = field(init=True)
    marks: list[Mark] = field(init=True)


# The machine vise that its page is drawn from, and the space between
# rows of dimension lines (inches).
VISE: MachineVise = KURT_D688
VISE_NAME: str = "KURT_D688"
ROW: float = 0.4

# How the floor of a pocket and hidden edges are drawn.
POCKET_FILL: str = "#aab4bd"
HIDDEN: str = "8 5"
CENTER_LINE: str = "12 4 3 4"


# Function `_in()`:
def _in(millimeters: float) -> float:
    """Return a length in inches.

    Arguments:
    * `millimeters` (`float`): The length (millimeters).

    Returns:
    * (`float`): The length (inches).
    """
    return millimeters / MM_PER_INCH


# Function `_xy()`:
def _xy(x: float, z: float) -> str:
    """Return a point as SVG path pixels.

    Arguments:
    * `x` (`float`): Its X (inches).
    * `z` (`float`): Its Z (inches), which points up.

    Returns:
    * (`str`): Its pixels, with Y pointing down.
    """
    return f"{x * SCALE:.1f} {-z * SCALE:.1f}"


# Function `_rectangle()`:
def _rectangle(
    low: tuple[float, float],
    high: tuple[float, float],
    fill: str = TOOL_FILL,
    dashes: str = "",
) -> ViewShape:
    """Return a rectangle.

    Arguments:
    * `low` (`tuple[float, float]`): Its lowest X and Z (inches).
    * `high` (`tuple[float, float]`): Its highest X and Z (inches).
    * `fill` (`str`): Its fill color, or `"none"`.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.

    Returns:
    * (`ViewShape`): The rectangle.
    """
    corners: Profile = [
        low,
        (high[0], low[1]),
        high,
        (low[0], high[1]),
    ]
    return _polygon(corners, fill, dashes)


# Function `_polygon()`:
def _polygon(
    corners: Profile, fill: str = TOOL_FILL, dashes: str = ""
) -> ViewShape:
    """Return a polygon.

    Arguments:
    * `corners` (`Profile`): Its corners, as X and Z in inches.
    * `fill` (`str`): Its fill color, or `"none"`.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.

    Returns:
    * (`ViewShape`): The polygon.
    """
    path: str = "M " + " L ".join(_xy(x, z) for x, z in corners) + " Z"
    return ViewShape(path, corners, fill, dashes)


# Function `_circle()`:
def _circle(
    center: tuple[float, float],
    radius: float,
    fill: str = TOOL_FILL,
    dashes: str = "",
) -> ViewShape:
    """Return a circle.

    Arguments:
    * `center` (`tuple[float, float]`): Its center (inches).
    * `radius` (`float`): Its radius (inches).
    * `fill` (`str`): Its fill color, or `"none"`.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.

    Returns:
    * (`ViewShape`): The circle, as two half circles.
    """
    x, z = center
    pixels: float = radius * SCALE
    arc: str = f"A {pixels:.1f} {pixels:.1f} 0 0 0"
    path: str = (
        f"M {_xy(x - radius, z)} {arc} {_xy(x + radius, z)} "
        f"{arc} {_xy(x - radius, z)} Z"
    )
    points: Profile = [(x - radius, z - radius), (x + radius, z + radius)]
    return ViewShape(path, points, fill, dashes)


# Function `_outline()`:
def _outline(
    polygon: RoundedPolygon, fill: str = TOOL_FILL, dashes: str = ""
) -> ViewShape:
    """Return an outline seen from above, with true arcs.

    Arguments:
    * `polygon` (`RoundedPolygon`): The outline (millimeters).
    * `fill` (`str`): Its fill color, or `"none"`.
    * `dashes` (`str`): An SVG `stroke-dasharray`, or `""` for none.

    Returns:
    * (`ViewShape`): The outline, with X and Y as the sketch's X and Z.
    """
    segments: tuple[XYSegment, ...] = polygon.segments
    start: tuple[float, float] = segments[0].start
    path: str = f"M {_xy(_in(start[0]), _in(start[1]))}"
    points: Profile = []
    for segment in segments:
        x: float = _in(segment.end[0])
        z: float = _in(segment.end[1])
        points.append((x, z))
        if isinstance(segment, ArcSegment):
            # Y points down in SVG, so a counter-clockwise arc has a
            # sweep flag of 0.
            pixels: float = _in(segment.radius) * SCALE
            large: int = 1 if abs(segment.sweep) > math.pi else 0
            sweep: int = 0 if segment.sweep > 0.0 else 1
            path += f" A {pixels:.1f} {pixels:.1f} 0 {large} {sweep}"
            path += f" {_xy(x, z)}"
        else:
            path += f" L {_xy(x, z)}"
    return ViewShape(path + " Z", points, fill, dashes)


# Function `_center_line()`:
def _center_line(
    across: bool, at: float, low: float, high: float
) -> ViewShape:
    """Return a center line, reaching past what it centers.

    Arguments:
    * `across` (`bool`): True for a line along X, False for one along Z.
    * `at` (`float`): Where it sits, in the other direction (inches).
    * `low` (`float`): Where what it centers starts (inches).
    * `high` (`float`): Where what it centers ends (inches).

    Returns:
    * (`ViewShape`): The line, unfilled.
    """
    ends: Profile = [
        (low - CENTER_LINE_PAST, at),
        (high + CENTER_LINE_PAST, at),
    ]
    if not across:
        ends = [(x, z) for z, x in ends]
    path: str = f"M {_xy(*ends[0])} L {_xy(*ends[1])}"
    return ViewShape(path, ends, "none", CENTER_LINE)


# Class `_ViseSizes`:
# It holds one number for each place that the views measure from.
@dataclass(frozen=True, slots=True)
class _ViseSizes:  # pylint: disable=too-many-instance-attributes
    """Where the parts of the machine vise's sample are, in inches.

    X is along the lead screw, toward the hexagon; Y across; Z up from
    the bottom of the base.  The jaws are as far open as they go.

    Attributes (alphabetized):
    * `bed_bottom` (`float`): The Z of the bottom of the bed.
    * `bed_top` (`float`): The Z of the top of the bed.
    * `face` (`float`): The X of the movable jaw's clamping face.
    * `fixed_face` (`float`): The X of the fixed jaw's clamping face.
    * `gap` (`float`): Half of the gap between the rails.
    * `half` (`float`): Half of the body's length.
    * `hex_end` (`float`): The X of the end of the hexagon.
    * `jaw_top` (`float`): The Z of the top of the jaws.
    * `moving_end` (`float`): The X of the end of the movable jaw.
    * `outer` (`float`): The Y of the rails' outer sides.
    * `plate` (`float`): A jaw plate's thickness.
    * `screw_z` (`float`): The Z of the lead screw's axis.
    * `stick` (`float`): The X of the end of the lead screw's cylinder.

    Constructor:
    * `_ViseSizes()`
    """

    # Attributes set by `__post_init__()` (alphabetized):
    bed_bottom: float = field(init=False, default=0.0)
    bed_top: float = field(init=False, default=0.0)
    face: float = field(init=False, default=0.0)
    fixed_face: float = field(init=False, default=0.0)
    gap: float = field(init=False, default=0.0)
    half: float = field(init=False, default=0.0)
    hex_end: float = field(init=False, default=0.0)
    jaw_top: float = field(init=False, default=0.0)
    moving_end: float = field(init=False, default=0.0)
    outer: float = field(init=False, default=0.0)
    plate: float = field(init=False, default=0.0)
    screw_z: float = field(init=False, default=0.0)
    stick: float = field(init=False, default=0.0)

    # Method `_ViseSizes.__post_init__()`:
    def __post_init__(self) -> None:
        """Work out where the parts are."""
        v: MachineVise = VISE
        sizes: dict[str, float] = {
            "bed_bottom": v.base.height + v.body.height,
            "bed_top": v.bed_top(),
            "face": v.movable_face(v.max_opening),
            "fixed_face": -v.body.length / 2.0 + v.fixed_jaw.length,
            "gap": v.rail_gap / 2.0,
            "half": v.body.length / 2.0,
            "hex_end": v.body.length / 2.0
            + v.lead_screw_stick_out
            + v.hex_length,
            "jaw_top": v.bed_top() + v.fixed_jaw.height,
            "moving_end": v.movable_face(v.max_opening) + v.movable_jaw.length,
            "outer": v.rail_gap / 2.0 + v.rail_width,
            "plate": v.jaw_plate.length,
            "screw_z": v.lead_screw_height,
            "stick": v.body.length / 2.0 + v.lead_screw_stick_out,
        }
        for name, millimeters in sizes.items():
            object.__setattr__(self, name, _in(millimeters))


# Function `_hexagon()`:
def _hexagon() -> Profile:
    """Return the corners of the hexagon on the lead screw's end.

    Returns:
    * (`Profile`): Each corner's Y and Z from the lead screw's axis
      (inches).
    """
    return [(_in(y), _in(z)) for y, z in VISE.hexagon()]


# Function `_vise_top()`:
def _vise_top(s: _ViseSizes) -> View:
    """Return the machine vise seen from above.

    Arguments:
    * `s` (`_ViseSizes`): Where its parts are.

    Returns:
    * (`View`): The view, X to the right and Y up.
    """
    # The pocket's floor and the lead screw in it, the bed, the jaws and
    # their plates, then the lead screw's end.
    v: MachineVise = VISE
    end: float = _in(v.end_block_length)
    screw: float = _in(v.lead_screw_diameter) / 2.0
    hex_y: float = max(y for y, _ in _hexagon())
    jaw: float = _in(v.fixed_jaw.width) / 2.0
    plate: float = _in(v.jaw_plate.width) / 2.0
    moving: float = _in(v.movable_jaw.width) / 2.0
    blocks: list[tuple[float, float]] = [
        (-s.half, -s.half + end),
        (s.half - end, s.half),
    ]
    shapes: list[ViewShape] = [
        _rectangle(
            (-s.half + end, -s.gap), (s.half - end, s.gap), POCKET_FILL
        ),
        _rectangle((-s.half + end, -screw), (s.half, screw)),
        _rectangle((-s.half, s.gap), (s.half, s.outer)),
        _rectangle((-s.half, -s.outer), (s.half, -s.gap)),
        *[_rectangle((low, -s.gap), (high, s.gap)) for low, high in blocks],
        _rectangle((-s.half, -jaw), (s.fixed_face, jaw)),
        _rectangle((s.fixed_face, -plate), (s.fixed_face + s.plate, plate)),
        _rectangle((s.face - s.plate, -plate), (s.face, plate)),
        _rectangle((s.face, -moving), (s.moving_end, moving)),
        _rectangle((s.half, -screw), (s.stick, screw)),
        _rectangle((s.stick, -hex_y), (s.hex_end, hex_y)),
    ]

    # Hidden: the base and the body with their notches, and the end
    # blocks under the jaws; and the center line.
    shapes += [
        _outline(
            v.base.outline("base", notches=v.base_notches), "none", HIDDEN
        ),
        _outline(
            v.body.outline("body", notches=v.body_notches), "none", HIDDEN
        ),
        *[
            _rectangle((low, -s.gap), (high, s.gap), "none", HIDDEN)
            for low, high in blocks
        ],
        _center_line(False, 0.0, -s.outer, s.outer),
    ]
    return View("top", "Top", shapes, _vise_top_marks(s))


# Function `_vise_top_marks()`:
def _vise_top_marks(s: _ViseSizes) -> list[Mark]:
    """Return the dimension lines and radii of the view from above.

    Arguments:
    * `s` (`_ViseSizes`): Where the parts are.

    Returns:
    * (`list[Mark]`): The marks.
    """
    # The lengths along the top, from the fixed jaw out to the hexagon.
    v: MachineVise = VISE
    end: float = _in(v.end_block_length)
    screw: float = _in(v.lead_screw_diameter) / 2.0
    hex_y: float = max(y for y, _ in _hexagon())
    jaw: float = _in(v.fixed_jaw.width) / 2.0
    above: float = s.outer + STAND_OFF
    marks: list[Mark] = [
        Dimension(
            "fixed_jaw.length", True, -s.half, s.fixed_face, above, (jaw, jaw)
        ),
        Dimension(
            "max_opening",
            True,
            s.fixed_face + s.plate,
            s.face - s.plate,
            above,
            (jaw, jaw),
        ),
        Dimension(
            "movable_jaw.length", True, s.face, s.moving_end, above, (jaw, jaw)
        ),
        Dimension(
            "lead_screw_stick_out",
            True,
            s.half,
            s.stick,
            above,
            (screw, screw),
        ),
        Dimension(
            "hex_length", True, s.stick, s.hex_end, above, (hex_y, hex_y)
        ),
        Dimension(
            "base.length", True, -s.half, s.half, above + ROW, (above, above)
        ),
    ]

    # Below: the notches, the screw end's end block, and the body.
    base_y: float = -_in(v.base.width) / 2.0
    body_y: float = -_in(v.body.width) / 2.0
    base_x: float = _in(v.base_notches.centers[-1])
    body_x: float = _in(v.body_notches.centers[0])
    base_w: float = _in(v.base_notches.width) / 2.0
    body_w: float = _in(v.body_notches.width) / 2.0
    below: float = -s.outer - STAND_OFF
    marks += [
        Dimension(
            "body_notches.width",
            True,
            body_x - body_w,
            body_x + body_w,
            below,
            (body_y, body_y),
        ),
        Dimension(
            "base_notches.width",
            True,
            base_x - base_w,
            base_x + base_w,
            below,
            (base_y, base_y),
        ),
        Dimension(
            "end_block_length",
            True,
            s.half - end,
            s.half,
            below,
            (-s.gap, -s.gap),
        ),
        Dimension(
            "body_notches.centers",
            True,
            body_x,
            0.0,
            below - ROW,
            (body_y + _in(v.body_notches.depth), below - ROW),
        ),
        Dimension(
            "base_notches.centers",
            True,
            0.0,
            base_x,
            below - ROW,
            (below - ROW, base_y + _in(v.base_notches.depth)),
        ),
        Dimension(
            "body.length",
            True,
            -s.half,
            s.half,
            below - 2 * ROW,
            (body_y, body_y),
        ),
    ]

    # The notches' depths, beside them, and the rails, past the hexagon.
    base_out: float = base_x + base_w + STAND_OFF
    body_out: float = body_x - body_w - STAND_OFF
    past: float = s.hex_end + STAND_OFF
    marks += [
        Dimension(
            "base_notches.depth",
            False,
            base_y,
            base_y + _in(v.base_notches.depth),
            base_out,
            (base_x + base_w, base_x + base_w),
        ),
        Dimension(
            "body_notches.depth",
            False,
            body_y,
            body_y + _in(v.body_notches.depth),
            body_out,
            (body_x - body_w, body_x - body_w),
        ),
        Dimension("rail_width", False, s.gap, s.outer, past, (s.half, s.half)),
        Dimension("rail_gap", False, -s.gap, s.gap, past, (s.half, s.half)),
        Dimension(
            "fixed_jaw.width",
            False,
            -jaw,
            jaw,
            -s.half - STAND_OFF,
            (-s.half, -s.half),
        ),
    ]
    return marks + _vise_radii(s)


# Function `_vise_radii()`:
def _vise_radii(s: _ViseSizes) -> list[Mark]:
    """Return the radii of the view from above.

    The base's are on its +X notch and corner, on the -Y side, and the
    body's on its -X notch and corner.

    Arguments:
    * `s` (`_ViseSizes`): Where the parts are.

    Returns:
    * (`list[Mark]`): The radii.
    """
    v: MachineVise = VISE
    marks: list[Mark] = []
    for name, block, notches, side, corner in (
        ("base", v.base, v.base_notches, 1.0, s.half),
        ("body", v.body, v.body_notches, -1.0, -s.half),
    ):
        # The notch's corners on the side away from the vise's center.
        edge: float = -_in(block.width) / 2.0
        x: float = _in(notches.centers[0 if side < 0 else -1])
        x += side * _in(notches.width) / 2.0
        inner: float = _in(notches.inner_radius)
        outer: float = _in(notches.outer_radius)
        deep: float = edge + _in(notches.depth)
        rounded: float = _in(block.corner_radius)
        marks += [
            Radius(
                f"{name}_notches.inner_radius",
                (x - side * inner, deep - inner),
                inner,
                90.0 + side * 45.0,
                (side * 0.2, 0.3),
            ),
            Radius(
                f"{name}_notches.outer_radius",
                (x + side * outer, edge + outer),
                outer,
                -90.0 - side * 45.0,
                (-side * 0.05, -0.32),
            ),
            Radius(
                f"{name}.corner_radius",
                (corner - side * rounded, edge + rounded),
                rounded,
                -90.0 + side * 45.0,
                (side * 0.25, 0.12),
            ),
        ]
    return marks


# Function `_vise_back()`:
def _vise_back(s: _ViseSizes) -> View:
    """Return the machine vise seen from its lead screw's end.

    Arguments:
    * `s` (`_ViseSizes`): Where its parts are.

    Returns:
    * (`View`): The view, Y to the right and Z up.
    """
    # The movable jaw, the base, the body and the bed, the lead screw's
    # hole, the lead screw and its hexagon; hidden, the movable jaw
    # plate's holes and counterbores.
    v: MachineVise = VISE
    base: float = _in(v.base.width) / 2.0
    body: float = _in(v.body.width) / 2.0
    moving: float = _in(v.movable_jaw.width) / 2.0
    screw: float = _in(v.lead_screw_diameter) / 2.0
    hole: float = _in(v.lead_screw_hole_diameter) / 2.0
    holes_x: float = _in(v.jaw_plate.hole_spacing) / 2.0
    holes_z: float = s.bed_top + _in(v.jaw_plate.hole_height)
    hexagon: Profile = [(y, s.screw_z + z) for y, z in _hexagon()]
    shapes: list[ViewShape] = [
        _rectangle((-moving, s.bed_top), (moving, s.jaw_top)),
        _rectangle((-base, 0.0), (base, _in(v.base.height))),
        _rectangle((-body, _in(v.base.height)), (body, s.bed_bottom)),
        _rectangle((-s.outer, s.bed_bottom), (s.outer, s.bed_top)),
        _circle((0.0, s.screw_z), hole, POCKET_FILL),
        _circle((0.0, s.screw_z), screw),
        _polygon(hexagon),
        *[
            _circle((x, holes_z), _in(diameter) / 2.0, "none", HIDDEN)
            for x in (-holes_x, holes_x)
            for diameter in (
                v.jaw_plate.hole_diameter,
                v.jaw_plate.counterbore_diameter,
            )
        ],
        _center_line(False, 0.0, 0.0, s.jaw_top),
    ]

    # The widths, above and below; the lead screw's height on the left,
    # and its sizes on the right.
    flat: float = max(y for y, z in _hexagon() if z > 0.0)
    left: float = -s.outer - STAND_OFF
    right: float = s.outer + STAND_OFF
    marks: list[Mark] = [
        Dimension(
            "movable_jaw.width",
            True,
            -moving,
            moving,
            s.jaw_top + STAND_OFF,
            (s.jaw_top, s.jaw_top),
        ),
        Dimension("base.width", True, -base, base, -STAND_OFF, (0.0, 0.0)),
        Dimension(
            "body.width",
            True,
            -body,
            body,
            -STAND_OFF - ROW,
            (_in(v.base.height), _in(v.base.height)),
        ),
        Dimension(
            "lead_screw_height", False, 0.0, s.screw_z, left, (-base, -screw)
        ),
        Dimension(
            "hex_size",
            False,
            s.screw_z - _in(v.hex_size) / 2.0,
            s.screw_z + _in(v.hex_size) / 2.0,
            right,
            (flat, flat),
        ),
        Dimension(
            "lead_screw_diameter",
            False,
            s.screw_z - screw,
            s.screw_z + screw,
            right + ROW,
            (0.0, 0.0),
        ),
        Dimension(
            "lead_screw_hole_diameter",
            False,
            s.screw_z - hole,
            s.screw_z + hole,
            right + 2 * ROW,
            (0.0, 0.0),
        ),
    ]
    return View("back", "Back (the hexagon's end)", shapes, marks)


# Function `_vise_side()`:
def _vise_side(s: _ViseSizes) -> View:
    """Return the machine vise seen from its -Y side.

    Arguments:
    * `s` (`_ViseSizes`): Where its parts are.

    Returns:
    * (`View`): The view, X to the right and Z up.
    """
    # The lead screw's end, the body and the base with their notches
    # (seen face on), the bed, then the jaws and jaw plates.
    v: MachineVise = VISE
    screw: float = _in(v.lead_screw_diameter) / 2.0
    hex_z: float = _in(v.hex_size) / 2.0
    base_top: float = _in(v.base.height)
    shapes: list[ViewShape] = [
        _rectangle((s.half, s.screw_z - screw), (s.stick, s.screw_z + screw)),
        _rectangle(
            (s.stick, s.screw_z - hex_z), (s.hex_end, s.screw_z + hex_z)
        ),
    ]
    for low, high, notches in (
        (base_top, s.bed_bottom, v.body_notches),
        (0.0, base_top, v.base_notches),
    ):
        shapes.append(_rectangle((-s.half, low), (s.half, high)))
        width: float = _in(notches.width) / 2.0
        shapes += [
            _rectangle((_in(x) - width, low), (_in(x) + width, high))
            for x in notches.centers
        ]
    shapes += [
        _rectangle((-s.half, s.bed_bottom), (s.half, s.bed_top)),
        _rectangle((-s.half, s.bed_top), (s.fixed_face, s.jaw_top)),
        _rectangle(
            (s.fixed_face, s.bed_top),
            (s.fixed_face + s.plate, s.bed_top + _in(v.jaw_plate.height)),
        ),
        _rectangle(
            (s.face - s.plate, s.bed_top),
            (s.face, s.bed_top + _in(v.jaw_plate.height)),
        ),
        _rectangle((s.face, s.bed_top), (s.moving_end, s.jaw_top)),
    ]

    # The heights: the stack on the left, the movable jaw on the right.
    left: float = -s.half - STAND_OFF
    edge: tuple[float, float] = (-s.half, -s.half)
    marks: list[Mark] = [
        Dimension("base.height", False, 0.0, base_top, left, edge),
        Dimension("body.height", False, base_top, s.bed_bottom, left, edge),
        Dimension("rail_height", False, s.bed_bottom, s.bed_top, left, edge),
        Dimension("fixed_jaw.height", False, s.bed_top, s.jaw_top, left, edge),
        Dimension(
            "movable_jaw.height",
            False,
            s.bed_top,
            s.jaw_top,
            s.hex_end + STAND_OFF,
            (s.moving_end, s.moving_end),
        ),
    ]
    return View("side", "Side (from -Y)", shapes, marks)


# Function `vise_views()`:
def vise_views() -> list[View]:
    """Return the views of the machine vise, in the document's order.

    Returns:
    * (`list[View]`): The top, back and side views.
    """
    sizes: _ViseSizes = _ViseSizes()
    return [_vise_top(sizes), _vise_back(sizes), _vise_side(sizes)]


# Function `vise_numbers()`:
def vise_numbers(views: list[View]) -> dict[str, str]:
    """Return the number of each size drawn, in the order drawn.

    Arguments:
    * `views` (`list[View]`): The views.

    Returns:
    * (`dict[str, str]`): Each size's path and number.
    """
    keys: list[str] = [mark.key for view in views for mark in view.marks]
    return {key: str(number) for number, key in enumerate(keys, 1)}


# Function `view_sketch()`:
def view_sketch(view: View, numbers: dict[str, str]) -> str:
    """Return one view, as an SVG file.

    Arguments:
    * `view` (`View`): The view.
    * `numbers` (`dict[str, str]`): What each mark is labeled with.

    Returns:
    * (`str`): The SVG file's text.
    """
    # The page, big enough for the shapes, the dimension lines and the
    # radii's letters.
    xs: list[float] = [x for shape in view.shapes for x, _ in shape.points]
    zs: list[float] = [z for shape in view.shapes for _, z in shape.points]
    _extend(
        [mark for mark in view.marks if isinstance(mark, Dimension)], xs, zs
    )
    for mark in view.marks:
        if isinstance(mark, Radius):
            xs.append(mark.center[0] + mark.letter_at[0])
            zs.append(mark.center[1] + mark.letter_at[1])
    root: ET.Element = _root(xs, zs)

    # The shapes, then the marks.
    for shape in view.shapes:
        attributes: dict[str, str] = {
            "d": shape.path,
            "fill": shape.fill,
            "stroke": INK,
            "stroke-width": "1" if shape.dashes else "2",
            "stroke-linejoin": "round",
        }
        if shape.dashes:
            attributes["stroke-dasharray"] = shape.dashes
        ET.SubElement(root, "path", attributes)
    for mark in view.marks:
        if isinstance(mark, Dimension):
            _dimension(root, mark, numbers[mark.key])
        elif isinstance(mark, Radius):
            _radius(root, mark, numbers[mark.key])
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


# Function `_attributes()`:
def _attributes(cls: type) -> dict[str, str]:
    """Return what a class's docstring says each attribute is.

    Arguments:
    * `cls` (`type`): The class.

    Returns:
    * (`dict[str, str]`): Each attribute's meaning, on one line.
    """
    doc: str = inspect.getdoc(cls) or ""
    listed: str = doc.split("Attributes:\n", maxsplit=1)[1]
    listed = listed.split("\n\n", maxsplit=1)[0]
    meanings: dict[str, str] = {}
    name: str = ""
    for line in listed.splitlines():
        if line.startswith("* `"):
            name = line[3:].split("`", maxsplit=1)[0]
            meanings[name] = line.split("):", maxsplit=1)[1].strip()
        else:
            meanings[name] = f"{meanings[name]} {line.strip()}".strip()
    return meanings


# Function `vise_sizes()`:
def vise_sizes() -> dict[str, str]:
    """Return every size of a machine vise, and what it means.

    Returns:
    * (`dict[str, str]`): Each size's path (such as `base.length`) and
      its meaning, from the docstrings, in the order of the fields.  The
      jaw plate has a section of its own.
    """
    parts: dict[type, dict[str, str]] = {
        part: _attributes(part) for part in (ViseBlock, ViseNotches)
    }
    meanings: dict[str, str] = {}
    for name, meaning in _attributes(MachineVise).items():
        part: object = getattr(VISE, name)
        if isinstance(part, (str, JawPlate)):
            continue
        if type(part) not in parts:
            meanings[name] = meaning
            continue
        for key, inner in parts[type(part)].items():
            joined: str = (
                f"{meaning.rstrip('.')}: {inner[0].lower()}{inner[1:]}"
            )
            meanings[f"{name}.{key}"] = joined
    return meanings


# Function `vise_section()`:
def vise_section() -> str:
    """Return the machine vise's section of the document.

    Returns:
    * (`str`): Its Markdown.
    """
    # What it is, from its docstring, and its views.
    doc: str = inspect.getdoc(MachineVise) or ""
    about: str = doc.split("\n\nAttributes:", maxsplit=1)[0]
    paragraphs: str = "\n\n".join(
        textwrap.fill(paragraph, 72) for paragraph in about.split("\n\n")
    )
    views: list[View] = vise_views()
    numbers: dict[str, str] = vise_numbers(views)
    images: str = "\n\n".join(
        f"{view.title}:\n\n"
        f"![Machine vise, {view.name}]"
        f"({SKETCHES}/machine_vise_{view.name}.svg)"
        for view in views
    )

    # The sizes, by number; then those not drawn.
    meanings: dict[str, str] = vise_sizes()
    rows: list[list[str]] = _size_rows(numbers, meanings)
    hidden: str = ", ".join(
        f"`{key}`" for key in meanings if key not in numbers
    )

    # How to make one, and where a setup names one.
    setup: object = next(
        item
        for item in json.loads(
            (HERE / "examples/setup/demo_plate.json").read_text(
                encoding="utf-8"
            )
        )["tooling"]
        if item["kind"] == "machine_vise"
    )
    python: str = (
        "from scraftcam.pybind.scraftpybind import PyBind, connect\n"
        f"from scraftcam.tooling.tools import {VISE_NAME}\n"
        "\n"
        'with connect("8080") as transport:\n'
        f"    {VISE_NAME}.model(PyBind(transport), opening=76.2)\n"
    )
    interface: str = "\n".join(
        _interface_entry(tools, name, False)
        for name in ("MachineVise", "ViseBlock", "ViseNotches")
    )
    return (
        "## Machine Vise\n\n"
        f"{paragraphs}\n\n"
        "The sketches are of `tools.KURT_D688`, opened as far as it goes.\n"
        "Hidden edges are dashed.  Its jaw plates are separate parts,\n"
        "described in [Jaw Plate](#jaw-plate).\n\n"
        f"{images}\n\n"
        f"{markdown_table(rows)}\n\n"
        f"{textwrap.fill(f'Not drawn (square on the sample): {hidden}.', 72)}"
        "\n\n"
        "A machine vise has no tools file entry yet, so it is made in\n"
        "Python, in millimeters, like `tools.KURT_D688`:\n\n"
        f"```python\n{python}```\n\n"
        "A setup file (`examples/setup/`) names one by its `type`:\n\n"
        f"```json\n{json.dumps(setup, indent=2)}\n```\n\n"
        f"{interface}"
    )


# Function `_size_rows()`:
def _size_rows(
    numbers: dict[str, str], meanings: dict[str, str]
) -> list[list[str]]:
    """Return the rows of a table of sizes, by number.

    Arguments:
    * `numbers` (`dict[str, str]`): Each size's number.
    * `meanings` (`dict[str, str]`): Each size's meaning.

    Returns:
    * (`list[list[str]]`): The heading row, then one row a size.
    """
    rows: list[list[str]] = [["Number", "Units", "Description"]]
    for key, number in numbers.items():
        units: str = "Lengths" if key.endswith(".centers") else "Length"
        rows.append([number, units, f"`{key}`: {meanings[key]}"])
    return rows


# The jaw plate that its section is drawn from.
JAW_PLATE: JawPlate = KURT_JAW_PLATE
JAW_PLATE_NAME: str = "KURT_JAW_PLATE"


# Function `jaw_plate_views()`:
def jaw_plate_views() -> list[View]:
    """Return the views of the jaw plate, in the document's order.

    Both are drawn with the plate's width across: from above, with its
    clamping face toward the bottom; and looking at its clamping face.

    Returns:
    * (`list[View]`): The top and face views.
    """
    # The plate's sizes (inches).
    p: JawPlate = JAW_PLATE
    thick: float = _in(p.length)
    half: float = _in(p.width) / 2.0
    tall: float = _in(p.height)
    holes: float = _in(p.hole_spacing) / 2.0
    hole: float = _in(p.hole_diameter) / 2.0
    bore: float = _in(p.counterbore_diameter) / 2.0
    deep: float = _in(p.counterbore_depth)
    up: float = _in(p.hole_height)

    # From above: each hole and counterbore hidden inside, the clamping
    # face at the bottom.
    top_shapes: list[ViewShape] = [_rectangle((-half, 0.0), (half, thick))]
    for x in (-holes, holes):
        top_shapes += [
            _rectangle((x - bore, 0.0), (x + bore, deep), "none", HIDDEN),
            _rectangle((x - hole, deep), (x + hole, thick), "none", HIDDEN),
            _center_line(False, x, 0.0, thick),
        ]
    top_marks: list[Mark] = [
        Dimension("length", False, 0.0, thick, half + STAND_OFF, (half, half)),
        Dimension(
            "counterbore_depth",
            False,
            0.0,
            deep,
            -half - STAND_OFF,
            (-half, -holes - bore),
        ),
    ]

    # The clamping face: the counterbores, with the holes through them.
    face_shapes: list[ViewShape] = [_rectangle((-half, 0.0), (half, tall))]
    for x in (-holes, holes):
        face_shapes += [
            _circle((x, up), bore),
            _circle((x, up), hole, POCKET_FILL),
            _center_line(False, x, up - bore, up + bore),
        ]
    face_shapes.append(_center_line(True, up, -half, half))
    face_marks: list[Mark] = [
        Dimension("width", True, -half, half, -STAND_OFF - ROW, (0.0, 0.0)),
        Dimension("hole_spacing", True, -holes, holes, -STAND_OFF, (up, up)),
        Dimension(
            "height", False, 0.0, tall, -half - STAND_OFF, (-half, -half)
        ),
        Dimension(
            "hole_height", False, 0.0, up, half + STAND_OFF, (half, holes)
        ),
        Dimension(
            "counterbore_diameter",
            True,
            -holes - bore,
            -holes + bore,
            tall + STAND_OFF,
            (up, up),
        ),
        Dimension(
            "hole_diameter",
            True,
            holes - hole,
            holes + hole,
            tall + STAND_OFF,
            (up, up),
        ),
    ]
    return [
        View("top", "Top (clamping face down)", top_shapes, top_marks),
        View("face", "Clamping face", face_shapes, face_marks),
    ]


# Function `jaw_plate_section()`:
def jaw_plate_section() -> str:
    """Return the jaw plate's section of the document.

    Returns:
    * (`str`): Its Markdown.
    """
    # What it is, from its docstring, and its views.
    doc: str = inspect.getdoc(JawPlate) or ""
    about: str = doc.split("\n\nAttributes:", maxsplit=1)[0]
    paragraphs: str = "\n\n".join(
        textwrap.fill(paragraph, 72) for paragraph in about.split("\n\n")
    )
    views: list[View] = jaw_plate_views()
    numbers: dict[str, str] = vise_numbers(views)
    images: str = "\n\n".join(
        f"{view.title}:\n\n"
        f"![Jaw plate, {view.name}]({SKETCHES}/jaw_plate_{view.name}.svg)"
        for view in views
    )

    # The sizes, by number; then the rest, and how to make one.
    meanings: dict[str, str] = _attributes(JawPlate)
    rows: list[list[str]] = _size_rows(numbers, meanings)
    others: str = "\n".join(
        textwrap.fill(f"* `{key}`: {meaning}", 72, subsequent_indent="  ")
        for key, meaning in meanings.items()
        if key not in numbers
    )
    python: str = (
        "from scraftcam.pybind.scraftpybind import PyBind, connect\n"
        f"from scraftcam.tooling.tools import {JAW_PLATE_NAME}\n"
        "\n"
        'with connect("8080") as transport:\n'
        f'    {JAW_PLATE_NAME}.model(PyBind(transport), "Jaw plate")\n'
    )
    return (
        "## Jaw Plate\n\n"
        f"{paragraphs}\n\n"
        f"The sketches are of `tools.{JAW_PLATE_NAME}`, the plate on\n"
        "`tools.KURT_D688`.  Hidden edges are dashed.\n\n"
        f"{images}\n\n"
        f"{markdown_table(rows)}\n\n"
        f"Not a size:\n\n{others}\n\n"
        "Like the vise, it is made in Python, in millimeters:\n\n"
        f"```python\n{python}```\n\n"
        f"{_interface_entry(tools, 'JawPlate', False)}"
    )


# The parallel that its section is drawn from.
PARALLEL: Parallel = next(
    parallel for parallel in PARALLELS if parallel.name == "Parallel 3/4 in A"
)


# Function `parallel_views()`:
def parallel_views() -> list[View]:
    """Return the views of a parallel, in the document's order.

    Returns:
    * (`list[View]`): Its side, looking through its holes, and its end.
    """
    # Its sizes (inches).
    p: Parallel = PARALLEL
    half: float = _in(p.length) / 2.0
    tall: float = _in(p.height)
    thick: float = _in(p.thickness)
    holes: float = _in(p.hole_spacing) / 2.0
    hole: float = _in(p.hole_diameter) / 2.0
    up: float = tall / 2.0

    # The side: the holes through it, and its center lines.
    side_shapes: list[ViewShape] = [_rectangle((-half, 0.0), (half, tall))]
    for x in (-holes, holes):
        side_shapes += [
            _circle((x, up), hole, POCKET_FILL),
            _center_line(False, x, up - hole, up + hole),
        ]
    side_shapes.append(_center_line(True, up, -half, half))
    side_marks: list[Mark] = [
        Dimension("length", True, -half, half, -STAND_OFF - ROW, (0.0, 0.0)),
        Dimension("hole_spacing", True, -holes, holes, -STAND_OFF, (up, up)),
        Dimension(
            "height", False, 0.0, tall, -half - STAND_OFF, (-half, -half)
        ),
        Dimension(
            "hole_diameter",
            True,
            holes - hole,
            holes + hole,
            tall + STAND_OFF,
            (up, up),
        ),
    ]

    # The end: the holes hidden inside it.
    end_shapes: list[ViewShape] = [
        _rectangle((-thick / 2.0, 0.0), (thick / 2.0, tall)),
        _rectangle(
            (-thick / 2.0, up - hole), (thick / 2.0, up + hole), "none", HIDDEN
        ),
    ]
    end_marks: list[Mark] = [
        Dimension(
            "thickness",
            True,
            -thick / 2.0,
            thick / 2.0,
            -STAND_OFF,
            (0.0, 0.0),
        ),
    ]
    return [
        View("side", "Side", side_shapes, side_marks),
        View("end", "End", end_shapes, end_marks),
    ]


# Function `parallel_section()`:
def parallel_section() -> str:
    """Return the parallel's section of the document.

    Returns:
    * (`str`): Its Markdown.
    """
    # What it is, from its docstring, and its views.
    doc: str = inspect.getdoc(Parallel) or ""
    about: str = doc.split("\n\nAttributes:", maxsplit=1)[0]
    paragraphs: str = "\n\n".join(
        textwrap.fill(paragraph, 72) for paragraph in about.split("\n\n")
    )
    views: list[View] = parallel_views()
    numbers: dict[str, str] = vise_numbers(views)
    images: str = "\n\n".join(
        f"{view.title}:\n\n"
        f"![Parallel, {view.name}]({SKETCHES}/parallel_{view.name}.svg)"
        for view in views
    )

    # The sizes, by number, and the set on hand.
    meanings: dict[str, str] = _attributes(Parallel)
    rows: list[list[str]] = _size_rows(numbers, meanings)
    heights: str = textwrap.fill(
        "`tools.PARALLELS` is a set of two of each of the standard "
        "imperial heights, in inches: "
        f"{', '.join(h.removesuffix(' in') for h in PARALLEL_HEIGHTS)}.  "
        "Each is "
        f"{_inches_text(PARALLEL.thickness)} thick and "
        f"{_inches_text(PARALLEL.length)} long, with two holes "
        f"{_inches_text(PARALLEL.hole_spacing)} apart, half as wide as "
        "the parallel is tall.  Each is named for its height and A or B "
        "(`Parallel 3/4 in A`).",
        72,
    )

    # How to make one, and where a setup names one.
    p: Parallel = PARALLEL
    python: str = (
        "from scraftcam.pybind.scraftpybind import PyBind, connect\n"
        "from scraftcam.tooling.tools import Parallel\n"
        "\n"
        "# Its sizes in millimeters; the holes are optional.\n"
        "parallel = Parallel(\n"
        '    "Parallel 3/4 in",\n'
        f"    height={p.height:.3f},\n"
        f"    thickness={p.thickness:.3f},\n"
        f"    length={p.length:.1f},\n"
        f"    hole_spacing={p.hole_spacing:.1f},\n"
        f"    hole_diameter={p.hole_diameter:.3f},\n"
        ")\n"
        'with connect("8080") as transport:\n'
        "    parallel.model(PyBind(transport), (0.0, 0.0, 0.0))\n"
    )
    setup: object = next(
        item
        for item in json.loads(
            (HERE / "examples/setup/demo_plate.json").read_text(
                encoding="utf-8"
            )
        )["tooling"]
        if item["kind"] == "parallel"
    )
    return (
        "## Parallel\n\n"
        f"{paragraphs}\n\n"
        f"The sketches are of `{PARALLEL.name}`, from `tools.PARALLELS`.\n"
        "Hidden edges are dashed.\n\n"
        f"{images}\n\n"
        f"{markdown_table(rows)}\n\n"
        f"{heights}\n\n"
        "It is made in Python, in millimeters:\n\n"
        f"```python\n{python}```\n\n"
        "A setup file (`examples/setup/`) names one of the set by its\n"
        "`type`:\n\n"
        f"```json\n{json.dumps(setup, indent=2)}\n```\n\n"
        f"{_interface_entry(tools, 'Parallel', False)}"
    )


# The grid plate that its section is drawn from, and how much larger
# its hole's section is drawn.
GRID: GridPlate = GRID_PLATE
DETAIL: float = 8.0


# Function `grid_plate_views()`:
def grid_plate_views() -> list[View]:
    """Return the views of the grid plate, in the document's order.

    Returns:
    * (`list[View]`): The view from above, and a section through one
      grid hole, drawn larger.
    """
    # The plate, its grid holes with their chamfers, and its tooling
    # holes: the tap drill holes filled, the close fit holes open.
    g: GridPlate = GRID
    half_x: float = _in(g.length) / 2.0
    half_y: float = _in(g.width) / 2.0
    hole: float = _in(g.hole_diameter) / 2.0
    top: float = _in(g.chamfered_diameter()) / 2.0
    shapes: list[ViewShape] = [
        _outline(g.outline((0.0, 0.0)), TOOL_FILL),
    ]
    for x, y in g.hole_centers():
        shapes.append(_circle((_in(x), _in(y)), top, "white"))
        if top > hole:
            shapes.append(_circle((_in(x), _in(y)), hole, "white"))
    for x, y, diameter in g.tooling_holes():
        fill: str = POCKET_FILL if diameter == g.tap_diameter else "white"
        shapes.append(_circle((_in(x), _in(y)), _in(diameter) / 2.0, fill))

    # Along the bottom: the edge, the pitch and the length; up the left
    # side, the width; the tooling holes along the top.
    columns: list[float] = [_in(x) for x, _ in g.hole_centers()[:2]]
    tooling: list[tuple[float, float, float]] = [
        (_in(x), _in(y), _in(d) / 2.0) for x, y, d in g.tooling_holes()
    ]
    below: float = -half_y - STAND_OFF
    corner: float = _in(g.corner_radius)
    marks: list[Mark] = [
        Dimension(
            "edge",
            True,
            -half_x,
            columns[0],
            below,
            (-half_y, -half_y + _in(g.edge)),
        ),
        Dimension(
            "pitch",
            True,
            columns[0],
            columns[1],
            below,
            (-half_y + _in(g.edge), -half_y + _in(g.edge)),
        ),
        Dimension(
            "length", True, -half_x, half_x, below - ROW, (below, below)
        ),
        Dimension(
            "width", False, -half_y, half_y, -half_x - STAND_OFF, (0.0, 0.0)
        ),
        Radius(
            "corner_radius",
            (half_x - corner, -half_y + corner),
            corner,
            -45.0,
            (0.35, -0.35),
        ),
    ]
    if tooling:
        # The top row: one of each size, and the distance between them.
        (x_tap, y_top, r_tap), (x_close, _, r_close) = tooling[-2:]
        if r_tap > r_close:
            (x_tap, r_tap), (x_close, r_close) = (
                (x_close, r_close),
                (x_tap, r_tap),
            )
        above: float = half_y + STAND_OFF
        marks += [
            Dimension(
                "tooling_pitch",
                True,
                tooling[-2][0],
                tooling[-1][0],
                above + ROW,
                (y_top, y_top),
            ),
            Dimension(
                "tap_diameter",
                True,
                x_tap - r_tap,
                x_tap + r_tap,
                above,
                (y_top, y_top),
            ),
            Dimension(
                "close_diameter",
                True,
                x_close - r_close,
                x_close + r_close,
                above,
                (y_top, y_top),
            ),
        ]
    return [
        View("top", "Top", shapes, marks),
        _grid_hole_section(),
    ]


# Function `_grid_hole_section()`:
def _grid_hole_section() -> View:
    """Return a section through one grid hole, `DETAIL` times size.

    Returns:
    * (`View`): The section, across the hole, a pitch wide.
    """
    g: GridPlate = GRID
    side: float = _in(g.pitch) / 2.0 * DETAIL
    hole: float = _in(g.hole_diameter) / 2.0 * DETAIL
    deep: float = _in(g.chamfer_depth) * DETAIL
    tall: float = _in(g.height) * DETAIL
    left: Profile = [
        (-side, 0.0),
        (-hole, 0.0),
        (-hole, tall - deep),
        (-hole - deep, tall),
        (-side, tall),
    ]
    right: Profile = [(-x, z) for x, z in reversed(left)]
    shapes: list[ViewShape] = [
        _polygon(left),
        _polygon(right),
        _center_line(False, 0.0, 0.0, tall),
    ]
    marks: list[Mark] = [
        Dimension("height", False, 0.0, tall, side + STAND_OFF, (side, side)),
        Dimension("hole_diameter", True, -hole, hole, -STAND_OFF, (0.0, 0.0)),
        Dimension(
            "chamfer_depth",
            False,
            tall - deep,
            tall,
            -side - STAND_OFF,
            (-hole, -side),
        ),
    ]
    title: str = f"Section through a grid hole ({DETAIL:.0f} times size)"
    return View("section", title, shapes, marks)


# Function `grid_plate_section()`:
def grid_plate_section() -> str:
    """Return the grid plate's section of the document.

    Returns:
    * (`str`): Its Markdown.
    """
    # What it is, from its docstring, and its views.
    doc: str = inspect.getdoc(GridPlate) or ""
    about: str = doc.split("\n\nAttributes:", maxsplit=1)[0]
    paragraphs: str = "\n\n".join(
        textwrap.fill(paragraph, 72) for paragraph in about.split("\n\n")
    )
    views: list[View] = grid_plate_views()
    numbers: dict[str, str] = vise_numbers(views)
    images: str = "\n\n".join(
        f"{view.title}:\n\n"
        f"![Grid plate, {view.name}]({SKETCHES}/grid_plate_{view.name}.svg)"
        for view in views
    )

    # The sizes, by number; then the rest, and how to make one.
    meanings: dict[str, str] = _attributes(GridPlate)
    rows: list[list[str]] = _size_rows(numbers, meanings)
    others: str = "\n".join(
        textwrap.fill(f"* `{key}`: {meaning}", 72, subsequent_indent="  ")
        for key, meaning in meanings.items()
        if key not in numbers
    )
    python: str = (
        "from scraftcam.model_cache import ModelCache\n"
        "from scraftcam.pybind.scraftpybind import PyBind, connect\n"
        "from scraftcam.tooling.tools import GRID_PLATE\n"
        "\n"
        "# Through the cache: slow the first time, then about a second.\n"
        'with connect("8080") as transport:\n'
        "    (plate,) = GRID_PLATE.cacheable()\n"
        "    ModelCache().insert(PyBind(transport), plate)\n"
    )
    toml: str = (HERE / "examples/shop/tooling.toml").read_text(
        encoding="utf-8"
    )
    toml = toml[toml.index("[[grid_plates]]") :]
    setup: object = next(
        item
        for item in json.loads(
            (HERE / "examples/setup/demo_stack.json").read_text(
                encoding="utf-8"
            )
        )["tooling"]
        if item["kind"] == "grid_plate"
    )
    return (
        "## Grid Plate\n\n"
        f"{paragraphs}\n\n"
        "The sketches are of `tools.GRID_PLATE`.  Its tap drill tooling\n"
        "holes are filled, and its close fit ones open.\n\n"
        "Chamfering the grid's holes is currently very slow to compute\n"
        "(about 4-1/2 minutes for `tools.GRID_PLATE`'s 200, against\n"
        "seconds without them), and is done again whenever the cache\n"
        "key changes.  Turning it off is recommended:\n"
        "`GridPlate.named(name, chamfer=False)` (in a setup's\n"
        "`args`, `chamfer = false`), as the demonstration does.\n\n"
        f"{images}\n\n"
        f"{markdown_table(rows)}\n\n"
        f"Not a size:\n\n{others}\n\n"
        "A shop describes its grid plates in a tooling file (`Shops.md`),\n"
        "as `examples/shop/tooling.toml` describes `tools.GRID_PLATE`:\n\n"
        f"```toml\n{toml}```\n\n"
        "Or it is made in Python, in millimeters:\n\n"
        f"```python\n{python}```\n\n"
        "A setup file (`examples/setup/`) names one by its `type`, from\n"
        "the shop's tooling files or `tools.py`:\n\n"
        f"```json\n{json.dumps(setup, indent=2)}\n```\n\n"
        f"{_interface_entry(tools, 'GridPlate', False)}"
    )


# Function `_inches_text()`:
def _inches_text(millimeters: float) -> str:
    """Return a length in inches, as a fraction where one fits.

    Arguments:
    * `millimeters` (`float`): The length (millimeters).

    Returns:
    * (`str`): The length, such as `1/8 in` or `6 in`.
    """
    eighths: float = _in(millimeters) * 8.0
    whole: int = round(eighths)
    assert abs(eighths - whole) < 1e-6, f"{millimeters=} is not in eighths"
    inches, rest = divmod(whole, 8)
    common: int = math.gcd(rest, 8)
    fraction: str = f"{rest // common}/{8 // common}" if rest else ""
    if inches and fraction:
        return f"{inches}-{fraction} in"
    return f"{fraction or inches} in"


# Function `document()`:
def document() -> str:
    """Return `Tool_Models.md`.

    Returns:
    * (`str`): The document.
    """
    lengths: str = ", ".join(f"`{unit}`" for unit in LENGTH)
    titles: list[str] = ["Python Interface"]
    titles += [page.title for page in PAGES]
    titles += ["Machine Vise", "Jaw Plate", "Parallel", "Grid Plate"]
    contents: str = "\n".join(
        f"* [{title}](#{title.lower().replace(' ', '-')})" for title in titles
    )
    interface: str = "\n".join(
        _interface_entry(module, name, brief)
        for module, name, brief in INTERFACE
    )
    return "\n".join(
        [
            textwrap.dedent(INTRODUCTION).format(lengths=lengths),
            f"## Contents\n\n{contents}\n",
            f"## Python Interface\n\n{interface}",
            *[section(page) for page in PAGES],
            vise_section(),
            jaw_plate_section(),
            parallel_section(),
            grid_plate_section(),
        ]
    )


# Function `main()`:
def main() -> None:
    """Write `Tool_Models.md` and its sketches."""
    DOCUMENT.write_text(document(), encoding="utf-8")
    directory: Path = HERE / SKETCHES
    directory.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        (directory / f"{page.kind}.svg").write_text(
            sketch(page), encoding="utf-8"
        )
    views: list[View] = vise_views()
    numbers: dict[str, str] = vise_numbers(views)
    for view in views:
        (directory / f"machine_vise_{view.name}.svg").write_text(
            view_sketch(view, numbers), encoding="utf-8"
        )
    for prefix, views in (
        ("jaw_plate", jaw_plate_views()),
        ("parallel", parallel_views()),
        ("grid_plate", grid_plate_views()),
    ):
        numbers = vise_numbers(views)
        for view in views:
            (directory / f"{prefix}_{view.name}.svg").write_text(
                view_sketch(view, numbers), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
