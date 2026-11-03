"""Tests for `setups`: setups read from JSON."""

import copy
import dataclasses
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from scraftcnc import setups
from scraftcnc.pybind.scraftpybind import SCHeadlessTransport, SCPyBind
from scraftcnc.tooling import tools

# An extracted `solidcraft-cli` (as the demo uses) for the live test.
HERE: Path = Path(__file__).resolve().parent.parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
INCH = 25.4

# `GRID_PLATE` without its chamfers, which take minutes to model: the
# same shape for every check here.
FLAT_PLATE = dataclasses.replace(tools.GRID_PLATE, chamfer_depth=0.0)


def setUpModule() -> None:
    """Have setups name the unchamfered plate."""
    patcher = mock.patch.dict(setups.PARTS, {"Grid plate": FLAT_PLATE})
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def example():
    """Return the example setup's JSON."""
    return json.loads(setups.EXAMPLE.read_text(encoding="utf-8"))


class TestExample(unittest.TestCase):
    """The example: a grid plate from a chunk, in a vise."""

    def setUp(self) -> None:
        self.setup = setups.SCSetup(example())

    def test_items(self) -> None:
        """Everything in the JSON is there."""
        names = [tool.layer.name for tool in self.setup.tooling]
        self.assertEqual(
            names,
            [
                "Mikini 1610L",
                "Kurt D688",
                "Parallel 1-1/2 in A",
                "Parallel 1-1/2 in B",
            ],
        )
        self.assertEqual(len(self.setup.materials), 1)
        self.assertEqual(len(self.setup.materials[0].parts), 1)

    def test_heights(self) -> None:
        """The JSON's heights match what the pieces stand on."""
        vise = tools.KURT_D688
        table, _, first, second = self.setup.tooling
        self.assertAlmostEqual(
            table.placement.z + tools.MIKINI_1610L.thickness, 0.0
        )
        self.assertAlmostEqual(first.placement.z, vise.bed_top())
        self.assertAlmostEqual(second.placement.z, vise.bed_top())
        self.assertAlmostEqual(
            self.setup.materials[0].placement.z,
            vise.bed_top() + first.layer.parallel.height,
        )

    def test_parallels_next_to_jaws(self) -> None:
        """Each parallel touches a jaw's plate, along the jaw."""
        gap = setups._gap(
            self.setup.tooling[1].layer, self.setup.tooling[1].placement
        )
        self.assertAlmostEqual(gap.high[1], 3.0 * INCH)
        self.assertAlmostEqual(gap.low[1], -3.0 * INCH)
        first = self.setup.tooling[2].keep_out().prisms[0].grown(-3.175)
        second = self.setup.tooling[3].keep_out().prisms[0].grown(-3.175)
        self.assertAlmostEqual(first.high[1], gap.high[1])
        self.assertAlmostEqual(second.low[1], gap.low[1])
        self.assertAlmostEqual(first.high[0] - first.low[0], 6.0 * INCH)

    def test_material_turned(self) -> None:
        """The material's 11-1/2 in is along X, its 6 in between the jaws."""
        bounds = self.setup.materials[0].bounds()
        self.assertAlmostEqual(bounds.high[0], 5.75 * INCH)
        self.assertAlmostEqual(bounds.high[1], 3.0 * INCH)
        self.assertAlmostEqual(bounds.high[2], 4.64 * INCH)

    def test_notes(self) -> None:
        """How it came out is reported, with its sizes."""
        text = "\n".join(self.setup.notes())
        self.assertNotIn("PART DOES NOT FIT", text)
        self.assertNotIn("NOT CLAMPED", text)
        self.assertNotIn("OUT OF REACH", text)
        self.assertIn("grip 0.235 in", text)
        self.assertIn("0.265 in above the jaws and 0.140 in above", text)
        self.assertIn("2.750 in past the jaws at each X end", text)
        self.assertIn("edge is 0.250 in from a jaw, 0.125 in from", text)
        self.assertIn("6.775 in at the low side", text)

    def test_keep_outs(self) -> None:
        """Tooling has keep-outs; material and parts do not."""
        keep_out = self.setup.keep_out()
        self.assertEqual(len(keep_out.prisms), 1 + 3 + 2)
        names = " ".join(prism.name for prism in keep_out.prisms)
        self.assertNotIn("aluminum", names)
        self.assertNotIn("Tooling", names)

    def test_report(self) -> None:
        """The report lists every item."""
        text = "\n".join(self.setup.report())
        for name in ("Mikini", "Kurt", "Raw aluminum", "Grid plate"):
            self.assertIn(name, text)


