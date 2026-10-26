"""Tests for `solidcraftcnc.py`: run `python3 -m unittest -v`."""

import math
import re
import unittest
from collections.abc import Sequence

from scgeometry import (
    SCArc,
    SCCorner,
    SCLoop,
    SCRoundPoly,
    SCSegment,
    distance_to,
)
from scmachine import SCMachine, SCTool
from solidcraftcnc import SCCNC, SCRing, _number, cut_order, plan_pocket
from test_scgeometry import dumbbell, square


# Function `machine()`:
def machine(**changes: object) -> SCMachine:
    """Return a test machine: end mill 1, drills 2 and 3, bits 5 and 6.

    Arguments:
    * `changes` (`object`): Preferences to change from the defaults.

    Returns:
    * (`SCMachine`): The machine.
    """
    settings: dict[str, object] = {
        "name": "Test mill",
        "z_safe": 1.0,
        "clearance": 0.05,
        "tool_change_z": 2.0,
        "tool_change": "T{number:02d}",
        "rapid_speed": 60.0,
        "drill_cycle": "G83",
        "through_overcut": 0.1,
        "stepover": 0.9,
        "ramp_angle": 3.0,
        "tools": (
            SCTool(1, "End mill", "end mill", 0.25, 1200, 12.0, 6.0),
            SCTool(2, "Drill", "drill", 0.234375, 1200, 4.0, 4.0, 0.05),
            SCTool(3, "Small drill", "drill", 0.125, 1200, 4.0, 4.0, 0.05),
            SCTool(5, "V-bit", "chamfer", 0.02, 1200, 12.0, 4.0, angle=90.0),
            SCTool(
                6,
                "Rounder",
                "corner round",
                0.125,
                1200,
                12.0,
                4.0,
                radius=0.0625,
            ),
        ),
    }
    settings.update(changes)
    return SCMachine(**settings)  # type: ignore[arg-type]


