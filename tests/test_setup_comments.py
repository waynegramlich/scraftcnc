"""Tests for `scraftcnc.setup_comments`."""

import tempfile
import unittest
import warnings
from pathlib import Path

from scraftcnc import __version__, demo, setup_comments
from scraftcnc.assembly import Assembly, AssemblyItem
from scraftcnc.shops import read
from scraftcnc.tooling.cutter_models import EXAMPLE_SHOP
from scraftcnc.tooling.shop_registries import use_shop
from tests.test_assembly import assert_same


# Function `setUpModule()`:
def setUpModule() -> None:
    """Fill the name registries from the example shop."""
    use_shop(read(EXAMPLE_SHOP))


def _assembly() -> Assembly:
    """Return an assembly with a bit of everything in it."""
    return Assembly(
        [
            AssemblyItem(
                kind="tooling",
                name="vise (6 in)",
                call="scraftcnc.tooling.tools:MachineVise.make",
                args={
                    "width": "6 in",
                    "opening": "6 in",
                    "jaws": 2,
                    "hardened": True,
                    "tags": ["a", "b (c)"],
                    "jaw": {"plate": "1/2 in", "deep": {"x": 1.5}},
                    "points": [{"name": "fixed (jaw)", "z": 0.0}],
                    "odd key": '\\ " \t é',
                },
                location=(1.0, -2.5, 3.25),
                orientation=1,
                color="#c0c0c0",
                transparency=0.5,
                note="Tighten the vise (firmly).",
                keep_out=tuple(
                    (
                        float(i),
                        0.0,
                        0.0,
                        float(i) + 100.125,
                        200.5,
                        300.25,
                    )
                    for i in range(4)
                ),
            ),
            AssemblyItem(
                kind="stock",
                name="stock",
                call="scraftcnc.assembly:Stock",
                args={
                    "material": "aluminum_6061",
                    "size": ["4 in", "3 in", "1/2 in"],
                },
            ),
        ]
    )


# Function `_read()`:
def _read(assembly: Assembly | None) -> Assembly:
    """Return an assembly that was read, which must not be `None`."""
    assert assembly is not None
    return assembly


class TestSetupComments(unittest.TestCase):
    """Tests for the writer and the reader."""

    def test_round_trip(self) -> None:
        """Write then read gives the same assembly."""
        assembly: Assembly = _assembly()
        lines: list[str] = setup_comments.write(assembly)
        self.assertEqual(lines[0], f'(SCC: version = "{__version__}")')
        line: str
        for line in lines:
            self.assertTrue(line.startswith("(SCC: ") and line.endswith(")"))
            self.assertNotIn("(", line[1:-1])
            self.assertNotIn(")", line[1:-1])
            self.assertLessEqual(len(line), 79, line)
        assert_same(self, _read(setup_comments.read(lines)), assembly)

    def test_optional_fields_absent(self) -> None:
        """An item with only the needed fields reads back the same."""
        assembly: Assembly = Assembly(
            [AssemblyItem("part", "plate", "scraftcnc.demo:model", {})]
        )
        lines: list[str] = setup_comments.write(assembly)
        self.assertFalse(any("note" in line for line in lines))
        self.assertEqual(setup_comments.read(lines), assembly)

    def test_other_lines_skipped(self) -> None:
        """G-code, other comments and indentation are skipped."""
        lines: list[str] = ["%", "(a comment)", "G21 (mm)"]
        lines += ["  " + line for line in setup_comments.write(_assembly())]
        lines += ["G0 X1 Y2", "(SCC is not this)", "M2", "%"]
        assert_same(self, _read(setup_comments.read(lines)), _assembly())

    def test_no_setup(self) -> None:
        """A program with no setup comments gives `None`."""
        self.assertIsNone(setup_comments.read(["G0 X0", "(hello)", "M2"]))

    def test_read_file(self) -> None:
        """A file is read, and its name is in error messages."""
        with tempfile.TemporaryDirectory() as directory:
            path: Path = Path(directory) / "part.nc"
            text: str = "\n".join(setup_comments.write(_assembly()))
            path.write_text(text + "\nG0 X0\nM2\n", encoding="utf-8")
            assert_same(
                self, _read(setup_comments.read_file(path)), _assembly()
            )
            path.write_text("(SCC: [[item]])\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "part.nc.*no version"):
                setup_comments.read_file(path)

    def test_errors(self) -> None:
        """Errors say what and where."""
        good: list[str] = setup_comments.write(_assembly())
        cases: list[tuple[list[str], str]] = [
            (["G0", "(SCC: [[item]])"], "line 2: setup comments have no"),
            (["G0", '(SCC: version = "0.1.0")', "(SCC: x = )"], "line 3"),
            (["(SCC: a) G0 X1"], "line 1: .*not one whole-line"),
            (['(SCC: version = "1.x")'], "version '1.x' is wrong"),
            (['(SCC: version = "0.0.1")', "(SCC: z = 1)"], "unknown keys"),
            ([good[0], "(SCC: [[item]])", '(SCC: kind = "x")'], "item 1"),
        ]
        lines: list[str]
        message: str
        for lines, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                setup_comments.read(lines)

    def test_newer_version(self) -> None:
        """A newer version warns, and is read as far as it can be."""
        lines: list[str] = setup_comments.write(_assembly())
        lines[0] = '(SCC: version = "999.0")'
        lines.insert(1, "(SCC: future = 1)")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_same(self, _read(setup_comments.read(lines)), _assembly())
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, setup_comments.SetupVersionWarning)

    def test_no_toml_form(self) -> None:
        """A value TOML can not hold is a `TypeError`."""
        assembly: Assembly = Assembly(
            [AssemblyItem("part", "p", "m:f", {"none": None})]
        )
        with self.assertRaises(TypeError):
            setup_comments.write(assembly)


class TestDemoSetup(unittest.TestCase):
    """The demonstration's G-code carries its setup."""

    def test_demo_round_trip(self) -> None:
        """The demo's program reads back into the same assembly."""
        assembly: Assembly = demo.demo_assembly()
        program: str = demo.with_setup(demo.cut_demo()[0].gcode(), assembly)
        lines: list[str] = program.splitlines()
        self.assertEqual(lines[0], "(SolidCraftCNC demo)")
        self.assertTrue(lines[1].startswith("(SCC: version"))
        back: Assembly | None = setup_comments.read(lines)
        assert back is not None
        assert_same(self, back, assembly)
        setup: list[str] = [line for line in lines if "(SCC:" in line]
        self.assertTrue(all(len(line) <= 79 for line in setup))
        self.assertTrue(any(item.keep_out for item in back.items))


if __name__ == "__main__":
    unittest.main()
