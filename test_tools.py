"""Tests for `tools`: the mill tables and their models."""

import math
import shutil
import unittest
from pathlib import Path

import tools
from scraftpybind import JSON, HeadlessTransport, SolidCraftPyBind

# An extracted `solidcraft-cli` (as the demo uses) for the live test.
HERE: Path = Path(__file__).resolve().parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"


class TestMillTables(unittest.TestCase):
    """The numbers describing the tables."""

    def test_mills(self) -> None:
        """The three entry level mills are there, smallest first."""
        names = [table.name for table in tools.MILL_TABLES]
        self.assertEqual(names, ["Tormach 440", "Tormach 770", "Tormach 1100"])

    def test_slots_fit(self) -> None:
        """Each table's slots and pockets lie inside it, apart."""
        for table in tools.MILL_TABLES:
            with self.subTest(table=table.name):
                centers = table.slot_centers()
                self.assertEqual(len(centers), table.slots)
                self.assertEqual(centers[0], -centers[-1])
                self.assertLess(
                    centers[-1] + table.head_width / 2.0, table.width / 2.0
                )
                self.assertLess(table.head_width, table.slot_spacing)
                self.assertLess(table.slot_depth, table.thickness)
                self.assertLess(table.throat_depth, table.slot_depth)
                self.assertLess(table.throat_width, table.head_width)
                self.assertLess(
                    table.slot_length + 2.0 * table.pocket_length,
                    table.length,
                )
                self.assertLess(table.pocket_width, table.width)

    def test_slot_outline(self) -> None:
        """A slot's outline is symmetric, and open at the table's top."""
        for table in tools.MILL_TABLES:
            with self.subTest(table=table.name):
                outline = table.slot_outline()
                self.assertEqual(outline[0][1], 0.0)
                self.assertEqual(outline[-1][1], 0.0)
                self.assertEqual(outline[0][0], -outline[-1][0])
                self.assertEqual(min(z for _, z in outline), -table.slot_depth)


