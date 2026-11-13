"""Tests for `shops`: the line finder, the reader and `Shops.md`."""

import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any, cast

from scraftcam import shops

# A `kind` line that does not belong in a location.
KIND_MACHINE: str = 'kind = "machine"'

# The example shop.
EXAMPLES: Path = Path(__file__).parent.parent / "examples" / "shop"


def lines_of(text: str) -> dict[shops.KeyPath, int]:
    """Return the line of every key path in some TOML."""
    tomllib.loads(text)
    # pylint: disable-next=protected-access
    return shops._Scanner(text).document()


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

    def problems(self, name: str = "shop.toml") -> list[str]:
        """Return the problems found reading a copied file."""
        with self.assertRaises(shops.ShopError) as caught:
            shops.read(self.directory / name)
        prefix = self.directory.as_posix() + "/"
        return [p.replace(prefix, "") for p in caught.exception.problems]


class TestReader(CopiedShop):
    """Reading the example shop, and copies of it with problems."""

    # The files changed most.
    MILL: str = "machines/shop_mill.toml"
    ROUTER: str = "machines/shop_router.toml"
    LINUXCNC: str = "controllers/linuxcnc.toml"
    END_MILL: str = "tools/1_4_in_2_flute_carbide_end_mill.toml"
    ROUTER_MILL: str = "tools/1_2_in_2_flute_carbide_end_mill.toml"
    BALL_MILL: str = "tools/1_4_in_2_flute_hss_ball_end_mill.toml"
    DRILL: str = "tools/15_64_in_hss_jobber_drill.toml"

    def test_example(self) -> None:
        """The example reads, its directories filled in."""
        shop: dict[str, Any] = shops.read(EXAMPLES / "shop.toml")
        self.assertEqual(shops.read(EXAMPLES), shop)
        mill = shop["machines"][0]
        self.assertEqual(mill["name"], "Shop mill")
        self.assertEqual(mill["controller"]["name"], "LinuxCNC")
        self.assertEqual(len(mill["axes"]), 3)
        self.assertEqual(
            mill["tool_table"]["tools"]["4"], "15/64 in HSS jobber drill"
        )
        self.assertEqual(len(shop["tools"][0]["end_mills"]), 7)
        self.assertEqual(
            shop["tooling"][0]["grid_plates"][0]["name"], "Grid plate"
        )
        self.assertEqual(len(shop["materials"]["materials"]), 19)
        self.assertEqual(shop["materials"]["groups"][0]["name"], "soft")
        self.assertEqual(shop["units"], "in")

    def test_syntax_error(self) -> None:
        """A TOML syntax error gives its file, line and column."""
        self.change(self.MILL, 'machine = "mill"', "machine = mill")
        self.assertEqual(
            self.problems(),
            [f"{self.at(self.MILL, 'machine = mill')}:11: Invalid value"],
        )

    def test_value_problems(self) -> None:
        """Every problem is found, each at its line."""
        self.change(self.MILL, '"5000 rpm"', "5000")
        self.change(self.MILL, 'travel = "9 in"', 'travel = "9 ipm"')
        self.change(self.MILL, "brake = true", "brakes = true")
        self.change(self.MILL, "t_slots = 3", 't_slots = "3"')
        self.change(self.MILL, '"mill"', '"lathe"')
        self.change(self.MILL, "4 = ", "100 = ")
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                [self.at(self.MILL, '"lathe"'), "machine"],
                [self.at(self.MILL, "9 ipm"), "axes[1].travel"],
                [self.at(self.MILL, "brakes ="), "axes[2].brakes"],
                [self.at(self.MILL, "t_slots ="), "table.t_slots"],
                [self.at(self.MILL, "= 5000"), "spindle.max_rpm"],
                [self.at(self.MILL, "[tool_table.tools]"), "tool_table.tools"],
            ],
        )

    def test_tools(self) -> None:
        """Tool names: unknown in a tool table, or used twice."""
        self.change(
            self.MILL,
            '2 = "1/8 in cobalt jobber drill"',
            '2 = "1/8 in drill"',
        )
        self.change(
            self.ROUTER_MILL,
            'name = "1/2 in 2 flute carbide end mill"',
            'name = "1/4 in 2 flute carbide end mill"',
        )
        self.change(self.END_MILL, "acquired = 2026-10-27", 'acquired = "now"')
        self.change(self.ROUTER_MILL, '"47.02 USD"', '"47.02 XX"')
        problems = self.problems()
        self.assertEqual(
            sorted(p.split(": ")[:2] for p in problems),
            sorted(
                [
                    [self.at(self.END_MILL, '"now"'), "acquired"],
                    [self.at(self.ROUTER_MILL, '"47.02 XX"'), "cost"],
                    [self.at(self.END_MILL, "name ="), "name"],
                    [self.at(self.MILL, "2 = "), "tool_table.tools.2"],
                    [self.at(self.ROUTER, "1 = "), "tool_table.tools.1"],
                ]
            ),
        )
        text = "\n".join(problems)
        self.assertIn("is not a date", text)
        self.assertIn("'XX' is the wrong unit", text)
        self.assertIn("also the name of the tool at", text)
        self.assertIn('no tool named "1/8 in drill"', text)

    def test_unique_ids(self) -> None:
        """A tool's `unique_id`: positive, unique and required."""
        changes = (
            (self.END_MILL, "unique_id = 1\n", "unique_id = 0\n"),
            (self.ROUTER_MILL, "unique_id = 2\n", "unique_id = -2\n"),
            (self.BALL_MILL, "unique_id = 3\n", 'unique_id = "3"\n'),
            (self.DRILL, "unique_id = 5\n", "unique_id = true\n"),
        )
        for name, old, new in changes:
            self.change(name, old, new)
        problems = self.problems()
        self.assertEqual(
            sorted(p.split(": ")[0] for p in problems),
            sorted(self.at(name, new.strip()) for name, _, new in changes),
        )
        for problem in problems:
            self.assertIn("is not a whole number of 1 or more", problem)

        # The same number twice, and none at all.
        for name, old, new in changes:
            self.change(name, new, old)
        self.change(self.DRILL, "unique_id = 5\n", "unique_id = 1\n")
        self.change(self.BALL_MILL, "unique_id = 3\n", "")
        text = "\n".join(self.problems())
        self.assertIn("1 is also the unique id of the tool at", text)
        self.assertIn("`unique_id` is missing", text)

    def test_example_unique_ids(self) -> None:
        """The example's unique ids run from 1, with no gaps."""
        shop: dict[str, Any] = shops.read(EXAMPLES)
        tools = shop["tools"][0]
        numbers = [
            tool["unique_id"] for key in shops.CNC_KINDS for tool in tools[key]
        ]
        self.assertEqual(sorted(numbers), list(range(1, len(numbers) + 1)))

    def test_holder(self) -> None:
        """`holder`: entries in any capitals, others ending in `!`."""
        self.change(
            self.END_MILL,
            'holder = ["r8", "1/4 in"]',
            'holder = ["CAT40", "ER32", "1/4 in"]',
        )
        self.change(
            self.ROUTER_MILL,
            'holder = ["er20", "1/2 in"]',
            'holder = ["Tormach", "12 mm"]',
        )
        self.change(
            self.BALL_MILL,
            'holder = ["r8", "3/8 in"]',
            'holder = ["capto-c6!", "hsk-a100", "drill-chuck", "3/8 in"]',
        )
        shop: dict[str, Any] = shops.read(self.directory)
        holders = {
            tool["name"]: tool["holder"]
            for tool in shop["tools"][0]["end_mills"]
        }
        self.assertEqual(
            holders["1/4 in 2 flute carbide end mill"],
            ["cat40", "er32", "1/4 in"],
        )
        self.assertEqual(
            holders["1/2 in 2 flute carbide end mill"], ["tormach", "12 mm"]
        )
        self.assertEqual(
            holders["1/4 in 2 flute HSS ball end mill"],
            ["capto-c6!", "hsk-a100", "drill-chuck", "3/8 in"],
        )

    def test_holder_problems(self) -> None:
        """A `holder` that is not understood, at its own line."""
        bad = (
            (
                self.END_MILL,
                'holder = ["r8", "1/4 in"]',
                'holder = ["capto", "1/4 in"]',
            ),
            (
                self.ROUTER_MILL,
                'holder = ["er20", "1/2 in"]',
                'holder = ["r8", "1/2"]',
            ),
            (self.BALL_MILL, 'holder = ["r8", "3/8 in"]', 'holder = ["r8"]'),
            (self.DRILL, 'holder = ["r8", "er32", "1/4 in"]', 'holder = "r8"'),
        )
        for name, old, new in bad:
            self.change(name, old, new)
        problems = self.problems()
        self.assertEqual(
            sorted(p.split(": ")[:2] for p in problems),
            sorted([self.at(name, new), "holder"] for name, _, new in bad),
        )
        text = "\n".join(problems)
        self.assertIn("or another ending in !", text)
        self.assertIn("is the wrong unit", text)
        self.assertIn("is not a list of what holds", text)

    def test_choices(self) -> None:
        """Choices in any capitals; `!` only where the list is open."""
        self.change(self.MILL, 'interface = "R8"', 'interface = "r8"')
        self.change(self.ROUTER, '"ER20"', '"HSK100A!"')
        self.change(self.DRILL, 'material = "HSS"', 'material = "unobtainium"')
        self.change(self.ROUTER_MILL, '"47.02 USD"', '"64.10 CAD"')
        self.change(self.MILL, 'machine = "mill"', 'machine = "lathe!"')
        problems = self.problems()
        self.assertEqual(
            sorted(p.split(": ")[:2] for p in problems),
            sorted(
                [
                    [self.at(self.MILL, '"lathe!"'), "machine"],
                    [self.at(self.DRILL, '"unobtainium"'), "material"],
                ]
            ),
        )

        # Once the problems are fixed, the choices read as the schema
        # spells them, or as written when they end in `!`.
        self.change(self.MILL, '"lathe!"', '"MILL"')
        self.change(self.DRILL, '"unobtainium"', '"unobtainium!"')
        shop: dict[str, Any] = shops.read(self.directory)
        machines = shop["machines"]
        self.assertEqual(machines[0]["machine"], "mill")
        self.assertEqual(machines[0]["spindle"]["interface"], "R8")
        self.assertEqual(machines[1]["spindle"]["interface"], "HSK100A!")
        drills = {tool["name"]: tool for tool in shop["tools"][0]["drills"]}
        self.assertEqual(
            drills["15/64 in HSS jobber drill"]["material"], "unobtainium!"
        )

    def test_shop_keys(self) -> None:
        """`units` and `machine_kinds`, as the GUI writes them."""
        self.change("shop.toml", 'units = "in"', 'units = "MM"')
        self.change("shop.toml", '"cnc_mill"', '"CNC_mill", "loom"')
        problems = self.problems()
        self.assertEqual(len(problems), 1)
        self.assertIn('"loom" is not one of', problems[0])
        self.change("shop.toml", ', "loom"', "")
        shop: dict[str, Any] = shops.read(self.directory)
        self.assertEqual(shop["units"], "mm")
        self.assertEqual(shop["machine_kinds"][0], "cnc_mill")

    def test_one_place_at_a_time(self) -> None:
        """A tool, and a T number, are each used once."""
        self.change(
            self.ROUTER,
            '1 = "1/2 in 2 flute carbide end mill"',
            '1 = "1/2 in 2 flute carbide end mill"\n'
            '2 = "1/4 in 2 flute carbide end mill"\n'
            '3 = "1/2 in 2 flute carbide end mill"\n'
            '03 = "15/64 in HSS jobber drill"',
        )
        self.assertEqual(
            [p.split(": ")[:2] for p in self.problems()],
            [[self.at(self.ROUTER, "[tool_table.tools]"), "tool_table.tools"]],
        )
        self.change(self.ROUTER, '03 = "15/64', '4 = "15/64')
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                [self.at(self.ROUTER, "2 = "), "tool_table.tools.2"],
                [self.at(self.ROUTER, "3 = "), "tool_table.tools.3"],
                [self.at(self.ROUTER, "4 = "), "tool_table.tools.4"],
            ],
        )
        self.assertIn("also loaded at", problems[0])
        self.assertIn(self.at(self.MILL, "1 = "), problems[0])

    def test_tool_number(self) -> None:
        """Where a tool is loaded, by machine and T number."""
        shop = shops.read(EXAMPLES)
        drill = "15/64 in HSS jobber drill"
        self.assertEqual(shops.loaded_in(shop, drill), ("Shop mill", 4))
        self.assertIsNone(shops.loaded_in(shop, "no such tool"))
        machines = shop["machines"]
        assert isinstance(machines, list)
        self.assertEqual(shops.tool_number(machines[0], drill), 4)
        with self.assertRaises(ValueError) as caught:
            shops.tool_number(machines[1], drill)
        self.assertIn('not loaded in "Shop router"', str(caught.exception))

    def test_top_must_be_a_shop(self) -> None:
        """A machine's file is not a shop."""
        problems = self.problems(self.MILL)
        self.assertIn("the top file must be a `shop`", problems[-1])

    def test_missing_and_kind(self) -> None:
        """Missing keys, and a `kind` that does not fit."""
        self.change(self.LINUXCNC, 'post_processor = "linuxcnc"\n', "")
        self.change(self.MILL, 'version = "0.0.1"\n', "")
        self.change(
            "shop.toml",
            'address = "',
            'kind = "machine"\naddress = "',
        )
        self.assertEqual(
            self.problems(),
            [
                self.at("shop.toml", KIND_MACHINE)
                + ": location.kind: a `location` belongs here",
                f"{self.LINUXCNC}:1: `post_processor` is missing",
                f"{self.MILL}:1: `version` is missing",
            ],
        )

    def test_versions(self) -> None:
        """A newer minor version, or another major one, is refused."""
        self.change(self.LINUXCNC, '"0.0.1"', '"0.1.0"')
        self.change(self.MILL, '"0.0.1"', '"1.0.0"')
        problems = self.problems()
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith(f"{self.LINUXCNC}:5: version"))
        self.assertTrue(problems[1].startswith(f"{self.MILL}:5: version"))

    def test_names(self) -> None:
        """Controllers by name; no `@`; files where they belong."""
        self.change(
            self.MILL, 'controller = "LinuxCNC"', 'controller = "Nope"'
        )
        self.change(
            self.ROUTER,
            'controller = "LinuxCNC"',
            'controller = "@linuxcnc.toml"',
        )
        shutil.copy(
            self.directory / self.LINUXCNC, self.directory / "tools/x.toml"
        )
        shutil.copy(
            self.directory / self.LINUXCNC,
            self.directory / "controllers/again.toml",
        )
        problems = self.problems()
        self.assertEqual(
            [p.split(": ")[:2] for p in problems],
            [
                ["controllers/linuxcnc.toml:1", "name"],
                ["tools/x.toml:1", "kind"],
                [self.at(self.MILL, '"Nope"'), "controller"],
                [self.at(self.ROUTER, '"@linuxcnc'), "controller"],
            ],
        )
        self.assertIn("also the name of another `controller`", problems[0])
        self.assertIn("does not belong in tools/", problems[1])
        self.assertIn('no `controller` named "Nope"', problems[2])
        self.assertIn('no longer named with "@"', problems[3])

    def test_unknown_kind(self) -> None:
        """A top file whose `kind` is not known."""
        self.change("shop.toml", 'kind = "shop"', 'kind = "shoppe"')
        self.assertEqual(
            [p.split(": ")[:2] for p in self.problems()],
            [[self.at("shop.toml", "shoppe"), "kind"]],
        )


