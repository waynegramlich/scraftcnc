"""Tests for `scmachine.py`: run `python3 -m unittest -v`."""

import tempfile
import unittest
from pathlib import Path

from scmachine import SCMachine, SCTool, load_machine
from test_solidcraftcnc import machine

# The project's own machine file.
MACHINE_FILE: Path = Path(__file__).resolve().parent / "machine.toml"


# Class `TestMachine`:
class TestMachine(unittest.TestCase):
    """Machine preferences and tool tables."""

    # Method `TestMachine.load()`:
    def load(self, text: str) -> SCMachine:
        """Load a machine file written from text.

        Arguments:
        * `text` (`str`): The file's contents.

        Returns:
        * (`SCMachine`): The machine.
        """
        with tempfile.TemporaryDirectory() as folder:
            path: Path = Path(folder) / "machine.toml"
            path.write_text(text, encoding="utf-8")
            return load_machine(path)

    # Method `TestMachine.test_project_file()`:
    def test_project_file(self) -> None:
        """The project's machine file loads, with its tools."""
        mill: SCMachine = load_machine(MACHINE_FILE)
        self.assertEqual(mill.change_words(4), ["T04"])
        self.assertEqual(mill.tool(1).kind, "end mill")
        self.assertEqual(mill.drill_for(mill.tool(1)).number, 4)

    # Method `TestMachine.test_bad_files()`:
    def test_bad_files(self) -> None:
        """Bad files say what is wrong, and where."""
        good: str = MACHINE_FILE.read_text(encoding="utf-8")
        cases: list[tuple[str, str]] = [
            ("not = [valid", "machine.toml"),
            ("[[tools]]\nnumber = 1\n", "needs a"),
            (good.replace("z_safe = 1.0", 'z_safe = "high"'), "z_safe"),
            (
                good.replace('drill_cycle = "G83"', 'drill_cycle = "G99"'),
                "drill",
            ),
            (good.replace("number = 2", "number = 1"), "not all different"),
            (good.replace("rpm = 1200", "rpm = 0", 1), "rpm"),
            (good.replace('kind = "drill"', 'kind = "tap"', 1), "kind"),
            (good.replace('name = "Shop mill"\n', ""), "name is missing"),
        ]
        text: str
        expected: str
        for text, expected in cases:
            with self.assertRaisesRegex(ValueError, expected):
                self.load(text)

    # Method `TestMachine.test_preferences()`:
    def test_preferences(self) -> None:
        """Preferences that make no sense are refused."""
        cases: tuple[dict[str, object], ...] = (
            {"clearance": -0.01},
            {"tool_change_z": 0.5},
            {"rapid_speed": 0.0},
            {"stepover": 0.0},
            {"stepover": 1.1},
            {"ramp_angle": 0.0},
            {"tool_change": "T{tool:02d}"},
            {"tool_change": "{number}"},
        )
        changes: dict[str, object]
        for changes in cases:
            with self.assertRaises(ValueError, msg=str(changes)):
                machine(**changes)
        with self.assertRaises(ValueError):
            SCTool(1, "Bad", "end mill", 0.0, 1200, 1.0, 1.0)
        with self.assertRaises(ValueError):
            SCTool(0, "Bad", "end mill", 0.25, 1200, 1.0, 1.0)


if __name__ == "__main__":
    unittest.main()
