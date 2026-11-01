"""Tests for `mount`: stacks of tooling and material."""

import dataclasses
import math
import shutil
import unittest
from pathlib import Path
from unittest import mock

import mount
import tools
from scgeometry import SCCorner, SCHole, SCRoundedPolygon
from scraftpybind import HeadlessTransport, SolidCraftPyBind

# An extracted `solidcraft-cli` (as the demo uses) for the live test.
HERE: Path = Path(__file__).resolve().parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"

TABLE = tools.MILL_TABLES[1]
VISE = tools.KURT_D688
INCH = 25.4


def work(length: float = 5.5, width: float = 12.0, thick: float = 0.5):
    """Return a plate, from its size in inches."""
    return mount.Plate("Work", length * INCH, width * INCH, thick * INCH)


class TestFirstMount(unittest.TestCase):
    """The first stack's places and notes."""

    def test_heights(self) -> None:
        """Each layer stands on the one below; the table's top is Z = 0."""
        places = mount.FIRST_MOUNT.places()
        self.assertAlmostEqual(places[0][2], -TABLE.thickness)
        self.assertAlmostEqual(places[1][2], 0.0)
        self.assertAlmostEqual(places[2][2], 2.64 * INCH)
        self.assertAlmostEqual(places[3][2], 4.14 * INCH)

    def test_centered_in_gap(self) -> None:
        """The work is midway between the plates, along X."""
        x = mount.FIRST_MOUNT.places()[3][0]
        fixed = (
            -VISE.middle.length / 2.0
            + VISE.fixed_jaw.length
            + VISE.plate.length
        )
        moving = VISE.moving_face(6.0 * INCH) - VISE.plate.length
        self.assertAlmostEqual(x - fixed, moving - x)
        self.assertAlmostEqual(moving - fixed, 6.0 * INCH)

    def test_parallels_under_work(self) -> None:
        """The parallels' outer faces are flush with the work's edges."""
        pair = mount.FIRST_MOUNT.layers[2]
        assert isinstance(pair, mount.ParallelPair)
        center = mount.FIRST_MOUNT.places()[2]
        low, high = pair.centers(center)
        half = pair.first.thickness / 2.0
        self.assertAlmostEqual((high[0] + half) - (low[0] - half), 5.5 * INCH)
        self.assertAlmostEqual((high[0] + low[0]) / 2.0, center[0])

    def test_notes(self) -> None:
        """The stack's shortcomings are reported, with their sizes."""
        text = "\n".join(mount.FIRST_MOUNT.notes)
        self.assertIn("NOT CLAMPED: the work is 0.500 in narrower", text)
        self.assertIn("grip 0.235 in of the 0.500 in", text)
        self.assertIn("0.265 in above the jaws, and 0.140 in above", text)
        self.assertIn("3.000 in past the jaws", text)
        self.assertIn("1.965 in past the table", text)

    def test_keep_outs(self) -> None:
        """The tooling has keep-outs, and the plate none."""
        regions = mount.FIRST_MOUNT.keep_out()
        self.assertEqual(len(regions.prisms), 1 + 3 + 2)
        self.assertEqual(regions.cylinders, [])
        self.assertEqual(work().keep_out((0.0, 0.0, 0.0)).prisms, [])

    def test_report(self) -> None:
        """The report lists the layers from the top down."""
        lines = mount.FIRST_MOUNT.report()
        self.assertIn("Aluminum plate", lines[1])
        self.assertIn("4.140 in to", lines[1])
        self.assertIn("Tormach 770", lines[4])


