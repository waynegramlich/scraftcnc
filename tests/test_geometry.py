"""Tests for `geometry.py`: run `python3 -m unittest -v`."""

# It takes many tests to cover this module's geometry, so it is longer
# than `pylint` likes.
# pylint: disable=too-many-lines

import math
import random
import types
import unittest
from collections.abc import Sequence
from typing import cast

from scraftcnc.geometry import (
    SLOP,
    Point,
    SCArc,
    SCCorner,
    SCHole,
    SCLine,
    SCLoop,
    SCRoundedPolygon,
    SCSegment,
    distance_to,
    fraction_of,
    inset,
    offset_segment,
    point_at,
    reverse_segment,
    split_at,
)
from scraftcnc.pybind.scraftpybind import SCPyBind


# Function `notched()`:
def notched() -> SCRoundedPolygon:
    """Return a notched rectangle, a different radius at each corner.

    Returns:
    * (`SCRoundedPolygon`): An 80 x 50 notched rectangle, going
      counter-clockwise, whose notch's inner corner turns the other way.
    """
    return SCRoundedPolygon(
        "Notched",
        [
            SCCorner(0.0, 0.0, 5.0),
            SCCorner(80.0, 0.0, 10.0),
            SCCorner(80.0, 50.0, 3.0),
            SCCorner(40.0, 50.0, 2.0),
            SCCorner(40.0, 30.0, 4.0),
            SCCorner(20.0, 30.0, 0.0),
            SCCorner(0.0, 50.0, 6.0),
        ],
        0.0,
        1.0,
    )


# Function `square()`:
def square(side: float, radius: float, ccw: bool = True) -> SCRoundedPolygon:
    """Return a square with one corner at the origin.

    Arguments:
    * `side` (`float`): The length of each side.
    * `radius` (`float`): The radius of every corner.
    * `ccw` (`bool`): True to go counter-clockwise.

    Returns:
    * (`SCRoundedPolygon`): The square.
    """
    points: list[tuple[float, float]] = [
        (0.0, 0.0),
        (side, 0.0),
        (side, side),
        (0.0, side),
    ]
    if not ccw:
        points.reverse()
    return SCRoundedPolygon(
        "Square", [SCCorner(x, y, radius) for x, y in points], 0.0, 1.0
    )


# Function `polygon()`:
def polygon(
    *points: tuple[float, float], radius: float = 0.0
) -> SCRoundedPolygon:
    """Return a polygon with the same radius at every corner.

    Arguments:
    * `points` (`tuple[float, float]`): The corners.
    * `radius` (`float`): The radius of every corner.

    Returns:
    * (`SCRoundedPolygon`): The polygon.
    """
    return SCRoundedPolygon(
        "Polygon", [SCCorner(x, y, radius) for x, y in points], 0.0, 1.0
    )


# Function `close()`:
def close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Return whether two points are the same, to rounding.

    Arguments:
    * `a` (`tuple[float, float]`): One point.
    * `b` (`tuple[float, float]`): The other.

    Returns:
    * (`bool`): True when they are within 1e-9 of each other.
    """
    return math.dist(a, b) < 1e-9


# Function `box()`:
# The arguments read like the constructor's, in the same order.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def box(
    name: str,
    low: float,
    high: float,
    z_start: float,
    z_end: float,
    children: Sequence[SCRoundedPolygon] = (),
) -> SCRoundedPolygon:
    """Return a square with sharp corners.

    Arguments:
    * `name` (`str`): Its name.
    * `low` (`float`): Its lowest X and Y.
    * `high` (`float`): Its highest X and Y.
    * `z_start` (`float`): The height it starts at.
    * `z_end` (`float`): The height it ends at.
    * `children` (`tuple[SCRoundedPolygon, ...]`): Its children.

    Returns:
    * (`SCRoundedPolygon`): The square.
    """
    corners: tuple[SCCorner, ...] = (
        SCCorner(low, low),
        SCCorner(high, low),
        SCCorner(high, high),
        SCCorner(low, high),
    )
    return SCRoundedPolygon(name, corners, z_start, z_end, children)


# Function `plate_with_island()`:
def plate_with_island() -> SCRoundedPolygon:
    """Return a plate with a hole, a pocket, an island, and its hole.

    Returns:
    * (`SCRoundedPolygon`): A 100 x 100 plate, from Z = 0 up to 10; a
      hole through it at (10, 10); a pocket from 30 to 90, down to Z = 5;
      an island from 50 to 70, up to Z = 10; a hole through everything
      at (60, 60).
    """
    island: SCRoundedPolygon = box(
        "Island", 50.0, 70.0, 5.0, 10.0, (SCHole(60.0, 60.0, 10.0, 10.0, 0.0),)
    )
    pocket: SCRoundedPolygon = box("Pocket", 30.0, 90.0, 10.0, 5.0, (island,))
    return box(
        "Plate",
        0.0,
        100.0,
        0.0,
        10.0,
        (SCHole(10.0, 10.0, 10.0, 10.0, 0.0), pocket),
    )


# Function `tip_over_strip()`:
def tip_over_strip() -> SCRoundedPolygon:
    """Return a polygon whose sharp corner would reach over its own arm.

    Returns:
    * (`SCRoundedPolygon`):
      A wedge rounded so hard that it stops near X = 52, though its
      sharp tip would reach X = 100, past a strip at X = 70 to 75.
    """
    return SCRoundedPolygon(
        "Tip",
        [
            SCCorner(0.0, -17.63),
            SCCorner(100.0, 0.0, 10.0),
            SCCorner(0.0, 17.63),
            SCCorner(10.0, 40.0),
            SCCorner(70.0, 40.0),
            SCCorner(70.0, -5.0),
            SCCorner(75.0, -5.0),
            SCCorner(75.0, 60.0),
            SCCorner(-10.0, 60.0),
            SCCorner(-10.0, -17.63),
        ],
        0.0,
        1.0,
    )


# Function `past_square()`:
def past_square(x: float, y: float) -> float:
    """Return how far past `square(20.0, 5.0)` a point is.

    Arguments:
    * `x` (`float`): The point's X.
    * `y` (`float`): The point's Y.

    Returns:
    * (`float`): The distance beyond its edge (below 0 inside).
    """
    return (
        math.hypot(
            max(abs(x - 10.0) - 5.0, 0.0),
            max(abs(y - 10.0) - 5.0, 0.0),
        )
        - 5.0
    )


# Function `past_circle()`:
def past_circle(x: float, y: float) -> float:
    """Return how far past a circle at (10, 10), radius 7, a point is.

    Arguments:
    * `x` (`float`): The point's X.
    * `y` (`float`): The point's Y.

    Returns:
    * (`float`): The distance beyond its edge (below 0 inside).
    """
    return math.hypot(x - 10.0, y - 10.0) - 7.0


# Function `arc_at()`:
def arc_at(
    center: tuple[float, float], radius: float, start: float, sweep: float
) -> SCArc:
    """Return an arc given by its angles.

    Arguments:
    * `center` (`tuple[float, float]`): Its center.
    * `radius` (`float`): Its radius.
    * `start` (`float`): The angle it starts at (degrees).
    * `sweep` (`float`):
      The angle it sweeps (degrees), positive counter-clockwise.

    Returns:
    * (`SCArc`): The arc.
    """
    first: float = math.radians(start)
    last: float = math.radians(start + sweep)
    return SCArc(
        (
            center[0] + radius * math.cos(first),
            center[1] + radius * math.sin(first),
        ),
        (
            center[0] + radius * math.cos(last),
            center[1] + radius * math.sin(last),
        ),
        center,
        radius,
        math.radians(sweep),
    )


# Class `TestLineEnters`:
class TestLineEnters(unittest.TestCase):
    """Whether a line enters an `SCRoundedPolygon`."""

    # Method `TestLineEnters.check()`:
    def check(
        self,
        poly: SCRoundedPolygon,
        start: tuple[float, float],
        end: tuple[float, float],
        expected: bool,
    ) -> None:
        """Check a line, going each way, with and without `bound`.

        Arguments:
        * `poly` (`SCRoundedPolygon`): The polygon.
        * `start` (`tuple[float, float]`): One end of the line.
        * `end` (`tuple[float, float]`): The other end.
        * `expected` (`bool`): True when the line should enter.
        """
        bound: tuple[SCLine, ...] = poly.bound
        for poly.bound in (bound, ()):
            self.assertEqual(
                poly.enters(SCLine(start, end)), expected, (start, end)
            )

            # The ends are swapped on purpose, to go the other way.
            # pylint: disable-next=arguments-out-of-order
            reverse: SCLine = SCLine(end, start)
            self.assertEqual(poly.enters(reverse), expected, (end, start))
        poly.bound = bound

    # Method `TestLineEnters.test_sharp()`:
    def test_sharp(self) -> None:
        """Lines around, through, into and inside a sharp square."""
        poly: SCRoundedPolygon = square(20.0, 0.0)
        self.check(poly, (-5.0, -5.0), (25.0, -5.0), False)
        self.check(poly, (-5.0, -5.0), (-1.0, -1.0), False)
        self.check(poly, (-5.0, 10.0), (25.0, 10.0), True)
        self.check(poly, (-5.0, 10.0), (10.0, 10.0), True)
        self.check(poly, (5.0, 5.0), (15.0, 15.0), True)

    # Method `TestLineEnters.test_touching()`:
    def test_touching(self) -> None:
        """Touching or following an edge is clear; going in is not."""
        poly: SCRoundedPolygon = square(20.0, 0.0)
        self.check(poly, (-5.0, 10.0), (0.0, 10.0), False)
        self.check(poly, (-5.0, 0.0), (25.0, 0.0), False)
        self.check(poly, (5.0, 0.0), (15.0, 0.0), False)
        self.check(poly, (-5.0, 5.0), (5.0, -5.0), False)
        self.check(poly, (0.0, 10.0), (1.0, 10.0), True)
        self.check(poly, (0.0, 10.0), (20.0, 10.0), True)
        self.check(poly, (0.0, 0.0), (20.0, 20.0), True)

    # Method `TestLineEnters.test_rounded_corner()`:
    def test_rounded_corner(self) -> None:
        """Where the sharp corner would be, the rounded one is clear."""
        poly: SCRoundedPolygon = square(20.0, 5.0)

        # A line across the sharp corner that misses the arc.
        self.check(poly, (-1.0, 3.0), (3.0, -1.0), False)

        # A line wholly in the piece that rounding took away.
        self.check(poly, (0.2, 0.2), (0.5, 0.2), False)

        # Exactly tangent to the arc, and just past tangent.
        tangent: float = 10.0 - 5.0 * math.sqrt(2.0)
        self.check(poly, (tangent + 1.0, -1.0), (-1.0, tangent + 1.0), False)
        self.check(
            poly,
            (tangent + 1.01, -1.0),
            (-1.0, tangent + 1.01),
            True,
        )
        self.check(poly, (-1.0, 5.0), (5.0, -1.0), True)

    # Method `TestLineEnters.test_inward_corner()`:
    def test_inward_corner(self) -> None:
        """A corner turning inward gains what rounding adds."""
        poly: SCRoundedPolygon = notched()

        # The arc about (36, 34), radius 4, fills in the notch's corner
        # at (40, 30).  This line is in that fill, out of the sharp
        # shape.
        sharp: SCRoundedPolygon = SCRoundedPolygon(
            "Sharp", [SCCorner(c.x, c.y) for c in poly.corners], 0.0, 1.0
        )
        self.check(sharp, (39.5, 30.5), (39.2, 30.8), False)
        self.check(poly, (39.5, 30.5), (39.2, 30.8), True)

        # In the notch, clear of the fill, and tangent to its arc.
        self.check(poly, (30.0, 40.0), (36.0, 34.0), False)
        apart: float = 4.0 / math.sqrt(2.0)
        touch: tuple[float, float] = (36.0 + apart, 34.0 - apart)
        self.check(
            poly,
            (touch[0] - 1.0, touch[1] - 1.0),
            (touch[0] + 1.0, touch[1] + 1.0),
            True,
        )
        self.check(poly, (36.0, 34.0), touch, False)

    # Method `TestLineEnters.test_bound()`:
    def test_bound(self) -> None:
        """`bound` closes up, with chords for corners turning inward."""
        poly: SCRoundedPolygon
        for poly in (square(20.0, 5.0), notched()):
            lines: tuple[SCLine, ...] = poly.bound
            for index, line in enumerate(lines):
                self.assertEqual(
                    line.end, lines[(index + 1) % len(lines)].start
                )
        self.assertEqual(len(square(20.0, 5.0).bound), 4)
        self.assertEqual(len(notched().bound), 8)

        # A circle's bound is its square; used up edges are dropped.
        self.assertEqual(
            len(SCRoundedPolygon.circle("C", 0, 0, 1, 0.0, 1.0).bound), 4
        )

    # Method `TestLineEnters.test_crossing_bound()`:
    def test_crossing_bound(self) -> None:
        """No `bound` is used when its lines cross, and answers hold."""
        poly: SCRoundedPolygon = tip_over_strip()
        self.assertEqual(poly.bound, ())

        # In the strip, under where the sharp tip would be.
        self.assertTrue(poly.enters(SCLine((72.0, 0.0), (73.0, 0.0))))

        # Beyond the rounded wedge, under where the sharp tip would be.
        self.assertFalse(poly.enters(SCLine((60.0, 0.0), (65.0, 0.0))))

    # Method `TestLineEnters.test_circle()`:
    def test_circle(self) -> None:
        """A circle: its square's corners are clear."""
        poly: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 3.0, 4.0, 2.0, 0.0, 1.0
        )
        self.check(poly, (1.1, 2.1), (1.4, 2.1), False)
        self.check(poly, (0.0, 2.0), (6.0, 2.0), False)
        self.check(poly, (0.0, 4.0), (6.0, 4.0), True)
        self.check(poly, (3.0, 4.0), (3.5, 4.0), True)
        self.check(poly, (0.0, 2.01), (6.0, 2.01), True)

    # Method `TestLineEnters.test_point()`:
    def test_point(self) -> None:
        """A line with no length is a point, as for a vertical move."""
        poly: SCRoundedPolygon = square(20.0, 0.0)
        self.check(poly, (10.0, 10.0), (10.0, 10.0), True)
        self.check(poly, (0.0, 10.0), (0.0, 10.0), False)
        self.check(poly, (200.0, 20.0), (200.0, 20.0), False)

    # Method `TestLineEnters.test_against_sampling()`:
    def test_against_sampling(self) -> None:
        """Random lines agree with walking along them."""
        generator: random.Random = random.Random(4)
        poly: SCRoundedPolygon
        for poly in (
            square(20.0, 5.0),
            notched(),
            tip_over_strip(),
            plate_with_island(),
            SCRoundedPolygon.circle("C", 3.0, 4.0, 2.0, 0.0, 1.0),
        ):
            xs: list[float] = [corner.x for corner in poly.corners]
            ys: list[float] = [corner.y for corner in poly.corners]
            for _ in range(200):
                start: tuple[float, float] = (
                    generator.uniform(min(xs) - 5.0, max(xs) + 5.0),
                    generator.uniform(min(ys) - 5.0, max(ys) + 5.0),
                )
                end: tuple[float, float] = (
                    generator.uniform(min(xs) - 5.0, max(xs) + 5.0),
                    generator.uniform(min(ys) - 5.0, max(ys) + 5.0),
                )

                # A walk can miss a short visit, so only finding solid
                # decides; `bound` must never change the answer.
                line: SCLine = SCLine(start, end)
                found: bool = any(
                    poly.enters(
                        SCLine(
                            point_at(line, step / 100.0),
                            point_at(line, step / 100.0),
                        )
                    )
                    for step in range(101)
                )
                entered: bool = poly.enters(line)
                if found:
                    self.assertTrue(entered, (poly.name, start, end))
                bound: tuple[SCLine, ...] = poly.bound
                poly.bound = ()
                self.assertEqual(
                    poly.enters(line), entered, (poly.name, start, end)
                )
                poly.bound = bound

    # Method `TestLineEnters.test_against_formulas()`:
    def test_against_formulas(self) -> None:
        """Random lines agree with formulas that use no `geometry`."""

        generator: random.Random = random.Random(5)
        for poly, past in (
            (square(20.0, 5.0), past_square),
            (
                SCRoundedPolygon.circle("C", 10.0, 10.0, 7.0, 0.0, 1.0),
                past_circle,
            ),
        ):
            answers: list[bool] = []
            for _ in range(500):
                ends: list[float] = [
                    generator.uniform(-5.0, 25.0) for _ in range(4)
                ]
                nearest: float = min(
                    past(
                        ends[0] + (ends[2] - ends[0]) * step / 2000.0,
                        ends[1] + (ends[3] - ends[1]) * step / 2000.0,
                    )
                    for step in range(2001)
                )

                # Steps are about 0.02, so this far away is clear.
                entered: bool = poly.enters(
                    SCLine((ends[0], ends[1]), (ends[2], ends[3]))
                )
                answers.append(entered)
                if nearest < 0.0:
                    self.assertTrue(entered, ends)
                elif nearest > 0.001:
                    self.assertFalse(entered, ends)

            # Both answers really came up.
            self.assertGreater(answers.count(True), 50)
            self.assertGreater(answers.count(False), 50)