class TestCNCMachine(CopiedShop):
    """A shop's machine, for the G-code side."""

    def test_cnc_machine(self) -> None:
        """A shop's machine, with its loaded tools, for the CNC side."""
        shop = shops.read(EXAMPLES)
        mill = shops.cnc_machine(shop, "Shop mill", "6061 aluminum")
        self.assertEqual(
            mill.change_lines(2, "a drill"),
            ["(MSG, Insert T02: a drill)", "M0", "T02 M6 G43 H02"],
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
        text = (self.directory / "machines/shop_router.toml").read_text(
            "utf-8"
        )
        start = text.index("[preferences]")
        end = text.find("\n[", start) + 1 or len(text)
        (self.directory / "machines/shop_router.toml").write_text(
            text[:start] + text[end:], encoding="utf-8"
        )
        shop = shops.read(self.directory)
        with self.assertRaises(ValueError) as caught:
            shops.cnc_machine(shop, "Shop router", "6061 aluminum")
        self.assertIn("has no preferences", str(caught.exception))


class TestToolCutting(unittest.TestCase):
    """Speeds and feeds worked out from the shop's `materials`."""

    def setUp(self) -> None:
        # The shop is TOML data, so `Any` lets the tests index into it.
        self.shop = cast(dict[str, Any], shops.read(EXAMPLES))
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
            '"unobtainium" is not one of: 1018 mild steel',
            str(caught.exception),
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
        written = (Path(__file__).parent.parent / "Shops.md").read_text(
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
        table = shops.markdown_table(
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
        """Each kind's example checks against its kind."""
        for kind in shops.KINDS.values():
            with self.subTest(kind=kind.kind):
                # pylint: disable-next=protected-access
                reader = shops._Reader(EXAMPLES)
                reader.named["controller"] = {"LinuxCNC": {}}
                # pylint: disable-next=protected-access
                source = shops._Source(kind.kind, {})
                reader.table(tomllib.loads(kind.example), kind, (), source)
                self.assertEqual(reader.problems, [])


if __name__ == "__main__":
    unittest.main()
