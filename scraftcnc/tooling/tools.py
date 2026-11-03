#!/usr/bin/env python3
"""3D models of the tooling that holds work on a machine, for SolidCraft.

So far, the tables of Tormach's three entry level mills, each with its
T-slots and the pockets at their ends that T-nuts drop in through;
the keep-out regions around them that a tool must not enter; generic
drills; double end countersinks; a vise; a set of parallels; and a
grid plate.

Every table has its top at `Z = 0`, its length along X and its center
on `X = 0`.  Run as a program, it shows them all in SolidCraft:

```
python3 tools.py 8080       # A GUI started with `--control 8080`.
python3 tools.py headless   # No window; prints the bodies it made.
python3 tools.py 8080 countersinks   # Only the double end countersinks.
python3 tools.py 8080 largest        # The largest of each kind of them.
python3 tools.py 8080 421-0261       # One of them, by its order number.
```
"""

# A `SCMillTable` holds one number per dimension on the drawing, which
# runs past `pylint`'s limit on attributes.
# pylint: disable=too-many-instance-attributes

# All of the tooling models live together for now, which runs past
# `pylint`'s limit on a module's size.
# pylint: disable=too-many-lines

import itertools
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from ..geometry import SCCorner, SCHole, SCRoundedPolygon
from ..model_cache import SCCacheable, source_digest
from ..plot import send_batch
from ..pybind.scraftpybind import JSON, SCPyBind, connect
from ..shops import LENGTH, measure
from .cutter_models import (
    COUNTERSINK_TIP_FLAT,
    MM_PER_INCH,
    FluteRun,
    flute_runs,
    flute_steps,
)

# A point: `(x, y, z)`, in millimeters.
Point = tuple[float, float, float]

# An arc: the `(x, y)` of its start, a point along it, and its end.
Arc = tuple[tuple[float, float], tuple[float, float], tuple[float, float]]

# How far apart the tables are drawn (millimeters).
TABLE_GAP: float = 100.0

# A cast iron gray.
TABLE_COLOR: str = "#8a8f94"

# How keep-out regions look: a see-through warning red.
KEEP_OUT_COLOR: str = "#e03c31"
KEEP_OUT_OPACITY: float = 0.25

# How far a table's keep-out region is grown past the table.
TABLE_MARGIN: str = "1/8 in"

# How far a drill's keep-out region is grown past the drill.
DRILL_MARGIN: str = "1/8 in"

# A bright steel, for drills.
DRILL_COLOR: str = "#c8ccd0"

# The sample drills' colors, so they are easy to tell apart.
SAMPLE_DRILL_COLORS: tuple[str, ...] = (
    "#2f6fde",
    "#2fae5b",
    "#e0a82e",
    "#8e4ec6",
    "#20b2aa",
)

# A drill's usual included point angle (degrees).
DRILL_POINT_ANGLE: float = 118.0

# How far apart the sample drills stand, and how far from the tables
# (millimeters).
DRILL_SPACING: float = 80.0
DRILL_ROW_Y: float = -100.0

# How far apart the double end countersinks stand when shown, in a row
# per catalog table (millimeters), and each table's color.
COUNTERSINK_SPACING: float = 40.0
COUNTERSINK_COLORS: dict[str, str] = {
    "Radius": "#2f6fde",
    "Plain": "#2fae5b",
    "Metric": "#e0a82e",
    "Left hand": "#8e4ec6",
}

# The included angle of the points on a double end countersink's small
# drills (degrees), and how wide the flat on each tip is, as a fraction
# of the drill's diameter.  A revolve that comes to a point on its axis
# has errors at the tip, and this is good enough.
COUNTERSINK_POINT_ANGLE: float = 90.0

# How many flutes each end of a countersink has.  The catalog does not
# say, so this is the common number, from memory.
COUNTERSINK_FLUTES: int = 2

# Where the vise stands, clear of the drills (millimeters).
VISE_ROW_Y: float = -250.0

# How the vise is shown: its jaws partly open, and how far they are
# raised off the rails (raise them to see how they go together).
VISE_OPENING: str = "3 in"
VISE_LIFT: str = "0 in"

# How far a vise's keep-out regions are grown past the vise.
VISE_MARGIN: str = "1/8 in"

# How far a parallel's keep-out region is grown past the parallel.
PARALLEL_MARGIN: str = "1/8 in"

# Where the parallels stand, clear of the vise, and how far apart: the
# two of a pair, and one pair from the next (millimeters).
PARALLEL_ROW_Y: float = -450.0
PARALLEL_PAIR_GAP: float = 12.7
PARALLEL_SET_GAP: float = 31.75

# A machine tool blue gray.
VISE_COLOR: str = "#4f6d8a"

# How far a grid plate's keep-out region is grown past the plate.
GRID_PLATE_MARGIN: str = "1/8 in"

# A bright, unpainted aluminum.
ALUMINUM_COLOR: str = "#e4e7ea"


# The code that builds tooling.  A change to it makes new models, as
# nothing else would notice that a cached model is out of date.
TOOLING_SOURCES: tuple[Path, ...] = (
    Path(__file__).resolve().parent / "mount.py",
    Path(__file__).resolve().parents[1] / "geometry.py",
    Path(__file__).resolve().parent / "tools.py",
)


# Function `tooling_shape()`:
def tooling_shape(item: Any, section: str = "") -> JSON:
    """Return what affects the shape of a piece of tooling.

    Arguments:
    * `item` (`Any`): The tooling, a dataclass with no colors.
    * `section` (`str`): Which part of it, if it is cached in parts.

    Returns:
    * (`JSON`): The tree, for `SCCacheable`.
    """
    return {
        "code": source_digest(TOOLING_SOURCES),
        "item": cast(JSON, asdict(item)),
        "section": section,
    }


# Function `_mm()`:
def _mm(length: str) -> float:
    """Return a length with its unit in millimeters.

    Arguments:
    * `length` (`str`): The length (such as `"1/8 in"`).

    Returns:
    * (`float`): The length (millimeters).
    """
    return measure(length, LENGTH) * MM_PER_INCH