class TestShopGridPlates(unittest.TestCase):
    """Grid plates described in the example shop's tooling file."""

    def test_same_as_tools(self) -> None:
        """The shop's plate is `tools.GRID_PLATE`, so it shares its cache."""
        shop = setups.grid_plates(setups.read(setups.SHOP))
        self.assertEqual(
            tools.SCGridPlate.from_shop(shop["Grid plate"]), tools.GRID_PLATE
        )

    def test_defaults(self) -> None:
        """Keys not given are 0: square corners, no chamfers, no tooling."""
        plate = tools.SCGridPlate.from_shop(
            {
                "name": "Small",
                "length": "4 in",
                "width": "4 in",
                "height": "1/2 in",
                "pitch": "1/2 in",
                "edge": "1/4 in",
                "hole_diameter": "0.144 in",
            }
        )
        self.assertEqual(len(plate.hole_centers()), 8 * 8)
        self.assertEqual(plate.tooling_holes(), [])
        self.assertEqual(
            (plate.corner_radius, plate.chamfer_depth), (0.0, 0.0)
        )


class TestProblems(unittest.TestCase):
    """Bad JSON is reported, with its entry, all at once."""

    def problems(self, change) -> str:
        """Return the problems after changing the example."""
        setup_json = copy.deepcopy(example())
        change(setup_json)
        with self.assertRaises(ValueError) as caught:
            setups.SCSetup(setup_json)
        return str(caught.exception)

    def test_no_unit(self) -> None:
        """A number with no unit is refused."""

        def change(setup_json):
            setup_json["tooling"][1]["height"] = "3"

        self.assertIn("tooling[1].height", self.problems(change))

    def test_orientation(self) -> None:
        """Only quarter turns are taken."""

        def change(setup_json):
            setup_json["tooling"][1]["orientation"] = "45 deg"

        self.assertIn("tooling[1].orientation", self.problems(change))

    def test_unknown(self) -> None:
        """Unknown names, kinds and keys are refused, all together."""

        def change(setup_json):
            setup_json["tooling"][0]["type"] = "Bridgeport"
            setup_json["tooling"][2]["kind"] = "clamp"
            setup_json["materials"][0]["colour"] = "red"
            setup_json["materials"][0]["parts"][0]["type"] = "Widget"

        text = self.problems(change)
        self.assertIn("tooling[0].type", text)
        self.assertIn("tooling[2].kind", text)
        self.assertIn("materials[0].colour", text)
        self.assertIn("materials[0].parts[0].type", text)

    def test_missing(self) -> None:
        """A missing key is refused."""

        def change(setup_json):
            del setup_json["machine"]["y_travel"]
            del setup_json["materials"][0]["size"]

        text = self.problems(change)
        self.assertIn("machine.y_travel: is missing", text)
        self.assertIn("materials[0].size: is missing", text)

    def test_too_wide(self) -> None:
        """A vise can not open past its limit."""

        def change(setup_json):
            setup_json["tooling"][1]["opening"] = "9 in"

        self.assertIn("tooling[1].opening", self.problems(change))

    def test_not_object(self) -> None:
        """A setup must be an object."""
        with self.assertRaises(ValueError):
            setups.SCSetup([])


class TestOtherSetups(unittest.TestCase):
    """Changes that the notes must catch."""

    def test_material_in_jaw(self) -> None:
        """Material wider than the gap is reported."""
        setup_json = example()
        setup_json["tooling"][1]["opening"] = "5 in"
        text = "\n".join(setups.SCSetup(setup_json).notes())
        self.assertIn("DOES NOT FIT", text)

    def test_not_clamped(self) -> None:
        """Material narrower than the gap is reported."""
        setup_json = example()
        setup_json["materials"][0]["size"][0] = "5 in"
        text = "\n".join(setups.SCSetup(setup_json).notes())
        self.assertIn("NOT CLAMPED: Raw aluminum is 1.000 in narrower", text)

    def test_out_of_reach(self) -> None:
        """A part past the travel is reported."""
        setup_json = example()
        setup_json["machine"]["y_travel"] = "4 in"
        text = "\n".join(setups.SCSetup(setup_json).notes())
        self.assertIn("OUT OF REACH: Grid plate reaches 0.750 in", text)

    def test_part_does_not_fit(self) -> None:
        """Material too small for the part is reported."""
        setup_json = example()
        setup_json["materials"][0]["size"][1] = "10 in"
        text = "\n".join(setups.SCSetup(setup_json).notes())
        self.assertIn(
            "Grid plate reaches past Raw aluminum along X, by 0.250 in "
            "on the low side and 0.250 in on the high side",
            text,
        )

    def test_part_margin(self) -> None:
        """The material is 1/2 in past the part at both ends."""
        material = setups.SCSetup(example()).materials[0]
        room = material.bounds()
        part = material.parts[0].bounds()
        self.assertAlmostEqual(part.low[0] - room.low[0], 0.5 * INCH)
        self.assertAlmostEqual(room.high[0] - part.high[0], 0.5 * INCH)

    def test_many_chunks(self) -> None:
        """A setup may hold several chunks, each with its own part."""
        setup_json = example()
        setup_json["materials"].append(
            copy.deepcopy(setup_json["materials"][0])
        )
        setup = setups.SCSetup(setup_json)
        self.assertEqual(len(setup.materials), 2)


