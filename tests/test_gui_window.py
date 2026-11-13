"""Tests of `scraftcam.gui.window` (offscreen) and `scraftcam.run`."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from scraftcam import run
from scraftcam.gui.app import App
from scraftcam.gui.views import TreeWatcher
from scraftcam.gui.window import PROBLEM_COLOR, NewShopDialog, Window
from tests import qt_app


# Function `settle()`:
def settle(window: Window, expected: list[object]) -> bool:
    """Run Qt's events until the first tree root shows `expected`.

    Arguments:
    * `window` (`Window`): The window.
    * `expected` (`list[object]`): The root's labels, nested.

    Returns:
    * (`bool`): True when it did, within about 3 seconds.
    """
    _try: int
    for _try in range(300):
        qt_app.process_events()
        if window.tree.labels()[:1] == [expected]:
            return True
        time.sleep(0.01)
    return False


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
        self.assertFalse(top.tree.isHidden())
        top.buttons["Tree"].click()
        self.assertTrue(top.tree.isHidden())
        top.buttons["Tree"].click()
        self.assertFalse(top.tree.isHidden())
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
            self.assertIn('machine_kinds = ["cnc_mill", "3d_printer"]', text)
            self.assertIn('units = "mm"', text)

            # Again, over the shop just made: refused, said in red.
            again: NewShopDialog = NewShopDialog(top, model)
            again.directory.setText(str(Path(temporary) / "shop"))
            again.name.setText("Other")
            again.make_button.click()
            self.assertTrue(model.latest().problem)
            self.assertIn("already exists", model.latest().text)

    def test_select(self) -> None:
        """A clicked item shows in the current panel; red for errors."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            (top / "shop").mkdir()
            shop: Path = top / "shop" / "shop.toml"
            shop.write_text('name = "Home"\n')
            (top / "shop" / "bad.toml").write_text("x = \n")
            design: Path = top / "plate.py"
            design.write_text(
                '"""A plate."""\n\ndef main() -> int:\n    return 0\n'
            )
            window: Window = Window(App(shop, design))
            self.assertEqual(
                window.tree.labels(),
                [
                    ["Home (shop)", ["bad.toml (error)"]],
                    ["plate (design)"],
                ],
            )

            # The design, in the first panel.
            item = window.tree.item_at_path(design)
            assert item is not None
            window.select_item(item)
            self.assertEqual(window.panels[0].text.toPlainText(), "A plate.")

            # A new panel is current; the bad file shows there, in red.
            window.buttons["+ Panel"].click()
            self.assertEqual(window.current, 1)
            item = window.tree.item_at_path(top / "shop" / "bad.toml")
            assert item is not None
            window.select_item(item)
            self.assertIn("syntax error", window.panels[1].text.toPlainText())
            self.assertIn("#c00000", window.panels[1].title.styleSheet())
            self.assertEqual(window.panels[0].text.toPlainText(), "A plate.")

            # Clicking the first panel makes it current again.
            window.panels[0].clicked.emit()
            self.assertEqual(window.current, 0)

    def test_edit(self) -> None:
        """[Edit] for Python; `VISUAL` run; else the default, hinted once."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            design: Path = top / "plate.py"
            design.write_text("def main() -> int:\n    return 0\n")
            (top / "notes").mkdir()
            (top / "notes" / "a.py").write_text("")
            model: App = App(None, design)
            window: Window = Window(model)
            self.assertTrue(window.edit_row.isHidden())

            # A directory: no [Edit].
            item = window.tree.item_at_path(top / "notes")
            assert item is not None
            window.select_item(item)
            self.assertTrue(window.edit_row.isHidden())

            # The design: [Edit] runs `VISUAL`.
            item = window.tree.item_at_path(design)
            assert item is not None
            window.select_item(item)
            self.assertFalse(window.edit_row.isHidden())
            self.assertEqual(window.edit_label.text(), "plate (design):")
            with (
                mock.patch.dict(os.environ, {"VISUAL": "kate"}),
                mock.patch("subprocess.Popen") as popen,
            ):
                window.buttons["Edit"].click()
            self.assertEqual(popen.call_args.args[0], ["kate", str(design)])

            # Neither set: the desktop's default, the hint only once.
            with (
                mock.patch.dict(os.environ, {"VISUAL": "", "EDITOR": ""}),
                mock.patch(
                    "PySide6.QtGui.QDesktopServices.openUrl",
                    return_value=True,
                ),
            ):
                window.buttons["Edit"].click()
                self.assertIn("environment variable", model.latest().text)
                model.say("later")
                window.buttons["Edit"].click()
                self.assertEqual(model.latest().text, "later")

    def test_watcher(self) -> None:
        """A file added, broken or removed outside shows in the tree."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            shop: Path = top / "shop.toml"
            shop.write_text('name = "Home"\n')
            model: App = App(shop, None)
            window: Window = Window(model)
            watcher: TreeWatcher = TreeWatcher(model)
            self.addCleanup(model.forget, watcher.follow)

            # Added, then broken, then removed.
            (top / "mill.toml").write_text('name = "Mill"\n')
            self.assertTrue(settle(window, ["Home (shop)", ["Mill (file)"]]))
            (top / "mill.toml").write_text("name = \n")
            self.assertTrue(
                settle(window, ["Home (shop)", ["mill.toml (error)"]])
            )
            (top / "mill.toml").unlink()
            self.assertTrue(settle(window, ["Home (shop)"]))


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
