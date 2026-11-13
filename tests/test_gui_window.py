"""Tests of `scraftcam.gui.window` (offscreen) and `scraftcam.run`."""

import os
import tempfile
import unittest
from pathlib import Path

from scraftcam import run
from scraftcam.gui.app import App
from scraftcam.gui.window import PROBLEM_COLOR, NewShopDialog, Window
from tests import qt_app  # noqa: F401  # pylint: disable=unused-import


class WindowTest(unittest.TestCase):
    """Tests of `Window`."""

    def test_top_line(self) -> None:
        """The names, the message, and [Stop All] only with two running."""
        model: App = App(None, Path("plate.py"))
        first: Window = Window(model)
        second: Window = Window(model)
        self.assertEqual(first.windowTitle(), "scraftcam: (none) (plate)")
        self.assertEqual(first.design_label.text(), "Design: plate")
        self.assertIn(PROBLEM_COLOR, first.message_label.styleSheet())

        # Both windows follow the model.
        model.say("hello")
        self.assertEqual(second.message_label.text(), "hello")
        self.assertEqual(first.message_label.styleSheet(), "")
        model.start_machine("shop mill")
        model.start_machine("router")
        self.assertFalse(second.buttons["Stop All"].isHidden())
        second.buttons["Stop All"].click()
        self.assertTrue(first.buttons["Stop All"].isHidden())

    def test_tree_and_panels(self) -> None:
        """[Tree] toggles the tree; [+ Panel] adds a panel."""
        top: Window = Window(App(None, None))
        self.assertTrue(top.tree.isHidden())
        top.buttons["Tree"].click()
        self.assertFalse(top.tree.isHidden())
        top.buttons["Tree"].click()
        self.assertTrue(top.tree.isHidden())
        top.buttons["+ Panel"].click()
        self.assertEqual(len(top.panels), 2)
        self.assertEqual(top.splitter.count(), 3)

    def test_close_refused(self) -> None:
        """A window controlling a running machine refuses to close."""
        model: App = App(None, None)
        top: Window = Window(model, {"shop mill"})
        top.show()
        model.start_machine("shop mill")
        top.buttons["x"].click()
        self.assertTrue(top.isVisible())
        self.assertEqual(model.latest().text, "Stop the shop mill first")
        model.stop_machine("shop mill")
        top.buttons["x"].click()
        self.assertFalse(top.isVisible())
        self.assertNotIn(top.redraw, model.listeners)

    def test_new_shop(self) -> None:
        """[New Shop] while there is none; the dialog makes one."""
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / ".git").mkdir()
            model: App = App(None, None)
            top: Window = Window(model)
            self.assertFalse(top.buttons["New Shop"].isHidden())
            dialog: NewShopDialog = NewShopDialog(top, model)
            self.assertTrue(dialog.kinds["cnc_mill"].isChecked())
            self.assertFalse(dialog.make_button.isEnabled())
            dialog.directory.setText(str(Path(temporary) / "shop"))
            dialog.name.setText("Garage")
            self.assertTrue(dialog.make_button.isEnabled())
            dialog.units.setCurrentText("Metric (mm)")
            dialog.kinds["3d_printer"].setChecked(True)
            dialog.make_button.click()
            self.assertEqual(top.shop_label.text(), "Shop: Garage")
            self.assertTrue(top.buttons["New Shop"].isHidden())
            self.assertTrue(top.new_shop_row.isHidden())
            text: str = (Path(temporary) / "shop" / "shop.toml").read_text()
            self.assertIn('machines = ["cnc_mill", "3d_printer"]', text)
            self.assertIn('units = "mm"', text)

            # Again, over the shop just made: refused, said in red.
            again: NewShopDialog = NewShopDialog(top, model)
            again.directory.setText(str(Path(temporary) / "shop"))
            again.name.setText("Other")
            again.make_button.click()
            self.assertTrue(model.latest().problem)
            self.assertIn("already exists", model.latest().text)


class RunTest(unittest.TestCase):
    """Tests of `run.shop_file()`."""

    def test_shop_file(self) -> None:
        """`--shop` as a file or a directory; else found from here."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            shop: Path = top / "shop.toml"
            self.assertIsNone(run.shop_file(str(top)))
            shop.write_text('name = "Home"\n')
            self.assertEqual(run.shop_file(str(top)), shop.resolve())
            self.assertEqual(run.shop_file(str(shop)), shop.resolve())
            (top / "sub").mkdir()
            here: str = os.getcwd()
            os.chdir(top / "sub")
            try:
                self.assertEqual(run.shop_file(""), shop.resolve())
            finally:
                os.chdir(here)


if __name__ == "__main__":
    unittest.main()