# Class `SCMillTable`:
@dataclass(frozen=True, slots=True)
class SCMillTable:
    """A mill's table, with T-slots along its length.

    All lengths are in millimeters, as in the drawing they come from.

    Attributes:
    * `name` (`str`): The mill's name.
    * `length` (`float`): The table's size along X.
    * `width` (`float`): The table's size along Y.
    * `thickness` (`float`): The plate's thickness, without its ways.
    * `slots` (`int`): How many T-slots it has.
    * `slot_spacing` (`float`): The distance between slot centers.
    * `slot_length` (`float`): The length of each slot.
    * `throat_width` (`float`): The width of a slot's narrow part.
    * `throat_depth` (`float`): The depth of a slot's narrow part.
    * `head_width` (`float`): The width of a slot's wide part.
    * `slot_depth` (`float`): The slot's whole depth.
    * `pocket_length` (`float`): An end pocket's size along X.
    * `pocket_width` (`float`): An end pocket's size along Y.

    Constructor:
    * `SCMillTable(name, length, width, thickness, slots, slot_spacing,
      slot_length, throat_width, throat_depth, head_width, slot_depth,
      pocket_length, pocket_width)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    length: float = field(init=True)
    width: float = field(init=True)
    thickness: float = field(init=True)
    slots: int = field(init=True)
    slot_spacing: float = field(init=True)
    slot_length: float = field(init=True)
    throat_width: float = field(init=True)
    throat_depth: float = field(init=True)
    head_width: float = field(init=True)
    slot_depth: float = field(init=True)
    pocket_length: float = field(init=True)
    pocket_width: float = field(init=True)

    # Method `SCMillTable.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the slots leave the plate in one piece.

        Raises:
        * `ValueError`: If the slots reach through the plate's bottom or
          its edges, or into one another.
        """
        if self.slot_depth >= self.thickness:
            raise ValueError(
                f"{self.slot_depth=} must be less than {self.thickness=}"
            )
        reach: float = self.slot_spacing * (self.slots - 1) / 2.0
        if (
            reach + self.head_width / 2.0 >= self.width / 2.0
            or self.head_width >= self.slot_spacing
        ):
            raise ValueError(
                f"{self.slots=} of {self.head_width=} on "
                f"{self.slot_spacing=} do not fit {self.width=}"
            )

    # Method `SCMillTable.slot_centers()`:
    def slot_centers(self) -> list[float]:
        """Return the Y of each slot's center, from the table's center.

        Returns:
        * (`list[float]`): The slots' centers, from most negative up.
        """
        first: float = -self.slot_spacing * (self.slots - 1) / 2.0
        return [
            first + index * self.slot_spacing for index in range(self.slots)
        ]

    # Method `SCMillTable.slot_outline()`:
    def slot_outline(self) -> list[tuple[float, float]]:
        """Return a slot's cross section, as seen looking along X.

        Returns:
        * (`list[tuple[float, float]]`):
          The closed outline's `(y, z)` points, from the slot's center
          and the table's top.
        """
        throat: float = self.throat_width / 2.0
        head: float = self.head_width / 2.0
        return [
            (-throat, 0.0),
            (-throat, -self.throat_depth),
            (-head, -self.throat_depth),
            (-head, -self.slot_depth),
            (head, -self.slot_depth),
            (head, -self.throat_depth),
            (throat, -self.throat_depth),
            (throat, 0.0),
        ]

    # Method `SCMillTable.prism()`:
    def prism(self, center_y: float = 0.0) -> "SCPrism":
        """Return the rectangular prism that just encloses the table.

        Arguments:
        * `center_y` (`float`): The Y of its center (millimeters).

        Returns:
        * (`SCPrism`): The prism, named for the table.
        """
        half_x: float = self.length / 2.0
        half_y: float = self.width / 2.0
        return SCPrism(
            self.name,
            (-half_x, center_y - half_y, -self.thickness),
            (half_x, center_y + half_y, 0.0),
        )

    # Method `SCMillTable.volume()`:
    def volume(self) -> float:
        """Return the volume the model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        slot: float = (
            self.throat_width * self.throat_depth
            + self.head_width * (self.slot_depth - self.throat_depth)
        ) * self.slot_length
        pocket: float = (
            self.pocket_length * self.pocket_width * self.slot_depth
        )
        plate: float = self.length * self.width * self.thickness
        return plate - self.slots * slot - 2.0 * pocket


# The tables, from Tormach's drawing of them (its knowledge base's
# "T-Slot Spacing on Tormach Mills", 2023).  The drawing dimensions all
# but `thickness`, `pocket_length` and `pocket_width`, which were scaled
# from it, so they are only good to a millimeter or two.  The pockets'
# depth is not shown, and is taken to be the slots'.
MILL_TABLES: tuple[SCMillTable, ...] = (
    SCMillTable(
        name="Tormach 440",
        length=460.0,
        width=160.0,
        thickness=40.0,
        slots=3,
        slot_spacing=50.0,
        slot_length=381.0,
        throat_width=10.0,
        throat_depth=7.0,
        head_width=20.0,
        slot_depth=16.0,
        pocket_length=25.0,
        pocket_width=135.0,
    ),
    SCMillTable(
        name="Tormach 770",
        length=660.0,
        width=205.0,
        thickness=60.0,
        slots=3,
        slot_spacing=50.0,
        slot_length=560.0,
        throat_width=16.0,
        throat_depth=13.0,
        head_width=32.0,
        slot_depth=26.0,
        pocket_length=35.0,
        pocket_width=181.0,
    ),
    SCMillTable(
        name="Tormach 1100",
        length=860.0,
        width=240.0,
        thickness=60.0,
        slots=3,
        slot_spacing=60.0,
        slot_length=650.0,
        throat_width=16.0,
        throat_depth=13.0,
        head_width=32.0,
        slot_depth=26.0,
        pocket_length=49.0,
        pocket_width=225.0,
    ),
)

# The table of the mill in the user's garage, a Mikini 1610L, as the user
# measured it: 30 x 10-1/2 in, five slots 1 in deep, with an 11/16 in
# throat and a 15/16 in foot, each 1/2 in high.  The user's 1 in height can
# not be the plate's, since slots that deep would cut it in strips, so the
# thickness is an estimate.  So is the spacing, which was not given: the
# 2-1/2 in of the published specifications puts the outer feet through the
# edges.  There are taken to be no pockets, with the slots running the
# table's whole length.
MIKINI_1610L: SCMillTable = SCMillTable(
    name="Mikini 1610L",
    length=_mm("30 in"),
    width=_mm("10-1/2 in"),
    thickness=_mm("2-1/2 in"),
    slots=5,
    slot_spacing=_mm("2 in"),
    slot_length=_mm("30 in"),
    throat_width=_mm("11/16 in"),
    throat_depth=_mm("1/2 in"),
    head_width=_mm("15/16 in"),
    slot_depth=_mm("1 in"),
    pocket_length=0.0,
    pocket_width=0.0,
)

# How far the Mikini 1610L's axes travel, from its published
# specifications (millimeters).
MIKINI_X_TRAVEL: float = _mm("16.75 in")
MIKINI_Y_TRAVEL: float = _mm("9.35 in")


# Class `SCPrism`:
@dataclass(frozen=True, slots=True)
class SCPrism:
    """A rectangular prism, with its sides along the axes.

    Attributes:
    * `name` (`str`): What it is.
    * `low` (`Point`): Its corner with the smallest X, Y and Z (mm).
    * `high` (`Point`): Its corner with the largest X, Y and Z (mm).

    Constructor:
    * `SCPrism(name, low, high)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    low: Point = field(init=True)
    high: Point = field(init=True)

    # Method `SCPrism.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the prism is not empty.

        Raises:
        * `ValueError`: If `low` is not below `high` on every axis.
        """
        if not all(low < high for low, high in zip(self.low, self.high)):
            raise ValueError(f"{self.low=} must be below {self.high=}")

    # Method `SCPrism.quarter_turned()`:
    def quarter_turned(self, x: float, y: float) -> "SCPrism":
        """Return the prism turned clockwise, seen from above: +X to -Y.

        Arguments:
        * `x` (`float`): The X of the vertical axis (millimeters).
        * `y` (`float`): The Y of the vertical axis (millimeters).

        Returns:
        * (`SCPrism`): The turned prism, with the same name.
        """
        return SCPrism(
            self.name,
            (x + self.low[1] - y, y - self.high[0] + x, self.low[2]),
            (x + self.high[1] - y, y - self.low[0] + x, self.high[2]),
        )

    # Method `SCPrism.grown()`:
    def grown(self, margin: float) -> "SCPrism":
        """Return the prism grown on all six sides.

        Arguments:
        * `margin` (`float`): How far each side moves out (millimeters).

        Returns:
        * (`SCPrism`): The larger prism, with the same name.
        """
        x0, y0, z0 = self.low
        x1, y1, z1 = self.high
        return SCPrism(
            self.name,
            (x0 - margin, y0 - margin, z0 - margin),
            (x1 + margin, y1 + margin, z1 + margin),
        )


# Function `box_prism()`:
def box_prism(name: str, size: Point, center: Point) -> SCPrism:
    """Return the prism around a box, up from the center of its bottom.

    Arguments:
    * `name` (`str`): What it is.
    * `size` (`Point`): Its size along X, Y and Z (millimeters).
    * `center` (`Point`): The center of its bottom face (millimeters).

    Returns:
    * (`SCPrism`): The prism.
    """
    x, y, z = center
    half_x: float = size[0] / 2.0
    half_y: float = size[1] / 2.0
    return SCPrism(
        name,
        (x - half_x, y - half_y, z),
        (x + half_x, y + half_y, z + size[2]),
    )


# Class `SCCylinder`:
@dataclass(frozen=True, slots=True)
class SCCylinder:
    """A cylinder standing along Z.

    Attributes:
    * `name` (`str`): What it is.
    * `center` (`tuple[float, float]`): Its axis' X and Y (mm).
    * `low` (`float`): The Z of its bottom (mm).
    * `high` (`float`): The Z of its top (mm).
    * `radius` (`float`): Its radius (mm).

    Constructor:
    * `SCCylinder(name, center, low, high, radius)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    center: tuple[float, float] = field(init=True)
    low: float = field(init=True)
    high: float = field(init=True)
    radius: float = field(init=True)

    # Method `SCCylinder.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the cylinder is not empty.

        Raises:
        * `ValueError`: If it has no height or no radius.
        """
        if self.low >= self.high or self.radius <= 0.0:
            raise ValueError(f"{self.low=}, {self.high=}, {self.radius=}")

    # Method `SCCylinder.grown()`:
    def grown(self, margin: float) -> "SCCylinder":
        """Return the cylinder grown on its side and both ends.

        Arguments:
        * `margin` (`float`): How far each surface moves out (mm).

        Returns:
        * (`SCCylinder`): The larger cylinder, with the same name.
        """
        return SCCylinder(
            self.name,
            self.center,
            self.low - margin,
            self.high + margin,
            self.radius + margin,
        )


# Class `SCKeepOut`:
@dataclass(slots=True)
class SCKeepOut:
    """The regions that a tool must not enter.

    Attributes:
    * `cylinders` (`list[SCCylinder]`): The cylinders.
    * `prisms` (`list[SCPrism]`): The rectangular prisms.

    Constructor:
    * `SCKeepOut()`
    """

    # Attributes filled in later (alphabetized):
    cylinders: list[SCCylinder] = field(init=False, default_factory=list)
    prisms: list[SCPrism] = field(init=False, default_factory=list)

    # Method `SCKeepOut.add_prism()`:
    def add_prism(self, prism: SCPrism, margin: str) -> SCPrism:
        """Grow a prism and add it as a region to keep out of.

        Arguments:
        * `prism` (`SCPrism`): The prism around the thing to protect.
        * `margin` (`str`):
          How far to grow it on all six sides, with its unit (such as
          `"1/8 in"`).

        Returns:
        * (`SCPrism`): The grown prism that was added.
        """
        grown: SCPrism = prism.grown(_mm(margin))
        self.prisms.append(grown)
        return grown

    # Method `SCKeepOut.add_cylinder()`:
    def add_cylinder(self, cylinder: SCCylinder, margin: str) -> SCCylinder:
        """Grow a cylinder and add it as a region to keep out of.

        Arguments:
        * `cylinder` (`SCCylinder`):
          The cylinder around the thing to protect.
        * `margin` (`str`):
          How far to grow its side and both ends, with its unit (such
          as `"1/8 in"`).

        Returns:
        * (`SCCylinder`): The grown cylinder that was added.
        """
        grown: SCCylinder = cylinder.grown(_mm(margin))
        self.cylinders.append(grown)
        return grown

    # Method `SCKeepOut.model()`:
    def model(self, solidcraft: SCPyBind) -> list[str]:
        """Model the regions in SolidCraft, as see-through bodies.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.

        Returns:
        * (`list[str]`):
          The names of the bodies: the prisms', then the cylinders'.
        """
        return [_model_prism(solidcraft, prism) for prism in self.prisms] + [
            _model_cylinder(solidcraft, cylinder)
            for cylinder in self.cylinders
        ]


# Function `_model_prism()`:
def _model_prism(solidcraft: SCPyBind, prism: SCPrism) -> str:
    """Model one keep-out prism as a see-through body.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `prism` (`SCPrism`): The prism.

    Returns:
    * (`str`): The body's name.
    """
    # Sketch its bottom on a plane at its lowest Z, and extrude it up.
    x0, y0, z0 = prism.low
    x1, y1, z1 = prism.high
    name: str = f"{prism.name} keep out"
    solidcraft.sketch.create(plane="XY", offset=z0, name=name)
    solidcraft.sketch.rectangle_center(
        center=((x0 + x1) / 2.0, (y0 + y1) / 2.0), corner=(x1, y1)
    )
    solidcraft.sketch.finish()
    return _extrude_keep_out(solidcraft, name, z1 - z0)


# Function `_model_cylinder()`:
def _model_cylinder(solidcraft: SCPyBind, cylinder: SCCylinder) -> str:
    """Model one keep-out cylinder as a see-through body.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `cylinder` (`SCCylinder`): The cylinder.

    Returns:
    * (`str`): The body's name.
    """
    # Sketch its bottom on a plane at its lowest Z, and extrude it up.
    name: str = f"{cylinder.name} keep out"
    solidcraft.sketch.create(plane="XY", offset=cylinder.low, name=name)
    solidcraft.sketch.circle_center(
        center=cylinder.center, diameter=2.0 * cylinder.radius
    )
    solidcraft.sketch.finish()
    return _extrude_keep_out(solidcraft, name, cylinder.high - cylinder.low)


# Function `_extrude_keep_out()`:
def _extrude_keep_out(solidcraft: SCPyBind, name: str, height: float) -> str:
    """Extrude the sketch just made into a see-through body.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `name` (`str`): The body's name.
    * `height` (`float`): How far to extrude it up (millimeters).

    Returns:
    * (`str`): The body's name (SolidCraft may change it, if the name
      is taken).
    """
    made: JSON = solidcraft.solid.extrude(distance=height, body_name=name)
    assert isinstance(made, dict)
    bodies: JSON = made["created_bodies"]
    assert isinstance(bodies, list) and isinstance(bodies[0], str)

    # Let what it protects show through.
    solidcraft.appearance.assign(
        bodies=[bodies[0]], color=KEEP_OUT_COLOR, opacity=KEEP_OUT_OPACITY
    )
    return bodies[0]


# Class `SCDrill`:
@dataclass(frozen=True, slots=True)
class SCDrill:
    """A generic twist drill, with straight grooves for its flutes.

    A picture rather than a true drill: each flute is a groove as deep
    as half the drill's radius, running straight up from the tip to the
    shank.  The grooved outline is extruded whole, and the point made by
    cutting away an inverse cone.  All lengths are in millimeters.

    Attributes:
    * `name` (`str`): What it is.
    * `diameter` (`float`): The cutting diameter.
    * `overall_length` (`float`): The length from tip to top.
    * `flutes` (`int`): How many flutes it has (1 to 5).
    * `shank_length` (`float`):
      The length of the plain part at the top, with no grooves.  At 0,
      the grooves run the whole length.
    * `shank_diameter` (`float`):
      The shank's diameter.  At 0, it is the same as `diameter`.
    * `point_angle` (`float`):
      The included angle at the tip (degrees); 180 makes it flat.

    Constructor:
    * `SCDrill(name, diameter, overall_length, flutes, shank_length,
      shank_diameter, point_angle)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    diameter: float = field(init=True)
    overall_length: float = field(init=True)
    flutes: int = field(init=True)
    shank_length: float = field(init=True, default=0.0)
    shank_diameter: float = field(init=True, default=0.0)
    point_angle: float = field(init=True, default=DRILL_POINT_ANGLE)

    # Method `SCDrill.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the numbers describe a drill.

        Raises:
        * `ValueError`: If one of them is out of range, or the shank
          and the point leave no room for the drill's body.
        """
        if self.diameter <= 0.0 or self.shank_diameter < 0.0:
            raise ValueError(f"{self.diameter=}, {self.shank_diameter=}")
        if not 1 <= self.flutes <= 5:
            raise ValueError(f"{self.flutes=} must be 1 to 5")
        if not 0.0 < self.point_angle <= 180.0:
            raise ValueError(f"{self.point_angle=} must be up to 180")
        if self.shank_length < 0.0 or self.body_top() <= self.point_height():
            raise ValueError(
                f"{self.overall_length=} is too short for "
                f"{self.shank_length=} and {self.point_angle=}"
            )

    # Method `SCDrill.point_height()`:
    def point_height(self) -> float:
        """Return how far the cone at the tip reaches up the drill.

        Returns:
        * (`float`): The cone's height (millimeters).
        """
        # A flat tip is exactly flat, not off by a rounding error.
        if self.point_angle == 180.0:
            return 0.0
        half_angle: float = math.radians(self.point_angle / 2.0)
        return (
            self.diameter / 2.0 * math.cos(half_angle) / math.sin(half_angle)
        )

    # Method `SCDrill.body_top()`:
    def body_top(self) -> float:
        """Return how far above the tip the shank starts.

        Returns:
        * (`float`): The height of the shank's bottom (millimeters).
        """
        return self.overall_length - self.shank_length

    # Method `SCDrill.section()`:
    def section(self) -> list[Arc]:
        """Return the drill's grooved outline, as seen from above.

        Each groove is a circle of half the drill's radius, centered on
        the drill's edge.  Using true arcs, rather than short lines,
        leaves no lines along the drill's sides.

        Returns:
        * (`list[Arc]`):
          The arcs of the closed outline, around the drill's axis: for
          each flute, its groove and the edge on to the next groove.
        """
        radius: float = self.diameter / 2.0
        groove: float = radius / 2.0

        # How far either side of a groove's center it meets the edge.
        reach: float = math.acos(1.0 - groove**2 / (2.0 * radius**2))
        pitch: float = 2.0 * math.pi / self.flutes

        # Function `at()`:
        def at(distance: float, angle: float) -> tuple[float, float]:
            """Return the point at a distance and angle from the axis.

            Arguments:
            * `distance` (`float`): How far from the axis.
            * `angle` (`float`): Its direction (radians).

            Returns:
            * (`tuple[float, float]`): The point's `(x, y)`.
            """
            return (distance * math.cos(angle), distance * math.sin(angle))

        arcs: list[Arc] = []
        for flute in range(self.flutes):
            angle: float = flute * pitch
            arcs.append(
                (
                    at(radius, angle - reach),
                    at(groove, angle),
                    at(radius, angle + reach),
                )
            )
            arcs.append(
                (
                    at(radius, angle + reach),
                    at(radius, angle + pitch / 2.0),
                    at(radius, angle + pitch - reach),
                )
            )
        return arcs

    # Method `SCDrill.point_cutter()`:
    def point_cutter(self) -> list[tuple[float, float]]:
        """Return the outline of the inverse cone that makes the point.

        Revolved, it is all that lies outside the point's cone, from
        just below the tip to past the drill's side.

        Returns:
        * (`list[tuple[float, float]]`):
          The closed outline's `(radius, height)` points, from the tip.
        """
        reach: float = self.diameter / 2.0 + 1.0
        rise: float = reach * self.point_height() / (self.diameter / 2.0)
        return [(0.0, 0.0), (reach, rise), (reach, -1.0), (0.0, -1.0)]

    # Method `SCDrill.groove_area()`:
    def groove_area(self) -> float:
        """Return the area one groove removes from the drill's section.

        Returns:
        * (`float`): The area (square millimeters).
        """
        big: float = self.diameter / 2.0
        small: float = big / 2.0
        return (
            big**2 * math.acos(1.0 - small**2 / (2.0 * big**2))
            + small**2 * math.acos(small / (2.0 * big))
            - 0.5 * small * math.sqrt(4.0 * big**2 - small**2)
        )

    # Method `SCDrill.cylinder()`:
    def cylinder(self, tip: tuple[float, float, float]) -> SCCylinder:
        """Return the cylinder that just encloses the drill.

        Arguments:
        * `tip` (`tuple[float, float, float]`): Where its tip is (mm).

        Returns:
        * (`SCCylinder`): The cylinder, named for the drill.
        """
        radius: float = max(self.diameter, self.shank_diameter) / 2.0
        return SCCylinder(
            self.name,
            (tip[0], tip[1]),
            tip[2],
            tip[2] + self.overall_length,
            radius,
        )

    # Method `SCDrill.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        tip: tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: str = DRILL_COLOR,
    ) -> str:
        """Model the drill, standing on its tip.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `tip` (`tuple[float, float, float]`): Where its tip goes (mm).
        * `color` (`str`): Its color, as `"#rrggbb"`.

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # Extrude the grooved outline, from the tip's height up to the shank.
        x, y, z = tip
        solidcraft.sketch.create(
            plane="XY", offset=z, name=f"{self.name} section"
        )
        for start, through, end in self.section():
            solidcraft.sketch.arc_three_point(
                start=[x + start[0], y + start[1]],
                through=[x + through[0], y + through[1]],
                end=[x + end[0], y + end[1]],
            )
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=self.body_top(), body_name=self.name
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        body: str = bodies[0]

        # Join on the shank, if it has one.
        if self.shank_length > 0.0:
            solidcraft.sketch.create(
                plane="XY",
                offset=z + self.body_top(),
                name=f"{self.name} shank",
            )
            solidcraft.sketch.circle_center(
                center=(x, y), diameter=self.shank_diameter or self.diameter
            )
            solidcraft.sketch.finish()
            solidcraft.solid.extrude(
                distance=self.shank_length,
                operation="join",
                targets=[body],
            )

        # Make the point by cutting away an inverse cone.
        if self.point_height() > 0.0:
            solidcraft.sketch.create(
                plane={
                    "origin": list(tip),
                    "x_dir": [1.0, 0.0, 0.0],
                    "y_dir": [0.0, 0.0, 1.0],
                },
                name=f"{self.name} point",
            )
            solidcraft.sketch.line(
                points=[[r, h] for r, h in self.point_cutter()], closed=True
            )
            solidcraft.sketch.finish()
            solidcraft.solid.revolve(
                axis={"origin": list(tip), "dir": [0.0, 0.0, 1.0]},
                operation="cut",
                targets=[body],
            )
        solidcraft.appearance.assign(bodies=[body], color=color)
        return body


