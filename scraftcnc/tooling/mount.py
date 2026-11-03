#!/usr/bin/env python3
"""Mounts: how work is held on a machine, as a stack of layers.

A `SCMount` is a list of layers, each of them tooling or material, and
each standing where the layer below says the next one goes.  The top
of the first layer is at `Z = 0`.  Tooling has keep-out regions;
material does not, since it is what gets cut.

Run as a program, it shows a stack in SolidCraft: `garage`, the Mikini
1610L's table with a Kurt vise turned along Y; `plate`, that table with
a grid plate; or `first`, a Tormach 770 table with a Kurt vise, a
pair of parallels and an aluminum plate.

```
python3 mount.py 8080 [garage|plate|first]     # A GUI on that port.
python3 mount.py headless [garage|plate|first] # No window; a report.
```
"""

import sys
from dataclasses import dataclass, field
from typing import Protocol

from ..model_cache import SCCacheable
from ..pybind.scraftpybind import SCPyBind, connect
from .cutter_models import MM_PER_INCH
from .tools import (
    ALUMINUM_COLOR,
    DRILL_COLOR,
    GRID_PLATE,
    KURT_D688,
    MIKINI_1610L,
    MIKINI_Y_TRAVEL,
    MILL_TABLES,
    PARALLEL_MARGIN,
    PARALLELS,
    TABLE_COLOR,
    TABLE_MARGIN,
    VISE_MARGIN,
    Point,
    SCKeepOut,
    SCMachineVise,
    SCMillTable,
    SCParallel,
    SCPrism,
    SCTormach,
    SCViseBlock,
    _mm,
    box_prism,
    tooling_shape,
)


# Function `_inches()`:
def _inches(length: float) -> str:
    """Return a length for a person to read.

    Arguments:
    * `length` (`float`): The length (millimeters).

    Returns:
    * (`str`): The length in inches, with its unit.
    """
    return f"{length / MM_PER_INCH:.3f} in"


