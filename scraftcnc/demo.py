#!/usr/bin/env python3
"""Cut and model a demonstration shape with `gcode`.

It prints the G-code for a notched plate, with a hole through it and a
pocket in it (around three islands), whose corners each have their own
radius, with its top edges beveled (and the hole's rounded over).
A roughing end mill clears the material, when the machine has one,
and the end mill finishes the walls and floors.
The machine and its tools come from the example shop
(`examples/shop/`), and its tools are named, not numbered: the places
the end mill goes down are drilled first, with the largest drill
smaller than it.  With a SolidCraft GUI's control port (`solidcraft --control
PORT`) or `headless`, it also models the plate in SolidCraft:

```
python3 -m scraftcnc.demo > demo.ngc
python3 -m scraftcnc.demo --plot demo.html > demo.ngc
python3 -m scraftcnc.demo 8080 > demo.ngc
python3 -m scraftcnc.demo headless > demo.ngc
```
"""

import dataclasses
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import setup_comments
from .assembly import (
    Assembly,
    AssemblyItem,
    keep_out_boxes,
    millimeters,
    resolve,
)
from .gcode import CNC, Stage
from .geometry import Corner, RoundedPolygon, point_at
from .machine import Machine, ToolEntry
from .plot import sketch_path, write_plot
from .pybind.scraftpybind import (
    JSON,
    HeadlessTransport,
    PyBind,
    Transport,
    connect,
)
from .shops import cnc_machine, read
from .tooling.shop_registries import use_shop

# A `solidcraft-cli` extracted from SolidCraft's AppImage, for
# headless sessions when none is on the `PATH` (if it is there; it is
# not part of this project).
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parents[1]
    / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
)

# SolidCraft's sketch coordinates are millimeters.
MM_PER_INCH: float = 25.4

# The shop, the machine in it that cuts the plate, and the end mill.
SHOP_FILE: Path = (
    Path(__file__).resolve().parents[1] / "examples/shop/home_shop.toml"
)
MACHINE: str = "Shop mill"

# The material the demonstration cuts, unless `--material` says.
MATERIAL: str = "6061 aluminum"
END_MILL: str = "1/4 in 2 flute carbide end mill"

# The bits that bevel and round over top edges, and the bevels' width.
CHAMFER_BIT: str = "1/8 in 90 deg carbide chamfer mill"
ROUNDING_BIT: str = "1/16 in radius carbide corner rounding mill"
BEVEL: float = 0.03


# Class `DemoPlate`:
@dataclass(slots=True)
class DemoPlate:
    """The demonstration plate's shape, for modeling it in SolidCraft.

    Attributes:
    * `outlines` (`list[RoundedPolygon]`):
      The plate's outline, then the outlines of its holes.
    * `pocket` (`list[RoundedPolygon]`):
      The outline of the pocket in its top, then its islands.
    * `sizes` (`tuple[float, float, float]`):
      The Z of the plate's top, its thickness, and the pocket's depth.
    * `edges` (`list[tuple[RoundedPolygon,
      Literal["chamfer", "fillet"], float]]`):
      The outlines whose top edges are beveled (by their width) or
      rounded over (by their radius).

    Constructor:
    * `DemoPlate(outlines, pocket, sizes, edges)`
    """

    # Constructor arguments:
    outlines: list[RoundedPolygon] = field(init=True)
    pocket: list[RoundedPolygon] = field(init=True)
    sizes: tuple[float, float, float] = field(init=True)
    edges: list[tuple[RoundedPolygon, Literal["chamfer", "fillet"], float]] = (
        field(init=True)
    )


# Function `demo_plate()`:
def demo_plate() -> RoundedPolygon:
    """Return the demonstration plate's outline.

    It is a 4 x 3 inch notched rectangle, going counter-clockwise, with
    a different radius at each corner; the notch's inner corner turns
    the other way.

    Returns:
    * (`RoundedPolygon`): The outline.
    """
    return RoundedPolygon(
        "Plate",
        [
            Corner(0.0, 0.0, 0.25),
            Corner(4.0, 0.0, 0.375),
            Corner(4.0, 3.0, 0.125),
            Corner(2.0, 3.0, 0.0625),
            Corner(2.0, 2.25, 0.1875),
            Corner(1.0, 2.25, 0.0),
            Corner(0.0, 3.0, 0.25),
        ],
        -0.5,
        0.0,
    )


