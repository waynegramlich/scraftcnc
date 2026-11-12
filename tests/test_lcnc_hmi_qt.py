"""Tests for `scraftcam.hmi.lcnc_hmi_qt`, the HMI in Qt.

Qt draws offscreen (`use_headless()`), so no display is needed; the
HMI runs with a dry-run `HMIMachine` (no LinuxCNC), and is pressed
through its command port's words, as `test_lcnc_hmi.py` presses the
`tkinter` HMI.
"""

import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any
from unittest import mock

from scraftcam.hmi import lcnc_hmi, lcnc_hmi_qt

# Offscreen, before the one `QApplication` is made.
lcnc_hmi_qt.use_headless()
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
        lcnc_hmi_qt.ANSWERS.clear()
        lcnc_hmi_qt.ASKED.clear()
        self.machine: lcnc_hmi.HMIMachine = lcnc_hmi.HMIMachine(True)
        self.hmi: lcnc_hmi_qt.HMI = lcnc_hmi_qt.HMI(self.machine, 10.0, None)
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

    # Method `TestQtHMI.open_with_origin()`:
    def open_with_origin(self) -> None:
        """Open the program, and set its origin where the tool is."""
        self.assertEqual(self.ask(f"open {self.file}"), "ok")
        self.ask("answer yes")
        self.assertEqual(self.ask("press Set Origin"), "ok")

    # Method `TestQtHMI.test_program_shows()`:
    def test_program_shows(self) -> None:
        """An opened program's lines come up in the coming window."""
        self.assertEqual(self.ask(f"open {self.file}"), "ok")
        self.assertEqual(self.tick()["coming"].split("\n")[0], "G20")
        self.assertEqual(self.machine.log[0], f"open {self.file}")

    # Method `TestQtHMI.test_origin_gate()`:
    def test_origin_gate(self) -> None:
        """Start waits for the origin; jogs do not."""
        # Opened: Start is greyed out until the origin is set.
        self.ask(f"open {self.file}")
        shown: dict[str, Any] = self.tick()
        self.assertFalse(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "disabled")
        self.assertEqual(shown["buttons"]["+X"], "normal")
        self.assertEqual(shown["message"], "Set the origin first")

        # Set Origin, after Yes.
        self.ask("answer yes")
        self.ask("press Set Origin")
        shown = self.tick()
        self.assertTrue(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "normal")
        self.assertEqual(shown["message"], "")
        self.assertIn("Set Origin", lcnc_hmi_qt.ASKED[0])

    # Method `TestQtHMI.test_no_answer_is_no()`:
    def test_no_answer_is_no(self) -> None:
        """With no answer waiting, a question is answered No."""
        self.ask(f"open {self.file}")
        self.assertEqual(self.ask("press Set Origin"), "ok")
        self.assertFalse(self.tick()["origin_set"])

    # Method `TestQtHMI.test_buttons_follow_the_run()`:
    def test_buttons_follow_the_run(self) -> None:
        """Start, Pause and Resume grey out as a person sees them."""
        # Before a run, Pause is greyed out.
        self.open_with_origin()
        buttons: dict[str, str] = self.tick()["buttons"]
        self.assertEqual(buttons["Pause"], "disabled")
        self.assertEqual(self.ask("press Pause"), "error: Pause is greyed out")

        # While running, Start and the jogs are.
        self.assertEqual(self.ask("press Start"), "ok")
        buttons = self.tick()["buttons"]
        self.assertEqual(buttons["Start"], "disabled")
        self.assertEqual(buttons["+X"], "disabled")
        self.assertEqual(self.ask("press Start"), "error: Start is greyed out")

        # Pause, Resume and Reset.
        self.assertEqual(self.ask("press Pause"), "ok")
        self.assertEqual(self.tick()["buttons"]["Resume"], "normal")
        self.assertEqual(self.ask("press Resume"), "ok")
        self.assertEqual(self.ask("press Reset"), "ok")
        self.assertEqual(self.tick()["buttons"]["Start"], "normal")
        self.assertEqual(
            [
                entry
                for entry in self.machine.log
                if not entry.startswith(("open", "tool table", "mdi"))
            ],
            ["run 0", "pause", "resume", "stop"],
        )

    # Method `TestQtHMI.test_tool_line()`:
    def test_tool_line(self) -> None:
        """-Tool and +Tool move the start line between tool changes."""
        self.ask(f"open {self.file}")
        self.tick()
        self.assertEqual(self.ask("press +Tool"), "ok")
        self.assertEqual(self.hmi.start, 2)
        self.ask("press +Tool")
        self.assertEqual(self.hmi.start, 4)
        self.ask("press -Tool")
        self.assertEqual(self.hmi.start, 2)

    # Method `TestQtHMI.test_jog_step()`:
    def test_jog_step(self) -> None:
        """A step button is chosen alone, and a jog goes by it."""
        self.assertEqual(self.tick()["step"], lcnc_hmi.JOG_STEP)
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
        self.assertAlmostEqual(self.hmi.override, lcnc_hmi.MIN_SPEED)
        self.hmi.slider.setValue(lcnc_hmi_qt.SLIDER_STEPS)
        self.assertAlmostEqual(self.hmi.override, 10.0)

    # Method `TestQtHMI.test_mdi_line()`:
    def test_mdi_line(self) -> None:
        """The MDI line is colored as it is typed; Execute runs it."""
        self.ask("type G0 X1")
        shown: dict[str, Any] = self.tick()
        self.assertEqual(shown["mdi_color"], lcnc_hmi.GOOD)
        self.assertEqual(shown["buttons"]["Execute"], "normal")
        self.assertEqual(self.ask("press Execute"), "ok")
        self.assertEqual(self.machine.log[-1], "mdi G0 X1")
        self.ask("type ???")
        shown = self.tick()
        self.assertEqual(shown["mdi_color"], lcnc_hmi.BAD)
        self.assertEqual(shown["buttons"]["Execute"], "disabled")

    # Method `TestQtHMI.test_set_axis()`:
    def test_set_axis(self) -> None:
        """Set X, Y and Z, one by one, set the origin."""
        self.ask(f"open {self.file}")
        self.tick()
        axis: str
        for axis in lcnc_hmi.AXES:
            self.ask(f"origin {axis} 1.5")
            self.ask("answer yes")
            self.assertEqual(self.ask(f"press Set {axis}"), "ok")
        shown: dict[str, Any] = self.tick()
        self.assertTrue(shown["origin_set"])
        self.assertEqual(shown["axes_set"], ["X", "Y", "Z"])
        self.assertEqual(shown["axis_entries"]["Z"], "1.5")

    # Method `TestQtHMI.test_tabs()`:
    def test_tabs(self) -> None:
        """Each tab can be shown; Tools fills its table when shown."""
        name: str
        for name in lcnc_hmi.TABS:
            self.assertEqual(self.ask(f"tab {name}"), "ok")
            self.assertEqual(self.tick()["tab"], name)
        self.ask("tab Tools")
        self.assertTrue(self.hmi.tools_table.toPlainText())
        self.assertTrue(self.ask("tab Nowhere").startswith("error: no tab"))

    # Method `TestQtHMI.test_toggles()`:
    def test_toggles(self) -> None:
        """A View toggle is pressed like a button."""
        shown: dict[str, Any] = self.tick()
        self.assertFalse(shown["toggles"]["Keep-outs"])
        self.assertEqual(self.ask("press Keep-outs"), "ok")
        shown = self.tick()
        self.assertTrue(shown["toggles"]["Keep-outs"])
        self.assertEqual(shown["message"], "No SolidCraft to show them in.")

    # Method `TestQtHMI.test_labels_unique()`:
    def test_labels_unique(self) -> None:
        """Every button's label is its own, so `press` finds just it."""
        labels: Counter[str] = Counter(
            button.text() for button in self.hmi.buttons()
        )
        self.assertEqual([label for label, n in labels.items() if n > 1], [])

    # Method `TestQtHMI.test_open_answer()`:
    def test_open_answer(self) -> None:
        """Open takes its file from the answer waiting."""
        self.ask(f"answer {self.file}")
        self.assertEqual(self.ask("press Open"), "ok")
        self.assertEqual(self.machine.log[0], f"open {self.file}")

    # Method `TestQtHMI.test_qt_messages()`:
    def test_qt_messages(self) -> None:
        """Headless, only the offscreen platform's noise is dropped."""
        with mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            lcnc_hmi_qt.qt_message(
                QtMsgType.QtWarningMsg,
                QMessageLogContext(),
                lcnc_hmi_qt.OFFSCREEN_NOISE,
            )
            lcnc_hmi_qt.qt_message(
                QtMsgType.QtWarningMsg, QMessageLogContext(), "Something"
            )
        self.assertEqual(stderr.getvalue(), "Something\n")

    # Method `TestQtHMI.test_quit()`:
    def test_quit(self) -> None:
        """`quit` closes the window."""
        self.hmi.show()
        self.assertTrue(self.hmi.isVisible())
        self.assertEqual(self.ask("quit"), "ok")
        self.assertFalse(self.hmi.isVisible())


if __name__ == "__main__":
    unittest.main()