# Class `SCLayer`:
class SCLayer(Protocol):
    """One layer of a `SCMount`: anything that can be stacked."""

    # Method `SCLayer.name()`:
    @property
    def name(self) -> str:
        """Return what the layer is."""

    # Method `SCLayer.seat()`:
    def seat(self) -> Point:
        """Return where the next layer stands.

        Returns:
        * (`Point`):
          The center of the next layer's bottom, from the center of
          this layer's bottom (millimeters).
        """

    # Method `SCLayer.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the layer.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`list[str]`): The names of the bodies.
        """

    # Method `SCLayer.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return the layer as models that can be cached.

        Returns:
        * (`tuple[SCCacheable, ...]`):
          The models, around the center of its bottom, or none if it is
          always to be built with `model()`.
        """

    # Method `SCLayer.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the regions around the layer that a tool must not enter.

        Arguments:
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`SCKeepOut`): The regions (none, for material).
        """


# Class `SCTableLayer`:
@dataclass(frozen=True, slots=True)
class SCTableLayer:
    """A mill's table.

    Attributes:
    * `table` (`SCMillTable`): The table.

    Constructor:
    * `SCTableLayer(table)`
    """

    # Constructor arguments:
    table: SCMillTable = field(init=True)

    # Method `SCTableLayer.name()`:
    @property
    def name(self) -> str:
        """Return the table's name."""
        return self.table.name

    # Method `SCTableLayer.seat()`:
    def seat(self) -> Point:
        """Return the middle of the table's top.

        Returns:
        * (`Point`): It, from the center of the table's bottom (mm).
        """
        return (0.0, 0.0, self.table.thickness)

    # Method `SCTableLayer.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the table.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`list[str]`): The name of the table's body.
        """
        # A table is modeled with its top at `Z = 0` and on `X = 0`.
        x, y, z = center
        body: str = SCTormach(solidcraft).mill_table(self.table, y)
        top: float = z + self.table.thickness
        if x != 0.0 or top != 0.0:
            solidcraft.solid.move(bodies=[body], translate=(x, 0.0, top))
        return [body]

    # Method `SCTableLayer.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return the table as a model that can be cached.

        Returns:
        * (`tuple[SCCacheable, ...]`): The table.
        """
        return (
            SCCacheable(
                self.table.name,
                tooling_shape(self.table),
                lambda solidcraft: self.model(solidcraft, (0.0, 0.0, 0.0)),
                color_of=lambda _body: TABLE_COLOR,
            ),
        )

    # Method `SCTableLayer.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the prism around the table.

        Arguments:
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`SCKeepOut`): One grown prism.
        """
        keep_out: SCKeepOut = SCKeepOut()
        keep_out.add_prism(
            box_prism(
                self.table.name,
                (self.table.length, self.table.width, self.table.thickness),
                center,
            ),
            TABLE_MARGIN,
        )
        return keep_out


# Class `SCMachineViseLayer`:
@dataclass(frozen=True, slots=True)
class SCMachineViseLayer:
    """A machine vise, with its jaws set to an opening.

    The next layer stands on the bed, in the middle of the gap.  A
    turned vise has its lead screw along Y, with the hexagon toward -Y (the
    operator) and the fixed jaw toward +Y; otherwise its lead screw is along
    X, with the hexagon toward +X.

    Attributes:
    * `vise` (`SCMachineVise`): The vise.
    * `opening` (`float`): The gap between its jaw plates (millimeters).
    * `turned` (`bool`): True if its lead screw runs along Y.

    Constructor:
    * `SCMachineViseLayer(vise, opening, turned)`
    """

    # Constructor arguments:
    vise: SCMachineVise = field(init=True)
    opening: float = field(init=True)
    turned: bool = field(init=True, default=False)

    # Method `SCMachineViseLayer.name()`:
    @property
    def name(self) -> str:
        """Return the vise's name."""
        return self.vise.name

    # Method `SCMachineViseLayer.seat()`:
    def seat(self) -> Point:
        """Return the middle of the gap, on top of the rails.

        Returns:
        * (`Point`): It, from the center of the base's bottom (mm).
        """
        gap: float = self.vise.gap_center(self.opening)
        height: float = self.vise.bed_top()
        return (0.0, -gap, height) if self.turned else (gap, 0.0, height)

    # Method `SCMachineViseLayer.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the vise.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`list[str]`): The names of the bodies.
        """
        if not self.turned:
            return self.vise.model(solidcraft, center, self.opening)

        # SolidCraft turns bodies about the origin, so build it there.
        x, y, z = center
        bodies: list[str] = self.vise.model(
            solidcraft, (0.0, 0.0, z), self.opening
        )
        solidcraft.solid.move(bodies=bodies, axis=(0, 0, 1), angle="-90 deg")
        if x != 0.0 or y != 0.0:
            solidcraft.solid.move(bodies=bodies, translate=(x, y, 0.0))
        return bodies

    # Method `SCMachineViseLayer.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return the vise as models that can be cached.

        Returns:
        * (`tuple[SCCacheable, ...]`):
          The vise, then what moves; none if it is `turned`, which a
          setup leaves to its placement.
        """
        return () if self.turned else self.vise.cacheable(self.opening)

    # Method `SCMachineViseLayer.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the prisms around the base and each jaw.

        Arguments:
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`SCKeepOut`): Three grown prisms.
        """
        keep_out: SCKeepOut = self.vise.keep_out(
            center, self.opening, VISE_MARGIN
        )
        if self.turned:
            keep_out.prisms = [
                prism.quarter_turned(center[0], center[1])
                for prism in keep_out.prisms
            ]
        return keep_out


# Class `SCParallelLayer`:
@dataclass(frozen=True, slots=True)
class SCParallelLayer:
    """One parallel, for a stack that places each of them itself.

    Attributes:
    * `parallel` (`SCParallel`): The parallel.

    Constructor:
    * `SCParallelLayer(parallel)`
    """

    # Constructor arguments:
    parallel: SCParallel = field(init=True)

    # Method `SCParallelLayer.name()`:
    @property
    def name(self) -> str:
        """Return the parallel's name."""
        return self.parallel.name

    # Method `SCParallelLayer.seat()`:
    def seat(self) -> Point:
        """Return the middle of the parallel's top edge.

        Returns:
        * (`Point`): It, from the center of its bottom edge (mm).
        """
        return (0.0, 0.0, self.parallel.height)

    # Method `SCParallelLayer.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the parallel.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`list[str]`): The name of its body.
        """
        return [self.parallel.model(solidcraft, center)]

    # Method `SCParallelLayer.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return the parallel as a model that can be cached.

        Returns:
        * (`tuple[SCCacheable, ...]`): The parallel.
        """
        return (
            SCCacheable(
                self.parallel.name,
                tooling_shape(self.parallel),
                lambda solidcraft: self.model(solidcraft, (0.0, 0.0, 0.0)),
                color_of=lambda _body: DRILL_COLOR,
            ),
        )

    # Method `SCParallelLayer.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the prism around the parallel.

        Arguments:
        * `center` (`Point`): The center of its bottom edge (mm).

        Returns:
        * (`SCKeepOut`): One grown prism.
        """
        keep_out: SCKeepOut = SCKeepOut()
        keep_out.add_prism(self.parallel.prism(center), PARALLEL_MARGIN)
        return keep_out


# Class `SCParallelPair`:
@dataclass(frozen=True, slots=True)
class SCParallelPair:
    """Two parallels of one height, side by side along X.

    Attributes:
    * `first` (`SCParallel`): The parallel toward -X.
    * `second` (`SCParallel`): The parallel toward +X.
    * `spacing` (`float`): The distance between their centers (mm).

    Constructor:
    * `SCParallelPair(first, second, spacing)`
    """

    # Constructor arguments:
    first: SCParallel = field(init=True)
    second: SCParallel = field(init=True)
    spacing: float = field(init=True)

    # Method `SCParallelPair.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the two can carry work between them.

        Raises:
        * `ValueError`: If their heights differ, or if they overlap.
        """
        if self.first.height != self.second.height:
            raise ValueError(
                f"{self.first.height=} must match {self.second.height=}"
            )
        if self.spacing < self.first.thickness:
            raise ValueError(
                f"{self.spacing=} is less than {self.first.thickness=}"
            )

    # Method `SCParallelPair.name()`:
    @property
    def name(self) -> str:
        """Return what the pair is."""
        return f"{self.first.name} and {self.second.name}"

    # Method `SCParallelPair.seat()`:
    def seat(self) -> Point:
        """Return the middle of the space above the pair.

        Returns:
        * (`Point`): It, from the middle of the pair's bottom (mm).
        """
        return (0.0, 0.0, self.first.height)

    # Method `SCParallelPair.centers()`:
    def centers(self, center: Point) -> list[Point]:
        """Return the center of each parallel's bottom edge.

        Arguments:
        * `center` (`Point`): The middle of the pair's bottom (mm).

        Returns:
        * (`list[Point]`): The first parallel's, then the second's.
        """
        x, y, z = center
        half: float = self.spacing / 2.0
        return [(x - half, y, z), (x + half, y, z)]

    # Method `SCParallelPair.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model both parallels.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The middle of the pair's bottom (mm).

        Returns:
        * (`list[str]`): The names of the bodies.
        """
        return [
            parallel.model(solidcraft, place)
            for parallel, place in zip(
                (self.first, self.second), self.centers(center)
            )
        ]

    # Method `SCParallelPair.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return nothing, since a mount builds its pair each time.

        Returns:
        * (`tuple[SCCacheable, ...]`): No models.
        """
        return ()

    # Method `SCParallelPair.keep_out()`:
    def keep_out(self, center: Point) -> SCKeepOut:
        """Return the prism around each parallel.

        Arguments:
        * `center` (`Point`): The middle of the pair's bottom (mm).

        Returns:
        * (`SCKeepOut`): Two grown prisms.
        """
        keep_out: SCKeepOut = SCKeepOut()
        for parallel, place in zip(
            (self.first, self.second), self.centers(center)
        ):
            keep_out.add_prism(parallel.prism(place), PARALLEL_MARGIN)
        return keep_out