# Class `TestArcEnters`:
class TestArcEnters(unittest.TestCase):
    """Whether an arc enters an `SCRoundedPolygon`."""

    # Method `TestArcEnters.check()`:
    def check(
        self, poly: SCRoundedPolygon, arc: SCArc, expected: bool
    ) -> None:
        """Check an arc, going each way, with and without `bound`.

        Arguments:
        * `poly` (`SCRoundedPolygon`): The polygon.
        * `arc` (`SCArc`): The arc.
        * `expected` (`bool`): True when the arc should enter.
        """
        bound: tuple[SCLine, ...] = poly.bound
        for poly.bound in (bound, ()):
            self.assertEqual(poly.enters(arc), expected, arc)
            self.assertEqual(poly.enters(reverse_segment(arc)), expected, arc)
        poly.bound = bound

    # Method `TestArcEnters.test_which_way_around()`:
    def test_which_way_around(self) -> None:
        """With the same ends and center, only the bulge decides."""
        poly: SCRoundedPolygon = square(20.0, 5.0)

        # From (-3, 5) to (-3, 15), both out: into the square, or away.
        self.check(poly, arc_at((-3.0, 10.0), 5.0, -90.0, 180.0), True)
        self.check(poly, arc_at((-3.0, 10.0), 5.0, -90.0, -180.0), False)

        # The straight line between those ends is clear.
        self.assertFalse(poly.enters(SCLine((-3.0, 5.0), (-3.0, 15.0))))

    # Method `TestArcEnters.test_ends_and_inside()`:
    def test_ends_and_inside(self) -> None:
        """Arcs starting in, ending in, and wholly in."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.check(poly, arc_at((-3.0, 10.0), 5.0, -30.0, 30.0), True)
        self.check(poly, arc_at((10.0, 10.0), 3.0, 0.0, 90.0), True)
        self.check(poly, arc_at((10.0, 10.0), 3.0, 0.0, 360.0), True)

    # Method `TestArcEnters.test_whole_circles()`:
    def test_whole_circles(self) -> None:
        """A whole turn around, through or inside a polygon."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.check(poly, arc_at((10.0, 10.0), 30.0, 0.0, 360.0), False)
        self.check(poly, arc_at((10.0, 10.0), 12.0, 0.0, 360.0), True)
        self.check(poly, arc_at((40.0, 10.0), 5.0, 0.0, 360.0), False)
        self.check(poly, arc_at((10.0, 10.0), 12.0, 0.0, -360.0), True)

    # Method `TestArcEnters.test_rounded_corner()`:
    def test_rounded_corner(self) -> None:
        """Where the sharp corner would be, the rounded one is clear."""
        poly: SCRoundedPolygon = square(20.0, 5.0)

        # In the piece that rounding took away, across the sharp corner.
        self.check(poly, arc_at((0.0, 0.0), 2.0, 0.0, 90.0), False)
        self.check(poly, arc_at((0.0, 0.0), 2.0, -45.0, 180.0), False)

        # Bigger, it reaches the arc: the rounded corner is 2.07 away.
        self.check(poly, arc_at((0.0, 0.0), 2.1, 0.0, 90.0), True)

        # Outside, and just touching the corner's arc, then past it.
        apart: float = 5.0 - 7.0 / math.sqrt(2.0)
        center: tuple[float, float] = (apart, apart)
        self.check(poly, arc_at(center, 2.0, 0.0, 360.0), False)
        self.check(poly, arc_at(center, 2.01, 0.0, 360.0), True)

    # Method `TestArcEnters.test_touching()`:
    def test_touching(self) -> None:
        """Touching, or running along, an edge or a corner is clear."""
        poly: SCRoundedPolygon = square(20.0, 5.0)

        # Tangent to the edge X = 0 from outside, then past it.
        self.check(poly, arc_at((-3.0, 10.0), 3.0, -90.0, 180.0), False)
        self.check(poly, arc_at((-3.0, 10.0), 3.01, -90.0, 180.0), True)

        # Along the corner's own arc; carrying on along its circle goes
        # into the square.
        self.check(poly, arc_at((5.0, 5.0), 5.0, 180.0, 90.0), False)
        self.check(poly, arc_at((5.0, 5.0), 5.0, 200.0, 40.0), False)
        self.check(poly, arc_at((5.0, 5.0), 5.0, 180.0, 180.0), True)

        # Ending exactly on the edge from outside.
        self.check(poly, arc_at((-3.0, 10.0), 3.0, 0.0, 90.0), False)

    # Method `TestArcEnters.test_inward_corner()`:
    def test_inward_corner(self) -> None:
        """A corner turning inward gains what rounding adds."""
        poly: SCRoundedPolygon = notched()
        sharp: SCRoundedPolygon = SCRoundedPolygon(
            "Sharp", [SCCorner(c.x, c.y) for c in poly.corners], 0.0, 1.0
        )

        # About the sharp corner at (40, 30), up in the notch.  It is
        # in the fill, though out of the sharp shape.
        arc: SCArc = arc_at((40.0, 30.0), 0.7, 180.0, -90.0)
        self.check(sharp, arc, False)
        self.check(poly, arc, True)

        # In the notch, clear of the fill.
        self.check(poly, arc_at((30.0, 40.0), 3.0, 0.0, 360.0), False)

    # Method `TestArcEnters.test_circle()`:
    def test_circle(self) -> None:
        """Arcs against a circle, including one of its own circle."""
        poly: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 3.0, 4.0, 2.0, 0.0, 1.0
        )
        self.check(poly, arc_at((3.0, 4.0), 2.0, 0.0, 360.0), False)
        self.check(poly, arc_at((3.0, 4.0), 2.0, 30.0, 200.0), False)
        self.check(poly, arc_at((3.0, 4.0), 1.0, 0.0, 360.0), True)
        self.check(poly, arc_at((3.0, 4.0), 3.0, 0.0, 360.0), False)
        self.check(poly, arc_at((6.0, 4.0), 1.0, 0.0, 360.0), False)
        self.check(poly, arc_at((6.0, 4.0), 1.1, 0.0, 360.0), True)

    # Method `TestArcEnters.test_no_length()`:
    def test_no_length(self) -> None:
        """An arc with no sweep is a point."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.check(poly, arc_at((10.0, 10.0), 3.0, 0.0, 0.0), True)
        self.check(poly, arc_at((30.0, 10.0), 3.0, 0.0, 0.0), False)

    # Method `TestArcEnters.test_too_far_around()`:
    def test_too_far_around(self) -> None:
        """An arc of over one turn is refused, not half checked."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        with self.assertRaisesRegex(ValueError, "over one turn"):
            poly.enters(arc_at((10.0, 10.0), 3.0, 0.0, 400.0))

    # Method `TestArcEnters.test_against_formulas()`:
    def test_against_formulas(self) -> None:
        """Random arcs agree with formulas that use no `geometry`."""
        generator: random.Random = random.Random(6)
        for poly, past in (
            (square(20.0, 5.0), past_square),
            (
                SCRoundedPolygon.circle("C", 10.0, 10.0, 7.0, 0.0, 1.0),
                past_circle,
            ),
        ):
            answers: list[bool] = []
            for _ in range(500):
                center: tuple[float, float] = (
                    generator.uniform(-5.0, 25.0),
                    generator.uniform(-5.0, 25.0),
                )
                radius: float = generator.uniform(0.5, 15.0)
                start: float = generator.uniform(-180.0, 180.0)
                sweep: float = generator.uniform(-360.0, 360.0)
                nearest: float = min(
                    past(
                        center[0]
                        + radius
                        * math.cos(
                            math.radians(start + sweep * step / 2000.0)
                        ),
                        center[1]
                        + radius
                        * math.sin(
                            math.radians(start + sweep * step / 2000.0)
                        ),
                    )
                    for step in range(2001)
                )

                # Steps are at most about 0.05, so this far is clear.
                entered: bool = poly.enters(
                    arc_at(center, radius, start, sweep)
                )
                answers.append(entered)
                if nearest < 0.0:
                    self.assertTrue(entered, (center, radius, start, sweep))
                elif nearest > 0.01:
                    self.assertFalse(entered, (center, radius, start, sweep))

            # Both answers really came up.
            self.assertGreater(answers.count(True), 50)
            self.assertGreater(answers.count(False), 50)

    # Method `TestArcEnters.test_against_sampling()`:
    def test_against_sampling(self) -> None:
        """Random arcs agree with walking along them."""
        generator: random.Random = random.Random(7)
        poly: SCRoundedPolygon
        for poly in (
            notched(),
            tip_over_strip(),
            plate_with_island(),
        ):
            xs: list[float] = [corner.x for corner in poly.corners]
            ys: list[float] = [corner.y for corner in poly.corners]
            for _ in range(200):
                arc: SCArc = arc_at(
                    (
                        generator.uniform(min(xs), max(xs)),
                        generator.uniform(min(ys), max(ys)),
                    ),
                    generator.uniform(0.5, 40.0),
                    generator.uniform(-180.0, 180.0),
                    generator.uniform(-360.0, 360.0),
                )
                entered: bool = poly.enters(arc)
                found: bool = any(
                    poly.enters(
                        SCLine(
                            point_at(arc, step / 100.0),
                            point_at(arc, step / 100.0),
                        )
                    )
                    for step in range(101)
                )
                if found:
                    self.assertTrue(entered, (poly.name, arc))

                # `bound` must never change the answer.
                bound: tuple[SCLine, ...] = poly.bound
                poly.bound = ()
                self.assertEqual(poly.enters(arc), entered, (poly.name, arc))
                poly.bound = bound