# Function `milling()`:
def milling(z_top: float = 0.0, **changes: object) -> SCCNC:
    """Return a program on the test machine, with the end mill in.

    Arguments:
    * `z_top` (`float`): The top of the material.
    * `changes` (`object`): Machine preferences to change.

    Returns:
    * (`SCCNC`): The program, after its tool change.
    """
    cnc: SCCNC = SCCNC("Test", machine(**changes), z_top)
    cnc.change_tool(1)
    return cnc


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
        """Start in inches at `z_safe`, then change to a tool."""
        cnc: SCCNC = milling()
        self.assertEqual(
            cnc.gcode(),
            "(Test)\nG20\nG90\nG17\nG94\nG0 Z1\n"
            "(Tool 1: End mill)\nG0 Z2\nT01\nM3 S1200\n",
        )
        self.assertEqual(cnc.cutter.diameter, 0.25)

        # Changing again stops the spindle first; the words come from
        # the machine's template.
        cnc.change_tool(2)
        self.assertEqual(
            cnc.gcode().splitlines()[10:],
            ["(Tool 2: Drill)", "M5", "T02", "M3 S1200"],
        )
        other: SCCNC = SCCNC("Test", machine(tool_change="T{number:02d} M06"))
        other.change_tool(3)
        self.assertIn("T03 M06\n", other.gcode())
        with self.assertRaises(KeyError):
            other.change_tool(9)

    # Method `TestSCCNC.test_settings()`:
    def test_settings(self) -> None:
        """Material too high for `z_safe`, and cutting with no tool."""
        with self.assertRaises(ValueError):
            SCCNC("Test", machine(), 1.0)
        with self.assertRaises(ValueError):
            SCCNC("Test", machine()).linear(z=-1.0)

    # Method `TestSCCNC.test_moves()`:
    def test_moves(self) -> None:
        """Unchanged axes and feeds, and still moves, are left out."""
        cnc: SCCNC = milling()
        cnc.rapid(x=1.0, y=2.0, z=1.0)
        cnc.rapid(x=1.0)
        cnc.linear(z=-1.0)
        cnc.linear(x=3.0)
        cnc.finish()
        self.assertEqual(
            cnc.gcode().splitlines()[10:],
            ["G0 X1 Y2 Z1", "G1 Z-1 F12", "G1 X3", "G0 Z1", "M5", "M2"],
        )

        # 2 inches of cutting at 12 per minute, 2 inches of rapids at
        # 60 per minute (the first move has no known start).
        self.assertAlmostEqual(cnc.minutes, 4.0 / 12.0 + 2.0 / 60.0)

    # Method `TestSCCNC.test_circle_arcs()`:
    def test_circle_arcs(self) -> None:
        """An arc back to where it started still gets written."""
        cnc: SCCNC = milling()
        cnc.rapid(x=1.0, y=0.0)
        cnc.arc(SCArc((1.0, 0.0), (1.0, 0.0), (0.0, 0.0), 1.0, -2 * math.pi))
        self.assertEqual(cnc.gcode().splitlines()[-1], "G2 I-1 J0 F12")

    # Method `TestSCCNC.test_profile_outside()`:
    def test_profile_outside(self) -> None:
        """Outside a polygon, the tool climb mills clockwise."""
        cnc: SCCNC = milling(z_safe=0.5)
        path: SCRoundPoly = cnc.profile(square(2.0, 0.25), -0.3, 0.125)
        self.assertFalse(path.is_ccw())
        self.assertEqual(path.corners[0].radius, 0.375)

        # The lead-in starts a tool diameter left of the middle of the
        # first (longest) edge, going up the left side.
        # It goes down at the plunge feed, and cuts at the feed.
        lines: list[str] = cnc.gcode().splitlines()
        self.assertEqual(
            lines[10:18],
            [
                "(Profile Square outside to Z-0.3)",
                "G0 Z0.5",
                "G0 X-0.375 Y1",
                "G0 Z0.05",
                "G1 Z-0.1 F6",
                "G3 X-0.125 I0.125 J0 F12",
                "G1 Y1.75",
                "G2 X0.25 Y2.125 I0.375 J0",
            ],
        )

        # The loop ends at the middle of that edge, and the lead-out
        # goes back to where the lead-in started.
        self.assertEqual(
            lines[24:27],
            ["G1 Y1", "G3 X-0.375 I-0.125 J0", "G1 Z-0.2 F6"],
        )

        # Three passes (0.3 deep, at most 0.125 each), four corners and
        # two leads each.
        self.assertEqual(
            [line for line in lines if line.startswith("G1 Z")],
            ["G1 Z-0.1 F6", "G1 Z-0.2 F6", "G1 Z-0.3 F6"],
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
        cnc: SCCNC = milling()
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
        cnc: SCCNC = milling()
        with self.assertRaises(ValueError):
            cnc.profile(square(1.0, 0.0), 0.0, 0.1)
        with self.assertRaises(ValueError):
            cnc.profile(square(1.0, 0.0), -0.1, 0.0)

    # Method `TestSCCNC.test_comment()`:
    def test_comment(self) -> None:
        """A comment may not hold parentheses."""
        cnc: SCCNC = milling()
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
    poly: SCRoundPoly,
    stepover: float,
    spacing: float,
    islands: Sequence[SCRoundPoly] = (),
) -> list[tuple[float, float]]:
    """Return the points of a pocket that no ring's cut reaches.

    The tool is 0.25 in across.

    Arguments:
    * `poly` (`SCRoundPoly`): The pocket.
    * `stepover` (`float`): The rings' stepover.
    * `spacing` (`float`): How far apart the points tried are.
    * `islands` (`Sequence[SCRoundPoly]`): Outlines left standing.

    Returns:
    * (`list[tuple[float, float]]`): The points left uncut.
    """
    # Every segment and spur that the tool's center follows.
    wall: SCLoop = SCLoop.from_poly(poly)
    holes: list[SCLoop] = [SCLoop.from_poly(island) for island in islands]
    region: list[SCLoop] = [
        wall,
        *(hole.reversed() if hole.is_ccw() else hole for hole in holes),
    ]
    cuts: list[SCSegment] = [
        segment
        for ring in rings(plan_pocket(region, 0.25, stepover))
        for segment in (
            *(part for loop in ring.loops for part in loop.segments),
            *ring.spurs,
        )
    ]

    # Try points in the pocket (not in an island), not right at a wall.
    xs: list[float] = [segment.start[0] for segment in wall.segments]
    ys: list[float] = [segment.start[1] for segment in wall.segments]
    missed: list[tuple[float, float]] = []
    for column in range(int((max(xs) - min(xs)) / spacing) + 1):
        for row in range(int((max(ys) - min(ys)) / spacing) + 1):
            point: tuple[float, float] = (
                min(xs) + column * spacing,
                min(ys) + row * spacing,
            )
            if (
                not wall.contains(point)
                or any(hole.contains(point) for hole in holes)
                or min(loop.distance(point) for loop in region) < 1e-3
            ):
                continue
            if min(distance_to(point, cut) for cut in cuts) > 0.125 + 1e-6:
                missed.append(point)
    return missed


