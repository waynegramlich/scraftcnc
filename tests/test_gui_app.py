"""Tests of `scraftcam.gui.app`."""

import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from scraftcam import shops
from scraftcam.gui import app


class FindShopTest(unittest.TestCase):
    """Tests of `find_shop()`, `shop_name()` and `design_name()`."""

    def test_found_here_or_above(self) -> None:
        """`shop.toml` is found in the directory or a parent, or not."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            below: Path = top / "a" / "b"
            below.mkdir(parents=True)
            self.assertIsNone(app.find_shop(below))
            shop: Path = top / "a" / "shop.toml"
            shop.write_text('name = "Home"\n')
            self.assertEqual(app.find_shop(below), shop.resolve())
            self.assertEqual(app.find_shop(top / "a"), shop.resolve())

    def test_names(self) -> None:
        """A shop's `name`, else its directory; a design's file name."""
        with tempfile.TemporaryDirectory() as temporary:
            shop: Path = Path(temporary) / "garage" / "shop.toml"
            shop.parent.mkdir()
            shop.write_text('name = "  Home shop "\n')
            self.assertEqual(app.shop_name(shop), "Home shop")
            shop.write_text("units = 'in'\n")
            self.assertEqual(app.shop_name(shop), "garage")
            self.assertEqual(app.design_name(Path("x/plate.py")), "plate")
            self.assertEqual(app.design_name(shop.parent), "garage")


class VersionControlTest(unittest.TestCase):
    """Tests of `in_repository()` and `version_control_hint()`."""

    def test_hints(self) -> None:
        """No hint in a repository; otherwise what to install or run."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            with mock.patch("shutil.which", return_value=None):
                self.assertIn(
                    "install git or hg", app.version_control_hint(top)
                )
            with mock.patch("shutil.which", return_value="/usr/bin/hg"):
                self.assertIn("`git init`", app.version_control_hint(top))
            (top / ".hg").mkdir()
            (top / "shop").mkdir()
            self.assertTrue(app.in_repository(top / "shop"))
            self.assertEqual(app.version_control_hint(top / "shop"), "")


class AppTest(unittest.TestCase):
    """Tests of `App`."""

    def test_no_shop(self) -> None:
        """With no shop, the names are `(none)`, and it says so."""
        model: app.App = app.App(None, None)
        self.assertEqual(model.title(), "scraftcam: (none) ((none))")
        self.assertTrue(model.latest().problem)
        self.assertIn("No shop.toml", model.latest().text)

    def test_shop_and_design(self) -> None:
        """The title has both names; a bad shop file is a problem."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            (top / ".git").mkdir()
            shop: Path = top / "shop.toml"
            shop.write_text('name = "Home"\n')
            (top / "plate.py").write_text("def main() -> int:\n    return 0\n")
            model: app.App = app.App(shop, top / "plate.py")
            self.assertEqual(model.title(), "scraftcam: Home (plate)")
            self.assertEqual(model.messages, [])

            # Not TOML: reported, never raised.
            shop.write_text("name = \n")
            model = app.App(shop, None)
            self.assertEqual(model.shop_title, app.NONE_NAME)
            self.assertTrue(model.latest().problem)

    def test_listeners_and_messages(self) -> None:
        """Every listener hears every change, until it is forgotten."""
        model: app.App = app.App(None, None)
        heard: list[int] = []

        def redraw() -> None:
            heard.append(len(model.messages))

        model.listen(redraw)
        model.say("one\n  two")
        self.assertEqual(model.latest(), app.Message("one two", False))
        model.forget(redraw)
        model.say("three")
        self.assertEqual(heard, [2])

    def test_machines(self) -> None:
        """[Stop All] with two machines; closing refused while one runs."""
        model: app.App = app.App(None, None)
        model.start_machine("shop mill")
        self.assertFalse(model.stop_all_shown())
        self.assertEqual(
            model.close_refusal({"shop mill"}), "Stop the shop mill first"
        )
        self.assertEqual(model.close_refusal({"router"}), "")
        model.start_machine("router")
        self.assertTrue(model.stop_all_shown())
        model.stop_all()
        self.assertFalse(model.stop_all_shown())
        self.assertEqual(model.close_refusal({"shop mill"}), "")


class NewShopTest(unittest.TestCase):
    """Tests of `new_shop_text()`, `create_shop()` and `App.new_shop()`."""

    def test_text(self) -> None:
        """The answers as TOML, which `tomllib` reads back."""
        text: str = app.new_shop_text(
            ' My  "big" shop ', "mm", ["manual_lathe", "cnc_mill"]
        )
        self.assertEqual(
            tomllib.loads(text),
            {
                "name": 'My "big" shop',
                "kind": "shop",
                "language": "English",
                "version": shops.FORMAT_VERSION,
                "units": "mm",
                "machine_kinds": ["cnc_mill", "manual_lathe"],
            },
        )

        # The shop reader takes it, and knows every kind asked about.
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "shop.toml").write_text(text)
            self.assertEqual(shops.read(Path(temporary))["units"], "mm")
        self.assertEqual(
            [kind for kind, _label, _ready in app.MACHINE_KINDS],
            list(shops.SHOP_MACHINE_KINDS),
        )
        bad: tuple[tuple[str, str, list[str]], ...] = (
            (" ", "in", []),
            ("A", "ft", []),
            ("A", "in", ["loom"]),
        )
        name: str
        units: str
        machines: list[str]
        for name, units, machines in bad:
            with self.assertRaises(ValueError):
                app.new_shop_text(name, units, machines)

    def test_new_shop(self) -> None:
        """A new shop is made and shown; never over an old one."""
        with tempfile.TemporaryDirectory() as temporary:
            directory: Path = Path(temporary) / "shop"
            model: app.App = app.App(None, None)
            heard: list[str] = []

            def redraw() -> None:
                heard.append(model.title())

            model.listen(redraw)
            with mock.patch("shutil.which", return_value="/usr/bin/git"):
                shop: Path = model.new_shop(directory, "Home", "in", [])
            self.assertEqual(shop, (directory / "shop.toml").resolve())
            self.assertEqual(heard[-1], "scraftcam: Home ((none))")
            self.assertTrue(model.latest().text.startswith("Created "))
            self.assertIn("`git init`", model.latest().text)
            with self.assertRaises(ValueError):
                model.new_shop(directory, "Again", "in", [])


if __name__ == "__main__":
    unittest.main()
