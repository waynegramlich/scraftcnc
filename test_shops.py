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


class TestMeasure(unittest.TestCase):
    """Measurements: decimals, fractions and units."""

    def test_numbers(self) -> None:
        """Decimals and fractions, in any unit of the right kind."""
        for text, inches in (
            ("0.5 in", 0.5),
            (".25in", 0.25),
            ("1/2 in", 0.5),
            ("1-1/2 in", 1.5),
            ("-1-1/2 in", -1.5),
            ("10 ft", 120.0),
            ("25.4 mm", 1.0),
            ("1e-3 in", 0.001),
        ):
            with self.subTest(text=text):
                self.assertAlmostEqual(
                    shops.measure(text, shops.UNITS["length"]), inches
                )

    def test_problems(self) -> None:
        """Bare numbers, bad numbers and wrong units are refused."""
        for value, problem in (
            (0.5, "needs a unit"),
            ("1 1/2 in", "is not a number and a unit"),
            ("1-1.5 in", "is not a number and a unit"),
            ("3/0 in", "divides by zero"),
            ("1/2 in/min", "is the wrong unit"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:
                    shops.measure(value, shops.UNITS["length"])
                self.assertIn(problem, str(caught.exception))


class CopiedShop(unittest.TestCase):
    """A copy of the example shop, to change and read."""

    def setUp(self) -> None:
        """Copy the example shop to a scratch directory."""
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch)
        self.directory = Path(scratch) / "shop"
        shutil.copytree(
            EXAMPLES,
            self.directory,
            ignore=shutil.ignore_patterns(".#*", "#*#", "*~"),
        )

    def change(self, name: str, old: str, new: str) -> None:
        """Change some text in one of the copied files."""
        file = self.directory / name
        text = file.read_text(encoding="utf-8")
        self.assertIn(old, text)
        file.write_text(text.replace(old, new, 1), encoding="utf-8")

    def at(self, name: str, text: str, nth: int = 1) -> str:
        """Return `FILE:LINE` of some text in a copied file."""
        lines = (self.directory / name).read_text("utf-8").splitlines()
        found = [n for n, line in enumerate(lines, 1) if text in line]
        self.assertGreaterEqual(len(found), nth, text)
        return f"{name}:{found[nth - 1]}"

    def problems(self, name: str = "home_shop.toml") -> list[str]:
        """Return the problems found reading a copied file."""
        with self.assertRaises(shops.SCShopError) as caught:
            shops.read(self.directory / name)
        prefix = self.directory.as_posix() + "/"
        return [p.replace(prefix, "") for p in caught.exception.problems]


class TestReader(CopiedShop):
    """Reading the example shop, and copies of it with problems."""

    def test_example(self) -> None:
        """The example reads, with its files spliced in."""
        shop = shops.read(EXAMPLES / "home_shop.toml")
        machines = shop["machines"]
        assert isinstance(machines, list)
        mill = machines[0]
        self.assertEqual(mill["name"], "Shop mill")
        self.assertEqual(mill["controller"]["name"], "LinuxCNC")
        self.assertEqual(len(mill["axes"]), 3)

    def test_one_file_or_many(self) -> None:
        """`shops.toml` (in place) reads as the split files do."""

        def without_header(value: object) -> object:
            """Drop the header keys that only files have."""
            if isinstance(value, dict):
                return {
                    key: without_header(item)
                    for key, item in value.items()
                    if key not in ("kind", "language", "version")
                }
            if isinstance(value, list):
                return [without_header(item) for item in value]
            return value

        whole = shops.read(EXAMPLES / "shops.toml")["shops"]
        split = shops.read(EXAMPLES / "home_shop.toml")
        assert isinstance(whole, list)
        self.assertEqual(without_header(whole[0]), without_header(split))

    def test_file_read_once(self) -> None:
        """A file named twice is read once, and spliced in twice."""
        self.change(
            "home_shop.toml",
            '"@shop_router.toml"]',
            '"@shop_router.toml", "@shop_mill.toml"]',
        )
        machines = shops.read(self.directory / "home_shop.toml")["machines"]
        assert isinstance(machines, list)
        self.assertIs(machines[0], machines[2])

        # The mill and the router share one controller file.
        self.assertIs(machines[0]["controller"], machines[1]["controller"])

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
        self.change("shop_mill_tools.toml", "4 = ", "100 = ")
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                [self.at("shop_mill.toml", '"lathe"'), "machine"],
                [self.at("shop_mill_tools.toml", "[tools]"), "tools"],
                [self.at("shop_mill.toml", "t_slots ="), "table.t_slots"],
                [self.at("shop_mill.toml", "= 5000"), "spindle.max_rpm"],
                [self.at("shop_mill.toml", "9 ipm"), "axes[1].travel"],
                [self.at("shop_mill.toml", "brakes ="), "axes[2].brakes"],
            ],
        )
        self.assertIn('"5000 rpm"', problems[3])
        self.assertIn("'ipm' is the wrong unit", problems[4])

    def test_tools(self) -> None:
        """Tool names: unknown in a tool table, or used twice."""
        self.change(
            "shop_mill_tools.toml",
            '2 = "1/8 in cobalt jobber drill"',
            '2 = "1/8 in drill"',
        )
        self.change(
            "tools.toml",
            'name = "1/2 in 2 flute carbide end mill"',
            'name = "1/4 in 2 flute carbide end mill"',
        )
        self.change("tools.toml", "acquired = 2026-10-27", 'acquired = "now"')
        self.change("tools.toml", '"47.02 USD"', '"47.02 XX"')
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                [
                    self.at("tools.toml", '"now"'),
                    "end_mills[0].acquired",
                ],
                [self.at("tools.toml", '"47.02 XX"'), "end_mills[1].cost"],
                [
                    self.at("tools.toml", '"1/4 in 2 flute carbide', 2),
                    "end_mills[1].name",
                ],
                [self.at("shop_mill_tools.toml", "2 = "), "tools.2"],
                [self.at("shop_router_tools.toml", "1 = "), "tools.1"],
            ],
        )
        self.assertIn("is not a date", problems[0])
        self.assertIn("'XX' is the wrong unit", problems[1])
        self.assertIn("also the name of the tool at", problems[2])
        self.assertIn('no tool named "1/8 in drill"', problems[3])

    def test_choices(self) -> None:
        """Choices in any capitals; `!` only where the list is open."""
        self.change("shop_mill.toml", 'interface = "R8"', 'interface = "r8"')
        self.change("shop_router.toml", '"ER20"', '"HSK100A!"')
        self.change(
            "tools.toml",
            'collet = "ER32"\nmaterial = "HSS"',
            'collet = "ER32"\nmaterial = "unobtainium"',
        )
        self.change("tools.toml", '"47.02 USD"', '"64.10 CAD"')
        self.change("shop_mill.toml", 'machine = "mill"', 'machine = "lathe!"')
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                [self.at("shop_mill.toml", '"lathe!"'), "machine"],
                [
                    self.at("tools.toml", '"unobtainium"'),
                    "drills[0].material",
                ],
            ],
        )
        self.assertIn("or another ending in !", problems[1])

        # Once the problems are fixed, the choices read as the schema
        # spells them, or as written when they end in `!`.
        self.change("shop_mill.toml", '"lathe!"', '"MILL"')
        self.change("tools.toml", '"unobtainium"', '"unobtainium!"')
        shop = shops.read(self.directory / "home_shop.toml")
        machines = shop["machines"]
        tools = shop["tools"]
        assert isinstance(machines, list) and isinstance(tools, list)
        self.assertEqual(machines[0]["machine"], "mill")
        self.assertEqual(machines[0]["spindle"]["interface"], "R8")
        self.assertEqual(machines[1]["spindle"]["interface"], "HSK100A!")
        self.assertEqual(tools[0]["drills"][0]["material"], "unobtainium!")
        self.assertEqual(tools[0]["end_mills"][1]["cost"], "64.10 CAD")

    def test_one_place_at_a_time(self) -> None:
        """A tool, a T number and a tool table are each used once."""
        self.change(
            "shop_router_tools.toml",
            '1 = "1/2 in 2 flute carbide end mill"',
            '1 = "1/2 in 2 flute carbide end mill"\n'
            '2 = "1/4 in 2 flute carbide end mill"\n'
            '3 = "1/2 in 2 flute carbide end mill"\n'
            '03 = "15/64 in HSS jobber drill"',
        )
        self.assertEqual(
            [p.split(": ")[:2] for p in self.problems()],
            [["shop_router_tools.toml:7", "tools"]],
        )
        self.change("shop_router_tools.toml", '03 = "15/64', '4 = "15/64')
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                ["shop_router_tools.toml:9", "tools.2"],
                ["shop_router_tools.toml:10", "tools.3"],
                ["shop_router_tools.toml:11", "tools.4"],
            ],
        )
        self.assertIn("also loaded at", problems[0])
        self.assertIn("shop_mill_tools.toml:8", problems[0])

        # Two machines may not share one tool table file.
        self.change(
            "shop_router.toml",
            '"@shop_router_tools.toml"',
            '"@shop_mill_tools.toml"',
        )
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [["shop_router.toml:9", "tool_table"]],
        )
        self.assertIn('also the tool table of "Shop mill"', problems[0])

    def test_tool_number(self) -> None:
        """Where a tool is loaded, by machine and T number."""
        shop = shops.read(EXAMPLES / "home_shop.toml")
        drill = "15/64 in HSS jobber drill"
        self.assertEqual(shops.loaded_in(shop, drill), ("Shop mill", 4))
        self.assertIsNone(shops.loaded_in(shop, "no such tool"))
        machines = shop["machines"]
        assert isinstance(machines, list)
        self.assertEqual(shops.tool_number(machines[0], drill), 4)
        with self.assertRaises(ValueError) as caught:
            shops.tool_number(machines[1], drill)
        self.assertIn('not loaded in "Shop router"', str(caught.exception))

    def test_tool_table_alone(self) -> None:
        """A machine read alone has its tool table unchecked."""
        mill = shops.read(EXAMPLES / "shop_mill.toml")
        self.assertEqual(mill["name"], "Shop mill")

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
                "home_shop.toml:13: location.kind: a `location` belongs here",
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
            '"@shop_router.toml"]',
            '"@shop_router.toml", "@../x.toml", "@nope.toml", '
            '"@linuxcnc.toml", "not a table"]',
        )
        self.change("shop_mill.toml", "@linuxcnc", "@home_shop")
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                ["shop_mill.toml:7", "controller"],
                ["home_shop.toml:6", "machines[2]"],
                ["home_shop.toml:6", "machines[3]"],
                ["home_shop.toml:6", "machines[4]"],
                ["home_shop.toml:6", "machines[5]"],
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


