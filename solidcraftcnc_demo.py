#!/usr/bin/env python3
"""Cut and model a demonstration shape with `solidcraftcnc`.

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
./solidcraftcnc_demo.py > demo.ngc
./solidcraftcnc_demo.py --plot demo.html > demo.ngc
./solidcraftcnc_demo.py 8080 > demo.ngc
./solidcraftcnc_demo.py headless > demo.ngc
```
"""

import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from scgeometry import SCCorner, SCRoundPoly, point_at
from scmachine import SCMachine, SCTool
from scplot import sketch_path, write_plot
from scraftpybind import (
    JSON,
    HeadlessTransport,
    SolidCraftPyBind,
    Transport,
    connect,
)
from shops import cnc_machine, read
from solidcraftcnc import SCCNC, Stage

# A `solidcraft-cli` extracted from SolidCraft's AppImage, for
# headless sessions when none is on the `PATH` (if it is there; it is
# not part of this project).
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parent
    / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
)

# SolidCraft's sketch coordinates are millimeters.
MM_PER_INCH: float = 25.4

# The shop, the machine in it that cuts the plate, and the end mill.
SHOP_FILE: Path = (
    Path(__file__).resolve().parent / "examples/shop/home_shop.toml"
)
MACHINE: str = "Shop mill"
END_MILL: str = "1/4 in 2 flute carbide end mill"

# The bits that bevel and round over top edges, and the bevels' width.
CHAMFER_BIT: str = "1/8 in 90 deg carbide chamfer mill"
ROUNDING_BIT: str = "1/16 in radius carbide corner rounding mill"
BEVEL: float = 0.03


# Class `Part`:
@dataclass(slots=True)
class Part:
    """The demonstration plate's shape, for modeling it in SolidCraft.

    Attributes:
    * `outlines` (`list[SCRoundPoly]`):
      The plate's outline, then the outlines of its holes.
    * `pocket` (`list[SCRoundPoly]`):
      The outline of the pocket in its top, then its islands.
    * `sizes` (`tuple[float, float, float]`):
      The Z of the plate's top, its thickness, and the pocket's depth.
    * `edges` (`list[tuple[SCRoundPoly, Literal["chamfer", "fillet"],
      float]]`):
      The outlines whose top edges are beveled (by their width) or
      rounded over (by their radius).

    Constructor:
    * `Part(outlines, pocket, sizes, edges)`
    """

    # Constructor arguments:
    outlines: list[SCRoundPoly] = field(init=True)
    pocket: list[SCRoundPoly] = field(init=True)
    sizes: tuple[float, float, float] = field(init=True)
    edges: list[tuple[SCRoundPoly, Literal["chamfer", "fillet"], float]] = (
        field(init=True)
    )


# Function `demo_plate()`:
def demo_plate() -> SCRoundPoly:
    """Return the demonstration plate's outline.

    It is a 4 x 3 inch notched rectangle, going counter-clockwise, with
    a different radius at each corner; the notch's inner corner turns
    the other way.

    Returns:
    * (`SCRoundPoly`): The outline.
    """
    return SCRoundPoly(
        "Plate",
        [
            SCCorner(0.0, 0.0, 0.25),
            SCCorner(4.0, 0.0, 0.375),
            SCCorner(4.0, 3.0, 0.125),
            SCCorner(2.0, 3.0, 0.0625),
            SCCorner(2.0, 2.25, 0.1875),
            SCCorner(1.0, 2.25, 0.0),
            SCCorner(0.0, 3.0, 0.25),
        ],
    )


# Function `demo_hole()`:
def demo_hole() -> SCRoundPoly:
    """Return the outline of the hole through the demonstration plate.

    Returns:
    * (`SCRoundPoly`): A rounded 0.6 x 1.1 inch rectangle.
    """
    return SCRoundPoly(
        "Hole",
        [
            SCCorner(3.0, 0.5, 0.1875),
            SCCorner(3.6, 0.5, 0.1875),
            SCCorner(3.6, 1.6, 0.1875),
            SCCorner(3.0, 1.6, 0.1875),
        ],
    )


# Function `demo_pocket()`:
def demo_pocket() -> SCRoundPoly:
    """Return the outline of the pocket in the demonstration plate.

    Returns:
    * (`SCRoundPoly`): A 2.45 x 1.75 inch rectangle with rounded
      corners.
    """
    corner: float = 0.1875
    return SCRoundPoly(
        "Pocket",
        [
            SCCorner(0.3, 0.3, corner),
            SCCorner(2.75, 0.3, corner),
            SCCorner(2.75, 2.05, corner),
            SCCorner(0.3, 2.05, corner),
        ],
    )


# Function `demo_islands()`:
def demo_islands() -> list[SCRoundPoly]:
    """Return the islands left standing in the demonstration's pocket.

    Returns:
    * (`list[SCRoundPoly]`): A triangle and a square with slightly
      rounded corners, and a square whose corner arcs make a circle.
    """
    edge: float = 0.0625
    return [
        SCRoundPoly(
            "Triangle",
            [
                SCCorner(0.65, 0.65, edge),
                SCCorner(1.25, 0.65, edge),
                SCCorner(0.95, 1.2, edge),
            ],
        ),
        SCRoundPoly(
            "Square",
            [
                SCCorner(1.65, 0.65, edge),
                SCCorner(2.15, 0.65, edge),
                SCCorner(2.15, 1.15, edge),
                SCCorner(1.65, 1.15, edge),
            ],
        ),
        SCRoundPoly(
            "Circle",
            [
                SCCorner(1.2, 1.35, 0.2),
                SCCorner(1.6, 1.35, 0.2),
                SCCorner(1.6, 1.75, 0.2),
                SCCorner(1.2, 1.75, 0.2),
            ],
        ),
    ]


