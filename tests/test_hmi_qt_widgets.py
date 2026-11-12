"""Tests for `scraftcam.hmi.lcnc_hmi`, the HMI in Qt.

Qt draws offscreen (`use_headless()`), so no display is needed; the
HMI runs with a dry-run `HMIMachine` (no LinuxCNC).  The HMI's
behaviour is tested in `test_lcnc_hmi.py` and `test_hmi_*.py`; these
are only what is Qt's own: the jog step group, the slider, and the
filter on Qt's messages.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scraftcam.hmi import hmi_machine, lcnc_hmi

# Offscreen, before the one `QApplication` is made.
lcnc_hmi.use_headless()
# pylint: disable-next=wrong-import-order,wrong-import-position
from PySide6.QtCore import QMessageLogContext, QtMsgType  # noqa: E402

# pylint: disable-next=wrong-import-order,wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

APPLICATION: Any = QApplication.instance() or QApplication([])


# Class `TestQtHMI`:
class TestQtHMI(unittest.TestCase):
    """The whole HMI, offscreen, pressed through its port's words."""

    # Method `TestQtHMI.setUp()`:
    def setUp(self) -> None:
        """Make an HMI and a small program."""
        # No questions waiting, and a dry-run machine.
        lcnc_hmi.ANSWERS.clear()
        lcnc_hmi.ASKED.clear()
        self.machine: hmi_machine.HMIMachine = hmi_machine.HMIMachine(True)
        self.hmi: lcnc_hmi.HMI = lcnc_hmi.HMI(self.machine, 10.0, None)
        self.hmi.timer.stop()
        self.addCleanup(self.hmi.deleteLater)

        # A program with two tool changes.
        directory: tempfile.TemporaryDirectory[str] = (
            tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        )
        self.top: Path = Path(self.enterContext(directory))
        self.file: Path = self.top / "part.ngc"
        lines: list[str] = ["G20", "T1 M6", "G0 X1", "T8 M6", "G0 X2", "M2"]
        self.file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Method `TestQtHMI.tick()`:
    def tick(self) -> dict[str, Any]:
        """Run the HMI's poll, and return what it shows.

        Returns:
        * (`dict[str, Any]`): What `show` answers.
        """
        self.hmi.poll()
        shown: dict[str, Any] = json.loads(self.ask("show"))
        return shown

    # Method `TestQtHMI.ask()`:
    def ask(self, line: str) -> str:
        """Send one line, as the command port would.

        Arguments:
        * `line` (`str`): The command.

        Returns:
        * (`str`): The answer.
        """
        return self.hmi.handle(line)

    # Method `TestQtHMI.test_no_answer_is_no()`:
    def test_no_answer_is_no(self) -> None:
        """With no answer waiting, a question is answered No."""
        self.ask(f"open {self.file}")
        self.assertEqual(self.ask("press Set Origin"), "ok")
        self.assertFalse(self.tick()["origin_set"])

    # Method `TestQtHMI.test_jog_step()`:
    def test_jog_step(self) -> None:
        """A step button is chosen alone, and a jog goes by it."""
        self.assertEqual(self.tick()["step"], hmi_machine.JOG_STEP)
        self.assertEqual(self.ask("press .1"), "ok")
        self.assertEqual(self.tick()["step"], ".1")
        self.assertEqual(self.ask("press -Y"), "ok")
        self.assertEqual(self.machine.log[-1], "jog Y -1")
        self.assertEqual(
            sum(button.isChecked() for button in self.hmi.steps.buttons()), 1
        )

    # Method `TestQtHMI.test_speed()`:
    def test_speed(self) -> None:
        """The speed moves the slider, and the slider sets the speed."""
        # From the port: kept within the slider's range.
        self.ask("speed 2")
        self.assertEqual(self.tick()["speed"], "2x")
        self.ask("speed 100")
        self.assertEqual(self.tick()["speed"], "10x")

        # From the slider, at its ends.
        self.hmi.slider.setValue(0)
        self.assertAlmostEqual(self.hmi.override, hmi_machine.MIN_SPEED)
        self.hmi.slider.setValue(lcnc_hmi.SLIDER_STEPS)
        self.assertAlmostEqual(self.hmi.override, 10.0)

    # Method `TestQtHMI.test_qt_messages()`:
    def test_qt_messages(self) -> None:
        """Headless, only the offscreen platform's noise is dropped."""
        with mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            lcnc_hmi.qt_message(
                QtMsgType.QtWarningMsg,
                QMessageLogContext(),
                lcnc_hmi.OFFSCREEN_NOISE,
            )
            lcnc_hmi.qt_message(
                QtMsgType.QtWarningMsg, QMessageLogContext(), "Something"
            )
        self.assertEqual(stderr.getvalue(), "Something\n")


if __name__ == "__main__":
    unittest.main()
