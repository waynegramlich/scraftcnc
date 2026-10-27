"""Tests for `shops`: the line finder, the reader and `Shops.md`."""

import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

import shops

# The example shop.
EXAMPLES: Path = Path(__file__).parent / "examples" / "shop"


def lines_of(text: str) -> dict[shops.KeyPath, int]:
    """Return the line of every key path in some TOML."""
    tomllib.loads(text)
    return shops._Scanner(text).document()  # pylint: disable=protected-access


class TestScanner(unittest.TestCase):
    """The line of every key, list item and table."""

    def test_pairs_and_tables(self) -> None:
        """Plain keys, dotted keys, quoted keys and table headers."""
        lines = lines_of(
            "a = 1\n"
            'b.c = "x"  # A comment.\n'
            '"d e".f = 2\n'
            "\n"
            "[g]\n"
            "h = true\n"
            "[g.i]\n"
            "'j' = 1979-05-27 07:32:00\n"
        )
        self.assertEqual(lines[("a",)], 1)
        self.assertEqual(lines[("b",)], 2)
        self.assertEqual(lines[("b", "c")], 2)
        self.assertEqual(lines[("d e", "f")], 3)
        self.assertEqual(lines[("g",)], 5)
        self.assertEqual(lines[("g", "h")], 6)
        self.assertEqual(lines[("g", "i")], 7)
        self.assertEqual(lines[("g", "i", "j")], 8)

    def test_arrays_of_tables(self) -> None:
        """`[[NAME]]` counts, and later headers refer to the last."""
        lines = lines_of(
            "[[a]]\nx = 1\n[[a]]\nx = 2\n[a.b]\ny = 3\n[[a.c]]\nz = 4\n"
        )
        self.assertEqual(lines[("a", 0, "x")], 2)
        self.assertEqual(lines[("a", 1)], 3)
        self.assertEqual(lines[("a", 1, "x")], 4)
        self.assertEqual(lines[("a", 1, "b", "y")], 6)
        self.assertEqual(lines[("a", 1, "c", 0, "z")], 8)

    def test_inline_tables_and_lists(self) -> None:
        """Values inside `{}` and `[]`, over several lines."""
        lines = lines_of(
            'a = { b = 1, c = { d = "}" } }\n'
            "e = [\n"
            '  "]",  # Not the end.\n'
            "  { f = 2 },\n"
            "  [3, 4],\n"
            "]\n"
            "g = 5\n"
        )
        self.assertEqual(lines[("a", "c", "d")], 1)
        self.assertEqual(lines[("e", 0)], 3)
        self.assertEqual(lines[("e", 1, "f")], 4)
        self.assertEqual(lines[("e", 2, 1)], 5)
        self.assertEqual(lines[("g",)], 7)

    def test_strings(self) -> None:
        """Strings whose contents look like structure."""
        lines = lines_of(
            'a = """\n'
            "[b]\n"
            'c = 1 \\""""\n'
            "d = '''\n"
            "e = [ '''\n"
            'f = "\\" # g"\n'
        )
        self.assertEqual(lines[("d",)], 4)
        self.assertEqual(lines[("f",)], 6)
        self.assertNotIn(("b",), lines)
        self.assertNotIn(("c",), lines)

    def test_locate(self) -> None:
        """A missing key is found at the nearest table above it."""
        lines = lines_of("a = 1\n[b]\nc = 2\n")
        self.assertEqual(shops.locate(lines, ("b", "missing")), 2)
        self.assertEqual(shops.locate(lines, ("missing",)), 1)