# Function `demo_hole()`:
def demo_hole() -> RoundedPolygon:
    """Return the outline of the hole through the demonstration plate.

    Returns:
    * (`RoundedPolygon`): A rounded 0.6 x 1.1 inch rectangle.
    """
    return RoundedPolygon(
        "Hole",
        [
            Corner(3.0, 0.5, 0.1875),
            Corner(3.6, 0.5, 0.1875),
            Corner(3.6, 1.6, 0.1875),
            Corner(3.0, 1.6, 0.1875),
        ],
        0.0,
        -0.5,
    )


# Function `demo_pocket()`:
def demo_pocket() -> RoundedPolygon:
    """Return the outline of the pocket in the demonstration plate.

    Returns:
    * (`RoundedPolygon`): A 2.45 x 1.75 inch rectangle with rounded
      corners.
    """
    corner: float = 0.1875
    return RoundedPolygon(
        "Pocket",
        [
            Corner(0.3, 0.3, corner),
            Corner(2.75, 0.3, corner),
            Corner(2.75, 2.05, corner),
            Corner(0.3, 2.05, corner),
        ],
        0.0,
        -0.25,
    )


# Function `demo_islands()`:
def demo_islands() -> list[RoundedPolygon]:
    """Return the islands left standing in the demonstration's pocket.

    Returns:
    * (`list[RoundedPolygon]`): A triangle and a square with slightly
      rounded corners, and a square whose corner arcs make a circle.
    """
    edge: float = 0.0625
    return [
        RoundedPolygon(
            "Triangle",
            [
                Corner(0.65, 0.65, edge),
                Corner(1.25, 0.65, edge),
                Corner(0.95, 1.2, edge),
            ],
            -0.25,
            0.0,
        ),
        RoundedPolygon(
            "Square",
            [
                Corner(1.65, 0.65, edge),
                Corner(2.15, 0.65, edge),
                Corner(2.15, 1.15, edge),
                Corner(1.65, 1.15, edge),
            ],
            -0.25,
            0.0,
        ),
        RoundedPolygon(
            "Circle",
            [
                Corner(1.2, 1.35, 0.2),
                Corner(1.6, 1.35, 0.2),
                Corner(1.6, 1.75, 0.2),
                Corner(1.2, 1.75, 0.2),
            ],
            -0.25,
            0.0,
        ),
    ]


# Function `model()`:
# Its options and the steps of one SolidCraft session make many locals.
def model(
    where: str,
    part: DemoPlate,
    cnc: CNC,
    *,
    path: bool = True,
    opaque: bool = False,
) -> int:
    """Model a plate in SolidCraft, in inches.

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.
    * `part` (`DemoPlate`): The plate's shape.
    * `cnc` (`CNC`):
      The program, whose tool path is drawn beside the plate (which is
      made see-through so that the path inside it shows).
    * `path` (`bool`): False to leave the tool path out (as when
      `sim_solidcraft.py` draws it, one tool at a time).
    * `opaque` (`bool`): True to leave the plate solid, not
      see-through (as when a tool is watched cutting its surface).

    Returns:
    * (`int`): The number of closed profiles the sketches made (one per
      outline when they all closed).

    Raises:
    * `OSError`: If SolidCraft is not there (no GUI on the port, or no
      `solidcraft-cli`).
    """
    # A headless session uses the extracted `solidcraft-cli` when none
    # is on the `PATH` and it exists.
    transport: Transport = connect(where)
    if (
        isinstance(transport, HeadlessTransport)
        and shutil.which(transport.cli) is None
        and SOLIDCRAFT_CLI.exists()
    ):
        transport = HeadlessTransport(cli=str(SOLIDCRAFT_CLI))

    # Build the plate, draw the tool path, and let it show through.
    with transport:
        solidcraft: PyBind = PyBind(transport)
        solidcraft.document.units(units="in")
        profiles: int = _build(solidcraft, part)
        if path:
            sketch_path(solidcraft, cnc, MM_PER_INCH)
        solidcraft.appearance.assign(
            bodies=[part.outlines[0].name],
            color="#9fb4c8",
            opacity=1.0 if opaque else 0.35,
        )
        solidcraft.view.apply(view="iso")
    return profiles


