"""Tests of `scraftcam.gui.tree`."""

import tempfile
import unittest
from pathlib import Path

from scraftcam.gui import tree


# Function `labels()`:
def labels(node: tree.Node) -> list[object]:
    """Return a tree's labels, nested as the tree is.

    Arguments:
    * `node` (`tree.Node`): The root.

    Returns:
    * (`list[object]`): Its label, then a list per child.
    """
    return [node.label(), *[labels(child) for child in node.children]]


class ShopTreeTest(unittest.TestCase):
    """Tests of `shop_tree()`."""

    def test_shop(self) -> None:
        """Directories first; names from `name`; errors kept, with lines."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            (top / "shop.toml").write_text('name = "Home"\n')
            (top / "machines").mkdir()
            (top / "machines" / "mill.toml").write_text('name = "Mill"\n')
            (top / "a.toml").write_text("x = 1\n")
            (top / "Bad.toml").write_text("x = \n")
            (top / "notes.txt").write_text("not shown\n")
            (top / ".hidden").mkdir()
            root: tree.Node = tree.shop_tree(top / "shop.toml")
            self.assertEqual(
                labels(root),
                [
                    "Home (shop)",
                    ["machines (directory)", ["Mill (file)"]],
                    ["a (file)"],
                    ["Bad.toml (error)"],
                ],
            )
            self.assertIn("syntax error", root.children[2].error)
            self.assertIn("line 1", root.children[2].error)


class DesignTreeTest(unittest.TestCase):
    """Tests of `design_tree()` and `docstring()`."""

    def test_design(self) -> None:
        """`main()` makes a design; packages; syntax errors; docstrings."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            design: Path = top / "plate.py"
            design.write_text(
                '"""A plate."""\n\ndef main() -> int:\n    return 0\n'
            )
            (top / "helpers.py").write_text("X = 1\n")
            (top / "broken.py").write_text("def (\n")
            (top / "parts").mkdir()
            (top / "parts" / "__init__.py").write_text('"""Parts."""\n')
            (top / "empty").mkdir()
            (top / "__pycache__").mkdir()
            (top / "__pycache__" / "x.py").write_text("")
            root: tree.Node
            clipped: bool
            root, clipped = tree.design_tree(design)
            self.assertFalse(clipped)
            self.assertEqual(
                labels(root),
                [
                    "plate (design)",
                    ["parts (package)", ["__init__ (python)"]],
                    ["broken (error)"],
                    ["helpers (python)"],
                ],
            )
            self.assertEqual(
                root.children[1].error[:23], "syntax error at line 1:"
            )
            self.assertEqual(tree.docstring(design), "A plate.")
            self.assertEqual(tree.docstring(top / "parts"), "Parts.")
            self.assertEqual(
                tree.docstring(top / "helpers.py"), "(no docstring)"
            )

            # A package as the design: what is in it.
            package: tree.Node = tree.design_tree(top / "parts")[0]
            self.assertEqual(
                labels(package), ["parts (package)", ["__init__ (python)"]]
            )

    def test_limit(self) -> None:
        """At most `limit` items, and it says so (#126)."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary)
            index: int
            for index in range(10):
                (top / f"m{index}.py").write_text("")
            root: tree.Node
            clipped: bool
            root, clipped = tree.design_tree(top / "m0.py", limit=5)
            self.assertTrue(clipped)
            self.assertEqual(len(root.children), 5)
            root, clipped = tree.design_tree(top / "m0.py", limit=9)
            self.assertFalse(clipped)


if __name__ == "__main__":
    unittest.main()
