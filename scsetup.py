#!/usr/bin/env python3
"""Setups: all of the tooling and material on a machine, from JSON.

A `Setup` says where everything goes: the location, orientation and
height of each piece of tooling, each chunk of material, and each part
to be made from a chunk.  Everything is given outright, with a unit on
every number, and `Setup` reports how it comes out.  There may be many
chunks of material, each becoming a different part, so that they can
all be cut with few tool changes.

In the JSON, `location` is the `[x, y]` of an item's center, `height` is
the Z of its bottom, and `orientation` is how far it is turned about its
center, seen from above: counterclockwise is positive, in quarter turns.
`examples/setup/tooling_plate.json` is an example.

```
python3 scsetup.py [FILE] 8080       # A GUI with `--control 8080`.
python3 scsetup.py [FILE] headless   # No window; prints the report.
```
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mount import Layer, ParallelLayer, Plate, TableLayer, ViseLayer, _inches
from scraftpybind import SolidCraftPyBind, connect
from sctoolmodel import MM_PER_INCH
from shops import ANGLE, LENGTH, measure
from tools import (
    KURT_D688,
    MIKINI_1610L,
    MILL_TABLES,
    PARALLELS,
    TABLE_MARGIN,
    TOOLING_PLATE,
    VISE_MARGIN,
    KeepOut,
    MillTable,
    Parallel,
    Point,
    Prism,
    ToolingPlate,
    Vise,
    _mm,
)

# The setup shown when no file is named.
EXAMPLE: Path = Path(__file__).resolve().parent / (
    "examples/setup/tooling_plate.json"
)

# How raw material looks: a translucent white box.
RAW_COLOR: str = "#ffffff"
RAW_OPACITY: float = 0.35

# How far apart two lengths may be and still be the same (millimeters).
TOLERANCE: float = 1.0e-6

# What the JSON can name.
TABLES: dict[str, MillTable] = {
    table.name: table for table in (*MILL_TABLES, MIKINI_1610L)
}
VISES: dict[str, Vise] = {KURT_D688.name: KURT_D688}
PARALLEL_TYPES: dict[str, Parallel] = {
    parallel.name: parallel for parallel in PARALLELS
}
PARTS: dict[str, ToolingPlate] = {TOOLING_PLATE.name: TOOLING_PLATE}


# Class `Placement`:
@dataclass(frozen=True, slots=True)
class Placement:
    """Where an item goes.

    Attributes:
    * `x` (`float`): The X of its center (millimeters).
    * `y` (`float`): The Y of its center (millimeters).
    * `z` (`float`): The Z of its bottom (millimeters).
    * `turns` (`int`):
      How many quarter turns clockwise it is turned, from 0 to 3.

    Constructor:
    * `Placement(x, y, z, turns)`
    """

    # Constructor arguments:
    x: float = field(init=True)
    y: float = field(init=True)
    z: float = field(init=True)
    turns: int = field(init=True)

    # Method `Placement.center()`:
    def center(self) -> Point:
        """Return the center of the item's bottom.

        Returns:
        * (`Point`): It (millimeters).
        """
        return (self.x, self.y, self.z)

    # Method `Placement.turned()`:
    def turned(self, prism: Prism) -> Prism:
        """Return a prism, around the item unturned, as the item is turned.

        Arguments:
        * `prism` (`Prism`): The prism, at the item's location.

        Returns:
        * (`Prism`): The prism with the item's turns.
        """
        for _ in range(self.turns):
            prism = prism.quarter_turned(self.x, self.y)
        return prism

    # Method `Placement.model()`:
    def model(self, layer: Layer, solidcraft: SolidCraftPyBind) -> list[str]:
        """Model an item here.

        Arguments:
        * `layer` (`Layer`): The item.
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

        Returns:
        * (`list[str]`): The names of its bodies.
        """
        # SolidCraft turns bodies about the origin, so build it there.
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


# Class `PlacedTool`:
@dataclass(frozen=True, slots=True)
class PlacedTool:
    """A piece of tooling, and where it goes.

    Attributes:
    * `layer` (`Layer`): The tooling.
    * `placement` (`Placement`): Where it goes.

    Constructor:
    * `PlacedTool(layer, placement)`
    """

    # Constructor arguments:
    layer: Layer = field(init=True)
    placement: Placement = field(init=True)

    # Method `PlacedTool.keep_out()`:
    def keep_out(self) -> KeepOut:
        """Return the regions around it that a tool must not enter.

        Returns:
        * (`KeepOut`): The regions, as it is placed.
        """
        keep_out: KeepOut = self.layer.keep_out(self.placement.center())
        keep_out.prisms = [
            self.placement.turned(prism) for prism in keep_out.prisms
        ]
        return keep_out


# Class `PlacedWork`:
@dataclass(frozen=True, slots=True)
class PlacedWork:
    """A chunk of material or a finished part, and where it goes.

    Attributes:
    * `solid` (`Plate | ToolingPlate`): The material or the part.
    * `placement` (`Placement`): Where it goes.
    * `parts` (`tuple[PlacedWork, ...]`):
      The parts to be made from it, if it is material.

    Constructor:
    * `PlacedWork(solid, placement, parts)`
    """

    # Constructor arguments:
    solid: Plate | ToolingPlate = field(init=True)
    placement: Placement = field(init=True)
    parts: tuple["PlacedWork", ...] = field(init=True, default=())

    # Method `PlacedWork.bounds()`:
    def bounds(self) -> Prism:
        """Return the prism that just encloses it, as it is placed.

        Returns:
        * (`Prism`): The prism.
        """
        return self.placement.turned(self.solid.prism(self.placement.center()))


# Class `_Reader`:
@dataclass(slots=True)
class _Reader:
    """Reads the JSON, saving every problem to report them all at once.

    Attributes:
    * `problems` (`list[str]`): What is wrong, each with its entry.

    Constructor:
    * `_Reader()`
    """

    # Attributes filled in later (alphabetized):
    problems: list[str] = field(init=False, default_factory=list)

    # Method `_Reader.problem()`:
    def problem(self, path: str, message: str) -> None:
        """Save a problem.

        Arguments:
        * `path` (`str`): The entry (such as `tooling[1].height`).
        * `message` (`str`): What is wrong with it.
        """
        self.problems.append(f"{path}: {message}")

    # Method `_Reader.keys()`:
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

    # Method `_Reader.items()`:
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

    # Method `_Reader.text()`:
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

    # Method `_Reader.length()`:
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

    # Method `_Reader.lengths()`:
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

    # Method `_Reader.placement()`:
    def placement(self, entry: dict[str, Any], path: str) -> Placement:
        """Return where an entry says it goes.

        Arguments:
        * `entry` (`dict[str, Any]`): The item's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`Placement`): Where it goes.
        """
        x, y = self.lengths(entry["location"], f"{path}.location", 2)
        z: float = self.length(entry["height"], f"{path}.height")
        return Placement(
            x, y, z, self.turns(entry["orientation"], f"{path}.orientation")
        )

    # Method `_Reader.turns()`:
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

    # Method `_Reader.tool()`:
    def tool(self, entry: Any, path: str) -> PlacedTool | None:
        """Return a piece of tooling.

        Arguments:
        * `entry` (`Any`): The tool's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`PlacedTool | None`): The tool, or `None` on a problem.
        """
        kind: Any = entry.get("kind") if isinstance(entry, dict) else None
        names: tuple[str, ...] = ("kind", "type", "location", "height")
        names += ("orientation",)
        if kind == "vise":
            names += ("opening",)
        item: dict[str, Any] = self.keys(entry, path, names)
        placement: Placement = self.placement(item, path)
        name: str = self.text(item["type"], f"{path}.type")
        layer: Layer | None = None
        if kind == "mill_table" and name in TABLES:
            layer = TableLayer(TABLES[name])
        elif kind == "parallel" and name in PARALLEL_TYPES:
            layer = ParallelLayer(PARALLEL_TYPES[name])
        elif kind == "vise" and name in VISES:
            layer = self.vise(VISES[name], item["opening"], path)
        elif kind not in ("mill_table", "parallel", "vise"):
            self.problem(f"{path}.kind", f"{kind!r} is not a kind of tooling")
        else:
            self.problem(f"{path}.type", f"{name!r} is not a known {kind}")
        return None if layer is None else PlacedTool(layer, placement)

    # Method `_Reader.vise()`:
    def vise(self, vise: Vise, entry: Any, path: str) -> ViseLayer | None:
        """Return a vise with its jaws set.

        Arguments:
        * `vise` (`Vise`): The vise.
        * `entry` (`Any`): The opening, from the JSON.
        * `path` (`str`): The vise's entry's name, for problems.

        Returns:
        * (`ViseLayer | None`): The vise, or `None` on a problem.
        """
        opening: float = self.length(entry, f"{path}.opening")
        if not 0.0 <= opening <= vise.max_opening:
            self.problem(
                f"{path}.opening",
                f"{entry!r} is past {_inches(vise.max_opening)}, the most "
                f"that a {vise.name} opens",
            )
            return None
        return ViseLayer(vise, opening)

    # Method `_Reader.part()`:
    def part(self, entry: Any, path: str) -> PlacedWork | None:
        """Return a part to be made.

        Arguments:
        * `entry` (`Any`): The part's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`PlacedWork | None`): The part, or `None` on a problem.
        """
        item: dict[str, Any] = self.keys(
            entry, path, ("type", "location", "height", "orientation")
        )
        placement: Placement = self.placement(item, path)
        name: str = self.text(item["type"], f"{path}.type")
        if name not in PARTS:
            self.problem(f"{path}.type", f"{name!r} is not a known part")
            return None
        return PlacedWork(PARTS[name], placement)

    # Method `_Reader.material()`:
    def material(self, entry: Any, path: str) -> PlacedWork | None:
        """Return a chunk of raw material, with the parts it becomes.

        Arguments:
        * `entry` (`Any`): The material's entry.
        * `path` (`str`): The entry's name, for problems.

        Returns:
        * (`PlacedWork | None`): The material, or `None` on a problem.
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
        parts: list[PlacedWork | None] = [
            self.part(part, f"{path}.parts[{index}]")
            for index, part in enumerate(
                self.items(item["parts"], f"{path}.parts")
            )
        ]
        placement: Placement = self.placement(item, path)
        if min(x, y, z) <= 0.0:
            self.problem(f"{path}.size", "must be three lengths above zero")
            return None
        return PlacedWork(
            Plate(name, x, y, z, RAW_COLOR, RAW_OPACITY),
            placement,
            tuple(part for part in parts if part is not None),
        )