# Class `SCPlate`:
@dataclass(frozen=True, slots=True)
class SCPlate:
    """A rectangular plate of material, which is what gets cut.

    Attributes:
    * `name` (`str`): What it is.
    * `length` (`float`): Its size along X (millimeters).
    * `width` (`float`): Its size along Y (millimeters).
    * `thickness` (`float`): Its size along Z (millimeters).
    * `color` (`str`): How it looks.
    * `opacity` (`float`): How solid it looks, from 0.0 to 1.0.

    Constructor:
    * `SCPlate(name, length, width, thickness, color, opacity)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    length: float = field(init=True)
    width: float = field(init=True)
    thickness: float = field(init=True)
    color: str = field(init=True, default=ALUMINUM_COLOR)
    opacity: float = field(init=True, default=1.0)

    # Method `SCPlate.prism()`:
    def prism(self, center: Point) -> SCPrism:
        """Return the rectangular prism that just encloses the plate.

        Arguments:
        * `center` (`Point`): The center of its bottom face (mm).

        Returns:
        * (`SCPrism`): The prism, named for the plate.
        """
        return box_prism(
            self.name, (self.length, self.width, self.thickness), center
        )

    # Method `SCPlate.seat()`:
    def seat(self) -> Point:
        """Return the middle of the plate's top.

        Returns:
        * (`Point`): It, from the center of the plate's bottom (mm).
        """
        return (0.0, 0.0, self.thickness)

    # Method `SCPlate.model()`:
    def model(self, solidcraft: SCPyBind, center: Point) -> list[str]:
        """Model the plate.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.
        * `center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`list[str]`): The name of the plate's body.
        """
        body: str = SCViseBlock(self.length, self.width, self.thickness).model(
            solidcraft, self.name, center
        )
        solidcraft.appearance.assign(
            bodies=[body], color=self.color, opacity=self.opacity
        )
        return [body]

    # Method `SCPlate.cacheable()`:
    def cacheable(self) -> tuple[SCCacheable, ...]:
        """Return nothing, since a plain box is quick to build.

        Returns:
        * (`tuple[SCCacheable, ...]`): No models.
        """
        return ()

    # Method `SCPlate.keep_out()`:
    def keep_out(self, _center: Point) -> SCKeepOut:
        """Return no regions, since a tool is meant to enter material.

        Arguments:
        * `_center` (`Point`): The center of its bottom (millimeters).

        Returns:
        * (`SCKeepOut`): An empty set of regions.
        """
        return SCKeepOut()


# Class `SCMount`:
@dataclass(frozen=True, slots=True)
class SCMount:
    """A stack of layers holding work on a machine.

    Attributes:
    * `name` (`str`): What it is.
    * `layers` (`tuple[SCLayer, ...]`): The layers, from the bottom up.
    * `notes` (`tuple[str, ...]`):
      What a person should know about how the stack came out.

    Constructor:
    * `SCMount(name, layers, notes)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    layers: tuple[SCLayer, ...] = field(init=True)
    notes: tuple[str, ...] = field(init=True, default=())

    # Method `SCMount.places()`:
    def places(self) -> list[Point]:
        """Return where each layer goes, with the first's top at `Z = 0`.

        Returns:
        * (`list[Point]`):
          The center of each layer's bottom (millimeters), in `layers`
          order.
        """
        places: list[Point] = []
        x: float = 0.0
        y: float = 0.0
        z: float = -self.layers[0].seat()[2]
        for layer in self.layers:
            places.append((x, y, z))
            seat_x, seat_y, seat_z = layer.seat()
            x, y, z = x + seat_x, y + seat_y, z + seat_z
        return places

    # Method `SCMount.report()`:
    def report(self) -> list[str]:
        """Return the stack as lines of text, from the top down.

        Returns:
        * (`list[str]`):
          The Z at each layer's bottom and where the next layer stands,
          then the `notes`.
        """
        lines: list[str] = [f"{self.name}:"]
        for layer, place in reversed(list(zip(self.layers, self.places()))):
            seat: float = place[2] + layer.seat()[2]
            lines.append(
                f"  {_inches(place[2]):>10} to {_inches(seat):>10}  "
                f"{layer.name}"
            )
        lines.extend(f"* {note}" for note in self.notes)
        return lines

    # Method `SCMount.model()`:
    def model(self, solidcraft: SCPyBind) -> list[str]:
        """Model every layer.

        Arguments:
        * `solidcraft` (`SCPyBind`): The SolidCraft session.

        Returns:
        * (`list[str]`): The names of the bodies, from the bottom up.
        """
        bodies: list[str] = []
        for layer, place in zip(self.layers, self.places()):
            bodies.extend(layer.model(solidcraft, place))
        return bodies

    # Method `SCMount.keep_out()`:
    def keep_out(self) -> SCKeepOut:
        """Return the regions of every layer that a tool must not enter.

        Returns:
        * (`SCKeepOut`): The regions, from the bottom up.
        """
        keep_out: SCKeepOut = SCKeepOut()
        for layer, place in zip(self.layers, self.places()):
            regions: SCKeepOut = layer.keep_out(place)
            keep_out.prisms.extend(regions.prisms)
            keep_out.cylinders.extend(regions.cylinders)
        return keep_out


