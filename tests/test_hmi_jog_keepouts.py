"""Tests for checking jogs against the setup's keep-outs (`T.hs~5.1.5` S8)."""

import unittest

from scraftcam.geometry import Corner, RoundedPolygon
from scraftcam.hmi import lcnc_hmi
from tests.qt_hmi import make_hmi


def clamp(x0: float, x1: float, top: float) -> RoundedPolygon:
    """Return a keep-out from `x0` to `x1` (inches), 1 in wide in Y."""
    corners = [Corner(x0, -0.5), Corner(x1, -0.5), Corner(x1, 0.5)]
    return RoundedPolygon("clamp", [*corners, Corner(x0, 0.5)], -1.0, top)


class TestJogKeepOuts(unittest.TestCase):
    """Jogs pressed through the command port's words, with no LinuxCNC.

    The tool tip is at the work origin, and no tool is in the spindle
    (radius 0).
    """

    def setUp(self) -> None:
        self.machine = lcnc_hmi.HMIMachine(True)
        self.hmi = make_hmi(self.machine)

    def guard(self, zone: RoundedPolygon) -> None:
        """Give the HMI a setup's keep-out, with its origin set."""
        self.hmi.zones = [zone]
        self.hmi.origin_set = True

    def jogs(self) -> list[str]:
        """Return the jogs sent so far."""
        return [entry for entry in self.machine.log if entry.startswith("jog")]

    def test_refused(self) -> None:
        """A jog into a keep-out sends nothing, and says why."""
        self.guard(clamp(0.5, 1.5, 0.25))
        self.hmi.handle("press 1")
        answer = self.hmi.handle("press +X")
        self.assertIn("Jog refused: it would enter clamp", answer)
        self.assertIn("smaller step", self.hmi.show_state()["message"])
        self.assertEqual(self.jogs(), [])

        # A smaller step that stays clear is sent.
        self.hmi.handle("press .1")
        self.assertEqual(self.hmi.handle("press +X"), "ok")
        self.assertEqual(self.jogs(), ["jog X +1"])

    def test_unchecked(self) -> None:
        """No setup, or no origin: jogs go, and that is said once."""
        self.assertEqual(self.hmi.handle("press +X"), "ok")
        self.assertEqual(
            self.hmi.show_state()["message"], "Jogs not checked: no setup"
        )
        self.hmi.message.setText("")
        self.hmi.handle("press -X")
        self.assertEqual(self.hmi.show_state()["message"], "")

        self.hmi.zones = [clamp(0.5, 1.5, 0.25)]
        self.hmi.handle("press 1")
        self.assertEqual(self.hmi.handle("press +X"), "ok")
        self.assertEqual(
            self.hmi.show_state()["message"],
            "Jogs not checked: origin not set",
        )
        self.assertEqual(len(self.jogs()), 3)

    def test_inside(self) -> None:
        """Inside a keep-out, only up goes; raise Z first."""
        self.guard(clamp(-0.5, 0.5, 0.25))
        self.hmi.handle("press .1")
        self.assertEqual(self.hmi.handle("press +Z"), "ok")
        self.assertIn("refused", self.hmi.handle("press +X"))
        self.assertIn("refused", self.hmi.handle("press -Z"))
        self.assertEqual(self.jogs(), ["jog Z +1"])

    def test_jog_hit(self) -> None:
        """The tool's radius counts: a wide tool beside a keep-out hits."""
        zones = [clamp(0.5, 1.5, 0.25)]
        start = (0.0, 0.0, 0.0)
        self.assertEqual(lcnc_hmi.jog_hit(zones, start, (0.3, 0, 0), 0.1), "")
        self.assertEqual(
            lcnc_hmi.jog_hit(zones, start, (0.3, 0, 0), 0.25), "clamp"
        )
        self.assertEqual(lcnc_hmi.jog_hit(zones, start, (0, 0, 1), 9.0), "")


if __name__ == "__main__":
    unittest.main()
