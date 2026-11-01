"""Tests for `scgeometry.py`: run `python3 -m unittest -v`."""

import math
import types
import unittest

import scgeometry
from scgeometry import (
    SCArc,
    SCCorner,
    SCLine,
    SCLoop,
    SCRoundedPolygon,
    SCSegment,
    distance_to,
    fraction_of,
    inset,
    offset_segment,
    point_at,
    split_at,
)


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
        "Square", [SCCorner(x, y, radius) for x, y in points]
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
        "Polygon", [SCCorner(x, y, radius) for x, y in points]
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
            SCRoundedPolygon("Slot", corners)

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


def _square(name, half, holes=(), regions=(), x=0.0):
    """Return a square polygon centered on `(x, 0)`."""
    return scgeometry.SCRoundedPolygon(
        name,
        [
            scgeometry.SCCorner(x - half, -half),
            scgeometry.SCCorner(x + half, -half),
            scgeometry.SCCorner(x + half, half),
            scgeometry.SCCorner(x - half, half),
        ],
        holes,
        regions,
    )


class _Sketch:
    """Stands in for SolidCraft's `sketch` commands, counting curves."""

    def __init__(self):
        self.circles = []
        self.count = 0

    def _curve(self):
        self.count += 1
        return {"curves": [f"c{self.count}"]}

    def line(self, **_arguments):
        """Draw a line."""
        return self._curve()

    def arc_center_point(self, **_arguments):
        """Draw an arc."""
        return self._curve()

    def circle_center(self, **arguments):
        """Draw a circle."""
        self.circles.append(arguments)
        return self._curve()


class TestInside(unittest.TestCase):
    """Holes and regions inside a rounded polygon."""

    def test_holes(self) -> None:
        """Round holes are kept, and stored as a tuple."""
        hole = scgeometry.SCHole(1.0, 2.0, 1.0)
        square = _square("S", 10.0, [hole])
        self.assertEqual(square.holes, (hole,))

    def test_no_size(self) -> None:
        """A hole must have a size."""
        with self.assertRaises(ValueError):
            scgeometry.SCHole(0.0, 0.0, 0.0)

    def test_hole_refused(self) -> None:
        """A hole must stay clear of the outline, and of other holes."""
        hole = scgeometry.SCHole
        for holes in (
            [hole(20.0, 0.0, 1.0)],
            [hole(9.5, 0.0, 1.0)],
            [hole(9.5, 0.0, 2.0)],
            [hole(0.0, 0.0, 2.0), hole(1.0, 0.0, 2.0)],
            [hole(0.0, 0.0, 2.0), hole(2.0, 0.0, 2.0)],
        ):
            with self.subTest(holes=holes), self.assertRaises(ValueError):
                _square("S", 10.0, holes)

    def test_rounded_corner_hole(self) -> None:
        """A hole near a corner is judged by the rounded outline."""
        corners = [
            scgeometry.SCCorner(0.0, 0.0, 3.0),
            scgeometry.SCCorner(10.0, 0.0, 3.0),
            scgeometry.SCCorner(10.0, 10.0, 3.0),
            scgeometry.SCCorner(0.0, 10.0, 3.0),
        ]
        hole = scgeometry.SCHole(0.5, 0.5, 0.5)
        with self.assertRaises(ValueError):
            scgeometry.SCRoundedPolygon("S", corners, [hole])

    def test_region_refused(self) -> None:
        """A region must stay clear of everything on its level."""
        hole = scgeometry.SCHole
        for holes, regions in (
            ((), [_square("R", 20.0)]),
            ((), [_square("R", 10.0)]),
            ((), [_square("R", 2.0, x=9.0)]),
            ((), [_square("R", 2.0, x=30.0)]),
            ((), [_square("A", 2.0), _square("B", 2.0, x=3.0)]),
            ((), [_square("A", 4.0), _square("B", 1.0)]),
            ([hole(0.0, 0.0, 1.0)], [_square("R", 2.0)]),
            ([hole(3.0, 0.0, 4.0)], [_square("R", 2.0)]),
        ):
            with self.subTest(regions=regions), self.assertRaises(ValueError):
                _square("S", 10.0, holes, regions)

    def test_island_with_holes(self) -> None:
        """An island in an opening may have its own holes and openings."""
        island = _square(
            "Island",
            5.0,
            [scgeometry.SCHole(3.0, 3.0, 1.0)],
            [_square("Inner opening", 1.0)],
        )
        opening = _square("Opening", 10.0, regions=[island])
        plate = _square("Plate", 20.0, regions=[opening])
        self.assertEqual(plate.regions[0].regions[0].holes[0].diameter, 1.0)

    def test_island_checked(self) -> None:
        """An island's own hole is checked against the island."""
        with self.assertRaises(ValueError):
            _square("Island", 5.0, [scgeometry.SCHole(5.0, 0.0, 1.0)])

    def test_sketch(self) -> None:
        """Everything inside is drawn, at every level, in millimeters."""
        island = _square("Island", 5.0, [scgeometry.SCHole(1.0, 2.0, 0.5)])
        plate = _square(
            "Plate",
            20.0,
            [scgeometry.SCHole(15.0, 15.0, 1.0)],
            [_square("Opening", 10.0, regions=[island])],
        )
        sketch = _Sketch()
        curves = plate.sketch(types.SimpleNamespace(sketch=sketch), 25.4)
        self.assertEqual(len(curves), 4 + 1 + 4 + 4 + 1)
        self.assertEqual(len(set(curves)), len(curves))
        self.assertEqual(
            [circle["diameter"] for circle in sketch.circles], [25.4, 12.7]
        )
        self.assertEqual(sketch.circles[1]["center"], (25.4, 50.8))

    def test_reversed_keeps_them(self) -> None:
        """Going around the other way keeps what is inside."""
        hole = scgeometry.SCHole(1.0, 2.0, 0.5)
        self.assertEqual(_square("S", 10.0, [hole]).reversed().holes, (hole,))

    def test_offset_drops_them(self) -> None:
        """A tool path follows only the outline."""
        hole = scgeometry.SCHole(1.0, 2.0, 0.5)
        self.assertEqual(_square("S", 10.0, [hole]).offset(1.0).holes, ())