class TestCNCMachine(CopiedShop):
    """A shop's machine, for the G-code side."""

    def test_cnc_machine(self) -> None:
        """A shop's machine, with its loaded tools, for the CNC side."""
        shop = shops.read(EXAMPLES / "home_shop.toml")
        mill = shops.cnc_machine(shop, "Shop mill", "6061 aluminum")
        self.assertEqual(
            mill.tool_change, "T{number:02d} M6 G43 H{number:02d}"
        )
        self.assertEqual(mill.drill_cycle, "G83")
        self.assertAlmostEqual(mill.stepover, 0.9)
        kinds = {tool.number: tool.kind for tool in mill.tools}
        self.assertEqual(
            kinds,
            {
                1: "end mill",
                2: "drill",
                4: "drill",
                5: "chamfer",
                6: "corner round",
                7: "ball end mill",
                8: "roughing end mill",
                9: "double angle",
            },
        )

        # Bits that cut along an edge are placed by their tips.
        rounding = mill.named("1/16 in radius carbide corner rounding mill")
        self.assertAlmostEqual(rounding.diameter, 0.0469)
        self.assertAlmostEqual(rounding.radius, 0.0625)
        drill = mill.drill_for(mill.named("1/4 in 2 flute carbide end mill"))
        self.assertEqual(drill.number, 4)
        self.assertAlmostEqual(drill.peck, 0.05)

        # The router is there too; there is no lathe.
        router = shops.cnc_machine(shop, "Shop router", "6061 aluminum")
        self.assertEqual(
            router.tool(1).name, "1/2 in 2 flute carbide end mill"
        )
        with self.assertRaises(ValueError) as caught:
            shops.cnc_machine(shop, "Lathe")
        self.assertIn('no machine named "Lathe"', str(caught.exception))

    def test_cnc_needs_preferences(self) -> None:
        """A machine with no preferences can not be run."""
        text = (self.directory / "shop_router.toml").read_text("utf-8")
        start = text.index("[preferences]")
        end = text.index("[table]")
        (self.directory / "shop_router.toml").write_text(
            text[:start] + text[end:], encoding="utf-8"
        )
        shop = shops.read(self.directory / "home_shop.toml")
        with self.assertRaises(ValueError) as caught:
            shops.cnc_machine(shop, "Shop router", "6061 aluminum")
        self.assertIn("has no preferences", str(caught.exception))


