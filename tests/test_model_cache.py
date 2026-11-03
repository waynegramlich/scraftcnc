"""Tests for `model_cache`: hashes, the files, and models in SolidCraft."""

import dataclasses
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scraftcnc import model_cache, setups
from scraftcnc.pybind.scraftpybind import JSON, SCHeadlessTransport, SCPyBind
from scraftcnc.shops import read
from scraftcnc.tooling import cutter_models, mount, tools

HERE: Path = Path(__file__).resolve().parent.parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
STACK: Path = HERE / "examples/setup/demo_stack.json"
INCH = 25.4


def session(directory: Path) -> SCHeadlessTransport:
    """Return a headless SolidCraft that may use a directory."""
    return SCHeadlessTransport(
        shutil.which("solidcraft-cli") or str(CLI), (str(directory),)
    )


# `GRID_PLATE` without its chamfers, which take minutes to model: the
# same shape for every check here.
FLAT_PLATE = dataclasses.replace(tools.GRID_PLATE, chamfer_depth=0.0)


def setUpModule() -> None:
    """Have setups name the unchamfered plate."""
    patcher = mock.patch.dict(setups.PARTS, {"Grid plate": FLAT_PLATE})
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def reply(value: JSON) -> Any:
    """Return a reply from SolidCraft untyped, for indexing in tests."""
    return value


def centers(solidcraft: SCPyBind, bodies: list[str]) -> dict[str, list[float]]:
    """Return where each body's center of mass is, by name."""
    found = reply(solidcraft.inspect.center_of_mass(bodies=bodies))
    return {entry["body"]: entry["center"] for entry in found["bodies"]}