# Function `parallel_pair()`:
def parallel_pair(height: str, spacing: float) -> SCParallelPair:
    """Return the pair of a given height from the set of parallels.

    Arguments:
    * `height` (`str`): Its height as `PARALLELS` names it (`"1-1/2 in"`).
    * `spacing` (`float`): The distance between their centers (mm).

    Returns:
    * (`SCParallelPair`): The pair.

    Raises:
    * `ValueError`: If the set has no such pair.
    """
    found: list[SCParallel] = [
        parallel
        for parallel in PARALLELS
        if parallel.name.startswith(f"Parallel {height} ")
    ]
    if len(found) != 2:
        raise ValueError(f"{height=} is not a pair of `PARALLELS`")
    return SCParallelPair(found[0], found[1], spacing)


# Function `vise_notes()`:
def vise_notes(
    table: SCMillTable,
    vise: SCMachineVise,
    opening: float,
    pair: SCParallelPair,
    work: SCPlate,
) -> tuple[str, ...]:
    """Return what a person should know about work held in a vise.

    Arguments:
    * `table` (`SCMillTable`): The table under the vise.
    * `vise` (`SCMachineVise`): The vise.
    * `opening` (`float`): The gap between its jaw plates (millimeters).
    * `pair` (`SCParallelPair`): The parallels under the work.
    * `work` (`SCPlate`): The work.

    Returns:
    * (`tuple[str, ...]`): The notes, one sentence each.
    """
    notes: list[str] = []

    # The jaws hold the work only if they are closed on it.
    slack: float = opening - work.length
    if slack > 0.0:
        notes.append(
            f"NOT CLAMPED: the work is {_inches(slack)} narrower than the "
            f"{_inches(opening)} gap between the jaws."
        )

    # The jaws grip what is below their tops.
    grip: float = min(
        vise.jaw_plate.height - pair.first.height, work.thickness
    )
    if grip > 0.0:
        notes.append(
            f"The jaws can grip {_inches(grip)} of the "
            f"{_inches(work.thickness)} thick work."
        )
    else:
        notes.append("NO GRIP: the work sits above the tops of the jaws.")

    # A tool stays above the jaws' keep-outs, which may hide the work.
    proud: float = pair.first.height + work.thickness - vise.jaw_plate.height
    clearance: float = proud - _mm(VISE_MARGIN)
    if clearance > 0.0:
        notes.append(
            f"The work's top is {_inches(proud)} above the jaws, and "
            f"{_inches(clearance)} above their keep-outs."
        )
    else:
        notes.append(
            f"KEEP-OUT: the jaws' keep-outs reach {_inches(-clearance)} "
            "above the work's top."
        )

    # Work past the jaws and the table has nothing under or beside it.
    past_jaws: float = (work.width - vise.jaw_plate.width) / 2.0
    if past_jaws > 0.0:
        notes.append(
            f"The work reaches {_inches(past_jaws)} past the jaws at each "
            "Y end, with no parallel under that part."
        )
    past_table: float = (work.width - table.width) / 2.0
    if past_table > 0.0:
        notes.append(
            f"The work reaches {_inches(past_table)} past the table at each "
            "Y end."
        )
    return tuple(notes)


