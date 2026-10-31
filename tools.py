#!/usr/bin/env python3
"""3D models of the tooling that holds work on a machine, for SolidCraft.

So far, the tables of Tormach's three entry level mills, each with its
T-slots and the pockets at their ends that T-nuts drop in through;
the keep-out regions around them that a tool must not enter; generic
drills; a vise; and a set of parallels.

Every table has its top at `Z = 0`, its length along X and its center
on `X = 0`.  Run as a program, it shows them all in SolidCraft:

```
python3 tools.py 8080       # A GUI started with `--control 8080`.
python3 tools.py headless   # No window; prints the bodies it made.
```
"""

# A `MillTable` holds one number per dimension on the drawing, which
# runs past `pylint`'s limit on attributes.
# pylint: disable=too-many-instance-attributes

# All of the tooling models live together for now, which runs past
# `pylint`'s limit on a module's size.
# pylint: disable=too-many-lines

import math
import sys
from dataclasses import dataclass, field

from scgeometry import SCCorner, SCRoundPoly
from scraftpybind import JSON, SolidCraftPyBind, connect
from sctoolmodel import MM_PER_INCH
from shops import LENGTH, measure

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


# Function `_mm()`:
def _mm(length: str) -> float:
    """Return a length with its unit in millimeters.

    Arguments:
    * `length` (`str`): The length (such as `"1/8 in"`).

    Returns:
    * (`float`): The length (millimeters).
    """
    return measure(length, LENGTH) * MM_PER_INCH


# Class `MillTable`:
@dataclass(frozen=True, slots=True)
class MillTable:
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
    * `MillTable(name, length, width, thickness, slots, slot_spacing,
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

    # Method `MillTable.slot_centers()`:
    def slot_centers(self) -> list[float]:
        """Return the Y of each slot's center, from the table's center.

        Returns:
        * (`list[float]`): The slots' centers, from most negative up.
        """
        first: float = -self.slot_spacing * (self.slots - 1) / 2.0
        return [
            first + index * self.slot_spacing for index in range(self.slots)
        ]

    # Method `MillTable.slot_outline()`:
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

    # Method `MillTable.prism()`:
    def prism(self, center_y: float = 0.0) -> "Prism":
        """Return the rectangular prism that just encloses the table.

        Arguments:
        * `center_y` (`float`): The Y of its center (millimeters).

        Returns:
        * (`Prism`): The prism, named for the table.
        """
        half_x: float = self.length / 2.0
        half_y: float = self.width / 2.0
        return Prism(
            self.name,
            (-half_x, center_y - half_y, -self.thickness),
            (half_x, center_y + half_y, 0.0),
        )

    # Method `MillTable.volume()`:
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
MILL_TABLES: tuple[MillTable, ...] = (
    MillTable(
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
    MillTable(
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
    MillTable(
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


# Class `Prism`:
@dataclass(frozen=True, slots=True)
class Prism:
    """A rectangular prism, with its sides along the axes.

    Attributes:
    * `name` (`str`): What it is.
    * `low` (`Point`): Its corner with the smallest X, Y and Z (mm).
    * `high` (`Point`): Its corner with the largest X, Y and Z (mm).

    Constructor:
    * `Prism(name, low, high)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    low: Point = field(init=True)
    high: Point = field(init=True)

    # Method `Prism.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the prism is not empty.

        Raises:
        * `ValueError`: If `low` is not below `high` on every axis.
        """
        if not all(low < high for low, high in zip(self.low, self.high)):
            raise ValueError(f"{self.low=} must be below {self.high=}")

    # Method `Prism.grown()`:
    def grown(self, margin: float) -> "Prism":
        """Return the prism grown on all six sides.

        Arguments:
        * `margin` (`float`): How far each side moves out (millimeters).

        Returns:
        * (`Prism`): The larger prism, with the same name.
        """
        x0, y0, z0 = self.low
        x1, y1, z1 = self.high
        return Prism(
            self.name,
            (x0 - margin, y0 - margin, z0 - margin),
            (x1 + margin, y1 + margin, z1 + margin),
        )


# Class `Cylinder`:
@dataclass(frozen=True, slots=True)
class Cylinder:
    """A cylinder standing along Z.

    Attributes:
    * `name` (`str`): What it is.
    * `center` (`tuple[float, float]`): Its axis' X and Y (mm).
    * `low` (`float`): The Z of its bottom (mm).
    * `high` (`float`): The Z of its top (mm).
    * `radius` (`float`): Its radius (mm).

    Constructor:
    * `Cylinder(name, center, low, high, radius)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    center: tuple[float, float] = field(init=True)
    low: float = field(init=True)
    high: float = field(init=True)
    radius: float = field(init=True)

    # Method `Cylinder.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the cylinder is not empty.

        Raises:
        * `ValueError`: If it has no height or no radius.
        """
        if self.low >= self.high or self.radius <= 0.0:
            raise ValueError(f"{self.low=}, {self.high=}, {self.radius=}")

    # Method `Cylinder.grown()`:
    def grown(self, margin: float) -> "Cylinder":
        """Return the cylinder grown on its side and both ends.

        Arguments:
        * `margin` (`float`): How far each surface moves out (mm).

        Returns:
        * (`Cylinder`): The larger cylinder, with the same name.
        """
        return Cylinder(
            self.name,
            self.center,
            self.low - margin,
            self.high + margin,
            self.radius + margin,
        )


# Class `KeepOut`:
@dataclass(slots=True)
class KeepOut:
    """The regions that a tool must not enter.

    Attributes:
    * `cylinders` (`list[Cylinder]`): The cylinders.
    * `prisms` (`list[Prism]`): The rectangular prisms.

    Constructor:
    * `KeepOut()`
    """

    # Attributes filled in later (alphabetized):
    cylinders: list[Cylinder] = field(init=False, default_factory=list)
    prisms: list[Prism] = field(init=False, default_factory=list)

    # Method `KeepOut.add_prism()`:
    def add_prism(self, prism: Prism, margin: str) -> Prism:
        """Grow a prism and add it as a region to keep out of.

        Arguments:
        * `prism` (`Prism`): The prism around the thing to protect.
        * `margin` (`str`):
          How far to grow it on all six sides, with its unit (such as
          `"1/8 in"`).

        Returns:
        * (`Prism`): The grown prism that was added.
        """
        grown: Prism = prism.grown(_mm(margin))
        self.prisms.append(grown)
        return grown

    # Method `KeepOut.add_cylinder()`:
    def add_cylinder(self, cylinder: Cylinder, margin: str) -> Cylinder:
        """Grow a cylinder and add it as a region to keep out of.

        Arguments:
        * `cylinder` (`Cylinder`): The cylinder around the thing to protect.
        * `margin` (`str`):
          How far to grow its side and both ends, with its unit (such
          as `"1/8 in"`).

        Returns:
        * (`Cylinder`): The grown cylinder that was added.
        """
        grown: Cylinder = cylinder.grown(_mm(margin))
        self.cylinders.append(grown)
        return grown

    # Method `KeepOut.model()`:
    def model(self, solidcraft: SolidCraftPyBind) -> list[str]:
        """Model the regions in SolidCraft, as see-through bodies.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

        Returns:
        * (`list[str]`):
          The names of the bodies: the prisms', then the cylinders'.
        """
        return [_model_prism(solidcraft, prism) for prism in self.prisms] + [
            _model_cylinder(solidcraft, cylinder)
            for cylinder in self.cylinders
        ]


# Function `_model_prism()`:
def _model_prism(solidcraft: SolidCraftPyBind, prism: Prism) -> str:
    """Model one keep-out prism as a see-through body.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `prism` (`Prism`): The prism.

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
def _model_cylinder(solidcraft: SolidCraftPyBind, cylinder: Cylinder) -> str:
    """Model one keep-out cylinder as a see-through body.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `cylinder` (`Cylinder`): The cylinder.

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
def _extrude_keep_out(
    solidcraft: SolidCraftPyBind, name: str, height: float
) -> str:
    """Extrude the sketch just made into a see-through body.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
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