# Function `depth()`:
def depth(ring: SCRing) -> int:
    """Return how many rings deep a ring's tree goes.

    Arguments:
    * `ring` (`SCRing`): The ring.

    Returns:
    * (`int`): 1 for a ring with none inside it.
    """
    return 1 + max((depth(child) for child in ring.children), default=0)


# Function `island_pocket()`:
def island_pocket() -> tuple[SCRoundPoly, list[SCRoundPoly]]:
    """Return a pocket with three islands, as the demonstration has.

    The islands are a triangle and a square with slightly rounded
    corners, and a square whose corner arcs make a circle.

    Returns:
    * (`SCRoundPoly`): The pocket.
    * (`list[SCRoundPoly]`): Its islands.
    """
    edge: float = 0.0625
    return (
        SCRoundPoly(
            "Pocket",
            [
                SCCorner(0.3, 0.3, 0.1875),
                SCCorner(2.75, 0.3, 0.1875),
                SCCorner(2.75, 2.05, 0.1875),
                SCCorner(0.3, 2.05, 0.1875),
            ],
        ),
        [
            SCRoundPoly(
                "Triangle",
                [
                    SCCorner(0.65, 0.65, edge),
                    SCCorner(1.25, 0.65, edge),
                    SCCorner(0.95, 1.2, edge),
                ],
            ),
            SCRoundPoly(
                "Square",
                [
                    SCCorner(1.65, 0.65, edge),
                    SCCorner(2.15, 0.65, edge),
                    SCCorner(2.15, 1.15, edge),
                    SCCorner(1.65, 1.15, edge),
                ],
            ),
            SCRoundPoly(
                "Circle",
                [
                    SCCorner(1.2, 1.35, 0.2),
                    SCCorner(1.6, 1.35, 0.2),
                    SCCorner(1.6, 1.75, 0.2),
                    SCCorner(1.2, 1.75, 0.2),
                ],
            ),
        ],
    )


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
            [SCLoop.from_poly(rounded_dumbbell())], 0.25, 0.9
        )
        self.assertEqual(len(roots), 1)
        self.assertEqual(len(roots[0].children), 2)
        self.assertEqual(roots[0].spurs, [])
        child: SCRing
        for child in roots[0].children:
            self.assertTrue(child.loops[0].is_ccw())
            self.assertEqual(len(child.spurs), 5)

        # A pocket too small for the tool is refused.
        with self.assertRaises(ValueError):
            plan_pocket([SCLoop.from_poly(square(0.2, 0.0))], 0.25, 0.9)

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
                self.assertEqual(uncut(poly, stepover, 0.01), [], poly.name)

    # Method `TestPocket.test_order()`:
    def test_order(self) -> None:
        """Rings are cut after the rings inside them."""
        roots: list[SCRing] = plan_pocket(
            [SCLoop.from_poly(square(2.0, 0.125))], 0.25, 0.9
        )
        order: list[tuple[SCRing, str]] = list(cut_order(roots[0], 0.25))
        self.assertIs(order[-1][0], roots[0])
        self.assertEqual(order[-1][1], "lead")
        self.assertEqual(order[0][1], "ramp")
        seen: list[SCRing] = []
        ring: SCRing
        for ring, _ in order:
            for child in ring.children:
                if child.length() >= 0.5 or child.children:
                    self.assertIn(child, seen)
            seen.append(ring)
        self.assertEqual(len(seen), len(rings(roots)))

    # Method `TestPocket.test_gcode()`:
    def test_gcode(self) -> None:
        """The pocket's G-code stays safe and ramps gently."""
        cnc: SCCNC = milling()
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
        """The machine's stepover and ramp angle are used."""
        narrow: SCCNC = milling(stepover=0.5)
        wide: SCCNC = milling()
        self.assertGreater(
            depth(narrow.pocket(square(2.0, 0.125), -0.1, 0.1)[0]),
            depth(wide.pocket(square(2.0, 0.125), -0.1, 0.1)[0]),
        )
        steep: SCCNC = milling(ramp_angle=30.0)
        steep.pocket(square(2.0, 0.125), -0.1, 0.1)
        self.assertLess(len(steep.commands), len(wide.commands))