# Function `slot_block()`:
def slot_block(width: float) -> SCRoundedPolygon:
    """Return a 20 x 20 block with a slot down from its top.

    Arguments:
    * `width` (`float`): The slot's width; it runs from X = 10 up.

    Returns:
    * (`SCRoundedPolygon`): The block; the slot's floor is at Y = 5.
    """
    return SCRoundedPolygon(
        "Slot",
        [
            SCCorner(0.0, 0.0),
            SCCorner(20.0, 0.0),
            SCCorner(20.0, 20.0),
            SCCorner(10.0 + width, 20.0),
            SCCorner(10.0 + width, 5.0),
            SCCorner(10.0, 5.0),
            SCCorner(10.0, 20.0),
            SCCorner(0.0, 20.0),
        ],
        0.0,
        1.0,
    )


# Function `star()`:
def star(generator: random.Random) -> SCRoundedPolygon | None:
    """Return a random star shaped polygon, with its corners rounded.

    Arguments:
    * `generator` (`random.Random`): Where the random numbers come from.

    Returns:
    * (`SCRoundedPolygon | None`):
      The polygon, or `None` when the corners' radii did not fit.
    """
    count: int = generator.randint(3, 12)
    corners: list[SCCorner] = []
    index: int
    for index in range(count):
        angle: float = 2.0 * math.pi * (index + generator.random() / 2) / count
        reach: float = generator.uniform(5.0, 30.0)
        corners.append(
            SCCorner(
                reach * math.cos(angle),
                reach * math.sin(angle),
                generator.choice((0.0, 0.0, 0.25, 1.0, 3.0)),
            )
        )
    try:
        return SCRoundedPolygon("Star", corners, 0.0, 1.0)
    except ValueError:
        return None


# Function `bounds_of()`:
def bounds_of(poly: SCRoundedPolygon) -> tuple[float, float, float, float]:
    """Return the box around a polygon's corners.

    Arguments:
    * `poly` (`SCRoundedPolygon`): The polygon.

    Returns:
    * (`tuple[float, float, float, float]`):
      Low X, high X, low Y, high Y.
    """
    xs: list[float] = [corner.x for corner in poly.corners]
    ys: list[float] = [corner.y for corner in poly.corners]
    return min(xs), max(xs), min(ys), max(ys)


# Function `plate_surface()`:
def plate_surface(x: float, y: float) -> float:
    """Return the height of `plate_with_island()`, by a plain formula.

    Arguments:
    * `x` (`float`): The X.
    * `y` (`float`): The Y.

    Returns:
    * (`float`): The height of the surface there, or `-inf` off of it.
    """
    if not 0.0 <= x <= 100.0 or not 0.0 <= y <= 100.0:
        return -math.inf
    if math.hypot(x - 10.0, y - 10.0) < 5.0:
        return 0.0
    if math.hypot(x - 60.0, y - 60.0) < 5.0:
        return 0.0
    if 50.0 <= x <= 70.0 and 50.0 <= y <= 70.0:
        return 10.0
    if 30.0 <= x <= 90.0 and 30.0 <= y <= 90.0:
        return 5.0
    return 10.0


# Function `tool_touches()`:
def tool_touches(line: SCLine, z: float, reach: float) -> bool:
    """Return whether a tool walked along a line finds `plate_surface()`.

    Arguments:
    * `line` (`SCLine`): The path of the tool's center.
    * `z` (`float`): The height of its tip.
    * `reach` (`float`): Its radius.

    Returns:
    * (`bool`): True when a point on or in its rim is below the surface.
    """
    steps: int = int(line.length() * 4) + 2
    step: int
    for step in range(steps + 1):
        center: tuple[float, float] = point_at(line, step / steps)
        turn: int
        for turn in range(24):
            angle: float = turn * math.pi / 12.0
            if (
                plate_surface(
                    center[0] + reach * math.cos(angle),
                    center[1] + reach * math.sin(angle),
                )
                > z
            ):
                return True
        if plate_surface(*center) > z:
            return True
    return False