# Function `model()`:
def model(where: str, part: Part, cnc: SCCNC, *, path: bool = True) -> int:
    """Model a plate in SolidCraft, in inches.

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.
    * `part` (`Part`): The plate's shape.
    * `cnc` (`SCCNC`):
      The program, whose tool path is drawn beside the plate (which is
      made see-through so that the path inside it shows).
    * `path` (`bool`): False to leave the tool path out (as when
      `sim_solidcraft.py` draws it, one tool at a time).

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

    # Sketch the outlines on the plate's bottom (whose origin is given
    # in millimeters), and extrude only the plate's own profile, so
    # that the holes stay holes.
    top: float
    thickness: float
    depth: float
    top, thickness, depth = part.sizes
    outlines: list[SCRoundPoly] = part.outlines
    with transport:
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
        solidcraft.document.units(units="in")
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
        _edges(solidcraft, part.edges, top * MM_PER_INCH)

        # Draw the tool path, and let it show through the plate.
        if path:
            sketch_path(solidcraft, cnc, MM_PER_INCH)
        solidcraft.appearance.assign(
            bodies=[outlines[0].name], color="#9fb4c8", opacity=0.35
        )
        solidcraft.view.apply(view="iso")
    assert isinstance(finished, dict) and isinstance(cut, dict)
    profiles: JSON = finished["profiles"]
    pockets: JSON = cut["profiles"]
    assert isinstance(profiles, int) and isinstance(pockets, int)
    return profiles + pockets


# Function `_edges()`:
def _edges(
    solidcraft: SolidCraftPyBind,
    edges: Sequence[tuple[SCRoundPoly, Literal["chamfer", "fillet"], float]],
    z: float,
) -> None:
    """Bevel or round over the top edges of outlines on the plate.

    Each edge is picked by a point on it: the middle of each segment
    of its outline, at the top.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): Where the plate is.
    * `edges` (`Sequence[tuple[SCRoundPoly, Literal["chamfer",
      "fillet"], float]]`):
      The outlines, how to finish each, and the size (inches).
    * `z` (`float`): The Z of the plate's top (mm).
    """
    poly: SCRoundPoly
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
            solidcraft.solid.chamfer(edges=points, distance=f"{size} in")
        else:
            solidcraft.solid.fillet(edges=points, radius=f"{size} in")


# Function `_sketch()`:
def _sketch(
    solidcraft: SolidCraftPyBind, outlines: list[SCRoundPoly], z: float
) -> list[str]:
    """Sketch outlines on a horizontal plane.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): Where to sketch them.
    * `outlines` (`list[SCRoundPoly]`): The outlines.
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
    outline: SCRoundPoly
    for outline in outlines[1:]:
        outline.sketch(solidcraft, MM_PER_INCH)
    return curves


# Function `cut_demo()`:
def cut_demo() -> tuple[SCCNC, SCTool]:
    """Cut the demonstration plate on the example shop's mill.

    Returns:
    * (`SCCNC`): The program.
    * (`SCTool`): The corner rounding bit (whose radius the model uses).
    """
    # Rough with the machine's rougher, if it has one, leaving its
    # finish allowance for the end mill; otherwise the end mill does
    # it all.
    plate: SCRoundPoly = demo_plate()
    hole: SCRoundPoly = demo_hole()
    pocket: SCRoundPoly = demo_pocket()
    islands: list[SCRoundPoly] = demo_islands()
    machine: SCMachine = cnc_machine(read(SHOP_FILE), MACHINE)
    end_mill: SCTool = machine.named(END_MILL)
    rougher: SCTool | None = machine.rougher_for(end_mill)
    first: SCTool = end_mill if rougher is None else rougher
    stage: Stage = "full" if rougher is None else "rough"

    # Drill where the first tool will go down, with the largest drill
    # smaller than it (through the plate for its hole and outline).
    cnc: SCCNC = SCCNC("SolidCraftCNC demo", machine)
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
    island: SCRoundPoly
    for island in islands:
        cnc.chamfer(island, BEVEL)
    cnc.chamfer(plate, BEVEL)
    rounding: SCTool = cnc.change_tool(machine.named(ROUNDING_BIT).number)
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
    if arguments[:1] == ["--plot"] and len(arguments) >= 2:
        plot = Path(arguments[1])
        arguments = arguments[2:]
    if len(arguments) > 1 or arguments[:1] == ["--plot"]:
        print(
            f"usage: {sys.argv[0]} [--plot FILE.html] [--no-path] "
            "[PORT|headless]",
            file=sys.stderr,
        )
        return 2

    # Cut it.
    plate: SCRoundPoly = demo_plate()
    hole: SCRoundPoly = demo_hole()
    pocket: SCRoundPoly = demo_pocket()
    islands: list[SCRoundPoly] = demo_islands()
    cnc: SCCNC
    rounding: SCTool
    cnc, rounding = cut_demo()
    print(cnc.gcode(), end="")
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
        part: Part = Part(
            [plate, hole],
            [pocket, *islands],
            (cnc.z_top, 0.5, 0.25),
            [
                (pocket, "chamfer", BEVEL),
                *((island, "chamfer", BEVEL) for island in islands),
                (plate, "chamfer", BEVEL),
                (hole, "fillet", rounding.radius),
            ],
        )
        # A SolidCraft that is not there is reported in one line.
        try:
            profiles: int = model(arguments[0], part, cnc, path=path)
        except OSError as error:
            print(f"solidcraftcnc_demo.py: {error}", file=sys.stderr)
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
