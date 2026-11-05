"""Stock, and the assembly of everything in one setup (a Mount).

`SCStock` is the raw material, a rectangular prism for now.
`SCAssembly` lists the items of one setup (tooling, stock and the
part) in stacking order, each placed from the origin of the item below
it.  `SCAssembly.to_dict()` and `SCAssembly.from_dict()` turn it into
and out of one ordered `item` list, as TOML's `[[item]]` or JSON.
Lengths are read as strings with units (`"4 in"`, `"3mm"`): a number
with no unit is a count, never a length (#48).  They are kept as
millimeter floats, and written back as strings with units.
"""

import importlib
from dataclasses import dataclass, field
from typing import Any

from .shops import LENGTH, measure
from .tooling.cutter_models import MM_PER_INCH
from .tooling.tools import Point, SCKeepOut, left_corner

# The kinds of item in an assembly, in no particular order.
KINDS: tuple[str, ...] = ("tooling", "stock", "part")

# A keep-out box: low X, Y, Z, then high X, Y, Z (millimeters).
Box = tuple[float, float, float, float, float, float]


# Function `millimeters()`:
def millimeters(value: str | float, what: str) -> float:
    """Return a length in millimeters.

    Arguments:
    * `value` (`str | float`):
      A string with a unit (such as `"1-1/2 in"` or `"3mm"`).  A
      plain number is a count, not a length, so it is an error.
    * `what` (`str`): What the length is, for the error message.

    Returns:
    * (`float`): The length (millimeters).

    Raises:
    * `TypeError`: If it is not a string.
    * `ValueError`: If it is not a length.
    """
    # A number with no unit is a count, never a length (#48).
    if not isinstance(value, str):
        raise TypeError(f"{what}: {value!r} is not a length with a unit")
    try:
        return measure(value, LENGTH) * MM_PER_INCH
    except ValueError as error:
        raise ValueError(f"{what}: {error}") from error


# Function `length_text()`:
def length_text(mm: float) -> str:
    """Return a length as a string with a unit.

    Inches (to 4 places) when that is exact, else millimeters.

    Arguments:
    * `mm` (`float`): The length (millimeters).

    Returns:
    * (`str`): Such as `"1.5 in"` or `"3.25 mm"`.
    """
    inches: float = round(mm / MM_PER_INCH, 4)
    if abs(inches * MM_PER_INCH - mm) < 1e-9:
        return f"{inches:.4f}".rstrip("0").rstrip(".") + " in"
    return f"{round(mm, 4):.4f}".rstrip("0").rstrip(".") + " mm"


# Function `lengths_text()`:
def lengths_text(lengths: tuple[float, ...]) -> str:
    """Return lengths as one string with one unit, such as `"0 1.5 in"`.

    Inches (to 4 places) when every one is exact, else millimeters.

    Arguments:
    * `lengths` (`tuple[float, ...]`): The lengths (millimeters).

    Returns:
    * (`str`): The numbers, then the unit.
    """
    texts: list[str] = [length_text(mm) for mm in lengths]
    if all(text.endswith(" in") for text in texts):
        return " ".join(text[:-3] for text in texts) + " in"
    return (
        " ".join(
            f"{round(mm, 4):.4f}".rstrip("0").rstrip(".") for mm in lengths
        )
        + " mm"
    )


