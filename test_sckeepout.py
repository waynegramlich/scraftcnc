"""Tests for `sckeepout`: programs against a Table/Vise/Parallels setup."""

import json
import math
import random
import unittest

import sckeepout
import scsetup
from scgeometry import SLOP, SCArc, SCLine
from scmachine import SCMachine, SCTool
from shops import cnc_machine, read
from solidcraftcnc import SCCNC
from solidcraftcnc_demo import MACHINE, MATERIAL, SHOP_FILE, cut_demo

JAWS = ("Kurt D688 fixed jaw", "Kurt D688 movable jaw")
PARALLELS = ("Parallel 1-1/2 in A", "Parallel 1-1/2 in B")

# Each zone's top, in inches from the top of the 1/2 in material.
TOPS = {
    "Mikini 1610L": -4.515,
    "Kurt D688 base to bed": -1.875,
    JAWS[0]: -0.14,
    JAWS[1]: -0.14,
    PARALLELS[0]: -0.375,
    PARALLELS[1]: -0.375,
}


def setup_zones():
    """Return the example setup's zones."""
    setup = scsetup.SCSetup(
        json.loads(scsetup.EXAMPLE.read_text(encoding="utf-8"))
    )
    return sckeepout.work_zones(setup, setup.materials[0])


def machine(tools=()):
    """Return a small machine, whose T1 is a 1/4 in end mill."""
    return SCMachine(
        name="Test mill",
        z_safe=1.0,
        clearance=0.05,
        tool_change_z=2.0,
        tool_change="T{number:02d}",
        rapid_speed=60.0,
        drill_cycle="G83",
        through_overcut=0.1,
        stepover=0.9,
        ramp_angle=3.0,
        tools=(
            SCTool(1, "End mill", "end mill", 0.25, 1200, 12.0, 6.0),
            SCTool(2, "Drill", "drill", 0.25, 1200, 4.0, 4.0, 0.05),
            *tools,
        ),
    )


def program(number=1, tools=()):
    """Return a program with a tool in the spindle, at `z_safe`."""
    cnc = SCCNC("Test", machine(tools))
    cnc.change_tool(number)
    cnc.rapid(z=1.0)
    return cnc


def rectangle_distance(point, box):
    """Return how far a point is from a box, with no `scgeometry`."""
    low_x, high_x, low_y, high_y = box
    across = max(low_x - point[0], 0.0, point[0] - high_x)
    along = max(low_y - point[1], 0.0, point[1] - high_y)
    return math.hypot(across, along)


class TestZones(unittest.TestCase):
    """The setup's prisms, as zones from the middle of the material."""

    def test_tops(self) -> None:
        """Each zone reaches the height that was worked out by hand."""
        zones = setup_zones()
        self.assertEqual({zone.name for zone in zones}, set(TOPS))
        for zone in zones:
            self.assertAlmostEqual(zone.z_end, TOPS[zone.name], places=6)

    def test_boxes(self) -> None:
        """The zones' sides are where they were worked out by hand."""
        boxes = {zone.name: zone.box for zone in setup_zones()}
        expected = {
            "Mikini 1610L": (-15.125, 15.125, -5.375, 5.375),
            JAWS[0]: (-3.125, 3.125, 2.875, 4.85),
            JAWS[1]: (-3.125, 3.125, -12.15, -2.875),
            PARALLELS[0]: (-3.125, 3.125, 2.75, 3.125),
            PARALLELS[1]: (-3.125, 3.125, -3.125, -2.75),
        }
        for name, box in expected.items():
            for got, want in zip(boxes[name], box):
                self.assertAlmostEqual(got, want, places=6)

    def test_material_elsewhere(self) -> None:
        """The zones follow the work origin."""
        data = json.loads(scsetup.EXAMPLE.read_text(encoding="utf-8"))
        data["materials"][0]["location"] = ["1 in", "0 in"]
        data["materials"][0]["height"] = "4.5 in"
        data["materials"][0]["parts"] = []
        setup = scsetup.SCSetup(data)
        zones = sckeepout.work_zones(setup, setup.materials[0])
        table = next(zone for zone in zones if zone.name == "Mikini 1610L")
        self.assertAlmostEqual(table.box[1], 14.125, places=6)
        self.assertAlmostEqual(table.z_end, 0.125 - 5.0, places=6)