# Class `TestGrown`:
class TestGrown(unittest.TestCase):
    """What `SCRoundedPolygon.grown()` keeps a tool's center out of."""

    # Method `TestGrown.test_square()`:
    def test_square(self) -> None:
        """Sharp corners come out rounded to the tool's radius."""
        moved: SCRoundedPolygon = square(20.0, 0.0).grown(1.0)
        reach: float = 1.0 + SLOP
        length: float = 4.0 * 20.0 + 2.0 * math.pi * reach
        self.assertAlmostEqual(SCLoop.from_poly(moved).length(), length)
        self.assertEqual(len(moved.segments), 8)
        self.assertTrue(moved.is_ccw())
        self.assertEqual(moved.name, "Square grown 1")

    # Method `TestGrown.test_circle()`:
    def test_circle(self) -> None:
        """A circle stays a circle, about the same center."""
        moved: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 3.0, 4.0, 2.0, 0.0, 1.0
        ).grown(1.0)
        segment: SCSegment
        for segment in moved.segments:
            assert isinstance(segment, SCArc)
            self.assertTrue(math.dist(segment.center, (3.0, 4.0)) < 1e-9)
            self.assertAlmostEqual(segment.radius, 3.0 + SLOP)

    # Method `TestGrown.test_zero_radius()`:
    def test_zero_radius(self) -> None:
        """A tool with no radius still gets the slop."""
        moved: SCRoundedPolygon = square(20.0, 0.0).grown(0.0)
        self.assertAlmostEqual(
            SCLoop.from_poly(moved).length(), 80.0 + 2.0 * math.pi * SLOP
        )

    # Method `TestGrown.test_bad_radius()`:
    def test_bad_radius(self) -> None:
        """A tool can not have a negative radius."""
        with self.assertRaisesRegex(ValueError, "negative"):
            square(20.0, 0.0).grown(-1.0)

    # Method `TestGrown.test_clockwise()`:
    def test_clockwise(self) -> None:
        """It grows the same either way around, and keeps the way."""
        forward: SCRoundedPolygon = square(20.0, 3.0).grown(1.0)
        backward: SCRoundedPolygon = square(20.0, 3.0, ccw=False).grown(1.0)
        self.assertTrue(forward.is_ccw())
        self.assertFalse(backward.is_ccw())
        self.assertAlmostEqual(
            SCLoop.from_poly(forward).length(),
            SCLoop.from_poly(backward).length(),
        )

    # Method `TestGrown.test_inward_corner()`:
    def test_inward_corner(self) -> None:
        """A corner turning inward loses radius, down to sharp."""
        moved: SCRoundedPolygon = notched().grown(1.0)
        radii: list[float] = [
            segment.radius
            for segment in moved.segments
            if isinstance(segment, SCArc) and segment.sweep < 0.0
        ]
        self.assertEqual(len(radii), 1)
        self.assertAlmostEqual(radii[0], 3.0 - SLOP)

        # With a bigger tool that arc is gone: the walls just meet.
        moved = notched().grown(5.0)
        self.assertFalse(
            [
                segment
                for segment in moved.segments
                if isinstance(segment, SCArc) and segment.sweep < 0.0
            ]
        )

    # Method `TestGrown.test_corner_matches_tool()`:
    def test_corner_matches_tool(self) -> None:
        """An inward corner of about the tool's radius builds."""
        radius: float
        for radius in (1.0 - 2.0 * SLOP, 1.0 - SLOP, 1.0, 1.0 + SLOP):
            bent: SCRoundedPolygon = SCRoundedPolygon(
                "Bent",
                [
                    SCCorner(0.0, 0.0),
                    SCCorner(30.0, 0.0),
                    SCCorner(30.0, 20.0),
                    SCCorner(15.0, 19.0, 1.0),
                    SCCorner(0.0, 20.0),
                ],
                0.0,
                1.0,
            )
            moved: SCRoundedPolygon = bent.grown(radius)
            self.assertEqual(moved.is_ccw(), bent.is_ccw())
            places: list[SCRoundedPolygon] = bent.shrunk(radius)
            self.assertEqual(len(places), 1)

    # Method `TestGrown.test_nearly_straight_corner()`:
    def test_nearly_straight_corner(self) -> None:
        """Corners that barely turn inward build, whatever the sizes."""
        built: int = 0
        sag: float
        for sag in (1.0, 0.1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7):
            corner: float
            for corner in (0.0, 0.25, 1.0, 3.0):
                # Too small an arc is refused, as ever: its neighbors
                # are within `TOUCH` of each other.
                try:
                    bent: SCRoundedPolygon = SCRoundedPolygon(
                        "Bent",
                        [
                            SCCorner(0.0, 0.0),
                            SCCorner(30.0, 0.0),
                            SCCorner(30.0, 20.0),
                            SCCorner(15.0, 20.0 - sag, corner),
                            SCCorner(0.0, 20.0),
                        ],
                        0.0,
                        1.0,
                    )
                except ValueError:
                    continue
                built += 1
                radius: float
                for radius in (0.1, 0.25, 1.0 - SLOP, 1.0, 1.0 + SLOP, 3.0):
                    self.assertTrue(bent.grown(radius).is_ccw())
                    self.assertEqual(len(bent.shrunk(radius)), 1)
        self.assertGreater(built, 20)

    # Method `TestGrown.test_slot_closes()`:
    def test_slot_closes(self) -> None:
        """A slot the tool does not fit leaves a corner of radius 0."""
        moved: SCRoundedPolygon = slot_block(1.0).grown(1.0)
        cusps: list[SCCorner] = [
            corner for corner in moved.corners if corner.radius == 0.0
        ]
        self.assertEqual(len(cusps), 1)
        self.assertAlmostEqual(cusps[0].x, 10.5)
        self.assertAlmostEqual(
            cusps[0].y, 20.0 + math.sqrt((1.0 + SLOP) ** 2 - 0.25)
        )

        # Above the cusp is clear; below it, into the old slot, is not.
        self.assertFalse(moved.enters(SCLine((10.5, 25.0), (10.5, 21.0))))
        self.assertTrue(moved.enters(SCLine((10.5, 25.0), (10.5, 20.0))))

    # Method `TestGrown.test_slot_widths()`:
    def test_slot_widths(self) -> None:
        """Every width near the tool's works, even at the slop's."""
        offset: float
        for offset in (0.0, 2.0 * SLOP):
            sign: float
            for sign in (-1.0, 1.0):
                near: float
                for near in (1e-3, 1e-5, 1e-6, 1e-7, 1e-9, 1e-12, 0.0):
                    width: float = 2.0 + offset + sign * near
                    moved: SCRoundedPolygon = slot_block(width).grown(1.0)
                    self.assertGreater(len(moved.corners), 3, width)

    # Method `TestGrown.test_slot_fit()`:
    def test_slot_fit(self) -> None:
        """Only a tool that fits can go down the slot."""
        self.assertFalse(
            slot_block(2.1)
            .grown(1.0)
            .enters(SCLine((11.05, 25.0), (11.05, 10.0)))
        )
        path: SCLine = SCLine((11.0, 25.0), (11.0, 10.0))
        self.assertTrue(slot_block(2.0).grown(1.0).enters(path))
        path = SCLine((10.95, 25.0), (10.95, 10.0))
        self.assertTrue(slot_block(1.9).grown(1.0).enters(path))

    # Method `TestGrown.test_cavity_closes()`:
    def test_cavity_closes(self) -> None:
        """A cavity behind a mouth too small for the tool is solid."""
        cavity: SCRoundedPolygon = SCRoundedPolygon(
            "Cavity",
            [
                SCCorner(0.0, 0.0),
                SCCorner(20.0, 0.0),
                SCCorner(20.0, 20.0),
                SCCorner(10.5, 20.0),
                SCCorner(10.5, 15.0),
                SCCorner(15.0, 15.0),
                SCCorner(15.0, 5.0),
                SCCorner(5.0, 5.0),
                SCCorner(5.0, 15.0),
                SCCorner(9.5, 15.0),
                SCCorner(9.5, 20.0),
                SCCorner(0.0, 20.0),
            ],
            0.0,
            1.0,
        )

        # In the middle of the cavity, the tool would really be clear.
        middle: tuple[float, float] = (10.0, 10.0)
        self.assertFalse(cavity.enters(SCLine(middle, middle)))
        self.assertTrue(cavity.grown(1.0).enters(SCLine(middle, middle)))

        # With a small enough tool, the mouth stays open.
        self.assertFalse(cavity.grown(0.25).enters(SCLine(middle, middle)))

    # Method `TestGrown.test_children_are_lost()`:
    def test_children_are_lost(self) -> None:
        """Children are gone, so their insides count as solid."""
        moved: SCRoundedPolygon = plate_with_island().grown(1.0)
        self.assertEqual(moved.children, ())
        self.assertEqual((moved.z_start, moved.z_end), (0.0, 10.0))
        center: tuple[float, float] = (10.0, 10.0)
        self.assertTrue(moved.enters(SCLine(center, center)))

    # Method `TestGrown.test_cusp_bound()`:
    def test_cusp_bound(self) -> None:
        """The quick test does not change answers on a closed slot."""
        generator: random.Random = random.Random(11)
        moved: SCRoundedPolygon = slot_block(1.0).grown(1.0)
        self.assertTrue(moved.bound)
        bound: tuple[SCLine, ...] = moved.bound
        for _ in range(300):
            line: SCLine = SCLine(
                (generator.uniform(-5.0, 25.0), generator.uniform(-5.0, 25.0)),
                (generator.uniform(-5.0, 25.0), generator.uniform(-5.0, 25.0)),
            )
            arc: SCArc = arc_at(
                (generator.uniform(0.0, 20.0), generator.uniform(15.0, 25.0)),
                generator.uniform(0.2, 5.0),
                generator.uniform(-180.0, 180.0),
                generator.uniform(-360.0, 360.0),
            )
            for move in (line, arc):
                moved.bound = bound
                answer: bool = moved.enters(move)
                moved.bound = ()
                self.assertEqual(moved.enters(move), answer, move)

    # Method `TestGrown.check_points()`:
    def check_points(
        self,
        poly: SCRoundedPolygon,
        radius: float,
        generator: random.Random,
    ) -> None:
        """Check `grown()` against the distance to the original outline.

        A point well outside the grown outline must be farther than the
        tool's radius from the polygon.  A point within the radius must
        be inside it.  The reverse of the first does not hold where a
        void or slot closed up, which only adds to what is solid.

        Arguments:
        * `poly` (`SCRoundedPolygon`): The polygon.
        * `radius` (`float`): The tool's radius.
        * `generator` (`random.Random`): The random numbers.
        """
        moved: SCRoundedPolygon = poly.grown(radius)
        loop: SCLoop = SCLoop.from_poly(poly)
        low_x, high_x, low_y, high_y = bounds_of(poly)
        reach: float = radius + 2.0
        for _ in range(150):
            point: tuple[float, float] = (
                generator.uniform(low_x - reach, high_x + reach),
                generator.uniform(low_y - reach, high_y + reach),
            )
            apart: float = 0.0
            if not loop.contains(point):
                apart = loop.distance(point)
            if abs(apart - radius) < 2.0 * SLOP:
                continue
            entered: bool = moved.enters(SCLine(point, point))
            if apart < radius:
                self.assertTrue(entered, (poly.corners, radius, point))
            if not entered:
                self.assertGreater(
                    apart, radius, (poly.corners, radius, point)
                )

    # Method `TestGrown.test_against_distance()`:
    def test_against_distance(self) -> None:
        """Fixed shapes agree with the distance to the original."""
        generator: random.Random = random.Random(12)
        poly: SCRoundedPolygon
        for poly in (
            square(20.0, 0.0),
            square(20.0, 5.0),
            notched(),
            tip_over_strip(),
            plate_with_island(),
            slot_block(1.0),
            slot_block(2.0),
            slot_block(3.0),
            SCRoundedPolygon.circle("C", 3.0, 4.0, 2.0, 0.0, 1.0),
        ):
            radius: float
            for radius in (0.0, 0.25, 1.0, 3.0, 12.0):
                self.check_points(poly, radius, generator)

    # Method `TestGrown.test_random_stars()`:
    def test_random_stars(self) -> None:
        """Random shapes all build, and agree with the distance."""
        generator: random.Random = random.Random(13)
        built: int = 0
        for _ in range(300):
            poly: SCRoundedPolygon | None = star(generator)
            if poly is None:
                continue
            built += 1
            self.check_points(
                poly, generator.choice((0.1, 0.5, 1.0, 2.5, 8.0)), generator
            )
        self.assertGreater(built, 100)

    # Method `TestGrown.test_tool_along_a_move()`:
    def test_tool_along_a_move(self) -> None:
        """Random moves agree with walking a tool along them."""
        generator: random.Random = random.Random(14)
        radius: float = 1.5
        poly: SCRoundedPolygon = notched()
        loop: SCLoop = SCLoop.from_poly(poly)
        moved: SCRoundedPolygon = poly.grown(radius)
        answers: list[bool] = []
        for _ in range(150):
            start: tuple[float, float] = (
                generator.uniform(-10.0, 90.0),
                generator.uniform(-10.0, 60.0),
            )
            move: SCSegment = SCLine(
                start,
                (
                    generator.uniform(-10.0, 90.0),
                    generator.uniform(-10.0, 60.0),
                ),
            )
            if generator.random() < 0.5:
                move = arc_at(
                    start,
                    generator.uniform(0.5, 30.0),
                    generator.uniform(-180.0, 180.0),
                    generator.uniform(-360.0, 360.0),
                )
            nearest: float = math.inf
            for step in range(301):
                point: tuple[float, float] = point_at(move, step / 300.0)
                nearest = min(
                    nearest,
                    0.0 if loop.contains(point) else loop.distance(point),
                )
            answer: bool = moved.enters(move)
            answers.append(answer)
            if nearest < radius:
                self.assertTrue(answer, move)
            elif nearest > radius + 0.05:
                self.assertFalse(answer, move)
        self.assertGreater(answers.count(True), 20)
        self.assertGreater(answers.count(False), 20)


# Class `TestShrunk`:
class TestShrunk(unittest.TestCase):
    """Where `SCRoundedPolygon.shrunk()` lets a tool's center go."""

    # Method `TestShrunk.test_square()`:
    def test_square(self) -> None:
        """A sharp square shrinks to a smaller sharp square."""
        places: list[SCRoundedPolygon] = square(20.0, 0.0).shrunk(1.0)
        self.assertEqual(len(places), 1)
        self.assertAlmostEqual(
            SCLoop.from_poly(places[0]).length(),
            4.0 * (18.0 - 2.0 * SLOP),
        )
        self.assertTrue(places[0].is_ccw())

    # Method `TestShrunk.test_circle()`:
    def test_circle(self) -> None:
        """A circle shrinks about its center, until no tool fits."""
        poly: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 3.0, 4.0, 2.0, 0.0, 1.0
        )
        places: list[SCRoundedPolygon] = poly.shrunk(1.0)
        self.assertEqual(len(places), 1)
        segment: SCSegment
        for segment in places[0].segments:
            assert isinstance(segment, SCArc)
            self.assertTrue(math.dist(segment.center, (3.0, 4.0)) < 1e-9)
            self.assertAlmostEqual(segment.radius, 1.0 - SLOP)
        self.assertEqual(poly.shrunk(2.0), [])
        self.assertEqual(poly.shrunk(3.0), [])

    # Method `TestShrunk.test_clockwise()`:
    def test_clockwise(self) -> None:
        """A clockwise outline shrinks inward just the same."""
        places: list[SCRoundedPolygon] = square(20.0, 3.0, ccw=False).shrunk(
            1.0
        )
        self.assertEqual(len(places), 1)
        self.assertTrue(places[0].is_ccw())
        self.assertLess(
            SCLoop.from_poly(places[0]).length(),
            SCLoop.from_poly(square(20.0, 3.0)).length(),
        )

    # Method `TestShrunk.test_bad_radius()`:
    def test_bad_radius(self) -> None:
        """A tool can not have a negative radius."""
        with self.assertRaisesRegex(ValueError, "negative"):
            square(20.0, 0.0).shrunk(-1.0)

    # Method `TestShrunk.test_neck_splits()`:
    def test_neck_splits(self) -> None:
        """A neck too narrow for the tool makes two separate places."""
        rooms: SCRoundedPolygon = SCRoundedPolygon(
            "Dumbbell",
            [
                SCCorner(0.0, 0.0),
                SCCorner(20.0, 0.0),
                SCCorner(20.0, 9.0),
                SCCorner(30.0, 9.0),
                SCCorner(30.0, 0.0),
                SCCorner(50.0, 0.0),
                SCCorner(50.0, 20.0),
                SCCorner(30.0, 20.0),
                SCCorner(30.0, 11.0),
                SCCorner(20.0, 11.0),
                SCCorner(20.0, 20.0),
                SCCorner(0.0, 20.0),
            ],
            0.0,
            1.0,
        )
        self.assertEqual(len(rooms.shrunk(0.5)), 1)
        places: list[SCRoundedPolygon] = rooms.shrunk(1.5)
        self.assertEqual(len(places), 2)

        # Each place holds its own end, and a move across leaves both.
        across: SCLine = SCLine((10.0, 10.0), (40.0, 10.0))
        self.assertTrue(all(place.leaves(across) for place in places))
        for point in ((10.0, 10.0), (40.0, 10.0)):
            self.assertEqual(
                sum(
                    not place.leaves(SCLine(point, point)) for place in places
                ),
                1,
            )

    # Method `TestShrunk.test_neck_widths()`:
    def test_neck_widths(self) -> None:
        """A neck about the tool's width splits or not, but works."""
        offset: float
        for offset in (0.0, 2.0 * SLOP):
            sign: float
            for sign in (-1.0, 1.0):
                near: float
                for near in (1e-3, 1e-5, 1e-6, 1e-7, 1e-9, 0.0):
                    half: float = 1.0 + offset / 2.0 + sign * near / 2.0
                    neck: SCRoundedPolygon = SCRoundedPolygon(
                        "Neck",
                        [
                            SCCorner(0.0, 0.0),
                            SCCorner(20.0, 0.0),
                            SCCorner(20.0, 10.0 - half),
                            SCCorner(30.0, 10.0 - half),
                            SCCorner(30.0, 0.0),
                            SCCorner(50.0, 0.0),
                            SCCorner(50.0, 20.0),
                            SCCorner(30.0, 20.0),
                            SCCorner(30.0, 10.0 + half),
                            SCCorner(20.0, 10.0 + half),
                            SCCorner(20.0, 20.0),
                            SCCorner(0.0, 20.0),
                        ],
                        0.0,
                        1.0,
                    )
                    self.assertIn(len(neck.shrunk(1.0)), (1, 2), half)

    # Method `TestShrunk.test_against_distance()`:
    def test_against_distance(self) -> None:
        """Random shapes agree with the distance to the original."""
        generator: random.Random = random.Random(15)
        built: int = 0
        polys: list[SCRoundedPolygon | None] = [
            notched(),
            square(20.0, 5.0),
            SCRoundedPolygon.circle("C", 0.0, 0.0, 9.0, 0.0, 1.0),
        ]
        polys += [star(generator) for _ in range(200)]
        poly: SCRoundedPolygon | None
        for poly in polys:
            if poly is None:
                continue
            built += 1
            radius: float = generator.choice((0.1, 0.5, 1.0, 2.5))
            places: list[SCRoundedPolygon] = poly.shrunk(radius)
            loop: SCLoop = SCLoop.from_poly(poly)
            low_x, high_x, low_y, high_y = bounds_of(poly)
            for _ in range(100):
                point: tuple[float, float] = (
                    generator.uniform(low_x, high_x),
                    generator.uniform(low_y, high_y),
                )
                apart: float = loop.distance(point)
                if abs(apart - radius) < 2.0 * SLOP:
                    continue
                allowed: bool = loop.contains(point) and apart > radius
                self.assertEqual(
                    any(
                        not place.leaves(SCLine(point, point))
                        for place in places
                    ),
                    allowed,
                    (poly.corners, radius, point),
                )
        self.assertGreater(built, 100)


