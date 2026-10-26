"""Tests for `solidcraftcnc.py`: run `python3 -m unittest -v`."""

import math
import re
import unittest

from scgeometry import (
    SCArc,
    SCCorner,
    SCLoop,
    SCRoundPoly,
    SCSegment,
    distance_to,
    point_at,
)
from solidcraftcnc import SCCNC, SCRing, _number, cut_order, plan_pocket
from test_scgeometry import dumbbell, square


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


# Function `rings()`:
def rings(roots: list[SCRing]) -> list[SCRing]:
    """Return every ring of a pocket's plan.

    Arguments:
    * `roots` (`list[SCRing]`): The outermost rings.

    Returns:
    * (`list[SCRing]`): All of the rings, each after those inside it.
    """
    return [ring for root in roots for ring in root.post_order()]


# Function `uncut()`:
def uncut(
    poly: SCRoundPoly, diameter: float, stepover: float, spacing: float
) -> list[tuple[float, float]]:
    """Return the points of a pocket that no ring's cut reaches.

    Arguments:
    * `poly` (`SCRoundPoly`): The pocket.
    * `diameter` (`float`): The tool's diameter.
    * `stepover` (`float`): The rings' stepover.
    * `spacing` (`float`): How far apart the points tried are.

    Returns:
    * (`list[tuple[float, float]]`): The points left uncut.
    """
    # Every segment and spur that the tool's center follows.
    boundary: SCLoop = SCLoop.from_poly(poly)
    cuts: list[SCSegment] = [
        segment
        for ring in rings(plan_pocket(boundary, diameter, stepover))
        for segment in (*ring.loop.segments, *ring.spurs)
    ]

    # Try points inside the pocket (a crossing count around its
    # outline, sampled finely), not right at its wall.
    outline: list[tuple[float, float]] = [
        point_at(segment, step / 20.0)
        for segment in boundary.segments
        for step in range(20)
    ]
    missed: list[tuple[float, float]] = []
    xs: list[float] = [point[0] for point in outline]
    ys: list[float] = [point[1] for point in outline]
    across: int = int((max(xs) - min(xs)) / spacing)
    up: int = int((max(ys) - min(ys)) / spacing)
    for column in range(across + 1):
        for row in range(up + 1):
            point: tuple[float, float] = (
                min(xs) + column * spacing,
                min(ys) + row * spacing,
            )
            if not inside(outline, point) or boundary.distance(point) < 1e-3:
                continue
            if (
                min(distance_to(point, cut) for cut in cuts)
                > diameter / 2 + 1e-6
            ):
                missed.append(point)
    return missed


# Function `inside()`:
def inside(
    outline: list[tuple[float, float]], point: tuple[float, float]
) -> bool:
    """Return whether a point is inside a polygon (counting crossings).

    Arguments:
    * `outline` (`list[tuple[float, float]]`): The polygon's corners.
    * `point` (`tuple[float, float]`): The point.

    Returns:
    * (`bool`): True when it is inside.
    """
    crossings: int = 0
    index: int
    x1: float
    y1: float
    for index, (x1, y1) in enumerate(outline):
        x2, y2 = outline[(index + 1) % len(outline)]
        if (y1 > point[1]) != (y2 > point[1]) and point[0] < x1 + (
            point[1] - y1
        ) * (x2 - x1) / (y2 - y1):
            crossings += 1
    return crossings % 2 == 1


# Function `rounded_dumbbell()`:
def rounded_dumbbell() -> SCRoundPoly:
    """Return the dumbbell with its corners rounded as a pocket's are.

    Returns:
    * (`SCRoundPoly`): The pocket.
    """
    return SCRoundPoly(
        "Bell",
        [
            SCCorner(
                corner.x,
                corner.y,
                0.1875 if index % 6 in (0, 1, 4, 5) else 0.0625,
            )
            for index, corner in enumerate(dumbbell().corners)
        ],
    )