# Class `SCStock`:
@dataclass(frozen=True, slots=True)
class SCStock:
    """Raw material: a rectangular prism (cylinders and tubes later).

    Its frame matches `tooling.mount.SCLayer`: points are from the
    center of its bottom.  It has no SolidCraft model yet, so it does
    not have `SCLayer`'s `model()` or `cacheable()`.

    Attributes:
    * `material` (`str`): A short name, such as `"aluminum_6061"`.
    * `size` (`tuple[str | float, str | float, str | float]`):
      Its X, Y and Z sizes, as given.
    * `dx` (`float`): Its X size (millimeters).
    * `dy` (`float`): Its Y size (millimeters).
    * `dz` (`float`): Its Z size, its thickness (millimeters).

    Constructor:
    * `SCStock(material, size)`
    """

    # Constructor arguments:
    material: str = field(init=True)
    size: tuple[str | float, str | float, str | float] = field(init=True)

    # Sizes in millimeters (alphabetized):
    dx: float = field(init=False, default=0.0)
    dy: float = field(init=False, default=0.0)
    dz: float = field(init=False, default=0.0)

    # Method `SCStock.__post_init__()`:
    def __post_init__(self) -> None:
        """Check the arguments and work out the sizes.

        Raises:
        * `ValueError`: If the material is empty, or a size is not a
          positive length.
        """
        if not self.material:
            raise ValueError(f"{self.material=} must be a non-empty name")
        if len(self.size) != 3:
            raise ValueError(f"{self.size=} must have X, Y and Z")
        axis: str
        value: str | float
        sizes: list[float] = []
        for axis, value in zip("xyz", self.size, strict=True):
            size: float = millimeters(value, f"stock size {axis}")
            if size <= 0.0:
                raise ValueError(f"stock size {axis} {value!r} must be > 0")
            sizes.append(size)

        # The dataclass is frozen, so set the sizes past it.
        object.__setattr__(self, "dx", sizes[0])
        object.__setattr__(self, "dy", sizes[1])
        object.__setattr__(self, "dz", sizes[2])

    # Method `SCStock.name()`:
    @property
    def name(self) -> str:
        """Return what the stock is."""
        return (
            f"{self.material} stock {self.dx:g} x {self.dy:g} x {self.dz:g} mm"
        )

    # Method `SCStock.seat()`:
    def seat(self) -> Point:
        """Return where the next layer stands: the middle of its top.

        Returns:
        * (`Point`): From the center of its bottom (millimeters).
        """
        return (0.0, 0.0, self.dz)

    # Method `SCStock.origin()`:
    def origin(self, turns: int = 0) -> Point:
        """Return the point handed up to the next item.

        It is the top, left (smallest X), outer corner, once the stock
        is turned.  "Outer" is taken to be the smallest Y, the side
        facing the operator.

        Arguments:
        * `turns` (`int`): The stock's quarter turns, counterclockwise.

        Returns:
        * (`Point`): From the center of its bottom, turned (millimeters).
        """
        x: float = self.dx / 2.0
        y: float = self.dy / 2.0
        corners: list[Point] = [
            (sx * x, sy * y, self.dz) for sx in (-1, 1) for sy in (-1, 1)
        ]
        return left_corner(corners, turns)

    # Method `SCStock.keep_out()`:
    def keep_out(self, _center: Point) -> SCKeepOut:
        """Return the regions a tool must not enter: none, for material.

        Arguments:
        * `_center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`SCKeepOut`): No regions.
        """
        return SCKeepOut()


# Function `keep_out_boxes()`:
def keep_out_boxes(thing: Any) -> tuple[Box, ...]:
    """Return an item's keep-out boxes, as an item's `keep_out` holds them.

    Each is low X, Y, Z then high X, Y, Z (millimeters), measured from
    the item's origin (`origin(0)`, the point it hands up), in its own
    unturned frame.  Only prisms: a keep-out cylinder is left out.

    Arguments:
    * `thing` (`Any`): The item's object, with `keep_out(center)` and
      `origin(turns)`.

    Returns:
    * (`tuple[Box, ...]`): The boxes.
    """
    keep_out: SCKeepOut = thing.keep_out((0.0, 0.0, 0.0))
    ox, oy, oz = thing.origin(0)
    return tuple(
        (
            prism.low[0] - ox,
            prism.low[1] - oy,
            prism.low[2] - oz,
            prism.high[0] - ox,
            prism.high[1] - oy,
            prism.high[2] - oz,
        )
        for prism in keep_out.prisms
    )


