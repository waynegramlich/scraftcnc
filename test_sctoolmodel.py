"""Tests for `sctoolmodel`: the tools' profiles and their models."""

import itertools
import math
import shutil
import unittest
from pathlib import Path
from typing import cast

import sctoolmodel
import shops
from scraftpybind import SCHeadlessTransport, SCPyBind

# The example shop, and an extracted `solidcraft-cli` (as the demo
# uses) for the live test.
HERE: Path = Path(__file__).resolve().parent
SHOP: Path = HERE / "examples/shop/home_shop.toml"
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"


def example_tools() -> dict[int, tuple[str, dict[str, object]]]:
    """Return the example shop mill's tools, by T number."""
    return shops.loaded_tools(shops.read(SHOP), "Shop mill")


class TestProfiles(unittest.TestCase):
    """Each kind of tool's profile."""

    def test_every_tool(self) -> None:
        """Every profile runs from the tip, up, and back to the axis."""
        tools = example_tools()
        self.assertEqual(sorted(tools), [1, 2, 4, 5, 6, 7, 8, 9])
        for number, (key, tool) in tools.items():
            with self.subTest(number=number):
                outline = sctoolmodel.profile(key, tool)
                length = shops.measure(tool["overall_length"], shops.LENGTH)
                self.assertEqual(outline[0], (0.0, 0.0))
                self.assertEqual(outline[-1], (0.0, length))
                self.assertTrue(all(r >= 0 for r, _ in outline))
                self.assertTrue(all(0 <= z <= length for _, z in outline))
                self.assertGreater(len(outline), 3)

    def test_drill_point(self) -> None:
        """A drill's tip is a cone at its point angle."""
        key, tool = example_tools()[4]
        self.assertEqual(key, "drills")
        outline = sctoolmodel.profile(key, tool)
        radius = 15 / 64 / 2
        self.assertAlmostEqual(outline[1][0], radius)
        self.assertAlmostEqual(
            outline[1][1], radius / math.tan(math.radians(59)), places=6
        )

    def test_ball_end(self) -> None:
        """A ball end mill's points around its end are on the ball."""
        key, tool = example_tools()[7]
        outline = sctoolmodel.profile(key, tool)
        radius = 0.125
        ball = [(r, z) for r, z in outline if z <= radius]
        self.assertEqual(len(ball), sctoolmodel.ARC_STEPS + 1)
        for r, z in ball:
            self.assertAlmostEqual(math.hypot(r, z - radius), radius)

    def test_bull_nose(self) -> None:
        """A bull nose's end rounds up to its side."""
        outline = sctoolmodel.profile(
            "end_mills",
            {
                "diameter": "1/2 in",
                "length_of_cut": "1 in",
                "overall_length": "3 in",
                "end": "bull_nose",
                "corner_radius": "1/8 in",
            },
        )
        self.assertEqual(outline[:2], [(0.0, 0.0), (0.125, 0.0)])
        self.assertIn((0.25, 0.125), outline)
        self.assertIn((0.25, 1.0), outline)

    def test_double_angle_at_its_rim(self) -> None:
        """A double angle cutter's included angle is at its rim."""
        outline = sctoolmodel.profile(
            "double_angle_cutters",
            {
                "diameter": "3/4 in",
                "width": "3/8 in",
                "overall_length": "2 in",
                "angle": "60 deg",
            },
        )
        (edge, _), (rim, height) = outline[1], outline[2]
        rim_angle = 2 * math.degrees(math.atan2(height, rim - edge))
        self.assertAlmostEqual(rim_angle, 60.0, places=5)

    def test_countersinks(self) -> None:
        """One end has a shank; two ends mirror each other."""
        sink = {
            "diameter": "1/2 in",
            "drill_diameter": "1/4 in",
            "drill_length": "1/4 in",
            "overall_length": "2 in",
            "angle": "90 deg",
        }
        single = sctoolmodel.profile("single_countersinks", sink)
        self.assertEqual(single[-2:], [(0.25, 2.0), (0.0, 2.0)])
        self.assertAlmostEqual(single[4][1], 0.375)
        double = sctoolmodel.profile("double_countersinks", sink)
        for (r1, z1), (r2, z2) in zip(double, reversed(double)):
            self.assertAlmostEqual(r1, r2)
            self.assertAlmostEqual(z1 + z2, 2.0)
        single_runs = sctoolmodel.tool_flute_runs("single_countersinks", sink)
        double_runs = sctoolmodel.tool_flute_runs("double_countersinks", sink)
        self.assertEqual(len(double_runs), 2 * len(single_runs))

    def test_drill_shank(self) -> None:
        """A drill steps to its shank, where `shank_length` says."""
        drill = {
            "diameter": "1/2 in",
            "length_of_cut": "2 in",
            "overall_length": "4 in",
            "point_angle": "90 deg",
        }
        plain = [(0.0, 0.0), (0.25, 0.25), (0.25, 4.0), (0.0, 4.0)]
        outline = sctoolmodel.profile
        self.assertEqual(outline("drills", drill), plain)
        self.assertEqual(
            outline("drills", {**drill, "shank_length": "1 in"}), plain
        )
        self.assertEqual(
            outline("drills", {**drill, "shank": "1/4 in"})[2:4],
            [(0.25, 2.0), (0.125, 2.0)],
        )
        self.assertEqual(
            outline(
                "drills",
                {**drill, "shank": "3/4 in", "shank_length": "1 in"},
            )[2:5],
            [(0.25, 3.0), (0.375, 3.0), (0.375, 4.0)],
        )

    def test_square_end_and_shank(self) -> None:
        """A rougher's 1/4 in flutes step out to its 3/8 in shank."""
        key, tool = example_tools()[8]
        self.assertEqual(
            sctoolmodel.profile(key, tool),
            [
                (0.0, 0.0),
                (0.125, 0.0),
                (0.125, 0.75),
                (0.1875, 0.75),
                (0.1875, 2.5),
                (0.0, 2.5),
            ],
        )

    def test_chamfer_mill(self) -> None:
        """A 90 degree chamfer mill rises one for one to its diameter."""
        key, tool = example_tools()[5]
        outline = sctoolmodel.profile(key, tool)
        self.assertEqual(outline[1], (0.01, 0.0))
        self.assertAlmostEqual(outline[2][0], 0.0625)
        self.assertAlmostEqual(outline[2][1], 0.0625 - 0.01)

    def test_corner_rounding_mill(self) -> None:
        """A corner rounding mill's quarter circle is hollow."""
        key, tool = example_tools()[6]
        outline = sctoolmodel.profile(key, tool)
        tip, radius = 0.0469 / 2, 0.0625
        arc = outline[1 : 2 + sctoolmodel.ARC_STEPS]
        self.assertAlmostEqual(arc[0][0], tip)
        self.assertAlmostEqual(arc[-1][0], tip + radius)
        self.assertAlmostEqual(arc[-1][1], radius)
        for r, z in arc:
            self.assertAlmostEqual(math.hypot(r - tip - radius, z), radius)

    def test_double_angle_cutter(self) -> None:
        """A double angle cutter's head is widest halfway up."""
        key, tool = example_tools()[9]
        outline = sctoolmodel.profile(key, tool)
        self.assertEqual(
            outline[1:4], [(0.0625, 0.0), (0.125, 0.0625), (0.0625, 0.125)]
        )

    def test_unknown_kind(self) -> None:
        """A tool of another kind is a plain cylinder."""
        self.assertEqual(
            sctoolmodel.profile(
                "probes", {"diameter": "1/8 in", "overall_length": "2 in"}
            ),
            [(0.0, 0.0), (0.0625, 0.0), (0.0625, 2.0), (0.0, 2.0)],
        )


