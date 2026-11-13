"""Tests for `scraftcam.carousel`: the slot plan and its messages."""

import dataclasses
import tempfile
import unittest
from pathlib import Path

from scraftcam import carousel, demo, shops
from scraftcam.gcode import CNC
from scraftcam.hmi import hmi_machine
from scraftcam.machine import Machine
from scraftcam.setups import SHOP as EXAMPLE_SHOP
from scraftcam.tooling.shop_registries import use_shop
from tests.qt_app import make_hmi


class TestPlan(unittest.TestCase):
    """The slots filled in first-use order, and Belady's swaps."""

    def test_fits(self) -> None:
        """No swap when the tools fit; each tool loaded once."""
        planned = carousel.plan([4, 8, 4, 1], 4)
        self.assertEqual(planned.load, {1: 4, 2: 8, 3: 1})
        self.assertEqual(planned.swaps, ())

    def test_furthest_next_use(self) -> None:
        """The tool used again latest goes out."""
        planned = carousel.plan([1, 2, 3, 1, 2, 1], 2)
        self.assertEqual(planned.load, {1: 1, 2: 2})
        # At 3: 1 is next used at once, 2 later, so 2 goes.
        self.assertEqual(planned.swaps[0], carousel.Swap(2, 2, 2, 3))

    def test_never_used_again(self) -> None:
        """A tool never used again goes out first."""
        planned = carousel.plan([1, 2, 1, 3, 1], 2)
        self.assertEqual(planned.swaps, (carousel.Swap(3, 2, 2, 3),))

    def test_no_slots(self) -> None:
        """A carousel needs slots."""
        with self.assertRaises(ValueError):
            carousel.plan([1], 0)


class TestMessages(unittest.TestCase):
    """Tools named by `unique_id` and their holders' colors."""

    def test_colors(self) -> None:
        """The resistor code of each digit, padded to the shop's."""
        self.assertEqual(carousel.colors(23, 2), "red/orange")
        self.assertEqual(carousel.colors(5, 2), "black/green")
        self.assertEqual(
            carousel.swap_message(23, 43, 2),
            "Swap tool 23 (red/orange) with tool 43 (yellow/orange)",
        )


class TestDemo(unittest.TestCase):
    """The demo, on the example mill (4 slots)."""

    def setUp(self) -> None:
        self.shop = shops.read(Path(EXAMPLE_SHOP))
        use_shop(self.shop)

    def test_prescan(self) -> None:
        """Reading the G-code finds the sequence `CNC` kept."""
        cnc = demo.cut_demo()[0]
        lines = cnc.gcode().splitlines()
        kept = [number for _, number in cnc.changes]
        self.assertEqual(carousel.gcode_sequence(lines), kept)
        self.assertEqual(kept, [4, 8, 1, 5, 6, 1])
        text = carousel.plan_text(cnc.machine, kept)
        self.assertEqual(text[0], "Load the carousel before Start (+X spoke):")
        self.assertIn("Swaps during the run: 1", text)

    def test_manual(self) -> None:
        """A machine without a carousel prompts at every change."""
        machine: Machine = shops.cnc_machine(
            self.shop, "Shop mill", "6061 aluminum"
        )
        for slots, pauses in ((0, 3), (2, 1)):
            cnc = CNC(
                "manual", dataclasses.replace(machine, carousel_slots=slots)
            )
            for number in (1, 4, 8):
                cnc.change_tool(number)
            cnc.finish()
            lines = cnc.gcode().splitlines()
            self.assertEqual(sum(line == "M0" for line in lines), pauses)
        self.assertEqual(
            carousel.plan_text(
                dataclasses.replace(machine, carousel_slots=0), [4]
            ),
            [],
        )

    def test_tools_tab(self) -> None:
        """The HMI's Tools tab lists the carousel's load and swaps."""
        hmi = make_hmi(hmi_machine.HMIMachine(True))
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch, "demo.ngc")
            path.write_text(demo.cut_demo()[0].gcode(), encoding="utf-8")
            hmi.open(str(path))
            hmi.poll()
            hmi.handle("tab Tools")
        table = hmi.show_state()["texts"][-1]
        self.assertIn("Load the carousel before Start", table)
        self.assertIn("slot 1: tool 5 (black/green) T04", table)
        self.assertIn("Swaps during the run: 1", table)


if __name__ == "__main__":
    unittest.main()
