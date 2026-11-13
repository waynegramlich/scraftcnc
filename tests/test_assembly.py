"""Tests for `scraftcam.assembly`."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from scraftcam.assembly import (
    Assembly,
    AssemblyItem,
    Stock,
    lengths_text,
    millimeters,
    resolve,
)
from scraftcam.demo import DemoPart, demo_assembly
from scraftcam.setups import Setup
from scraftcam.shops import read
from scraftcam.tooling.cutter_models import EXAMPLE_SHOP
from scraftcam.tooling.shop_registries import use_shop
from scraftcam.tooling.tools import GridPlate


# Function `setUpModule()`:
def setUpModule() -> None:  # pylint: disable=invalid-name
    """Fill the name registries from the example shop."""
    use_shop(read(EXAMPLE_SHOP))


# Function `assert_same()`:
def assert_same(
    test: unittest.TestCase, actual: Assembly, wanted: Assembly
) -> None:
    """Check that two assemblies match, lengths to within 1e-6 mm.

    Lengths are written to 4 places with a unit, so a round trip
    through inches may not give back the very same float.
    """
    test.assertEqual(len(actual.items), len(wanted.items))
    got: AssemblyItem
    want: AssemblyItem
    for got, want in zip(actual.items, wanted.items, strict=True):
        test.assertEqual(
            replace(got, location=(0.0, 0.0, 0.0), keep_out=()),
            replace(want, location=(0.0, 0.0, 0.0), keep_out=()),
        )
        test.assertEqual(len(got.keep_out), len(want.keep_out))
        lengths: tuple[float, ...] = got.location + tuple(
            mm for box in got.keep_out for mm in box
        )
        wanted_lengths: tuple[float, ...] = want.location + tuple(
            mm for box in want.keep_out for mm in box
        )
        mm: float
        wanted_mm: float
        for mm, wanted_mm in zip(lengths, wanted_lengths, strict=True):
            test.assertAlmostEqual(mm, wanted_mm, delta=1e-6)


class TestStock(unittest.TestCase):
    """`Stock`."""

    def test_sizes(self) -> None:
        """Sizes with units become millimeters."""
        stock: Stock = Stock("aluminum_6061", ("4 in", "3mm", "12.5 mm"))
        self.assertAlmostEqual(stock.dx, 101.6)
        self.assertAlmostEqual(stock.dy, 3.0)
        self.assertAlmostEqual(stock.dz, 12.5)
        self.assertEqual(stock.seat(), (0.0, 0.0, 12.5))
        self.assertEqual(stock.origin(), (-50.8, -1.5, 12.5))
        self.assertEqual(stock.keep_out((0.0, 0.0, 0.0)).prisms, [])
        self.assertIn("aluminum_6061", stock.name)

    def test_errors(self) -> None:
        """Bad materials and sizes are refused."""
        with self.assertRaises(ValueError):
            Stock("", ("1 in", "1 in", "1 in"))
        with self.assertRaisesRegex(ValueError, "size y"):
            Stock("brass", ("1 in", "2 parsecs", "1 in"))
        with self.assertRaisesRegex(ValueError, "> 0"):
            Stock("brass", ("1 in", "1 in", "0 in"))
        with self.assertRaisesRegex(TypeError, "size x.*unit"):
            Stock("brass", (1.0, "1 in", "1 in"))
        with self.assertRaises(TypeError):
            millimeters(True, "flag")


def _assembly() -> Assembly:
    """Return a small assembly."""
    return Assembly(
        [
            AssemblyItem(
                "tooling",
                "vise",
                "scraftcam.tooling.mount:vise_mount",
                {"opening": "4 in"},
                keep_out=((0.0, 0.0, 0.0, 10.0, 20.0, 30.0),),
                note="Clean the jaws.",
            ),
            AssemblyItem(
                "stock",
                "plate",
                "scraftcam.assembly:Stock",
                {
                    "material": "aluminum_6061",
                    "size": ["4 in", "3 in", "1/2 in"],
                },
                location=(1.0, 2.0, 3.0),
                orientation=1,
                color="#c0c0c0",
                transparency=0.5,
            ),
        ]
    )


class TestAssembly(unittest.TestCase):
    """`Assembly` and `AssemblyItem`."""

    def test_round_trip(self) -> None:
        """`to_dict()` and `from_dict()` give the same assembly."""
        assembly: Assembly = _assembly()
        table: dict[str, Any] = assembly.to_dict()
        self.assertEqual(
            [item["name"] for item in table["item"]],
            [
                "vise",
                "plate",
            ],
        )
        self.assertNotIn("color", table["item"][0])
        self.assertEqual(table["item"][1]["location"][0], "1 mm")
        self.assertTrue(table["item"][0]["keep_out"][0].endswith(" mm"))
        assert_same(self, Assembly.from_dict(table), assembly)

    def test_old_box_form(self) -> None:
        """A box as six strings, each with a unit, still reads (#82)."""
        table: dict[str, Any] = _assembly().to_dict()
        table["item"][0]["keep_out"] = [
            ["0 in", "0 in", "0 in", "1 in", "2 in", "3 in"]
        ]
        new: dict[str, Any] = _assembly().to_dict()
        new["item"][0]["keep_out"] = ["0 0 0 1 2 3 in"]
        self.assertEqual(
            Assembly.from_dict(table).items[0].keep_out,
            Assembly.from_dict(new).items[0].keep_out,
        )
        self.assertEqual(lengths_text((0.0, 25.4, 1.0)), "0 25.4 1 mm")
        self.assertEqual(lengths_text((0.0, 25.4)), "0 1 in")

    def test_units_in_tables(self) -> None:
        """Locations and keep-outs may have units."""
        item: AssemblyItem = AssemblyItem.from_dict(
            {
                "kind": "part",
                "name": "part",
                "call": "scraftcam.demo:demo_part",
                "location": ["1 in", "0 in", "2mm"],
                "keep_out": [["0 in", "0 in", "0 in", "1 in", "1mm", "1mm"]],
            },
            1,
        )
        actual: float
        wanted: float
        for actual, wanted in zip(
            item.location, (25.4, 0.0, 2.0), strict=True
        ):
            self.assertAlmostEqual(actual, wanted)
        for actual, wanted in zip(
            item.keep_out[0], (0.0, 0.0, 0.0, 25.4, 1.0, 1.0), strict=True
        ):
            self.assertAlmostEqual(actual, wanted)
        self.assertEqual(
            AssemblyItem.from_dict(
                {"kind": "part", "name": "p", "call": "m:f"}, 1
            ).location,
            (0.0, 0.0, 0.0),
        )

    def test_errors(self) -> None:
        """Errors name the item."""
        good: dict[str, Any] = _assembly().to_dict()["item"][1]
        changes: list[tuple[dict[str, Any], str]] = [
            ({"kind": "spindle"}, "kind"),
            ({"call": "no_colon"}, "call"),
            ({"call": "m:A.b.c"}, "call"),
            ({"orientation": 4}, "orientation"),
            ({"transparency": 2.0}, "transparency"),
            ({"location": ["1 in", "2 in"]}, "3 lengths"),
            ({"location": [1, 2, 3]}, "not a length with a unit"),
            ({"keep_out": [["1 in"] * 3 + ["0 in"] + ["2 in"] * 2]}, "empty"),
            ({"keep_out": [[0, 0, 0, 1, 1, 1]]}, "not a length with a unit"),
            ({"keep_out": [[1, 2, 3]]}, "6 lengths"),
            ({"colour": "red"}, "unknown"),
        ]
        change: dict[str, Any]
        expected: str
        for change, expected in changes:
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(
                    ValueError, rf"item 1 \('plate'\).*{expected}"
                ),
            ):
                Assembly.from_dict({"item": [good | change]})
        with self.assertRaisesRegex(ValueError, "missing"):
            Assembly.from_dict({"item": [{"name": "x"}]})
        with self.assertRaisesRegex(ValueError, "twice"):
            Assembly.from_dict({"item": [good, good]})
        with self.assertRaisesRegex(ValueError, "item list"):
            Assembly.from_dict({})
        with self.assertRaisesRegex(ValueError, "not a list"):
            Assembly.from_dict({"item": 3})
        with self.assertRaisesRegex(ValueError, "args"):
            Assembly.from_dict({"item": [good | {"args": 3}]})


