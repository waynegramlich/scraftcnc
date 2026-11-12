"""Tests for `scraftcam.setup_view`."""

import json
import os
import shutil
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from scraftcam.assembly import (
    Assembly,
    AssemblyItem,
    Stock,
    millimeters,
    resolve,
)
from scraftcam.demo import DemoPart, demo_assembly
from scraftcam.model_cache import Cacheable, InsertedModel
from scraftcam.pybind.scraftpybind import (
    HeadlessTransport,
    PyBind,
    SolidCraftError,
)
from scraftcam.setup_view import (
    PlacedItem,
    SetupView,
    box_edges,
    display_keys,
    keep_out_prisms,
    named_origins,
    place,
)
from scraftcam.shops import read
from scraftcam.tooling.cutter_models import EXAMPLE_SHOP
from scraftcam.tooling.mount import ParallelLayer
from scraftcam.tooling.shop_registries import use_shop
from scraftcam.tooling.tools import GridPlate, Point, quarter_turn
from tests.flat_plate import FLAT_PLATE

# The demonstration's setup file.
DEMO_STACK: Path = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "setup"
    / "demo_stack.json"
)


# The name `unittest` looks for.
def setUpModule() -> None:  # pylint: disable=invalid-name
    """Fill the name dictionaries from the example shop."""
    use_shop(read(EXAMPLE_SHOP))


# A stand-in needs only `origin()`.
class _Fake:  # pylint: disable=too-few-public-methods
    """An object whose origin is a fixed point, turned."""

    def __init__(self, point: Point) -> None:
        self.point: Point = point

    def origin(self, turns: int = 0) -> Point:
        """Return the point, turned."""
        return quarter_turn(self.point, turns)


def _resolver(fakes: dict[str, Any]) -> Callable[[AssemblyItem], Any]:
    """Return a resolver that finds each item's object by its name."""

    def found(item: AssemblyItem) -> Any:
        """Return the item's object."""
        return fakes[item.name]

    return found


def _item(name: str, location: Point, turns: int = 0) -> AssemblyItem:
    """Return a tooling item."""
    return AssemblyItem(
        kind="tooling",
        name=name,
        call="fake:thing",
        args={},
        location=location,
        orientation=turns,
    )