# Function `_build()`:
def _build(solidcraft: PyBind, part: DemoPlate) -> int:
    """Build a plate in a session: extrude it, cut its pocket, finish it.

    Arguments:
    * `solidcraft` (`PyBind`): The session.
    * `part` (`DemoPlate`): The plate's shape.

    Returns:
    * (`int`): The number of closed profiles the sketches made.
    """
    # Sketch the outlines on the plate's bottom (whose origin is given
    # in millimeters), and extrude only the plate's own profile, so
    # that the holes stay holes.
    top: float
    thickness: float
    depth: float
    top, thickness, depth = part.sizes
    outlines: list[RoundedPolygon] = part.outlines
    curves: list[str] = _sketch(
        solidcraft, outlines, (top - thickness) * MM_PER_INCH
    )
    finished: JSON = solidcraft.sketch.finish()
    solidcraft.solid.extrude(
        distance=f"{thickness} in",
        profiles=[{"curves": curves}],
        body_name=outlines[0].name,
    )

    # Cut the pocket down from the top, around its islands.
    curves = _sketch(solidcraft, part.pocket, top * MM_PER_INCH)
    cut: JSON = solidcraft.sketch.finish()
    solidcraft.solid.extrude(
        distance=f"{depth} in",
        direction="negative",
        operation="cut",
        profiles=[{"curves": curves}],
    )

    # Bevel and round over the top edges.
    _edges(solidcraft, part.edges, top * MM_PER_INCH, outlines[0].name)
    assert isinstance(finished, dict) and isinstance(cut, dict)
    profiles: JSON = finished["profiles"]
    pockets: JSON = cut["profiles"]
    assert isinstance(profiles, int) and isinstance(pockets, int)
    return profiles + pockets


# Function `demo_shape()`:
def demo_shape(top: float, thickness: float, rounding: float) -> DemoPlate:
    """Return the demonstration plate's shape.

    Arguments:
    * `top` (`float`): The Z of the plate's top (inches).
    * `thickness` (`float`): The plate's thickness (inches).
    * `rounding` (`float`):
      The radius the hole's top edge is rounded over by (inches).

    Returns:
    * (`DemoPlate`): The plate, its hole, its pocket and islands, and how
      their top edges are finished.
    """
    plate: RoundedPolygon = demo_plate()
    hole: RoundedPolygon = demo_hole()
    pocket: RoundedPolygon = demo_pocket()
    islands: list[RoundedPolygon] = demo_islands()
    return DemoPlate(
        [plate, hole],
        [pocket, *islands],
        (top, thickness, 0.25),
        [
            (pocket, "chamfer", BEVEL),
            *((island, "chamfer", BEVEL) for island in islands),
            (plate, "chamfer", BEVEL),
            (hole, "fillet", rounding),
        ],
    )