# Function `_part_notes()`:
def _part_notes(material: PlacedWork) -> list[str]:
    """Return how the parts fit in a chunk of material.

    Arguments:
    * `material` (`PlacedWork`): The material.

    Returns:
    * (`list[str]`): The notes, one sentence each.
    """
    notes: list[str] = []
    room: Prism = material.bounds()
    for part in material.parts:
        bounds: Prism = part.bounds()
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
def _gap(layer: ViseLayer, placement: Placement) -> Prism:
    """Return the space between a vise's plates, up to their tops.

    Arguments:
    * `layer` (`ViseLayer`): The vise.
    * `placement` (`Placement`): Where it goes.

    Returns:
    * (`Prism`): The space, as the vise is placed.
    """
    vise: Vise = layer.vise
    middle: float = placement.x + vise.gap_center(layer.opening)
    half_jaw: float = vise.plate.width / 2.0
    rails: float = placement.z + vise.base_height()
    return placement.turned(
        Prism(
            "gap",
            (
                middle - layer.opening / 2.0,
                placement.y - half_jaw,
                rails,
            ),
            (
                middle + layer.opening / 2.0,
                placement.y + half_jaw,
                rails + vise.plate.height,
            ),
        )
    )


# Function `_held_notes()`:
# Each of the sizes it compares gets a name, past `pylint`'s limit.
# pylint: disable-next=too-many-locals
def _held_notes(tool: PlacedTool, material: PlacedWork) -> list[str]:
    """Return how a vise holds a chunk of material.

    Arguments:
    * `tool` (`PlacedTool`): The vise, whose `layer` is a `ViseLayer`.
    * `material` (`PlacedWork`): The material.

    Returns:
    * (`list[str]`): The notes, one sentence each.
    """
    assert isinstance(tool.layer, ViseLayer)
    gap: Prism = _gap(tool.layer, tool.placement)
    bounds: Prism = material.bounds()
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
        edges: Prism = part.bounds()
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


