"""Tests for `scraftcnc.tooling.registry` and the tooling registries."""

import unittest
from typing import Any

from scraftcnc.shops import read
from scraftcnc.tooling import tools
from scraftcnc.tooling.cutter_models import (
    EXAMPLE_SHOP,
    SCCutter,
    register_cutters,
    shop_tools,
)
from scraftcnc.tooling.registry import SCRegistry, key
from scraftcnc.tooling.shop_registries import use_shop


# Function `setUpModule()`:
def setUpModule() -> None:
    """Fill the name registries from the example shop."""
    use_shop(read(EXAMPLE_SHOP))


class TestRegistry(unittest.TestCase):
    """`key()` and `SCRegistry`."""

    def test_key(self) -> None:
        """Names become short identifiers."""
        self.assertEqual(key("Kurt D688"), "kurt_d688")
        self.assertEqual(key("Parallel 1-1/8 in A"), "parallel_1_1_8_in_a")
        self.assertEqual(key("kurt_d688"), "kurt_d688")

    def test_named(self) -> None:
        """An object is found by its key or its name."""
        registry: SCRegistry[int] = SCRegistry("number")
        self.assertEqual(registry.add("Forty Two", 42), 42)
        self.assertEqual(registry.named("forty_two"), 42)
        self.assertEqual(registry.named("Forty Two"), 42)

    def test_unknown(self) -> None:
        """An unknown name lists the known keys."""
        registry: SCRegistry[int] = SCRegistry("number")
        registry.add("One", 1)
        registry.add("Two", 2)
        with self.assertRaises(KeyError) as caught:
            registry.named("Three")
        self.assertIn("one, two", str(caught.exception))

    def test_duplicate(self) -> None:
        """A different object with the same key names both."""
        registry: SCRegistry[str] = SCRegistry("word")
        registry.add("A b", "first")
        registry.add("a_b", "first")
        with self.assertRaises(ValueError) as caught:
            registry.add("A-B", "second")
        self.assertIn("'first'", str(caught.exception))
        self.assertIn("'second'", str(caught.exception))


class TestTooling(unittest.TestCase):
    """The four tooling classes' `named()`."""

    def test_round_trip(self) -> None:
        """Each registered object comes back by key and by name."""
        item: Any
        for item in (
            *tools.MILL_TABLES,
            tools.MIKINI_1610L,
            tools.KURT_D688,
            *tools.PARALLELS,
        ):
            named: Any = type(item).named
            self.assertIs(named(item.name), item)
            self.assertIs(named(key(item.name)), item)

        # The grid plate is the shop's own, equal to the built-in one.
        plate: tools.SCGridPlate = tools.GRID_PLATE
        self.assertEqual(tools.SCGridPlate.named(plate.name), plate)
        self.assertEqual(tools.SCGridPlate.named(key(plate.name)), plate)
        self.assertIs(tools.SCMachineVise.named("kurt_d688"), tools.KURT_D688)
        self.assertIs(
            tools.SCMillTable.named("mikini_1610l"), tools.MIKINI_1610L
        )

    def test_unknown(self) -> None:
        """An unknown vise is a `KeyError`."""
        with self.assertRaises(KeyError):
            tools.SCMachineVise.named("no_such_vise")


class TestKeyProperty(unittest.TestCase):
    """Each tooling object knows its key."""

    def test_keys(self) -> None:
        """`key` is the registry key, and `named()` finds the object."""
        self.assertEqual(tools.KURT_D688.key, "kurt_d688")
        self.assertEqual(tools.GRID_PLATE.key, "grid_plate")
        for registry in (
            tools.SCMillTable.REGISTRY,
            tools.SCMachineVise.REGISTRY,
            tools.SCParallel.REGISTRY,
            tools.SCGridPlate.REGISTRY,
        ):
            for name_key, item in registry.items.items():
                with self.subTest(key=name_key):
                    self.assertEqual(item.key, name_key)


if __name__ == "__main__":
    unittest.main()


class TestCutters(unittest.TestCase):
    """Test the cutter registry of `tooling.cutter_models`."""

    def test_named_round_trip(self) -> None:
        """Test that every tool of the example shop is found by name."""
        shop: dict[str, object] = read(EXAMPLE_SHOP)
        found: list[tuple[str, dict[str, object]]] = shop_tools(shop)
        self.assertEqual(len(SCCutter.REGISTRY.items), len(found))
        kind: str
        tool: dict[str, object]
        for kind, tool in found:
            cutter: SCCutter = SCCutter.named(str(tool["name"]))
            self.assertEqual(cutter, SCCutter(kind, tool))
            self.assertIs(SCCutter.named(cutter.key), cutter)

    def test_unknown_name(self) -> None:
        """Test that an unknown name lists the known keys."""
        with self.assertRaises(KeyError) as caught:
            SCCutter.named("No such bit")
        message: str = str(caught.exception)
        self.assertIn("No cutter is named 'No such bit'", message)
        self.assertIn("1_4_in_2_flute_carbide_end_mill", message)

    def test_duplicate_names(self) -> None:
        """Test that two different tools with one key are an error."""
        cutters: SCRegistry[SCCutter] = SCRegistry("cutter")
        shop: dict[str, object] = read(EXAMPLE_SHOP)
        register_cutters(shop, cutters)
        register_cutters(shop, cutters)
        first: SCCutter = next(iter(cutters.items.values()))
        other: SCCutter = SCCutter("drills", first.tool)
        with self.assertRaises(ValueError) as caught:
            cutters.add(first.name, other)
        self.assertIn(first.key, str(caught.exception))


class TestUseShop(unittest.TestCase):
    """`use_shop()` leaves nothing of an earlier shop."""

    def test_nothing_left(self) -> None:
        """An entry only an earlier shop had is gone after `use_shop()`."""
        shop: dict[str, object] = read(EXAMPLE_SHOP)
        use_shop(shop)
        registries: tuple[SCRegistry[Any], ...] = (
            SCCutter.REGISTRY,
            tools.SCMillTable.REGISTRY,
            tools.SCMachineVise.REGISTRY,
            tools.SCParallel.REGISTRY,
            tools.SCGridPlate.REGISTRY,
        )
        counts: list[int] = [len(found.items) for found in registries]
        for found in registries:
            found.items["only_in_shop_a"] = object()
        use_shop(shop)
        for found, count in zip(registries, counts, strict=True):
            self.assertNotIn("only_in_shop_a", found.items)
            self.assertEqual(len(found.items), count)
            self.assertTrue(found.items)
