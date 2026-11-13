"""Tests of `scraftcam.gui.editor`."""

import sys
import unittest
from pathlib import Path

from scraftcam.gui import editor


# Function `found()`:
def found(name: str) -> str | None:
    """Find only `konsole` (a `shutil.which` stand-in).

    Arguments:
    * `name` (`str`): A program.

    Returns:
    * (`str | None`): Its path, for `konsole` only.
    """
    return "/usr/bin/konsole" if name == "konsole" else None


# Function `nothing()`:
def nothing(_name: str) -> str | None:
    """Find nothing (a `shutil.which` stand-in).

    Arguments:
    * `_name` (`str`): A program (ignored).

    Returns:
    * (`str | None`): None.
    """
    return None


class EditorCommandTest(unittest.TestCase):
    """Tests of `editor_command()`."""

    def test_order(self) -> None:
        """`VISUAL`, then `EDITOR` in a terminal, then the default."""
        path: Path = Path("/x/plate.py")
        self.assertEqual(
            editor.editor_command(
                path, {"VISUAL": "code -w", "EDITOR": "vi"}, found
            ),
            (["code", "-w", "/x/plate.py"], ""),
        )
        self.assertEqual(editor.editor_command(path, {}, found), ([], ""))
        if sys.platform != "win32":
            self.assertEqual(
                editor.editor_command(path, {"EDITOR": "emacs -nw"}, found),
                (["konsole", "-e", "emacs", "-nw", "/x/plate.py"], ""),
            )
            command: list[str]
            problem: str
            command, problem = editor.editor_command(
                path, {"EDITOR": "vi"}, nothing
            )
            self.assertEqual(command, [])
            self.assertIn("environment variable VISUAL", problem)


if __name__ == "__main__":
    unittest.main()