class TestResolve(unittest.TestCase):
    """`resolve()` builds each demonstration item from its call."""

    def test_demo_items(self) -> None:
        """Each tooling call gives the layer `demo_stack.json` gives."""
        # The layers from the JSON, in the same order as `_TOOLING`.
        path: Path = Path("examples/setup/demo_stack.json")
        setup: Setup = Setup(json.loads(path.read_text("utf-8")))
        # The demonstration's grid plate is unchamfered (`chamfer=False`).
        expected: list[Any] = [
            (
                replace(tool.layer, chamfer_width=0.0, edge_chamfer=0.0)
                if isinstance(tool.layer, GridPlate)
                else tool.layer
            )
            for tool in setup.tooling
        ]
        items: list[AssemblyItem] = demo_assembly().items
        tooling: list[AssemblyItem] = [
            item for item in items if item.kind == "tooling"
        ]
        self.assertEqual(len(tooling), len(expected))
        for item, layer in zip(tooling, expected, strict=True):
            with self.subTest(item=item.name):
                self.assertEqual(resolve(item), layer)

        # The stock is an `Stock`; the part resolves to the plate,
        # without SolidCraft.
        stock: AssemblyItem = next(
            item for item in items if item.kind == "stock"
        )
        self.assertIsInstance(resolve(stock), Stock)
        part: AssemblyItem = next(
            item for item in items if item.kind == "part"
        )
        plate: Any = resolve(part)
        self.assertIsInstance(plate, DemoPart)
        self.assertEqual(plate.material, "6061 aluminum")
        self.assertAlmostEqual(plate.thickness, 12.7)

    def test_errors_name_the_item(self) -> None:
        """A bad call or bad arguments name the item."""
        bad: AssemblyItem = AssemblyItem(
            "tooling", "odd", "scraftcam.assembly:Nope", {}
        )
        with self.assertRaisesRegex(ValueError, "'odd'"):
            resolve(bad)
        unknown: AssemblyItem = AssemblyItem(
            "tooling",
            "vise",
            "scraftcam.tooling.mount:MachineViseLayer.named",
            {"vise": "no_such_vise", "opening": "1 in"},
        )
        with self.assertRaisesRegex(ValueError, "'vise'.*kurt_d688"):
            resolve(unknown)
        wide: AssemblyItem = replace(
            unknown, args={"vise": "kurt_d688", "opening": "20 in"}
        )
        with self.assertRaisesRegex(ValueError, "'vise'.*opening"):
            resolve(wide)


if __name__ == "__main__":
    unittest.main()