class TestKeepOut(unittest.TestCase):
    """Growing the keep-out regions."""

    def test_grown(self) -> None:
        """A prism grows by the margin on all six sides."""
        prism = tools.Prism("Box", (0.0, 1.0, 2.0), (3.0, 5.0, 7.0))
        grown = prism.grown(1.0)
        self.assertEqual(grown.low, (-1.0, 0.0, 1.0))
        self.assertEqual(grown.high, (4.0, 6.0, 8.0))
        self.assertEqual(grown.name, "Box")

    def test_empty_prism(self) -> None:
        """A prism with no size on some axis is refused."""
        with self.assertRaises(ValueError):
            tools.Prism("Flat", (0.0, 0.0, 0.0), (1.0, 1.0, 0.0))

    def test_margin_units(self) -> None:
        """A margin is read with its unit."""
        prism = tools.Prism("Box", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        for margin in ("1/8 in", "1/8 inch", "3.175 mm"):
            with self.subTest(margin=margin):
                grown = tools.KeepOut().add_prism(prism, margin)
                self.assertAlmostEqual(grown.low[0], -3.175)
                self.assertAlmostEqual(grown.high[2], 4.175)

    def test_one_per_table(self) -> None:
        """Each table's prism encloses it, 1/8 inch away."""
        tormach = tools.Tormach(None)  # type: ignore[arg-type]
        keep_out = tormach.mill_table_keep_out()
        self.assertEqual(len(keep_out.prisms), len(tools.MILL_TABLES))
        for table, prism in zip(tools.MILL_TABLES, keep_out.prisms):
            with self.subTest(table=table.name):
                self.assertAlmostEqual(
                    prism.high[0] - prism.low[0], table.length + 6.35
                )
                self.assertAlmostEqual(
                    prism.high[1] - prism.low[1], table.width + 6.35
                )
                self.assertAlmostEqual(
                    prism.high[2] - prism.low[2], table.thickness + 6.35
                )
                self.assertAlmostEqual(prism.high[2], 3.175)


class TestDrill(unittest.TestCase):
    """The numbers describing a drill."""

    def test_section(self) -> None:
        """The outline closes, with a groove and an edge per flute."""
        for flutes in range(1, 6):
            with self.subTest(flutes=flutes):
                arcs = tools.Drill("D", 20.0, 100.0, flutes).section()
                self.assertEqual(len(arcs), 2 * flutes)
                for (_, _, end), (start, _, _) in zip(
                    arcs, arcs[1:] + arcs[:1]
                ):
                    self.assertAlmostEqual(end[0], start[0])
                    self.assertAlmostEqual(end[1], start[1])

                # Grooves reach half the radius; edges stay on the radius.
                for index, (start, through, _) in enumerate(arcs):
                    self.assertAlmostEqual(math.hypot(*start), 10.0)
                    self.assertAlmostEqual(
                        math.hypot(*through), 10.0 if index % 2 else 5.0
                    )

    def test_flat_tip_has_no_height(self) -> None:
        """A flat tip's height is exactly zero."""
        drill = tools.Drill("D", 20.0, 100.0, 2, point_angle=180.0)
        self.assertEqual(drill.point_height(), 0.0)

    def test_refused(self) -> None:
        """Numbers that make no drill are refused."""
        for args in (
            (0.0, 100.0, 2),
            (10.0, 100.0, 0),
            (10.0, 100.0, 6),
            (10.0, 100.0, 2, 100.0),
            (10.0, 1.0, 2),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tools.Drill("D", *args)

    def test_cylinder(self) -> None:
        """The cylinder encloses the drill, up from its tip."""
        drill = tools.Drill("D", 20.0, 100.0, 2, 40.0, 30.0)
        cylinder = drill.cylinder((1.0, 2.0, 3.0))
        self.assertEqual(cylinder.center, (1.0, 2.0))
        self.assertEqual((cylinder.low, cylinder.high), (3.0, 103.0))
        self.assertEqual(cylinder.radius, 15.0)

    def test_cylinder_grown(self) -> None:
        """A keep-out grows the side and both ends by the margin."""
        cylinder = tools.Cylinder("C", (0.0, 0.0), 0.0, 10.0, 5.0)
        grown = tools.KeepOut().add_cylinder(cylinder, "1/8 in")
        self.assertAlmostEqual(grown.low, -3.175)
        self.assertAlmostEqual(grown.high, 13.175)
        self.assertAlmostEqual(grown.radius, 8.175)


@unittest.skipUnless(
    CLI.exists() or shutil.which("solidcraft-cli"), "needs solidcraft-cli"
)
class TestModels(unittest.TestCase):
    """The tables, modeled with no window."""

    def test_volumes(self) -> None:
        """Each body has the volume that its numbers call for."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            names = tools.Tormach(solidcraft).mill_tables()
            result: JSON = solidcraft.inspect.center_of_mass(bodies=names)
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        for table, body in zip(tools.MILL_TABLES, bodies):
            assert isinstance(body, dict)
            volume = body["volume"]
            assert isinstance(volume, float)
            self.assertEqual(body["body"], table.name)
            self.assertAlmostEqual(volume, table.volume(), delta=1.0)

    def test_drill_volumes(self) -> None:
        """Flat tipped drills match the volumes worked out by hand."""
        drills = [
            tools.Drill("Plain", 20.0, 100.0, 3, point_angle=180.0),
            tools.Drill("Shank", 20.0, 100.0, 2, 40.0, 10.0, 180.0),
        ]
        expected = [
            (math.pi * 100.0 - 3 * drills[0].groove_area()) * 100.0,
            (math.pi * 100.0 - 2 * drills[1].groove_area()) * 60.0
            + math.pi * 25.0 * 40.0,
        ]
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            names = [
                drill.model(solidcraft, (index * 50.0, 10.0, 5.0))
                for index, drill in enumerate(drills)
            ]
            result: JSON = solidcraft.inspect.center_of_mass(bodies=names)
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        for body, volume in zip(bodies, expected):
            assert isinstance(body, dict)
            found = body["volume"]
            assert isinstance(found, float)
            # SolidCraft reports round bodies about 1.1 % low, as if
            # measured on facets.
            self.assertAlmostEqual(found, volume, delta=volume * 0.015)

    def test_sample_drills(self) -> None:
        """Each sample drill sits inside its keep-out cylinder."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            names, keep_out = tools.sample_drills(solidcraft)
            regions = keep_out.model(solidcraft)
            result: JSON = solidcraft.inspect.center_of_mass(
                bodies=names + regions
            )
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        count = len(tools.SAMPLE_DRILLS)
        self.assertEqual(len(bodies), 2 * count)
        for drill_body, region in zip(bodies[:count], bodies[count:]):
            assert isinstance(drill_body, dict) and isinstance(region, dict)
            drill_volume = drill_body["volume"]
            region_volume = region["volume"]
            assert isinstance(drill_volume, float)
            assert isinstance(region_volume, float)
            self.assertLess(drill_volume, region_volume)

    def test_keep_out_volumes(self) -> None:
        """Keep-outs add new bodies, and leave the tables as they were."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            tormach = tools.Tormach(solidcraft)
            tables = tormach.mill_tables()
            keep_out = tormach.mill_table_keep_out()
            regions = keep_out.model(solidcraft)
            result: JSON = solidcraft.inspect.center_of_mass(
                bodies=tables + regions
            )
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        expected = [table.volume() for table in tools.MILL_TABLES] + [
            (prism.high[0] - prism.low[0])
            * (prism.high[1] - prism.low[1])
            * (prism.high[2] - prism.low[2])
            for prism in keep_out.prisms
        ]
        self.assertEqual(len(bodies), len(expected))
        for body, volume in zip(bodies, expected):
            assert isinstance(body, dict)
            found = body["volume"]
            assert isinstance(found, float)
            self.assertAlmostEqual(found, volume, delta=1.0)


if __name__ == "__main__":
    unittest.main()