# Class `DemoPart`:
@dataclass(slots=True, frozen=True)
class DemoPart:
    """The demonstration plate as a setup's part item (`demo_part()`).

    Making one touches no SolidCraft session; `model()` builds it.

    Attributes:
    * `material` (`str`): The material it is cut from (a shop name).
    * `thickness` (`float`): Its thickness (mm).

    Constructor:
    * `DemoPart(material, thickness)`
    """

    # Constructor arguments:
    material: str = field(init=True)
    thickness: float = field(init=True)

    # Method `DemoPart.model()`:
    def model(
        self, solidcraft: PyBind, point: tuple[float, float, float]
    ) -> list[str]:
        """Build the plate in a session, centered over a point.

        Arguments:
        * `solidcraft` (`PyBind`): The session.
        * `point` (`tuple[float, float, float]`):
          Where the middle of the plate's bottom goes (mm).

        Returns:
        * (`list[str]`): The names of its bodies (one).
        """
        # The hole's round over is the shop's corner rounding bit.
        machine: Machine = cnc_machine(read(SHOP_FILE), MACHINE, self.material)
        rounding: float = machine.named(ROUNDING_BIT).radius
        thickness: float = self.thickness / MM_PER_INCH
        part: DemoPlate = demo_shape(
            point[2] / MM_PER_INCH + thickness, thickness, rounding
        )
        _build(solidcraft, part)

        # The outline runs from (0, 0) to (4, 3) inches: move its
        # middle onto the point.
        name: str = part.outlines[0].name
        solidcraft.solid.move(
            bodies=[name],
            translate=(
                point[0] - 2.0 * MM_PER_INCH,
                point[1] - 1.5 * MM_PER_INCH,
                0.0,
            ),
        )
        return [name]


# Function `demo_part()`:
def demo_part(material: str, thickness: str | float) -> DemoPart:
    """Return the demonstration plate, for a setup's part item.

    Arguments:
    * `material` (`str`): The material it is cut from (a shop name).
    * `thickness` (`str | float`): Its thickness, with a unit.

    Returns:
    * (`DemoPart`): The plate, not yet built.

    Raises:
    * `TypeError`: If the thickness has no unit.
    * `ValueError`: If the thickness can not be read.
    """
    return DemoPart(material, millimeters(thickness, "part thickness"))


# Function `_edges()`:
def _edges(
    solidcraft: PyBind,
    edges: Sequence[
        tuple[RoundedPolygon, Literal["chamfer", "fillet"], float]
    ],
    z: float,
    body: str,
) -> None:
    """Bevel or round over the top edges of outlines on the plate.

    Each edge is picked by a point on it: the middle of each segment
    of its outline, at the top.

    Arguments:
    * `solidcraft` (`PyBind`): Where the plate is.
    * `edges` (`Sequence[tuple[RoundedPolygon, Literal["chamfer",
      "fillet"], float]]`):
      The outlines, how to finish each, and the size (inches).
    * `z` (`float`): The Z of the plate's top (mm).
    * `body` (`str`): The plate's body, so that only its edges are
      picked (a tool path drawn in the session can pass through the
      same points).
    """
    poly: RoundedPolygon
    kind: Literal["chamfer", "fillet"]
    size: float
    for poly, kind, size in edges:
        points: list[tuple[float, float, float]] = [
            (
                point_at(segment, 0.5)[0] * MM_PER_INCH,
                point_at(segment, 0.5)[1] * MM_PER_INCH,
                z,
            )
            for segment in poly.segments
        ]
        if kind == "chamfer":
            solidcraft.solid.chamfer(
                edges=points, distance=f"{size} in", body=body
            )
        else:
            solidcraft.solid.fillet(
                edges=points, radius=f"{size} in", body=body
            )


# Function `_sketch()`:
def _sketch(
    solidcraft: PyBind, outlines: list[RoundedPolygon], z: float
) -> list[str]:
    """Sketch outlines on a horizontal plane.

    Arguments:
    * `solidcraft` (`PyBind`): Where to sketch them.
    * `outlines` (`list[RoundedPolygon]`): The outlines.
    * `z` (`float`): The plane's Z (mm).

    Returns:
    * (`list[str]`): The curves of the first outline.
    """
    solidcraft.sketch.create(
        plane={
            "origin": [0.0, 0.0, z],
            "x_dir": [1.0, 0.0, 0.0],
            "y_dir": [0.0, 1.0, 0.0],
        },
        name=outlines[0].name,
    )
    curves: list[str] = outlines[0].sketch(solidcraft, MM_PER_INCH)
    outline: RoundedPolygon
    for outline in outlines[1:]:
        outline.sketch(solidcraft, MM_PER_INCH)
    return curves