# Class `TestPocket`:
class TestPocket(unittest.TestCase):
    """Pockets: their rings, and the G-code that clears them."""

    # Method `TestPocket.test_plan()`:
    def test_plan(self) -> None:
        """A dumbbell's rings come apart into one tree per lobe."""
        roots: list[SCRing] = plan_pocket(
            SCLoop.from_poly(rounded_dumbbell()), 0.25, 0.9
        )
        self.assertEqual(len(roots), 1)
        self.assertEqual(len(roots[0].children), 2)
        self.assertEqual(roots[0].spurs, [])
        child: SCRing
        for child in roots[0].children:
            self.assertTrue(child.loop.is_ccw())
            self.assertEqual(len(child.spurs), 5)

        # A pocket too small for the tool is refused.
        with self.assertRaises(ValueError):
            plan_pocket(SCLoop.from_poly(square(0.2, 0.0)), 0.25, 0.9)

    # Method `TestPocket.test_coverage()`:
    def test_coverage(self) -> None:
        """The rings and spurs reach every point of a pocket."""
        poly: SCRoundPoly
        for poly in (
            rounded_dumbbell(),
            SCRoundPoly(
                "Triangle",
                [
                    SCCorner(0, 0, 0.2),
                    SCCorner(2, 0, 0.2),
                    SCCorner(0.5, 1.2, 0.2),
                ],
            ),
            square(1.3, 0.125),
        ):
            stepover: float
            for stepover in (0.5, 0.9, 1.0):
                self.assertEqual(
                    uncut(poly, 0.25, stepover, 0.01), [], poly.name
                )

    # Method `TestPocket.test_order()`:
    def test_order(self) -> None:
        """Rings are cut after the rings inside them."""
        roots: list[SCRing] = plan_pocket(
            SCLoop.from_poly(square(2.0, 0.125)), 0.25, 0.9
        )
        order: list[tuple[SCRing, str]] = list(cut_order(roots[0], 0.25))
        self.assertIs(order[-1][0], roots[0])
        self.assertEqual(order[-1][1], "lead")
        self.assertEqual(order[0][1], "ramp")
        seen: list[SCRing] = []
        ring: SCRing
        for ring, _ in order:
            for child in ring.children:
                if child.loop.length() >= 0.5 or child.children:
                    self.assertIn(child, seen)
            seen.append(ring)
        self.assertEqual(len(seen), len(rings(roots)))

    # Method `TestPocket.test_gcode()`:
    def test_gcode(self) -> None:
        """The pocket's G-code stays safe and ramps gently."""
        cnc: SCCNC = SCCNC("Test")
        cnc.pocket(rounded_dumbbell(), -0.25, 0.125)
        cnc.finish()
        x: float = 0.0
        y: float = 0.0
        z: float = 1.0
        line: str
        for line in cnc.gcode().splitlines()[7:]:
            if line.startswith("("):
                continue
            words: dict[str, float] = {
                letter: float(value)
                for letter, value in re.findall(r"([A-Z])(-?[0-9.]+)", line)
            }
            code: float = words.get("G", -1.0)
            new: tuple[float, float, float] = (
                words.get("X", x),
                words.get("Y", y),
                words.get("Z", z),
            )
            run: float = math.dist((x, y), new[:2])
            if code in (2.0, 3.0):
                arc: SCArc = SCArc(
                    (x, y),
                    new[:2],
                    (x + words["I"], y + words["J"]),
                    math.hypot(words["I"], words["J"]),
                    0.0,
                )
                half: float = math.asin(min(run / 2 / arc.radius, 1.0))
                run = 2 * half * arc.radius

            # It never goes below the floor; rapids across are above
            # the work; going down while moving is no steeper than 3
            # degrees.
            self.assertGreaterEqual(new[2], -0.25 - 1e-9, line)
            if code == 0.0 and run > 0.0:
                self.assertGreaterEqual(z, cnc.z_top + cnc.clearance, line)
            if new[2] < z - 1e-4 and run > 0.0:
                self.assertLessEqual(
                    (z - new[2]) / run,
                    math.tan(math.radians(3.0)) * 1.01,
                    line,
                )
            x, y, z = new
        self.assertEqual(z, cnc.z_safe)

    # Method `TestPocket.test_settings()`:
    def test_settings(self) -> None:
        """A stepover or ramp angle that makes no sense is refused."""
        with self.assertRaises(ValueError):
            SCCNC("Test", stepover=0.0)
        with self.assertRaises(ValueError):
            SCCNC("Test", stepover=1.1)
        with self.assertRaises(ValueError):
            SCCNC("Test", ramp_angle=0.0)


if __name__ == "__main__":
    unittest.main()