class TestHash(unittest.TestCase):
    """The file a tree of shape options names."""

    def test_digits(self) -> None:
        """A hash is 16 hex digits."""
        self.assertRegex(model_cache.shape_hash({"a": 1}), "^[0-9a-f]{16}$")

    def test_key_order(self) -> None:
        """The order of a tree's keys does not matter."""
        self.assertEqual(
            model_cache.shape_hash({"a": 1, "b": [2, {"c": 3, "d": 4}]}),
            model_cache.shape_hash({"b": [2, {"d": 4, "c": 3}], "a": 1}),
        )

    def test_values(self) -> None:
        """A different value is a different hash."""
        self.assertNotEqual(
            model_cache.shape_hash({"a": 1.0}),
            model_cache.shape_hash({"a": 1.5}),
        )

    def test_path(self) -> None:
        """A file is MODEL_NAME__HASH.step, with a safe name."""
        cache = model_cache.SCModelCache(Path("/cache"))
        shape = {"a": 1}
        model = model_cache.SCCacheable("1/4 in mill", shape, lambda _: [])
        self.assertEqual(
            cache.path(model),
            Path(f"/cache/1_4_in_mill__{model_cache.shape_hash(shape)}.step"),
        )

    def test_source_digest(self) -> None:
        """A digest follows the source files."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "code.py"
            path.write_text("a", encoding="utf-8")
            first = model_cache.source_digest([path])
            path.write_text("b", encoding="utf-8")
            self.assertNotEqual(first, model_cache.source_digest([path]))


class TestMatrix(unittest.TestCase):
    """Where a model is placed."""

    def test_turns(self) -> None:
        """Quarter turns are clockwise, seen from above, offset included."""
        for turns, want in (
            (0, (11.0, 20.0)),
            (1, (10.0, 19.0)),
            (2, (9.0, 20.0)),
            (3, (10.0, 21.0)),
            (4, (11.0, 20.0)),
        ):
            matrix = model_cache.placement_matrix(
                turns, (10.0, 20.0, 30.0), (1.0, 0.0, 2.0)
            )
            self.assertEqual((matrix[0][3], matrix[1][3]), want)
            self.assertEqual(matrix[2][3], 32.0)


class TestSweep(unittest.TestCase):
    """Files older than a week go."""

    def test_sweep(self) -> None:
        """An old file is deleted and a young one kept, in one pass."""
        with tempfile.TemporaryDirectory() as directory:
            cache = model_cache.SCModelCache(Path(directory) / "a" / "b")
            cache.sweep()
            old = cache.directory / "old__0.step"
            young = cache.directory / "young__0.step"
            late = cache.directory / "late__0.step"
            week = time.time() - model_cache.MAX_AGE
            for path, when in ((old, week - 60.0), (young, week + 60.0)):
                path.write_text("", encoding="utf-8")
                os.utime(path, (when, when))

            # It runs only once for a cache.
            cache.sweep()
            self.assertTrue(old.exists())
            cache.swept = False
            cache.sweep()
            self.assertFalse(old.exists())
            self.assertTrue(young.exists())
            self.assertFalse(late.exists())


class TestLive(unittest.TestCase):
    """Models in a headless SolidCraft."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.cache = model_cache.SCModelCache(self.directory)
        self.setup = setups.SCSetup(
            json.loads(STACK.read_text(encoding="utf-8"))
        )

    def test_build_once_and_freshen(self) -> None:
        """A model is built the first time, and its file freshened after."""
        builds = []

        def build(solidcraft: SCPyBind) -> list[str]:
            builds.append(1)
            return [
                cutter_models.model(
                    solidcraft, "Pin", [(0, 0), (1, 0), (1, 2), (0, 2)]
                )
            ]

        model = model_cache.SCCacheable("Pin", {"pin": 1}, build)
        path = self.cache.path(model)
        with session(self.directory) as transport:
            solidcraft = SCPyBind(transport)
            first = self.cache.insert(solidcraft, model)
            assert first is not None
            self.assertEqual(first.bodies, ["Pin"])
            self.assertEqual(
                [item.name for item in self.directory.iterdir()], [path.name]
            )
            when = time.time() - 3600.0
            os.utime(path, (when, when))
            second = self.cache.insert(solidcraft, model)
            assert second is not None
            self.assertEqual(second.bodies, ["Pin (2)"])
        self.assertEqual(len(builds), 1)
        self.assertGreater(path.stat().st_mtime, when + 3000.0)

    def test_broken_directory(self) -> None:
        """A directory that can not be made means building, with no file."""
        blocker = self.directory / "file"
        blocker.write_text("", encoding="utf-8")
        cache = model_cache.SCModelCache(blocker / "cache")
        model = model_cache.SCCacheable("Pin", {"pin": 1}, lambda _: [])
        with session(self.directory) as transport:
            solidcraft = SCPyBind(transport)
            self.assertIsNone(cache.insert(solidcraft, model))
        self.assertTrue(cache.broken)

    def test_stack_matches_built(self) -> None:
        """Cached twice, the stack lands just where a built one does."""
        with session(self.directory) as transport:
            solidcraft = SCPyBind(transport)
            names = self.setup.model(solidcraft)
            want = centers(solidcraft, names)
        for _ in range(2):
            with session(self.directory) as transport:
                solidcraft = SCPyBind(transport)
                names = self.setup.model(solidcraft, self.cache)
                got = centers(solidcraft, names)
                appearance = reply(solidcraft.appearance.list())["bodies"]
            self.assertEqual(sorted(got), sorted(want))
            for name, place in want.items():
                for got_axis, want_axis in zip(got[name], place, strict=True):
                    # Round bodies measure a little differently.
                    self.assertAlmostEqual(
                        got_axis, want_axis, places=1, msg=name
                    )
            self.assertEqual(
                appearance["Kurt D688 lead screw"]["color"], tools.DRILL_COLOR
            )
            self.assertEqual(
                appearance["Kurt D688 slider"]["color"], tools.VISE_COLOR
            )
            self.assertEqual(
                appearance["Mikini 1610L"]["color"], tools.TABLE_COLOR
            )
            self.assertFalse(self.cache.broken)
            self.assertEqual(len(list(self.directory.glob("*.step"))), 6)

    def test_units_only_to_build(self) -> None:
        """A design in inches changes units only to build in its session."""
        cli = shutil.which("solidcraft-cli") or str(CLI)
        for program, want_changes in (
            (cli, 0),  # Built headless.
            ("no-such-program", 0),  # Now all are in the cache.
        ):
            self.check_units(program, want_changes)
        for path in self.directory.iterdir():
            path.unlink()
        self.check_units("no-such-program", 2)

    def check_units(self, program: str, want_changes: int) -> None:
        """Model the setup in inches, counting the changes of units."""
        with session(self.directory) as transport:
            solidcraft = SCPyBind(transport)
            solidcraft.document.units(units="in")
            commands = type(solidcraft.document)
            with (
                mock.patch.object(model_cache, "HEADLESS_CLI", program),
                mock.patch.object(
                    commands,
                    "units",
                    autospec=True,
                    side_effect=commands.units,
                ) as units,
            ):
                names = self.setup.model(solidcraft, self.cache, "in")
            self.assertEqual(units.call_count, want_changes)
            self.assertFalse(self.cache.broken)
            table = centers(solidcraft, names)["Mikini 1610L"]
            self.assertAlmostEqual(table[0], 2.0 * INCH, places=1)
            self.assertAlmostEqual(table[1], 1.5 * INCH, places=1)

    def test_built_in_its_own_session(self) -> None:
        """With the program, a model is not built in the design's session."""
        cli = shutil.which("solidcraft-cli") or str(CLI)
        sessions = []

        def build(solidcraft: SCPyBind) -> list[str]:
            sessions.append(solidcraft)
            return [
                cutter_models.model(
                    solidcraft, "Pin", [(0, 0), (1, 0), (1, 2), (0, 2)]
                )
            ]

        model = model_cache.SCCacheable("Pin", {"pin": 2}, build)
        with (
            session(self.directory) as transport,
            mock.patch.object(model_cache, "HEADLESS_CLI", cli),
        ):
            solidcraft = SCPyBind(transport)
            inserted = self.cache.insert(solidcraft, model)
            assert inserted is not None
            self.assertEqual(inserted.bodies, ["Pin"])
        self.assertEqual(len(sessions), 1)
        self.assertIsNot(sessions[0], solidcraft)

    def test_vise_two_files(self) -> None:
        """The vise is two files, which any opening shares."""
        vise = tools.KURT_D688
        for opening in (10.0, 100.0):
            layer = mount.SCMachineViseLayer(vise, opening)
            with session(self.directory) as transport:
                setups.SCPlacement(0.0, 0.0, 0.0, 0).model(
                    layer, SCPyBind(transport), self.cache
                )
        self.assertFalse(self.cache.broken)
        self.assertEqual(
            sorted(
                path.name.split("__")[0] for path in self.directory.iterdir()
            ),
            ["Kurt_D688", "Kurt_D688_movable"],
        )

    def test_tool_with_lines_at_a_place(self) -> None:
        """A cached tool lands, and moves, with its flute lines."""
        tool = cutter_models.shop_tools(read(cutter_models.EXAMPLE_SHOP))[4]
        at = (2.0, 1.0, 3.0)
        with session(self.directory) as transport:
            solidcraft = SCPyBind(transport)
            want = centers(
                solidcraft,
                [cutter_models.model_tool(solidcraft, "T", tool, at).body],
            )["T"]
        for _ in range(2):
            with session(self.directory) as transport:
                solidcraft = SCPyBind(transport)
                made = cutter_models.model_tool(
                    solidcraft, "T5", tool, at, "#123456", self.cache
                )
                self.assertFalse(self.cache.broken)
                self.assertEqual(made.body, "T5")
                self.assertEqual(made.sketch, "T5 flutes")
                solidcraft.browser.visibility(
                    visible=False, items=made.items()
                )
                got = centers(solidcraft, ["T5"])["T5"]
                color = reply(solidcraft.appearance.list())["bodies"]["T5"][
                    "color"
                ]
            self.assertEqual(color, "#123456")
            for got_axis, want_axis in zip(got, want, strict=True):
                self.assertAlmostEqual(got_axis, want_axis, places=2)


if __name__ == "__main__":
    unittest.main()