@unittest.skipUnless(
    shutil.which("solidcraft-cli") or CLI.exists(), "no solidcraft-cli"
)
class TestModel(unittest.TestCase):
    """A tool modeled in a headless SolidCraft."""

    def test_drill(self) -> None:
        """The 15/64 in drill stands on its tip at the origin."""
        key, tool = example_tools()[4]
        cli = "solidcraft-cli" if shutil.which("solidcraft-cli") else str(CLI)
        with SCHeadlessTransport(cli=cli) as transport:
            solidcraft = SCPyBind(transport)
            body = sctoolmodel.model(
                solidcraft, "Drill", sctoolmodel.profile(key, tool)
            )
            solidcraft.component.from_bodies(bodies=[body])
            properties = solidcraft.occurrence.properties(
                occurrence=f"{body}:1"
            )
        assert isinstance(properties, dict)
        box = properties["total"]["bbox"]
        radius = 15 / 64 / 2 * 25.4
        for got, want in zip(
            box["min"] + box["max"],
            [-radius, -radius, 0.0, radius, radius, 3.875 * 25.4],
            strict=True,
        ):
            self.assertAlmostEqual(got, want, places=3)


class TestFlutes(unittest.TestCase):
    """The lines that stand for a tool's flutes."""

    def setUp(self) -> None:
        """Index the example shop's tools by their `unique_id`."""
        self.tools = {
            tool["unique_id"]: (key, tool)
            for key, tool in sctoolmodel.shop_tools(shops.read(SHOP))
        }

    def test_every_tool_has_lines(self) -> None:
        """Every tool's lines stay on the tool, and none is degenerate."""
        for key, tool in self.tools.values():
            with self.subTest(tool=tool["name"]):
                length = shops.measure(tool["overall_length"], shops.LENGTH)
                runs = sctoolmodel.tool_flute_runs(key, tool)
                self.assertTrue(runs)
                for _, points in runs:
                    self.assertGreaterEqual(len(points), 2)
                    for _, _, z in points:
                        self.assertLess(z, length)

    def test_path_stops_at_length_of_cut(self) -> None:
        """A drill's flutes end at its `length_of_cut`, on its side."""
        key, tool = self.tools[5]
        path = sctoolmodel.flute_path(key, tool)
        cut = shops.measure(tool["length_of_cut"], shops.LENGTH)
        radius = shops.measure(tool["diameter"], shops.LENGTH) / 2
        self.assertEqual(path[0], (0.0, 0.0))
        self.assertAlmostEqual(path[-1][0], radius)
        self.assertAlmostEqual(path[-1][1], cut)

    def test_helical_edges(self) -> None:
        """Each helical flute has two edges, splines, off the tip."""
        key, tool = self.tools[4]
        runs = sctoolmodel.tool_flute_runs(key, tool)
        self.assertEqual(len(runs), 2 * cast(int, tool["flutes"]))
        for command, points in runs:
            self.assertEqual(command, "sketch.spline3d")
            self.assertGreater(points[0][0] ** 2 + points[0][1] ** 2, 0.01)

    def test_helix_lead(self) -> None:
        """A helix turns by the rise over its lead, right handed."""
        points = sctoolmodel.flute_runs(
            [(0.0, 0.0), (1.0, 0.0), (1.0, 10.0)], 1, 30.0
        )[0][1]
        lifted = 1.0 + sctoolmodel.FLUTE_LIFT
        lead = 2.0 * math.pi * lifted / math.tan(math.radians(30.0))
        rise = points[1][2] - points[0][2]
        turned = math.atan2(points[1][1], points[1][0]) - math.atan2(
            points[0][1], points[0][0]
        )
        self.assertAlmostEqual(turned, 2.0 * math.pi * rise / lead)
        self.assertGreater(turned, 0.0)

    def test_runout_closes(self) -> None:
        """A flute's two edges meet where the flute ends."""
        runs = sctoolmodel.flute_runs(
            [(0.0, 0.0), (1.0, 0.0), (1.0, 10.0)], 1, 30.0
        )
        for first, second in zip(runs[0][1][-1], runs[1][1][-1], strict=True):
            self.assertAlmostEqual(first, second)

    def test_straight_flutes(self) -> None:
        """Straight flutes are one line each, off the surface."""
        key, tool = self.tools[7]
        runs = sctoolmodel.tool_flute_runs(key, tool)
        self.assertEqual(len(runs), tool["flutes"])
        for command, points in runs:
            self.assertEqual(command, "sketch.line3d")
            self.assertLess(points[0][2], 0.0)

    def test_no_line_on_the_flat(self) -> None:
        """A straight fluted tool's line starts past the flat on its tip."""
        key, tool = self.tools[7]
        tip = shops.measure(tool["tip_diameter"], shops.LENGTH) / 2
        self.assertEqual(sctoolmodel.flute_path(key, tool)[0], (tip, 0.0))

    def test_no_known_flutes(self) -> None:
        """A kind of tool with no known flutes gets no lines."""
        self.assertEqual(sctoolmodel.tool_flute_runs("other", {}), [])

    def test_steps(self) -> None:
        """The steps place the lines, in millimeters, in one sketch."""
        steps = sctoolmodel.flute_steps(
            "T",
            [("sketch.line3d", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])],
            (1.0, 2.0, 3.0),
        )
        self.assertEqual(steps[0]["command"], "sketch.create")
        self.assertEqual(steps[-1]["command"], "sketch.finish")
        params = cast(dict[str, list[list[float]]], steps[2]["params"])
        for found, expected in zip(
            itertools.chain(*params["points"]),
            (25.4, 50.8, 76.2, 50.8, 50.8, 76.2),
            strict=True,
        ):
            self.assertAlmostEqual(found, expected)

    def test_lift(self) -> None:
        """A flat end and a side each stand off by the whole lift."""
        lift = sctoolmodel.FLUTE_LIFT
        points = sctoolmodel.flute_runs(
            [(0.0, 0.0), (1.0, 0.0), (1.0, 0.1)], 1
        )[0][1]
        self.assertAlmostEqual(points[0][2], -lift)
        self.assertAlmostEqual(points[1][0], 1.0 + lift)
        self.assertAlmostEqual(points[1][2], -lift)
        self.assertAlmostEqual(points[2][0], 1.0 + lift)