# The tooling of `examples/setup/demo_stack.json`, bottom first: name,
# call, args, X, Y, Z, quarter turns and a note.  X, Y and Z place the
# center of the item's bottom, measured from the origin handed up by
# the item below, in the setup frame, not turned (#32); the table's
# are absolute.  The stock is centered on the grid plate (#80) and the
# work zero is the plate's lower left top corner, as the G-code has it
# (`T.hlp~3.3.1` #78).  Quarter turns match `demo_stack.json`'s degrees
# (counterclockwise: -90 deg is 3).  The vise's origin is its fixed
# jaw's top as modeled, on the rails (111.125 mm above the vise's
# bottom, #55).  These are only written into the
# `.nc` comments; the models are still drawn from `demo_stack.json`'s
# absolute positions.
# Each `call` is a `named()` class method, so `args` hold keys.
_TOOLING: tuple[
    tuple[str, str, dict[str, str | bool], str, str, str, int, str], ...
] = (
    (
        "mill table",
        "scraftcnc.tooling.mount:TableLayer.named",
        {"table": "mikini_1610l"},
        "2 in",
        "1-1/2 in",
        "-7.64 in",
        0,
        "Clean the table.",
    ),
    (
        "vise",
        "scraftcnc.tooling.mount:MachineViseLayer.named",
        {"vise": "kurt_d688", "opening": "5-1/2 in"},
        "15 in",
        "-8.65 in",
        "0 in",
        3,
        "Set the vise on the table, turned 90 degrees, and square it.",
    ),
    (
        "parallel A",
        "scraftcnc.tooling.mount:ParallelLayer.named",
        {"parallel": "parallel_1_1_2_in_a"},
        "3 in",
        "-0.0625 in",
        "-1.735 in",
        3,
        "Set a 1-1/2 in parallel against the fixed jaw.",
    ),
    (
        "parallel B",
        "scraftcnc.tooling.mount:ParallelLayer.named",
        {"parallel": "parallel_1_1_2_in_b"},
        "3 in",
        "-5.4375 in",
        "-1.735 in",
        3,
        "Set the other parallel against the moving jaw.",
    ),
    (
        "grid plate",
        "scraftcnc.tooling.tools:GridPlate.named",
        {"name": "grid_plate", "chamfer": False},
        "3 in",
        "-2.75 in",
        "-0.235 in",
        1,
        "Clamp the grid plate in the vise, on the parallels.",
    ),
)

# The stock the plate is cut from (its outline is 4 x 3 inches).
STOCK_SIZE: tuple[str, str, str] = ("4-1/2 in", "3-1/2 in", "1/2 in")


# Function `demo_assembly()`:
def demo_assembly(material: str = MATERIAL) -> Assembly:
    """Return the demonstration's setup, from `demo_stack.json`.

    Each location is the center of the item's bottom, measured from
    the origin handed up by the item below, in the setup frame, not
    turned (#32); the table's is absolute.  The vise's origin is its
    fixed jaw's top as modeled (111.125 mm above the vise's bottom,
    #55).  There are no keep-outs yet.

    Arguments:
    * `material` (`str`): The material being cut.

    Returns:
    * (`Assembly`): The tooling, the stock and the part.
    """
    # The tooling, bottom first.
    items: list[AssemblyItem] = [
        AssemblyItem(
            kind="tooling",
            name=name,
            call=call,
            args=dict(args),
            location=(
                millimeters(x, f"{name} x"),
                millimeters(y, f"{name} y"),
                millimeters(z, f"{name} z"),
            ),
            orientation=turns,
            note=note,
        )
        for name, call, args, x, y, z, turns, note in _TOOLING
    ]

    # Each tooling item carries its own keep-outs (#41a, #47).
    items = [
        dataclasses.replace(item, keep_out=keep_out_boxes(resolve(item)))
        for item in items
    ]

    # The stock centered on the grid plate (#80), and the part cut
    # from it.  The part
    # is assumed centered in the stock in X and Y, as thick as it, so
    # from the stock's top, left, outer corner (`Stock.origin()`)
    # its bottom's center is half the stock's size in X and Y, and
    # the stock's thickness down.
    short: str = "_".join(reversed(material.lower().split()))
    items.append(
        AssemblyItem(
            kind="stock",
            name="stock",
            call="scraftcnc.assembly:Stock",
            args={"material": short, "size": list(STOCK_SIZE)},
            location=(
                millimeters("5.25 in", "stock x"),
                millimeters("2.75 in", "stock y"),
                0.0,
            ),
            note="Set the stock on the grid plate and clamp it.",
        )
    )
    items.append(
        AssemblyItem(
            kind="part",
            name="demo plate",
            call="scraftcnc.demo:demo_part",
            args={"material": material, "thickness": "1/2 in"},
            location=(
                millimeters("2-1/4 in", "part x"),
                millimeters("1-3/4 in", "part y"),
                -millimeters("1/2 in", "part z"),
            ),
            note="Cut the plate; G54 zero is its lower left top corner.",
        )
    )
    return Assembly(items)