# Sample drills, showing the variations.
SAMPLE_DRILLS: tuple[SCDrill, ...] = (
    SCDrill("Drill 1/4 x 4", _mm("1/4 in"), _mm("4 in"), 2, _mm("1-1/2 in")),
    SCDrill("Drill 1/2 x 6", _mm("1/2 in"), _mm("6 in"), 2, _mm("2 in")),
    SCDrill(
        "Drill 1 x 6, 1/2 shank",
        _mm("1 in"),
        _mm("6 in"),
        2,
        _mm("3 in"),
        _mm("1/2 in"),
    ),
    SCDrill(
        "Drill 3/4 x 8, 3 flute", _mm("3/4 in"), _mm("8 in"), 3, _mm("3 in")
    ),
    SCDrill("Drill 1/2 x 4, 4 flute", _mm("1/2 in"), _mm("4 in"), 4),
)


# Function `sample_drills()`:
def sample_drills(
    solidcraft: SCPyBind,
) -> tuple[list[str], SCKeepOut]:
    """Model `SAMPLE_DRILLS` in a row, each with a keep-out cylinder.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Returns:
    * (`tuple[list[str], SCKeepOut]`):
      The names of the drills' bodies, and their keep-out regions.
    """
    bodies: list[str] = []
    keep_out: SCKeepOut = SCKeepOut()
    for index, (drill, color) in enumerate(
        zip(SAMPLE_DRILLS, SAMPLE_DRILL_COLORS)
    ):
        center: float = (index - (len(SAMPLE_DRILLS) - 1) / 2) * DRILL_SPACING
        tip: tuple[float, float, float] = (center, DRILL_ROW_Y, 0.0)
        bodies.append(drill.model(solidcraft, tip, color))
        keep_out.add_cylinder(drill.cylinder(tip), DRILL_MARGIN)
    return bodies, keep_out


# Class `SCDoubleEndCountersink`:
@dataclass(frozen=True, slots=True)
class SCDoubleEndCountersink:
    """A combined drill and countersink, cut at both ends (a center drill).

    A body with a small drill at each end, joined by a cone.  It stands
    on one tip, with its axis along Z.  It is a solid of revolution,
    with a small flat on each tip, and its flutes are lines drawn on
    its surface.  All lengths are in millimeters.

    The catalog gives no length for the small drill, so each is taken to
    reach as far from its tip as it is wide, the usual proportion.

    Attributes:
    * `order_number` (`str`): The catalog's order number.
    * `family` (`str`): Which of the catalog's tables it is from.
    * `size` (`str`): The catalog's size number (empty if metric).
    * `body_diameter` (`float`): The diameter of its body.
    * `drill_diameter` (`float`): The diameter of the small drills.
    * `overall_length` (`float`): Its length, from tip to tip.
    * `angle` (`float`): The countersink's included angle (degrees).
    * `radius` (`float`):
      The catalog's radius, for the radius type (otherwise 0).  It is
      only kept as data: the model has a plain cone, at the user's word.
    * `left_hand` (`bool`): True if it cuts left handed.
    * `point_angle` (`float`):
      The included angle of the small drills' points (degrees).

    Constructor:
    * `SCDoubleEndCountersink(order_number, family, size, body_diameter,
      drill_diameter, overall_length, angle, radius, left_hand,
      point_angle)`
    """

    # Constructor arguments:
    order_number: str = field(init=True)
    family: str = field(init=True)
    size: str = field(init=True)
    body_diameter: float = field(init=True)
    drill_diameter: float = field(init=True)
    overall_length: float = field(init=True)
    angle: float = field(init=True)
    radius: float = field(init=True, default=0.0)
    left_hand: bool = field(init=True, default=False)
    point_angle: float = field(init=True, default=COUNTERSINK_POINT_ANGLE)

    # Method `SCDoubleEndCountersink.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that both ends fit on the body.

        Raises:
        * `ValueError`: If the sizes do not make a countersink.
        """
        if not 0.0 < self.drill_diameter < self.body_diameter:
            raise ValueError(
                f"{self.order_number}: {self.drill_diameter=} must be "
                f"less than {self.body_diameter=}"
            )
        if not 0.0 < self.angle < 180.0:
            raise ValueError(f"{self.order_number}: {self.angle=}")
        if 2.0 * self.body_start() >= self.overall_length:
            raise ValueError(
                f"{self.order_number}: its ends need "
                f"{2.0 * self.body_start():g} of {self.overall_length=}"
            )

    # Method `SCDoubleEndCountersink.name()`:
    def name(self) -> str:
        """Return a name for its body.

        Returns:
        * (`str`): The name, with its order number.
        """
        return f"Countersink {self.order_number}"

    # Method `SCDoubleEndCountersink.step()`:
    def step(self) -> float:
        """Return how far the body's radius is past the small drill's.

        Returns:
        * (`float`): The difference (millimeters).
        """
        return (self.body_diameter - self.drill_diameter) / 2.0

    # Method `SCDoubleEndCountersink.tip_radius()`:
    def tip_radius(self) -> float:
        """Return the radius of the flat on each tip.

        Returns:
        * (`float`): The radius (millimeters).
        """
        return COUNTERSINK_TIP_FLAT * self.drill_diameter / 2.0

    # Method `SCDoubleEndCountersink.point_height()`:
    def point_height(self) -> float:
        """Return the height of the point, from the flat to the drill.

        Returns:
        * (`float`): The height (millimeters).
        """
        half: float = math.radians(self.point_angle / 2.0)
        drop: float = self.drill_diameter / 2.0 - self.tip_radius()
        return drop / math.tan(half)

    # Method `SCDoubleEndCountersink.body_start()`:
    def body_start(self) -> float:
        """Return how far the full body starts from a tip.

        Returns:
        * (`float`): The distance (millimeters).
        """
        rise: float = self.step() / math.tan(math.radians(self.angle / 2.0))
        return self.drill_diameter + rise

    # Method `SCDoubleEndCountersink.profile()`:
    def profile(self) -> list[tuple[float, float]]:
        """Return its outline, from one tip along its side to the other.

        Returns:
        * (`list[tuple[float, float]]`):
          The `(radius, height)` of each point (millimeters), starting
          and ending on the axis.
        """
        drill: float = self.drill_diameter / 2.0
        side: list[tuple[float, float]] = [
            (0.0, 0.0),
            (self.tip_radius(), 0.0),
            (drill, self.point_height()),
            (drill, self.drill_diameter),
            (self.body_diameter / 2.0, self.body_start()),
        ]
        return side + [
            (radius, self.overall_length - height)
            for radius, height in reversed(side)
        ]

    # Method `SCDoubleEndCountersink.flute_runs()`:
    def flute_runs(self) -> list[FluteRun]:
        """Return the lines that stand for the flutes at both ends.

        Returns:
        * (`list[FluteRun]`): The lines (millimeters), straight along
          the outline from each point's shoulder to the full body.
        """
        lower: list[FluteRun] = flute_runs(
            self.profile()[2:5], COUNTERSINK_FLUTES
        )
        upper: list[FluteRun] = [
            (
                command,
                [[x, y, self.overall_length - z] for x, y, z in points],
            )
            for command, points in lower
        ]
        return lower + upper

    # Method `SCDoubleEndCountersink.volume()`:
    def volume(self) -> float:
        """Return the volume the model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        points: list[tuple[float, float]] = self.profile()
        return sum(
            math.pi
            / 3.0
            * (top[1] - bottom[1])
            * (bottom[0] ** 2 + bottom[0] * top[0] + top[0] ** 2)
            for bottom, top in itertools.pairwise(points)
        )

    # Method `SCDoubleEndCountersink.cylinder()`:
    def cylinder(self, tip: Point) -> SCCylinder:
        """Return the cylinder that just encloses it.

        Arguments:
        * `tip` (`Point`): Where its lower tip is (millimeters).

        Returns:
        * (`SCCylinder`): The cylinder, named for it.
        """
        return SCCylinder(
            self.name(),
            (tip[0], tip[1]),
            tip[2],
            tip[2] + self.overall_length,
            self.body_diameter / 2.0,
        )

    # Method `SCDoubleEndCountersink.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        tip: Point = (0.0, 0.0, 0.0),
        color: str = DRILL_COLOR,
    ) -> str:
        """Sketch its outline and revolve it about its axis.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `tip` (`Point`): Where its lower tip is (millimeters).
        * `color` (`str`): How it looks.

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The plane has sketch X along the radius, and sketch Y up.
        solidcraft.sketch.create(
            plane={
                "origin": list(tip),
                "x_dir": [1.0, 0.0, 0.0],
                "y_dir": [0.0, 0.0, 1.0],
            },
            name=f"{self.name()} profile",
        )
        drawn: JSON = solidcraft.sketch.line(
            points=[[r, z] for r, z in self.profile()], closed=True
        )
        assert isinstance(drawn, dict)
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.revolve(
            axis={"origin": list(tip), "dir": [0.0, 0.0, 1.0]},
            profiles=[{"curves": drawn["curves"]}],
            body_name=self.name(),
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        solidcraft.appearance.assign(bodies=[bodies[0]], color=color)

        # Draw the flutes on it.
        send_batch(
            solidcraft,
            flute_steps(f"{self.name()} flutes", self.flute_runs(), tip, 1.0),
        )
        return bodies[0]


# Rows of the catalog's tables: size, body, drill and overall length.
_COUNTERSINK_SIZES: dict[str, tuple[str, str, str, str]] = {
    "1": ("1/8 in", "3/64 in", "1-1/4 in", "5/32 in"),
    "2": ("3/16 in", "5/64 in", "1-7/8 in", "7/32 in"),
    "3": ("1/4 in", "7/64 in", "2 in", "9/32 in"),
    "4": ("5/16 in", "1/8 in", "2-1/8 in", "3/8 in"),
    "4-1/2": ("3/8 in", "9/64 in", "2-1/2 in", "7/16 in"),
    "5": ("7/16 in", "3/16 in", "2-3/4 in", "1/2 in"),
    "6": ("1/2 in", "7/32 in", "3 in", "9/16 in"),
    "7": ("5/8 in", "1/4 in", "3-1/4 in", "45/64 in"),
    "8": ("3/4 in", "5/16 in", "3-1/2 in", "7/8 in"),
    "9": ("7/8 in", "11/32 in", "3-5/8 in", "1 in"),
    "10": ("1 in", "3/8 in", "3-3/4 in", "1-7/64 in"),
}


# Function `_inch_countersink()`:
def _inch_countersink(
    order_number: str,
    family: str,
    size: str,
    angle: float,
) -> SCDoubleEndCountersink:
    """Return a countersink with one of the catalog's inch sizes.

    Arguments:
    * `order_number` (`str`): The catalog's order number.
    * `family` (`str`): Which of the tables it is from.
    * `size` (`str`): Its size number.
    * `angle` (`float`): Its included angle (degrees).

    Returns:
    * (`SCDoubleEndCountersink`): The countersink.
    """
    body, drill, length, radius = _COUNTERSINK_SIZES[size]
    return SCDoubleEndCountersink(
        order_number,
        family,
        size,
        _mm(body),
        _mm(drill),
        _mm(length),
        angle,
        _mm(radius) if family == "Radius" else 0.0,
        family == "Left hand",
    )


# The Shars 2026 catalog's page 24, with both ends cut: the radius type,
# the plain 82 and 90 degree type (a row has an order number for each),
# the metric DIN 333 type and the left hand type, which stops at size 7.
DOUBLE_END_COUNTERSINKS: dict[str, SCDoubleEndCountersink] = {
    countersink.order_number: countersink
    for countersink in (
        *(
            _inch_countersink(order_number, "Radius", size, 60.0)
            for size, order_number in (
                ("1", "421-0130"),
                ("2", "421-0145"),
                ("3", "421-0160"),
                ("4", "421-0175"),
                ("4-1/2", "421-0379"),
                ("5", "421-0190"),
                ("6", "421-0205"),
                ("7", "421-0220"),
                ("8", "421-0235"),
                ("9", "421-0250"),
                ("10", "421-0261"),
            )
        ),
        *(
            _inch_countersink(order_number, "Plain", size, angle)
            for size, order_82, order_90 in (
                ("1", "421-0139", "421-0141"),
                ("2", "421-0154", "421-0156"),
                ("3", "421-0169", "421-0171"),
                ("4", "421-0184", "421-0186"),
                ("5", "421-0199", "421-0201"),
                ("6", "421-0214", "421-0216"),
                ("7", "421-0229", "421-0231"),
                ("8", "421-0244", "421-0246"),
            )
            for order_number, angle in ((order_82, 82.0), (order_90, 90.0))
        ),
        *(
            SCDoubleEndCountersink(
                order_number,
                "Metric",
                "",
                _mm(f"{body} mm"),
                _mm(f"{drill} mm"),
                _mm(f"{length} mm"),
                60.0,
            )
            for body, drill, length, order_number in (
                ("3.15", "0.50", "25.00", "421-0388"),
                ("3.15", "1.00", "31.50", "421-0390"),
                ("3.15", "1.25", "31.50", "421-0391"),
                ("4.00", "1.60", "35.50", "421-0392"),
                ("5.00", "2.00", "40.00", "421-0393"),
                ("6.30", "2.50", "45.00", "421-0394"),
                ("8.00", "3.15", "50.00", "421-0395"),
                ("10.00", "4.00", "56.00", "421-0396"),
                ("12.50", "5.00", "63.00", "421-0397"),
                ("16.00", "6.30", "71.00", "421-0398"),
            )
        ),
        *(
            _inch_countersink(order_number, "Left hand", size, 60.0)
            for size, order_number in (
                ("1", "421-0138"),
                ("2", "421-0153"),
                ("3", "421-0168"),
                ("4", "421-0183"),
                ("5", "421-0198"),
                ("6", "421-0213"),
                ("7", "421-0228"),
            )
        ),
    )
}


# Function `largest_countersinks()`:
def largest_countersinks(solidcraft: SCPyBind) -> list[str]:
    """Model the largest countersink of each table, side by side.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Returns:
    * (`list[str]`): The names of the bodies.
    """
    bodies: list[str] = []
    for column, (family, color) in enumerate(COUNTERSINK_COLORS.items()):
        largest: SCDoubleEndCountersink = max(
            (
                countersink
                for countersink in DOUBLE_END_COUNTERSINKS.values()
                if countersink.family == family
            ),
            key=lambda countersink: countersink.body_diameter,
        )
        tip: Point = (column * COUNTERSINK_SPACING, 0.0, 0.0)
        bodies.append(largest.model(solidcraft, tip, color))
    return bodies


# Function `countersink_rows()`:
def countersink_rows(
    solidcraft: SCPyBind,
) -> list[str]:
    """Model all of `DOUBLE_END_COUNTERSINKS`, a row for each table.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Returns:
    * (`list[str]`): The names of the bodies.
    """
    bodies: list[str] = []
    for row, (family, color) in enumerate(COUNTERSINK_COLORS.items()):
        members: list[SCDoubleEndCountersink] = [
            countersink
            for countersink in DOUBLE_END_COUNTERSINKS.values()
            if countersink.family == family
        ]
        for column, countersink in enumerate(members):
            tip: Point = (
                (column - (len(members) - 1) / 2.0) * COUNTERSINK_SPACING,
                row * COUNTERSINK_SPACING,
                0.0,
            )
            bodies.append(countersink.model(solidcraft, tip, color))
    return bodies


# Class `SCViseNotches`:
@dataclass(frozen=True, slots=True)
class SCViseNotches:
    """The notches in both sides of one layer of a vise's base.

    Each side has one rectangular notch per center, so the notches on
    the two sides line up.  All four of a notch's corners are rounded.
    All lengths are in millimeters.

    Attributes:
    * `centers` (`tuple[float, ...]`):
      The X of each notch's center (X1, X2, ...), from the block's
      center, from most negative up.  Empty, the sides are plain.
    * `width` (`float`): A notch's size along X.
    * `depth` (`float`): How far a notch reaches in from the side.
    * `inner_radius` (`float`): The radius of its two corners farthest in.
    * `outer_radius` (`float`):
      The radius of its two corners where it meets the side.

    Constructor:
    * `SCViseNotches(centers, width, depth, inner_radius, outer_radius)`
    """

    # Constructor arguments:
    centers: tuple[float, ...] = field(init=True)
    width: float = field(init=True)
    depth: float = field(init=True)
    inner_radius: float = field(init=True)
    outer_radius: float = field(init=True)

    # Method `SCViseNotches.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the numbers describe notches.

        Raises:
        * `ValueError`: If one is out of range or out of order.
        """
        if self.width <= 0.0 or self.depth <= 0.0:
            raise ValueError(f"{self.width=}, {self.depth=}")
        if self.inner_radius < 0.0 or self.outer_radius < 0.0:
            raise ValueError(f"{self.inner_radius=}, {self.outer_radius=}")
        if list(self.centers) != sorted(self.centers):
            raise ValueError(f"{self.centers=} must be in order")

    # Method `SCViseNotches.side_corners()`:
    def side_corners(self, edge_y: float, direction: int) -> list[SCCorner]:
        """Return the corners of the notches along one side of a block.

        Arguments:
        * `edge_y` (`float`): The Y of the side (millimeters).
        * `direction` (`int`):
          +1 for the -Y side, walked toward +X; -1 for the +Y side, walked
          toward -X.  Either way, the block lies to the left.

        Returns:
        * (`list[SCCorner]`): Four corners per notch, in walking order.
        """
        half: float = direction * self.width / 2.0
        inner_y: float = edge_y + direction * self.depth
        corners: list[SCCorner] = []
        for center in self.centers[::direction]:
            corners += [
                SCCorner(center - half, edge_y, self.outer_radius),
                SCCorner(center - half, inner_y, self.inner_radius),
                SCCorner(center + half, inner_y, self.inner_radius),
                SCCorner(center + half, edge_y, self.outer_radius),
            ]
        return corners

    # Method `SCViseNotches.area()`:
    def area(self) -> float:
        """Return the area that all of the notches remove from a block.

        Returns:
        * (`float`): The area (square millimeters).
        """
        # An inner corner's round leaves material; an outer's removes it.
        fillet: float = 1.0 - math.pi / 4.0
        one: float = self.width * self.depth + 2.0 * fillet * (
            self.outer_radius**2 - self.inner_radius**2
        )
        return 2.0 * len(self.centers) * one


