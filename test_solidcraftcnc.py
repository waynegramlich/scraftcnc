"""Tests for `solidcraftcnc.py`: run `python3 -m unittest -v`."""

import math
import unittest

from solidcraftcnc import (
    SCCNC,
    SCArc,
    SCCorner,
    SCLine,
    SCRoundPoly,
    SCSegment,
    _number,
)


# Function `notched()`:
def notched() -> SCRoundPoly:
    """Return a notched rectangle, a different radius at each corner.

    Returns:
    * (`SCRoundPoly`): An 80 x 50 notched rectangle, going
      counter-clockwise, whose notch's inner corner turns the other way.
    """
    return SCRoundPoly(
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
def square(side: float, radius: float, ccw: bool = True) -> SCRoundPoly:
    """Return a square with one corner at the origin.

    Arguments:
    * `side` (`float`): The length of each side.
    * `radius` (`float`): The radius of every corner.
    * `ccw` (`bool`): True to go counter-clockwise.

    Returns:
    * (`SCRoundPoly`): The square.
    """
    points: list[tuple[float, float]] = [
        (0.0, 0.0),
        (side, 0.0),
        (side, side),
        (0.0, side),
    ]
    if not ccw:
        points.reverse()
    return SCRoundPoly("Square", [SCCorner(x, y, radius) for x, y in points])


# Function `polygon()`:
def polygon(*points: tuple[float, float], radius: float = 0.0) -> SCRoundPoly:
    """Return a polygon with the same radius at every corner.

    Arguments:
    * `points` (`tuple[float, float]`): The corners.
    * `radius` (`float`): The radius of every corner.

    Returns:
    * (`SCRoundPoly`): The polygon.
    """
    return SCRoundPoly("Polygon", [SCCorner(x, y, radius) for x, y in points])


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


# Class `TestSCRoundPoly`:
class TestSCRoundPoly(unittest.TestCase):
    """The outline that `SCRoundPoly` computes."""

    # Method `TestSCRoundPoly.check_outline()`:
    def check_outline(self, poly: SCRoundPoly) -> None:
        """Check that an outline is closed and its arcs are true.

        Arguments:
        * `poly` (`SCRoundPoly`): The polygon to check.
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

    # Method `TestSCRoundPoly.test_square_ccw()`:
    def test_square_ccw(self) -> None:
        """A rounded square: 4 lines and 4 counter-clockwise arcs."""
        poly: SCRoundPoly = square(20.0, 3.0)
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

    # Method `TestSCRoundPoly.test_square_cw()`:
    def test_square_cw(self) -> None:
        """Going clockwise, every arc is clockwise."""
        poly: SCRoundPoly = square(20.0, 3.0, ccw=False)
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

    # Method `TestSCRoundPoly.test_sharp()`:
    def test_sharp(self) -> None:
        """Sharp corners give just the polygon's edges."""
        poly: SCRoundPoly = square(10.0, 0.0)
        self.check_outline(poly)
        self.assertTrue(
            all(isinstance(segment, SCLine) for segment in poly.segments)
        )
        self.assertEqual(len(poly.segments), 4)

    # Method `TestSCRoundPoly.test_circle()`:
    def test_circle(self) -> None:
        """Arcs that use up every edge leave no lines: a circle."""
        poly: SCRoundPoly = square(10.0, 5.0)
        self.check_outline(poly)
        self.assertEqual(len(poly.segments), 4)
        self.assertTrue(
            all(isinstance(segment, SCArc) for segment in poly.segments)
        )

    # Method `TestSCRoundPoly.test_notched()`:
    def test_notched(self) -> None:
        """A notched shape, with one corner turning the other way."""
        poly: SCRoundPoly = notched()
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

    # Method `TestSCRoundPoly.test_errors()`:
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

    # Method `TestSCRoundPoly.test_crossings()`:
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
            SCRoundPoly("Slot", corners)

    # Method `TestSCRoundPoly.test_reversed()`:
    def test_reversed(self) -> None:
        """Reversing keeps the first corner and flips the direction."""
        poly: SCRoundPoly = notched()
        back: SCRoundPoly = poly.reversed()
        self.check_outline(back)
        self.assertFalse(back.is_ccw())
        self.assertEqual(back.corners[0], poly.corners[0])
        self.assertEqual(back.corners[1], poly.corners[-1])
        self.assertAlmostEqual(back.signed_area, -poly.signed_area)

    # Method `TestSCRoundPoly.test_offset_square()`:
    def test_offset_square(self) -> None:
        """A rounded square, moved out and in."""
        # Moved out, both ways around, the corners' radii grow (the
        # clockwise square starts at its top left corner).
        poly: SCRoundPoly
        first: tuple[float, float]
        for poly, first in (
            (square(20.0, 3.0), (-1.0, -1.0)),
            (square(20.0, 3.0, ccw=False), (-1.0, 21.0)),
        ):
            out: SCRoundPoly = poly.offset(1.0)
            self.check_outline(out)
            self.assertEqual(out.is_ccw(), poly.is_ccw())
            self.assertAlmostEqual(abs(out.signed_area), 22.0**2)
            self.assertTrue(close((out.corners[0].x, out.corners[0].y), first))
            self.assertEqual(
                [corner.radius for corner in out.corners], [4.0] * 4
            )

        # Moved in past a corner's radius, the corner becomes sharp.
        inner: SCRoundPoly = square(20.0, 3.0).offset(-4.0)
        self.assertEqual(
            [corner.radius for corner in inner.corners], [0.0] * 4
        )
        self.assertAlmostEqual(inner.signed_area, 12.0**2)

        # Moved in too far, it collapses.
        with self.assertRaises(ValueError):
            square(20.0, 3.0).offset(-10.0)

    # Method `TestSCRoundPoly.test_offset_notched()`:
    def test_offset_notched(self) -> None:
        """Moved out, the notch's inner corner shrinks its radius."""
        out: SCRoundPoly = notched().offset(1.0)
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
        moved: SCRoundPoly = notched().offset(5.0)
        self.assertEqual(moved.corners[4].radius, 0.0)


# Class `TestSCCNC`:
class TestSCCNC(unittest.TestCase):
    """The G-code that `SCCNC` writes."""

    # Method `TestSCCNC.test_number()`:
    def test_number(self) -> None:
        """Numbers lose their trailing zeros, and `-0` is `0`."""
        self.assertEqual(_number(12.5), "12.5")
        self.assertEqual(_number(-3.0), "-3")
        self.assertEqual(_number(-0.00001), "0")
        self.assertEqual(_number(1.23456), "1.2346")

    # Method `TestSCCNC.test_start()`:
    def test_start(self) -> None:
        """The program starts in inches, at `z_safe`, spindle on."""
        cnc: SCCNC = SCCNC("Test")
        self.assertEqual(
            cnc.gcode(),
            "(Test)\nG20\nG90\nG17\nG94\nG0 Z1\nM3 S1200\n",
        )
        self.assertEqual(cnc.tool_diameter, 0.25)
        self.assertEqual(cnc.rapid_speed, 60.0)
        self.assertEqual(cnc.work_speed, 12.0)

    # Method `TestSCCNC.test_settings()`:
    def test_settings(self) -> None:
        """Settings that make no sense are refused."""
        with self.assertRaises(ValueError):
            SCCNC("Test", z_top=1.0, z_safe=1.0)
        with self.assertRaises(ValueError):
            SCCNC("Test", z_safe=0.05)
        with self.assertRaises(ValueError):
            SCCNC("Test", clearance=-0.01)
        with self.assertRaises(ValueError):
            SCCNC("Test", tool_diameter=0.0)
        with self.assertRaises(ValueError):
            SCCNC("Test", work_speed=-1.0)
        with self.assertRaises(ValueError):
            SCCNC("Test", spindle_rpm=0.0)

    # Method `TestSCCNC.test_moves()`:
    def test_moves(self) -> None:
        """Unchanged axes and feeds, and still moves, are left out."""
        cnc: SCCNC = SCCNC("Test")
        cnc.rapid(x=1.0, y=2.0, z=1.0)
        cnc.rapid(x=1.0)
        cnc.linear(z=-1.0)
        cnc.linear(x=3.0)
        cnc.finish()
        self.assertEqual(
            cnc.gcode().splitlines()[7:],
            ["G0 X1 Y2", "G1 Z-1 F12", "G1 X3", "G0 Z1", "M5", "M2"],
        )

        # 2 inches of cutting at 12 per minute, 2 inches of rapids at
        # 60 per minute (the first move has no known start).
        self.assertAlmostEqual(cnc.minutes, 4.0 / 12.0 + 2.0 / 60.0)

    # Method `TestSCCNC.test_circle_arcs()`:
    def test_circle_arcs(self) -> None:
        """An arc back to where it started still gets written."""
        cnc: SCCNC = SCCNC("Test")
        cnc.rapid(x=1.0, y=0.0)
        cnc.arc(SCArc((1.0, 0.0), (1.0, 0.0), (0.0, 0.0), 1.0, -2 * math.pi))
        self.assertEqual(cnc.gcode().splitlines()[-1], "G2 I-1 J0 F12")

    # Method `TestSCCNC.test_profile_outside()`:
    def test_profile_outside(self) -> None:
        """Outside a polygon, the tool climb mills clockwise."""
        cnc: SCCNC = SCCNC("Test", z_safe=0.5)
        path: SCRoundPoly = cnc.profile(square(2.0, 0.25), -0.3, 0.125)
        self.assertFalse(path.is_ccw())
        self.assertEqual(path.corners[0].radius, 0.375)

        # The lead-in starts a tool diameter left of the middle of the
        # first (longest) edge, going up the left side.
        lines: list[str] = cnc.gcode().splitlines()
        self.assertEqual(
            lines[7:14],
            [
                "(Profile Square outside to Z-0.3)",
                "G0 X-0.375 Y1",
                "G0 Z0.05",
                "G1 Z-0.1 F12",
                "G3 X-0.125 I0.125 J0",
                "G1 Y1.75",
                "G2 X0.25 Y2.125 I0.375 J0",
            ],
        )

        # The loop ends at the middle of that edge, and the lead-out
        # goes back to where the lead-in started.
        self.assertEqual(
            lines[20:23], ["G1 Y1", "G3 X-0.375 I-0.125 J0", "G1 Z-0.2"]
        )

        # Three passes (0.3 deep, at most 0.125 each), four corners and
        # two leads each.
        self.assertEqual(
            [line for line in lines if line.startswith("G1 Z")],
            ["G1 Z-0.1 F12", "G1 Z-0.2", "G1 Z-0.3"],
        )
        self.assertEqual(
            len([line for line in lines if line.startswith("G2 ")]), 12
        )
        self.assertEqual(
            len([line for line in lines if line.startswith("G3 ")]), 6
        )
        self.assertEqual(lines[-1], "G0 Z0.5")

    # Method `TestSCCNC.test_profile_inside()`:
    def test_profile_inside(self) -> None:
        """Inside a polygon, the tool climb mills counter-clockwise."""
        cnc: SCCNC = SCCNC("Test")
        hole: SCRoundPoly = square(1.0, 0.25, ccw=False)
        path: SCRoundPoly = cnc.profile(hole, -0.1, 0.5, inside=True)
        self.assertTrue(path.is_ccw())
        self.assertEqual(path.corners[0].radius, 0.125)
        gcode: str = cnc.gcode()
        self.assertEqual(gcode.count("\nG3 "), 6)
        self.assertNotIn("\nG2 ", gcode)

        # The lead-in starts inside the hole, left of the path going
        # down its left side.
        self.assertIn("G0 X0.375 Y0.5\n", gcode)

        # A hole too small for the tool is refused, and so is one too
        # small for the lead-in.
        with self.assertRaises(ValueError):
            cnc.profile(square(0.2, 0.0), -0.1, 0.5, inside=True)
        with self.assertRaisesRegex(ValueError, "lead-in"):
            cnc.profile(square(0.45, 0.0), -0.1, 0.5, inside=True)
        cnc.profile(square(0.55, 0.0), -0.1, 0.5, inside=True)

    # Method `TestSCCNC.test_profile_errors()`:
    def test_profile_errors(self) -> None:
        """Depths that make no sense are refused."""
        cnc: SCCNC = SCCNC("Test")
        with self.assertRaises(ValueError):
            cnc.profile(square(1.0, 0.0), 0.0, 0.1)
        with self.assertRaises(ValueError):
            cnc.profile(square(1.0, 0.0), -0.1, 0.0)

    # Method `TestSCCNC.test_comment()`:
    def test_comment(self) -> None:
        """A comment may not hold parentheses."""
        cnc: SCCNC = SCCNC("Test")
        with self.assertRaises(ValueError):
            cnc.comment("a (nested) comment")


if __name__ == "__main__":
    unittest.main()