class TestViseMount(unittest.TestCase):
    """Other stacks in a vise."""

    def build(self, opening: float, height: str, plate: mount.Plate):
        """Return a stack, with the opening in inches."""
        return mount.vise_mount(TABLE, VISE, opening * INCH, height, plate)

    def test_clamped(self) -> None:
        """Jaws closed on the work give no complaint about clamping."""
        notes = "\n".join(self.build(5.5, "1-1/2 in", work()).notes)
        self.assertNotIn("NOT CLAMPED", notes)

    def test_no_grip(self) -> None:
        """Parallels as tall as the jaws leave nothing to grip."""
        notes = "\n".join(self.build(6.0, "1-7/8 in", work()).notes)
        self.assertIn("NO GRIP", notes)

    def test_buried(self) -> None:
        """Thin work low in the jaws lies under their keep-outs."""
        notes = "\n".join(self.build(6.0, "1/2 in", work(thick=0.25)).notes)
        self.assertIn("KEEP-OUT", notes)

    def test_refused(self) -> None:
        """Work wider than the gap, or an unknown height, is refused."""
        with self.assertRaises(ValueError):
            self.build(5.0, "1-1/2 in", work())
        with self.assertRaises(ValueError):
            self.build(6.0, "1-1/16 in", work())

    def test_pair_refused(self) -> None:
        """A pair must match in height and not overlap."""
        low, high = tools.PARALLELS[0], tools.PARALLELS[2]
        with self.assertRaises(ValueError):
            mount.ParallelPair(low, high, 100.0)
        with self.assertRaises(ValueError):
            mount.ParallelPair(low, tools.PARALLELS[1], 1.0)


class TestGarage(unittest.TestCase):
    """The Mikini 1610L's table, with the vise turned along Y."""

    def test_table(self) -> None:
        """The table has the specifications' slots."""
        table = tools.MIKINI_1610L
        self.assertAlmostEqual(table.width, 10.5 * INCH)
        self.assertEqual(len(table.slot_centers()), 5)
        self.assertAlmostEqual(table.throat_width, 11.0 / 16.0 * INCH)
        self.assertAlmostEqual(table.head_width, 15.0 / 16.0 * INCH)
        self.assertAlmostEqual(table.throat_depth, 0.5 * INCH)
        self.assertAlmostEqual(table.slot_depth, INCH)

    def test_table_refused(self) -> None:
        """Slots through the plate, or its edges, are refused."""
        table = tools.MIKINI_1610L
        with self.assertRaises(ValueError):
            dataclasses.replace(table, thickness=INCH)
        with self.assertRaises(ValueError):
            dataclasses.replace(table, slot_spacing=2.5 * INCH)

    def test_turned_prism(self) -> None:
        """A quarter turn sends +X to -Y, about the axis given."""
        prism = tools.Prism("P", (10.0, -1.0, 0.0), (20.0, 1.0, 5.0))
        turned = prism.quarter_turned(10.0, 0.0)
        self.assertEqual(turned.low, (9.0, -10.0, 0.0))
        self.assertEqual(turned.high, (11.0, 0.0, 5.0))

    def test_keep_outs(self) -> None:
        """The base's keep-out runs along Y, the hexagon toward -Y."""
        base = mount.GARAGE_MOUNT.keep_out().prisms[1]
        self.assertAlmostEqual(base.low[0], -(3.0 + 0.125) * INCH)
        self.assertAlmostEqual(base.high[0], (3.0 + 0.125) * INCH)
        self.assertAlmostEqual(base.low[1], -(7.875 + 1.0 + 0.125) * INCH)
        self.assertAlmostEqual(base.high[1], (7.875 + 0.125) * INCH)

    def test_seat(self) -> None:
        """A turned vise's gap is toward +Y, at its fixed jaw."""
        layer = mount.GARAGE_MOUNT.layers[1]
        self.assertAlmostEqual(layer.seat()[0], 0.0)
        self.assertAlmostEqual(layer.seat()[1], 3.15 * INCH)

    def test_notes(self) -> None:
        """The fit is reported, with its sizes."""
        text = "\n".join(mount.GARAGE_MOUNT.notes)
        self.assertIn("2.625 in past the rear", text)
        self.assertIn("3.625 in to the end of the hexagon", text)
        self.assertIn("reaches 1.475 in past it", text)