# Class `TestLeaves`:
class TestLeaves(unittest.TestCase):
    """Whether a move leaves an `SCRoundedPolygon`."""

    # Method `TestLeaves.test_lines()`:
    def test_lines(self) -> None:
        """Lines staying in, going out, and starting out."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.assertFalse(poly.leaves(SCLine((5.0, 5.0), (15.0, 15.0))))
        self.assertTrue(poly.leaves(SCLine((5.0, 5.0), (25.0, 5.0))))
        self.assertTrue(poly.leaves(SCLine((25.0, 5.0), (5.0, 5.0))))
        self.assertTrue(poly.leaves(SCLine((25.0, 5.0), (30.0, 5.0))))

    # Method `TestLeaves.test_touching()`:
    def test_touching(self) -> None:
        """Touching or following the outline stays in."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.assertFalse(poly.leaves(SCLine((10.0, 10.0), (10.0, 0.0))))
        self.assertFalse(poly.leaves(SCLine((5.0, 0.0), (15.0, 0.0))))
        self.assertFalse(poly.leaves(arc_at((5.0, 5.0), 5.0, 180.0, 90.0)))

    # Method `TestLeaves.test_rounded_corner()`:
    def test_rounded_corner(self) -> None:
        """Where the sharp corner would be is out of the rounded one."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.assertTrue(poly.leaves(SCLine((0.2, 0.2), (0.5, 0.2))))
        self.assertFalse(
            square(20.0, 0.0).leaves(SCLine((0.2, 0.2), (0.5, 0.2)))
        )

    # Method `TestLeaves.test_out_and_back()`:
    def test_out_and_back(self) -> None:
        """Both ends can be inside, with the middle out."""
        poly: SCRoundedPolygon = notched()

        # Across the notch from one side to the other.
        self.assertTrue(poly.leaves(SCLine((10.0, 45.0), (60.0, 45.0))))

        # An arc bulging out of a square, or staying in.
        block: SCRoundedPolygon = square(20.0, 0.0)
        self.assertTrue(block.leaves(arc_at((18.0, 10.0), 5.0, -60.0, 120.0)))
        self.assertFalse(block.leaves(arc_at((10.0, 10.0), 5.0, 0.0, 360.0)))
        self.assertFalse(block.leaves(arc_at((10.0, 10.0), 5.0, 0.0, -360.0)))

    # Method `TestLeaves.test_point_and_turns()`:
    def test_point_and_turns(self) -> None:
        """A point works, and an arc over one turn is refused."""
        poly: SCRoundedPolygon = square(20.0, 5.0)
        self.assertFalse(poly.leaves(SCLine((10.0, 10.0), (10.0, 10.0))))
        self.assertTrue(poly.leaves(SCLine((30.0, 10.0), (30.0, 10.0))))
        with self.assertRaisesRegex(ValueError, "over one turn"):
            poly.leaves(arc_at((10.0, 10.0), 3.0, 0.0, 400.0))

    # Method `TestLeaves.test_against_formulas()`:
    def test_against_formulas(self) -> None:
        """Random moves agree with formulas that use no `geometry`."""
        generator: random.Random = random.Random(16)
        poly: SCRoundedPolygon = square(20.0, 5.0)
        answers: list[bool] = []
        for _ in range(300):
            start: tuple[float, float] = (
                generator.uniform(0.0, 20.0),
                generator.uniform(0.0, 20.0),
            )
            move: SCSegment = SCLine(
                start,
                (generator.uniform(0.0, 20.0), generator.uniform(0.0, 20.0)),
            )
            if generator.random() < 0.5:
                move = arc_at(
                    start,
                    generator.uniform(0.5, 10.0),
                    generator.uniform(-180.0, 180.0),
                    generator.uniform(-360.0, 360.0),
                )
            farthest: float = max(
                past_square(*point_at(move, step / 1000.0))
                for step in range(1001)
            )
            answer: bool = poly.leaves(move)
            answers.append(answer)
            if farthest > 0.0:
                self.assertTrue(answer, move)
            elif farthest < -0.01:
                self.assertFalse(answer, move)
        self.assertGreater(answers.count(True), 30)
        self.assertGreater(answers.count(False), 30)


# Class `TestLoopPolygon`:
class TestLoopPolygon(unittest.TestCase):
    """`SCLoop.polygon()`, which turns a loop back into corners."""

    # Method `TestLoopPolygon.test_round_trip()`:
    def test_round_trip(self) -> None:
        """A polygon's own loop comes back as the same outline."""
        poly: SCRoundedPolygon
        for poly in (
            notched(),
            square(20.0, 5.0),
            square(20.0, 5.0, ccw=False),
            SCRoundedPolygon.circle("C", 1.1, -2.3, 0.37, 0.0, 1.0),
        ):
            loop: SCLoop = SCLoop.from_poly(poly)
            again: SCRoundedPolygon = loop.polygon("Again", 0.0, 1.0)
            self.assertEqual(again.name, "Again")
            self.assertEqual(again.is_ccw(), poly.is_ccw())
            self.assertAlmostEqual(
                SCLoop.from_poly(again).length(), loop.length()
            )
            self.assertAlmostEqual(
                SCLoop.from_poly(again).signed_area(), loop.signed_area()
            )

    # Method `TestLoopPolygon.test_backtrack()`:
    def test_backtrack(self) -> None:
        """A line going back over its neighbors is dropped."""
        loop: SCLoop = SCLoop(
            "Z",
            (
                SCLine((0.0, 0.0), (10.0, 0.0)),
                SCLine((10.0, 0.0), (10.0, 5.001)),
                SCLine((10.0, 5.001), (10.0, 5.0)),
                SCLine((10.0, 5.0), (10.0, 10.0)),
                SCLine((10.0, 10.0), (0.0, 10.0)),
                SCLine((0.0, 10.0), (0.0, 0.0)),
            ),
        )
        poly: SCRoundedPolygon = loop.polygon("Z", 0.0, 1.0)
        self.assertEqual(len(poly.corners), 4)
        self.assertAlmostEqual(
            SCLoop.from_poly(poly).signed_area(), 100.0, delta=0.01
        )

    # Method `TestLoopPolygon.test_kept()`:
    def test_kept(self) -> None:
        """A short real feature, wider than the slop, stays."""
        loop: SCLoop = SCLoop(
            "Step",
            (
                SCLine((0.0, 0.0), (10.0, 0.0)),
                SCLine((10.0, 0.0), (10.0, 5.0)),
                SCLine((10.0, 5.0), (10.002, 5.0)),
                SCLine((10.002, 5.0), (10.002, 10.0)),
                SCLine((10.002, 10.0), (0.0, 10.0)),
                SCLine((0.0, 10.0), (0.0, 0.0)),
            ),
        )
        self.assertEqual(len(loop.polygon("Step", 0.0, 1.0).corners), 6)

    # Method `TestLoopPolygon.test_tiny()`:
    def test_tiny(self) -> None:
        """A segment shorter than the slop is dropped."""
        loop: SCLoop = SCLoop(
            "Tiny",
            (
                SCLine((0.0, 0.0), (10.0, 0.0)),
                SCLine((10.0, 0.0), (10.0, 10.0)),
                SCLine((10.0, 10.0), (10.0 - SLOP / 2.0, 10.0)),
                SCLine((10.0 - SLOP / 2.0, 10.0), (0.0, 10.0)),
                SCLine((0.0, 10.0), (0.0, 0.0)),
            ),
        )
        self.assertEqual(len(loop.polygon("Tiny", 0.0, 1.0).corners), 4)

    # Method `TestLoopPolygon.test_near_fit()`:
    def test_near_fit(self) -> None:
        """Arcs that about use up an edge leave no line, and join up."""
        reach: float
        for reach in (5.0 - 2e-7, 5.0, 5.0 + 2e-7):
            poly: SCRoundedPolygon = square(10.0, reach)
            self.assertEqual(len(poly.segments), 4)
            index: int
            segment: SCSegment
            for index, segment in enumerate(poly.segments):
                following: SCSegment = poly.segments[(index + 1) % 4]
                self.assertEqual(segment.end, following.start)
        with self.assertRaisesRegex(ValueError, "of an edge"):
            square(10.0, 5.001)

    # Method `TestLoopPolygon.test_cusp()`:
    def test_cusp(self) -> None:
        """Two arcs meeting at an angle are three corners."""
        # The whole outline: a box with a cusp in its top.
        moved: SCRoundedPolygon = slot_block(1.0).grown(1.0)
        self.assertEqual(
            [corner.radius for corner in moved.corners].count(0.0), 1
        )
        rebuilt: SCRoundedPolygon = SCLoop.from_poly(moved).polygon(
            "Again", 0.0, 1.0
        )
        self.assertEqual(
            [corner.radius for corner in rebuilt.corners].count(0.0), 1
        )
        self.assertAlmostEqual(
            SCLoop.from_poly(rebuilt).length(),
            SCLoop.from_poly(moved).length(),
        )


