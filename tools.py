#!/usr/bin/env python3
"""3D models of the tooling that holds work on a machine, for SolidCraft.

So far, the tables of Tormach's three entry level mills, each with its
T-slots and the pockets at their ends that T-nuts drop in through;
the keep-out regions around them that a tool must not enter; and generic
drills.

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

import math
import sys
from dataclasses import dataclass, field

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
    """Show tables, drills and their keep-outs, in a new design."""
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
        solidcraft.view.apply(view="iso")


if __name__ == "__main__":
    main()