class TestPlace(unittest.TestCase):
    """Tests for `place()`."""

    def check(self, placed: PlacedItem, expected: Point) -> None:
        """Check where an item was placed."""
        got: Point = (placed.x, placed.y, placed.z)
        axis: int
        for axis in range(3):
            self.assertAlmostEqual(got[axis], expected[axis], places=6)

    def test_turns(self) -> None:
        """Each item's origin is turned by its own quarter turns."""
        turns: int
        expected: list[Point] = [
            (11.0, 22.0, 3.0),
            (8.0, 21.0, 3.0),
            (9.0, 18.0, 3.0),
            (12.0, 19.0, 3.0),
        ]
        for turns in range(4):
            with self.subTest(turns=turns):
                assembly: Assembly = Assembly(
                    [
                        _item("base", (10.0, 20.0, 0.0), turns),
                        _item("top", (0.0, 0.0, 0.0)),
                    ]
                )
                fakes: dict[str, Any] = {
                    "base": _Fake((1.0, 2.0, 3.0)),
                }
                placed: list[PlacedItem] = place(assembly, _resolver(fakes))
                self.assertEqual(placed[0].turns, turns)
                self.check(placed[0], (10.0, 20.0, 0.0))
                self.check(placed[1], expected[turns])

    def test_chain(self) -> None:
        """Offsets chain up the stack; the top item is never built."""
        assembly: Assembly = Assembly(
            [
                _item("a", (100.0, 0.0, -50.0)),
                _item("b", (5.0, 6.0, 0.0), 1),
                _item("c", (1.0, 1.0, 1.0)),
            ]
        )
        fakes: dict[str, Any] = {
            "a": _Fake((-10.0, 10.0, 20.0)),
            "b": _Fake((1.0, 0.0, 2.0)),
        }
        placed: list[PlacedItem] = place(assembly, _resolver(fakes))
        self.check(placed[0], (100.0, 0.0, -50.0))
        self.check(placed[1], (95.0, 16.0, -30.0))
        self.check(placed[2], (96.0, 18.0, -27.0))

    def test_parallels_pass_through(self) -> None:
        """Parallels do not change the origin handed up."""
        parallel: ParallelLayer = ParallelLayer.named("parallel_1_1_2_in_a")
        assembly: Assembly = Assembly(
            [
                _item("vise", (0.0, 0.0, 0.0)),
                _item("parallel A", (3.0, 4.0, -5.0)),
                _item("parallel B", (3.0, -4.0, -5.0)),
                _item("plate", (1.0, 2.0, 3.0)),
            ]
        )
        fakes: dict[str, Any] = {
            "vise": _Fake((10.0, 20.0, 30.0)),
            "parallel A": parallel,
            "parallel B": parallel,
        }
        placed: list[PlacedItem] = place(assembly, _resolver(fakes))
        self.check(placed[1], (13.0, 24.0, 25.0))
        self.check(placed[2], (13.0, 16.0, 25.0))
        self.check(placed[3], (11.0, 22.0, 33.0))

    def test_demo(self) -> None:
        """The demo's tooling lands where `demo_stack.json` puts it.

        `demo_stack.json` centers the plate on the work zero; the
        G-code's work zero is the plate's lower left top corner, so
        `demo.py` centers the stock and the plate on the grid plate at
        `middle` (2, 1.5) in instead (`T.hlp~3.3.1` #78, #80).
        """
        stack: dict[str, Any] = json.loads(DEMO_STACK.read_text())
        middle: tuple[float, float] = (
            millimeters("2 in", "x"),
            millimeters("1-1/2 in", "y"),
        )
        placed: list[PlacedItem] = place(demo_assembly(), resolve)
        layer: dict[str, Any]
        here: PlacedItem
        for here, layer in zip(placed, stack["tooling"], strict=False):
            with self.subTest(item=here.item.name):
                self.check(
                    here,
                    (
                        millimeters(layer["location"][0], "x"),
                        millimeters(layer["location"][1], "y"),
                        millimeters(layer["height"], "z"),
                    ),
                )

        # The stock and the part are centered on the grid plate.
        half: float = millimeters("1/2 in", "z")
        self.check(placed[-2], (middle[0], middle[1], -half))
        self.check(placed[-1], (middle[0], middle[1], -half))
        plate: PlacedItem = placed[-3]
        self.check(plate, (middle[0], middle[1], plate.z))

    def test_named_origins(self) -> None:
        """The demo's origins, in work millimeters (the step 3 boxes)."""
        origins = dict(named_origins(demo_assembly()))
        self.assertEqual(
            list(origins),
            [
                "mill table: top upper left",
                "vise: fixed jaw top left inner",
                "grid plate: top left outer",
                "stock: top left outer",
                "work zero",
            ],
        )
        expected: dict[str, tuple[float, float, float]] = {
            "mill table: top upper left": (-330.2, 171.45, -130.556),
            "grid plate: top left outer": (-82.55, -31.75, -12.7),
            "stock: top left outer": (-6.35, -6.35, 0.0),
            "work zero": (0.0, 0.0, 0.0),
        }
        name: str
        for name, point in expected.items():
            for got, want in zip(origins[name], point, strict=True):
                self.assertAlmostEqual(got, want, places=3, msg=name)


# A stand-in for one SolidCraft command namespace.
class _Namespace:  # pylint: disable=too-few-public-methods
    """Records each command called on it."""

    def __init__(self, name: str, calls: list[tuple[str, Any]]) -> None:
        self.name: str = name
        self.calls: list[tuple[str, Any]] = calls

    def __getattr__(self, command: str) -> Callable[..., Any]:
        def called(**arguments: Any) -> Any:
            """Record the call; a 3D line makes one curve."""
            self.calls.append((f"{self.name}.{command}", arguments))
            if command == "line3d":
                return {"curves": [f"c{len(self.calls)}"]}
            return {}

        return called