# Class `TestSCRoundedPolygon`:
class TestSCRoundedPolygon(unittest.TestCase):
    """The outline that `SCRoundedPolygon` computes."""

    # Method `TestSCRoundedPolygon.check_outline()`:
    def check_outline(self, poly: SCRoundedPolygon) -> None:
        """Check that an outline is closed and its arcs are true.

        Arguments:
        * `poly` (`SCRoundedPolygon`): The polygon to check.
        """
        segments: tuple[SCSegment, ...] = poly.segments
        index: int
        segment: SCSegment
        for index, segment in enumerate(segments):
            following: SCSegment = segments[(index + 1) % len(segments)]
            self.assertTrue(close(segment.end, following.start))
            if isinstance(segment, SCArc):
                self.assertAlmostEqual(
                    math.dist(segment.center, segment.start), segment.radius
                )
                self.assertAlmostEqual(
                    math.dist(segment.center, segment.end), segment.radius
                )

    # Method `TestSCRoundedPolygon.test_square_ccw()`:
    def test_square_ccw(self) -> None:
        """A rounded square: 4 lines and 4 counter-clockwise arcs."""
        poly: SCRoundedPolygon = square(20.0, 3.0)
        self.check_outline(poly)
        self.assertTrue(poly.is_ccw())
        self.assertAlmostEqual(poly.signed_area, 400.0)
        kinds: list[type] = [type(segment) for segment in poly.segments]
        self.assertEqual(kinds, [SCLine, SCArc] * 4)

        # The outline starts on the edge leaving the first corner.
        self.assertTrue(close(poly.segments[0].start, (3.0, 0.0)))
        self.assertTrue(close(poly.segments[0].end, (17.0, 0.0)))
        arc: SCSegment = poly.segments[1]
        assert isinstance(arc, SCArc)
        self.assertTrue(close(arc.center, (17.0, 3.0)))
        self.assertAlmostEqual(arc.sweep, math.pi / 2)

        # Its length is the straight parts plus one whole circle.
        length: float = sum(segment.length() for segment in poly.segments)
        self.assertAlmostEqual(length, 4 * 14.0 + 2 * math.pi * 3.0)

    # Method `TestSCRoundedPolygon.test_square_cw()`:
    def test_square_cw(self) -> None:
        """Going clockwise, every arc is clockwise."""
        poly: SCRoundedPolygon = square(20.0, 3.0, ccw=False)
        self.check_outline(poly)
        self.assertFalse(poly.is_ccw())
        sweeps: list[float] = [
            segment.sweep
            for segment in poly.segments
            if isinstance(segment, SCArc)
        ]
        self.assertEqual(len(sweeps), 4)
        for sweep in sweeps:
            self.assertAlmostEqual(sweep, -math.pi / 2)

    # Method `TestSCRoundedPolygon.test_sharp()`:
    def test_sharp(self) -> None:
        """Sharp corners give just the polygon's edges."""
        poly: SCRoundedPolygon = square(10.0, 0.0)
        self.check_outline(poly)
        self.assertTrue(
            all(isinstance(segment, SCLine) for segment in poly.segments)
        )
        self.assertEqual(len(poly.segments), 4)

    # Method `TestSCRoundedPolygon.test_circle()`:
    def test_circle(self) -> None:
        """Arcs that use up every edge leave no lines: a circle."""
        poly: SCRoundedPolygon = square(10.0, 5.0)
        self.check_outline(poly)
        self.assertEqual(len(poly.segments), 4)
        self.assertTrue(
            all(isinstance(segment, SCArc) for segment in poly.segments)
        )

    # Method `TestSCRoundedPolygon.test_circle_method()`:
    def test_circle_method(self) -> None:
        """`circle()` is four quarter arcs around the given center."""
        poly: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 1.1, -2.3, 0.37, 0.0, 1.0
        )
        self.check_outline(poly)
        self.assertEqual(poly.name, "C")
        self.assertTrue(poly.is_ccw())
        self.assertEqual(len(poly.segments), 4)
        segment: SCSegment
        for segment in poly.segments:
            assert isinstance(segment, SCArc)
            self.assertTrue(close(segment.center, (1.1, -2.3)))
            self.assertAlmostEqual(segment.radius, 0.37)
            self.assertAlmostEqual(segment.sweep, math.pi / 2)

        # Its outline is a true circle, with its inside where it belongs.
        loop: SCLoop = SCLoop.from_poly(poly)
        self.assertAlmostEqual(loop.length(), 2.0 * math.pi * 0.37)
        self.assertAlmostEqual(loop.signed_area(), math.pi * 0.37**2)
        self.assertTrue(loop.contains((1.1, -2.3)))
        self.assertTrue(loop.contains((1.1 + 0.36, -2.3)))
        self.assertFalse(loop.contains((1.1 + 0.27, -2.3 + 0.27)))
        self.assertAlmostEqual(loop.distance((1.1 + 1.0, -2.3)), 0.63)

    # Method `TestSCRoundedPolygon.test_circle_sizes()`:
    def test_circle_sizes(self) -> None:
        """Rounding does not upset `circle()` at any likely size."""
        x: float
        y: float
        radius: float
        for x, y in ((0.0, 0.0), (0.1, 0.7), (-123.456, 789.012)):
            for radius in (0.001, 1.0 / 3.0, 0.0625, 7.0, 1234.5678):
                poly: SCRoundedPolygon = SCRoundedPolygon.circle(
                    "C", x, y, radius, 0.0, 1.0
                )
                self.assertEqual(len(poly.segments), 4)
                self.check_outline(poly)

    # Method `TestSCRoundedPolygon.test_circle_bad_radius()`:
    def test_circle_bad_radius(self) -> None:
        """A circle needs a radius above zero."""
        radius: float
        for radius in (0.0, -1.0):
            with self.assertRaisesRegex(ValueError, "above zero"):
                SCRoundedPolygon.circle("C", 0.0, 0.0, radius, 0.0, 1.0)

    # Method `TestSCRoundedPolygon.test_circle_offset()`:
    def test_circle_offset(self) -> None:
        """Growing or shrinking a circle gives a circle, until it is gone."""
        poly: SCRoundedPolygon = SCRoundedPolygon.circle(
            "C", 3.0, 4.0, 2.0, 0.0, 1.0
        )
        distance: float
        for distance in (0.25, -0.25):
            moved: SCRoundedPolygon = poly.offset(distance)
            self.assertEqual(len(moved.segments), 4)
            segment: SCSegment
            for segment in moved.segments:
                assert isinstance(segment, SCArc)
                self.assertTrue(close(segment.center, (3.0, 4.0)))
                self.assertAlmostEqual(segment.radius, 2.0 + distance)
        with self.assertRaises(ValueError):
            poly.offset(-2.0)

        # `inset()`, as the keep out zones will use: in, out, and gone.
        loops: list[SCLoop] = inset([SCLoop.from_poly(poly)], 0.25, "In")
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(loops[0].length(), 2.0 * math.pi * 1.75)
        out: list[SCLoop] = inset(
            [SCLoop.from_poly(poly.reversed())], 0.25, "Out"
        )
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0].length(), 2.0 * math.pi * 2.25)
        self.assertEqual(inset([SCLoop.from_poly(poly)], 2.5, "Gone"), [])

    # Method `TestSCRoundedPolygon.test_notched()`:
    def test_notched(self) -> None:
        """A notched shape, with one corner turning the other way."""
        poly: SCRoundedPolygon = notched()
        self.check_outline(poly)
        sweeps: list[float] = [
            segment.sweep
            for segment in poly.segments
            if isinstance(segment, SCArc)
        ]
        self.assertEqual(len(sweeps), 6)
        self.assertEqual(len([sweep for sweep in sweeps if sweep < 0]), 1)

        # The arc at the 135 degree corner.
        arc: SCArc = next(
            segment
            for segment in poly.segments
            if isinstance(segment, SCArc) and segment.radius == 6.0
        )
        self.assertAlmostEqual(arc.sweep, math.radians(135.0))
        self.assertTrue(close(arc.end, (0.0, 50.0 - 6.0 * (1 + 2**0.5))))

    # Method `TestSCRoundedPolygon.test_errors()`:
    def test_errors(self) -> None:
        """Polygons that cannot be rounded are refused."""
        with self.assertRaises(ValueError):
            square(10.0, 5.1)
        with self.assertRaises(ValueError):
            polygon((0, 0), (1, 0))
        with self.assertRaises(ValueError):
            polygon((0, 0), (0, 0), (1, 1))
        with self.assertRaises(ValueError):
            polygon((0, 0), (1, 0), (2, 0), (1, 1))
        with self.assertRaises(ValueError):
            polygon((0, 0), (2, 0), (1, 0))
        with self.assertRaises(ValueError):
            SCCorner(0, 0, -1.0)

    # Method `TestSCRoundedPolygon.test_crossings()`:
    def test_crossings(self) -> None:
        """Outlines that cross or touch themselves are refused."""
        # A bow tie: two edges cross.
        with self.assertRaisesRegex(ValueError, "cross at"):
            polygon((0, 0), (2, 2), (2, 0), (0, 2))

        # A corner touching an edge, and two edges overlapping.
        with self.assertRaisesRegex(ValueError, "cross at"):
            polygon((0, 0), (4, 0), (4, 2), (2, 0), (0, 2))
        with self.assertRaisesRegex(ValueError, "cross at"):
            polygon(
                (0, 0), (4, 0), (4, 2), (3, 2), (3, 0), (1, 0), (1, 2), (0, 2)
            )

        # Rounding a corner can be what makes the outline cross: a slot
        # that runs close to a corner with a big radius.
        slot: list[tuple[float, float]] = [
            (0, 0),
            (10, 0),
            (10, 10),
            (0, 10),
            (0, 9.5),
            (9.5, 9.5),
            (9.5, 9),
            (0, 9),
        ]
        polygon(*slot)
        corners: list[SCCorner] = [SCCorner(x, y) for x, y in slot]
        corners[2] = SCCorner(10, 10, 4.0)
        with self.assertRaisesRegex(ValueError, "cross at"):
            SCRoundedPolygon("Slot", corners, 0.0, 1.0)

    # Method `TestSCRoundedPolygon.test_reversed()`:
    def test_reversed(self) -> None:
        """Reversing keeps the first corner and flips the direction."""
        poly: SCRoundedPolygon = notched()
        back: SCRoundedPolygon = poly.reversed()
        self.check_outline(back)
        self.assertFalse(back.is_ccw())
        self.assertEqual(back.corners[0], poly.corners[0])
        self.assertEqual(back.corners[1], poly.corners[-1])
        self.assertAlmostEqual(back.signed_area, -poly.signed_area)

    # Method `TestSCRoundedPolygon.test_offset_square()`:
    def test_offset_square(self) -> None:
        """A rounded square, moved out and in."""
        # Moved out, both ways around, the corners' radii grow (the
        # clockwise square starts at its top left corner).
        poly: SCRoundedPolygon
        first: tuple[float, float]
        for poly, first in (
            (square(20.0, 3.0), (-1.0, -1.0)),
            (square(20.0, 3.0, ccw=False), (-1.0, 21.0)),
        ):
            out: SCRoundedPolygon = poly.offset(1.0)
            self.check_outline(out)
            self.assertEqual(out.is_ccw(), poly.is_ccw())
            self.assertAlmostEqual(abs(out.signed_area), 22.0**2)
            self.assertTrue(close((out.corners[0].x, out.corners[0].y), first))
            self.assertEqual(
                [corner.radius for corner in out.corners], [4.0] * 4
            )

        # Moved in past a corner's radius, the corner becomes sharp.
        inner: SCRoundedPolygon = square(20.0, 3.0).offset(-4.0)
        self.assertEqual(
            [corner.radius for corner in inner.corners], [0.0] * 4
        )
        self.assertAlmostEqual(inner.signed_area, 12.0**2)

        # Moved in too far, it collapses.
        with self.assertRaises(ValueError):
            square(20.0, 3.0).offset(-10.0)

    # Method `TestSCRoundedPolygon.test_offset_notched()`:
    def test_offset_notched(self) -> None:
        """Moved out, the notch's inner corner shrinks its radius."""
        out: SCRoundedPolygon = notched().offset(1.0)
        self.check_outline(out)
        radii: list[float] = [corner.radius for corner in out.corners]
        self.assertEqual(radii, [6.0, 11.0, 4.0, 3.0, 3.0, 0.0, 7.0])

        # The moved edges are 1 from the old ones.
        self.assertTrue(close((out.corners[4].x, out.corners[4].y), (39, 31)))

        # Every point of the moved outline is 1 from the old one, so
        # an arc's center stays put.
        arc: SCArc = next(
            segment
            for segment in out.segments
            if isinstance(segment, SCArc) and segment.radius == 11.0
        )
        self.assertTrue(close(arc.center, (70.0, 10.0)))

        # The sharp concave corner is cut with the tool's own radius.
        moved: SCRoundedPolygon = notched().offset(5.0)
        self.assertEqual(moved.corners[4].radius, 0.0)


