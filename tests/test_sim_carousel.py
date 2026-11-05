"""Tests of the tool carousel drawn in SolidCraft (`CarouselView`)."""

import math
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from scraftcnc.carousel import Plan, Swap, spoke_ends
from scraftcnc.lcnc import sim_solidcraft


class TestSpokeEnds(unittest.TestCase):
    """The spokes' ends, with the slot in use at +X."""

    def test_front_at_plus_x(self) -> None:
        """The front slot is at +X; the others go counterclockwise."""
        ends = spoke_ends((1.0, 2.0, 3.0), 2.0, 4, 2)
        self.assertEqual(ends[2], (3.0, 2.0, 3.0))
        x, y, z = ends[3]
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 4.0)
        self.assertEqual(z, 3.0)
        x, y, _ = ends[1]
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 0.0)

    def test_all_at_spoke_length(self) -> None:
        """Every end is a spoke's length from the hub."""
        for end in spoke_ends((0.0, 0.0, 0.0), 2.5, 5, 1).values():
            self.assertAlmostEqual(math.hypot(end[0], end[1]), 2.5)


def tool_model() -> Any:
    """Return a stand-in for a `ToolModel`."""
    model: Any = mock.MagicMock()
    model.modeled.items.return_value = [f"items {id(model)}"]
    return model


class TestCarouselView(unittest.TestCase):
    """The spokes turn, and the tools follow, with no animation."""

    def setUp(self) -> None:
        self.solidcraft: Any = mock.MagicMock()
        # A stand-in for a `ToolRack`: its tool in use and its tools.
        self.rack: Any = cast(
            Any,
            SimpleNamespace(
                current=0,
                tools={number: tool_model() for number in (1, 4, 8)},
            ),
        )
        machine: Any = SimpleNamespace(
            carousel_hub=(10.0, 0.0, 0.0), spoke_length=2.0
        )
        planned: Plan = Plan({1: 4, 2: 8}, (Swap(2, 2, 8, 1),))
        self.view = sim_solidcraft.CarouselView(
            self.solidcraft, mock.MagicMock(), machine, planned, self.rack
        )

    def sample(self, tool: int, changed: bool, origin: Any = None) -> None:
        """Hand the view a sample, as the display does."""
        self.rack.current = tool
        self.view.sample(
            SimpleNamespace(tool=tool, origin=origin or (1.0, 0.0, 0.0)),
            changed,
        )

    def tip(self, number: int) -> tuple[float, float, float]:
        """Return where a tool was last moved to."""
        found: tuple[float, float, float] = self.rack.tools[
            number
        ].move_to.call_args.args[0]
        return found

    def test_first_sample_draws(self) -> None:
        """The first sample draws the spokes, in work coordinates."""
        with mock.patch.object(sim_solidcraft, "send_batch") as batch:
            self.sample(0, False)
        self.assertEqual(batch.call_count, 1)
        x, y, _ = self.tip(4)
        self.assertAlmostEqual(x, 11.0)
        self.assertAlmostEqual(y, 0.0)
        x, y, _ = self.tip(8)
        self.assertAlmostEqual(x, 7.0)
        self.assertAlmostEqual(y, 0.0)

    def test_same_sample_does_nothing(self) -> None:
        """Nothing is sent while nothing changes."""
        with mock.patch.object(sim_solidcraft, "send_batch") as batch:
            self.sample(0, False)
            calls: int = len(self.solidcraft.mock_calls)
            self.sample(0, False)
        self.assertEqual(batch.call_count, 1)
        self.assertEqual(len(self.solidcraft.mock_calls), calls)

    def test_change_turns_the_spokes(self) -> None:
        """A tool change puts its slot at +X; the others move."""
        with mock.patch.object(sim_solidcraft, "send_batch") as batch:
            self.sample(0, False)
            self.sample(8, True)
        self.assertEqual(self.view.front, 2)
        self.assertEqual(batch.call_count, 2)
        x, y, _ = self.tip(4)
        self.assertAlmostEqual(x, 7.0)
        self.assertAlmostEqual(y, 0.0)

    def test_swap(self) -> None:
        """A tool not in a slot comes in by its swap; the old is hidden."""
        with mock.patch.object(sim_solidcraft, "send_batch"):
            self.sample(0, False)
            self.sample(4, True)
            self.sample(1, True)
        self.assertEqual(self.view.slots, {1: 4, 2: 1})
        self.assertEqual(self.view.front, 2)
        hidden: list[Any] = [
            call.kwargs["items"]
            for call in self.solidcraft.browser.visibility.call_args_list
            if call.kwargs["visible"] is False
        ]
        self.assertIn(self.rack.tools[8].modeled.items(), hidden)

    def test_origin_change_places_again(self) -> None:
        """A new work origin draws the spokes again, moved."""
        with mock.patch.object(sim_solidcraft, "send_batch") as batch:
            self.sample(0, False)
            self.sample(0, False, (2.0, 0.0, 0.0))
        self.assertEqual(batch.call_count, 2)
        x, _, _ = self.tip(4)
        self.assertAlmostEqual(x, 10.0)


if __name__ == "__main__":
    unittest.main()
