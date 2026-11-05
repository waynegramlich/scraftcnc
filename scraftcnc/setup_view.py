"""Where each item of a setup goes, and drawing it in SolidCraft.

`place()` turns an `SCAssembly`'s relative locations into absolute
positions in the setup frame (millimeters), with no SolidCraft.  The
first item's location is absolute.  Each later item's location is the
center of its bottom, measured from the origin handed up by the item
below, in the setup frame, not turned (#32).  An item hands up its
absolute position plus its object's `origin(turns)`; parallels hand up
nothing new, so the item above them is placed from the origin below
the parallels (the vise's, #29).

`SCSetupView` draws the placed items in a SolidCraft session, and on
the next assembly changes only the items that differ (#68).
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from .assembly import SCAssembly, SCItem, SCStock, resolve
from .model_cache import (
    SCCacheable,
    SCInserted,
    SCModelCache,
    item_key,
    keyed_by_item,
    placement_matrix,
)
from .pybind.scraftpybind import JSON, SCPyBind, SCSolidCraftError
from .tooling.mount import SCParallelLayer
from .tooling.tools import Point, quarter_turn

# What builds an item's object from it (`assembly.resolve()`).
Resolver = Callable[[SCItem], Any]

# How opaque each kind of item is unless it says otherwise (#13a).
OPACITY: dict[str, float] = {"tooling": 0.35, "stock": 0.35, "part": 1.0}

# What tells one shown item from another: its cache key, where it is,
# how it looks, and which copy of the same it is.
DisplayKey = tuple[str, str, float, float, float, int, str, float, int]

# How many places a position is rounded to in a display key (mm).
PLACES: int = 6


# Class `SCPlaced`:
@dataclass(frozen=True, slots=True)
class SCPlaced:
    """An item of a setup, placed in the setup frame.

    Attributes:
    * `item` (`SCItem`): The item.
    * `x` (`float`): The X of the center of its bottom (millimeters).
    * `y` (`float`): The Y of the center of its bottom (millimeters).
    * `z` (`float`): The Z of the center of its bottom (millimeters).
    * `turns` (`int`): Quarter turns counterclockwise about Z (0-3).

    Constructor:
    * `SCPlaced(item, x, y, z, turns)`
    """

    # Constructor arguments:
    item: SCItem = field(init=True)
    x: float = field(init=True)
    y: float = field(init=True)
    z: float = field(init=True)
    turns: int = field(init=True)


# Function `place()`:
def place(
    assembly: SCAssembly, resolver: Resolver = resolve
) -> list[SCPlaced]:
    """Place every item of an assembly in the setup frame.

    Only items with an item above them are resolved (for their
    `origin()`), so the top item (the part) is never built.

    Arguments:
    * `assembly` (`SCAssembly`): The items, bottom first.
    * `resolver` (`Resolver`):
      What builds an item's object (`assembly.resolve()` by default).

    Returns:
    * (`list[SCPlaced]`): The items, in the same order, placed.

    Raises:
    * `ValueError`: If an item can not be built (from `resolver`).
    """
    placed: list[SCPlaced] = []
    origin: Point = (0.0, 0.0, 0.0)
    items: list[SCItem] = assembly.items
    index: int
    item: SCItem
    for index, item in enumerate(items):
        # The center of its bottom, from the origin handed up.
        dx, dy, dz = item.location
        here: SCPlaced = SCPlaced(
            item=item,
            x=origin[0] + dx,
            y=origin[1] + dy,
            z=origin[2] + dz,
            turns=item.orientation % 4,
        )
        placed.append(here)

        # The origin handed up, unless this is the top or a parallel.
        if index + 1 < len(items):
            thing: Any = resolver(item)
            if not isinstance(thing, SCParallelLayer):
                offset: Point = thing.origin(here.turns)
                origin = (
                    here.x + offset[0],
                    here.y + offset[1],
                    here.z + offset[2],
                )
    return placed


# The operator's view (#75): radians above level, millimeters from
# the stock's top middle, and the field of view (radians; perspective).
VIEW_PITCH: float = 0.35
VIEW_DISTANCE: float = 700.0
VIEW_FOV: float = 0.7

# What each kind of item's handed-up origin is (by class name), for
# the operator's list (`T.emsagc~5.2` #36, #38).
ORIGIN_NAMES: dict[str, str] = {
    "SCTableLayer": "top upper left",
    "SCMachineViseLayer": "fixed jaw top left inner",
    "SCGridPlate": "top left outer",
    "SCPlate": "top left outer",
    "SCStock": "top left outer",
}


# Function `named_origins()`:
def named_origins(
    assembly: SCAssembly, resolver: Resolver = resolve
) -> list[tuple[str, Point]]:
    """Return the setup's named origins, in work coordinates.

    The setup frame is the work frame: its zero is the G-code's work
    zero.  Each item but the top one (the part) and the parallels
    hands up an origin; the work zero itself comes last.  Names show
    underscores as spaces (#58).

    Arguments:
    * `assembly` (`SCAssembly`): The items, bottom first.
    * `resolver` (`Resolver`): What builds an item's object.

    Returns:
    * (`list[tuple[str, Point]]`): Each origin's name and point
      (millimeters).

    Raises:
    * `ValueError`: If an item can not be built (from `resolver`).
    """
    origins: list[tuple[str, Point]] = []
    here: SCPlaced
    for here in place(assembly, resolver)[:-1]:
        thing: Any = resolver(here.item)
        if isinstance(thing, SCParallelLayer):
            continue
        offset: Point = thing.origin(here.turns)
        what: str = ORIGIN_NAMES.get(type(thing).__name__, "origin")
        name: str = here.item.name.replace("_", " ")
        origins.append(
            (
                f"{name}: {what}",
                (here.x + offset[0], here.y + offset[1], here.z + offset[2]),
            )
        )
    origins.append(("work zero", (0.0, 0.0, 0.0)))
    return origins


# Class `SCShown`:
@dataclass(slots=True)
class SCShown:
    """What one item put in the SolidCraft design.

    Attributes:
    * `bodies` (`list[str]`): The names of its bodies.
    * `sketches` (`list[str]`): Its sketches (timeline names or ids),
      deleted whole with what depends on them.

    Constructor:
    * `SCShown(bodies, sketches)`
    """

    # Constructor arguments:
    bodies: list[str] = field(init=True)
    sketches: list[str] = field(init=True)


# Function `display_keys()`:
def display_keys(placed: list[SCPlaced]) -> list[DisplayKey]:
    """Return what tells each placed item from the others.

    Two items alike in every way (cache key, place, looks) are told
    apart by a count, so both are shown.

    Arguments:
    * `placed` (`list[SCPlaced]`): The placed items.

    Returns:
    * (`list[DisplayKey]`): One key per item, in the same order.
    """
    seen: Counter[tuple[Any, ...]] = Counter()
    keys: list[DisplayKey] = []
    here: SCPlaced
    for here in placed:
        item: SCItem = here.item
        base: tuple[str, str, float, float, float, int, str, float] = (
            item.kind,
            item_key(item),
            round(here.x, PLACES),
            round(here.y, PLACES),
            round(here.z, PLACES),
            here.turns,
            item.color,
            item.transparency,
        )
        keys.append((*base, seen[base]))
        seen[base] += 1
    return keys


# Function `opacity()`:
def opacity(item: SCItem) -> float:
    """Return how opaque an item is drawn.

    A `transparency` of 0.0 (the default) means the kind's default
    (`OPACITY`); anything more overrides it.

    Arguments:
    * `item` (`SCItem`): The item.

    Returns:
    * (`float`): From 0.0 (clear) to 1.0 (solid).
    """
    if item.transparency > 0.0:
        return 1.0 - item.transparency
    return OPACITY.get(item.kind, 1.0)


# Function `box_edges()`:
def prism_edges(low: Point, high: Point) -> list[list[list[float]]]:
    """Return the edges of an upright box as 3D polylines.

    Arguments:
    * `low` (`Point`): Its corner with the smallest X, Y and Z (mm).
    * `high` (`Point`): Its corner with the largest X, Y and Z (mm).

    Returns:
    * (`list[list[list[float]]]`): Two closed loops of 5 points
      (bottom, top) and 4 vertical edges of 2 points (millimeters).
    """
    corners: list[tuple[float, float]] = [
        (low[0], low[1]),
        (high[0], low[1]),
        (high[0], high[1]),
        (low[0], high[1]),
    ]
    edges: list[list[list[float]]] = [
        [[x, y, z] for x, y in corners + corners[:1]]
        for z in (low[2], high[2])
    ]
    edges.extend([[x, y, low[2]], [x, y, high[2]]] for x, y in corners)
    return edges


# Function `keep_out_prisms()`:
def keep_out_prisms(
    here: SCPlaced, origin: Point
) -> list[tuple[Point, Point]]:
    """Return an item's keep-out boxes in the setup (work) frame.

    Arguments:
    * `here` (`SCPlaced`): The item, placed.
    * `origin` (`Point`): Its unturned origin (`origin(0)`), from the
      center of its bottom, which its boxes are measured from.

    Returns:
    * (`list[tuple[Point, Point]]`): Each box's low and high corners
      (millimeters).
    """
    prisms: list[tuple[Point, Point]] = []
    box: tuple[float, ...]
    for box in here.item.keep_out:
        corners: list[Point] = [
            quarter_turn(
                (origin[0] + x, origin[1] + y, origin[2] + z), here.turns
            )
            for x in (box[0], box[3])
            for y in (box[1], box[4])
            for z in (box[2], box[5])
        ]
        prisms.append(
            (
                (
                    here.x + min(c[0] for c in corners),
                    here.y + min(c[1] for c in corners),
                    here.z + min(c[2] for c in corners),
                ),
                (
                    here.x + max(c[0] for c in corners),
                    here.y + max(c[1] for c in corners),
                    here.z + max(c[2] for c in corners),
                ),
            )
        )
    return prisms


# Function `box_edges()`:
def box_edges(here: SCPlaced, stock: SCStock) -> list[list[list[float]]]:
    """Return the edges of a stock's box as 3D polylines.

    Arguments:
    * `here` (`SCPlaced`): Where the stock is (center of its bottom).
    * `stock` (`SCStock`): The stock.

    Returns:
    * (`list[list[list[float]]]`): Two closed loops of 5 points
      (bottom, top) and 4 vertical edges of 2 points (millimeters).
    """
    # A quarter turn swaps the X and Y sizes.
    dx: float = stock.dx if here.turns % 2 == 0 else stock.dy
    dy: float = stock.dy if here.turns % 2 == 0 else stock.dx
    return prism_edges(
        (here.x - dx / 2, here.y - dy / 2, here.z),
        (here.x + dx / 2, here.y + dy / 2, here.z + stock.dz),
    )


# Class `SCSetupView`:
# Its state is what is shown, how far, and how; all of it is needed.
@dataclass(slots=True)
class SCSetupView:  # pylint: disable=too-many-instance-attributes
    """A setup shown in a SolidCraft session, changed only where needed.

    Attributes:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `cache` (`SCModelCache | None`):
      Where models are kept between runs, or `None` to build them.
    * `resolver` (`Resolver`): What builds an item's object.
    * `keep_outs` (`bool`): True to draw the items' keep-outs too.
    * `viewed` (`bool`): True once the operator's view is set.
    * `progress` (`tuple[int, int]`): How many of the last `show()`'s
      changes are done, of how many (read by other threads).
    * `counts` (`tuple[int, int, int]`): How many items the last
      `show()` added, kept and removed.
    * `shown` (`dict[DisplayKey, SCShown]`): What is in the design.
    * `sketches` (`int`): How many stock sketches have been made.

    Constructor:
    * `SCSetupView(solidcraft, cache, resolver)`
    """

    # Constructor arguments:
    solidcraft: SCPyBind = field(init=True)
    cache: SCModelCache | None = field(init=True, default=None)
    resolver: Resolver = field(init=True, default=resolve)

    # Remaining attributes (alphabetized):
    counts: tuple[int, int, int] = field(init=False, default=(0, 0, 0))
    keep_outs: bool = field(init=False, default=False)
    progress: tuple[int, int] = field(init=False, default=(0, 0))
    viewed: bool = field(init=False, default=False)
    shown: dict[DisplayKey, SCShown] = field(init=False, default_factory=dict)
    sketches: int = field(init=False, default=0)

    # Method `SCSetupView.show()`:
    def show(self, assembly: SCAssembly) -> None:
        """Show an assembly, changing only what differs from the last.

        Arguments:
        * `assembly` (`SCAssembly`): The items, bottom first.

        Raises:
        * `ValueError`: If an item can not be built (from `resolver`).
        * `RuntimeError`: If an item could not be taken out; it stays
          in `shown`, and the rest is still shown.
        """
        placed: list[SCPlaced] = place(assembly, self.resolver)
        wanted: dict[DisplayKey, SCPlaced] = dict(
            zip(display_keys(placed), placed, strict=True)
        )

        # Each item's keep-outs are one more thing shown, when asked.
        if self.keep_outs:
            wanted.update(
                {
                    ("keep_out", *key[1:]): here
                    for key, here in list(wanted.items())
                    if here.item.keep_out
                }
            )
        needed: set[DisplayKey] = set(wanted)
        current: set[DisplayKey] = set(self.shown)

        # Take away what is no longer wanted, then draw what is new.
        key: DisplayKey
        failed: list[str] = []
        total: int = len(current - needed) + len(needed - current)
        done: int = 0
        self.progress = (done, total)
        for key in current - needed:
            try:
                self.erase(self.shown[key])
                del self.shown[key]
            except SCSolidCraftError as error:
                failed.append(str(error))
            done += 1
            self.progress = (done, total)
        for key in needed - current:
            self.shown[key] = (
                self.draw_keep_out(wanted[key])
                if key[0] == "keep_out"
                else self.draw(wanted[key])
            )
            done += 1
            self.progress = (done, total)
        self.counts = (
            len(needed - current),
            len(needed & current),
            len(current - needed) - len(failed),
        )
        if not self.viewed and self.shown:
            self.operator_view(placed)
        if failed:
            raise RuntimeError(f"not taken out: {'; '.join(failed)}")

    # Method `SCSetupView.operator_view()`:
    def operator_view(self, placed: list[SCPlaced]) -> None:
        """Look at the stock as the operator does, once (#75).

        From the front (-Y), `VIEW_PITCH` above level, in perspective
        (`VIEW_FOV`), `VIEW_DISTANCE` from the stock's top middle (or
        SolidCraft's front view, framing everything, with no stock).

        Arguments:
        * `placed` (`list[SCPlaced]`): The items shown, placed.
        """
        self.viewed = True
        stocks: list[SCPlaced] = [
            here for here in placed if here.item.kind == "stock"
        ]
        if not stocks:
            self.solidcraft.view.apply(view="front")
            return
        here: SCPlaced = stocks[0]
        stock: Any = self.resolver(here.item)
        self.solidcraft.view.apply(
            camera={
                "target": [here.x, here.y, here.z + float(stock.dz)],
                "yaw": 0.0,
                "pitch": VIEW_PITCH,
                "distance": VIEW_DISTANCE,
                "fov": VIEW_FOV,
            }
        )

    # Method `SCSetupView.erase()`:
    def erase(self, shown: SCShown) -> None:
        """Take one item out of the design.

        Arguments:
        * `shown` (`SCShown`): What the item put there.
        """
        if shown.bodies:
            self.solidcraft.solid.remove(bodies=cast(JSON, shown.bodies))
            shown.bodies = []
        if shown.sketches:
            self.solidcraft.timeline.delete(
                features=cast(JSON, shown.sketches)
            )
            shown.sketches = []

    # Method `SCSetupView.draw_keep_out()`:
    def draw_keep_out(self, here: SCPlaced) -> SCShown:
        """Draw an item's keep-outs as wire boxes, in a sketch of their own.

        Arguments:
        * `here` (`SCPlaced`): The item, placed.

        Returns:
        * (`SCShown`): The sketch.
        """
        origin: Point = self.resolver(here.item).origin(0)
        self.sketches += 1
        name: str = f"keep_out_{self.sketches}"
        self.solidcraft.sketch.create(plane="XY", name=name)
        self.solidcraft.sketch.options(sketch_3d=True)
        low: Point
        high: Point
        for low, high in keep_out_prisms(here, origin):
            points: list[list[float]]
            for points in prism_edges(low, high):
                self.solidcraft.sketch.line3d(points=cast(JSON, points))
        self.solidcraft.sketch.finish()
        return SCShown(bodies=[], sketches=[name])

    # Method `SCSetupView.draw()`:
    def draw(self, here: SCPlaced) -> SCShown:
        """Put one placed item in the design.

        Stock is a wire outline (#45); tooling and parts are bodies,
        from the cache when they can be.

        Arguments:
        * `here` (`SCPlaced`): The item, placed.

        Returns:
        * (`SCShown`): What it put there.
        """
        thing: Any = self.resolver(here.item)
        if isinstance(thing, SCStock):
            return SCShown(bodies=[], sketches=[self.outline(here, thing)])
        sketches: list[str] = []
        bodies: list[str] | None = self.inserted(here, thing)
        if bodies is None:
            # What it builds from sketches, they go with it.
            before: set[str] = self.sketch_ids()
            bodies = self.built(here, thing)
            sketches = sorted(self.sketch_ids() - before)
        if bodies:
            look: dict[str, JSON] = {"opacity": opacity(here.item)}
            if here.item.color:
                look["color"] = here.item.color
            self.solidcraft.appearance.assign(
                bodies=cast(JSON, bodies), **look
            )
        return SCShown(bodies=bodies, sketches=sketches)

    # Method `SCSetupView.sketch_ids()`:
    def sketch_ids(self) -> set[str]:
        """Return the ids of every sketch in the design.

        Returns:
        * (`set[str]`): The ids (as text).
        """
        inspected: Any = self.solidcraft.document.inspect()
        sketches: Any = (
            inspected.get("sketches", [])
            if isinstance(inspected, dict)
            else []
        )
        return {str(sketch["id"]) for sketch in sketches}

    # Method `SCSetupView.outline()`:
    def outline(self, here: SCPlaced, stock: SCStock) -> str:
        """Draw a stock as the 12 edges of its box, in a 3D sketch.

        Arguments:
        * `here` (`SCPlaced`): Where it is.
        * `stock` (`SCStock`): The stock.

        Returns:
        * (`str`): The sketch's name.
        """
        self.sketches += 1
        self.solidcraft.sketch.create(
            plane="XY", name=f"stock_{self.sketches}"
        )
        self.solidcraft.sketch.options(sketch_3d=True)
        points: list[list[float]]
        for points in box_edges(here, stock):
            self.solidcraft.sketch.line3d(points=cast(JSON, points))
        self.solidcraft.sketch.finish()
        return f"stock_{self.sketches}"

    # Method `SCSetupView.inserted()`:
    def inserted(self, here: SCPlaced, thing: Any) -> list[str] | None:
        """Put an item's models in from the cache.

        Arguments:
        * `here` (`SCPlaced`): Where it goes.
        * `thing` (`Any`): Its object (with `cacheable()`, if cached).

        Returns:
        * (`list[str] | None`): The names of its bodies, or `None` if it
          must be built instead.
        """
        if self.cache is None or not hasattr(thing, "cacheable"):
            return None
        models: tuple[SCCacheable, ...] = thing.cacheable()
        if not models:
            return None
        bodies: list[str] = []
        model: SCCacheable
        for model in models:
            got: SCInserted | None = self.cache.insert(
                self.solidcraft,
                keyed_by_item(model, here.item),
                placement_matrix(
                    here.turns, (here.x, here.y, here.z), model.offset
                ),
            )
            if got is None:
                # What did go in must not be there twice.
                if bodies:
                    self.solidcraft.solid.remove(bodies=cast(JSON, bodies))
                return None
            bodies.extend(got.bodies)
        return bodies

    # Method `SCSetupView.built()`:
    def built(self, here: SCPlaced, thing: Any) -> list[str]:
        """Build an item in the session, as `SCPlacement.model()` does.

        Arguments:
        * `here` (`SCPlaced`): Where it goes.
        * `thing` (`Any`): Its object, with `model(solidcraft, point)`.

        Returns:
        * (`list[str]`): The names of its bodies.
        """
        # SolidCraft turns bodies about the origin, so build it there.
        bodies: list[str] = list(
            thing.model(self.solidcraft, (0.0, 0.0, here.z))
        )
        if here.turns:
            self.solidcraft.solid.move(
                bodies=cast(JSON, bodies),
                axis=(0.0, 0.0, 1.0),
                angle=f"{90 * here.turns} deg",
            )
        if here.x != 0.0 or here.y != 0.0:
            self.solidcraft.solid.move(
                bodies=cast(JSON, bodies), translate=(here.x, here.y, 0.0)
            )
        return bodies