class TestReader(unittest.TestCase):
    """Reading the example shop, and copies of it with problems."""

    def setUp(self) -> None:
        """Copy the example shop to a scratch directory."""
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch)
        self.directory = Path(scratch) / "shop"
        shutil.copytree(EXAMPLES, self.directory)

    def change(self, name: str, old: str, new: str) -> None:
        """Change some text in one of the copied files."""
        file = self.directory / name
        text = file.read_text(encoding="utf-8")
        self.assertIn(old, text)
        file.write_text(text.replace(old, new, 1), encoding="utf-8")

    def problems(self, name: str = "home_shop.toml") -> list[str]:
        """Return the problems found reading a copied file."""
        with self.assertRaises(shops.SCShopError) as caught:
            shops.read(self.directory / name)
        prefix = self.directory.as_posix() + "/"
        return [p.replace(prefix, "") for p in caught.exception.problems]

    def test_example(self) -> None:
        """The example reads, with its files spliced in."""
        shop = shops.read(EXAMPLES / "home_shop.toml")
        machines = shop["machines"]
        assert isinstance(machines, list)
        mill = machines[0]
        self.assertEqual(mill["name"], "Shop mill")
        self.assertEqual(mill["controller"]["name"], "LinuxCNC")
        self.assertEqual(len(mill["axes"]), 3)

    def test_file_read_once(self) -> None:
        """A file named twice is read once, and spliced in twice."""
        self.change(
            "home_shop.toml",
            '["@shop_mill.toml"]',
            '["@shop_mill.toml", "@shop_mill.toml"]',
        )
        machines = shops.read(self.directory / "home_shop.toml")["machines"]
        assert isinstance(machines, list)
        self.assertIs(machines[0], machines[1])

    def test_syntax_error(self) -> None:
        """A TOML syntax error gives its line and column."""
        self.change("shop_mill.toml", 'machine = "mill"', "machine = mill")
        self.assertEqual(
            self.problems(), ["shop_mill.toml:6:11: Invalid value"]
        )

    def test_value_problems(self) -> None:
        """Every problem is found, each at its line."""
        self.change("shop_mill.toml", '"5000 rpm"', "5000")
        self.change("shop_mill.toml", 'travel = "9 in"', 'travel = "9 ipm"')
        self.change("shop_mill.toml", "brake = true", "brakes = true")
        self.change("shop_mill.toml", "t_slots = 3", 't_slots = "3"')
        self.change("shop_mill.toml", '"mill"', '"lathe"')
        self.change("shop_mill.toml", "4 = ", "100 = ")
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                ["shop_mill.toml:6", "machine"],
                ["shop_mill.toml:8", "tool_table"],
                ["shop_mill.toml:13", "table.t_slots"],
                ["shop_mill.toml:21", "spindle.max_rpm"],
                ["shop_mill.toml:37", "axes[1].travel"],
                ["shop_mill.toml:49", "axes[2].brakes"],
            ],
        )
        self.assertIn('"5000 rpm"', problems[3])
        self.assertIn("'ipm' is the wrong unit", problems[4])

    def test_missing_and_kind(self) -> None:
        """Missing keys, and a `kind` that does not fit."""
        self.change("linuxcnc.toml", 'post_processor = "linuxcnc"\n', "")
        self.change("shop_mill.toml", 'version = "0.0.1"\n', "")
        self.change(
            "home_shop.toml",
            'address = "',
            'kind = "machine"\naddress = "',
        )
        self.assertEqual(
            self.problems(),
            [
                "linuxcnc.toml:1: `post_processor` is missing",
                "shop_mill.toml:1: `version` is missing",
                "home_shop.toml:11: location.kind: a `location` belongs here",
            ],
        )

    def test_versions(self) -> None:
        """A newer minor version, or another major one, is refused."""
        self.change("linuxcnc.toml", '"0.0.1"', '"0.1.0"')
        self.change("shop_mill.toml", '"0.0.1"', '"1.0.0"')
        problems = self.problems()
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("shop_mill.toml:5: version"))
        self.assertTrue(problems[1].startswith("linuxcnc.toml:5: version"))

    def test_references(self) -> None:
        """Bad names, missing files, loops and files of the wrong kind."""
        self.change(
            "home_shop.toml",
            '["@shop_mill.toml"]',
            '["@shop_mill.toml", "@../x.toml", "@nope.toml", '
            '"@linuxcnc.toml", "not a table"]',
        )
        self.change("shop_mill.toml", "@linuxcnc", "@home_shop")
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                ["shop_mill.toml:7", "controller"],
                ["home_shop.toml:6", "machines[1]"],
                ["home_shop.toml:6", "machines[2]"],
                ["home_shop.toml:6", "machines[3]"],
                ["home_shop.toml:6", "machines[4]"],
            ],
        )
        self.assertIn(
            "home_shop.toml -> shop_mill.toml -> home_shop.toml", problems[0]
        )
        self.assertIn("in this directory", problems[1])
        self.assertIn('no file "nope.toml"', problems[2])
        self.assertIn("is a `controller` file", problems[3])
        self.assertIn("is not a `machine` table", problems[4])

    def test_unknown_kind(self) -> None:
        """A top file whose `kind` is not known."""
        self.change("home_shop.toml", 'kind = "shop"', 'kind = "shoppe"')
        self.assertEqual(
            [p.split(": ")[:2] for p in self.problems()],
            [["home_shop.toml:3", "kind"]],
        )