# A stand-in for a SolidCraft session.
# One attribute per SolidCraft namespace used, so many attributes.
# pylint: disable-next=too-few-public-methods,too-many-instance-attributes
class _Session:
    """Has `solid`, `sketch`, `appearance`, `document`, `timeline`
    and `view`, recording calls; `browser`'s go to `shown` alone."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.solid: _Namespace = _Namespace("solid", self.calls)
        self.sketch: _Namespace = _Namespace("sketch", self.calls)
        self.appearance: _Namespace = _Namespace("appearance", self.calls)
        self.document: _Namespace = _Namespace("document", self.calls)
        self.timeline: _Namespace = _Namespace("timeline", self.calls)
        self.view: _Namespace = _Namespace("view", self.calls)
        self.shown: list[tuple[str, Any]] = []
        self.browser: _Namespace = _Namespace("browser", self.shown)

    def names(self) -> list[str]:
        """Return the commands called, and forget them."""
        names: list[str] = [name for name, _ in self.calls]
        self.calls.clear()
        return names


# A stand-in namespace whose every command fails.
class _Refusing:  # pylint: disable=too-few-public-methods
    """Answers every command with one function."""

    def __init__(self, answer: Callable[..., Any]) -> None:
        self.answer: Callable[..., Any] = answer

    def __getattr__(self, _command: str) -> Callable[..., Any]:
        return self.answer


# A stand-in for the model cache.
class _Cache:  # pylint: disable=too-few-public-methods
    """Inserts each model as one body."""

    def __init__(self) -> None:
        self.count: int = 0

    def insert(self, _solidcraft: Any, model: Any, _matrix: Any) -> Any:
        """Return one new body for the model."""
        self.count += 1
        return InsertedModel(
            bodies=[f"{model.name}_{self.count}"],
            component=self.count,
            occurrence=self.count,
        )


# A stand-in tooling object that is cached.
class _Tooling(_Fake):
    """A tooling object with one cacheable model."""

    def cacheable(self) -> tuple[Cacheable, ...]:
        """Return its one model."""
        return (Cacheable(name="tool", shape={}, build=lambda _: []),)


# A stand-in part, built in the session.
class _Part:  # pylint: disable=too-few-public-methods
    """A part that builds one body."""

    def model(self, _solidcraft: Any, _point: Point) -> list[str]:
        """Return its body."""
        return ["part_body"]


class TestSetupView(unittest.TestCase):
    """Tests for `SetupView`."""

    def setUp(self) -> None:
        """A view on a fake session, with three tooling items."""
        self.session: _Session = _Session()
        fakes: dict[str, Any] = {
            "vise": _Tooling((0.0, 0.0, 10.0)),
            "parallel A": _Tooling((0.0, 0.0, 5.0)),
            "parallel B": _Tooling((0.0, 0.0, 5.0)),
            "stock": Stock("aluminum_6061", ("4 in", "3 in", "1/2 in")),
            "part": _Part(),
        }
        self.view: SetupView = SetupView(
            cast(Any, self.session), cast(Any, _Cache()), _resolver(fakes)
        )

    @staticmethod
    def assembly(part_x: float = 0.0, *, part: bool = True) -> Assembly:
        """Return the test assembly."""
        items: list[AssemblyItem] = [
            _item("vise", (0.0, 0.0, 0.0)),
            _item("parallel A", (0.0, 4.0, 0.0)),
            _item("parallel B", (0.0, 0.0, 0.0)),
            AssemblyItem(
                kind="stock",
                name="stock",
                call="fake:stock",
                args={},
                location=(0.0, 0.0, 0.0),
                orientation=0,
            ),
        ]
        if part:
            items.append(
                AssemblyItem(
                    kind="part",
                    name="part",
                    call="fake:part",
                    args={},
                    location=(part_x, 0.0, 0.0),
                    orientation=0,
                )
            )
        return Assembly(items)

    def test_first_show(self) -> None:
        """The first show draws everything."""
        self.view.show(self.assembly())
        self.assertEqual(self.view.counts, (5, 0, 0))
        calls: list[tuple[str, Any]] = list(self.session.calls)
        names: list[str] = [name for name, _ in calls]
        self.assertEqual(names.count("sketch.line3d"), 6)
        self.assertEqual(names.count("sketch.create"), 1)
        looks: list[Any] = [
            arguments
            for name, arguments in calls
            if name == "appearance.assign"
        ]
        self.assertEqual(len(looks), 4)
        part: list[Any] = [
            look for look in looks if look["bodies"] == ["part_body"]
        ]
        self.assertEqual(part[0]["opacity"], 1.0)
        self.assertTrue(
            all(look["opacity"] == 0.35 for look in looks if look not in part)
        )

    def test_same_again(self) -> None:
        """Showing the same assembly again changes nothing."""
        self.view.show(self.assembly())
        self.session.names()
        self.view.show(self.assembly())
        self.assertEqual(self.view.counts, (0, 5, 0))
        self.assertEqual(self.session.names(), [])

    def test_moved(self) -> None:
        """Moving one item removes it and draws it again."""
        self.view.show(self.assembly())
        self.session.names()
        self.view.show(self.assembly(part_x=6.0))
        self.assertEqual(self.view.counts, (1, 4, 1))
        self.assertEqual(
            self.session.names(),
            [
                "solid.remove",
                "document.inspect",
                "solid.move",
                "document.inspect",
                "appearance.assign",
            ],
        )

    def test_dropped(self) -> None:
        """Dropping an item removes only it."""
        self.view.show(self.assembly())
        self.session.names()
        self.view.show(self.assembly(part=False))
        self.assertEqual(self.view.counts, (0, 4, 1))
        self.assertEqual(self.session.names(), ["solid.remove"])

    def test_erase_fails(self) -> None:
        """An item that will not go stays shown; the rest goes on."""
        self.view.show(self.assembly())
        stock_keys = [key for key in self.view.shown if key[0] == "stock"]

        def refuse(**_arguments: Any) -> Any:
            """Refuse, as SolidCraft does when it can not."""
            raise SolidCraftError("timeline.delete", "no", False, False)

        self.session.timeline = cast(Any, _Refusing(refuse))
        with self.assertRaisesRegex(RuntimeError, "not taken out"):
            self.view.show(Assembly(self.assembly().items[:3]))
        self.assertTrue(all(key in self.view.shown for key in stock_keys))
        self.assertEqual(self.view.counts, (0, 3, 1))

    def test_stock_sketch_deleted(self) -> None:
        """A stock outline goes as a whole sketch, by name."""
        self.view.show(self.assembly())
        self.session.names()
        self.view.show(Assembly(self.assembly().items[:3]))
        self.assertIn(
            ("timeline.delete", {"features": ["stock_1"]}),
            self.session.calls,
        )

    def test_keep_outs(self) -> None:
        """Keep-outs come as red see-through boxes, and go when off."""
        items: list[AssemblyItem] = self.assembly().items
        items[0] = replace(items[0], keep_out=((0, 0, 0, 1, 2, 3),))
        assembly: Assembly = Assembly(items)
        self.view.show(assembly)
        self.session.names()
        self.view.keep_outs = True
        self.view.show(assembly)
        self.assertEqual(self.view.counts, (1, 5, 0))
        names: list[str] = self.session.names()
        self.assertEqual(names.count("solid.box"), 1)
        self.assertIn("appearance.assign", names)
        self.assertNotIn("sketch.line3d", names)
        self.view.keep_outs = False
        self.view.show(assembly)
        self.assertEqual(self.view.counts, (0, 5, 1))
        self.assertEqual(self.session.names(), ["solid.remove"])

    def test_hidden(self) -> None:
        """Hidden kinds are hidden after each show, and shown again."""
        items: list[AssemblyItem] = self.assembly().items
        items[0] = replace(items[0], keep_out=((0, 0, 0, 1, 2, 3),))
        assembly: Assembly = Assembly(items)
        self.view.keep_outs = True
        self.view.hidden = {"keep_out"}
        self.view.show(assembly)
        visible = {
            str(args["items"][0]).split("_", maxsplit=1)[0]: args["visible"]
            for _, args in self.session.shown
        }
        self.assertEqual(visible, {"keep": False, "stock": True})
        self.session.shown.clear()
        self.view.hidden = set()
        self.view.apply_hidden()
        self.assertTrue(all(args["visible"] for _, args in self.session.shown))

    def test_origin_and_holders(self) -> None:
        """The origin by its folder, holders by their bands' names."""
        bodies = [{"name": "Holder 3021 band 1"}, {"name": "vise"}]
        self.session.document = cast(
            Any,
            type(
                "_Document",
                (),
                {"inspect": staticmethod(lambda: {"bodies": bodies})},
            )(),
        )
        self.view.hidden = {"origin", "holder"}
        self.view.apply_hidden()
        self.assertEqual(
            [args for _, args in self.session.shown],
            [
                {"visible": False, "folder": "origin"},
                {"visible": False, "items": ["Holder 3021 band 1"]},
            ],
        )

        # Shown again once each; then nothing more is sent.
        self.session.shown.clear()
        self.view.hidden = set()
        self.view.apply_hidden()
        self.assertEqual(len(self.session.shown), 2)
        self.assertTrue(all(args["visible"] for _, args in self.session.shown))
        self.session.shown.clear()
        self.view.apply_hidden()
        self.assertEqual(self.session.shown, [])

    def test_keep_out_prisms(self) -> None:
        """A box from the origin, turned once and placed."""
        here: PlacedItem = PlacedItem(
            replace(self.assembly().items[0], keep_out=((0, 0, 0, 1, 2, 3),)),
            10.0,
            20.0,
            30.0,
            1,
        )
        self.assertEqual(
            keep_out_prisms(here, (0.0, 0.0, 0.0)),
            [((8.0, 20.0, 30.0), (10.0, 21.0, 33.0))],
        )

    def test_operator_view(self) -> None:
        """The first show looks at the stock from the front, once."""
        self.view.show(self.assembly())
        views = [
            args for name, args in self.session.calls if name == "view.apply"
        ]
        self.assertEqual(len(views), 1)
        camera = views[0]["camera"]
        self.assertEqual((camera["yaw"], camera["pitch"]), (0.0, 0.35))
        self.assertGreater(camera["fov"], 0.0)
        self.session.names()
        self.view.show(self.assembly(part_x=6.0))
        self.assertNotIn("view.apply", self.session.names())

    def test_steps(self) -> None:
        """Showing items 1..N, N growing, adds one item at a time."""
        items: list[AssemblyItem] = self.assembly().items
        count: int
        for count in range(1, len(items) + 1):
            self.view.show(Assembly(items[:count]))
            self.assertEqual(self.view.counts, (1, count - 1, 0))
        self.view.show(Assembly(items))
        self.assertEqual(self.view.counts, (0, len(items), 0))

    def test_demo_part(self) -> None:
        """The demonstration's part item reaches `DemoPart.model()`."""
        built: list[tuple[DemoPart, Point]] = []

        def model(part: DemoPart, _solidcraft: Any, point: Point) -> Any:
            """Record the part and where it goes."""
            built.append((part, point))
            return ["plate"]

        def resolver(item: AssemblyItem) -> Any:
            """Fake the tooling; resolve the stock and the part."""
            if item.kind == "tooling":
                return _Tooling((0.0, 0.0, 0.0))
            return resolve(item)

        view: SetupView = SetupView(
            cast(Any, self.session), cast(Any, _Cache()), resolver
        )
        with patch.object(DemoPart, "model", model):
            view.show(demo_assembly())
        self.assertEqual(len(built), 1)
        part: DemoPart = built[0][0]
        self.assertEqual(part.material, "6061 aluminum")
        self.assertAlmostEqual(part.thickness, 12.7)
        self.assertIn(
            ("appearance.assign", {"bodies": ["plate"], "opacity": 1.0}),
            self.session.calls,
        )

    def test_twins(self) -> None:
        """Two items alike in every way are both kept apart."""
        twin: PlacedItem = PlacedItem(
            _item("twin", (0.0, 0.0, 0.0)), 1.0, 2.0, 3.0, 0
        )
        keys: list[Any] = display_keys([twin, twin])
        self.assertEqual(len(set(keys)), 2)