# Function `vise_mount()`:
def vise_mount(
    table: SCMillTable,
    vise: SCMachineVise,
    opening: float,
    height: str,
    work: SCPlate,
) -> SCMount:
    """Return a stack of a table, a vise, parallels and work.

    The vise is centered on the table, and the work in the gap between
    the jaws.  The parallels lie under the work's X edges, flush with
    them, so that they stay under the work as the jaws close on it.

    Arguments:
    * `table` (`SCMillTable`): The table.
    * `vise` (`SCMachineVise`): The vise.
    * `opening` (`float`): The gap between its jaw plates (millimeters).
    * `height` (`str`): The parallels' height, as `PARALLELS` names it.
    * `work` (`SCPlate`): The work, whose `length` lies across the jaws.

    Returns:
    * (`SCMount`): The stack, with its notes.

    Raises:
    * `ValueError`: If the work does not fit between the jaws, or the set
      of parallels has no such height.
    """
    if work.length > opening:
        raise ValueError(f"{work.length=} does not fit {opening=}")
    thickness: float = PARALLELS[0].thickness
    pair: SCParallelPair = parallel_pair(height, work.length - thickness)
    return SCMount(
        f"{work.name} in a {vise.name} on a {table.name}",
        (SCTableLayer(table), SCMachineViseLayer(vise, opening), pair, work),
        vise_notes(table, vise, opening, pair, work),
    )