# Function `dumbbell()`:
def dumbbell() -> SCRoundedPolygon:
    """Return two 0.9 x 1.5 lobes joined by a 0.4 wide neck.

    Returns:
    * (`SCRoundedPolygon`): The shape, with sharp corners.
    """
    return polygon(
        (0.4, 0.4),
        (1.3, 0.4),
        (1.3, 0.95),
        (1.7, 0.95),
        (1.7, 0.4),
        (2.6, 0.4),
        (2.6, 1.9),
        (1.7, 1.9),
        (1.7, 1.35),
        (1.3, 1.35),
        (1.3, 1.9),
        (0.4, 1.9),
    )


# Class `TestSCLoop`:
class TestSCLoop(unittest.TestCase):
    """Loops of lines and arcs, and the classic offset (`inset()`)."""

    # Method `TestSCLoop.check_inset()`:
    def check_inset(
        self, region: SCLoop, distance: float, loops: list[SCLoop]
    ) -> None:
        """Check that inset loops are closed, `distance` from the edge.

        Arguments:
        * `region` (`SCLoop`): The region's outline.
        * `distance` (`float`): How far in the loops are.
        * `loops` (`list[SCLoop]`): The loops `inset()` found.
        """
        loop: SCLoop
        for loop in loops:
            self.assertTrue(loop.is_ccw())
            index: int
            segment: SCSegment
            for index, segment in enumerate(loop.segments):
                following: SCSegment = loop.segments[
                    (index + 1) % len(loop.segments)
                ]
                self.assertTrue(close(segment.end, following.start))
                fraction: float
                for fraction in (0.0, 0.25, 0.5, 0.75):
                    self.assertAlmostEqual(
                        region.distance(point_at(segment, fraction)),
                        distance,
                        places=6,
                    )

    # Method `TestSCLoop.test_area()`:
    def test_area(self) -> None:
        """The area counts the slivers between arcs and their chords."""
        loop: SCLoop = SCLoop.from_poly(square(10.0, 3.0))
        self.assertAlmostEqual(loop.signed_area(), 100.0 - (4 - math.pi) * 9)
        self.assertTrue(loop.is_ccw())
        back: SCLoop = loop.reversed()
        self.assertAlmostEqual(back.signed_area(), -loop.signed_area())
        self.assertAlmostEqual(back.length(), loop.length())
        self.assertAlmostEqual(loop.distance((5.0, 5.0)), 5.0)
        self.assertAlmostEqual(loop.distance((-1.0, -1.0)), 2**0.5 * 4 - 3)

    # Method `TestSCLoop.test_corners()`:
    def test_corners(self) -> None:
        """Only sharp corners are corners."""
        self.assertEqual(len(SCLoop.from_poly(square(10.0, 0.0)).corners()), 4)
        self.assertEqual(SCLoop.from_poly(square(10.0, 3.0)).corners(), [])

    # Method `TestSCLoop.test_segments()`:
    def test_segments(self) -> None:
        """Arcs and lines split, measure and move as they should."""
        arc: SCArc = SCArc(
            (1.0, 0.0), (0.0, 1.0), (0.0, 0.0), 1.0, math.pi / 2
        )
        middle: tuple[float, float] = point_at(arc, 0.5)
        self.assertTrue(close(middle, (0.5**0.5, 0.5**0.5)))
        self.assertAlmostEqual(fraction_of(arc, middle), 0.5)
        pieces: list[SCSegment] = split_at(arc, [middle, (1.0, 0.0)])
        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(
            sum(piece.length() for piece in pieces), math.pi / 2
        )
        self.assertAlmostEqual(distance_to((2.0, 0.0), arc), 1.0)
        self.assertAlmostEqual(distance_to((0.0, -1.0), arc), 2**0.5)

        # A counter-clockwise arc shrinks moving left; past its center
        # it turns into a line.
        moved: SCSegment | None = offset_segment(arc, 0.25)
        assert isinstance(moved, SCArc)
        self.assertAlmostEqual(moved.radius, 0.75)
        self.assertIsInstance(offset_segment(arc, 1.5), SCLine)
        self.assertIsNone(offset_segment(arc, 1.0))
        line: SCSegment | None = offset_segment(SCLine((0, 0), (2, 0)), 1.0)
        assert isinstance(line, SCLine)
        self.assertTrue(close(line.start, (0.0, 1.0)))

    # Method `TestSCLoop.test_inset_square()`:
    def test_inset_square(self) -> None:
        """A square moves in to a smaller square, then vanishes."""
        sharp: SCLoop = SCLoop.from_poly(square(10.0, 0.0))
        loops: list[SCLoop] = inset([sharp], 1.0, "In")
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(loops[0].signed_area(), 64.0)
        self.assertEqual(len(loops[0].segments), 4)
        self.check_inset(sharp, 1.0, loops)
        self.assertEqual(inset([sharp], 5.1, "In"), [])

        # A rounded square's corners shrink, then go sharp.
        rounded: SCLoop = SCLoop.from_poly(square(10.0, 3.0))
        loops = inset([rounded], 1.0, "In")
        self.assertAlmostEqual(
            loops[0].signed_area(), 64.0 - (4 - math.pi) * 4
        )
        self.check_inset(rounded, 1.0, loops)
        loops = inset([rounded], 4.0, "In")
        self.assertAlmostEqual(loops[0].signed_area(), 4.0)
        self.assertEqual(len(loops[0].corners()), 4)

    # Method `TestSCLoop.test_inset_concave()`:
    def test_inset_concave(self) -> None:
        """Inside a corner that turns right, the inset is an arc."""
        shape: SCLoop = SCLoop.from_poly(
            polygon((0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4))
        )
        loops: list[SCLoop] = inset([shape], 0.5, "L")
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(
            loops[0].signed_area(), 5.0 + 0.25 - math.pi * 0.25 / 4
        )
        arcs: list[SCArc] = [
            segment
            for segment in loops[0].segments
            if isinstance(segment, SCArc)
        ]
        self.assertEqual(len(arcs), 1)
        self.assertTrue(close(arcs[0].center, (2.0, 2.0)))
        self.assertAlmostEqual(arcs[0].radius, 0.5)
        self.check_inset(shape, 0.5, loops)

    # Method `TestSCLoop.test_inset_splits()`:
    def test_inset_splits(self) -> None:
        """A dumbbell comes apart at its neck, then vanishes."""
        shape: SCLoop = SCLoop.from_poly(dumbbell())
        loops: list[SCLoop] = inset([shape], 0.1, "Bell")
        self.assertEqual(len(loops), 1)
        self.check_inset(shape, 0.1, loops)

        # Past half the neck's width, the lobes are separate.
        loops = inset([shape], 0.21, "Bell")
        self.assertEqual([loop.name for loop in loops], ["Bell 1", "Bell 2"])
        self.assertAlmostEqual(loops[0].signed_area(), loops[1].signed_area())
        self.check_inset(shape, 0.21, loops)
        # A sliver lasts a little longer where the neck opens into
        # each lobe.
        loops = inset([shape], 0.46, "Bell")
        self.assertEqual(len(loops), 2)
        self.check_inset(shape, 0.46, loops)
        self.assertEqual(inset([shape], 0.6, "Bell"), [])

    # Method `TestSCLoop.test_inset_rounded_shapes()`:
    def test_inset_rounded_shapes(self) -> None:
        """Insets of rounded, notched shapes stay true."""
        shape: SCLoop = SCLoop.from_poly(notched())
        distance: float
        for distance in (1.0, 2.5, 4.0, 8.0):
            self.check_inset(shape, distance, inset([shape], distance, "N"))


class _SCSketch:
    """Stands in for SolidCraft's `sketch` commands, counting curves."""

    def __init__(self) -> None:
        self.circles: list[dict[str, object]] = []
        self.count: int = 0

    def _curve(self) -> dict[str, list[str]]:
        self.count += 1
        return {"curves": [f"c{self.count}"]}

    def line(self, **_arguments: object) -> dict[str, list[str]]:
        """Draw a line."""
        return self._curve()

    def arc_center_point(self, **_arguments: object) -> dict[str, list[str]]:
        """Draw an arc."""
        return self._curve()

    def circle_center(self, **arguments: object) -> dict[str, list[str]]:
        """Draw a circle."""
        self.circles.append(arguments)
        return self._curve()