# Class `Drill`:
@dataclass(frozen=True, slots=True)
class Drill:
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
    * `Drill(name, diameter, overall_length, flutes, shank_length,
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

    # Method `Drill.__post_init__()`:
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

    # Method `Drill.point_height()`:
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

    # Method `Drill.body_top()`:
    def body_top(self) -> float:
        """Return how far above the tip the shank starts.

        Returns:
        * (`float`): The height of the shank's bottom (millimeters).
        """
        return self.overall_length - self.shank_length

    # Method `Drill.section()`:
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

    # Method `Drill.point_cutter()`:
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

    # Method `Drill.groove_area()`:
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

    # Method `Drill.cylinder()`:
    def cylinder(self, tip: tuple[float, float, float]) -> Cylinder:
        """Return the cylinder that just encloses the drill.

        Arguments:
        * `tip` (`tuple[float, float, float]`): Where its tip is (mm).

        Returns:
        * (`Cylinder`): The cylinder, named for the drill.
        """
        radius: float = max(self.diameter, self.shank_diameter) / 2.0
        return Cylinder(
            self.name,
            (tip[0], tip[1]),
            tip[2],
            tip[2] + self.overall_length,
            radius,
        )

    # Method `Drill.model()`:
    def model(
        self,
        solidcraft: SolidCraftPyBind,
        tip: tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: str = DRILL_COLOR,
    ) -> str:
        """Model the drill, standing on its tip.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
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
SAMPLE_DRILLS: tuple[Drill, ...] = (
    Drill("Drill 1/4 x 4", _mm("1/4 in"), _mm("4 in"), 2, _mm("1-1/2 in")),
    Drill("Drill 1/2 x 6", _mm("1/2 in"), _mm("6 in"), 2, _mm("2 in")),
    Drill(
        "Drill 1 x 6, 1/2 shank",
        _mm("1 in"),
        _mm("6 in"),
        2,
        _mm("3 in"),
        _mm("1/2 in"),
    ),
    Drill(
        "Drill 3/4 x 8, 3 flute", _mm("3/4 in"), _mm("8 in"), 3, _mm("3 in")
    ),
    Drill("Drill 1/2 x 4, 4 flute", _mm("1/2 in"), _mm("4 in"), 4),
)


# Function `sample_drills()`:
def sample_drills(
    solidcraft: SolidCraftPyBind,
) -> tuple[list[str], KeepOut]:
    """Model `SAMPLE_DRILLS` in a row, each with a keep-out cylinder.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

    Returns:
    * (`tuple[list[str], KeepOut]`):
      The names of the drills' bodies, and their keep-out regions.
    """
    bodies: list[str] = []
    keep_out: KeepOut = KeepOut()
    for index, (drill, color) in enumerate(
        zip(SAMPLE_DRILLS, SAMPLE_DRILL_COLORS)
    ):
        center: float = (index - (len(SAMPLE_DRILLS) - 1) / 2) * DRILL_SPACING
        tip: tuple[float, float, float] = (center, DRILL_ROW_Y, 0.0)
        bodies.append(drill.model(solidcraft, tip, color))
        keep_out.add_cylinder(drill.cylinder(tip), DRILL_MARGIN)
    return bodies, keep_out


# Class `ViseNotches`:
@dataclass(frozen=True, slots=True)
class ViseNotches:
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
    * `ViseNotches(centers, width, depth, inner_radius, outer_radius)`
    """

    # Constructor arguments:
    centers: tuple[float, ...] = field(init=True)
    width: float = field(init=True)
    depth: float = field(init=True)
    inner_radius: float = field(init=True)
    outer_radius: float = field(init=True)

    # Method `ViseNotches.__post_init__()`:
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

    # Method `ViseNotches.side_corners()`:
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

    # Method `ViseNotches.area()`:
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


# Class `ViseBlock`:
@dataclass(frozen=True, slots=True)
class ViseBlock:
    """A block of a vise: a layer of its base, or a jaw.

    Its outline is a rectangle with rounded corners, and perhaps notches
    in its sides, extruded straight up.  All lengths are in millimeters.

    Attributes:
    * `length` (`float`): Its size along X, the screw's direction.
    * `width` (`float`): Its size along Y.
    * `height` (`float`): Its size along Z.
    * `corner_radius` (`float`): The radius of its four corners.

    Constructor:
    * `ViseBlock(length, width, height, corner_radius)`
    """

    # Constructor arguments:
    length: float = field(init=True)
    width: float = field(init=True)
    height: float = field(init=True)
    corner_radius: float = field(init=True, default=0.0)

    # Method `ViseBlock.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the numbers describe a block.

        Raises:
        * `ValueError`: If it has no size, or its corners do not fit.
        """
        if min(self.length, self.width, self.height) <= 0.0:
            raise ValueError(f"{self.length=}, {self.width=}, {self.height=}")
        if not 0.0 <= 2.0 * self.corner_radius <= min(self.length, self.width):
            raise ValueError(f"{self.corner_radius=} does not fit")

    # Method `ViseBlock.outline()`:
    def outline(
        self,
        name: str,
        center: tuple[float, float] = (0.0, 0.0),
        notches: ViseNotches | None = None,
    ) -> SCRoundPoly:
        """Return the block's outline, as seen from above.

        Arguments:
        * `name` (`str`): The outline's name.
        * `center` (`tuple[float, float]`): Its center's X and Y (mm).
        * `notches` (`ViseNotches | None`): The notches in its sides.

        Returns:
        * (`SCRoundPoly`): The outline, counter-clockwise.

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
        return SCRoundPoly(
            name,
            [
                SCCorner(x + corner.x, y + corner.y, corner.radius)
                for corner in corners
            ],
        )

    # Method `ViseBlock.volume()`:
    def volume(self, notches: ViseNotches | None = None) -> float:
        """Return the volume the model should have.

        Arguments:
        * `notches` (`ViseNotches | None`): The notches in its sides.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        corners: float = (4.0 - math.pi) * self.corner_radius**2
        removed: float = 0.0 if notches is None else notches.area()
        return (self.length * self.width - corners - removed) * self.height

    # Method `ViseBlock.model()`:
    def model(
        self,
        solidcraft: SolidCraftPyBind,
        name: str,
        center: Point = (0.0, 0.0, 0.0),
        notches: ViseNotches | None = None,
    ) -> str:
        """Model the block, up from the center of its bottom face.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `name` (`str`): The body's name.
        * `center` (`Point`): The center of its bottom face (mm).
        * `notches` (`ViseNotches | None`): The notches in its sides.

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