# Class `TestDrill`:
class TestDrill(unittest.TestCase):
    """Drilling where the end mill goes down."""

    # Method `TestDrill.test_cycles()`:
    def test_cycles(self) -> None:
        """Each canned cycle, and pecks written out as moves."""
        cycle: str
        for cycle in ("G81", "G73", "G83"):
            cnc: SCCNC = SCCNC("Test", machine(drill_cycle=cycle))
            cnc.change_tool(2)
            cnc.drill([(1.0, 1.0), (2.0, 1.5)], -0.2)
            lines: list[str] = cnc.gcode().splitlines()[10:]
            first: str = f"{cycle} X1 Y1 Z-0.2 R0.05"
            if cycle != "G81":
                first += " Q0.05"
            self.assertEqual(
                lines,
                [
                    "(Drill 2 holes to Z-0.2)",
                    "G0 Z1",
                    "G98",
                    f"{first} F4",
                    "X2 Y1.5",
                    "G80",
                ],
            )
            self.assertEqual(cnc.position, (2.0, 1.5, 1.0))

        # Pecks: 0.05 at a time, back up to `R` between them, and back
        # down quickly to just above the last.
        cnc = SCCNC("Test", machine(drill_cycle="moves"))
        cnc.change_tool(2)
        cnc.drill([(1.0, 1.0)], -0.1)
        self.assertEqual(
            cnc.gcode().splitlines()[12:],
            [
                "G0 X1 Y1",
                "G0 Z0.05",
                "G1 Z-0.05 F4",
                "G0 Z0.05",
                "G0 Z0",
                "G1 Z-0.1",
                "G0 Z0.05",
                "G0 Z1",
            ],
        )

        # Only a drill drills.
        with self.assertRaises(ValueError):
            milling().drill([(0.0, 0.0)], -0.1)

    # Method `TestDrill.test_drill_for()`:
    def test_drill_for(self) -> None:
        """The largest drill smaller than the end mill is chosen."""
        mill: SCMachine = machine()
        self.assertEqual(mill.drill_for(mill.tool(1)).number, 2)
        small: SCTool = SCTool(9, "Tiny", "end mill", 0.1, 1, 1.0, 1.0)
        with self.assertRaises(ValueError):
            mill.drill_for(small)

    # Method `TestDrill.test_drilled_pocket()`:
    def test_drilled_pocket(self) -> None:
        """A drilled pocket plunges down its holes, not ramping."""
        cnc: SCCNC = milling()
        poly: SCRoundPoly = rounded_dumbbell()
        entries: list[tuple[float, float]] = cnc.pocket_entries(
            poly, cnc.cutter
        )
        self.assertEqual(len(entries), 2)
        cnc.pocket(poly, -0.25, 0.125, drilled=True)
        lines: list[str] = cnc.gcode().splitlines()

        # Every move down in X and Y together is gone; the plunges are
        # at the entries, at the plunge feed.
        self.assertFalse(
            [line for line in lines if " Z-" in line and " X" in line]
        )
        plunges: list[int] = [
            index
            for index, line in enumerate(lines)
            if line.startswith("G1 Z-") and "F6" in line
        ]
        self.assertEqual(len(plunges), 4)
        for index in plunges:
            self.assertTrue(
                any(
                    f"X{_number(x)} Y{_number(y)}" in " ".join(lines[:index])
                    for x, y in entries
                )
            )

        # A profile goes down at its lead-in's start.
        self.assertEqual(
            cnc.profile_entry(square(2.0, 0.25), cnc.cutter), (-0.375, 1.0)
        )