# Class `Setup`:
class Setup:
    """All of the tooling and material on a machine, from JSON.

    Attributes:
    * `name` (`str`): What it is.
    * `machine` (`str`): The machine's name.
    * `x_travel` (`float`): How far its X axis travels (millimeters).
    * `y_travel` (`float`): How far its Y axis travels (millimeters).
    * `tooling` (`list[PlacedTool]`): The tooling, from the bottom up.
    * `materials` (`list[PlacedWork]`): The chunks of raw material.

    Constructor:
    * `Setup(setup_json)`
    """

    # Method `Setup.__init__()`:
    def __init__(self, setup_json: dict[str, Any]) -> None:
        """Read a setup.

        Arguments:
        * `setup_json` (`dict[str, Any]`): The setup, as parsed JSON.

        Raises:
        * `ValueError`: With every problem found, one to a line.
        """
        reader: _Reader = _Reader()
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
        tools: list[PlacedTool | None] = [
            reader.tool(entry, f"tooling[{index}]")
            for index, entry in enumerate(
                reader.items(top["tooling"], "tooling")
            )
        ]
        materials: list[PlacedWork | None] = [
            reader.material(entry, f"materials[{index}]")
            for index, entry in enumerate(
                reader.items(top["materials"], "materials")
            )
        ]
        if reader.problems:
            raise ValueError("\n".join(reader.problems))
        self.tooling: list[PlacedTool] = [
            tool for tool in tools if tool is not None
        ]
        self.materials: list[PlacedWork] = [
            material for material in materials if material is not None
        ]

    # Method `Setup.model()`:
    def model(self, solidcraft: SolidCraftPyBind) -> list[str]:
        """Model the tooling, then the material, then the parts.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.

        Returns:
        * (`list[str]`): The names of the bodies.
        """
        bodies: list[str] = []
        for tool in self.tooling:
            bodies.extend(tool.placement.model(tool.layer, solidcraft))
        for material in self.materials:
            bodies.extend(material.placement.model(material.solid, solidcraft))
        for material in self.materials:
            for part in material.parts:
                bodies.extend(part.placement.model(part.solid, solidcraft))
        return bodies

    # Method `Setup.keep_out()`:
    def keep_out(self) -> KeepOut:
        """Return the regions that a tool must not enter.

        Material and parts have none, since they are what gets cut.

        Returns:
        * (`KeepOut`): The regions of all of the tooling.
        """
        keep_out: KeepOut = KeepOut()
        for tool in self.tooling:
            regions: KeepOut = tool.keep_out()
            keep_out.prisms.extend(regions.prisms)
            keep_out.cylinders.extend(regions.cylinders)
        return keep_out

    # Method `Setup._table_notes()`:
    def _table_notes(self) -> list[str]:
        """Return how far a vise reaches past the table it stands on.

        Returns:
        * (`list[str]`): The notes, one sentence each.
        """
        notes: list[str] = []
        tables: list[PlacedTool] = [
            tool for tool in self.tooling if isinstance(tool.layer, TableLayer)
        ]
        if not tables:
            return notes
        table: Prism = tables[0].keep_out().prisms[0].grown(-_mm(TABLE_MARGIN))
        for tool in self.tooling:
            if isinstance(tool.layer, ViseLayer):
                base: Prism = (
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

    # Method `Setup._reach_notes()`:
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
                bounds: Prism = part.bounds()
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

    # Method `Setup.notes()`:
    def notes(self) -> list[str]:
        """Return what a person should know about how the setup came out.

        Returns:
        * (`list[str]`): The notes, one sentence each.
        """
        notes: list[str] = []
        for material in self.materials:
            notes.extend(_part_notes(material))
            for tool in self.tooling:
                if isinstance(tool.layer, ViseLayer):
                    notes.extend(_held_notes(tool, material))
        notes.extend(self._table_notes())
        notes.extend(self._reach_notes())
        return notes

    # Method `Setup.report()`:
    def report(self) -> list[str]:
        """Return the setup as lines of text.

        Returns:
        * (`list[str]`):
          Each item's height, location and turns, then the `notes()`.
        """
        lines: list[str] = [f"{self.name} ({self.machine}):"]
        items: list[tuple[str, Placement]] = [
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
    setup: Setup = Setup(json.loads(path.read_text(encoding="utf-8")))
    with connect(target) as transport:
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
        solidcraft.file.new()
        print(setup.model(solidcraft))
        print(setup.keep_out().model(solidcraft))
        solidcraft.view.apply(view="iso")
    print("\n".join(setup.report()))


if __name__ == "__main__":
    main()