# Class `Vise`:
@dataclass(frozen=True, slots=True)
class Vise:
    """A milling vise, of the kind that Kurt makes.

    A picture rather than a true vise: enough to know what it is.

    The bottom and the middle are blocks, stacked and centered on one
    another.  They have notches in both sides that line up, for hold
    downs: the middle's are bigger, so that a box wrench fits around the
    nut.  On top, two rails run the whole length, with a block between
    them at each end.  Under the opening that leaves, the middle has a
    pocket down to the bottom, where the screw shows.

    The screw is a cylinder along X, from the pocket's -X end out through
    a hole in the middle's +X end, ending in an extruded hexagon.

    The jaws sit on the rails: the fixed jaw at the -X end, away from the
    hexagon, and the moving jaw opening toward +X.  Under the moving jaw,
    a slider fits between the rails and reaches down through the pocket,
    with a hole that the screw goes through.  It starts at the jaw's
    clamping face and is shorter than the jaw by an end block's length, so
    that the jaw reaches the base's +X end as the slider meets the end
    block.  A plate on each jaw's clamping face does the actual clamping,
    with two holes for the screws that hold it on.

    All lengths are in millimeters.

    Attributes:
    * `name` (`str`): What it is.
    * `bottom` (`ViseBlock`): The base's bottom layer.
    * `middle` (`ViseBlock`): The base's middle layer.
    * `bottom_notches` (`ViseNotches`): The notches in the bottom.
    * `middle_notches` (`ViseNotches`):
      The notches in the middle, at the same places but bigger.
    * `rail_width` (`float`): A rail's size along Y.
    * `rail_height` (`float`): The height of the rails and end blocks.
    * `rail_gap` (`float`): The distance between the rails.
    * `end_block_length` (`float`): An end block's size along X.
    * `fixed_jaw` (`ViseBlock`): The jaw that stays put.
    * `moving_jaw` (`ViseBlock`): The jaw that the screw moves.
    * `plate` (`ViseBlock`):
      A jaw plate, whose `length` is its thickness along X.
    * `plate_hole_spacing` (`float`): The distance between its holes.
    * `plate_hole_diameter` (`float`): The diameter of its holes.
    * `plate_hole_height` (`float`):
      The height of its holes' centers above its bottom.
    * `max_opening` (`float`): The largest gap between the plates.
    * `screw_diameter` (`float`): The screw's diameter.
    * `screw_stick_out` (`float`):
      How far the screw's cylinder reaches past the base's +X end.
    * `screw_height` (`float`):
      The height of the screw's axis above the base's bottom.
    * `screw_hole_diameter` (`float`):
      The diameter of the hole for the screw in the middle's end.
    * `hex_size` (`float`):
      The size across the flats of the hexagon on the screw's end.
    * `hex_length` (`float`): The hexagon's size along X.

    Constructor:
    * `Vise(name, bottom, middle, bottom_notches, middle_notches,
      rail_width, rail_height, rail_gap, end_block_length, fixed_jaw,
      moving_jaw, plate, plate_hole_spacing, plate_hole_diameter,
      plate_hole_height, max_opening, screw_diameter, screw_stick_out,
      screw_height, screw_hole_diameter, hex_size, hex_length)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    bottom: ViseBlock = field(init=True)
    middle: ViseBlock = field(init=True)
    bottom_notches: ViseNotches = field(init=True)
    middle_notches: ViseNotches = field(init=True)
    rail_width: float = field(init=True)
    rail_height: float = field(init=True)
    rail_gap: float = field(init=True)
    end_block_length: float = field(init=True)
    fixed_jaw: ViseBlock = field(init=True)
    moving_jaw: ViseBlock = field(init=True)
    plate: ViseBlock = field(init=True)
    plate_hole_spacing: float = field(init=True)
    plate_hole_diameter: float = field(init=True)
    plate_hole_height: float = field(init=True)
    max_opening: float = field(init=True)
    screw_diameter: float = field(init=True)
    screw_stick_out: float = field(init=True)
    screw_height: float = field(init=True)
    screw_hole_diameter: float = field(init=True)
    hex_size: float = field(init=True)
    hex_length: float = field(init=True)

    # Method `Vise.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the parts fit together.

        Raises:
        * `ValueError`: If the notches, the rails, the end blocks, the
          jaws, the slider or the screw do not fit.
        """
        self._check_notches()

        # The rails must have a size, and stay on the middle.
        rails: float = self.rail_gap + 2.0 * self.rail_width
        if (
            min(self.rail_width, self.rail_height, self.rail_gap) <= 0.0
            or rails > self.bottom.width
        ):
            raise ValueError(
                f"{self.rail_width=}, {self.rail_height=} and "
                f"{self.rail_gap=} do not fit {self.bottom.width=}"
            )

        # The end blocks must leave an opening between them.
        if not 0.0 < 2.0 * self.end_block_length < self.middle.length:
            raise ValueError(
                f"{self.end_block_length=} does not fit {self.middle.length=}"
            )

        # The jaws and plates must stay on the rails when wide open.
        jaws: float = (
            self.fixed_jaw.length
            + 2.0 * self.plate.length
            + self.max_opening
            + self.moving_jaw.length
        )
        if self.max_opening <= 0.0 or jaws > self.middle.length:
            raise ValueError(
                f"{self.max_opening=} and the jaws need {jaws:g} of "
                f"{self.middle.length=}"
            )

        # The jaws must match, and leave the slider some length.
        if (
            self.fixed_jaw.width != self.moving_jaw.width
            or self.fixed_jaw.height != self.moving_jaw.height
            or self.fixed_jaw.width > self.bottom.width
        ):
            raise ValueError(
                f"{self.fixed_jaw=} and {self.moving_jaw=} must match, on "
                f"{self.bottom.width=}"
            )
        if self.moving_jaw.length <= self.end_block_length:
            raise ValueError(
                f"{self.moving_jaw.length=} must exceed "
                f"{self.end_block_length=}"
            )
        self._check_plate()
        self._check_screw()

    # Method `Vise._check_notches()`:
    def _check_notches(self) -> None:
        """Check that the notches line up and fit their layers.

        Raises:
        * `ValueError`: If they are not at the same places, the middle's
          do not clear the bottom's or reach the pocket, or they do not
          fit their layers.
        """
        bottom: ViseNotches = self.bottom_notches
        middle: ViseNotches = self.middle_notches
        if bottom.centers != middle.centers:
            raise ValueError(
                f"{bottom.centers=} must line up with {middle.centers=}"
            )

        # The middle's notches must leave the bottom's open from above,
        # and a wall beside the pocket.
        bottom_in: float = self.bottom.width / 2.0 - bottom.depth
        middle_in: float = self.middle.width / 2.0 - middle.depth
        if middle.width < bottom.width or middle_in > bottom_in:
            raise ValueError(f"{middle=} must clear {bottom=}")
        if middle.centers and middle_in <= self.rail_gap / 2.0:
            raise ValueError(f"{middle=} reaches the pocket")

        # Making the outlines raises if the notches do not fit.
        self.bottom.outline(self.name, notches=bottom)
        self.middle.outline(self.name, notches=middle)

    # Method `Vise._check_plate()`:
    def _check_plate(self) -> None:
        """Check that a plate fits its jaw, and its holes fit the plate.

        Raises:
        * `ValueError`: If they do not.
        """
        if (
            self.plate.width > self.fixed_jaw.width
            or self.plate.height > self.fixed_jaw.height
        ):
            raise ValueError(f"{self.plate=} must fit {self.fixed_jaw=}")
        radius: float = self.plate_hole_diameter / 2.0
        if (
            radius <= 0.0
            or self.plate_hole_spacing / 2.0 + radius >= self.plate.width / 2.0
            or self.plate_hole_spacing <= 2.0 * radius
            or self.plate_hole_height - radius <= 0.0
            or self.plate_hole_height + radius >= self.plate.height
        ):
            raise ValueError(
                f"{self.plate_hole_diameter=} at {self.plate_hole_spacing=} "
                f"and {self.plate_hole_height=} do not fit {self.plate=}"
            )

    # Method `Vise._check_screw()`:
    def _check_screw(self) -> None:
        """Check that the screw fits its hole, and its hole the middle.

        Raises:
        * `ValueError`: If it does not.
        """
        radius: float = self.screw_hole_diameter / 2.0
        if (
            not 0.0 < self.screw_diameter <= self.screw_hole_diameter
            or self.screw_hole_diameter >= self.rail_gap
            or self.screw_height - radius < self.bottom.height
            or self.screw_height + radius
            > self.bottom.height + self.middle.height
        ):
            raise ValueError(
                f"{self.screw_diameter=} in {self.screw_hole_diameter=} at "
                f"{self.screw_height=} does not fit in {self.middle=} "
                f"with {self.rail_gap=}"
            )
        if min(self.screw_stick_out, self.hex_size, self.hex_length) <= 0.0:
            raise ValueError(
                f"{self.screw_stick_out=}, {self.hex_size=}, "
                f"{self.hex_length=}"
            )

    # Method `Vise.base_height()`:
    def base_height(self) -> float:
        """Return the height of the base, up to the top of the rails.

        Returns:
        * (`float`): The height (millimeters).
        """
        return self.bottom.height + self.middle.height + self.rail_height

    # Method `Vise.overall_length()`:
    def overall_length(self) -> float:
        """Return the vise's length, out to the end of the hexagon.

        Returns:
        * (`float`): The length (millimeters).
        """
        return self.middle.length + self.screw_stick_out + self.hex_length

    # Method `Vise.opening_length()`:
    def opening_length(self) -> float:
        """Return the length of the opening between the end blocks.

        Returns:
        * (`float`): The length (millimeters).
        """
        return self.middle.length - 2.0 * self.end_block_length

    # Method `Vise.slider()`:
    def slider(self) -> ViseBlock:
        """Return the block under the moving jaw, between the rails.

        Returns:
        * (`ViseBlock`):
          The slider: as wide as the end blocks, shorter than the moving
          jaw by an end block's length, and reaching from the jaw's bottom
          down to the pocket's floor.  Its hole is not included.
        """
        return ViseBlock(
            self.moving_jaw.length - self.end_block_length,
            self.rail_gap,
            self.middle.height + self.rail_height,
        )

    # Method `Vise.slider_volume()`:
    def slider_volume(self) -> float:
        """Return the volume the slider's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        slider: ViseBlock = self.slider()
        hole: float = (
            math.pi * (self.screw_diameter / 2.0) ** 2 * slider.length
        )
        return slider.volume() - hole

    # Method `Vise.plate_volume()`:
    def plate_volume(self) -> float:
        """Return the volume a jaw plate's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        hole: float = math.pi * (self.plate_hole_diameter / 2.0) ** 2
        return self.plate.volume() - 2.0 * hole * self.plate.length

    # Method `Vise.moving_face()`:
    def moving_face(self, opening: float) -> float:
        """Return the X of the moving jaw's clamping face, behind its plate.

        Arguments:
        * `opening` (`float`): The gap between the plates (millimeters).

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
            -self.middle.length / 2.0
            + self.fixed_jaw.length
            + 2.0 * self.plate.length
            + opening
        )

    # Method `Vise.hexagon()`:
    def hexagon(self) -> list[tuple[float, float]]:
        """Return the corners of the screw's hexagon, flats up and down.

        Returns:
        * (`list[tuple[float, float]]`):
          The `(y, z)` of each corner, from the screw's axis.
        """
        radius: float = self.hex_size / math.sqrt(3.0)
        return [
            (
                radius * math.cos(math.radians(60.0 * index)),
                radius * math.sin(math.radians(60.0 * index)),
            )
            for index in range(6)
        ]

    # Method `Vise.middle_volume()`:
    def middle_volume(self) -> float:
        """Return the volume the middle's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        pocket: float = (
            self.opening_length() * self.rail_gap * self.middle.height
        )
        hole: float = (
            math.pi
            * (self.screw_hole_diameter / 2.0) ** 2
            * self.end_block_length
        )
        return self.middle.volume(self.middle_notches) - pocket - hole

    # Method `Vise.screw_volume()`:
    def screw_volume(self) -> float:
        """Return the volume the screw's model should have.

        Returns:
        * (`float`): The volume (cubic millimeters).
        """
        cylinder: float = (
            math.pi
            * (self.screw_diameter / 2.0) ** 2
            * (
                self.opening_length()
                + self.end_block_length
                + self.screw_stick_out
            )
        )
        hexagon: float = math.sqrt(3.0) / 2.0 * self.hex_size**2
        return cylinder + hexagon * self.hex_length

    # Method `Vise.keep_out()`:
    # Each edge of the three prisms gets a name, past `pylint`'s limit.
    def keep_out(  # pylint: disable=too-many-locals
        self,
        center: Point = (0.0, 0.0, 0.0),
        opening: float = 0.0,
        margin: str = VISE_MARGIN,
    ) -> KeepOut:
        """Return the regions around the vise that a tool must not enter.

        One prism holds the base and the hexagon, one the fixed jaw and
        its plate, and one the moving jaw and its plate.  The moving
        jaw's reaches out to the end of the hexagon, which is where the
        jaw and the wrench on the hexagon go.

        Arguments:
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the plates (mm).
        * `margin` (`str`):
          How far to grow each prism, with its unit (such as `"1/8 in"`).

        Returns:
        * (`KeepOut`): The three grown prisms, in that order.

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        x, y, z = center
        half_x: float = self.middle.length / 2.0
        hex_end: float = x + half_x + self.screw_stick_out + self.hex_length
        half_base: float = self.bottom.width / 2.0
        half_jaw: float = self.fixed_jaw.width / 2.0
        rails: float = z + self.base_height()
        jaw_top: float = rails + self.fixed_jaw.height
        fixed_end: float = (
            x - half_x + self.fixed_jaw.length + self.plate.length
        )
        moving_start: float = x + self.moving_face(opening) - self.plate.length

        keep_out: KeepOut = KeepOut()
        for name, low, high in (
            (
                "base",
                (x - half_x, y - half_base, z),
                (hex_end, y + half_base, rails),
            ),
            (
                "fixed jaw",
                (x - half_x, y - half_jaw, rails),
                (fixed_end, y + half_jaw, jaw_top),
            ),
            (
                "moving jaw",
                (moving_start, y - half_jaw, rails),
                (hex_end, y + half_jaw, jaw_top),
            ),
        ):
            keep_out.add_prism(Prism(f"{self.name} {name}", low, high), margin)
        return keep_out

    # Method `Vise.model()`:
    def model(
        self,
        solidcraft: SolidCraftPyBind,
        center: Point = (0.0, 0.0, 0.0),
        opening: float = 0.0,
        lift: float = 0.0,
    ) -> list[str]:
        """Model the vise, up from the center of the base's bottom face.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the bottom face (mm).
        * `opening` (`float`): The gap between the plates (mm).
        * `lift` (`float`):
          How far to raise the jaws, the slider and the plates off the
          rails, to see how they go together (mm).

        Returns:
        * (`list[str]`):
          The names of the bodies: the bottom, the middle, the rails, the
          end blocks, the screw, the jaws, the slider and the plates.

        Raises:
        * `ValueError`: If `opening` is out of range.
        """
        # Stack the blocks, each on the one before.
        x, y, z = center
        bottom: str = self.bottom.model(
            solidcraft, f"{self.name} bottom", center, self.bottom_notches
        )
        middle: str = self.middle.model(
            solidcraft,
            f"{self.name} middle",
            (x, y, z + self.bottom.height),
            self.middle_notches,
        )
        self._cut_pocket(solidcraft, middle, center)
        self._cut_screw_hole(solidcraft, middle, center)
        return [
            bottom,
            middle,
            *self._model_rails(solidcraft, center),
            self._model_screw(solidcraft, center),
            *self._model_jaws(solidcraft, center, opening, lift),
        ]

    # Method `Vise._end_plane()`:
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

    # Method `Vise._cut_pocket()`:
    def _cut_pocket(
        self, solidcraft: SolidCraftPyBind, body: str, center: Point
    ) -> None:
        """Cut the pocket in the middle, under the rails' opening.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `body` (`str`): The middle's body.
        * `center` (`Point`): The center of the base's bottom face (mm).
        """
        x, y, z = center
        name: str = f"{self.name} pocket"
        solidcraft.sketch.create(
            plane="XY", offset=z + self.bottom.height, name=name
        )
        pocket: ViseBlock = ViseBlock(
            self.opening_length(), self.rail_gap, self.middle.height
        )
        pocket.outline(name, (x, y)).sketch(solidcraft)
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.middle.height, operation="cut", targets=[body]
        )

    # Method `Vise._cut_screw_hole()`:
    def _cut_screw_hole(
        self, solidcraft: SolidCraftPyBind, body: str, center: Point
    ) -> None:
        """Cut the hole for the screw, through the middle's +X end wall.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `body` (`str`): The middle's body.
        * `center` (`Point`): The center of the base's bottom face (mm).
        """
        solidcraft.sketch.create(
            plane=self._end_plane(center, self.middle.length / 2.0),
            name=f"{self.name} screw hole",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.screw_height),
            diameter=self.screw_hole_diameter,
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.end_block_length,
            direction="negative",
            operation="cut",
            targets=[body],
        )

    # Method `Vise._model_rails()`:
    def _model_rails(
        self, solidcraft: SolidCraftPyBind, center: Point
    ) -> list[str]:
        """Model the two rails, and the two end blocks between them.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).

        Returns:
        * (`list[str]`): The names of the rails, then the end blocks.
        """
        x, y, z = center
        top: float = z + self.bottom.height + self.middle.height
        rail: ViseBlock = ViseBlock(
            self.middle.length, self.rail_width, self.rail_height
        )
        block: ViseBlock = ViseBlock(
            self.end_block_length, self.rail_gap, self.rail_height
        )
        rail_y: float = (self.rail_gap + self.rail_width) / 2.0
        block_x: float = (self.middle.length - self.end_block_length) / 2.0
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
                solidcraft, f"{self.name} screw end", (x + block_x, y, top)
            ),
        ]

    # Method `Vise._model_jaws()`:
    def _model_jaws(
        self,
        solidcraft: SolidCraftPyBind,
        center: Point,
        opening: float,
        lift: float,
    ) -> list[str]:
        """Model the jaws, the slider under one, and their plates.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `opening` (`float`): The gap between the plates (mm).
        * `lift` (`float`): How far to raise them all (mm).

        Returns:
        * (`list[str]`):
          The names of the jaws, then of the slider, then of the plates.
        """
        x, y, z = center
        face: float = self.moving_face(opening)
        top: float = z + self.base_height() + lift
        fixed_x: float = -(self.middle.length - self.fixed_jaw.length) / 2.0
        half_plate: float = self.plate.length / 2.0
        fixed_face: float = -self.middle.length / 2.0 + self.fixed_jaw.length
        return [
            self.fixed_jaw.model(
                solidcraft, f"{self.name} fixed jaw", (x + fixed_x, y, top)
            ),
            self.moving_jaw.model(
                solidcraft,
                f"{self.name} moving jaw",
                (x + face + self.moving_jaw.length / 2.0, y, top),
            ),
            self._model_slider(solidcraft, center, face, lift),
            self._model_plate(
                solidcraft,
                f"{self.name} fixed plate",
                (x + fixed_face + half_plate, y, top),
            ),
            self._model_plate(
                solidcraft,
                f"{self.name} moving plate",
                (x + face - half_plate, y, top),
            ),
        ]

    # Method `Vise._model_plate()`:
    def _model_plate(
        self, solidcraft: SolidCraftPyBind, name: str, center: Point
    ) -> str:
        """Model a jaw plate, with the holes for its two screws.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `name` (`str`): The body's name.
        * `center` (`Point`): The center of the plate's bottom face (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        body: str = self.plate.model(solidcraft, name, center)

        # Cut both holes back through it from its +X face.
        solidcraft.sketch.create(
            plane=self._end_plane(center, self.plate.length / 2.0),
            name=f"{name} holes",
        )
        half: float = self.plate_hole_spacing / 2.0
        for across in (-half, half):
            solidcraft.sketch.circle_center(
                center=(across, self.plate_hole_height),
                diameter=self.plate_hole_diameter,
            )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=self.plate.length,
            direction="negative",
            operation="cut",
            targets=[body],
        )
        return body

    # Method `Vise._model_slider()`:
    def _model_slider(
        self,
        solidcraft: SolidCraftPyBind,
        center: Point,
        face: float,
        lift: float,
    ) -> str:
        """Model the slider, with the hole that the screw goes through.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).
        * `face` (`float`): The X of the moving jaw's clamping face (mm).
        * `lift` (`float`): How far to raise it (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The block, with its bottom on the pocket's floor.
        x, y, z = center
        slider: ViseBlock = self.slider()
        body: str = slider.model(
            solidcraft,
            f"{self.name} slider",
            (
                x + face + slider.length / 2.0,
                y,
                z + self.bottom.height + lift,
            ),
        )

        # The hole, cut back from the slider's +X end.
        solidcraft.sketch.create(
            plane=self._end_plane(center, face + slider.length),
            name=f"{self.name} slider hole",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.screw_height + lift),
            diameter=self.screw_diameter,
        )
        solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=slider.length,
            direction="negative",
            operation="cut",
            targets=[body],
        )
        return body

    # Method `Vise._model_screw()`:
    def _model_screw(self, solidcraft: SolidCraftPyBind, center: Point) -> str:
        """Model the screw: a cylinder, with a hexagon on its end.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of the base's bottom face (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The cylinder, from the pocket's -X end out past the +X end.
        solidcraft.sketch.create(
            plane=self._end_plane(center, -self.opening_length() / 2.0),
            name=f"{self.name} screw",
        )
        solidcraft.sketch.circle_center(
            center=(0.0, self.screw_height), diameter=self.screw_diameter
        )
        solidcraft.sketch.finish()
        made: JSON = solidcraft.solid.extrude(
            distance=(
                self.opening_length()
                + self.end_block_length
                + self.screw_stick_out
            ),
            body_name=f"{self.name} screw",
        )
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        assert isinstance(bodies, list) and isinstance(bodies[0], str)
        body: str = bodies[0]

        # Join the hexagon onto its end.
        solidcraft.sketch.create(
            plane=self._end_plane(
                center, self.middle.length / 2.0 + self.screw_stick_out
            ),
            name=f"{self.name} hex",
        )
        solidcraft.sketch.line(
            points=[
                [across, self.screw_height + up]
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
# 4.375 in).  All of its layers are 6 in wide but the middle, at the
# user's word; the listings' 8.25 in overall width is not used.  The usual
# 6 in plate's thickness and holes come from the user's notes: about
# 0.725 in, on 3-7/8 in centers, for 1/2-13 screws, with centers 0.940 in
# or more above the bottom (17/32 in is a clearance hole).  Its 3/4 in hex
# comes from the Shars 2026 catalog, page 317, which sells handles for it
# (7/8 in for Kurt's 8 in vises).  Everything else is an estimate, good
# enough to know what it is.
KURT_D688: Vise = Vise(
    name="Kurt D688",
    bottom=ViseBlock(
        _mm("15.75 in"), _mm("6 in"), _mm("0.5 in"), _mm("1/2 in")
    ),
    middle=ViseBlock(
        _mm("15.75 in"), _mm("5-1/4 in"), _mm("1.39 in"), _mm("1/2 in")
    ),
    bottom_notches=ViseNotches(
        centers=(_mm("-4 in"), _mm("4 in")),
        width=_mm("7/8 in"),
        depth=_mm("7/8 in"),
        inner_radius=_mm("1/4 in"),
        outer_radius=_mm("1/8 in"),
    ),
    middle_notches=ViseNotches(
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
    fixed_jaw=ViseBlock(_mm("1 in"), _mm("6 in"), _mm("1.735 in")),
    moving_jaw=ViseBlock(_mm("3-3/4 in"), _mm("6 in"), _mm("1.735 in")),
    plate=ViseBlock(_mm("0.725 in"), _mm("6 in"), _mm("1.735 in")),
    plate_hole_spacing=_mm("3-7/8 in"),
    plate_hole_diameter=_mm("17/32 in"),
    plate_hole_height=_mm("0.94 in"),
    max_opening=_mm("8.8 in"),
    screw_diameter=_mm("1 in"),
    screw_stick_out=_mm("1/4 in"),
    screw_height=_mm("1.195 in"),
    screw_hole_diameter=_mm("1-1/8 in"),
    hex_size=_mm("3/4 in"),
    hex_length=_mm("3/4 in"),
)


# Class `Parallel`:
@dataclass(frozen=True, slots=True)
class Parallel:
    """A parallel: a thin steel bar that work sits on in a vise.

    It stands on edge, with its length along Y, the way it lies along
    the jaws of a vise whose screw runs along X.  All lengths are in
    millimeters.

    Attributes:
    * `name` (`str`): What it is.
    * `height` (`float`): Its size along Z.
    * `thickness` (`float`): Its size along X.
    * `length` (`float`): Its size along Y.

    Constructor:
    * `Parallel(name, height, thickness, length)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    height: float = field(init=True)
    thickness: float = field(init=True)
    length: float = field(init=True)

    # Method `Parallel.block()`:
    def block(self) -> ViseBlock:
        """Return the parallel's shape.

        Returns:
        * (`ViseBlock`): A block with square corners.

        Raises:
        * `ValueError`: If it has no size.
        """
        return ViseBlock(self.thickness, self.length, self.height)

    # Method `Parallel.prism()`:
    def prism(self, center: Point) -> Prism:
        """Return the rectangular prism that just encloses the parallel.

        Arguments:
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`Prism`): The prism, named for the parallel.
        """
        x, y, z = center
        half_x: float = self.thickness / 2.0
        half_y: float = self.length / 2.0
        return Prism(
            self.name,
            (x - half_x, y - half_y, z),
            (x + half_x, y + half_y, z + self.height),
        )

    # Method `Parallel.model()`:
    def model(self, solidcraft: SolidCraftPyBind, center: Point) -> str:
        """Model the parallel, up from the center of its bottom edge.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        body: str = self.block().model(solidcraft, self.name, center)
        solidcraft.appearance.assign(bodies=[body], color=DRILL_COLOR)
        return body


# The heights of a set of parallels.  The set stops at 2 in, the high end
# of what is sold.
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
    "1-3/4 in",
    "1-7/8 in",
    "2 in",
)

# A whole set: two parallels of each height, since work sits on a pair.
PARALLELS: tuple[Parallel, ...] = tuple(
    Parallel(
        f"Parallel {height} {side}",
        _mm(height),
        _mm("1/8 in"),
        _mm("6 in"),
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
    solidcraft: SolidCraftPyBind,
) -> tuple[list[str], KeepOut]:
    """Model `PARALLELS` in a row, each with a keep-out prism.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

    Returns:
    * (`tuple[list[str], KeepOut]`):
      The names of the parallels' bodies, and their keep-out regions.
    """
    bodies: list[str] = []
    keep_out: KeepOut = KeepOut()
    for parallel, x in zip(PARALLELS, parallel_centers()):
        center: Point = (x, PARALLEL_ROW_Y, 0.0)
        bodies.append(parallel.model(solidcraft, center))
        keep_out.add_prism(parallel.prism(center), PARALLEL_MARGIN)
    return bodies, keep_out


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


# Class `Tormach`:
@dataclass(slots=True)
class Tormach:
    """Models of Tormach's equipment.

    Attributes:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

    Constructor:
    * `Tormach(solidcraft)`
    """

    # Constructor arguments:
    solidcraft: SolidCraftPyBind = field(init=True)

    # Method `Tormach.mill_tables()`:
    def mill_tables(self) -> list[str]:
        """Model the tables of the 440, 770 and 1100, side by side.

        Returns:
        * (`list[str]`): The names of the bodies, in `MILL_TABLES` order.
        """
        return [
            self.mill_table(table, center_y)
            for table, center_y in zip(MILL_TABLES, table_centers())
        ]

    # Method `Tormach.mill_table_keep_out()`:
    def mill_table_keep_out(self, margin: str = TABLE_MARGIN) -> KeepOut:
        """Return the tables' keep-out regions, laid out as `mill_tables()`.

        Arguments:
        * `margin` (`str`):
          How far to grow each table's prism, with its unit.

        Returns:
        * (`KeepOut`): One grown prism per table.
        """
        keep_out: KeepOut = KeepOut()
        for table, center_y in zip(MILL_TABLES, table_centers()):
            keep_out.add_prism(table.prism(center_y), margin)
        return keep_out

    # Method `Tormach.mill_table()`:
    def mill_table(self, table: MillTable, center_y: float = 0.0) -> str:
        """Model one mill table.

        Arguments:
        * `table` (`MillTable`): The table.
        * `center_y` (`float`): The Y of its center (millimeters).

        Returns:
        * (`str`): The body's name (SolidCraft may change it, if the
          name is taken).
        """
        # The plate, from the top down.
        solidcraft: SolidCraftPyBind = self.solidcraft
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

        # The pockets at the ends of the slots.
        offset: float = (table.slot_length + table.pocket_length) / 2.0
        for pocket_x in (-offset, offset):
            self._cut_pocket(table, body, pocket_x, center_y)
        solidcraft.appearance.assign(bodies=[body], color=TABLE_COLOR)
        return body

    # Method `Tormach._cut_slot()`:
    def _cut_slot(self, table: MillTable, body: str, center_y: float) -> None:
        """Cut one T-slot.

        Arguments:
        * `table` (`MillTable`): The table.
        * `body` (`str`): The table's body.
        * `center_y` (`float`): The Y of the slot's center (millimeters).
        """
        # The plane looks along +X, with sketch X along Y and sketch Y up.
        solidcraft: SolidCraftPyBind = self.solidcraft
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

    # Method `Tormach._cut_pocket()`:
    def _cut_pocket(
        self, table: MillTable, body: str, center_x: float, center_y: float
    ) -> None:
        """Cut one of the pockets at the ends of the slots.

        Arguments:
        * `table` (`MillTable`): The table.
        * `body` (`str`): The table's body.
        * `center_x` (`float`): The X of the pocket's center (millimeters).
        * `center_y` (`float`): The Y of the pocket's center (millimeters).
        """
        solidcraft: SolidCraftPyBind = self.solidcraft
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
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
        solidcraft.file.new()
        tormach: Tormach = Tormach(solidcraft)
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