# Class `SCViseBlock`:
@dataclass(frozen=True, slots=True)
class SCViseBlock:
    """A block of a vise: a layer of its base, or a jaw.

    Its outline is a rectangle with rounded corners, and perhaps notches
    in its sides, extruded straight up.  All lengths are in millimeters.

    Attributes:
    * `length` (`float`): Its size along X, the lead screw's direction.
    * `width` (`float`): Its size along Y.
    * `height` (`float`): Its size along Z.
    * `corner_radius` (`float`): The radius of its four corners.

    Constructor:
    * `SCViseBlock(length, width, height, corner_radius)`
    """

    # Constructor arguments:
    length: float = field(init=True)
    width: float = field(init=True)
    height: float = field(init=True)
    corner_radius: float = field(init=True, default=0.0)

    # Method `SCViseBlock.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the numbers describe a block.

        Raises:
        * `ValueError`: If it has no size, or its corners do not fit.
        """
        if min(self.length, self.width, self.height) <= 0.0:
            raise ValueError(f"{self.length=}, {self.width=}, {self.height=}")
        if not 0.0 <= 2.0 * self.corner_radius <= min(self.length, self.width):
            raise ValueError(f"{self.corner_radius=} does not fit")

    # Method `SCViseBlock.outline()`:
    def outline(
        self,
        name: str,
        center: tuple[float, float] = (0.0, 0.0),
        notches: SCViseNotches | None = None,
    ) -> SCRoundedPolygon:
        """Return the block's outline, as seen from above.

        Arguments:
        * `name` (`str`): The outline's name.
        * `center` (`tuple[float, float]`): Its center's X and Y (mm).
        * `notches` (`SCViseNotches | None`): The notches in its sides.

        Returns:
        * (`SCRoundedPolygon`): The outline, counter-clockwise.

        Raises:
        * `ValueError`: If the notches do not fit the block.
        """
        x, y = center
        half_x: float = self.length / 2.0
        half_y: float = self.width / 2.0
        radius: float = self.corner_radius

        # Walk around counter-clockwise, about the origin for now.
        low_side: list[SCCorner] = []
        high_side: list[SCCorner] = []
        if notches is not None:
            low_side = notches.side_corners(-half_y, 1)
            high_side = notches.side_corners(half_y, -1)
        corners: list[SCCorner] = [
            SCCorner(-half_x, -half_y, radius),
            *low_side,
            SCCorner(half_x, -half_y, radius),
            SCCorner(half_x, half_y, radius),
            *high_side,
            SCCorner(-half_x, half_y, radius),
        ]
        return SCRoundedPolygon(
            name,
            [
                SCCorner(x + corner.x, y + corner.y, corner.radius)
                for corner in corners
            ],
            0.0,
            self.height,
        )

    # Method `SCViseBlock.volume()`:
    def volume(self, notches: SCViseNotches | None = None) -> float:
        """Return the volume the model should have.

        Arguments:
        * `notches` (`SCViseNotches | None`): The notches in its sides.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        corners: float = (4.0 - math.pi) * self.corner_radius**2
        removed: float = 0.0 if notches is None else notches.area()
        return (self.length * self.width - corners - removed) * self.height

    # Method `SCViseBlock.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        name: str,
        center: Point = (0.0, 0.0, 0.0),
        notches: SCViseNotches | None = None,
    ) -> str:
        """Model the block, up from the center of its bottom face.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `name` (`str`): The body's name.
        * `center` (`Point`): The center of its bottom face (mm).
        * `notches` (`SCViseNotches | None`): The notches in its sides.

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # Sketch the outline at the bottom face, and extrude it up.
        x, y, z = center
        solidcraft.sketch.create(plane="XY", offset=z, name=name)
        self.outline(name, (x, y), notches).sketch(solidcraft)
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=self.height, body_name=name
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        solidcraft.appearance.assign(bodies=[bodies[0]], color=VISE_COLOR)
        return bodies[0]


# Class `SCJawPlate`:
@dataclass(frozen=True, slots=True)
class SCJawPlate:
    """A jaw plate: the replaceable part of a vise's jaw that clamps.

    A machine vise's jaw plates are separate parts, each held to its jaw
    by two socket head cap screws.  Each screw goes through a counterbore
    in the clamping face, so that its head sits below the face.  The
    hole patterns are standard enough that plates from one maker fit
    another's vises: a 6 in vise has holes on 3.875 in centers, for
    1/2-13 screws.

    The plate is a block: `length` is its thickness, from its clamping
    face back to its jaw; `width` runs across the vise, and `height` up.
    All lengths are in millimeters.

    Attributes:
    * `screw` (`str`): The screws that hold it on (e.g. `1/2-13 SHCS`).
    * `length` (`float`): Its thickness, from its clamping face back.
    * `width` (`float`): Its size across the vise.
    * `height` (`float`): Its size up.
    * `hole_spacing` (`float`): The distance between its two holes.
    * `hole_diameter` (`float`): The diameter of its holes.
    * `hole_height` (`float`):
      The height of its holes' centers above its bottom.
    * `counterbore_diameter` (`float`):
      The diameter of the counterbores, for the screws' heads.
    * `counterbore_depth` (`float`):
      How deep the counterbores reach in from the clamping face.

    Constructor:
    * `SCJawPlate(screw, length, width, height, hole_spacing,
      hole_diameter, hole_height, counterbore_diameter,
      counterbore_depth)`
    """

    # Constructor arguments:
    screw: str = field(init=True)
    length: float = field(init=True)
    width: float = field(init=True)
    height: float = field(init=True)
    hole_spacing: float = field(init=True)
    hole_diameter: float = field(init=True)
    hole_height: float = field(init=True)
    counterbore_diameter: float = field(init=True)
    counterbore_depth: float = field(init=True)

    # Method `SCJawPlate.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the holes and counterbores fit the plate.

        Raises:
        * `ValueError`: If the plate has no size, or they do not fit.
        """
        if min(self.length, self.width, self.height) <= 0.0:
            raise ValueError(f"{self.length=}, {self.width=}, {self.height=}")

        # The counterbores are the wider part of each hole, so they are
        # what must fit, beside each other and inside the plate.
        hole: float = self.hole_diameter / 2.0
        counterbore: float = self.counterbore_diameter / 2.0
        if not 0.0 < hole < counterbore or not (
            0.0 < self.counterbore_depth < self.length
        ):
            raise ValueError(
                f"{self.hole_diameter=} and {self.counterbore_diameter=} "
                f"{self.counterbore_depth=} deep do not fit the plate"
            )
        if (
            self.hole_spacing <= 2.0 * counterbore
            or self.hole_spacing / 2.0 + counterbore >= self.width / 2.0
            or self.hole_height - counterbore <= 0.0
            or self.hole_height + counterbore >= self.height
        ):
            raise ValueError(
                f"{self.hole_diameter=} and {self.counterbore_diameter=} "
                f"{self.counterbore_depth=} deep, at {self.hole_spacing=} "
                f"and {self.hole_height=}, do not fit the plate"
            )

    # Method `SCJawPlate.block()`:
    def block(self) -> SCViseBlock:
        """Return the plate without its holes.

        Returns:
        * (`SCViseBlock`): The block.
        """
        return SCViseBlock(self.length, self.width, self.height)

    # Method `SCJawPlate.volume()`:
    def volume(self) -> float:
        """Return the volume its model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        hole: float = math.pi * (self.hole_diameter / 2.0) ** 2
        counterbore: float = math.pi * (self.counterbore_diameter / 2.0) ** 2
        deep: float = self.counterbore_depth
        each: float = hole * (self.length - deep) + counterbore * deep
        return self.block().volume() - 2.0 * each

    # Method `SCJawPlate.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        name: str,
        center: Point = (0.0, 0.0, 0.0),
        facing: float = 1.0,
    ) -> str:
        """Model the plate, with its holes and counterbores.

        Its thickness is along X, and its width along Y.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `name` (`str`): The body's name.
        * `center` (`Point`): The center of its bottom face (mm).
        * `facing` (`float`):
          `1.0` if its clamping face faces +X, `-1.0` if it faces -X.

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        body: str = self.block().model(solidcraft, name, center)

        # Cut the holes through it, then the counterbores, each from the
        # clamping face in.  The face's sketch looks back into the plate.
        x, y, z = center
        plane: dict[str, JSON] = {
            "origin": [x + facing * self.length / 2.0, y, z],
            "x_dir": [0.0, facing, 0.0],
            "y_dir": [0.0, 0.0, 1.0],
        }
        half: float = self.hole_spacing / 2.0
        for diameter, depth, part in (
            (self.hole_diameter, self.length, "holes"),
            (
                self.counterbore_diameter,
                self.counterbore_depth,
                "counterbores",
            ),
        ):
            solidcraft.sketch.create(plane=plane, name=f"{name} {part}")
            for across in (-half, half):
                solidcraft.sketch.circle_center(
                    center=(across, self.hole_height), diameter=diameter
                )
            solidcraft.sketch.finish()
            solidcraft.solid.extrude(
                distance=depth,
                direction="negative",
                operation="cut",
                targets=[body],
            )
        return body