# Function `with_setup()`:
def with_setup(gcode: str, assembly: Assembly) -> str:
    """Return a program with its setup comments after its header.

    They go after any leading `%` and comment lines, before the first
    command.

    Arguments:
    * `gcode` (`str`): The program.
    * `assembly` (`Assembly`): Its setup.

    Returns:
    * (`str`): The program with the `(SCC: ...)` lines in it.
    """
    lines: list[str] = gcode.splitlines(keepends=True)
    at: int = 0
    while at < len(lines) and lines[at].lstrip()[:1] in ("%", "("):
        at += 1
    setup: list[str] = [line + "\n" for line in setup_comments.write(assembly)]
    return "".join(lines[:at] + setup + lines[at:])


# Function `cut_demo()`:
def cut_demo(material: str = MATERIAL) -> tuple[CNC, ToolEntry]:
    """Cut the demonstration plate on the example shop's mill.

    Arguments:
    * `material` (`str`):
      The material being cut, which sets the drills' speeds and feeds.

    Returns:
    * (`CNC`): The program.
    * (`ToolEntry`): The corner rounding bit (whose radius the model uses).
    """
    # Rough with the machine's rougher, if it has one, leaving its
    # finish allowance for the end mill; otherwise the end mill does
    # it all.
    plate: RoundedPolygon = demo_plate()
    hole: RoundedPolygon = demo_hole()
    pocket: RoundedPolygon = demo_pocket()
    islands: list[RoundedPolygon] = demo_islands()

    # The example shop is the one in use: its tooling is what is named.
    shop: dict[str, object] = read(SHOP_FILE)
    use_shop(shop)
    machine: Machine = cnc_machine(shop, MACHINE, material)
    end_mill: ToolEntry = machine.named(END_MILL)
    rougher: ToolEntry | None = machine.rougher_for(end_mill)
    first: ToolEntry = end_mill if rougher is None else rougher
    stage: Stage = "full" if rougher is None else "rough"

    # Drill where the first tool will go down, with the largest drill
    # smaller than it (through the plate for its hole and outline).
    cnc: CNC = CNC("SolidCraftCNC demo", machine)
    cnc.change_tool(machine.drill_for(first).number)
    cnc.drill(cnc.pocket_entries(pocket, first, islands, stage), -0.25)
    cnc.drill(
        [
            cnc.profile_entry(hole, first, inside=True, stage=stage),
            cnc.profile_entry(plate, first, stage=stage),
        ],
        -0.5,
        through=True,
    )

    # Clear the 0.25 inch deep pocket around its three islands, and cut
    # the hole, through a 0.5 inch plate, 0.125 inch at a time (and
    # rough the plate's outline, which leaves it held to the stock).
    cnc.change_tool(first.number)
    cnc.pocket(
        pocket, -0.25, 0.125, islands=islands, drilled=True, stage=stage
    )
    cnc.profile(hole, -0.5, 0.125, inside=True, through=True, stage=stage)
    if rougher is not None:
        cnc.profile(plate, -0.5, 0.125, through=True, stage="rough")
        cnc.change_tool(end_mill.number)
        cnc.pocket(pocket, -0.25, 0.25, islands=islands, stage="finish")
        cnc.profile(hole, -0.5, 0.5, inside=True, through=True, stage="finish")

    # Bevel the top edges of the pocket, its islands and the plate's
    # outside, round over the hole's, and then cut the plate out.
    cnc.change_tool(machine.named(CHAMFER_BIT).number)
    cnc.chamfer(pocket, BEVEL, inside=True)
    island: RoundedPolygon
    for island in islands:
        cnc.chamfer(island, BEVEL)
    cnc.chamfer(plate, BEVEL)
    rounding: ToolEntry = cnc.change_tool(machine.named(ROUNDING_BIT).number)
    cnc.chamfer(hole, inside=True)
    cnc.change_tool(end_mill.number)
    cnc.profile(
        plate,
        -0.5,
        0.125,
        through=True,
        stage="full" if rougher is None else "finish",
    )
    cnc.finish()
    return cnc, rounding