# Class `TestIslands`:
class TestIslands(unittest.TestCase):
    """Pockets with islands left standing in them."""

    # Method `TestIslands.test_plan()`:
    def test_plan(self) -> None:
        """The wall ring goes around each island, clockwise."""
        poly: SCRoundPoly
        islands: list[SCRoundPoly]
        poly, islands = island_pocket()
        cnc: SCCNC = milling()
        roots: list[SCRing] = cnc.pocket(poly, -0.1, 0.1, islands=islands)
        self.assertEqual(len(roots), 1)
        self.assertEqual(len(roots[0].loops), 4)
        self.assertTrue(roots[0].loops[0].is_ccw())
        self.assertFalse(any(loop.is_ccw() for loop in roots[0].loops[1:]))
        self.assertIn("(Pocket Pocket around 3 islands to Z-0.1)", cnc.gcode())

        # A drill hole for each loop of each ring with nothing in it.
        entries: list[tuple[float, float]] = cnc.pocket_entries(
            poly, cnc.cutter, islands
        )
        loops: int = sum(
            len(ring.loops)
            for root in roots
            for ring, mode in cut_order(root, 0.25)
            if mode == "ramp"
        )
        self.assertEqual(len(entries), loops)

    # Method `TestIslands.test_coverage()`:
    def test_coverage(self) -> None:
        """Every point of the pocket outside the islands is reached."""
        poly: SCRoundPoly
        islands: list[SCRoundPoly]
        poly, islands = island_pocket()
        stepover: float
        for stepover in (0.9, 1.0):
            self.assertEqual(uncut(poly, stepover, 0.01, islands), [])

    # Method `TestIslands.test_gcode()`:
    def test_gcode(self) -> None:
        """No cut comes nearer an island than the tool's radius."""
        poly: SCRoundPoly
        islands: list[SCRoundPoly]
        poly, islands = island_pocket()
        cnc: SCCNC = milling()
        cnc.pocket(poly, -0.1, 0.1, islands=islands)
        holes: list[SCLoop] = [SCLoop.from_poly(island) for island in islands]
        line: str
        for line in cnc.gcode().splitlines():
            found: dict[str, float] = {
                letter: float(value)
                for letter, value in re.findall(r"([XY])(-?[0-9.]+)", line)
            }
            if not line.startswith(("G1", "G2", "G3")) or len(found) < 2:
                continue
            point: tuple[float, float] = (found["X"], found["Y"])
            for hole in holes:
                self.assertFalse(hole.contains(point), line)
                self.assertGreaterEqual(
                    hole.distance(point), 0.125 - 1e-4, line
                )

    # Method `TestIslands.test_bad_islands()`:
    def test_bad_islands(self) -> None:
        """Islands outside the pocket, or crossing, are refused."""
        poly: SCRoundPoly
        islands: list[SCRoundPoly]
        poly, islands = island_pocket()
        cnc: SCCNC = milling()
        outside: SCRoundPoly = square(0.2, 0.0)
        crossing: SCRoundPoly = SCRoundPoly(
            "Across",
            [SCCorner(x, y) for x, y in ((0.2, 1), (0.5, 1), (0.5, 1.2))],
        )
        bad: list[SCRoundPoly]
        for bad in ([outside], [crossing], [islands[0], islands[0]]):
            with self.assertRaises(ValueError):
                cnc.pocket(poly, -0.1, 0.1, islands=bad)


# Class `TestEdges`:
class TestEdges(unittest.TestCase):
    """Cuts through the part, and chamfered or rounded edges."""

    # Method `TestEdges.test_through()`:
    def test_through(self) -> None:
        """A cut through the part goes 10% of its thickness deeper."""
        cnc: SCCNC = milling()
        self.assertAlmostEqual(cnc.below(-0.5), -0.55)
        self.assertEqual(cnc.below(-0.5, through=False), -0.5)
        cnc.profile(square(1.0, 0.25), -0.5, 0.25, through=True)
        self.assertIn("(Profile Square outside to Z-0.55)", cnc.gcode())
        depths: list[str] = [
            line
            for line in cnc.gcode().splitlines()
            if line.startswith("G1 Z")
        ]
        self.assertEqual(depths[-1], "G1 Z-0.55 F6")
        cnc.change_tool(2)
        cnc.drill([(0.0, 0.0)], -0.5, through=True)
        self.assertIn(" Z-0.55 R", cnc.gcode())

    # Method `TestEdges.test_bevel()`:
    def test_bevel(self) -> None:
        """A V-bit runs just off the wall, deep enough to bevel."""
        cnc: SCCNC = milling()
        cnc.change_tool(5)
        path: SCRoundPoly = cnc.chamfer(square(1.0, 0.25), 0.03)
        lines: list[str] = cnc.gcode().splitlines()
        self.assertIn("(Chamfer Square 0.03 wide outside)", lines)

        # 45 degrees: as deep as it is wide (plus the clearance); the
        # tip's center is its radius plus the clearance off the wall.
        self.assertIn("G1 Z-0.035 F4", lines)
        self.assertAlmostEqual(path.corners[0].x, -0.015)
        self.assertFalse(path.is_ccw())
        with self.assertRaises(ValueError):
            cnc.chamfer(square(1.0, 0.25))

        # Inside a hole, it goes around the other way.
        inner: SCRoundPoly = cnc.chamfer(square(1.0, 0.25), 0.03, inside=True)
        self.assertTrue(inner.is_ccw())
        self.assertAlmostEqual(inner.corners[0].x, 0.015)

    # Method `TestEdges.test_round_over()`:
    def test_round_over(self) -> None:
        """A corner rounding bit rides its tip radius off the wall."""
        cnc: SCCNC = milling()
        cnc.change_tool(6)
        path: SCRoundPoly = cnc.chamfer(square(1.0, 0.25))
        lines: list[str] = cnc.gcode().splitlines()
        self.assertIn("(Round over Square to 0.0625 outside)", lines)
        self.assertIn("G1 Z-0.0625 F4", lines)
        self.assertAlmostEqual(path.corners[0].x, -0.0625)

        # An end mill cannot chamfer.
        with self.assertRaises(ValueError):
            milling().chamfer(square(1.0, 0.25), 0.03)


if __name__ == "__main__":
    unittest.main()
