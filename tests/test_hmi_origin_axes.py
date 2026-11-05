"""Tests for setting the origin one axis at a time (`T.hs~5.1.5` S7)."""

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from scraftcnc.hmi import lcnc_hmi, lcnc_hmi_headless


class TestOriginAxes(unittest.TestCase):
    """Set X, Set Y and Set Z, through the command port's words."""

    def setUp(self) -> None:
        lcnc_hmi.use_headless()
        lcnc_hmi_headless.ANSWERS.clear()
        lcnc_hmi_headless.ASKED.clear()
        self.machine = lcnc_hmi.HMIMachine(True)
        self.root: Any = lcnc_hmi_headless.Tk()
        self.hmi = lcnc_hmi.HMI(cast(Any, self.root), self.machine, 10.0, None)
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.file = Path(scratch.name, "part.ngc")
        self.file.write_text("G20\nG0 X1\nM2\n", encoding="utf-8")
        self.assertEqual(self.ask(f"open {self.file}"), "ok")

    def ask(self, line: str) -> str:
        """Send one line, as the command port would."""
        return self.hmi.handle(line)

    def mdi(self) -> list[str]:
        """Return the MDI lines sent so far."""
        return [entry for entry in self.machine.log if entry.startswith("mdi")]

    def set_axis(self, axis: str, value: str) -> str:
        """Type a number for an axis, answer yes, and press its button."""
        self.ask(f"origin {axis} {value}")
        self.ask("answer yes")
        return self.ask(f"press Set {axis}")

    def test_one_axis(self) -> None:
        """One axis sets only that axis, in the program's units."""
        self.assertEqual(self.set_axis("X", "1.25"), "ok")
        self.assertEqual(self.mdi(), ["mdi G20", "mdi G10 L20 P1 X1.25"])
        shown = self.hmi.show()
        self.assertEqual(shown["axes_set"], ["X"])
        self.assertFalse(shown["origin_set"])
        self.assertEqual(shown["message"], "Origin still to set: Y Z")
        self.assertEqual(shown["axis_entries"]["X"], "1.25")

    def test_bad_number(self) -> None:
        """A bad number is colored, and greys its button out."""
        self.ask("origin Y 1.2.3")
        self.assertEqual(self.hmi.show()["buttons"]["Set Y"], "disabled")
        self.assertEqual(
            str(self.hmi.axis_entries["Y"].cget("background")), lcnc_hmi.BAD
        )
        self.assertIn("greyed out", self.ask("press Set Y"))
        self.assertIn("error: no axis", self.ask("origin W 1"))

    def test_no_sends_nothing(self) -> None:
        """Answering No (the default) sends nothing."""
        self.ask("origin Z 0")
        self.assertEqual(self.ask("press Set Z"), "ok")
        self.assertEqual(self.mdi(), [])
        self.assertEqual(self.hmi.show()["axes_set"], [])

    def test_all_three(self) -> None:
        """All three axes, in any order, set the origin; Start comes up."""
        for axis, value in (("Z", "0"), ("X", "-1"), ("Y", "2.5")):
            self.assertEqual(self.set_axis(axis, value), "ok")
        self.root.run_one()
        shown = self.hmi.show()
        self.assertTrue(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "normal")
        self.assertEqual(shown["message"], "")

        # A new open clears them.
        self.ask(f"open {self.file}")
        shown = self.hmi.show()
        self.assertEqual((shown["axes_set"], shown["origin_set"]), ([], False))

    def test_not_while_running(self) -> None:
        """While a program runs, the buttons are greyed out."""
        self.ask("origin X 1")
        self.hmi.set_running(True, False)
        self.assertIn("greyed out", self.ask("press Set X"))
        self.hmi.set_running(True, True)
        self.assertEqual(self.hmi.show()["buttons"]["Set X"], "disabled")
        self.assertEqual(self.mdi(), [])


if __name__ == "__main__":
    unittest.main()