class TestChildren(unittest.TestCase):
    """The heights and children of a rounded polygon."""

    def test_same_heights(self) -> None:
        """Equal heights raise an exception, however it is made."""
        with self.assertRaisesRegex(ValueError, "both 2.0"):
            box("B", 0.0, 1.0, 2.0, 2.0)
        with self.assertRaisesRegex(ValueError, "both"):
            SCRoundedPolygon.circle("C", 0.0, 0.0, 1.0, 0.5, 0.5)
        with self.assertRaisesRegex(ValueError, "go down"):
            SCHole(0.0, 0.0, 1.0, 0.5, 0.5)

    def test_kept(self) -> None:
        """Children are kept as a tuple, and heights carry over."""
        hole = SCHole(5.0, 5.0, 1.0, 1.0, 0.0)
        plate = box("P", 0.0, 10.0, 0.0, 1.0, [hole])
        self.assertEqual(plate.children, (hole,))
        self.assertEqual(plate.reversed().children, (hole,))
        self.assertEqual(plate.reversed().z_end, 1.0)
        self.assertEqual(plate.offset(1.0).children, ())
        self.assertEqual(plate.offset(1.0).z_end, 1.0)

    def test_exact_match(self) -> None:
        """A child must start exactly where its parent ends."""
        with self.assertRaisesRegex(ValueError, "not at z_end"):
            box(
                "P",
                0.0,
                10.0,
                0.0,
                1.0,
                [SCHole(5.0, 5.0, 1.0, 1.0 + 1e-12, 0.0)],
            )
        with self.assertRaisesRegex(ValueError, "not at z_end"):
            box("P", 0.0, 10.0, 0.0, 1.0, [box("B", 2.0, 3.0, 0.0, 2.0)])
        box(
            "P",
            0.0,
            10.0,
            0.0,
            0.1 + 0.2,
            [box("B", 2.0, 3.0, 0.1 + 0.2, 2.0)],
        )
        with self.assertRaisesRegex(ValueError, "not at z_end"):
            box("P", 0.0, 10.0, 0.0, 0.1 + 0.2, [box("B", 2.0, 3.0, 0.3, 2.0)])

    def test_enclosed(self) -> None:
        """A child stays within its parent, but may touch its wall."""
        for bad in (
            box("B", 5.0, 15.0, 1.0, 2.0),
            box("B", 20.0, 30.0, 1.0, 2.0),
            box("B", -5.0, 15.0, 1.0, 2.0),
        ):
            with self.assertRaisesRegex(ValueError, "not inside"):
                box("P", 0.0, 10.0, 0.0, 1.0, [bad])
        with self.assertRaisesRegex(ValueError, "not inside"):
            box("P", 0.0, 10.0, 0.0, 1.0, [SCHole(9.9, 5.0, 1.0, 1.0, 0.0)])

        # Flush with one wall, with two, and the same outline.
        box("P", 0.0, 10.0, 0.0, 1.0, [box("B", 0.0, 5.0, 1.0, 2.0)])
        box("P", 0.0, 10.0, 0.0, 1.0, [box("B", 0.0, 10.0, 1.0, 2.0)])
        box("P", 0.0, 10.0, 0.0, 1.0, [SCHole(9.5, 5.0, 1.0, 1.0, 0.0)])

    def test_siblings(self) -> None:
        """Siblings may touch, but not overlap."""
        first = box("A", 1.0, 4.0, 1.0, 2.0)
        for bad in (
            box("B", 3.0, 6.0, 1.0, 2.0),
            box("B", 2.0, 3.0, 1.0, 2.0),
            box("B", 1.0, 4.0, 1.0, 2.0),
        ):
            with self.assertRaisesRegex(ValueError, "overlaps"):
                box("P", 0.0, 10.0, 0.0, 1.0, [first, bad])
            with self.assertRaisesRegex(ValueError, "overlaps"):
                box("P", 0.0, 10.0, 0.0, 1.0, [bad, first])
        box("P", 0.0, 10.0, 0.0, 1.0, [first, box("B", 5.0, 6.0, 1.0, 0.5)])

        # Corners that touch, and a square beside it sharing a wall: the
        # square's corners only touch along that wall, with no overlap.
        beside = SCRoundedPolygon(
            "C",
            [
                SCCorner(4.0, 1.0),
                SCCorner(6.0, 1.0),
                SCCorner(6.0, 4.0),
                SCCorner(4.0, 4.0),
            ],
            1.0,
            2.0,
        )
        box("P", 0.0, 10.0, 0.0, 1.0, [first, beside])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            box(
                "P",
                0.0,
                10.0,
                0.0,
                1.0,
                [
                    SCHole(5.0, 5.0, 2.0, 1.0, 0.0),
                    SCHole(6.0, 5.0, 2.0, 1.0, 0.0),
                ],
            )

    def test_hole(self) -> None:
        """An `SCHole` is a rounded polygon that goes down."""
        hole = SCHole(1.0, 2.0, 0.5, 3.0, 1.0)
        self.assertIsInstance(hole, SCRoundedPolygon)
        self.assertEqual((hole.x, hole.y, hole.diameter), (1.0, 2.0, 0.5))
        self.assertTrue(hole.enters(SCLine((1.0, 2.0), (1.0, 2.0))))
        self.assertEqual(len(hole.shrunk(0.1)), 1)
        with self.assertRaisesRegex(ValueError, "above zero"):
            SCHole(1.0, 2.0, 0.0, 3.0, 1.0)
        with self.assertRaisesRegex(ValueError, "go down"):
            SCHole(1.0, 2.0, 0.5, 1.0, 3.0)
        counterbore = SCHole(
            1.0, 2.0, 2.0, 3.0, 2.0, [SCHole(1.0, 2.0, 1.0, 2.0, 1.0)]
        )
        self.assertEqual(len(counterbore.children), 1)

    def test_sketch(self) -> None:
        """The sketch has the outline, and what runs the whole height."""
        through = SCHole(5.0, 5.0, 1.0, 1.0, 0.0)
        blind = SCHole(2.0, 2.0, 0.5, 1.0, 0.5)
        counterbore = box(
            "Cut", 6.0, 9.0, 1.0, 0.0, [box("In", 7.0, 8.0, 0.0, 1.0)]
        )
        plate = box("P", 0.0, 10.0, 0.0, 1.0, [through, blind, counterbore])
        sketch = _SCSketch()
        # A stand-in with only the `sketch` commands that are used.
        solidcraft = cast(SCPyBind, types.SimpleNamespace(sketch=sketch))
        curves = plate.sketch(solidcraft, 25.4)
        self.assertEqual(len(curves), 4 + 1 + 4)
        self.assertEqual(len(sketch.circles), 1)
        self.assertEqual(sketch.circles[0]["diameter"], 25.4)
        self.assertEqual(sketch.circles[0]["center"], (127.0, 127.0))


# Class `TestHits`:
class TestHits(unittest.TestCase):
    """Whether a tool hits a root or its descendants."""

    def setUp(self) -> None:
        """Make the plate, with its pocket, island and holes."""
        self.plate: SCRoundedPolygon = plate_with_island()

    def hit(
        self,
        start: Point,
        end: Point,
        z: float,
        radius: float = 1.0,
        poly: SCRoundedPolygon | None = None,
    ) -> bool:
        """Return whether a line move at a height hits."""
        return (poly or self.plate).hits(SCLine(start, end), z, radius)

    def test_above(self) -> None:
        """Above everything, or just at its top, nothing is hit."""
        self.assertFalse(self.hit((-5.0, 50.0), (105.0, 50.0), 11.0))
        self.assertFalse(self.hit((-5.0, 50.0), (105.0, 50.0), 10.0))
        self.assertTrue(self.hit((-5.0, 50.0), (105.0, 50.0), 9.99))

    def test_outside(self) -> None:
        """Beside the plate, at any height, is clear, until it touches."""
        self.assertFalse(self.hit((-5.0, 0.0), (-5.0, 100.0), -50.0))
        self.assertFalse(self.hit((-1.1, 0.0), (-1.1, 100.0), 5.0))
        self.assertTrue(self.hit((-1.0, 0.0), (-1.0, 100.0), 5.0))
        self.assertTrue(self.hit((-0.9, 0.0), (-0.9, 100.0), 5.0))

    def test_pocket(self) -> None:
        """In the pocket, above its floor, clear of its walls and island."""
        self.assertFalse(self.hit((35.0, 35.0), (85.0, 35.0), 6.0))
        self.assertFalse(self.hit((35.0, 35.0), (85.0, 35.0), 5.0))
        self.assertTrue(self.hit((35.0, 35.0), (85.0, 35.0), 4.9))

        # Touching the wall, across it, and starting outside it.
        self.assertTrue(self.hit((31.0, 35.0), (31.0, 85.0), 6.0))
        self.assertTrue(self.hit((35.0, 35.0), (25.0, 35.0), 6.0))
        self.assertTrue(self.hit((20.0, 35.0), (35.0, 35.0), 6.0))

        # The island, whose top is level with the plate's.
        self.assertTrue(self.hit((35.0, 60.0), (55.0, 60.0), 6.0))
        self.assertTrue(self.hit((49.5, 40.0), (49.5, 80.0), 6.0))
        self.assertFalse(self.hit((48.5, 40.0), (48.5, 80.0), 6.0))
        self.assertFalse(self.hit((48.5, 40.0), (48.5, 80.0), 11.0))
        self.assertFalse(self.hit((48.5, 40.0), (48.5, 80.0), 10.0))
        self.assertFalse(self.hit((47.0, 40.0), (47.0, 80.0), 6.0))
        self.assertFalse(self.hit((47.0, 40.0), (47.0, 80.0), 9.0))

    def test_holes(self) -> None:
        """A hole lets a tool down, as far as its floor."""
        # The plate's hole, diameter 10: a tool of radius 1 at its center.
        self.assertFalse(self.hit((10.0, 10.0), (10.0, 10.0), 1.0))
        self.assertFalse(self.hit((10.0, 10.0), (10.0, 10.0), 0.0))
        self.assertTrue(self.hit((10.0, 10.0), (10.0, 10.0), -0.1))
        self.assertFalse(self.hit((8.0, 10.0), (12.0, 10.0), 1.0))
        self.assertTrue(self.hit((5.0, 10.0), (12.0, 10.0), 1.0))

        # A tool too big for it.
        self.assertTrue(self.hit((10.0, 10.0), (10.0, 10.0), 1.0, 5.0))
        self.assertFalse(self.hit((10.0, 10.0), (10.0, 10.0), 1.0, 4.9))

        # The hole in the island, below the pocket's floor.
        self.assertFalse(self.hit((60.0, 60.0), (60.0, 60.0), 1.0))
        self.assertTrue(self.hit((60.0, 60.0), (54.0, 60.0), 1.0))

    def test_below_floor_in_deep_hole(self) -> None:
        """A hole below a pocket's floor is reached through that floor."""
        hole = SCHole(50.0, 50.0, 10.0, 5.0, 2.0)
        pocket = box("Pocket", 30.0, 70.0, 10.0, 5.0, (hole,))
        plate = box("Plate", 0.0, 100.0, 0.0, 10.0, (pocket,))
        self.assertFalse(self.hit((50.0, 50.0), (50.0, 50.0), 3.0, 1.0, plate))
        self.assertFalse(self.hit((50.0, 50.0), (50.0, 50.0), 2.0, 1.0, plate))
        self.assertTrue(self.hit((50.0, 50.0), (50.0, 50.0), 1.9, 1.0, plate))
        self.assertTrue(self.hit((40.0, 40.0), (40.0, 40.0), 3.0, 1.0, plate))

    def test_boss(self) -> None:
        """A boss on a plate blocks where the plate does not."""
        step = box("Boss", 40.0, 60.0, 10.0, 20.0)
        plate = box("Plate", 0.0, 100.0, 0.0, 10.0, (step,))
        self.assertFalse(self.hit((0.0, 50.0), (30.0, 50.0), 12.0, 1.0, plate))
        self.assertTrue(self.hit((0.0, 50.0), (39.5, 50.0), 12.0, 1.0, plate))
        self.assertFalse(
            self.hit((0.0, 50.0), (100.0, 50.0), 20.0, 1.0, plate)
        )

        # Flush with the plate's wall, the tool stays off of it too.
        flush = box("Boss", 0.0, 60.0, 10.0, 20.0)
        plate = box("Plate", 0.0, 100.0, 0.0, 10.0, (flush,))
        self.assertTrue(self.hit((-0.5, 30.0), (-0.5, 40.0), 12.0, 1.0, plate))
        self.assertFalse(
            self.hit((-5.0, 30.0), (-5.0, 40.0), 12.0, 1.0, plate)
        )

    def test_arcs(self) -> None:
        """Arcs work the same as lines."""
        arc = arc_at((60.0, 60.0), 20.0, 0.0, 360.0)
        self.assertFalse(self.plate.hits(arc, 6.0, 1.0))
        self.assertTrue(self.plate.hits(arc, 4.0, 1.0))
        self.assertTrue(
            self.plate.hits(arc_at((60.0, 60.0), 12.0, 0.0, 360.0), 6.0, 1.0)
        )
        self.assertFalse(
            self.plate.hits(arc_at((60.0, 60.0), 12.0, 0.0, 360.0), 11.0, 1.0)
        )

    def test_root_must_go_up(self) -> None:
        """A root going down is refused where it is used."""
        hole = SCHole(5.0, 5.0, 1.0, 1.0, 0.0)
        with self.assertRaisesRegex(ValueError, "must go up"):
            hole.hits(SCLine((0.0, 0.0), (1.0, 0.0)), 0.5, 0.1)
        with self.assertRaisesRegex(ValueError, "must go up"):
            # Refused before SolidCraft is used, so none is given.
            hole.model(None)  # type: ignore[arg-type]

    def test_against_height_field(self) -> None:
        """Random moves agree with walking a tool over the surface."""
        generator = random.Random(21)
        answers = []
        for _ in range(250):
            start = (generator.uniform(-5, 105), generator.uniform(-5, 105))
            if generator.random() < 0.5:
                end = (
                    start[0] + generator.uniform(-15, 15),
                    start[1] + generator.uniform(-15, 15),
                )
            else:
                end = (generator.uniform(-5, 105), generator.uniform(-5, 105))
            z = generator.choice((-1.0, 1.0, 4.0, 6.0, 9.0, 11.0))
            radius = generator.choice((0.5, 1.0, 2.0, 4.0))
            line = SCLine(start, end)

            # A real touch must be found, and with room to spare it must
            # be clear: this plate gives no false alarms.
            answer = self.plate.hits(line, z, radius)
            answers.append(answer)
            if tool_touches(line, z, radius * 0.99):
                self.assertTrue(answer, (start, end, z, radius))
            elif not tool_touches(line, z, radius + 0.1):
                self.assertFalse(answer, (start, end, z, radius))
        self.assertGreater(answers.count(True), 30)
        self.assertGreater(answers.count(False), 30)