class TestToolingPlate(unittest.TestCase):
    """The tooling plate's grid of holes."""

    def test_grid(self) -> None:
        """The grid fills the plate, 1/2 in from all four sides."""
        centers = tools.TOOLING_PLATE.hole_centers()
        self.assertEqual(len(centers), 10 * 20)
        self.assertAlmostEqual(centers[0][0], -2.25 * INCH)
        self.assertAlmostEqual(centers[0][1], -4.75 * INCH)
        self.assertAlmostEqual(centers[-1][0], 2.25 * INCH)
        self.assertAlmostEqual(centers[-1][1], 4.75 * INCH)
        self.assertAlmostEqual(centers[1][0] - centers[0][0], 0.5 * INCH)

    def test_outline(self) -> None:
        """The outline is an `SCRoundedPolygon` with four 1/4 in corners."""
        outline = tools.TOOLING_PLATE.outline((1.0, 2.0))
        self.assertEqual(len(outline.corners), 4)
        self.assertTrue(outline.is_ccw())
        for corner in outline.corners:
            self.assertAlmostEqual(corner.radius, 0.25 * INCH)
        self.assertAlmostEqual(outline.corners[2].x, 1.0 + 2.75 * INCH)
        self.assertAlmostEqual(outline.corners[2].y, 2.0 + 5.25 * INCH)

    def test_outline_has_the_holes(self) -> None:
        """The outline holds all of the grid, moved with its center."""
        holes = tools.TOOLING_PLATE.outline((1.0, 2.0)).children
        self.assertEqual(len(holes), 200)
        self.assertAlmostEqual(holes[0].x, 1.0 - 2.25 * INCH)
        self.assertAlmostEqual(holes[0].y, 2.0 - 4.75 * INCH)
        self.assertAlmostEqual(holes[0].diameter, 0.144 * INCH)

    def test_screw_fits(self) -> None:
        """The chart runs #2 to #12: nominal, then close, then loose."""
        self.assertEqual(
            list(tools.SCREW_FITS), ["#2", "#4", "#6", "#8", "#10", "#12"]
        )
        for fit in tools.SCREW_FITS.values():
            with self.subTest(screw=fit.screw):
                self.assertLess(fit.nominal, fit.close)
                self.assertLess(fit.close, fit.loose)
        six = tools.SCREW_FITS["#6"]
        self.assertEqual((six.close_drill, six.loose_drill), ("#27", "#25"))
        self.assertEqual(tools.TOOLING_PLATE.hole_diameter, six.close)

    def test_refused(self) -> None:
        """A grid that does not fit the plate is refused."""
        plate = tools.TOOLING_PLATE
        for changes in (
            {"length": 5.3 * INCH},
            {"hole_diameter": 0.5 * INCH},
            {"hole_diameter": 0.0},
            {"edge": 6.0 * INCH},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dataclasses.replace(plate, **changes)

    def test_stack(self) -> None:
        """It stands on the table, with a keep-out around it."""
        stack = mount.PLATE_MOUNT
        self.assertAlmostEqual(stack.places()[1][2], 0.0)
        prism = stack.keep_out().prisms[1]
        self.assertAlmostEqual(prism.high[2], 0.625 * INCH)
        self.assertAlmostEqual(prism.high[1], 5.375 * INCH)


class TestModel(unittest.TestCase):
    """The stack in SolidCraft, with no window."""

    def test_no_overlaps(self) -> None:
        """No two bodies of the stack overlap."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            names = mount.FIRST_MOUNT.model(solidcraft)
            self.assertEqual(len(names), 1 + 12 + 2 + 1)
            result = solidcraft.inspect.interference(bodies=names)
            assert isinstance(result, dict)
            self.assertEqual(result["checked"], len(names))
            self.assertEqual(result["interferences"], [])
            self.assertEqual(result["unchecked"], [])

    def test_garage(self) -> None:
        """The table's volume is right; the turned vise lands in place."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            names = mount.GARAGE_MOUNT.model(solidcraft)
            result = solidcraft.inspect.center_of_mass(bodies=[names[0]])
            assert isinstance(result, dict)
            self.assertAlmostEqual(
                float(result["volume"]) / tools.MIKINI_1610L.volume(), 1.0, 4
            )
            fixed = solidcraft.inspect.center_of_mass(
                bodies=["Kurt D688 fixed jaw"]
            )
            assert isinstance(fixed, dict)
            x, y, z = fixed["center"]
            self.assertAlmostEqual(x, 0.0)
            self.assertAlmostEqual(y, (7.875 - 0.5) * INCH)
            self.assertAlmostEqual(z, (2.64 + 1.735 / 2.0) * INCH)
            result = solidcraft.inspect.interference(bodies=names)
            assert isinstance(result, dict)
            self.assertEqual(result["checked"], len(names))
            self.assertEqual(result["interferences"], [])
            self.assertEqual(result["unchecked"], [])

    def test_tooling_plate(self) -> None:
        """All of the holes are cut, and the plate sits on the table."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            plate = tools.TOOLING_PLATE
            names = mount.PLATE_MOUNT.model(solidcraft)

            # Volumes of many holes measure a few percent off, so check
            # each hole's own faces (two half cylinders) instead.
            faces = solidcraft.model.faces(body=names[1])
            assert isinstance(faces, dict)
            holes = [
                face["cylinder"]
                for face in faces["faces"]
                if face.get("cylinder")
                and face["cylinder"]["radius"] < plate.hole_diameter
            ]
            self.assertEqual(
                {
                    (round(hole["origin"][0], 3), round(hole["origin"][1], 3))
                    for hole in holes
                },
                {(round(x, 3), round(y, 3)) for x, y in plate.hole_centers()},
            )
            self.assertEqual(len(holes), 2 * 200)
            for hole in holes:
                self.assertAlmostEqual(
                    hole["radius"], plate.hole_diameter / 2.0
                )
            result = solidcraft.inspect.interference(bodies=names)
            assert isinstance(result, dict)
            self.assertEqual(result["interferences"], [])

    def test_one_extrude(self) -> None:
        """The plate takes one extrude, and no cut, and makes one body."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            commands = type(solidcraft.solid)
            with mock.patch.object(
                commands, "extrude", autospec=True, wraps=commands.extrude
            ) as extrude:
                names = tools.TOOLING_PLATE.model(solidcraft, (0.0, 0.0, 0.0))
            self.assertEqual(extrude.call_count, 1)
            self.assertNotIn("operation", extrude.call_args.kwargs)
            self.assertEqual(len(names), 1)

    def test_model(self) -> None:
        """A plate with a pocket, an island, holes and a boss."""

        def square(name, half, z_start, z_end, children=(), x=0.0):
            corners = [
                SCCorner(x - half, -half),
                SCCorner(x + half, -half),
                SCCorner(x + half, half),
                SCCorner(x - half, half),
            ]
            return SCRoundedPolygon(name, corners, z_start, z_end, children)

        island = square(
            "Island", 15.0, 5.0, 10.0, [SCHole(0.0, 0.0, 10.0, 10.0, 0.0)]
        )
        pocket = square("Pocket", 30.0, 10.0, 5.0, [island])
        through = SCHole(40.0, 40.0, 10.0, 10.0, 0.0)
        boss = square("Boss", 5.0, 10.0, 15.0, x=-40.0)
        plate = square("Plate", 50.0, 0.0, 10.0, [pocket, through, boss])
        program = shutil.which("solidcraft-cli") or str(CLI)
        with HeadlessTransport(program) as transport:
            solidcraft = SolidCraftPyBind(transport)
            self.assertEqual(plate.model(solidcraft), "Plate")
            volume = solidcraft.inspect.center_of_mass(bodies=["Plate"])[
                "volume"
            ]
        hole = math.pi * 25.0
        expected = (
            100.0**2 * 10.0
            - (60.0**2 - 30.0**2) * 5.0
            - hole * 10.0
            - hole * 10.0
            + 10.0**2 * 5.0
        )
        self.assertAlmostEqual(volume / expected, 1.0, 2)


if __name__ == "__main__":
    unittest.main()