class TestToolCutting(unittest.TestCase):
    """Speeds and feeds worked out from the shop's `materials`."""

    def setUp(self) -> None:
        self.shop = shops.read(EXAMPLES / "home_shop.toml")
        self.mill = next(
            machine
            for machine in self.shop["machines"]
            if machine["name"] == "Shop mill"
        )
        self.tools = {
            tool["name"]: tool
            for tools in self.shop["tools"]
            for key in ("drills", "end_mills")
            for tool in tools.get(key, [])
        }

    def cutting(self, name: str, material: str) -> tuple[float, ...]:
        return shops.tool_cutting(
            self.shop, self.mill, self.tools[name], material
        )

    def test_hss_drill(self) -> None:
        """RPM = 12 SFM / (pi D); feed = midpoint x factor x RPM."""
        rpm, feed, plunge = self.cutting("15/64 in HSS jobber drill", "steel")
        self.assertAlmostEqual(rpm, 12 * 100 / (3.141592653589793 * 15 / 64))
        self.assertAlmostEqual(feed, rpm * 0.004 * 1.0)
        self.assertAlmostEqual(plunge, feed)

    def test_spindle_limit(self) -> None:
        """A carbide end mill in aluminum is held to the top RPM."""
        rpm, feed, plunge = self.cutting(
            "1/4 in 2 flute carbide end mill", "aluminum"
        )
        self.assertAlmostEqual(rpm, 5000.0)
        self.assertAlmostEqual(feed, 5000 * 0.0015 * 2 * 1.5)
        self.assertAlmostEqual(plunge, feed / 2)

    def test_cobalt_factor(self) -> None:
        """Cobalt runs at its factor of HSS's surface speed."""
        rpm, _, _ = self.cutting(
            "1/4 in 4 flute cobalt roughing end mill", "steel"
        )
        self.assertAlmostEqual(rpm, 12 * 100 * 1.1 / (3.141592653589793 / 4))

    def test_own_cutting_wins(self) -> None:
        """A tool's own entry wins, in any capitals."""
        self.assertEqual(
            self.cutting("1/8 in cobalt jobber drill", "6061 ALUMINUM"),
            (1200.0, 4.0, 4.0),
        )

    def test_unknown_material(self) -> None:
        """An unknown material lists the shop's materials."""
        with self.assertRaises(ValueError) as caught:
            self.cutting("15/64 in HSS jobber drill", "unobtainium")
        self.assertIn(
            '"unobtainium" is not one of: aluminum', str(caught.exception)
        )

    def test_needs_own_cutting(self) -> None:
        """A tool material with no data needs its own entry."""
        tool = dict(self.tools["15/64 in HSS jobber drill"], material="PCD")
        with self.assertRaises(ValueError) as caught:
            shops.tool_cutting(self.shop, self.mill, tool, "steel")
        self.assertIn('needs a `cutting."steel"` entry', str(caught.exception))

    def test_too_large(self) -> None:
        """A tool larger than every range is refused."""
        tool = dict(self.tools["15/64 in HSS jobber drill"], diameter="2 in")
        with self.assertRaises(ValueError) as caught:
            shops.tool_cutting(self.shop, self.mill, tool, "steel")
        self.assertIn("larger than every `feed_ranges`", str(caught.exception))


class TestAxisLimits(TestToolCutting):
    """Feeds the axes can not reach, and edge finishing bits."""

    def test_axis_limit(self) -> None:
        """A feed over the axes' limit scales the RPM down with it."""
        mill = dict(self.mill)
        mill["axes"] = [
            dict(axis, max_feed="10 in/min") for axis in mill["axes"]
        ]
        rpm, feed, plunge = shops.tool_cutting(
            self.shop,
            mill,
            self.tools["1/4 in 2 flute carbide end mill"],
            "aluminum",
        )
        self.assertAlmostEqual(feed, 10.0)
        self.assertAlmostEqual(rpm, 5000.0 * 10.0 / 22.5)
        self.assertAlmostEqual(plunge, 5.0)

    def test_widest(self) -> None:
        """A corner rounding mill is as wide as its tip and radii."""
        self.assertAlmostEqual(
            shops._widest({"tip_diameter": "0.0469 in", "radius": "1/16 in"}),
            0.0469 + 0.125,
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