# Class `SCItem`:
# Ten fields, one per key of an item table:
@dataclass(frozen=True, slots=True)
class SCItem:  # pylint: disable=too-many-instance-attributes
    """One item of an assembly: tooling, stock or the part.

    Attributes:
    * `kind` (`str`): `"tooling"`, `"stock"` or `"part"`.
    * `name` (`str`): Its name, unique in the assembly.
    * `call` (`str`):
      What builds it: `"module:Class.method"` or `"module:function"`.
    * `args` (`dict[str, Any]`): The arguments of `call` (hashed).
    * `location` (`Point`):
      Where it goes, from the origin of the item below (millimeters).
    * `orientation` (`int`):
      Quarter turns counterclockwise about Z (0 to 3): the item's +X
      axis points to +X at 0, +Y at 1, -X at 2 and -Y at 3 (#46).
    * `color` (`str`): Its color (such as `"#c0c0c0"`), or `""`.
    * `transparency` (`float`): From 0.0 (solid) to 1.0 (clear).
    * `note` (`str`): A note for the operator, or `""`.
    * `keep_out` (`tuple[Box, ...]`):
      Boxes a tool must not enter (millimeters, from its origin).

    Constructor:
    * `SCItem(kind, name, call, args, location, orientation, color,
      transparency, note, keep_out)`
    """

    # Constructor arguments:
    kind: str = field(init=True)
    name: str = field(init=True)
    call: str = field(init=True)
    args: dict[str, Any] = field(init=True)
    location: Point = field(init=True, default=(0.0, 0.0, 0.0))
    orientation: int = field(init=True, default=0)
    color: str = field(init=True, default="")
    transparency: float = field(init=True, default=0.0)
    note: str = field(init=True, default="")
    keep_out: tuple[Box, ...] = field(init=True, default=())

    # Method `SCItem.__post_init__()`:
    def __post_init__(self) -> None:
        """Check the arguments.

        Raises:
        * `TypeError`: If `args` is not a table.
        * `ValueError`: If one is wrong (the message names the item).
        """
        where: str = f"item {self.name!r}"
        if not self.name:
            raise ValueError(f"item {self.name!r}: name must not be empty")
        if self.kind not in KINDS:
            raise ValueError(f"{where}: kind {self.kind!r} not in {KINDS}")
        if not _call_ok(self.call):
            raise ValueError(
                f"{where}: call {self.call!r} is not "
                '"module:Class.method" or "module:function"'
            )
        if not isinstance(self.args, dict):
            raise TypeError(f"{where}: args must be a table")
        if isinstance(self.orientation, bool) or self.orientation not in (
            0,
            1,
            2,
            3,
        ):
            raise ValueError(
                f"{where}: orientation {self.orientation!r} is not 0 to 3"
            )
        if not 0.0 <= self.transparency <= 1.0:
            raise ValueError(
                f"{where}: transparency {self.transparency!r} "
                "is not 0.0 to 1.0"
            )
        box: Box
        for box in self.keep_out:
            if not all(box[axis] < box[axis + 3] for axis in range(3)):
                raise ValueError(f"{where}: keep_out {box!r} is empty")

    # Method `SCItem.to_dict()`:
    def to_dict(self) -> dict[str, Any]:
        """Return the item as a table (TOML or JSON).

        Returns:
        * (`dict[str, Any]`):
          The item; empty optional fields are left out.
        """
        table: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "call": self.call,
            "args": dict(self.args),
            "location": [length_text(mm) for mm in self.location],
            "orientation": self.orientation,
        }
        if self.color:
            table["color"] = self.color
        if self.transparency:
            table["transparency"] = self.transparency
        if self.note:
            table["note"] = self.note
        if self.keep_out:
            table["keep_out"] = [lengths_text(box) for box in self.keep_out]
        return table

    # Method `SCItem.from_dict()`:
    @staticmethod
    def from_dict(table: dict[str, Any], index: int) -> "SCItem":
        """Return an item read from a table.

        Arguments:
        * `table` (`dict[str, Any]`): The item, from TOML or JSON.
        * `index` (`int`): Its place in the list, for error messages.

        Returns:
        * (`SCItem`): The item.

        Raises:
        * `TypeError`: If it is not a table.
        * `ValueError`: If it is wrong (the message names the item).
        """
        if not isinstance(table, dict):
            raise TypeError(f"item {index}: is not a table")
        name: Any = table.get("name", "")
        where: str = f"item {index} ({name!r})"
        known: set[str] = {
            "kind",
            "name",
            "call",
            "args",
            "location",
            "orientation",
            "color",
            "transparency",
            "note",
            "keep_out",
        }
        unknown: list[str] = sorted(set(table) - known)
        if unknown:
            raise ValueError(f"{where}: unknown keys {unknown}")
        missing: list[str] = [
            key for key in ("kind", "name", "call") if key not in table
        ]
        if missing:
            raise ValueError(f"{where}: missing keys {missing}")
        try:
            location: Point = _point(
                table.get("location", ("0 in", "0 in", "0 in"))
            )
            boxes: tuple[Box, ...] = tuple(
                _box(box) for box in _list(table.get("keep_out", []))
            )
            transparency: Any = table.get("transparency", 0.0)
            if isinstance(transparency, bool) or not isinstance(
                transparency, (int, float)
            ):
                raise TypeError(f"transparency {transparency!r} not a number")
            return SCItem(
                kind=table["kind"],
                name=name,
                call=table["call"],
                args=table.get("args", {}),
                location=location,
                orientation=table.get("orientation", 0),
                color=str(table.get("color", "")),
                transparency=float(transparency),
                note=str(table.get("note", "")),
                keep_out=boxes,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"{where}: {error}") from error