class TestMarkdown(unittest.TestCase):
    """`Shops.md`, written from the schema."""

    def test_every_kind(self) -> None:
        """Every kind has a section, and its example is good TOML."""
        text = shops.markdown()
        self.assertIn(f"format version `{shops.FORMAT_VERSION}`", text)
        for kind in shops.KINDS.values():
            self.assertIn(f"## `{kind.kind}`\n", text)
            tomllib.loads(kind.example)

    def test_shops_md_is_current(self) -> None:
        """`Shops.md` is what `shops.py markdown` writes now."""
        written = (Path(__file__).parent / "Shops.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            written,
            shops.markdown(),
            "Shops.md is out of date: ./shops.py markdown > Shops.md",
        )

    def test_no_wide_lines(self) -> None:
        """No line of `Shops.md` is wider than `MARKDOWN_WIDTH`."""
        for line in shops.markdown().splitlines():
            self.assertLessEqual(len(line), shops.MARKDOWN_WIDTH, line)

    def test_wrap(self) -> None:
        """Wide cells wrap, keeping code spans whole."""
        table = shops._markdown_table(  # pylint: disable=protected-access
            [
                ["Key", "Meaning"],
                ["`a`", "one two `three four`, five six"],
                ["`b`", "seven"],
            ],
            width=26,
        )
        self.assertEqual(
            table.splitlines(),
            [
                "| Key | Meaning          |",
                "| --- | ---------------- |",
                "| `a` | one two          |",
                "|     | `three four`,    |",
                "|     | five six         |",
                "| `b` | seven            |",
            ],
        )

    def test_tables_line_up(self) -> None:
        """In every table, each row's `|`s are where the heading's are."""
        tables: list[list[str]] = []
        previous = ""
        for line in shops.markdown().splitlines():
            if line.startswith("|"):
                if not previous.startswith("|"):
                    tables.append([])
                tables[-1].append(line)
            previous = line
        self.assertEqual(len(tables), len(shops.KINDS) + 2)
        for table in tables:
            bars = [i for i, c in enumerate(table[0]) if c == "|"]
            for row in table:
                self.assertEqual(
                    [i for i, c in enumerate(row) if c == "|"], bars, row
                )

    def test_examples_check(self) -> None:
        """Examples with no `@` names check against their own kind."""
        for kind in shops.KINDS.values():
            if "@" in kind.example:
                continue
            with self.subTest(kind=kind.kind):
                reader = shops._Reader(EXAMPLES)  # pylint: disable=W0212
                source = shops._Source(kind.kind, {})  # pylint: disable=W0212
                reader.table(tomllib.loads(kind.example), kind, (), source)
                self.assertEqual(reader.problems, [])


if __name__ == "__main__":
    unittest.main()
