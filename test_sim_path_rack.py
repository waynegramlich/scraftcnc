"""Tests of which tool path `sim_solidcraft.SCPathRack` shows."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scraftcnc.lcnc import sim_solidcraft

PROGRAM: str = """G20 G90
G0 X0 Y0 Z1
T4 M6 G43 H4
G0 X1 Y1
T8 M6 G43 H8
G0 X2 Y2
T1 M6 G43 H1
G0 X3 Y3
M2
"""


class TestPathRack(unittest.TestCase):
    """Only the path of the tool in use shows, from before the start."""

    def setUp(self) -> None:
        self.solidcraft = mock.MagicMock()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(sim_solidcraft, "send_batch"),
        ):
            file = Path(directory, "p.ngc")
            file.write_text(PROGRAM, encoding="utf-8")
            self.rack = sim_solidcraft.SCPathRack(
                self.solidcraft, mock.MagicMock(), file
            )

    def shown(self) -> list[tuple[bool, list[str]]]:
        """Return each visibility change, in order."""
        return [
            (call.kwargs["visible"], call.kwargs["items"])
            for call in self.solidcraft.browser.visibility.call_args_list
        ]

    def test_first_path_shows_before_the_start(self) -> None:
        """The first tool's path shows, with the next one drawn."""
        self.assertEqual(self.shown(), [(True, ["T04 path"])])
        self.assertEqual(sorted(self.rack.sketches), [4, 8])

    def test_empty_spindle_changes_nothing(self) -> None:
        """No tool in the spindle leaves the first path showing."""
        self.rack.show(0)
        self.assertEqual(self.shown(), [(True, ["T04 path"])])

    def test_tool_change(self) -> None:
        """A new tool hides the old path, and shows its own."""
        with mock.patch.object(sim_solidcraft, "send_batch"):
            self.rack.show(4)
            self.rack.show(8)
        self.assertEqual(
            self.shown(),
            [
                (True, ["T04 path"]),
                (False, ["T04 path"]),
                (True, ["T08 path"]),
            ],
        )
        self.assertIn(1, self.rack.sketches)


if __name__ == "__main__":
    unittest.main()