class TestCrashes(unittest.TestCase):
    """A deliberate crash into each zone, for each kind of move."""

    def hits(self, cnc, name):
        """Return whether a program's last line enters a zone."""
        last = len(cnc.commands)
        return any(
            found.kind == "keep out"
            and found.zone == name
            and found.line == last
            for found in sckeepout.check_program(cnc, setup_zones())
        )

    def sides(self, zone):
        """Yield the middle of each side of a zone, with its way out."""
        low_x, high_x, low_y, high_y = zone.box
        middle_x = (low_x + high_x) / 2.0
        middle_y = (low_y + high_y) / 2.0
        yield (high_x, middle_y), (1.0, 0.0)
        yield (low_x, middle_y), (-1.0, 0.0)
        yield (middle_x, high_y), (0.0, 1.0)
        yield (middle_x, low_y), (0.0, -1.0)

    def line_to(self, zone, edge, out, gap):
        """Return a program going straight at a side, stopping `gap` off."""
        z = zone.z_end - 0.01
        cnc = program()
        far = 1.125
        cnc.rapid(edge[0] + out[0] * far, edge[1] + out[1] * far)
        cnc.rapid(z=z)
        reach = 0.125 + gap
        cnc.linear(edge[0] + out[0] * reach, edge[1] + out[1] * reach)
        return cnc

    def arc_past(self, zone, edge, out, gap):
        """Return a program whose half circle comes `gap` off a side."""
        z = zone.z_end - 0.01
        radius = 1.0
        center = (
            edge[0] + out[0] * (0.125 + gap + radius),
            edge[1] + out[1] * (0.125 + gap + radius),
        )
        side = (-out[1], out[0])
        start = (center[0] + side[0] * radius, center[1] + side[1] * radius)
        end = (center[0] - side[0] * radius, center[1] - side[1] * radius)
        cnc = program()
        cnc.rapid(*start)
        cnc.rapid(z=z)
        cnc.arc(SCArc(start, end, center, radius, math.pi))
        return cnc

    def test_vertical(self) -> None:
        """Going straight down hits a zone just below its top, not above."""
        for zone in setup_zones():
            low_x, high_x, low_y, high_y = zone.box
            x = (low_x + high_x) / 2.0
            y = (low_y + high_y) / 2.0
            with self.subTest(zone=zone.name):
                for z, expected in (
                    (zone.z_end - 0.01, True),
                    (zone.z_end + 0.01, False),
                ):
                    cnc = program()
                    cnc.rapid(x, y)
                    cnc.linear(z=z)
                    self.assertEqual(self.hits(cnc, zone.name), expected)

    def test_lines(self) -> None:
        """A line stops short of each grown side, or goes in."""
        for zone in setup_zones():
            for edge, out in self.sides(zone):
                with self.subTest(zone=zone.name, out=out):
                    self.assertTrue(
                        self.hits(
                            self.line_to(zone, edge, out, -0.01), zone.name
                        )
                    )
                    self.assertFalse(
                        self.hits(
                            self.line_to(zone, edge, out, 0.01), zone.name
                        )
                    )

    def test_arcs(self) -> None:
        """Only the middle of an arc comes near each side."""
        for zone in setup_zones():
            for edge, out in self.sides(zone):
                with self.subTest(zone=zone.name, out=out):
                    self.assertTrue(
                        self.hits(
                            self.arc_past(zone, edge, out, -0.01), zone.name
                        )
                    )
                    self.assertFalse(
                        self.hits(
                            self.arc_past(zone, edge, out, 0.01), zone.name
                        )
                    )

    def test_ramp(self) -> None:
        """A ramp is tested at its lowest Z."""
        cnc = program()
        cnc.rapid(0.0, 2.0)
        cnc.rapid(z=0.0)
        cnc.linear(y=3.5, z=-0.2)
        self.assertTrue(self.hits(cnc, JAWS[0]))

    def test_helix(self) -> None:
        """A whole circle going down is tested at its lowest Z."""
        cnc = program()
        cnc.rapid(0.0, 2.0)
        cnc.rapid(z=0.0)
        center = (0.0, 2.25)
        cnc.arc(
            SCArc((0.0, 2.0), (0.0, 2.0), center, 0.25, 2.0 * math.pi), -0.2
        )
        self.assertFalse(self.hits(cnc, JAWS[0]))
        cnc = program()
        cnc.rapid(0.0, 2.0)
        cnc.rapid(z=0.0)
        center = (0.0, 2.5)
        cnc.arc(
            SCArc((0.0, 2.0), (0.0, 2.0), center, 0.5, 2.0 * math.pi), -0.2
        )
        self.assertTrue(self.hits(cnc, JAWS[0]))

    def test_cycle(self) -> None:
        """A canned cycle is a vertical move down to its bottom."""
        cnc = program(2)
        cnc.drill([(0.0, 3.5)], -0.2)
        found = sckeepout.check_program(cnc, setup_zones())
        self.assertEqual(
            [item.zone for item in found if item.kind == "keep out"],
            [JAWS[0]],
        )
        cnc = program(2)
        cnc.drill([(0.0, 0.0)], -0.5, through=True)
        self.assertEqual(sckeepout.check_program(cnc, setup_zones()), [])

    def test_widest_radius(self) -> None:
        """A chamfer bit is checked at its widest, not at its tip."""
        narrow = SCTool(5, "Tip", "chamfer", 0.02, 1200, 12.0, 4.0, angle=90.0)
        wide = SCTool(
            5, "Wide", "chamfer", 0.02, 1200, 12.0, 4.0, angle=90.0, widest=0.5
        )
        results = []
        for tool in (narrow, wide):
            cnc = program(5, (tool,))
            cnc.rapid(0.0, 2.5)
            cnc.linear(z=-0.2)
            results.append(self.hits(cnc, PARALLELS[0]))
        self.assertEqual(results, [False, False])
        results = []
        for tool in (narrow, wide):
            cnc = program(5, (tool,))
            cnc.rapid(0.0, 2.6)
            cnc.linear(z=-0.45)
            results.append(self.hits(cnc, PARALLELS[0]))
        self.assertEqual(results, [False, True])

    def test_every_zone_is_reported(self) -> None:
        """Nothing stops at the first violation."""
        cnc = program()
        cnc.rapid(0.0, 3.0)
        cnc.linear(z=-5.0)
        names = {
            found.zone
            for found in sckeepout.check_program(cnc, setup_zones())
            if found.kind == "keep out"
        }
        self.assertEqual(names, set(TOPS) - {JAWS[1], PARALLELS[1]})