# Class `SCAssembly`:
@dataclass(slots=True)
class SCAssembly:
    """The items of one setup (a Mount), in stacking order.

    Attributes:
    * `items` (`list[SCItem]`): The items, bottom first.

    Constructor:
    * `SCAssembly(items)`
    """

    # Constructor arguments:
    items: list[SCItem] = field(init=True, default_factory=list)

    # Method `SCAssembly.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the item names are unique.

        Raises:
        * `ValueError`: If two items have the same name.
        """
        seen: set[str] = set()
        item: SCItem
        for item in self.items:
            if item.name in seen:
                raise ValueError(f"item {item.name!r}: name used twice")
            seen.add(item.name)

    # Method `SCAssembly.to_dict()`:
    def to_dict(self) -> dict[str, Any]:
        """Return the assembly as one ordered `item` list.

        Returns:
        * (`dict[str, Any]`): `{"item": [...]}`, as TOML's `[[item]]`.
        """
        return {"item": [item.to_dict() for item in self.items]}

    # Method `SCAssembly.from_dict()`:
    @staticmethod
    def from_dict(table: dict[str, Any]) -> "SCAssembly":
        """Return an assembly read from a table (TOML or JSON).

        Arguments:
        * `table` (`dict[str, Any]`): A table with an `item` list.

        Returns:
        * (`SCAssembly`): The assembly.

        Raises:
        * `ValueError`: If it is wrong (the message names the item).
        """
        if "item" not in table:
            raise ValueError("assembly: needs an item list")
        try:
            entries: list[Any] = _list(table["item"])
        except TypeError as error:
            raise ValueError(f"assembly: item {error}") from error
        return SCAssembly(
            [
                SCItem.from_dict(entry, index)
                for index, entry in enumerate(entries, start=1)
            ]
        )


# Function `resolve()`:
def resolve(item: SCItem) -> Any:
    """Build an item by calling its `call` with its `args`.

    `call` is `"module:Class.method"` or `"module:function"`: the
    module is imported, then each name after the colon is looked up in
    turn, and the result is called with `**args`.

    Arguments:
    * `item` (`SCItem`): The item.

    Returns:
    * (`Any`): What the call returns (a layer, `SCStock`, ...).

    Raises:
    * `ValueError`: If the call can not be found or fails (the message
      names the item).
    """
    # Find what to call.
    module_name, _, path = item.call.partition(":")
    try:
        target: Any = importlib.import_module(module_name)
        for name in path.split("."):
            target = getattr(target, name)
    except (ImportError, AttributeError) as error:
        raise ValueError(
            f"Item {item.name!r}: can not find {item.call!r}: {error}"
        ) from error

    # Call it.
    try:
        return target(**item.args)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Item {item.name!r}: {item.call}({item.args!r}) failed: {error}"
        ) from error


# Function `_call_ok()`:
def _call_ok(call: object) -> bool:
    """Return whether a call is `module:Class.method` or `module:function`.

    Arguments:
    * `call` (`object`): The call.

    Returns:
    * (`bool`): Whether it has that form.
    """
    if not isinstance(call, str) or call.count(":") != 1:
        return False
    module: str
    rest: str
    module, rest = call.split(":")
    names: list[str] = module.split(".") + rest.split(".")
    return len(rest.split(".")) <= 2 and all(
        name.isidentifier() for name in names
    )


# Function `_list()`:
def _list(value: object) -> list[Any]:
    """Return a value as a list.

    Arguments:
    * `value` (`object`): The value.

    Returns:
    * (`list[Any]`): The value.

    Raises:
    * `TypeError`: If it is not a list.
    """
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{value!r} is not a list")
    return list(value)


# Function `_point()`:
def _point(value: object) -> Point:
    """Return a location from three lengths.

    Arguments:
    * `value` (`object`): Three lengths (strings with units).

    Returns:
    * (`Point`): The location (millimeters).

    Raises:
    * `ValueError`: If it is not three lengths.
    """
    lengths: list[Any] = _list(value)
    if len(lengths) != 3:
        raise ValueError(f"location {value!r} needs 3 lengths")
    return (
        millimeters(lengths[0], "location x"),
        millimeters(lengths[1], "location y"),
        millimeters(lengths[2], "location z"),
    )


# Function `_box()`:
def _box(value: object) -> Box:
    """Return a keep-out box from six lengths.

    Arguments:
    * `value` (`object`): Low X, Y, Z, then high X, Y, Z: one string
      of six numbers and a unit (`"0 0 0 1 2 3 in"`), or six lengths.

    Returns:
    * (`Box`): The box (millimeters).

    Raises:
    * `ValueError`: If it is not six lengths.
    """
    # One string, six numbers and one unit (#82): each gets the unit.
    lengths: list[Any]
    if isinstance(value, str):
        words: list[str] = value.split()
        lengths = [f"{word} {words[-1]}" for word in words[:-1]]
    else:
        lengths = _list(value)
    if len(lengths) != 6:
        raise ValueError(f"keep_out {value!r} needs 6 lengths")
    mm: list[float] = [millimeters(length, "keep_out") for length in lengths]
    return (mm[0], mm[1], mm[2], mm[3], mm[4], mm[5])
