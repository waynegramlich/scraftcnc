"""Tests for `tool_models`, `Tool_Models.md` and one-tool models."""

import json
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import sctoolmodel
import shops
import tool_models
from scraftpybind import SCHeadlessTransport, SCPyBind


class TestFiles(unittest.TestCase):
    """The written files, and what they say."""

    def test_document_is_current(self) -> None:
        """`Tool_Models.md` is what `tool_models.py` writes now."""
        self.assertEqual(
            tool_models.DOCUMENT.read_text(encoding="utf-8"),
            tool_models.document(),
            "Tool_Models.md is out of date: ./tool_models.py",
        )

    def test_sketches_are_current(self) -> None:
        """Each sketch is current, and good XML."""
        for page in tool_models.PAGES:
            path = tool_models.HERE / tool_models.SKETCHES
            text = (path / f"{page.kind}.svg").read_text(encoding="utf-8")
            self.assertEqual(text, tool_models.sketch(page))
            ET.fromstring(text)

    def test_vise_sketches_are_current(self) -> None:
        """Each view of the vise and jaw plate is current, and good XML."""
        path = tool_models.HERE / tool_models.SKETCHES
        for prefix, views in (
            ("machine_vise", tool_models.vise_views()),
            ("jaw_plate", tool_models.jaw_plate_views()),
            ("parallel", tool_models.parallel_views()),
            ("grid_plate", tool_models.grid_plate_views()),
        ):
            numbers = tool_models.vise_numbers(views)
            for view in views:
                name = f"{prefix}_{view.name}.svg"
                text = (path / name).read_text(encoding="utf-8")
                self.assertEqual(text, tool_models.view_sketch(view, numbers))
                ET.fromstring(text)

    def test_vise_sizes_all_listed(self) -> None:
        """Every size drawn is a size of the vise, drawn once."""
        views = tool_models.vise_views()
        keys = [mark.key for view in views for mark in view.marks]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(set(keys), set(tool_models.vise_sizes()))

    def test_no_wide_lines(self) -> None:
        """No line of the document is wider than `MARKDOWN_WIDTH`."""
        for line in tool_models.document().splitlines():
            self.assertLessEqual(len(line), shops.MARKDOWN_WIDTH, line)

    def test_every_page_in_contents(self) -> None:
        """The contents list every section."""
        text = tool_models.document()
        for page in tool_models.PAGES:
            anchor = page.title.lower().replace(" ", "-")
            self.assertIn(f"* [{page.title}](#{anchor})\n", text)
            self.assertIn(f"\n## {page.title}\n", text)

    def test_interface_has_types_and_exceptions(self) -> None:
        """The main function shows its type hints and exceptions."""
        text = tool_models.document()
        self.assertIn("    solidcraft: SCPyBind,\n", text)
        self.assertIn(") -> SCModeledTool\n", text)
        self.assertIn("* `SCShopError`:", text)
        self.assertIn("SCModeledTool.items() -> list[str]", text)

    def test_letters_mean_one_size(self) -> None:
        """A letter means one key, in every kind."""
        seen: dict[str, str] = {}
        for kind in shops.KINDS.values():
            for schema in kind.fields:
                if schema.letter:
                    self.assertEqual(
                        seen.setdefault(schema.letter, schema.key),
                        schema.key,
                    )

    def test_every_letter_is_drawn(self) -> None:
        """Each sketch draws exactly the letters in its table."""
        for page in tool_models.PAGES:
            _, tool = shops.check_tool(page.sample)
            drawn = {d.key for d in page.dimensions(tool)}
            self.assertEqual(
                drawn,
                {
                    s.key
                    for s in shops.KINDS[page.kind].fields
                    if s.letter and s.key not in page.unused_keys
                },
            )


class TestExamples(unittest.TestCase):
    """Every example in the document works."""

    def test_samples_are_good_json(self) -> None:
        """Each sample survives JSON and passes the check."""
        for page in tool_models.PAGES:
            shops.check_tool(json.loads(json.dumps(page.sample)))

    def test_python_compiles(self) -> None:
        """Each Python example is good Python."""
        for page in tool_models.PAGES:
            compile(
                tool_models._python(page),  # pylint: disable=W0212
                page.kind,
                "exec",
            )

    def test_tools_file_reads(self) -> None:
        """Each tools file example passes the reader."""
        header = (
            'name = "Tools"\nkind = "tools"\n'
            'language = "English"\nversion = "0.0.1"\n\n'
        )
        for page in tool_models.PAGES:
            entry = tool_models._toml(page)  # pylint: disable=W0212
            with tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / "tools.toml"
                file.write_text(header + entry, encoding="utf-8")
                self.assertTrue(shops.read(file)[f"{page.kind}s"])


class TestCheckTool(unittest.TestCase):
    """`shops.check_tool()`."""

    def test_material_is_required(self) -> None:
        """A description with no material is refused."""
        sample = dict(tool_models.PAGES[0].sample)
        del sample["material"]
        with self.assertRaisesRegex(shops.SCShopError, "`material`"):
            shops.check_tool(sample)

    def test_good(self) -> None:
        """A good description gives its list and the tool."""
        key, tool = shops.check_tool(tool_models.PAGES[0].sample)
        self.assertEqual(key, "end_mills")
        self.assertEqual(tool["diameter"], "1/2 in")

    def test_unknown_kind(self) -> None:
        """A kind that is not a tool is refused."""
        with self.assertRaisesRegex(shops.SCShopError, "kind: 'lathe'"):
            shops.check_tool({"kind": "lathe"})

    def test_every_problem(self) -> None:
        """A missing key and a wrong unit are both reported."""
        with self.assertRaises(shops.SCShopError) as caught:
            shops.check_tool(
                {
                    "kind": "end_mill",
                    "material": "carbide",
                    "diameter": "1/2",
                    "overall_length": "3 in",
                    "flutes": 2,
                    "end": "square",
                }
            )
        self.assertEqual(len(caught.exception.problems), 2)


@unittest.skipUnless(
    shutil.which("solidcraft-cli"), "`solidcraft-cli` is not on the `PATH`"
)
class TestModelDescription(unittest.TestCase):
    """`sctoolmodel.model_description()`, in a real session."""

    def test_models_each_sample(self) -> None:
        """Each sample becomes a body, named for its kind."""
        for page in tool_models.PAGES:
            with SCHeadlessTransport() as transport:
                modeled = sctoolmodel.model_description(
                    SCPyBind(transport), page.sample
                )
            self.assertEqual(modeled.body, page.kind.replace("_", " "))