class TestBruteForce(unittest.TestCase):
    """The answers against plain distances, with no offsets."""

    def test_random_moves(self) -> None:
        """Walk points along random moves and measure them directly."""
        generator = random.Random(4)
        zones = setup_zones()
        checked = 0
        for _ in range(4000):
            radius = generator.uniform(0.02, 0.5)
            start = (generator.uniform(-18, 18), generator.uniform(-14, 8))
            end = (
                start[0] + generator.uniform(-6, 6),
                start[1] + generator.uniform(-6, 6),
            )
            z = generator.uniform(-6.0, 0.5)
            if generator.random() < 0.5:
                move = SCLine(start, end)
                points = [
                    (
                        start[0] + (end[0] - start[0]) * index / 500,
                        start[1] + (end[1] - start[1]) * index / 500,
                    )
                    for index in range(501)
                ]
            else:
                code = generator.choice((2, 3))
                # Keep the center equally far from both ends.
                chord = (end[0] - start[0], end[1] - start[1])
                length = math.hypot(*chord) or 1.0
                along = generator.uniform(-3, 3)
                offset = (
                    chord[0] / 2.0 - chord[1] / length * along,
                    chord[1] / 2.0 + chord[0] / length * along,
                )
                move = sckeepout.arc_segments(start, end, offset, code)[0]
                center = move.center
                first = math.atan2(start[1] - center[1], start[0] - center[0])
                points = [
                    (
                        center[0]
                        + move.radius
                        * math.cos(first + move.sweep * index / 800),
                        center[1]
                        + move.radius
                        * math.sin(first + move.sweep * index / 800),
                    )
                    for index in range(801)
                ]
            for zone in zones:
                if zone.z_end <= z:
                    self.assertFalse(zone.hits(move, z, radius))
                    continue
                nearest = min(
                    rectangle_distance(point, zone.box) for point in points
                )
                # The walk can miss a little, and the zone grows by `SLOP`.
                if abs(nearest - radius) < 0.02:
                    continue
                checked += 1
                self.assertEqual(
                    zone.hits(move, z, radius),
                    nearest < radius,
                    (zone.name, move, z, radius, nearest),
                )
        self.assertGreater(checked, 5000)
        self.assertLess(SLOP, 0.02)


