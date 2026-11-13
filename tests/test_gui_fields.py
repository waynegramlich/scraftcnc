"""Tests of `scraftcam.gui.fields` and the panel's field rows."""

import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from scraftcam.gui import fields
from scraftcam.gui.tree import FILE, Node
from scraftcam.gui.views import BAD_STYLE, Panel
from tests import qt_app

# An example tool, copied before it is edited.
TOOL: Path = (
    Path(__file__).parent.parent
    / "examples"
    / "shop"
    / "tools"
    / "1_16_in_radius_carbide_corner_rounding_mill.toml"
)


class FieldsTest(unittest.TestCase):
    """Tests of the Qt free part."""

    def setUp(self) -> None:
        """Read the example tool."""
        self.item: dict[str, object] = fields.read_item(TOOL)[0]

    def row(self, key: str, units: str = "in") -> fields.Row:
        """Return one of the tool's rows.

        Arguments:
        * `key` (`str`): The field's key.
        * `units` (`str`): The shop's units.

        Returns:
        * (`fields.Row`): Its row.
        """
        return next(
            row
            for row in fields.rows(self.item, units)
            if row.schema.key == key
        )

    def test_rows(self) -> None:
        """Rows come in `KINDS` order; `kind` is not edited."""
        keys: list[str] = [
            row.schema.key for row in fields.rows(self.item, "in")
        ]
        self.assertEqual(
            keys[:5], ["name", "kind", "language", "version", "notes"]
        )
        self.assertFalse(self.row("kind").editable)
        self.assertTrue(self.row("radius").editable)
        self.assertNotIn("holder", keys)
        self.assertIn("holder", fields.rest_text(self.item))

    def test_check(self) -> None:
        """Bad values have problems; good ones show the shop's units."""
        row: fields.Row = self.row("radius", "mm")
        self.assertEqual(row.shown, "1.5875 mm")
        fields.check(row, "1/16 furlong", "mm")
        self.assertTrue(row.problem)
        self.assertEqual(row.shown, "")
        self.assertIsNone(fields.with_value(self.item, row))
        fields.check(row, "2 mm", "mm")
        self.assertEqual((row.problem, row.shown), ("", ""))
        changed: dict[str, object] | None = fields.with_value(self.item, row)
        self.assertIsNotNone(changed)
        assert changed is not None
        self.assertEqual(changed["radius"], "2 mm")

    def test_numbers_and_empty(self) -> None:
        """Whole numbers are typed bare; an empty optional field goes."""
        row: fields.Row = self.row("flutes")
        fields.check(row, "x", "in")
        self.assertTrue(row.problem)
        fields.check(row, "4", "in")
        changed: dict[str, object] | None = fields.with_value(self.item, row)
        assert changed is not None
        self.assertEqual(changed["flutes"], 4)
        notes: fields.Row = self.row("notes")
        fields.check(notes, "", "in")
        changed = fields.with_value(self.item, notes)
        assert changed is not None
        self.assertNotIn("notes", changed)
        name: fields.Row = self.row("name")
        fields.check(name, " ", "in")
        self.assertEqual(name.problem, "required")


class PanelFieldsTest(unittest.TestCase):
    """Tests of the panel's rows, offscreen."""

    def test_edit_writes(self) -> None:
        """A good value is written; a bad one is shown and not."""
        qt_app.process_events()
        with tempfile.TemporaryDirectory() as directory:
            path: Path = Path(directory) / TOOL.name
            shutil.copy(TOOL, path)
            panel: Panel = Panel(1)
            panel.show_node(Node(path.name, FILE, path, ""), "mm")
            self.assertEqual(panel.shown["radius"].text(), "1.5875 mm")

            # A bad value: light red, not written.
            before: str = path.read_text(encoding="utf-8")
            panel.typed("radius", "lots")
            panel.write("radius")
            self.assertEqual(panel.entries["radius"].styleSheet(), BAD_STYLE)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

            # A good one: written, and the rows kept when shown again.
            panel.typed("radius", "1/8 in")
            panel.write("radius")
            with path.open("rb") as file:
                self.assertEqual(tomllib.load(file)["radius"], "1/8 in")
            entry: object = panel.entries["radius"]
            panel.show_node(Node(path.name, FILE, path, ""), "mm")
            self.assertIs(panel.entries["radius"], entry)
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
