"""Tests for `tools`: the mill tables and their models."""

import dataclasses
import itertools
import math
import shutil
import unittest
from pathlib import Path

from scraftcnc.pybind.scraftpybind import JSON, SCHeadlessTransport, SCPyBind
from scraftcnc.tooling import tools

# An extracted `solidcraft-cli` (as the demo uses) for the live test.
HERE: Path = Path(__file__).resolve().parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"

# Where the live test puts the vise's jaws (millimeters).
VISE_OPENING: float = 50.0
VISE_LIFT: float = 100.0


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
        prism = tools.SCPrism("Box", (0.0, 1.0, 2.0), (3.0, 5.0, 7.0))
        grown = prism.grown(1.0)
        self.assertEqual(grown.low, (-1.0, 0.0, 1.0))
        self.assertEqual(grown.high, (4.0, 6.0, 8.0))
        self.assertEqual(grown.name, "Box")

    def test_empty_prism(self) -> None:
        """A prism with no size on some axis is refused."""
        with self.assertRaises(ValueError):
            tools.SCPrism("Flat", (0.0, 0.0, 0.0), (1.0, 1.0, 0.0))

    def test_margin_units(self) -> None:
        """A margin is read with its unit."""
        prism = tools.SCPrism("Box", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        for margin in ("1/8 in", "1/8 inch", "3.175 mm"):
            with self.subTest(margin=margin):
                grown = tools.SCKeepOut().add_prism(prism, margin)
                self.assertAlmostEqual(grown.low[0], -3.175)
                self.assertAlmostEqual(grown.high[2], 4.175)

    def test_one_per_table(self) -> None:
        """Each table's prism encloses it, 1/8 inch away."""
        tormach = tools.SCTormach(None)  # type: ignore[arg-type]
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
                arcs = tools.SCDrill("D", 20.0, 100.0, flutes).section()
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
        drill = tools.SCDrill("D", 20.0, 100.0, 2, point_angle=180.0)
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
                tools.SCDrill("D", *args)

    def test_cylinder(self) -> None:
        """The cylinder encloses the drill, up from its tip."""
        drill = tools.SCDrill("D", 20.0, 100.0, 2, 40.0, 30.0)
        cylinder = drill.cylinder((1.0, 2.0, 3.0))
        self.assertEqual(cylinder.center, (1.0, 2.0))
        self.assertEqual((cylinder.low, cylinder.high), (3.0, 103.0))
        self.assertEqual(cylinder.radius, 15.0)

    def test_cylinder_grown(self) -> None:
        """A keep-out grows the side and both ends by the margin."""
        cylinder = tools.SCCylinder("C", (0.0, 0.0), 0.0, 10.0, 5.0)
        grown = tools.SCKeepOut().add_cylinder(cylinder, "1/8 in")
        self.assertAlmostEqual(grown.low, -3.175)
        self.assertAlmostEqual(grown.high, 13.175)
        self.assertAlmostEqual(grown.radius, 8.175)


class TestVise(unittest.TestCase):
    """The numbers describing a vise."""

    def test_kurt_size(self) -> None:
        """The D688 has the overall size its listings give."""
        vise = tools.KURT_D688
        self.assertAlmostEqual(
            vise.bed_top() + vise.fixed_jaw.height, 4.375 * 25.4
        )
        self.assertAlmostEqual(vise.overall_length(), 16.75 * 25.4)
        self.assertAlmostEqual(vise.base.width, 6.0 * 25.4)

        # The middle is two or three times as high as the bottom.
        self.assertGreaterEqual(vise.body.height, 2.0 * vise.base.height)
        self.assertLessEqual(vise.body.height, 3.0 * vise.base.height)

        # The third layer is as wide as the lower two.
        self.assertAlmostEqual(
            vise.rail_gap + 2.0 * vise.rail_width, vise.base.width
        )

        # The jaws are two or three times as high as the rails, and the
        # moving one three or four times as long as the fixed one.
        self.assertGreaterEqual(vise.fixed_jaw.height, 2.0 * vise.rail_height)
        self.assertLessEqual(vise.fixed_jaw.height, 3.0 * vise.rail_height)
        self.assertGreaterEqual(
            vise.movable_jaw.length, 3.0 * vise.fixed_jaw.length
        )
        self.assertLessEqual(
            vise.movable_jaw.length, 4.0 * vise.fixed_jaw.length
        )
        self.assertAlmostEqual(vise.fixed_jaw.width, vise.base.width)
        self.assertLess(vise.body.width, vise.base.width)
        self.assertAlmostEqual(vise.jaw_plate.width, 6.0 * 25.4)
        self.assertAlmostEqual(vise.jaw_plate.hole_spacing, 3.875 * 25.4)
        self.assertAlmostEqual(vise.max_opening, 8.8 * 25.4)
        self.assertAlmostEqual(vise.hex_size, 0.75 * 25.4)

    def test_slider(self) -> None:
        """The slider fits the rails, and is shorter than the movable jaw."""
        vise = tools.KURT_D688
        slider = vise.slider()
        self.assertAlmostEqual(
            slider.length, vise.movable_jaw.length - vise.end_block_length
        )
        self.assertEqual(slider.width, vise.rail_gap)
        self.assertAlmostEqual(
            slider.height, vise.body.height + vise.rail_height
        )
        self.assertLess(
            vise.base.height,
            vise.lead_screw_height - vise.lead_screw_diameter / 2.0,
        )

    def test_moving_face(self) -> None:
        """The jaws touch at no opening, and stay on the base when open."""
        vise = tools.KURT_D688
        half = vise.body.length / 2.0
        self.assertAlmostEqual(
            vise.movable_face(0.0),
            -half + vise.fixed_jaw.length + 2.0 * vise.jaw_plate.length,
        )
        wide = vise.movable_face(vise.max_opening)
        self.assertLessEqual(wide + vise.movable_jaw.length, half)

        # The slider never runs into either end block.
        self.assertGreaterEqual(
            vise.movable_face(0.0), -half + vise.end_block_length
        )
        self.assertLessEqual(
            wide + vise.slider().length, half - vise.end_block_length
        )
        for opening in (-1.0, vise.max_opening + 1.0):
            with self.subTest(opening=opening), self.assertRaises(ValueError):
                vise.movable_face(opening)

    def test_keep_out(self) -> None:
        """The prisms hold the base and hexagon, and each jaw and plate."""
        vise = tools.KURT_D688
        margin = 3.175
        base, fixed, moving = vise.keep_out(
            (10.0, 20.0, 30.0), VISE_OPENING
        ).prisms
        half = vise.body.length / 2.0
        hex_end = 10.0 + half + vise.lead_screw_stick_out + vise.hex_length
        rails = 30.0 + vise.bed_top()
        top = rails + vise.fixed_jaw.height

        # All three are as wide as the vise, and grown on all sides.
        for prism in (base, fixed, moving):
            self.assertAlmostEqual(prism.low[1], 20.0 - 76.2 - margin)
            self.assertAlmostEqual(prism.high[1], 20.0 + 76.2 + margin)

        self.assertAlmostEqual(base.low[0], 10.0 - half - margin)
        self.assertAlmostEqual(base.high[0], hex_end + margin)
        self.assertAlmostEqual(base.low[2], 30.0 - margin)
        self.assertAlmostEqual(base.high[2], rails + margin)

        self.assertAlmostEqual(fixed.low[0], 10.0 - half - margin)
        self.assertAlmostEqual(
            fixed.high[0],
            10.0
            - half
            + vise.fixed_jaw.length
            + vise.jaw_plate.length
            + margin,
        )
        self.assertAlmostEqual(fixed.low[2], rails - margin)
        self.assertAlmostEqual(fixed.high[2], top + margin)

        # The movable jaw's starts at its jaw plate, and reaches the hex.
        self.assertAlmostEqual(
            moving.low[0],
            10.0
            + vise.movable_face(VISE_OPENING)
            - vise.jaw_plate.length
            - margin,
        )
        self.assertAlmostEqual(moving.high[0], hex_end + margin)
        self.assertAlmostEqual(moving.low[2], rails - margin)
        self.assertAlmostEqual(moving.high[2], top + margin)

    def test_keep_out_follows_opening(self) -> None:
        """The gap between the jaws' regions is the opening, less margins."""
        vise = tools.KURT_D688
        for opening in (10.0, 100.0, vise.max_opening):
            with self.subTest(opening=opening):
                _, fixed, moving = vise.keep_out(opening=opening).prisms
                self.assertAlmostEqual(
                    moving.low[0] - fixed.high[0], opening - 2.0 * 3.175
                )
        with self.assertRaises(ValueError):
            vise.keep_out(opening=vise.max_opening + 1.0)

    def test_hexagon(self) -> None:
        """The hexagon has the size asked for across its flats."""
        corners = tools.KURT_D688.hexagon()
        self.assertEqual(len(corners), 6)
        height = max(up for _, up in corners) - min(up for _, up in corners)
        self.assertAlmostEqual(height, 0.75 * 25.4)

    def test_outline(self) -> None:
        """A block's outline is its rectangle, with rounded corners."""
        block = tools.SCViseBlock(100.0, 60.0, 10.0, 5.0)
        outline = block.outline("Block", (7.0, -3.0))
        self.assertEqual(len(outline.segments), 8)
        self.assertTrue(outline.is_ccw())
        self.assertAlmostEqual(outline.signed_area, 6000.0)
        self.assertEqual(
            [(corner.x, corner.y) for corner in outline.corners],
            [(-43.0, -33.0), (57.0, -33.0), (57.0, 27.0), (-43.0, 27.0)],
        )

    def test_sharp_outline(self) -> None:
        """A block with no corner radius has only its four edges."""
        outline = tools.SCViseBlock(100.0, 60.0, 10.0).outline("Block")
        self.assertEqual(len(outline.segments), 4)

    def test_notched_outline(self) -> None:
        """The notches line up across the block, four corners each."""
        block = tools.SCViseBlock(100.0, 60.0, 10.0, 5.0)
        notches = tools.SCViseNotches((-20.0, 20.0), 10.0, 8.0, 3.0, 1.0)
        outline = block.outline("Block", (0.0, 0.0), notches)
        corners = [(corner.x, corner.y) for corner in outline.corners]
        self.assertEqual(len(corners), 4 + 4 * 2 * 2)
        self.assertTrue(outline.is_ccw())
        for x in (-25.0, -15.0, 15.0, 25.0):
            for y in (-30.0, -22.0, 22.0, 30.0):
                with self.subTest(x=x, y=y):
                    self.assertIn((x, y), corners)
        self.assertEqual(
            {corner.radius for corner in outline.corners}, {1.0, 3.0, 5.0}
        )

    def test_any_number_of_notches(self) -> None:
        """Any number of notches per side works, even none."""
        block = tools.SCViseBlock(100.0, 60.0, 10.0, 5.0)
        for centers in ((), (0.0,), (-30.0, 0.0, 30.0)):
            with self.subTest(centers=centers):
                notches = tools.SCViseNotches(centers, 10.0, 8.0, 3.0, 1.0)
                outline = block.outline("Block", notches=notches)
                self.assertEqual(len(outline.corners), 4 + 8 * len(centers))
                self.assertAlmostEqual(
                    outline.signed_area, 6000.0 - 160.0 * len(centers)
                )

    def test_notch_area(self) -> None:
        """The rounds at the inner and outer corners count."""
        fillet = 1.0 - math.pi / 4.0
        notches = tools.SCViseNotches((0.0,), 10.0, 8.0, 3.0, 1.0)
        self.assertAlmostEqual(
            notches.area(), 2.0 * (80.0 + 2.0 * fillet * (1.0 - 9.0))
        )

    def test_notches_refused(self) -> None:
        """Numbers that make no notches are refused."""
        for args in (
            ((0.0,), 0.0, 8.0, 3.0, 1.0),
            ((0.0,), 10.0, 0.0, 3.0, 1.0),
            ((0.0,), 10.0, 8.0, -3.0, 1.0),
            ((0.0,), 10.0, 8.0, 3.0, -1.0),
            ((5.0, 0.0), 10.0, 8.0, 3.0, 1.0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tools.SCViseNotches(*args)

    def test_block_refused(self) -> None:
        """Numbers that make no block are refused."""
        for args in (
            (0.0, 60.0, 10.0),
            (100.0, 60.0, -1.0),
            (100.0, 60.0, 10.0, -1.0),
            (100.0, 60.0, 10.0, 31.0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tools.SCViseBlock(*args)

    def test_jaw_plate_refused(self) -> None:
        """A jaw plate whose holes do not fit is refused."""
        for sizes in (
            {"length": 0.0},
            {"hole_diameter": 0.0},
            {"hole_diameter": 25.0},
            {"counterbore_depth": 0.0},
            {"counterbore_depth": 20.0},
            {"hole_spacing": 10.0},
            {"hole_spacing": 6.0 * 25.4},
            {"hole_height": 5.0},
            {"hole_height": 40.0},
        ):
            with self.subTest(sizes=sizes), self.assertRaises(ValueError):
                dataclasses.replace(tools.KURT_JAW_PLATE, **sizes)

    def test_jaw_plate_volume(self) -> None:
        """A jaw plate's volume takes out its holes and counterbores."""
        plate = tools.KURT_JAW_PLATE
        hole = math.pi * (plate.hole_diameter / 2.0) ** 2
        counterbore = math.pi * (plate.counterbore_diameter / 2.0) ** 2
        deep = plate.counterbore_depth
        self.assertAlmostEqual(
            plate.volume(),
            plate.length * plate.width * plate.height
            - 2.0 * (hole * (plate.length - deep) + counterbore * deep),
        )

    def test_vise_refused(self) -> None:
        """Parts that do not fit together are refused."""

        def notches(
            centers: tuple[float, ...],
            width: float,
            depth: float = 35.0,
            radius: float = 1.0,
        ) -> tools.SCViseNotches:
            """Return notches with the given places and sizes."""
            return tools.SCViseNotches(centers, width, depth, radius, 1.0)

        def plate(**sizes: float) -> tools.SCJawPlate:
            """Return the D688's jaw plate with some sizes changed."""
            return dataclasses.replace(tools.KURT_JAW_PLATE, **sizes)

        jaw = tools.KURT_D688.fixed_jaw
        for change in (
            {"rail_width": 0.0},
            {"rail_height": 0.0},
            {"rail_gap": 0.0},
            {"rail_width": 3.0 * 25.4},
            {"end_block_length": 0.0},
            {"end_block_length": 8.0 * 25.4},
            {"max_opening": 11.0 * 25.4},
            {"jaw_plate": plate(width=300.0, hole_spacing=200.0)},
            {"jaw_plate": plate(height=50.0)},
            {"fixed_jaw": tools.SCViseBlock(38.1, 100.0, jaw.height)},
            {"fixed_jaw": tools.SCViseBlock(38.1, jaw.width, 50.0)},
            {"movable_jaw": tools.SCViseBlock(30.0, jaw.width, jaw.height)},
            {
                "fixed_jaw": tools.SCViseBlock(38.1, 300.0, jaw.height),
                "movable_jaw": tools.SCViseBlock(133.35, 300.0, jaw.height),
            },
            {"lead_screw_height": 0.6 * 25.4},
            {"lead_screw_height": 1.6 * 25.4},
            {"lead_screw_hole_diameter": 0.9 * 25.4},
            {"rail_gap": 1.0 * 25.4},
            {"lead_screw_stick_out": 0.0},
            {"hex_size": 0.0},
            {"hex_length": 0.0},
            # Notches that overlap, run off the end or do not fit.
            {"base_notches": notches((0.0, 2.54), 25.4)},
            {"base_notches": notches((7.8 * 25.4,), 25.4)},
            {"base_notches": notches((-101.6, 101.6), 25.4, radius=20.0)},
            # Middle notches that are not in line, do not clear the
            # bottom's, or break into the pocket.
            {"body_notches": notches((-101.6, 90.0), 44.45)},
            {"body_notches": notches((-101.6, 101.6), 20.0)},
            {"body_notches": notches((-101.6, 101.6), 44.45, depth=5.0)},
            {"body_notches": notches((-101.6, 101.6), 44.45, depth=80.0)},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                dataclasses.replace(tools.KURT_D688, **change)


class TestParallels(unittest.TestCase):
    """The numbers describing a set of parallels."""

    def test_heights(self) -> None:
        """Pairs go from 1/2 in to 1-5/8 in, by 1/8 in."""
        heights = [parallel.height for parallel in tools.PARALLELS]
        self.assertEqual(len(heights), 2 * 10)
        for index in range(10):
            with self.subTest(index=index):
                expected = (0.5 + index / 8.0) * 25.4
                self.assertAlmostEqual(heights[2 * index], expected)
                self.assertAlmostEqual(heights[2 * index + 1], expected)

    def test_holes(self) -> None:
        """Holes are optional, but need both sizes, and must fit."""
        self.assertFalse(tools.SCParallel("P", 20.0, 4.0, 100.0).has_holes())
        for spacing, diameter in (
            (50.0, 0.0),
            (0.0, 8.0),
            (50.0, 20.0),
            (8.0, 8.0),
            (95.0, 8.0),
        ):
            with (
                self.subTest(spacing=spacing, diameter=diameter),
                self.assertRaises(ValueError),
            ):
                tools.SCParallel("P", 20.0, 4.0, 100.0, spacing, diameter)
        parallel = tools.SCParallel("P", 20.0, 4.0, 100.0, 50.0, 10.0)
        self.assertAlmostEqual(
            parallel.volume(), 20.0 * 4.0 * 100.0 - 2.0 * math.pi * 25.0 * 4.0
        )

    def test_size(self) -> None:
        """Each is 1/8 in thick and 6 in long, and has its own name."""
        for parallel in tools.PARALLELS:
            with self.subTest(parallel=parallel.name):
                self.assertAlmostEqual(parallel.thickness, 3.175)
                self.assertAlmostEqual(parallel.length, 152.4)
        names = {parallel.name for parallel in tools.PARALLELS}
        self.assertEqual(len(names), len(tools.PARALLELS))

    def test_row(self) -> None:
        """The row is centered, and keep-outs do not touch."""
        centers = tools.parallel_centers()
        self.assertAlmostEqual(centers[0], -centers[-1])
        clearance = min(
            after - before for before, after in itertools.pairwise(centers)
        )
        self.assertGreater(clearance, 3.175 + 2.0 * 3.175)

    def test_prism(self) -> None:
        """A parallel's prism encloses it, up from its bottom edge."""
        parallel = tools.SCParallel("P", 20.0, 4.0, 100.0)
        prism = parallel.prism((10.0, 30.0, 5.0))
        self.assertEqual(prism.low, (8.0, -20.0, 5.0))
        self.assertEqual(prism.high, (12.0, 80.0, 25.0))

    def test_clear_of_vise(self) -> None:
        """The row stands clear of the vise's keep-out region."""
        vise = tools.KURT_D688.keep_out((0.0, tools.VISE_ROW_Y, 0.0))
        row = tools.PARALLELS[0].prism((0.0, tools.PARALLEL_ROW_Y, 0.0))
        self.assertLess(row.high[1] + 3.175, vise.prisms[0].low[1])


@unittest.skipUnless(
    CLI.exists() or shutil.which("solidcraft-cli"), "needs solidcraft-cli"
)
class TestCountersinks(unittest.TestCase):
    """The double end countersinks of the catalog's page 24."""

    def test_tables(self) -> None:
        """All four tables are there, with their sizes."""
        sinks = tools.DOUBLE_END_COUNTERSINKS
        families = [sink.family for sink in sinks.values()]
        self.assertEqual(families.count("Radius"), 11)
        self.assertEqual(families.count("Plain"), 16)
        self.assertEqual(families.count("Metric"), 10)
        self.assertEqual(families.count("Left hand"), 7)
        self.assertEqual(len(sinks), 44)

    def test_rows(self) -> None:
        """The four order numbers named match the catalog's rows."""
        sinks = tools.DOUBLE_END_COUNTERSINKS
        first = sinks["421-0130"]
        self.assertAlmostEqual(first.body_diameter, 0.125 * 25.4)
        self.assertAlmostEqual(first.drill_diameter, 3.0 / 64.0 * 25.4)
        self.assertAlmostEqual(first.overall_length, 1.25 * 25.4)
        self.assertAlmostEqual(first.radius, 5.0 / 32.0 * 25.4)
        self.assertEqual(first.angle, 60.0)
        self.assertEqual(sinks["421-0139"].angle, 82.0)
        self.assertEqual(sinks["421-0141"].angle, 90.0)
        self.assertEqual(sinks["421-0141"].radius, 0.0)
        metric = sinks["421-0388"]
        self.assertAlmostEqual(metric.body_diameter, 3.15)
        self.assertAlmostEqual(metric.drill_diameter, 0.5)
        self.assertAlmostEqual(metric.overall_length, 25.0)
        self.assertTrue(sinks["421-0138"].left_hand)
        self.assertFalse(first.left_hand)
        self.assertAlmostEqual(sinks["421-0228"].body_diameter, 0.625 * 25.4)

    def test_cone(self) -> None:
        """A plain end's cone has the catalog's angle."""
        sink = tools.DOUBLE_END_COUNTERSINKS["421-0141"]
        step = sink.step()
        self.assertAlmostEqual(sink.body_start() - sink.drill_diameter, step)
        points = sink.profile()
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertAlmostEqual(points[-1][1], sink.overall_length)
        self.assertEqual(points[-1][0], 0.0)

    def test_radius_type_is_conical(self) -> None:
        """The radius type has a pure cone, at the catalog's 60 degrees."""
        sink = tools.DOUBLE_END_COUNTERSINKS["421-0261"]
        points = sink.profile()
        self.assertEqual(len(points), 10)
        (r_low, z_low), (r_high, z_high) = points[3], points[4]
        self.assertAlmostEqual(r_low, sink.drill_diameter / 2.0)
        self.assertAlmostEqual(r_high, sink.body_diameter / 2.0)
        self.assertAlmostEqual(
            2.0 * math.degrees(math.atan2(r_high - r_low, z_high - z_low)),
            60.0,
        )

    def test_flat_tips(self) -> None:
        """Each tip is flat, 5 % of the small drill's diameter across."""
        for sink in tools.DOUBLE_END_COUNTERSINKS.values():
            points = sink.profile()
            self.assertEqual(points[0], (0.0, 0.0))
            self.assertEqual(points[1][1], 0.0)
            self.assertAlmostEqual(
                2.0 * points[1][0], 0.05 * sink.drill_diameter
            )
            self.assertAlmostEqual(points[-2][1], sink.overall_length)
            self.assertAlmostEqual(points[-2][0], points[1][0])

    def test_point_angle(self) -> None:
        """The point is a 90 degree cone, from the flat to the drill."""
        sink = tools.DOUBLE_END_COUNTERSINKS["421-0141"]
        points = sink.profile()
        self.assertAlmostEqual(
            points[2][0] - points[1][0], points[2][1] - points[1][1]
        )

    def test_symmetric(self) -> None:
        """Both ends are the same."""
        for sink in tools.DOUBLE_END_COUNTERSINKS.values():
            points = sink.profile()
            for (r_low, z_low), (r_high, z_high) in zip(
                points, reversed(points)
            ):
                self.assertAlmostEqual(r_low, r_high)
                self.assertAlmostEqual(z_low + z_high, sink.overall_length)

    def test_cylinder(self) -> None:
        """Its keep-out cylinder encloses it, from its tip up."""
        sink = tools.DOUBLE_END_COUNTERSINKS["421-0138"]
        cylinder = sink.cylinder((1.0, 2.0, 3.0))
        self.assertEqual(cylinder.name, "Countersink 421-0138")
        self.assertAlmostEqual(cylinder.radius, 0.0625 * 25.4)
        self.assertAlmostEqual(cylinder.low, 3.0)
        self.assertAlmostEqual(cylinder.high, 3.0 + 1.25 * 25.4)

    def test_refused(self) -> None:
        """Sizes that do not make a countersink are refused."""
        sink = tools.DOUBLE_END_COUNTERSINKS["421-0130"]
        for changes in (
            {"drill_diameter": sink.body_diameter},
            {"angle": 180.0},
            {"overall_length": 2.0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dataclasses.replace(sink, **changes)


class TestModels(unittest.TestCase):
    """The tables, modeled with no window."""

    def test_volumes(self) -> None:
        """Each body has the volume that its numbers call for."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = tools.SCTormach(solidcraft).mill_tables()
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
            tools.SCDrill("Plain", 20.0, 100.0, 3, point_angle=180.0),
            tools.SCDrill("Shank", 20.0, 100.0, 2, 40.0, 10.0, 180.0),
        ]
        expected = [
            (math.pi * 100.0 - 3 * drills[0].groove_area()) * 100.0,
            (math.pi * 100.0 - 2 * drills[1].groove_area()) * 60.0
            + math.pi * 25.0 * 40.0,
        ]
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
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
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
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

    def _vise_bodies(self) -> list[dict[str, JSON]]:
        """Return what SolidCraft measures of the modeled `KURT_D688`."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = tools.KURT_D688.model(
                solidcraft, (10.0, 20.0, 30.0), VISE_OPENING, VISE_LIFT
            )
            result: JSON = solidcraft.inspect.center_of_mass(bodies=names)
        self.assertEqual(
            [name.removeprefix("Kurt D688 ") for name in names],
            [
                "base",
                "body",
                "front rail",
                "back rail",
                "fixed end",
                "lead screw end",
                "lead screw",
                "fixed jaw",
                "movable jaw",
                "slider",
                "fixed jaw plate",
                "movable jaw plate",
            ],
        )
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        found: list[dict[str, JSON]] = []
        for body in bodies:
            assert isinstance(body, dict)
            found.append(body)
        return found

    def test_vise_volumes(self) -> None:
        """The vise's bodies have the volumes worked out by hand."""
        vise = tools.KURT_D688
        length = vise.body.length
        rail = length * vise.rail_width * vise.rail_height
        block = vise.end_block_length * vise.rail_gap * vise.rail_height
        expected = (
            vise.base.volume(vise.base_notches),
            vise.body_volume(),
            rail,
            rail,
            block,
            block,
            vise.lead_screw_volume(),
            vise.fixed_jaw.volume(),
            vise.movable_jaw.volume(),
            vise.slider_volume(),
            vise.jaw_plate_volume(),
            vise.jaw_plate_volume(),
        )
        bodies = self._vise_bodies()
        self.assertEqual(len(bodies), len(expected))
        for body, volume in zip(bodies, expected):
            found = body["volume"]
            assert isinstance(found, float)
            # SolidCraft measures round parts about 1.1 % low.
            self.assertAlmostEqual(found, volume, delta=volume * 0.015)

    def test_vise_places(self) -> None:
        """The vise's bodies are centered where they should be."""
        vise = tools.KURT_D688
        top = 30.0 + vise.base.height + vise.body.height
        rail_y = (vise.rail_gap + vise.rail_width) / 2.0
        block_x = (vise.body.length - vise.end_block_length) / 2.0
        rail_z = top + vise.rail_height / 2.0
        places = {
            0: (10.0, 20.0, 30.0 + vise.base.height / 2.0),
            2: (10.0, 20.0 - rail_y, rail_z),
            3: (10.0, 20.0 + rail_y, rail_z),
            4: (10.0 - block_x, 20.0, rail_z),
            5: (10.0 + block_x, 20.0, rail_z),
        }
        face = vise.movable_face(VISE_OPENING)
        jaw_z = (
            top + vise.rail_height + VISE_LIFT + vise.fixed_jaw.height / 2.0
        )
        places[7] = (
            10.0
            - block_x
            - (vise.end_block_length - vise.fixed_jaw.length) / 2.0,
            20.0,
            jaw_z,
        )
        places[8] = (10.0 + face + vise.movable_jaw.length / 2.0, 20.0, jaw_z)
        bodies = self._vise_bodies()
        for index, place in places.items():
            center = bodies[index]["center"]
            assert isinstance(center, list)
            for value, expected in zip(center, place):
                assert isinstance(value, float)
                self.assertAlmostEqual(value, expected, places=6)

        # The screw lies on its axis, and goes toward +X.
        center = bodies[6]["center"]
        assert isinstance(center, list)
        assert isinstance(center[0], float)
        assert isinstance(center[1], float)
        assert isinstance(center[2], float)
        self.assertGreater(center[0], 10.0)
        self.assertAlmostEqual(center[1], 20.0, places=3)
        self.assertAlmostEqual(
            center[2], 30.0 + vise.lead_screw_height, places=3
        )

    def test_plate_places(self) -> None:
        """Each plate is on its jaw's clamping face, facing the other."""
        vise = tools.KURT_D688
        plate = vise.jaw_plate
        half = plate.length / 2.0
        fixed = -vise.body.length / 2.0 + vise.fixed_jaw.length

        # The counterbores, in the clamping face, move each plate's
        # center of mass back from its middle, toward its jaw.
        deep = plate.counterbore_depth
        bores = 2.0 * math.pi * (plate.counterbore_diameter / 2.0) ** 2 * deep
        holes = (
            2.0
            * math.pi
            * (plate.hole_diameter / 2.0) ** 2
            * (plate.length - deep)
        )
        back = (bores * (half - deep / 2.0) - holes * deep / 2.0) / (
            plate.volume()
        )
        expected = (
            10.0 + fixed + half - back,
            10.0 + vise.movable_face(VISE_OPENING) - half + back,
        )
        bodies = self._vise_bodies()
        for body, place in zip(bodies[10:], expected):
            center = body["center"]
            assert isinstance(center, list)
            assert isinstance(center[0], float)
            assert isinstance(center[1], float)
            # SolidCraft's round faces are a little off, which moves
            # the center of mass about 0.001 mm.
            self.assertAlmostEqual(center[0], place, places=2)
            self.assertAlmostEqual(center[1], 20.0, places=3)

    def test_plates_gap(self) -> None:
        """The opening is measured between the plates."""
        vise = tools.KURT_D688
        fixed = -vise.body.length / 2.0 + vise.fixed_jaw.length
        self.assertAlmostEqual(
            vise.movable_face(VISE_OPENING)
            - vise.jaw_plate.length
            - (fixed + vise.jaw_plate.length),
            VISE_OPENING,
        )

    def test_countersinks(self) -> None:
        """Every countersink revolves to the right volume and place."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = tools.countersink_rows(solidcraft)
            self.assertEqual(len(names), 44)
            for sink in tools.DOUBLE_END_COUNTERSINKS.values():
                with self.subTest(order_number=sink.order_number):
                    result = solidcraft.inspect.center_of_mass(
                        bodies=[sink.name()]
                    )
                    assert isinstance(result, dict)
                    self.assertAlmostEqual(
                        float(result["volume"]) / sink.volume(),
                        1.0,
                        delta=0.02,
                    )
                    self.assertAlmostEqual(
                        result["center"][2],
                        sink.overall_length / 2.0,
                        delta=0.01,
                    )

                    # Exact surfaces: the body and both small drills.
                    faces = solidcraft.model.faces(body=sink.name())
                    assert isinstance(faces, dict)
                    radii = [
                        face["cylinder"]["radius"]
                        for face in faces["faces"]
                        if face.get("cylinder")
                    ]
                    self.assertEqual(len(radii), 2 * 3 + 3)
                    self.assertAlmostEqual(
                        max(radii), sink.body_diameter / 2.0, 6
                    )
                    self.assertAlmostEqual(
                        min(radii), sink.drill_diameter / 2.0, 6
                    )

    def test_largest(self) -> None:
        """The largest of each table, one body each."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = tools.largest_countersinks(solidcraft)
        self.assertEqual(
            names,
            [
                "Countersink 421-0261",
                "Countersink 421-0244",
                "Countersink 421-0398",
                "Countersink 421-0228",
            ],
        )

    def test_countersink_faces(self) -> None:
        """It lands at its tip, with only cones, cylinders and flats."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            sink = tools.DOUBLE_END_COUNTERSINKS["421-0130"]
            body = sink.model(solidcraft, (5.0, 6.0, 7.0))
            result = solidcraft.inspect.center_of_mass(bodies=[body])
            faces = solidcraft.model.faces(body=body)
        assert isinstance(result, dict)
        self.assertAlmostEqual(result["center"][0], 5.0, 3)
        self.assertAlmostEqual(result["center"][1], 6.0, 3)
        assert isinstance(faces, dict)

        # Seven pieces of outline, each in the revolve's three sectors,
        # and a single flat face on each tip.
        self.assertEqual(len(faces["faces"]), 7 * 3 + 2)

    def test_vise_assembled(self) -> None:
        """With the jaws down on the rails, no two bodies overlap."""
        vise = tools.KURT_D688
        program = shutil.which("solidcraft-cli") or str(CLI)
        for opening in (0.0, VISE_OPENING, vise.max_opening):
            with (
                self.subTest(opening=opening),
                SCHeadlessTransport(program) as transport,
            ):
                solidcraft = SCPyBind(transport)
                names = vise.model(solidcraft, opening=opening)
                result = solidcraft.inspect.interference(bodies=names)
                assert isinstance(result, dict)
                self.assertEqual(result["checked"], len(names))
                self.assertEqual(result["interferences"], [])
                self.assertEqual(result["unchecked"], [])

    def test_vise_keep_out_volumes(self) -> None:
        """The vise's keep-out bodies have the volumes of their prisms."""
        keep_out = tools.KURT_D688.keep_out(opening=VISE_OPENING)
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = keep_out.model(solidcraft)
            result: JSON = solidcraft.inspect.center_of_mass(bodies=names)
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        self.assertEqual(len(bodies), 3)
        for body, prism in zip(bodies, keep_out.prisms):
            assert isinstance(body, dict)
            found = body["volume"]
            assert isinstance(found, float)
            volume = (
                (prism.high[0] - prism.low[0])
                * (prism.high[1] - prism.low[1])
                * (prism.high[2] - prism.low[2])
            )
            self.assertAlmostEqual(found, volume, delta=1.0)

    def test_parallel_set(self) -> None:
        """Each parallel and keep-out has the volume its numbers call for."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names, keep_out = tools.parallel_set(solidcraft)
            regions = keep_out.model(solidcraft)
            result: JSON = solidcraft.inspect.center_of_mass(
                bodies=names + regions
            )
        assert isinstance(result, dict)
        bodies = result["bodies"]
        assert isinstance(bodies, list)
        expected = [parallel.volume() for parallel in tools.PARALLELS] + [
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
            # Round faces measure a little off, so allow 1 %.
            self.assertAlmostEqual(found, volume, delta=0.01 * volume)

    def test_slider_place(self) -> None:
        """The slider starts at the jaw's face, lifted, between the rails."""
        vise = tools.KURT_D688
        center = self._vise_bodies()[9]["center"]
        assert isinstance(center, list)
        assert isinstance(center[0], float) and isinstance(center[1], float)
        self.assertAlmostEqual(
            center[0],
            10.0
            + vise.movable_face(VISE_OPENING)
            + vise.slider().length / 2.0,
            places=3,
        )
        self.assertAlmostEqual(center[1], 20.0, places=3)

    def test_keep_out_volumes(self) -> None:
        """Keep-outs add new bodies, and leave the tables as they were."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            tormach = tools.SCTormach(solidcraft)
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