class TestRapids(unittest.TestCase):
    """Rapids belong at `z_safe`."""

    def kinds(self, cnc):
        """Return the texts of a program's rapid violations."""
        return [
            found.text
            for found in sckeepout.check_program(cnc, [])
            if found.kind == "rapid"
        ]

    def test_sideways(self) -> None:
        """Sideways below `z_safe` is reported, and at it is not."""
        cnc = program()
        cnc.rapid(1.0, 1.0)
        self.assertEqual(self.kinds(cnc), [])
        cnc.linear(z=0.5)
        cnc.rapid(2.0, 1.0)
        self.assertEqual(len(self.kinds(cnc)), 1)

    def test_down_and_up(self) -> None:
        """Going down below `z_safe` is reported; going up never is."""
        cnc = program()
        cnc.rapid(1.0, 1.0)
        cnc.rapid(z=0.05)
        self.assertEqual(len(self.kinds(cnc)), 1)
        cnc.linear(z=-0.2)
        cnc.rapid(z=1.0)
        self.assertEqual(len(self.kinds(cnc)), 1)

    def test_drill(self) -> None:
        """A drill may rapid down, but only to above `z_top`."""
        cnc = program(2)
        cnc.rapid(1.0, 1.0)
        cnc.rapid(z=0.05)
        self.assertEqual(self.kinds(cnc), [])
        cnc.rapid(z=-0.1)
        self.assertEqual(len(self.kinds(cnc)), 1)

    def test_cycle_is_exempt(self) -> None:
        """A canned cycle's own rapids are allowed."""
        cnc = program(2)
        cnc.drill([(1.0, 1.0), (2.0, 2.0)], -0.3)
        self.assertEqual(self.kinds(cnc), [])


class TestUnchecked(unittest.TestCase):
    """What the checker does not understand is reported, never passed."""

    def text(self, cnc):
        """Return a program's `unchecked` lines."""
        return [
            found.line
            for found in sckeepout.check_program(cnc, [])
            if found.kind == "unchecked"
        ]

    def test_nothing_is_unchecked(self) -> None:
        """An ordinary program has none."""
        cnc = program()
        cnc.rapid(1.0, 1.0)
        cnc.linear(z=-0.2)
        cnc.finish()
        self.assertEqual(self.text(cnc), [])

    def test_bare_axes(self) -> None:
        """A line of just X and Y is the old form of a canned cycle."""
        cnc = program()
        cnc.add({"X": 1.0, "Y": 1.0})
        self.assertEqual(self.text(cnc), [len(cnc.commands)])

    def test_unknown_code(self) -> None:
        """A `G` code that is not known is reported."""
        cnc = program()
        cnc.add({"G": 41})
        self.assertEqual(self.text(cnc), [len(cnc.commands)])

    def test_cycle_with_axes(self) -> None:
        """A cycle with its own X and Y is a combined command."""
        cnc = program(2)
        cnc.rapid(1.0, 1.0)
        cnc.add({"G": 83, "X": 2.0, "Y": 2.0, "Z": -1.0, "R": 0.05})
        self.assertEqual(self.text(cnc), [len(cnc.commands)])

    def test_no_tool(self) -> None:
        """A cut with no tool known is reported."""
        cnc = SCCNC("Test", machine())
        cnc.add({"G": 0, "X": 1.0, "Y": 1.0})
        cnc.add({"G": 1, "Z": -0.5, "F": 5.0})
        self.assertEqual(self.text(cnc), [len(cnc.commands)])

    def test_not_known_low(self) -> None:
        """A move below `z_safe` from an unknown place is reported."""
        cnc = SCCNC("Test", machine())
        cnc.commands.clear()
        cnc.add({"G": 0, "Z": 0.0})
        self.assertEqual(self.text(cnc), [1])


