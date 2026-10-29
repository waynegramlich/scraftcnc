"""Tests for `scmachine.py`: run `python3 -m unittest -v`."""

import unittest
from pathlib import Path

from scmachine import SCMachine, SCTool
from shops import cnc_machine, read
from test_solidcraftcnc import machine

# The example shop.
SHOP_FILE: Path = (
    Path(__file__).resolve().parent / "examples/shop/home_shop.toml"
)


# Class `TestMachine`:
class TestMachine(unittest.TestCase):
    """Machine preferences and tool tables."""

    # Method `TestMachine.test_example_shop()`:
    def test_example_shop(self) -> None:
        """The example shop's mill, with its tools."""
        mill: SCMachine = cnc_machine(
            read(SHOP_FILE), "Shop mill", "6061 aluminum"
        )
        self.assertEqual(mill.change_words(4), ["T04", "M6", "G43", "H04"])
        self.assertEqual(mill.tool(1).kind, "end mill")
        self.assertEqual(mill.drill_for(mill.tool(1)).number, 4)
        self.assertAlmostEqual(mill.through_overcut, 0.1)
        self.assertEqual(mill.tool(5).angle, 90.0)
        self.assertEqual(mill.tool(6).radius, 0.0625)
        self.assertEqual(mill.named("1/8 in cobalt jobber drill").number, 2)
        with self.assertRaises(KeyError):
            mill.tool(3)
        with self.assertRaises(KeyError):
            mill.named("no such tool")

    # Method `TestMachine.test_preferences()`:
    def test_preferences(self) -> None:
        """Preferences that make no sense are refused."""
        cases: tuple[dict[str, object], ...] = (
            {"clearance": -0.01},
            {"tool_change_z": 0.5},
            {"rapid_speed": 0.0},
            {"stepover": 0.0},
            {"stepover": 1.1},
            {"ramp_angle": 0.0},
            {"through_overcut": 1.5},
            {"tool_change": "T{tool:02d}"},
            {"tool_change": "{number}"},
        )
        changes: dict[str, object]
        for changes in cases:
            with self.assertRaises(ValueError, msg=str(changes)):
                machine(**changes)
        with self.assertRaises(ValueError):
            SCTool(1, "Bad", "end mill", 0.0, 1200, 1.0, 1.0)
        with self.assertRaises(ValueError):
            SCTool(0, "Bad", "end mill", 0.25, 1200, 1.0, 1.0)
        with self.assertRaises(ValueError):
            SCTool(5, "Bad", "chamfer", 0.02, 1200, 1.0, 1.0, angle=180.0)
        with self.assertRaises(ValueError):
            SCTool(6, "Bad", "corner round", 0.1, 1200, 1.0, 1.0)


if __name__ == "__main__":
    unittest.main()