# Function `main()`:
def main() -> int:
    """Print the demonstration's G-code, plot it, and model it.

    The arguments are optional: `--plot FILE.html` writes a page that
    plots the tool path, and a SolidCraft GUI's control port (or
    `headless`) models the plate in SolidCraft.

    Returns:
    * (`int`): The exit status.
    """
    # Read the arguments.
    arguments: list[str] = sys.argv[1:]
    plot: Path | None = None
    path: bool = "--no-path" not in arguments
    if not path:
        arguments.remove("--no-path")
    opaque: bool = "--opaque" in arguments
    if opaque:
        arguments.remove("--opaque")
    material: str = MATERIAL
    if "--material" in arguments:
        at: int = arguments.index("--material")
        if at + 1 < len(arguments):
            material = arguments[at + 1]
            del arguments[at : at + 2]
    if arguments[:1] == ["--plot"] and len(arguments) >= 2:
        plot = Path(arguments[1])
        arguments = arguments[2:]
    if len(arguments) > 1 or arguments[:1] == ["--plot"]:
        print(
            f"usage: {sys.argv[0]} [--plot FILE.html] [--no-path] [--opaque] "
            "[--material NAME] [PORT|headless]",
            file=sys.stderr,
        )
        return 2

    # Cut it.
    plate: RoundedPolygon = demo_plate()
    hole: RoundedPolygon = demo_hole()
    pocket: RoundedPolygon = demo_pocket()
    islands: list[RoundedPolygon] = demo_islands()
    cnc: CNC
    rounding: ToolEntry
    cnc, rounding = cut_demo(material)
    print(with_setup(cnc.gcode(), demo_assembly(material)), end="")
    print(f"About {cnc.minutes:.1f} minutes", file=sys.stderr)

    # Plot it, if asked to, with the plate's outlines at its top and
    # bottom, and the pocket's at its floor.
    if plot is not None:
        write_plot(
            plot,
            cnc,
            [
                (plate, cnc.z_top),
                (plate, cnc.z_top - 0.5),
                (hole, cnc.z_top),
                (hole, cnc.z_top - 0.5),
                (pocket, cnc.z_top),
                (pocket, cnc.z_top - 0.25),
                *((island, cnc.z_top) for island in islands),
            ],
            "Demo Plate Tool Path",
        )
        print(f"Wrote {plot}", file=sys.stderr)

    # Model it, if asked to.
    if arguments:
        part: DemoPlate = demo_shape(cnc.z_top, 0.5, rounding.radius)
        # A SolidCraft that is not there is reported in one line.
        try:
            profiles: int = model(
                arguments[0], part, cnc, path=path, opaque=opaque
            )
        except OSError as error:
            print(f"demo.py: {error}", file=sys.stderr)
            return 1
        print(f"{plate.name}: {profiles} profile(s)", file=sys.stderr)
        # The plate's sketch has 2 profiles (the plate around its hole,
        # and the hole); the pocket's has 1 around the islands, and 1
        # inside each.
        if profiles != 3 + len(islands):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