class TestPrograms(unittest.TestCase):
    """Whole programs on the Table/Vise/Parallels setup."""

    def test_demo_is_clear(self) -> None:
        """The demonstration plate stays out of every zone."""
        setup = scsetup.SCSetup(
            json.loads(sckeepout.DEMO_SETUP.read_text(encoding="utf-8"))
        )
        cnc = cut_demo()[0]
        cnc.remap(0, -2.0, -1.5)
        found = sckeepout.check_program(
            cnc, sckeepout.work_zones(setup, setup.materials[0])
        )
        self.assertEqual(found, [])

    def test_tooling_plate_fails_as_predicted(self) -> None:
        """The tooling plate's long edges, and nothing else, enter zones."""
        setup = scsetup.SCSetup(
            json.loads(scsetup.EXAMPLE.read_text(encoding="utf-8"))
        )
        material = setup.materials[0]
        cnc = sckeepout.tooling_plate_program(
            material.parts[0].placement.turns,
            sckeepout.shop_machine_with_hole_drill(),
        )
        zones = sckeepout.work_zones(setup, material)
        found = sckeepout.check_program(cnc, zones)
        self.assertEqual({item.kind for item in found}, {"keep out"})
        names = {item.zone for item in found if item.kind == "keep out"}
        self.assertEqual(names, set(JAWS) | set(PARALLELS))

        # All of the holes are clear, since the end mill alone is reported.
        hits = [item for item in found if item.kind == "keep out"]
        change = next(
            line
            for line, command in enumerate(cnc.commands, 1)
            if str(command.get("T", "")) == "01"
            or command.get("note") == "1/4 in 2 flute carbide end mill"
        )
        self.assertTrue(all(item.line > change for item in hits))
        self.assertTrue(all("T1 " in item.text for item in hits))

        # Hand figures: each line's reach, and below which zone's top.
        bad = {item.line: [] for item in hits}
        for item in hits:
            bad[item.line].append(item.zone)
        tracker = {"X": None, "Y": None, "Z": None}
        for line, command in enumerate(cnc.commands, 1):
            old = dict(tracker)
            for letter in "XYZ":
                if letter in command:
                    tracker[letter] = float(command[letter])
            if line <= change or old["X"] is None or line not in bad:
                continue
            low_z = min(old["Z"], tracker["Z"])
            for zone in bad[line]:
                self.assertLess(low_z, TOPS[zone], (line, zone))
            # The end mill's center is on or beyond a long side's path.
            self.assertGreater(
                max(abs(old["Y"]), abs(tracker["Y"])), 2.75, line
            )

        # The short ends are clear, at every depth.
        tracker = {"X": None, "Y": None, "Z": None}
        ends = 0
        for line, command in enumerate(cnc.commands, 1):
            old = dict(tracker)
            for letter in "XYZ":
                if letter in command:
                    tracker[letter] = float(command[letter])
            if (
                command.get("G") == 1
                and "Y" in command
                and old["Y"] != tracker["Y"]
                and abs(abs(tracker["X"]) - 5.375) < 0.001
            ):
                ends += 1
                self.assertNotIn(line, bad)
        self.assertGreater(ends, 0)

        # The first pass is above every top, and the next is not.
        depths = sorted(
            {
                float(command["Z"])
                for command in cnc.commands[change:]
                if command.get("G") == 1 and float(command.get("Z", 1.0)) < 0.0
            },
            reverse=True,
        )
        self.assertGreater(depths[0], -0.14)
        self.assertLess(depths[1], -0.14)
        shallow = [
            float(command["Z"])
            for line, command in enumerate(cnc.commands, 1)
            if line in bad and "Z" in command and command.get("G") == 1
        ]
        self.assertLess(max(shallow), -0.14)


class TestReport(unittest.TestCase):
    """The report."""

    def test_counts_and_lines(self) -> None:
        """It counts them, and shows each with its G-code line."""
        cnc = program()
        cnc.rapid(0.0, 3.5)
        cnc.linear(z=-0.2)
        text = sckeepout.report(
            cnc, sckeepout.check_program(cnc, setup_zones())
        )
        self.assertIn("1 keep out: Kurt D688 fixed jaw", text)
        self.assertIn("G1 Z-0.2", text)
        self.assertIn(f"line {len(cnc.commands)}:", text)

    def test_shop_tools_know_their_widest(self) -> None:
        """The shop's chamfer and corner rounding bits report their widest."""
        shop = cnc_machine(read(SHOP_FILE), MACHINE, MATERIAL)
        chamfer = shop.named("1/8 in 90 deg carbide chamfer mill")
        self.assertAlmostEqual(chamfer.widest_radius(), 0.0625)
        self.assertLess(chamfer.diameter, chamfer.widest)
        rounding = shop.named("1/16 in radius carbide corner rounding mill")
        self.assertAlmostEqual(
            rounding.widest_radius(),
            rounding.diameter / 2.0 + rounding.radius,
        )


if __name__ == "__main__":
    unittest.main()
