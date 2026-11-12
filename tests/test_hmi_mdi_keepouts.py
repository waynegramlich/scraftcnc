"""Tests for checking typed (MDI) moves against keep-outs (S12)."""

import unittest
from typing import Any, cast

from scraftcam.geometry import Corner, RoundedPolygon
from scraftcam.hmi import lcnc_hmi, lcnc_hmi_headless


def clamp(x0: float, x1: float, top: float) -> RoundedPolygon:
    """Return a keep-out from `x0` to `x1` (inches), 1 in wide in Y."""
    corners = [Corner(x0, -0.5), Corner(x1, -0.5), Corner(x1, 0.5)]
    return RoundedPolygon("clamp", [*corners, Corner(x0, 0.5)], -1.0, top)


class TestMdiKeepOuts(unittest.TestCase):
    """MDI lines typed and run through the command port, no LinuxCNC.

    The tool tip is at the work origin, and no tool is in the spindle
    (radius 0).
    """

    def setUp(self) -> None:
        lcnc_hmi.use_headless()
        self.machine = lcnc_hmi.HMIMachine(True)
        self.root: Any = lcnc_hmi_headless.Tk()
        self.hmi = lcnc_hmi.HMI(cast(Any, self.root), self.machine, 10.0, None)

    def guard(self) -> None:
        """Give the HMI a setup's keep-out, with its origin set."""
        self.hmi.zones = [clamp(0.5, 1.5, 0.25)]
        self.hmi.origin_set = True

    def run_line(self, line: str) -> str:
        """Type a line and press Execute; return the port's answer."""
        self.hmi.handle(f"type {line}")
        return self.hmi.handle("press Execute")

    def sent(self) -> list[str]:
        """Return the MDI lines sent so far."""
        return [entry for entry in self.machine.log if entry.startswith("mdi")]

    def test_refused(self) -> None:
        """A move into a keep-out sends nothing, and says why."""
        self.guard()
        answer: str = self.run_line("G0 X1")
        self.assertIn("MDI refused: it would enter clamp", answer)
        self.assertIn("would enter clamp", self.hmi.show()["message"])
        self.assertEqual(self.sent(), [])

        # One that stays clear is sent.
        self.assertEqual(self.run_line("G0 X0.4"), "ok")
        self.assertEqual(self.sent(), ["mdi G0 X0.4"])

    def test_metric(self) -> None:
        """Millimeters are read as such: 25.4 mm hits, 10 mm does not."""
        self.guard()
        self.assertIn("refused", self.run_line("G21 G0 X25.4"))
        self.assertEqual(self.run_line("G21 G0 X10"), "ok")
        self.assertEqual(self.sent(), ["mdi G21 G0 X10"])

    def test_incremental_refused(self) -> None:
        """`G91` moves are not followed, so they are refused."""
        self.guard()
        self.assertIn("G91", self.run_line("G91 G0 X0.1"))
        self.assertEqual(self.sent(), [])

    def test_no_move(self) -> None:
        """A line that does not move runs."""
        self.guard()
        self.assertEqual(self.run_line("G10 L20 P1 X0"), "ok")
        self.assertEqual(self.sent(), ["mdi G10 L20 P1 X0"])

    def test_unchecked(self) -> None:
        """No setup: the line runs, and that is said once."""
        self.assertEqual(self.run_line("G0 X1"), "ok")
        self.assertEqual(
            self.hmi.show()["message"], "MDI not checked: no setup"
        )
        self.assertEqual(self.sent(), ["mdi G0 X1"])

    def test_axis_words_only(self) -> None:
        """`Z-4` (no move word) is checked as a straight move (the user's
        drive through the grid plate)."""
        self.guard()
        self.assertIn("refused", self.run_line("X1"))
        self.assertEqual(self.sent(), [])
        self.assertEqual(
            len(lcnc_hmi.mdi_segments("Z-4", (1, 0, 1), False)), 1
        )

    def test_machine_coordinates_refused(self) -> None:
        """`G28`, `G30` and `G53` moves are not followed, so refused."""
        self.guard()
        for line in ("G28 Z1", "G30", "G53 G0 Z0"):
            self.assertIn("can not be checked", self.run_line(line))
        self.assertEqual(self.sent(), [])

    def test_segments(self) -> None:
        """An arc comes back as short pieces, end to end, in inches."""
        pieces = lcnc_hmi.mdi_segments(
            "G2 X2 Y0 I1 J0 F5", (0.0, 0.0, 0.0), False
        )
        self.assertGreater(len(pieces), 2)
        for value in pieces[0][0]:
            self.assertAlmostEqual(value, 0.0)
        x, y, _ = pieces[-1][1]
        self.assertAlmostEqual(x, 2.0)
        self.assertAlmostEqual(y, 0.0)


if __name__ == "__main__":
    unittest.main()
