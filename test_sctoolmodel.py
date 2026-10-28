"""Tests for `sctoolmodel`: the tools' profiles and their models."""

import math
import shutil
import unittest
from pathlib import Path

import sctoolmodel
import shops
from scraftpybind import HeadlessTransport, SolidCraftPyBind

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
        with HeadlessTransport(cli=cli) as transport:
            solidcraft = SolidCraftPyBind(transport)
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


if __name__ == "__main__":
    unittest.main()