# Function `turned_vise_notes()`:
def turned_vise_notes(
    table: SCMillTable, vise: SCMachineVise, opening: float, y_travel: float
) -> tuple[str, ...]:
    """Return how a vise centered on a table, turned along Y, fits it.

    Arguments:
    * `table` (`SCMillTable`): The table, whose width lies along Y.
    * `vise` (`SCMachineVise`): The vise.
    * `opening` (`float`): The gap between its jaw plates (millimeters).
    * `y_travel` (`float`): How far the Y axis travels (millimeters).

    Returns:
    * (`tuple[str, ...]`): The notes, one sentence each.
    """
    # The base's length against the table's width.
    past_table: float = (vise.base.length - table.width) / 2.0
    hex_past: float = past_table + vise.lead_screw_stick_out + vise.hex_length
    notes: list[str] = []
    notes.append(
        f"The base is {_inches(vise.base.length)} long on a "
        f"{_inches(table.width)} wide table: {_inches(past_table)} past "
        f"the rear edge, and {_inches(past_table)} past the front, or "
        f"{_inches(hex_past)} to the end of the hexagon."
    )

    # What the Y axis reaches, with its travel centered on the table.
    gap: float = -vise.gap_center(opening)
    beyond: float = abs(gap) + (opening - y_travel) / 2.0
    if beyond > 0.0:
        notes.append(
            f"OUT OF REACH: with the Y travel centered on the table, the "
            f"{_inches(opening)} gap reaches {_inches(beyond)} past it."
        )
    return tuple(notes)


# The first stack, as the user described it, on the middle of Tormach's
# three tables.  The user gave no thickness for the plate; 1/2 in is the
# demonstration's.
FIRST_MOUNT: SCMount = vise_mount(
    MILL_TABLES[1],
    KURT_D688,
    _mm("6 in"),
    "1-1/2 in",
    SCPlate("Aluminum plate", _mm("5-1/2 in"), _mm("12 in"), _mm("1/2 in")),
)


# The mill in the user's garage: does a full size vise fit its table?
GARAGE_OPENING: float = _mm("6 in")
GARAGE_MOUNT: SCMount = SCMount(
    f"{KURT_D688.name} on a {MIKINI_1610L.name}",
    (
        SCTableLayer(MIKINI_1610L),
        SCMachineViseLayer(KURT_D688, GARAGE_OPENING, turned=True),
    ),
    turned_vise_notes(
        MIKINI_1610L, KURT_D688, GARAGE_OPENING, MIKINI_Y_TRAVEL
    ),
)

# The grid plate directly on that table, whose width it matches.
PLATE_MOUNT: SCMount = SCMount(
    f"{GRID_PLATE.name} on a {MIKINI_1610L.name}",
    (SCTableLayer(MIKINI_1610L), GRID_PLATE),
)

# The stacks that can be shown.
MOUNTS: dict[str, SCMount] = {
    "garage": GARAGE_MOUNT,
    "plate": PLATE_MOUNT,
    "first": FIRST_MOUNT,
}


# Function `main()`:
def main() -> None:
    """Show a stack and its keep-outs, in a new design."""
    target: str = sys.argv[1] if len(sys.argv) > 1 else "8080"
    stack: SCMount = MOUNTS[sys.argv[2] if len(sys.argv) > 2 else "garage"]
    with connect(target) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.file.new()
        print(stack.model(solidcraft))
        print(stack.keep_out().model(solidcraft))
        solidcraft.view.apply(view="iso")
    print("\n".join(stack.report()))


if __name__ == "__main__":
    main()