# Class `SCMachineVise`:
@dataclass(frozen=True, slots=True)
class SCMachineVise:
    """A machine vise, of the kind that Kurt makes.

    A picture rather than a true vise: enough to know what it is.  A real
    Kurt is one casting; the model stacks it in layers, named from the
    bottom up: the base, the body and the bed.  On the bed sit the fixed
    jaw and the movable jaw, each with a jaw plate on its clamping face.

    The base and the body are blocks, stacked and centered on one
    another.  They have notches in both sides that line up, for hold
    downs: the body's are bigger, so that a box wrench fits around the
    nut.  The bed is two rails that run the whole length, with an end
    block between them at each end.  Under the opening that leaves, the
    body has a pocket down to the base, where the lead screw shows.

    The lead screw is a cylinder along X, from the pocket's -X end out
    through a hole in the body's +X end, ending in an extruded hexagon.

    The jaws sit on the bed: the fixed jaw at the -X end, away from the
    hexagon, and the movable jaw opening toward +X.  Under the movable
    jaw, a slider fits between the rails and reaches down through the
    pocket, with a hole that the lead screw goes through.  It starts at
    the jaw's clamping face and is shorter than the jaw by an end block's
    length, so that the jaw reaches the bed's +X end as the slider meets
    the end block.  The jaw plates do the actual clamping; each has two
    holes for the screws that hold it on.

    All lengths are in millimeters.

    Attributes:
    * `name` (`str`): What it is.
    * `base` (`SCViseBlock`): The bottom layer.
    * `body` (`SCViseBlock`): The layer on the base.
    * `base_notches` (`SCViseNotches`): The notches in the base.
    * `body_notches` (`SCViseNotches`):
      The notches in the body, at the same places but bigger.
    * `rail_width` (`float`): A bed rail's size along Y.
    * `rail_height` (`float`): The height of the bed: its rails and end
      blocks.
    * `rail_gap` (`float`): The distance between the rails.
    * `end_block_length` (`float`): An end block's size along X.
    * `fixed_jaw` (`SCViseBlock`): The jaw that stays put.
    * `movable_jaw` (`SCViseBlock`): The jaw that the lead screw moves.
    * `jaw_plate` (`SCJawPlate`): The jaw plate on each jaw.
    * `max_opening` (`float`): The largest gap between the jaw plates.
    * `lead_screw_diameter` (`float`): The lead screw's diameter.
    * `lead_screw_stick_out` (`float`):
      How far the lead screw's cylinder reaches past the body's +X end.
    * `lead_screw_height` (`float`):
      The height of the lead screw's axis above the base's bottom.
    * `lead_screw_hole_diameter` (`float`):
      The diameter of the hole for the lead screw in the body's end.
    * `hex_size` (`float`):
      The size across the flats of the hexagon on the lead screw's end.
    * `hex_length` (`float`): The hexagon's size along X.

    Constructor:
    * `SCMachineVise(name, base, body, base_notches, body_notches,
      rail_width, rail_height, rail_gap, end_block_length, fixed_jaw,
      movable_jaw, jaw_plate, max_opening, lead_screw_diameter,
      lead_screw_stick_out, lead_screw_height, lead_screw_hole_diameter,
      hex_size, hex_length)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    base: SCViseBlock = field(init=True)
    body: SCViseBlock = field(init=True)
    base_notches: SCViseNotches = field(init=True)
    body_notches: SCViseNotches = field(init=True)
    rail_width: float = field(init=True)
    rail_height: float = field(init=True)
    rail_gap: float = field(init=True)
    end_block_length: float = field(init=True)
    fixed_jaw: SCViseBlock = field(init=True)
    movable_jaw: SCViseBlock = field(init=True)
    jaw_plate: SCJawPlate = field(init=True)
    max_opening: float = field(init=True)
    lead_screw_diameter: float = field(init=True)
    lead_screw_stick_out: float = field(init=True)
    lead_screw_height: float = field(init=True)
    lead_screw_hole_diameter: float = field(init=True)
    hex_size: float = field(init=True)
    hex_length: float = field(init=True)

    # Method `SCMachineVise.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the parts fit together.

        Raises:
        * `ValueError`: If the notches, the rails, the end blocks, the
          jaws, the slider or the lead screw do not fit.
        """
        self._check_notches()

        # The bed's rails must have a size, and stay on the body.
        rails: float = self.rail_gap + 2.0 * self.rail_width
        if (
            min(self.rail_width, self.rail_height, self.rail_gap) <= 0.0
            or rails > self.base.width
        ):
            raise ValueError(
                f"{self.rail_width=}, {self.rail_height=} and "
                f"{self.rail_gap=} do not fit {self.base.width=}"
            )

        # The end blocks must leave an opening between them.
        if not 0.0 < 2.0 * self.end_block_length < self.body.length:
            raise ValueError(
                f"{self.end_block_length=} does not fit {self.body.length=}"
            )

        # The jaws and jaw plates must stay on the bed when wide open.
        jaws: float = (
            self.fixed_jaw.length
            + 2.0 * self.jaw_plate.length
            + self.max_opening
            + self.movable_jaw.length
        )
        if self.max_opening <= 0.0 or jaws > self.body.length:
            raise ValueError(
                f"{self.max_opening=} and the jaws need {jaws:g} of "
                f"{self.body.length=}"
            )

        # The jaws must match, and leave the slider some length.
        if (
            self.fixed_jaw.width != self.movable_jaw.width
            or self.fixed_jaw.height != self.movable_jaw.height
            or self.fixed_jaw.width > self.base.width
        ):
            raise ValueError(
                f"{self.fixed_jaw=} and {self.movable_jaw=} must match, on "
                f"{self.base.width=}"
            )
        if self.movable_jaw.length <= self.end_block_length:
            raise ValueError(
                f"{self.movable_jaw.length=} must exceed "
                f"{self.end_block_length=}"
            )
        self._check_jaw_plate()
        self._check_lead_screw()

    # Method `SCMachineVise._check_notches()`:
    def _check_notches(self) -> None:
        """Check that the notches line up and fit their layers.

        Raises:
        * `ValueError`: If they are not at the same places, the body's
          do not clear the base's or reach the pocket, or they do not
          fit their layers.
        """
        base: SCViseNotches = self.base_notches
        body: SCViseNotches = self.body_notches
        if base.centers != body.centers:
            raise ValueError(
                f"{base.centers=} must line up with {body.centers=}"
            )

        # The body's notches must leave the base's open from above,
        # and a wall beside the pocket.
        base_in: float = self.base.width / 2.0 - base.depth
        body_in: float = self.body.width / 2.0 - body.depth
        if body.width < base.width or body_in > base_in:
            raise ValueError(f"{body=} must clear {base=}")
        if body.centers and body_in <= self.rail_gap / 2.0:
            raise ValueError(f"{body=} reaches the pocket")

        # Making the outlines raises if the notches do not fit.
        self.base.outline(self.name, notches=base)
        self.body.outline(self.name, notches=body)

    # Method `SCMachineVise._check_jaw_plate()`:
    def _check_jaw_plate(self) -> None:
        """Check that a jaw plate fits its jaw.

        Raises:
        * `ValueError`: If it does not.
        """
        if (
            self.jaw_plate.width > self.fixed_jaw.width
            or self.jaw_plate.height > self.fixed_jaw.height
        ):
            raise ValueError(f"{self.jaw_plate=} must fit {self.fixed_jaw=}")

    # Method `SCMachineVise._check_lead_screw()`:
    def _check_lead_screw(self) -> None:
        """Check that the lead screw fits its hole, and its hole the body.

        Raises:
        * `ValueError`: If it does not.
        """
        radius: float = self.lead_screw_hole_diameter / 2.0
        if (
            not 0.0 < self.lead_screw_diameter <= self.lead_screw_hole_diameter
            or self.lead_screw_hole_diameter >= self.rail_gap
            or self.lead_screw_height - radius < self.base.height
            or self.lead_screw_height + radius
            > self.base.height + self.body.height
        ):
            raise ValueError(
                f"{self.lead_screw_diameter=} in "
                f"{self.lead_screw_hole_diameter=} at "
                f"{self.lead_screw_height=} does not fit in {self.body=} "
                f"with {self.rail_gap=}"
            )
        if (
            min(self.lead_screw_stick_out, self.hex_size, self.hex_length)
            <= 0.0
        ):
            raise ValueError(
                f"{self.lead_screw_stick_out=}, {self.hex_size=}, "
                f"{self.hex_length=}"
            )

    # Method `SCMachineVise.bed_top()`:
    def bed_top(self) -> float:
        """Return the height of the top of the bed, above the base's bottom.

        Returns:
        * (`float`): The height (millimeters).
        """
        return self.base.height + self.body.height + self.rail_height

    # Method `SCMachineVise.overall_length()`:
    def overall_length(self) -> float:
        """Return the vise's length, out to the end of the hexagon.

        Returns:
        * (`float`): The length (millimeters).
        """
        return self.body.length + self.lead_screw_stick_out + self.hex_length

    # Method `SCMachineVise.opening_length()`:
    def opening_length(self) -> float:
        """Return the length of the opening between the end blocks.

        Returns:
        * (`float`): The length (millimeters).
        """
        return self.body.length - 2.0 * self.end_block_length

    # Method `SCMachineVise.slider()`:
    def slider(self) -> SCViseBlock:
        """Return the block under the movable jaw, between the rails.

        Returns:
        * (`SCViseBlock`):
          The slider: as wide as the end blocks, shorter than the movable
          jaw by an end block's length, and reaching from the jaw's bottom
          down to the pocket's floor.  Its hole is not included.
        """
        return SCViseBlock(
            self.movable_jaw.length - self.end_block_length,
            self.rail_gap,
            self.body.height + self.rail_height,
        )

    # Method `SCMachineVise.slider_volume()`:
    def slider_volume(self) -> float:
        """Return the volume the slider's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        slider: SCViseBlock = self.slider()
        hole: float = (
            math.pi * (self.lead_screw_diameter / 2.0) ** 2 * slider.length
        )
        return slider.volume() - hole

    # Method `SCMachineVise.jaw_plate_volume()`:
    def jaw_plate_volume(self) -> float:
        """Return the volume a jaw plate's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        return self.jaw_plate.volume()

    # Method `SCMachineVise.movable_face()`:
    def movable_face(self, opening: float) -> float:
        """Return the X of the movable jaw's clamping face, behind its plate.

        Arguments:
        * `opening` (`float`): The gap between the jaw plates (millimeters).

        Returns:
        * (`float`): Its X, from the center of the base (millimeters).

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        if not 0.0 <= opening <= self.max_opening:
            raise ValueError(
                f"{opening=} must be from 0 to {self.max_opening=}"
            )
        return (
            -self.body.length / 2.0
            + self.fixed_jaw.length
            + 2.0 * self.jaw_plate.length
            + opening
        )

    # Method `SCMachineVise.gap_center()`:
    def gap_center(self, opening: float) -> float:
        """Return the X of the middle of the gap between the jaw plates.

        Arguments:
        * `opening` (`float`): The gap between the jaw plates (millimeters).

        Returns:
        * (`float`): Its X, from the center of the base (millimeters).

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        return (
            self.movable_face(opening) - self.jaw_plate.length - opening / 2.0
        )

    # Method `SCMachineVise.hexagon()`:
    def hexagon(self) -> list[tuple[float, float]]:
        """Return the corners of the lead screw's hexagon, flats up and down.

        Returns:
        * (`list[tuple[float, float]]`):
          The `(y, z)` of each corner, from the lead screw's axis.
        """
        radius: float = self.hex_size / math.sqrt(3.0)
        return [
            (
                radius * math.cos(math.radians(60.0 * index)),
                radius * math.sin(math.radians(60.0 * index)),
            )
            for index in range(6)
        ]

    # Method `SCMachineVise.body_volume()`:
    def body_volume(self) -> float:
        """Return the volume the body's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        pocket: float = (
            self.opening_length() * self.rail_gap * self.body.height
        )
        hole: float = (
            math.pi
            * (self.lead_screw_hole_diameter / 2.0) ** 2
            * self.end_block_length
        )
        return self.body.volume(self.body_notches) - pocket - hole

    # Method `SCMachineVise.lead_screw_volume()`:
    def lead_screw_volume(self) -> float:
        """Return the volume the lead screw's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        cylinder: float = (
            math.pi
            * (self.lead_screw_diameter / 2.0) ** 2
            * (
                self.opening_length()
                + self.end_block_length
                + self.lead_screw_stick_out
            )
        )
        hexagon: float = math.sqrt(3.0) / 2.0 * self.hex_size**2
        return cylinder + hexagon * self.hex_length

    # Method `SCMachineVise.keep_out()`:
    # Each edge of the three prisms gets a name, past `pylint`'s limit.
    def keep_out(  # pylint: disable=too-many-locals
        self,
        center: Point = (0.0, 0.0, 0.0),
        opening: float = 0.0,
        margin: str = VISE_MARGIN,
    ) -> SCKeepOut:
        """Return the regions around the vise that a tool must not enter.

        One prism holds the base and the hexagon, one the fixed jaw and
        its plate, and one the movable jaw and its plate.  The movable
        jaw's reaches out to the end of the hexagon, which is where the
        jaw and the wrench on the hexagon go.

        Arguments:
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the jaw plates (mm).
        * `margin` (`str`):
          How far to grow each prism, with its unit (such as `"1/8 in"`).

        Returns:
        * (`SCKeepOut`): The three grown prisms, in that order.

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        x, y, z = center
        half_x: float = self.body.length / 2.0
        hex_end: float = (
            x + half_x + self.lead_screw_stick_out + self.hex_length
        )
        half_base: float = self.base.width / 2.0
        half_jaw: float = self.fixed_jaw.width / 2.0
        rails: float = z + self.bed_top()
        jaw_top: float = rails + self.fixed_jaw.height
        fixed_end: float = (
            x - half_x + self.fixed_jaw.length + self.jaw_plate.length
        )
        moving_start: float = (
            x + self.movable_face(opening) - self.jaw_plate.length
        )

        keep_out: SCKeepOut = SCKeepOut()
        for name, low, high in (
            (
                "base to bed",
                (x - half_x, y - half_base, z),
                (hex_end, y + half_base, rails),
            ),
            (
                "fixed jaw",
                (x - half_x, y - half_jaw, rails),
                (fixed_end, y + half_jaw, jaw_top),
            ),
            (
                "movable jaw",
                (moving_start, y - half_jaw, rails),
                (hex_end, y + half_jaw, jaw_top),
            ),
        ):
            keep_out.add_prism(
                SCPrism(f"{self.name} {name}", low, high), margin
            )
        return keep_out

    # Method `SCMachineVise.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        center: Point = (0.0, 0.0, 0.0),
        opening: float = 0.0,
        lift: float = 0.0,
    ) -> list[str]:
        """Model the vise, up from the center of the base's bottom face.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the bottom face (mm).
        * `opening` (`float`): The gap between the jaw plates (mm).
        * `lift` (`float`):
          How far to raise the jaws, the slider and the jaw plates off
          the bed, to see how they go together (mm).

        Returns:
        * (`list[str]`):
          The names of the bodies: the base, the body, the rails, the end
          blocks, the lead screw, the jaws, the slider and the jaw plates.

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        # Stack the blocks, each on the one before.
        return [
            *self._model_stationary(solidcraft, center),
            *self._model_jaws(solidcraft, center, opening, lift),
        ]

    # Method `SCMachineVise._model_stationary()`:
    def _model_stationary(
        self, solidcraft: SCPyBind, center: Point
    ) -> list[str]:
        """Model what never moves, but for the fixed jaw and its plate.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the bottom face (mm).

        Returns:
        * (`list[str]`):
          The names of the bodies: the base, the body, the rails, the end
          blocks and the lead screw.
        """
        x, y, z = center
        base: str = self.base.model(
            solidcraft, f"{self.name} base", center, self.base_notches
        )
        body: str = self.body.model(
            solidcraft,
            f"{self.name} body",
            (x, y, z + self.base.height),
            self.body_notches,
        )
        self._cut_pocket(solidcraft, body, center)
        self._cut_lead_screw_hole(solidcraft, body, center)
        return [
            base,
            body,
            *self._model_bed(solidcraft, center),
            self._model_lead_screw(solidcraft, center),
        ]

    # Method `SCMachineVise.cacheable()`:
    def cacheable(self, opening: float) -> tuple[SCCacheable, ...]:
        """Return the vise as models that can be cached.

        What moves when the vise opens is one model, built closed, and
        everything else is another, so an opening needs no new files.

        Arguments:
        * `opening` (`float`): The gap between the jaw plates (mm).

        Returns:
        * (`tuple[SCCacheable, ...]`): The vise, then what moves.
        """
        origin: Point = (0.0, 0.0, 0.0)
        return (
            SCCacheable(
                self.name,
                tooling_shape(self, "fixed"),
                lambda solidcraft: [
                    *self._model_stationary(solidcraft, origin),
                    self._model_fixed_jaw(solidcraft, origin, 0.0),
                    self._model_fixed_jaw_plate(solidcraft, origin, 0.0),
                ],
                color_of=lambda body: (
                    DRILL_COLOR if " screw" in body else VISE_COLOR
                ),
            ),
            SCCacheable(
                f"{self.name} movable",
                tooling_shape(self, "movable"),
                lambda solidcraft: [
                    self._model_movable_jaw(solidcraft, origin, 0.0, 0.0),
                    self._model_slider(
                        solidcraft, origin, self.movable_face(0.0), 0.0
                    ),
                    self._model_movable_jaw_plate(
                        solidcraft, origin, 0.0, 0.0
                    ),
                ],
                (
                    self.movable_face(opening) - self.movable_face(0.0),
                    0.0,
                    0.0,
                ),
                lambda _body: VISE_COLOR,
            ),
        )

    # Method `SCMachineVise._end_plane()`:
    def _end_plane(self, center: Point, end_x: float) -> dict[str, JSON]:
        """Return a plane across the vise that faces +X.

        Sketch X runs along Y and sketch Y runs up, from the middle of
        the base's bottom.

        Arguments:
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `end_x` (`float`): How far along X it is from `center` (mm).

        Returns:
        * (`dict[str, JSON]`): The plane, for `sketch.create`.
        """
        x, y, z = center
        return {
            "origin": [x + end_x, y, z],
            "x_dir": [0.0, 1.0, 0.0],
            "y_dir": [0.0, 0.0, 1.0],
        }

    # Method `SCMachineVise._cut_pocket()`:
    def _cut_pocket(
        self, solidcraft: SCPyBind, body: str, center: Point
    ) -> None:
        """Cut the pocket in the body, under the bed's opening.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `body` (`str`): The body's SolidCraft body.
        * `center` (`Point`): The center of the base's bottom face (mm).
        """
        x, y, z = center
        name: str = f"{self.name} pocket"
        solidcraft.sketch.create(
            plane="XY", offset=z + self.base.height, name=name
        )
        pocket: SCViseBlock = SCViseBlock(
            self.opening_length(), self.rail_gap, self.body.height
        )
        pocket.outline(name, (x, y)).sketch(solidcraft)
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.body.height, operation="cut", targets=[body]
        )

    # Method `SCMachineVise._cut_lead_screw_hole()`:
    def _cut_lead_screw_hole(
        self, solidcraft: SCPyBind, body: str, center: Point
    ) -> None:
        """Cut the hole for the lead screw, through the body's +X end.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `body` (`str`): The body's SolidCraft body.
        * `center` (`Point`): The center of the base's bottom face (mm).
        """
        solidcraft.sketch.create(
            plane=self._end_plane(center, self.body.length / 2.0),
            name=f"{self.name} lead screw hole",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.lead_screw_height),
            diameter=self.lead_screw_hole_diameter,
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.end_block_length,
            direction="negative",
            operation="cut",
            targets=[body],
        )

    # Method `SCMachineVise._model_bed()`:
    def _model_bed(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the bed: two rails, and two end blocks between them.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).

        Returns:
        * (`list[str]`): The names of the rails, then the end blocks.
        """
        x, y, z = center
        top: float = z + self.base.height + self.body.height
        rail: SCViseBlock = SCViseBlock(
            self.body.length, self.rail_width, self.rail_height
        )
        block: SCViseBlock = SCViseBlock(
            self.end_block_length, self.rail_gap, self.rail_height
        )
        rail_y: float = (self.rail_gap + self.rail_width) / 2.0
        block_x: float = (self.body.length - self.end_block_length) / 2.0
        return [
            rail.model(
                solidcraft, f"{self.name} front rail", (x, y - rail_y, top)
            ),
            rail.model(
                solidcraft, f"{self.name} back rail", (x, y + rail_y, top)
            ),
            block.model(
                solidcraft, f"{self.name} fixed end", (x - block_x, y, top)
            ),
            block.model(
                solidcraft,
                f"{self.name} lead screw end",
                (x + block_x, y, top),
            ),
        ]

    # Method `SCMachineVise._model_jaws()`:
    def _model_jaws(
        self,
        solidcraft: SCPyBind,
        center: Point,
        opening: float,
        lift: float,
    ) -> list[str]:
        """Model the jaws, the slider under one, and their plates.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the jaw plates (mm).
        * `lift` (`float`): How far to raise them all (mm).

        Returns:
        * (`list[str]`):
          The names of the jaws, then of the slider, then of the plates.
        """
        return [
            self._model_fixed_jaw(solidcraft, center, lift),
            self._model_movable_jaw(solidcraft, center, opening, lift),
            self._model_slider(
                solidcraft, center, self.movable_face(opening), lift
            ),
            self._model_fixed_jaw_plate(solidcraft, center, lift),
            self._model_movable_jaw_plate(solidcraft, center, opening, lift),
        ]

    # Method `SCMachineVise._model_fixed_jaw()`:
    def _model_fixed_jaw(
        self, solidcraft: SCPyBind, center: Point, lift: float
    ) -> str:
        """Model the fixed jaw.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name.
        """
        x, y, z = center
        fixed_x: float = -(self.body.length - self.fixed_jaw.length) / 2.0
        return self.fixed_jaw.model(
            solidcraft,
            f"{self.name} fixed jaw",
            (x + fixed_x, y, z + self.bed_top() + lift),
        )

    # Method `SCMachineVise._model_fixed_jaw_plate()`:
    def _model_fixed_jaw_plate(
        self, solidcraft: SCPyBind, center: Point, lift: float
    ) -> str:
        """Model the jaw plate on the fixed jaw.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name.
        """
        x, y, z = center
        fixed_face: float = -self.body.length / 2.0 + self.fixed_jaw.length
        return self.jaw_plate.model(
            solidcraft,
            f"{self.name} fixed jaw plate",
            (
                x + fixed_face + self.jaw_plate.length / 2.0,
                y,
                z + self.bed_top() + lift,
            ),
        )

    # Method `SCMachineVise._model_movable_jaw()`:
    def _model_movable_jaw(
        self,
        solidcraft: SCPyBind,
        center: Point,
        opening: float,
        lift: float,
    ) -> str:
        """Model the movable jaw.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the jaw plates (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name.
        """
        x, y, z = center
        face: float = self.movable_face(opening)
        return self.movable_jaw.model(
            solidcraft,
            f"{self.name} movable jaw",
            (
                x + face + self.movable_jaw.length / 2.0,
                y,
                z + self.bed_top() + lift,
            ),
        )

    # Method `SCMachineVise._model_movable_jaw_plate()`:
    def _model_movable_jaw_plate(
        self,
        solidcraft: SCPyBind,
        center: Point,
        opening: float,
        lift: float,
    ) -> str:
        """Model the jaw plate on the movable jaw.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the jaw plates (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name.
        """
        x, y, z = center
        face: float = self.movable_face(opening)
        return self.jaw_plate.model(
            solidcraft,
            f"{self.name} movable jaw plate",
            (
                x + face - self.jaw_plate.length / 2.0,
                y,
                z + self.bed_top() + lift,
            ),
            facing=-1.0,
        )

    # Method `SCMachineVise._model_slider()`:
    def _model_slider(
        self,
        solidcraft: SCPyBind,
        center: Point,
        face: float,
        lift: float,
    ) -> str:
        """Model the slider, with the hole that the lead screw goes through.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `face` (`float`): The X of the movable jaw's clamping face (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The block, with its bottom on the pocket's floor.
        x, y, z = center
        slider: SCViseBlock = self.slider()
        body: str = slider.model(
            solidcraft,
            f"{self.name} slider",
            (
                x + face + slider.length / 2.0,
                y,
                z + self.base.height + lift,
            ),
        )

        # The hole, cut back from the slider's +X end.
        solidcraft.sketch.create(
            plane=self._end_plane(center, face + slider.length),
            name=f"{self.name} slider hole",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.lead_screw_height + lift),
            diameter=self.lead_screw_diameter,
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=slider.length,
            direction="negative",
            operation="cut",
            targets=[body],
        )
        return body

    # Method `SCMachineVise._model_lead_screw()`:
    def _model_lead_screw(self, solidcraft: SCPyBind, center: Point) -> str:
        """Model the lead screw: a cylinder, with a hexagon on its end.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The cylinder, from the pocket's -X end out past the +X end.
        solidcraft.sketch.create(
            plane=self._end_plane(center, -self.opening_length() / 2.0),
            name=f"{self.name} lead screw",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.lead_screw_height),
            diameter=self.lead_screw_diameter,
        )
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=(
                self.opening_length()
                + self.end_block_length
                + self.lead_screw_stick_out
            ),
            body_name=f"{self.name} lead screw",
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        body: str = bodies[0]

        # Join the hexagon onto its end.
        solidcraft.sketch.create(
            plane=self._end_plane(
                center, self.body.length / 2.0 + self.lead_screw_stick_out
            ),
            name=f"{self.name} hex",
        )
        solidcraft.sketch.line(
            points=[
                [across, self.lead_screw_height + up]
                for across, up in self.hexagon()
            ],
            closed=True,
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.hex_length, operation="join", targets=[body]
        )
        solidcraft.appearance.assign(bodies=[body], color=DRILL_COLOR)
        return body


# Kurt's D688: its jaw plate's height, opening, and overall length and
# height come from used machinery listings (1.735 in, 8.8 in, and 16.75 x
# 4.375 in).  All of its layers are 6 in wide but the body, at the
# user's word; the listings' 8.25 in overall width is not used.  The usual
# 6 in plate's thickness and holes come from the user's notes: about
# 0.725 in, on 3-7/8 in centers, for 1/2-13 screws, with centers 0.940 in
# or more above the bottom (17/32 in is a clearance hole).  Its 20 mm
# counterbores are the usual size for those screws; 17/32 in deep, to
# sink a 1/2 in tall head, is an estimate.  Its 3/4 in hex
# comes from the Shars 2026 catalog, page 317, which sells handles for it
# (7/8 in for Kurt's 8 in vises).  Everything else is an estimate, good
# enough to know what it is.
KURT_JAW_PLATE: SCJawPlate = SCJawPlate(
    screw="1/2-13 SHCS",
    length=_mm("0.725 in"),
    width=_mm("6 in"),
    height=_mm("1.735 in"),
    hole_spacing=_mm("3-7/8 in"),
    hole_diameter=_mm("17/32 in"),
    hole_height=_mm("0.94 in"),
    counterbore_diameter=_mm("20 mm"),
    counterbore_depth=_mm("17/32 in"),
)
KURT_D688: SCMachineVise = SCMachineVise(
    name="Kurt D688",
    base=SCViseBlock(
        _mm("15.75 in"), _mm("6 in"), _mm("0.5 in"), _mm("1/2 in")
    ),
    body=SCViseBlock(
        _mm("15.75 in"), _mm("5-1/4 in"), _mm("1.39 in"), _mm("1/2 in")
    ),
    base_notches=SCViseNotches(
        centers=(_mm("-4 in"), _mm("4 in")),
        width=_mm("7/8 in"),
        depth=_mm("7/8 in"),
        inner_radius=_mm("1/4 in"),
        outer_radius=_mm("1/8 in"),
    ),
    body_notches=SCViseNotches(
        centers=(_mm("-4 in"), _mm("4 in")),
        width=_mm("1-3/4 in"),
        depth=_mm("1 in"),
        inner_radius=_mm("3/8 in"),
        outer_radius=_mm("1/8 in"),
    ),
    rail_width=_mm("1-3/4 in"),
    rail_height=_mm("0.75 in"),
    rail_gap=_mm("2-1/2 in"),
    end_block_length=_mm("1-1/2 in"),
    fixed_jaw=SCViseBlock(_mm("1 in"), _mm("6 in"), _mm("1.735 in")),
    movable_jaw=SCViseBlock(_mm("3-3/4 in"), _mm("6 in"), _mm("1.735 in")),
    jaw_plate=KURT_JAW_PLATE,
    max_opening=_mm("8.8 in"),
    lead_screw_diameter=_mm("1 in"),
    lead_screw_stick_out=_mm("1/4 in"),
    lead_screw_height=_mm("1.195 in"),
    lead_screw_hole_diameter=_mm("1-1/8 in"),
    hex_size=_mm("3/4 in"),
    hex_length=_mm("3/4 in"),
)


# Class `SCParallel`:
@dataclass(frozen=True, slots=True)
class SCParallel:
    """A parallel: a thin steel bar that work sits on in a vise.

    Parallels come in matched pairs, one under each side of the work.
    Most have two round holes through them, which make them lighter and
    easier to pick up; the holes are optional.

    It stands on edge, with its length along Y, the way it lies along
    the jaws of a vise whose lead screw runs along X.  Its holes go
    through it along X, halfway up, the same distance either side of its
    middle.  All lengths are in millimeters.

    Attributes:
    * `name` (`str`): What it is.
    * `height` (`float`): Its size along Z.
    * `thickness` (`float`): Its size along X.
    * `length` (`float`): Its size along Y.
    * `hole_spacing` (`float`):
      Optional.  The distance between its two holes' centers; 0 for no
      holes.
    * `hole_diameter` (`float`):
      Optional.  The diameter of its holes; 0 for no holes.

    Constructor:
    * `SCParallel(name, height, thickness, length, hole_spacing,
      hole_diameter)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    height: float = field(init=True)
    thickness: float = field(init=True)
    length: float = field(init=True)
    hole_spacing: float = field(init=True, default=0.0)
    hole_diameter: float = field(init=True, default=0.0)

    # Method `SCParallel.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the parallel has a size, and its holes fit.

        Raises:
        * `ValueError`: If it has no size, it has only one of the hole
          sizes, or its holes do not fit.
        """
        if min(self.height, self.thickness, self.length) <= 0.0:
            raise ValueError(
                f"{self.height=}, {self.thickness=}, {self.length=}"
            )
        radius: float = self.hole_diameter / 2.0
        if (self.hole_spacing == 0.0) != (self.hole_diameter == 0.0):
            raise ValueError(
                f"{self.hole_spacing=} and {self.hole_diameter=} must both "
                "be 0, for no holes, or both be given"
            )
        if self.has_holes() and (
            radius < 0.0
            or self.hole_diameter >= self.height
            or self.hole_spacing <= self.hole_diameter
            or self.hole_spacing / 2.0 + radius >= self.length / 2.0
        ):
            raise ValueError(
                f"{self.hole_diameter=} at {self.hole_spacing=} does not "
                f"fit {self.height=} and {self.length=}"
            )

    # Method `SCParallel.has_holes()`:
    def has_holes(self) -> bool:
        """Return True if the parallel has holes.

        Returns:
        * (`bool`): True if it has holes.
        """
        return self.hole_diameter != 0.0

    # Method `SCParallel.volume()`:
    def volume(self) -> float:
        """Return the volume its model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        hole: float = math.pi * (self.hole_diameter / 2.0) ** 2
        holes: float = 2.0 * hole * self.thickness if self.has_holes() else 0.0
        return self.height * self.thickness * self.length - holes

    # Method `SCParallel.block()`:
    def block(self) -> SCViseBlock:
        """Return the parallel's shape.

        Returns:
        * (`SCViseBlock`): A block with square corners.

        Raises:
        * `ValueError`: If it has no size.
        """
        return SCViseBlock(self.thickness, self.length, self.height)

    # Method `SCParallel.prism()`:
    def prism(self, center: Point) -> SCPrism:
        """Return the rectangular prism that just encloses the parallel.

        Arguments:
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`SCPrism`): The prism, named for the parallel.
        """
        x, y, z = center
        half_x: float = self.thickness / 2.0
        half_y: float = self.length / 2.0
        return SCPrism(
            self.name,
            (x - half_x, y - half_y, z),
            (x + half_x, y + half_y, z + self.height),
        )

    # Method `SCParallel.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> str:
        """Model the parallel, up from the center of its bottom edge.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        body: str = self.block().model(solidcraft, self.name, center)
        solidcraft.appearance.assign(bodies=[body], color=DRILL_COLOR)
        if not self.has_holes():
            return body

        # Cut both holes through it, from its +X face.
        x, y, z = center
        solidcraft.sketch.create(
            plane={
                "origin": [x + self.thickness / 2.0, y, z],
                "x_dir": [0.0, 1.0, 0.0],
                "y_dir": [0.0, 0.0, 1.0],
            },
            name=f"{self.name} holes",
        )
        half: float = self.hole_spacing / 2.0
        for across in (-half, half):
            solidcraft.sketch.circle_center(
                center=(across, self.height / 2.0),
                diameter=self.hole_diameter,
            )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.thickness,
            direction="negative",
            operation="cut",
            targets=[body],
        )
        return body


# The heights of a set of parallels: the standard imperial heights, 1/2
# in up to 1-5/8 in, by 1/8 in (the user).
PARALLEL_HEIGHTS: tuple[str, ...] = (
    "1/2 in",
    "5/8 in",
    "3/4 in",
    "7/8 in",
    "1 in",
    "1-1/8 in",
    "1-1/4 in",
    "1-3/8 in",
    "1-1/2 in",
    "1-5/8 in",
)

# A whole set: two parallels of each height, since work sits on a pair.
# Each has two holes 3 in apart, half as wide as it is tall; the holes
# are Claude's estimate of a typical set.
PARALLELS: tuple[SCParallel, ...] = tuple(
    SCParallel(
        f"Parallel {height} {side}",
        _mm(height),
        _mm("1/8 in"),
        _mm("6 in"),
        hole_spacing=_mm("3 in"),
        hole_diameter=_mm(height) / 2.0,
    )
    for height in PARALLEL_HEIGHTS
    for side in "AB"
)


# Function `parallel_centers()`:
def parallel_centers() -> list[float]:
    """Return the X of each parallel when the set is laid out in a row.

    Returns:
    * (`list[float]`):
      Each parallel's center (millimeters), in `PARALLELS` order, with
      the row centered on `X = 0`.
    """
    centers: list[float] = []
    edge: float = 0.0
    for index, parallel in enumerate(PARALLELS):
        centers.append(edge + parallel.thickness / 2.0)
        gap: float = PARALLEL_SET_GAP if index % 2 else PARALLEL_PAIR_GAP
        edge += parallel.thickness + gap
    middle: float = (centers[0] + centers[-1]) / 2.0
    return [center - middle for center in centers]


# Function `parallel_set()`:
def parallel_set(
    solidcraft: SCPyBind,
) -> tuple[list[str], SCKeepOut]:
    """Model `PARALLELS` in a row, each with a keep-out prism.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Returns:
    * (`tuple[list[str], SCKeepOut]`):
      The names of the parallels' bodies, and their keep-out regions.
    """
    bodies: list[str] = []
    keep_out: SCKeepOut = SCKeepOut()
    for parallel, x in zip(PARALLELS, parallel_centers()):
        center: Point = (x, PARALLEL_ROW_Y, 0.0)
        bodies.append(parallel.model(solidcraft, center))
        keep_out.add_prism(parallel.prism(center), PARALLEL_MARGIN)
    return bodies, keep_out


# Class `SCScrewFit`:
@dataclass(frozen=True, slots=True)
class SCScrewFit:
    """The holes that a screw passes through.  Lengths are millimeters.

    Attributes:
    * `screw` (`str`): The screw's size (such as `"#6"`).
    * `nominal` (`float`): The screw's nominal diameter.
    * `close_drill` (`str`): The drill for a close fit.
    * `close` (`float`): The diameter of a close fit hole.
    * `loose_drill` (`str`): The drill for a loose (free) fit.
    * `loose` (`float`): The diameter of a loose fit hole.

    Constructor:
    * `SCScrewFit(screw, nominal, close_drill, close, loose_drill,
      loose)`
    """

    # Constructor arguments:
    screw: str = field(init=True)
    nominal: float = field(init=True)
    close_drill: str = field(init=True)
    close: float = field(init=True)
    loose_drill: str = field(init=True)
    loose: float = field(init=True)


# The user's chart of close and loose holes for imperial screws.
SCREW_FITS: dict[str, SCScrewFit] = {
    fit.screw: fit
    for fit in (
        SCScrewFit(
            "#2",
            _mm("0.0860 in"),
            "#43",
            _mm("0.0890 in"),
            "#41",
            _mm("0.0960 in"),
        ),
        SCScrewFit(
            "#4",
            _mm("0.1120 in"),
            "#32",
            _mm("0.1160 in"),
            "#30",
            _mm("0.1285 in"),
        ),
        SCScrewFit(
            "#6",
            _mm("0.1380 in"),
            "#27",
            _mm("0.1440 in"),
            "#25",
            _mm("0.1495 in"),
        ),
        SCScrewFit(
            "#8",
            _mm("0.1640 in"),
            "#18",
            _mm("0.1695 in"),
            "#16",
            _mm("0.1770 in"),
        ),
        SCScrewFit(
            "#10",
            _mm("0.1900 in"),
            "#9",
            _mm("0.1960 in"),
            "#7",
            _mm("0.2010 in"),
        ),
        SCScrewFit(
            "#12",
            _mm("0.2160 in"),
            "#2",
            _mm("0.2210 in"),
            "#1",
            _mm("0.2280 in"),
        ),
    )
}


# Class `SCGridPlate`:
@dataclass(frozen=True, slots=True)
class SCGridPlate:
    """A grid plate: a plate with a grid of holes, for holding work down.

    The grid has the same pitch along X and Y, and fills the plate, with
    its outer holes `edge` in from all four sides.  Each hole's top edge
    may be chamfered at 45 degrees.

    It may also have tooling holes, in an even number of rows and
    columns, centered on the plate, each one dead center between four of
    the grid's holes.  They come in two sizes, a tap drill for a thread
    and a close fit for the same screw, in a checkerboard: a tooling
    hole's neighbors along X and Y are the other size.  With them, grid
    plates are easy to make in pairs in a home shop, and pairs of them
    hold many parts made at the same time.

    Its outline is an `SCRoundedPolygon` with its four corners rounded
    and all of the holes inside, so that one extrude makes the plate;
    one chamfer command then does every chamfer.  All lengths are in
    millimeters.

    Chamfers take a lot of computing, once.  `GRID_PLATE`'s 200 took
    SolidCraft about 4-1/2 minutes, keeping four processors busy,
    against 2 seconds without them.  The model cache (`model_cache.py`,
    which `setups.py` and `show_demo.py` use) keeps the plate as a STEP
    file in `~/.scraftcnc/tool_cache/`, which loads in about a second,
    so the cost comes again only when the plate's numbers change, or
    `tools.py`, `mount.py` or `geometry.py` does.  `model()` called
    directly does not use the cache.

    Attributes:
    * `name` (`str`): What it is.
    * `length` (`float`): Its size along X.
    * `width` (`float`): Its size along Y.
    * `height` (`float`): Its size along Z, its thickness.
    * `pitch` (`float`): The distance between grid holes, along X and Y.
    * `edge` (`float`): The distance from a side to the nearest holes.
    * `hole_diameter` (`float`): The diameter of the grid's holes.
    * `corner_radius` (`float`): Optional.  The radius of its corners.
    * `chamfer_depth` (`float`):
      Optional.  How deep the 45 degree chamfer on each grid hole's top
      edge is; 0 for none.  Slow to model the first time (above).
    * `tooling_columns` (`int`):
      Optional.  The number of columns of tooling holes, an even number;
      0 for none.
    * `tooling_rows` (`int`):
      Optional.  The number of rows of tooling holes, an even number; 0
      for none.
    * `tooling_pitch` (`float`):
      Optional.  The distance between tooling holes, along X and Y.
    * `tap_diameter` (`float`):
      Optional.  The diameter of the tooling holes to be threaded (the
      tap drill).
    * `close_diameter` (`float`):
      Optional.  The diameter of the close fit tooling holes.

    Constructor:
    * `SCGridPlate(name, length, width, height, pitch, edge,
      hole_diameter, corner_radius, chamfer_depth, tooling_columns,
      tooling_rows, tooling_pitch, tap_diameter, close_diameter)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    length: float = field(init=True)
    width: float = field(init=True)
    height: float = field(init=True)
    pitch: float = field(init=True)
    edge: float = field(init=True)
    hole_diameter: float = field(init=True)
    corner_radius: float = field(init=True, default=0.0)
    chamfer_depth: float = field(init=True, default=0.0)
    tooling_columns: int = field(init=True, default=0)
    tooling_rows: int = field(init=True, default=0)
    tooling_pitch: float = field(init=True, default=0.0)
    tap_diameter: float = field(init=True, default=0.0)
    close_diameter: float = field(init=True, default=0.0)

    # Method `SCGridPlate.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the grid and the tooling holes fit the plate.

        Raises:
        * `ValueError`: If the grid does not reach `edge` from every
          side, the holes run into one another or a side, the chamfers
          do not fit, or the tooling holes are not as described.
        """
        if self.height <= 0.0 or self.pitch <= 0.0:
            raise ValueError(f"{self.height=} and {self.pitch=}")
        for size in (self.length, self.width):
            steps: float = (size - 2.0 * self.edge) / self.pitch
            if steps < 0.0 or abs(steps - round(steps)) > 1.0e-9:
                raise ValueError(
                    f"{self.pitch=} does not divide {size=} less "
                    f"{self.edge=} on both sides"
                )
        top: float = self.chamfered_diameter()
        if not (
            0.0 < self.hole_diameter
            and top < min(self.pitch, 2.0 * self.edge)
            and 0.0 <= self.chamfer_depth < self.height
        ):
            raise ValueError(
                f"{self.hole_diameter=} with {self.chamfer_depth=} does "
                f"not fit {self.pitch=} and {self.edge=}"
            )
        self._check_tooling()

    # Method `SCGridPlate.from_shop()`:
    @staticmethod
    def from_shop(plate: dict[str, object]) -> "SCGridPlate":
        """Return a grid plate described in a shop's tooling file.

        Arguments:
        * `plate` (`dict[str, object]`):
          Its `[[grid_plates]]` entry, from `shops.read()`, which has
          checked its keys and units.

        Returns:
        * (`SCGridPlate`): The plate, in millimeters.

        Raises:
        * `ValueError`: If its numbers do not make a grid plate.
        """

        # A length in millimeters, or 0 if it is not given.
        def size(key: str) -> float:
            return _mm(str(plate[key])) if key in plate else 0.0

        # A count, or 0 if it is not given.
        def count(key: str) -> int:
            value: object = plate.get(key, 0)
            assert isinstance(value, int)
            return value

        return SCGridPlate(
            name=str(plate["name"]),
            length=size("length"),
            width=size("width"),
            height=size("height"),
            pitch=size("pitch"),
            edge=size("edge"),
            hole_diameter=size("hole_diameter"),
            corner_radius=size("corner_radius"),
            chamfer_depth=size("chamfer_depth"),
            tooling_columns=count("tooling_columns"),
            tooling_rows=count("tooling_rows"),
            tooling_pitch=size("tooling_pitch"),
            tap_diameter=size("tap_diameter"),
            close_diameter=size("close_diameter"),
        )

    # Method `SCGridPlate._check_tooling()`:
    def _check_tooling(self) -> None:
        """Check that the tooling holes are as described.

        Raises:
        * `ValueError`: If the counts are odd or only one is given, the
          holes are not between grid holes, or they run into one another
          or the grid's holes.
        """
        counts: tuple[int, int] = (self.tooling_columns, self.tooling_rows)
        if counts == (0, 0):
            return
        if min(counts) <= 0 or any(count % 2 for count in counts):
            raise ValueError(
                f"{self.tooling_columns=} and {self.tooling_rows=} must be "
                "both 0, or both even"
            )

        # Each tooling hole is at the middle of four grid holes.
        for places, size in (
            (self._tooling_places(self.tooling_columns), self.length),
            (self._tooling_places(self.tooling_rows), self.width),
        ):
            grid: list[float] = _grid(size, self.edge, self.pitch)
            for place in places:
                cells: float = (place - grid[0]) / self.pitch - 0.5
                if (
                    abs(cells - round(cells)) > 1.0e-6
                    or not grid[0] < place < grid[-1]
                ):
                    raise ValueError(
                        f"{place=} is not between the grid's holes "
                        f"along {size=}"
                    )

        # Clear of each other, and of the grid's holes, a half diagonal
        # away.
        largest: float = max(self.tap_diameter, self.close_diameter)
        clear: float = (
            largest + self.chamfered_diameter()
        ) / 2.0 < self.pitch / math.sqrt(2.0)
        if (
            min(self.tap_diameter, self.close_diameter) <= 0.0
            or largest >= self.tooling_pitch
            or not clear
        ):
            raise ValueError(
                f"{self.tap_diameter=} and {self.close_diameter=} at "
                f"{self.tooling_pitch=} do not fit the grid"
            )

    # Method `SCGridPlate._tooling_places()`:
    def _tooling_places(self, count: int) -> list[float]:
        """Return the places of tooling holes along one side.

        Arguments:
        * `count` (`int`): How many there are along it.

        Returns:
        * (`list[float]`): The places, from the plate's middle, lowest
          first (millimeters).
        """
        first: float = -self.tooling_pitch * (count - 1) / 2.0
        return [first + index * self.tooling_pitch for index in range(count)]

    # Method `SCGridPlate.chamfered_diameter()`:
    def chamfered_diameter(self) -> float:
        """Return the diameter of a grid hole at the plate's top.

        Returns:
        * (`float`): The diameter, with its chamfer (millimeters).
        """
        return self.hole_diameter + 2.0 * self.chamfer_depth

    # Method `SCGridPlate.hole_centers()`:
    def hole_centers(self) -> list[tuple[float, float]]:
        """Return where the grid's holes are, from the plate's center.

        Returns:
        * (`list[tuple[float, float]]`):
          Each hole's `(x, y)`, by rows from the most negative up.
        """
        columns: list[float] = _grid(self.length, self.edge, self.pitch)
        rows: list[float] = _grid(self.width, self.edge, self.pitch)
        return [(x, y) for y in rows for x in columns]

    # Method `SCGridPlate.tooling_holes()`:
    def tooling_holes(self) -> list[tuple[float, float, float]]:
        """Return where the tooling holes are, and their sizes.

        The one at the lowest X and Y is a tap drill hole; the rest
        make a checkerboard from it.

        Returns:
        * (`list[tuple[float, float, float]]`):
          Each hole's `(x, y, diameter)`, from the plate's center, by
          rows from the most negative up; none if it has none.
        """
        if not self.tooling_columns:
            return []
        columns: list[float] = self._tooling_places(self.tooling_columns)
        rows: list[float] = self._tooling_places(self.tooling_rows)
        return [
            (
                x,
                y,
                self.close_diameter if (i + j) % 2 else self.tap_diameter,
            )
            for j, y in enumerate(rows)
            for i, x in enumerate(columns)
        ]

    # Method `SCGridPlate.volume()`:
    def volume(self) -> float:
        """Return the volume the model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        # Each chamfer is a cone's frustum less the hole it surrounds.
        hole: float = self.hole_diameter / 2.0
        top: float = self.chamfered_diameter() / 2.0
        deep: float = self.chamfer_depth
        chamfer: float = (
            math.pi * deep * ((top**2 + top * hole + hole**2) / 3.0 - hole**2)
        )
        grid: float = len(self.hole_centers()) * (
            math.pi * hole**2 * self.height + chamfer
        )
        tooling: float = sum(
            math.pi * (diameter / 2.0) ** 2 * self.height
            for _, _, diameter in self.tooling_holes()
        )
        corners: float = (4.0 - math.pi) * self.corner_radius**2
        whole: float = (self.length * self.width - corners) * self.height
        return whole - grid - tooling

    # Method `SCGridPlate.seat()`:
    def seat(self) -> Point:
        """Return the middle of the plate's top.

        Returns:
        * (`Point`): It, from the center of the plate's bottom (mm).
        """
        return (0.0, 0.0, self.height)

    # Method `SCGridPlate.outline()`:
    def outline(self, center: tuple[float, float]) -> SCRoundedPolygon:
        """Return the plate's outline and holes, as seen from above.

        Arguments:
        * `center` (`tuple[float, float]`): Its center's X and Y (mm).

        Returns:
        * (`SCRoundedPolygon`): The outline, counter-clockwise, with the
          grid's holes and then the tooling holes as its children.
        """
        x, y = center
        half_x: float = self.length / 2.0
        half_y: float = self.width / 2.0
        radius: float = self.corner_radius
        holes: list[tuple[float, float, float]] = [
            (hole_x, hole_y, self.hole_diameter)
            for hole_x, hole_y in self.hole_centers()
        ] + self.tooling_holes()
        return SCRoundedPolygon(
            self.name,
            [
                SCCorner(x - half_x, y - half_y, radius),
                SCCorner(x + half_x, y - half_y, radius),
                SCCorner(x + half_x, y + half_y, radius),
                SCCorner(x - half_x, y + half_y, radius),
            ],
            0.0,
            self.height,
            [
                SCHole(x + hole_x, y + hole_y, diameter, self.height, 0.0)
                for hole_x, hole_y, diameter in holes
            ],
        )

    # Method `SCGridPlate.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the plate, up from the center of its bottom face.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom face (mm).

        Returns:
        * (`list[str]`): The name of the plate's body.
        """
        x, y, z = center

        # Sketch it all at the bottom face, and make it with one extrude.
        solidcraft.sketch.create(plane="XY", offset=z, name=self.name)
        self.outline((x, y)).sketch(solidcraft)
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=self.height, body_name=self.name
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        body: str = bodies[0]

        # Chamfer every grid hole's top edge at once, naming each edge by
        # a point on it.  A hole's circle is two half circles that meet
        # along X, so the point is the middle of the +Y one.
        if self.chamfer_depth > 0.0:
            radius: float = self.hole_diameter / 2.0
            solidcraft.solid.chamfer(
                edges=[
                    [x + hole_x, y + hole_y + radius, z + self.height]
                    for hole_x, hole_y in self.hole_centers()
                ],
                distance=self.chamfer_depth,
                body=body,
            )
        solidcraft.appearance.assign(bodies=[body], color=ALUMINUM_COLOR)
        return [body]

    # Method `SCGridPlate.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return the plate as a model that can be cached.

        Returns:
        * (`tuple[SCCacheable, ...]`): The plate.
        """
        return (
            SCCacheable(
                self.name,
                tooling_shape(self),
                lambda solidcraft: self.model(solidcraft, (0.0, 0.0, 0.0)),
                color_of=lambda _body: ALUMINUM_COLOR,
            ),
        )

    # Method `SCGridPlate.prism()`:
    def prism(self, center: Point) -> SCPrism:
        """Return the rectangular prism that just encloses the plate.

        Arguments:
        * `center` (`Point`): The center of its bottom face (mm).

        Returns:
        * (`SCPrism`): The prism, named for the plate.
        """
        return box_prism(
            self.name, (self.length, self.width, self.height), center
        )

    # Method `SCGridPlate.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the prism around the plate.

        Arguments:
        * `center` (`Point`): The center of its bottom face (mm).

        Returns:
        * (`SCKeepOut`): One grown prism.
        """
        keep_out: SCKeepOut = SCKeepOut()
        keep_out.add_prism(self.prism(center), GRID_PLATE_MARGIN)
        return keep_out


# Function `_grid()`:
def _grid(size: float, edge: float, spacing: float) -> list[float]:
    """Return the places along a side for a grid of holes.

    Arguments:
    * `size` (`float`): The side's length (millimeters).
    * `edge` (`float`): How far the outer holes are from its ends (mm).
    * `spacing` (`float`): The distance between holes (millimeters).

    Returns:
    * (`list[float]`): The places, from the side's middle, lowest first.
    """
    count: int = round((size - 2.0 * edge) / spacing) + 1
    first: float = -spacing * (count - 1) / 2.0
    return [first + index * spacing for index in range(count)]


# A grid plate as the user described it, whose holes fill it at 1/2 in,
# reaching 1/2 in from all four sides.  The user gave no thickness; 1/2 in
# is an estimate.  Its corners are 1/4 in rounds.  Each grid hole is a
# close fit for a #6 screw, with a 1/32 in chamfer.  Its tooling holes,
# 2 by 4 on 3 in centers, are for #10-32 screws: #21 (0.159 in), the tap
# drill, and a close fit; Claude's choice.
GRID_PLATE: SCGridPlate = SCGridPlate(
    name="Grid plate",
    length=_mm("5-1/2 in"),
    width=_mm("10-1/2 in"),
    height=_mm("1/2 in"),
    pitch=_mm("1/2 in"),
    edge=_mm("1/2 in"),
    hole_diameter=SCREW_FITS["#6"].close,
    corner_radius=_mm("1/4 in"),
    chamfer_depth=_mm("1/32 in"),
    tooling_columns=2,
    tooling_rows=4,
    tooling_pitch=_mm("3 in"),
    tap_diameter=_mm("0.159 in"),
    close_diameter=SCREW_FITS["#10"].close,
)


# Function `table_centers()`:
def table_centers() -> list[float]:
    """Return where the tables go when they are shown side by side.

    Returns:
    * (`list[float]`):
      The Y of each table's center (millimeters), in `MILL_TABLES`
      order, smallest table first with a gap between them.
    """
    centers: list[float] = []
    edge: float = 0.0
    for table in MILL_TABLES:
        centers.append(edge + table.width / 2.0)
        edge += table.width + TABLE_GAP
    return centers


# Class `SCTormach`:
@dataclass(slots=True)
class SCTormach:
    """Models of Tormach's equipment.

    Attributes:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Constructor:
    * `SCTormach(solidcraft)`
    """

    # Constructor arguments:
    solidcraft: SCPyBind = field(init=True)

    # Method `SCTormach.mill_tables()`:
    def mill_tables(self) -> list[str]:
        """Model the tables of the 440, 770 and 1100, side by side.

        Returns:
        * (`list[str]`): The names of the bodies, in `MILL_TABLES` order.
        """
        return [
            self.mill_table(table, center_y)
            for table, center_y in zip(MILL_TABLES, table_centers())
        ]

    # Method `SCTormach.mill_table_keep_out()`:
    def mill_table_keep_out(self, margin: str = TABLE_MARGIN) -> SCKeepOut:
        """Return the tables' keep-out regions, laid out as `mill_tables()`.

        Arguments:
        * `margin` (`str`):
          How far to grow each table's prism, with its unit.

        Returns:
        * (`SCKeepOut`): One grown prism per table.
        """
        keep_out: SCKeepOut = SCKeepOut()
        for table, center_y in zip(MILL_TABLES, table_centers()):
            keep_out.add_prism(table.prism(center_y), margin)
        return keep_out

    # Method `SCTormach.mill_table()`:
    def mill_table(self, table: SCMillTable, center_y: float = 0.0) -> str:
        """Model one mill table.

        Arguments:
        * `table` (`SCMillTable`): The table.
        * `center_y` (`float`): The Y of its center (millimeters).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The plate, from the top down.
        solidcraft: SCPyBind = self.solidcraft
        solidcraft.sketch.create(plane="XY", name=f"{table.name} plate")
        solidcraft.sketch.rectangle_center(
            center=(0.0, center_y),
            corner=(table.length / 2.0, center_y + table.width / 2.0),
        )
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=table.thickness,
            direction="negative",
            body_name=table.name,
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        body: str = bodies[0]

        # The T-slots, each cut both ways from a sketch across its middle.
        for slot_y in table.slot_centers():
            self._cut_slot(table, body, center_y + slot_y)

        # The pockets at the ends of the slots, if it has any.
        offset: float = (table.slot_length + table.pocket_length) / 2.0
        if table.pocket_length > 0.0:
            for pocket_x in (-offset, offset):
                self._cut_pocket(table, body, pocket_x, center_y)
        solidcraft.appearance.assign(bodies=[body], color=TABLE_COLOR)
        return body

    # Method `SCTormach._cut_slot()`:
    def _cut_slot(
        self, table: SCMillTable, body: str, center_y: float
    ) -> None:
        """Cut one T-slot.

        Arguments:
        * `table` (`SCMillTable`): The table.
        * `body` (`str`): The table's body.
        * `center_y` (`float`): The Y of the slot's center (millimeters).
        """
        # The plane looks along +X, with sketch X along Y and sketch Y up.
        solidcraft: SCPyBind = self.solidcraft
        solidcraft.sketch.create(
            plane={
                "origin": [0.0, center_y, 0.0],
                "x_dir": [0.0, 1.0, 0.0],
                "y_dir": [0.0, 0.0, 1.0],
            },
            name=f"{table.name} slot",
        )
        solidcraft.sketch.line(
            points=[[y, z] for y, z in table.slot_outline()], closed=True
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=table.slot_length,
            direction="symmetric",
            operation="cut",
            targets=[body],
        )

    # Method `SCTormach._cut_pocket()`:
    def _cut_pocket(
        self, table: SCMillTable, body: str, center_x: float, center_y: float
    ) -> None:
        """Cut one of the pockets at the ends of the slots.

        Arguments:
        * `table` (`SCMillTable`): The table.
        * `body` (`str`): The table's body.
        * `center_x` (`float`): The X of the pocket's center (millimeters).
        * `center_y` (`float`): The Y of the pocket's center (millimeters).
        """
        solidcraft: SCPyBind = self.solidcraft
        solidcraft.sketch.create(plane="XY", name=f"{table.name} pocket")
        solidcraft.sketch.rectangle_center(
            center=(center_x, center_y),
            corner=(
                center_x + table.pocket_length / 2.0,
                center_y + table.pocket_width / 2.0,
            ),
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=table.slot_depth,
            direction="negative",
            operation="cut",
            targets=[body],
        )


# Function `main()`:
def main() -> None:
    """Show tables, drills, a vise and keep-outs, in a new design."""
    target: str = sys.argv[1] if len(sys.argv) > 1 else "8080"
    with connect(target) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.file.new()
        if sys.argv[2:] == ["countersinks"]:
            print(countersink_rows(solidcraft))
            solidcraft.view.apply(view="iso")
            return
        if sys.argv[2:] and sys.argv[2] in DOUBLE_END_COUNTERSINKS:
            print(
                DOUBLE_END_COUNTERSINKS[sys.argv[2]].model(
                    solidcraft, color=COUNTERSINK_COLORS["Radius"]
                )
            )
            solidcraft.view.apply(view="iso")
            return
        if sys.argv[2:] == ["largest"]:
            print(largest_countersinks(solidcraft))
            solidcraft.view.apply(view="iso")
            return
        tormach: SCTormach = SCTormach(solidcraft)
        print(tormach.mill_tables())
        print(tormach.mill_table_keep_out().model(solidcraft))
        drills, keep_out = sample_drills(solidcraft)
        print(drills)
        print(keep_out.model(solidcraft))
        print(
            KURT_D688.model(
                solidcraft,
                (0.0, VISE_ROW_Y, 0.0),
                _mm(VISE_OPENING),
                _mm(VISE_LIFT),
            )
        )
        print(
            KURT_D688.keep_out(
                (0.0, VISE_ROW_Y, 0.0), _mm(VISE_OPENING)
            ).model(solidcraft)
        )
        parallels, keep_out = parallel_set(solidcraft)
        print(parallels)
        print(keep_out.model(solidcraft))
        solidcraft.view.apply(view="iso")


if __name__ == "__main__":
    main()
