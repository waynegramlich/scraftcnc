#!/usr/bin/env python3
"""Setups: all of the tooling and material on a machine, from JSON.

A `SCSetup` says where everything goes: the location, orientation and
height of each piece of tooling, each chunk of material, and each part
to be made from a chunk.  Everything is given outright, with a unit on
every number, and `SCSetup` reports how it comes out.  There may be many
chunks of material, each becoming a different part, so that they can
all be cut with few tool changes.

In the JSON, `location` is the `[x, y]` of an item's center, `height` is
the Z of its bottom, and `orientation` is how far it is turned about its
center, seen from above: counterclockwise is positive, in quarter turns.
`examples/setup/grid_plate.json` is an example.

```
python3 scsetup.py [FILE] 8080       # A GUI with `--control 8080`.
python3 scsetup.py [FILE] headless   # No window; prints the report.
```
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from mount import (
    SCLayer,
    SCMachineViseLayer,
    SCParallelLayer,
    SCPlate,
    SCTableLayer,
    _inches,
)
from scmodelcache import (
    SCInserted,
    SCModelCache,
    cache_for,
    placement_matrix,
)
from scraftpybind import JSON, DocumentUnitsUnits, SCPyBind, connect
from sctoolmodel import MM_PER_INCH
from shops import ANGLE, LENGTH, grid_plates, measure, read
from tools import (
    GRID_PLATE,
    KURT_D688,
    MIKINI_1610L,
    MILL_TABLES,
    PARALLELS,
    TABLE_MARGIN,
    VISE_MARGIN,
    Point,
    SCGridPlate,
    SCKeepOut,
    SCMachineVise,
    SCMillTable,
    SCParallel,
    SCPrism,
    _mm,
)

# The setup shown when no file is named.
EXAMPLE: Path = Path(__file__).resolve().parent / (
    "examples/setup/grid_plate.json"
)

# How raw material looks: a translucent white box.
RAW_COLOR: str = "#ffffff"
RAW_OPACITY: float = 0.35

# How far apart two lengths may be and still be the same (millimeters).
TOLERANCE: float = 1.0e-6

# What the JSON can name.
TABLES: dict[str, SCMillTable] = {
    table.name: table for table in (*MILL_TABLES, MIKINI_1610L)
}
MACHINE_VISES: dict[str, SCMachineVise] = {KURT_D688.name: KURT_D688}
PARALLEL_TYPES: dict[str, SCParallel] = {
    parallel.name: parallel for parallel in PARALLELS
}


# The shop whose tooling the JSON can name, beyond what `tools.py` has.
SHOP: Path = Path(__file__).resolve().parent / "examples/shop/home_shop.toml"


# The grid plates the JSON can name: `tools.GRID_PLATE` and the shop's.
PARTS: dict[str, SCGridPlate] = {
    GRID_PLATE.name: GRID_PLATE,
    **{
        name: SCGridPlate.from_shop(plate)
        for name, plate in grid_plates(read(SHOP)).items()
    },
}


# Class `SCPlacement`:
@dataclass(frozen=True, slots=True)
class SCPlacement:
    """Where an item goes.

    Attributes:
    * `x` (`float`): The X of its center (millimeters).
    * `y` (`float`): The Y of its center (millimeters).
    * `z` (`float`): The Z of its bottom (millimeters).
    * `turns` (`int`):
      How many quarter turns clockwise it is turned, from 0 to 3.

    Constructor:
    * `SCPlacement(x, y, z, turns)`
    """

    # Constructor arguments:
    x: float = field(init=True)
    y: float = field(init=True)
    z: float = field(init=True)
    turns: int = field(init=True)

    # Method `SCPlacement.center()`:
    def center(self) -> Point:
        """Return the center of the item's bottom.

        Returns:
        * (`Point`): It (millimeters).
        """
        return (self.x, self.y, self.z)

    # Method `SCPlacement.turned()`:
    def turned(self, prism: SCPrism) -> SCPrism:
        """Return a prism, around the item unturned, as the item is turned.

        Arguments:
        * `prism` (`SCPrism`): The prism, at the item's location.

        Returns:
        * (`SCPrism`): The prism with the item's turns.
        """
        for _ in range(self.turns):
            prism = prism.quarter_turned(self.x, self.y)
        return prism

    # Method `SCPlacement.model()`:
    def model(
        self,
        layer: SCLayer,
        solidcraft: SCPyBind,
        cache: SCModelCache | None = None,
        before_building: Callable[[], None] = lambda: None,
    ) -> list[str]:
        """Model an item here.

        Arguments:
        * `layer` (`SCLayer`): The item.
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `cache` (`SCModelCache | None`):
          Where to keep its models between runs, or `None` to build it.
        * `before_building` (`Callable[[], None]`):
          Called before anything is built, rather than inserted.

        Returns:
        * (`list[str]`): The names of its bodies.
        """
        if cache is not None:
            cached: list[str] | None = self.model_cached(
                layer, solidcraft, cache, before_building
            )
            if cached is not None:
                return cached

        # SolidCraft turns bodies about the origin, so build it there.
        before_building()
        bodies: list[str] = layer.model(solidcraft, (0.0, 0.0, self.z))
        if self.turns:
            solidcraft.solid.move(
                bodies=bodies,
                axis=(0, 0, 1),
                angle=f"{-90 * self.turns} deg",
            )
        if self.x != 0.0 or self.y != 0.0:
            solidcraft.solid.move(
                bodies=bodies, translate=(self.x, self.y, 0.0)
            )
        return bodies

    # Method `SCPlacement.model_cached()`:
    def model_cached(
        self,
        layer: SCLayer,
        solidcraft: SCPyBind,
        cache: SCModelCache,
        before_building: Callable[[], None],
    ) -> list[str] | None:
        """Model an item here from the cache.

        Arguments:
        * `layer` (`SCLayer`): The item.
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `cache` (`SCModelCache`): The cache.
        * `before_building` (`Callable[[], None]`):
          Called before a model that is not in the cache is built.

        Returns:
        * (`list[str] | None`):
          The names of its bodies, or `None` if it must be built: it is
          not to be cached, or the cache could not be used.
        """
        models = layer.cacheable()
        if not models:
            return None
        bodies: list[str] = []
        for model in models:
            inserted: SCInserted | None = cache.insert(
                solidcraft,
                model,
                placement_matrix(self.turns, self.center(), model.offset),
                before_building,
            )
            if inserted is None:
                # What did go in must not be there twice.
                if bodies:
                    solidcraft.solid.remove(bodies=cast(JSON, bodies))
                return None
            bodies.extend(inserted.bodies)
        return bodies


# Class `SCPlacedTool`:
@dataclass(frozen=True, slots=True)
class SCPlacedTool:
    """A piece of tooling, and where it goes.

    Attributes:
    * `layer` (`SCLayer`): The tooling.
    * `placement` (`SCPlacement`): Where it goes.

    Constructor:
    * `SCPlacedTool(layer, placement)`
    """

    # Constructor arguments:
    layer: SCLayer = field(init=True)
    placement: SCPlacement = field(init=True)

    # Method `SCPlacedTool.keep_out()`:
    def keep_out(self) -> SCKeepOut:
        """Return the regions around it that a tool must not enter.

        Returns:
        * (`SCKeepOut`): The regions, as it is placed.
        """
        keep_out: SCKeepOut = self.layer.keep_out(self.placement.center())
        keep_out.prisms = [
            self.placement.turned(prism) for prism in keep_out.prisms
        ]
        return keep_out


# Class `SCPlacedWork`:
@dataclass(frozen=True, slots=True)
class SCPlacedWork:
    """A chunk of material or a finished part, and where it goes.

    Attributes:
    * `solid` (`SCPlate | SCGridPlate`): The material or the part.
    * `placement` (`SCPlacement`): Where it goes.
    * `parts` (`tuple[SCPlacedWork, ...]`):
      The parts to be made from it, if it is material.

    Constructor:
    * `SCPlacedWork(solid, placement, parts)`
    """

    # Constructor arguments:
    solid: SCPlate | SCGridPlate = field(init=True)
    placement: SCPlacement = field(init=True)
    parts: tuple["SCPlacedWork", ...] = field(init=True, default=())

    # Method `SCPlacedWork.bounds()`:
    def bounds(self) -> SCPrism:
        """Return the prism that just encloses it, as it is placed.

        Returns:
        * (`SCPrism`): The prism.
        """
        return self.placement.turned(self.solid.prism(self.placement.center()))

    # Method `SCPlacedWork.work_origin()`:
    def work_origin(self) -> Point:
        """Return where the G-code's X0 Y0 Z0 is: the middle of its top.

        Returns:
        * (`Point`): It, in the setup's coordinates (millimeters).
        """
        bounds: SCPrism = self.bounds()
        return (
            (bounds.low[0] + bounds.high[0]) / 2.0,
            (bounds.low[1] + bounds.high[1]) / 2.0,
            bounds.high[2],
        )


# Class `_SCReader`:
@dataclass(slots=True)
class _SCReader:
    """Reads the JSON, saving every problem to report them all at once.

    Attributes:
    * `problems` (`list[str]`): What is wrong, each with its entry.

    Constructor:
    * `_SCReader()`
    """

    # Attributes filled in later (alphabetized):
    problems: list[str] = field(init=False, default_factory=list)

    # Method `_SCReader.problem()`:
    def problem(self, path: str, message: str) -> None:
        """Save a problem.

        Arguments:
        * `path` (`str`): The entry (such as `tooling[1].height`).
        * `message` (`str`): What is wrong with it.
        """
        self.problems.append(f"{path}: {message}")

    # Method `_SCReader.keys()`:
    def keys(
        self, entry: Any, path: str, keys: tuple[str, ...]
    ) -> dict[str, Any]:
        """Return an entry that must have exactly the keys given.

        Arguments:
        * `entry` (`Any`): The entry, from the JSON.
        * `path` (`str`): The entry's name, for problems.
        * `keys` (`tuple[str, ...]`): The keys it must have.

        Returns:
        * (`dict[str, Any]`):
          The entry, with a `None` for each missing key.
        """
        if not isinstance(entry, dict):
            self.problem(path, "must be an object")
            return dict.fromkeys(keys)
        for key in entry:
            if key not in keys:
                self.problem(f"{path}.{key}", "is not a known key")
        result: dict[str, Any] = {}
        for key in keys:
            if key not in entry:
                self.problem(f"{path}.{key}", "is missing")
            result[key] = entry.get(key)
        return result

    # Method `_SCReader.items()`:
    def items(self, entry: Any, path: str) -> list[Any]:
        """Return an entry that must be a list.

        Arguments:
        * `entry` (`Any`): The entry, from the JSON.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`list[Any]`): The list (empty, if it is not one).
        """
        if isinstance(entry, list):
            return entry
        if entry is not None:
            self.problem(path, "must be a list")
        return []

    # Method `_SCReader.text()`:
    def text(self, entry: Any, path: str) -> str:
        """Return an entry that must be a string.

        Arguments:
        * `entry` (`Any`): The entry, from the JSON.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`str`): The string (empty, if it is not one).
        """
        if isinstance(entry, str):
            return entry
        if entry is not None:
            self.problem(path, "must be a string")
        return ""

    # Method `_SCReader.length()`:
    def length(self, entry: Any, path: str) -> float:
        """Return a length with a unit.

        Arguments:
        * `entry` (`Any`): The length, from the JSON.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`float`): The length (millimeters; zero, if it is not one).
        """
        if entry is None:
            return 0.0
        try:
            return measure(entry, LENGTH) * MM_PER_INCH
        except ValueError as error:
            self.problem(path, str(error))
            return 0.0

    # Method `_SCReader.lengths()`:
    def lengths(self, entry: Any, path: str, count: int) -> list[float]:
        """Return a list of lengths with units.

        Arguments:
        * `entry` (`Any`): The list, from the JSON.
        * `path` (`str`): The entry's name, for problems.
        * `count` (`int`): How many it must have.

        Returns:
        * (`list[float]`): The lengths (millimeters); zeros on a problem.
        """
        if entry is None:
            return [0.0] * count
        if not isinstance(entry, list) or len(entry) != count:
            self.problem(path, f"must be a list of {count} lengths")
            return [0.0] * count
        return [
            self.length(item, f"{path}[{index}]")
            for index, item in enumerate(entry)
        ]

    # Method `_SCReader.placement()`:
    def placement(self, entry: dict[str, Any], path: str) -> SCPlacement:
        """Return where an entry says it goes.

        Arguments:
        * `entry` (`dict[str, Any]`): The item's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`SCPlacement`): Where it goes.
        """
        x, y = self.lengths(entry["location"], f"{path}.location", 2)
        z: float = self.length(entry["height"], f"{path}.height")
        return SCPlacement(
            x, y, z, self.turns(entry["orientation"], f"{path}.orientation")
        )

    # Method `_SCReader.turns()`:
    def turns(self, entry: Any, path: str) -> int:
        """Return an orientation as quarter turns clockwise.

        Arguments:
        * `entry` (`Any`): The orientation, from the JSON.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`int`): The turns, from 0 to 3 (zero, on a problem).
        """
        if entry is None:
            return 0
        try:
            degrees: float = measure(entry, ANGLE)
        except ValueError as error:
            self.problem(path, str(error))
            return 0
        if degrees % 90.0 != 0.0:
            self.problem(path, f"{entry!r} is not a whole quarter turn")
            return 0
        return round(-degrees / 90.0) % 4

    # Method `_SCReader.tool()`:
    def tool(self, entry: Any, path: str) -> SCPlacedTool | None:
        """Return a piece of tooling.

        Arguments:
        * `entry` (`Any`): The tool's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`SCPlacedTool | None`): The tool, or `None` on a problem.
        """
        kind: Any = entry.get("kind") if isinstance(entry, dict) else None
        names: tuple[str, ...] = ("kind", "type", "location", "height")
        names += ("orientation",)
        if kind == "machine_vise":
            names += ("opening",)
        item: dict[str, Any] = self.keys(entry, path, names)
        placement: SCPlacement = self.placement(item, path)
        name: str = self.text(item["type"], f"{path}.type")
        layer: SCLayer | None = None
        if kind == "mill_table" and name in TABLES:
            layer = SCTableLayer(TABLES[name])
        elif kind == "parallel" and name in PARALLEL_TYPES:
            layer = SCParallelLayer(PARALLEL_TYPES[name])
        elif kind == "machine_vise" and name in MACHINE_VISES:
            layer = self.vise(MACHINE_VISES[name], item["opening"], path)
        elif kind == "grid_plate" and name in PARTS:
            layer = PARTS[name]
        elif kind not in (
            "mill_table",
            "parallel",
            "grid_plate",
            "machine_vise",
        ):
            self.problem(f"{path}.kind", f"{kind!r} is not a kind of tooling")
        else:
            self.problem(f"{path}.type", f"{name!r} is not a known {kind}")
        return None if layer is None else SCPlacedTool(layer, placement)

    # Method `_SCReader.vise()`:
    def vise(
        self, vise: SCMachineVise, entry: Any, path: str
    ) -> SCMachineViseLayer | None:
        """Return a vise with its jaws set.

        Arguments:
        * `vise` (`SCMachineVise`): The vise.
        * `entry` (`Any`): The opening, from the JSON.
        * `path` (`str`): The vise's entry's name, for problems.

        Returns:
        * (`SCMachineViseLayer | None`): The vise, or `None` on a problem.
        """
        opening: float = self.length(entry, f"{path}.opening")
        if not 0.0 <= opening <= vise.max_opening:
            self.problem(
                f"{path}.opening",
                f"{entry!r} is past {_inches(vise.max_opening)}, the most "
                f"that a {vise.name} opens",
            )
            return None
        return SCMachineViseLayer(vise, opening)

    # Method `_SCReader.part()`:
    def part(self, entry: Any, path: str) -> SCPlacedWork | None:
        """Return a part to be made.

        Arguments:
        * `entry` (`Any`): The part's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`SCPlacedWork | None`): The part, or `None` on a problem.
        """
        item: dict[str, Any] = self.keys(
            entry, path, ("type", "location", "height", "orientation")
        )
        placement: SCPlacement = self.placement(item, path)
        name: str = self.text(item["type"], f"{path}.type")
        if name not in PARTS:
            self.problem(f"{path}.type", f"{name!r} is not a known part")
            return None
        return SCPlacedWork(PARTS[name], placement)

    # Method `_SCReader.material()`:
    def material(self, entry: Any, path: str) -> SCPlacedWork | None:
        """Return a chunk of raw material, with the parts it becomes.

        Arguments:
        * `entry` (`Any`): The material's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`SCPlacedWork | None`): The material, or `None` on a problem.
        """
        item: dict[str, Any] = self.keys(
            entry,
            path,
            (
                "name",
                "material",
                "size",
                "location",
                "height",
                "orientation",
                "parts",
            ),
        )
        self.text(item["material"], f"{path}.material")
        name: str = self.text(item["name"], f"{path}.name")
        x, y, z = self.lengths(item["size"], f"{path}.size", 3)
        parts: list[SCPlacedWork | None] = [
            self.part(part, f"{path}.parts[{index}]")
            for index, part in enumerate(
                self.items(item["parts"], f"{path}.parts")
            )
        ]
        placement: SCPlacement = self.placement(item, path)
        if min(x, y, z) <= 0.0:
            self.problem(f"{path}.size", "must be three lengths above zero")
            return None
        return SCPlacedWork(
            SCPlate(name, x, y, z, RAW_COLOR, RAW_OPACITY),
            placement,
            tuple(part for part in parts if part is not None),
        )


# Function `_part_notes()`:
def _part_notes(material: SCPlacedWork) -> list[str]:
    """Return how the parts fit in a chunk of material.

    Arguments:
    * `material` (`SCPlacedWork`): The material.

    Returns:
    * (`list[str]`): The notes, one sentence each.
    """
    notes: list[str] = []
    room: SCPrism = material.bounds()
    for part in material.parts:
        bounds: SCPrism = part.bounds()
        for axis, letter in enumerate("XYZ"):
            below: float = room.low[axis] - bounds.low[axis]
            above: float = bounds.high[axis] - room.high[axis]
            if max(below, above) > TOLERANCE:
                notes.append(
                    f"PART DOES NOT FIT: {part.solid.name} reaches past "
                    f"{room.name} along {letter}, by {_inches(below)} on "
                    f"the low side and {_inches(above)} on the high side."
                )
    return notes


# Function `_gap()`:
def _gap(layer: SCMachineViseLayer, placement: SCPlacement) -> SCPrism:
    """Return the space between a vise's jaw plates, up to their tops.

    Arguments:
    * `layer` (`SCMachineViseLayer`): The vise.
    * `placement` (`SCPlacement`): Where it goes.

    Returns:
    * (`SCPrism`): The space, as the vise is placed.
    """
    vise: SCMachineVise = layer.vise
    middle: float = placement.x + vise.gap_center(layer.opening)
    half_jaw: float = vise.jaw_plate.width / 2.0
    rails: float = placement.z + vise.bed_top()
    return placement.turned(
        SCPrism(
            "gap",
            (
                middle - layer.opening / 2.0,
                placement.y - half_jaw,
                rails,
            ),
            (
                middle + layer.opening / 2.0,
                placement.y + half_jaw,
                rails + vise.jaw_plate.height,
            ),
        )
    )


# Function `_held_notes()`:
# Each of the sizes it compares gets a name, past `pylint`'s limit.
# pylint: disable-next=too-many-locals
def _held_notes(tool: SCPlacedTool, material: SCPlacedWork) -> list[str]:
    """Return how a vise holds a chunk of material.

    Arguments:
    * `tool` (`SCPlacedTool`):
      The vise, whose `layer` is a `SCMachineViseLayer`.
    * `material` (`SCPlacedWork`): The material.

    Returns:
    * (`list[str]`): The notes, one sentence each.
    """
    assert isinstance(tool.layer, SCMachineViseLayer)
    gap: SCPrism = _gap(tool.layer, tool.placement)
    bounds: SCPrism = material.bounds()
    across: int = 1 if tool.placement.turns % 2 else 0
    along: int = 1 - across
    margin: float = _mm(VISE_MARGIN)
    notes: list[str] = []

    # The jaws hold it only if it just fills the gap.
    slack: float = (gap.high[across] - gap.low[across]) - (
        bounds.high[across] - bounds.low[across]
    )
    inside: float = min(
        bounds.low[across] - gap.low[across],
        gap.high[across] - bounds.high[across],
    )
    if inside < -TOLERANCE:
        notes.append(
            f"DOES NOT FIT: {bounds.name} reaches {_inches(-inside)} into a "
            "jaw."
        )
    elif slack > TOLERANCE:
        notes.append(
            f"NOT CLAMPED: {bounds.name} is {_inches(slack)} narrower than "
            "the gap between the jaws."
        )

    # How much of it the jaws hold, and how much a tool can get at.
    grip: float = min(gap.high[2], bounds.high[2]) - bounds.low[2]
    proud: float = bounds.high[2] - gap.high[2]
    notes.append(
        f"The jaws grip {_inches(grip)} of {bounds.name}'s "
        f"{_inches(bounds.high[2] - bounds.low[2])} height; its top is "
        f"{_inches(proud)} above the jaws and {_inches(proud - margin)} "
        "above their keep-outs."
    )
    past: float = (bounds.high[along] - bounds.low[along]) - (
        gap.high[along] - gap.low[along]
    )
    if past > TOLERANCE:
        notes.append(
            f"{bounds.name} reaches {_inches(past / 2.0)} past the jaws at "
            f"each {'XY'[along]} end."
        )

    # How close a part comes to the jaws' keep-outs.
    for part in material.parts:
        edges: SCPrism = part.bounds()
        room: float = min(
            edges.low[across] - gap.low[across],
            gap.high[across] - edges.high[across],
        )
        if -TOLERANCE <= room - margin <= margin:
            notes.append(
                f"{part.solid.name}'s edge is {_inches(room)} from a jaw, "
                f"{_inches(room - margin)} from its keep-out: too close to "
                "cut that edge all the way through in this setup."
            )
    return notes


# Class `SCSetup`:
class SCSetup:
    """All of the tooling and material on a machine, from JSON.

    Attributes:
    * `name` (`str`): What it is.
    * `machine` (`str`): The machine's name.
    * `x_travel` (`float`): How far its X axis travels (millimeters).
    * `y_travel` (`float`): How far its Y axis travels (millimeters).
    * `tooling` (`list[SCPlacedTool]`): The tooling, from the bottom up.
    * `materials` (`list[SCPlacedWork]`): The chunks of raw material.

    Constructor:
    * `SCSetup(setup_json)`
    """

    # Method `SCSetup.__init__()`:
    def __init__(self, setup_json: dict[str, Any]) -> None:
        """Read a setup.

        Arguments:
        * `setup_json` (`dict[str, Any]`): The setup, as parsed JSON.

        Raises:
        * `ValueError`: With every problem found, one to a line.
        """
        reader: _SCReader = _SCReader()
        top: dict[str, Any] = reader.keys(
            setup_json, "setup", ("name", "machine", "tooling", "materials")
        )
        machine: dict[str, Any] = reader.keys(
            top["machine"], "machine", ("name", "x_travel", "y_travel")
        )
        self.name: str = reader.text(top["name"], "name")
        self.machine: str = reader.text(machine["name"], "machine.name")
        self.x_travel: float = reader.length(
            machine["x_travel"], "machine.x_travel"
        )
        self.y_travel: float = reader.length(
            machine["y_travel"], "machine.y_travel"
        )
        tools: list[SCPlacedTool | None] = [
            reader.tool(entry, f"tooling[{index}]")
            for index, entry in enumerate(
                reader.items(top["tooling"], "tooling")
            )
        ]
        materials: list[SCPlacedWork | None] = [
            reader.material(entry, f"materials[{index}]")
            for index, entry in enumerate(
                reader.items(top["materials"], "materials")
            )
        ]
        if reader.problems:
            raise ValueError("\n".join(reader.problems))
        self.tooling: list[SCPlacedTool] = [
            tool for tool in tools if tool is not None
        ]
        self.materials: list[SCPlacedWork] = [
            material for material in materials if material is not None
        ]

    # Method `SCSetup.model()`:
    def model(
        self,
        solidcraft: SCPyBind,
        cache: SCModelCache | None = None,
        units: DocumentUnitsUnits = "mm",
    ) -> list[str]:
        """Model the tooling, then the material, then the parts.

        A setup's numbers are millimeters, so a design in other units
        goes to millimeters while anything is built, and back.  With a
        complex design a change takes seconds, so it is not made when
        everything comes from the cache, whose placements are always in
        millimeters.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `cache` (`SCModelCache | None`):
          Where to keep the models between runs, or `None` to build them.
        * `units` (`DocumentUnitsUnits`): The units the design is in.

        Returns:
        * (`list[str]`): The names of the bodies.
        """
        changed: list[bool] = []

        # Function `to_millimeters()`:
        def to_millimeters() -> None:
            """Put the design in millimeters, if it needs it, once."""
            if units != "mm" and not changed:
                solidcraft.document.units(units="mm")
                changed.append(True)

        bodies: list[str] = []
        for tool in self.tooling:
            bodies.extend(
                tool.placement.model(
                    tool.layer, solidcraft, cache, to_millimeters
                )
            )
        for material in self.materials:
            bodies.extend(
                material.placement.model(
                    material.solid, solidcraft, cache, to_millimeters
                )
            )
        for material in self.materials:
            for part in material.parts:
                bodies.extend(
                    part.placement.model(
                        part.solid, solidcraft, cache, to_millimeters
                    )
                )
        if changed:
            solidcraft.document.units(units=units)
        return bodies

    # Method `SCSetup.keep_out()`:
    def keep_out(self) -> SCKeepOut:
        """Return the regions that a tool must not enter.

        Material and parts have none, since they are what gets cut.

        Returns:
        * (`SCKeepOut`): The regions of all of the tooling.
        """
        keep_out: SCKeepOut = SCKeepOut()
        for tool in self.tooling:
            regions: SCKeepOut = tool.keep_out()
            keep_out.prisms.extend(regions.prisms)
            keep_out.cylinders.extend(regions.cylinders)
        return keep_out

    # Method `SCSetup._table_notes()`:
    def _table_notes(self) -> list[str]:
        """Return how far a vise reaches past the table it stands on.

        Returns:
        * (`list[str]`): The notes, one sentence each.
        """
        notes: list[str] = []
        tables: list[SCPlacedTool] = [
            tool
            for tool in self.tooling
            if isinstance(tool.layer, SCTableLayer)
        ]
        if not tables:
            return notes
        table: SCPrism = (
            tables[0].keep_out().prisms[0].grown(-_mm(TABLE_MARGIN))
        )
        for tool in self.tooling:
            if isinstance(tool.layer, SCMachineViseLayer):
                base: SCPrism = (
                    tool.keep_out().prisms[0].grown(-_mm(VISE_MARGIN))
                )
                for axis, letter in enumerate("XY"):
                    low: float = table.low[axis] - base.low[axis]
                    high: float = base.high[axis] - table.high[axis]
                    if max(low, high) > TOLERANCE:
                        notes.append(
                            f"{tool.layer.name} reaches past the table along "
                            f"{letter}: {_inches(low)} at the low side, "
                            f"{_inches(high)} at the high side (negative "
                            "stops short of the edge)."
                        )
        return notes

    # Method `SCSetup._reach_notes()`:
    def _reach_notes(self) -> list[str]:
        """Return which parts the axes can not reach.

        The travel is taken to be centered on `X = 0` and `Y = 0`.

        Returns:
        * (`list[str]`): The notes, one sentence each.
        """
        notes: list[str] = []
        limits: tuple[float, float] = (
            self.x_travel / 2.0,
            self.y_travel / 2.0,
        )
        for material in self.materials:
            for part in material.parts:
                bounds: SCPrism = part.bounds()
                for axis, letter in enumerate("XY"):
                    past: float = (
                        max(bounds.high[axis], -bounds.low[axis])
                        - limits[axis]
                    )
                    if past > TOLERANCE:
                        notes.append(
                            f"OUT OF REACH: {part.solid.name} reaches "
                            f"{_inches(past)} past the {letter} travel."
                        )
        return notes

    # Method `SCSetup.notes()`:
    def notes(self) -> list[str]:
        """Return what a person should know about how the setup came out.

        Returns:
        * (`list[str]`): The notes, one sentence each.
        """
        notes: list[str] = []
        for material in self.materials:
            notes.extend(_part_notes(material))
            for tool in self.tooling:
                if isinstance(tool.layer, SCMachineViseLayer):
                    notes.extend(_held_notes(tool, material))
        notes.extend(self._table_notes())
        notes.extend(self._reach_notes())
        return notes

    # Method `SCSetup.report()`:
    def report(self) -> list[str]:
        """Return the setup as lines of text.

        Returns:
        * (`list[str]`):
          Each item's height, location and turns, then the `notes()`.
        """
        lines: list[str] = [f"{self.name} ({self.machine}):"]
        items: list[tuple[str, SCPlacement]] = [
            (tool.layer.name, tool.placement) for tool in self.tooling
        ]
        for material in self.materials:
            items.append((material.solid.name, material.placement))
            items.extend(
                (part.solid.name, part.placement) for part in material.parts
            )
        for name, place in items:
            degrees: int = (180 - 90 * place.turns) % 360 - 180
            lines.append(
                f"  Z {_inches(place.z):>10}  X {_inches(place.x):>10}  "
                f"Y {_inches(place.y):>10}  {degrees:>4} deg  {name}"
            )
        lines.extend(f"* {note}" for note in self.notes())
        return lines


# Function `main()`:
def main() -> None:
    """Show a setup and its keep-outs, in a new design."""
    arguments: list[str] = sys.argv[1:]
    target: str = arguments.pop() if arguments else "8080"
    path: Path = Path(arguments[0]) if arguments else EXAMPLE
    setup: SCSetup = SCSetup(json.loads(path.read_text(encoding="utf-8")))
    with connect(target) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.file.new()
        print(setup.model(solidcraft, cache_for(target)))
        print(setup.keep_out().model(solidcraft))
        solidcraft.view.apply(view="iso")
    print("\n".join(setup.report()))


if __name__ == "__main__":
    main()