# A live check needs `SCRAFTCAM_SOLIDCRAFT=1` and `solidcraft-cli`.
CLI: str | None = shutil.which("solidcraft-cli")
LIVE: bool = os.environ.get("SCRAFTCAM_SOLIDCRAFT") == "1" and bool(CLI)


@unittest.skipUnless(LIVE, "needs SCRAFTCAM_SOLIDCRAFT=1 and solidcraft-cli")
class TestLive(unittest.TestCase):
    """The demonstration's setup, shown in a headless SolidCraft."""

    # One live run, with its parts named for what they check.
    # pylint: disable-next=too-many-locals
    def test_demo_setup(self) -> None:
        """Bodies appear, in the stock, and a second show does nothing."""
        assert CLI is not None
        assembly: Assembly = demo_assembly()
        with (
            tempfile.TemporaryDirectory() as directory,
            HeadlessTransport(CLI, (directory,)) as transport,
            # The chamfers take minutes to build and add nothing here.
            patch.dict(GridPlate.REGISTRY.items, {"grid_plate": FLAT_PLATE}),
        ):
            solidcraft: PyBind = PyBind(transport)
            view: SetupView = SetupView(solidcraft)
            view.show(assembly)
            first: tuple[int, int, int] = view.counts
            bodies: list[str] = [
                body for shown in view.shown.values() for body in shown.bodies
            ]
            reply: Any = cast(Any, solidcraft.model.faces(body="Plate"))
            view.show(assembly)
            second: tuple[int, int, int] = view.counts

        # Every item was drawn, and the second show kept them all.
        count: int = len(assembly.items)
        self.assertEqual(first, (count, 0, 0))
        self.assertEqual(second, (0, count, 0))
        self.assertIn("Plate", bodies)

        # The part's face centroids lie inside the stock's box.
        placed: list[PlacedItem] = place(assembly, resolve)
        stock_at: PlacedItem = next(
            here for here in placed if here.item.kind == "stock"
        )
        corners: list[list[float]] = [
            point
            for loop in box_edges(
                stock_at, cast(Stock, resolve(stock_at.item))
            )
            for point in loop
        ]
        axis: int
        for axis in range(3):
            low: float = min(point[axis] for point in corners) - 1e-6
            high: float = max(point[axis] for point in corners) + 1e-6
            values: list[float] = [
                face["centroid"][axis] for face in reply["faces"]
            ]
            self.assertGreaterEqual(min(values), low, f"axis {axis}")
            self.assertLessEqual(max(values), high, f"axis {axis}")


if __name__ == "__main__":
    unittest.main()