class TestHolders(unittest.TestCase):
    """The holders: truncated cones with resistor color code bands."""

    def setUp(self) -> None:
        self.shop = shops.read(SHOP)
        self.tools = sctoolmodel.shop_tools(self.shop)
        self.tool = dict(self.tools[0][1])

    def test_tools_in_order(self) -> None:
        """Every tool, loaded or not, comes in `unique_id` order."""
        self.assertEqual(
            [tool["unique_id"] for _, tool in self.tools],
            list(range(1, 13)),
        )

    def test_digits(self) -> None:
        """The longest number sets the number of bands."""
        self.assertEqual(sctoolmodel.unique_id_digits(self.tools), 2)
        self.assertEqual(sctoolmodel.unique_id_digits(self.tools[:9]), 1)
        self.assertEqual(sctoolmodel.unique_id_digits([]), 1)

    def test_colors(self) -> None:
        """Bands read from the base, with leading zeros."""
        colors = sctoolmodel.RESISTOR_COLORS
        for number, digits, expected in (
            (1, 2, (0, 1)),
            (47, 2, (4, 7)),
            (305, 3, (3, 0, 5)),
            (9, 1, (9,)),
        ):
            self.tool["unique_id"] = number
            bands = sctoolmodel.holder_bands(self.tool, digits)
            self.assertEqual(
                [color for color, _ in bands],
                [colors[digit] for digit in expected],
            )

    def test_cone(self) -> None:
        """The bands stack up into one straight truncated cone."""
        self.tool["unique_id"] = 123
        self.tool["holder"] = ["r8", "1/4 in"]
        bands = sctoolmodel.holder_bands(self.tool, 3)

        # They meet, from the base at the top down to the tool end.
        length = sctoolmodel.HOLDER_LENGTH
        self.assertAlmostEqual(bands[0][1][2][1], length)
        self.assertAlmostEqual(bands[-1][1][0][1], 0.0)
        for upper, lower in itertools.pairwise(bands):
            self.assertAlmostEqual(upper[1][0][1], lower[1][3][1])
            self.assertAlmostEqual(upper[1][1][0], lower[1][2][0])

        # The ends have the right radii.
        self.assertAlmostEqual(
            bands[0][1][2][0], sctoolmodel.HOLDER_BASE_DIAMETER / 2
        )
        self.assertAlmostEqual(
            bands[-1][1][1][0], (0.25 + sctoolmodel.HOLDER_WALL) / 2
        )

    def test_wide_bore(self) -> None:
        """A bore wider than the base widens the base: no upside down cone."""
        self.tool["holder"] = ["cat50", "2 in"]
        bands = sctoolmodel.holder_bands(self.tool, 1)
        self.assertEqual(bands[0][1][1][0], bands[0][1][2][0])


if __name__ == "__main__":
    unittest.main()