class TestDemoStack(unittest.TestCase):
    """The stack that `show_demo.py` stands the demonstration plate on."""

    def setUp(self) -> None:
        path = HERE / "examples/setup/demo_stack.json"
        self.setup = setups.SCSetup(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def test_each_rests_on_the_last(self) -> None:
        """Each piece stands on the one below, up to the plate's bottom."""
        table, vise, first, second, plate = self.setup.tooling
        rails = table.placement.z + tools.MIKINI_1610L.thickness
        self.assertAlmostEqual(vise.placement.z, rails)
        rails += tools.KURT_D688.bed_top()
        self.assertAlmostEqual(first.placement.z, rails)
        self.assertAlmostEqual(second.placement.z, rails)
        self.assertAlmostEqual(
            plate.placement.z, rails + first.layer.parallel.height
        )

        # The demonstration plate is 1/2 in thick, with its top at Z 0.
        self.assertAlmostEqual(
            plate.placement.z + tools.GRID_PLATE.height, -0.5 * INCH
        )

    def test_centered_under_the_demonstration_plate(self) -> None:
        """The stack is centered on the 4 x 3 in plate, at X 2 and Y 1.5."""
        table, vise, first, second, plate = self.setup.tooling
        center = (2.0 * INCH, 1.5 * INCH)
        self.assertAlmostEqual(table.placement.x, center[0])
        self.assertAlmostEqual(table.placement.y, center[1])
        self.assertAlmostEqual(plate.placement.x, center[0])
        self.assertAlmostEqual(plate.placement.y, center[1])

        # The vise's gap, which is as wide as the grid plate.
        layer = vise.layer
        self.assertAlmostEqual(layer.opening, tools.GRID_PLATE.length)
        self.assertAlmostEqual(
            vise.placement.y - layer.vise.gap_center(layer.opening), center[1]
        )
        self.assertAlmostEqual(vise.placement.x, center[0])

        # The parallels are next to the jaws, under the grid plate.
        half = (layer.opening - first.layer.parallel.thickness) / 2.0
        self.assertAlmostEqual(first.placement.y, center[1] + half)
        self.assertAlmostEqual(second.placement.y, center[1] - half)


class TestModel(unittest.TestCase):
    """The setup in SolidCraft, with no window."""

    def test_model(self) -> None:
        """Nothing overlaps, and everything lands where the JSON says."""
        program = shutil.which("solidcraft-cli") or str(CLI)
        setup = setups.SCSetup(example())
        with SCHeadlessTransport(program) as transport:
            solidcraft = SCPyBind(transport)
            names = setup.model(solidcraft)
            self.assertEqual(len(names), 1 + 12 + 2 + 1 + 1)

            # The part overlaps its material on purpose.
            others = [name for name in names if name != "Grid plate"]
            result = solidcraft.inspect.interference(bodies=others)
            self.assertEqual(result["interferences"], [])
            self.assertEqual(result["unchecked"], [])

            # The fixed jaw is at the rear, its middle on `X = 0`.
            fixed = solidcraft.inspect.center_of_mass(
                bodies=["Kurt D688 fixed jaw"]
            )
            x, y, z = fixed["center"]
            self.assertAlmostEqual(x, 0.0)
            self.assertAlmostEqual(y, (3.0 + 0.725 + 0.5) * INCH)
            self.assertAlmostEqual(z, (2.64 + 1.735 / 2.0) * INCH)

            # A parallel lies along the jaw, next to it.
            parallel = solidcraft.inspect.center_of_mass(
                bodies=["Parallel 1-1/2 in A"]
            )
            x, y, z = parallel["center"]
            self.assertAlmostEqual(x, 0.0)
            self.assertAlmostEqual(y, 2.9375 * INCH)
            self.assertAlmostEqual(z, (2.64 + 0.75) * INCH)

            # The part's corners and grid holes turned with it: 20 along X
            # and 10 along Y, each hole two half cylinders.  Its tooling
            # holes are other sizes.
            faces = solidcraft.model.faces(body="Grid plate")
            arcs = [
                face["cylinder"]
                for face in faces["faces"]
                if face.get("cylinder")
            ]
            hole = FLAT_PLATE.hole_diameter / 2.0
            corners = [arc for arc in arcs if arc["radius"] > 0.2 * INCH]
            origins = [
                arc["origin"]
                for arc in arcs
                if abs(arc["radius"] - hole) < 0.001
            ]
            self.assertEqual(len(corners), 4)
            for corner in corners:
                self.assertAlmostEqual(corner["radius"], 0.25 * INCH)
                self.assertAlmostEqual(abs(corner["origin"][0]) / INCH, 5.0)
                self.assertAlmostEqual(abs(corner["origin"][1]) / INCH, 2.5)
            self.assertEqual(len(origins), 2 * 200)
            xs = {round(origin[0], 3) for origin in origins}
            ys = {round(origin[1], 3) for origin in origins}
            self.assertEqual((len(xs), len(ys)), (20, 10))
            self.assertAlmostEqual(max(xs) / INCH, 4.75, 2)
            self.assertAlmostEqual(max(ys) / INCH, 2.25, 2)


if __name__ == "__main__":
    unittest.main()
