#!/usr/bin/env python3
# Part 1: These lines look like `#` comments, but they are Python's inline
# script metadata (PEP 723) that the EZPkg bootstrap needs.  Never remove them.
# /// script
# requires-python = ">=3.11"
# dependencies = ["ezpkg>=0.0.1.dev0,<0.1"]
# ///
"""Cut and model a demonstration shape with `solidcraftcnc`.

It prints the G-code for a notched plate, with a hole through it and a
pocket in it, whose corners each have their own radius.  With a
SolidCraft GUI's control port (`solidcraft --control PORT`) or
`headless`, it also models the plate in SolidCraft:

```
./solidcraftcnc_demo.py > demo.ngc
./solidcraftcnc_demo.py --plot demo.html > demo.ngc
./solidcraftcnc_demo.py 8080 > demo.ngc
./solidcraftcnc_demo.py headless > demo.ngc
```
"""

# The bootstrap below must never be edited, so `ruff format` is told
# to leave it alone, and `pylint` is told not to report its compact
# style (from here to the `enable` after it).
# pylint: disable=multiple-statements,missing-function-docstring
# pylint: disable=raise-missing-from,possibly-used-before-assignment
# fmt: off
# Begin the EZPkg bootstrap.  Never edit it.
import hashlib
import importlib
import json
import pathlib
import subprocess
import sys
import urllib.request as req

try:  # Do not edit try block!  See https://pypi.org/project/ezpkg/
    s = "find ezpkg"; t = pathlib.Path.home()/".ezpkg"; w = t/"ezpkg.whl"
    def g(u):  # Fetch u, with curl if this Python has no certificates.
        try: return req.urlopen(u, None, 60).read()
        except req.URLError as y: z = y  # As on python.org's macOS Python.
        try: return subprocess.run(["curl", "-fsSL", u],
                                   capture_output=True, check=True).stdout
        except Exception: raise z from None
    try: m = None; m = importlib.import_module("ezpkg")  # Already importable?
    except ImportError: pass
    if m is None and not w.is_file():  # Not downloaded yet.
        s = "download ezpkg"; d = g("https://pypi.org/pypi/ezpkg/json")
        e = next(e for e in json.loads(d)["urls"] if e["url"][-4:] == ".whl")
        r = g(e["url"])
        if hashlib.sha256(r).hexdigest() != e["digests"]["sha256"]:
            raise ValueError(f"{e['filename']} fails its SHA-256 check")
        t.mkdir(parents=True, exist_ok=True); p = t/"ezpkg.part"
        p.write_bytes(r); p.replace(w)  # The rename is atomic.
    if m is None:  # Python imports it straight from the wheel.
        s = "import ezpkg"; sys.path.insert(0, str(w))
        m = importlib.import_module("ezpkg")
    s = "fetch packages"; m.EZPkg().install(bootstrap="2026-10-23")
except Exception as x:
    raise SystemExit(f"ezpkg: {s} failed: {x!r}")  # Do not edit try block!
# End the EZPkg bootstrap.  Your imports go below it.
# fmt: on
# pylint: enable=multiple-statements,missing-function-docstring
# pylint: enable=raise-missing-from,possibly-used-before-assignment

# The bootstrap has already imported `sys`.
import shutil
from pathlib import Path

from pysolidcraft import (
    JSON,
    HeadlessTransport,
    PySolidCraft,
    Transport,
    connect,
)
from scgeometry import SCCorner, SCRoundPoly
from scplot import sketch_path, write_plot
from solidcraftcnc import SCCNC

# The `solidcraft-cli` extracted from the SolidCraft project's
# AppImage, for headless sessions when none is on the `PATH`.
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parent
    / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
)

# SolidCraft's sketch coordinates are millimeters.
MM_PER_INCH: float = 25.4


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

    It is a dumbbell: two 0.9 x 1.5 inch lobes joined by a 0.4 inch
    wide neck, so that its rings come apart into one tree per lobe.

    Returns:
    * (`SCRoundPoly`): The outline.
    """
    corner: float = 0.1875
    neck: float = 0.0625
    return SCRoundPoly(
        "Pocket",
        [
            SCCorner(0.4, 0.4, corner),
            SCCorner(1.3, 0.4, corner),
            SCCorner(1.3, 0.95, neck),
            SCCorner(1.7, 0.95, neck),
            SCCorner(1.7, 0.4, corner),
            SCCorner(2.6, 0.4, corner),
            SCCorner(2.6, 1.9, corner),
            SCCorner(1.7, 1.9, corner),
            SCCorner(1.7, 1.35, neck),
            SCCorner(1.3, 1.35, neck),
            SCCorner(1.3, 1.9, corner),
            SCCorner(0.4, 1.9, corner),
        ],
    )


# Function `model()`:
def model(
    where: str,
    outlines: list[SCRoundPoly],
    pocket: SCRoundPoly,
    sizes: tuple[float, float, float],
    cnc: SCCNC,
) -> int:
    """Model a plate in SolidCraft, in inches.

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.
    * `outlines` (`list[SCRoundPoly]`):
      The plate's outline, then the outlines of its holes.
    * `pocket` (`SCRoundPoly`): The outline of the pocket in its top.
    * `sizes` (`tuple[float, float, float]`):
      The Z of the plate's top, its thickness, and the pocket's depth.
    * `cnc` (`SCCNC`):
      The program, whose tool path is drawn beside the plate (which is
      made see-through so that the path inside it shows).

    Returns:
    * (`int`): The number of closed profiles the sketches made (one per
      outline when they all closed).
    """
    # A headless session uses the extracted `solidcraft-cli` unless
    # one is on the `PATH`.
    transport: Transport = connect(where)
    if (
        isinstance(transport, HeadlessTransport)
        and shutil.which(transport.cli) is None
    ):
        transport = HeadlessTransport(cli=str(SOLIDCRAFT_CLI))

    # Sketch the outlines on the plate's bottom (whose origin is given
    # in millimeters), and extrude only the plate's own profile, so
    # that the holes stay holes.
    top: float
    thickness: float
    depth: float
    top, thickness, depth = sizes
    with transport:
        solidcraft: PySolidCraft = PySolidCraft(transport)
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

        # Cut the pocket down from the top.
        curves = _sketch(solidcraft, [pocket], top * MM_PER_INCH)
        cut: JSON = solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=f"{depth} in",
            direction="negative",
            operation="cut",
            profiles=[{"curves": curves}],
        )

        # Draw the tool path, and let it show through the plate.
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


# Function `_sketch()`:
def _sketch(
    solidcraft: PySolidCraft, outlines: list[SCRoundPoly], z: float
) -> list[str]:
    """Sketch outlines on a horizontal plane.

    Arguments:
    * `solidcraft` (`PySolidCraft`): Where to sketch them.
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
    if arguments[:1] == ["--plot"] and len(arguments) >= 2:
        plot = Path(arguments[1])
        arguments = arguments[2:]
    if len(arguments) > 1 or arguments[:1] == ["--plot"]:
        print(
            f"usage: {sys.argv[0]} [--plot FILE.html] [PORT|headless]",
            file=sys.stderr,
        )
        return 2

    # Clear the 0.25 inch deep pocket, cut the hole, then cut the plate
    # out, through a 0.5 inch plate, 0.125 inch at a time, with the
    # default 0.25 inch end mill.
    plate: SCRoundPoly = demo_plate()
    hole: SCRoundPoly = demo_hole()
    pocket: SCRoundPoly = demo_pocket()
    cnc: SCCNC = SCCNC("SolidCraftCNC demo")
    cnc.pocket(pocket, -0.25, 0.125)
    cnc.profile(hole, -0.5, 0.125, inside=True)
    cnc.profile(plate, -0.5, 0.125)
    cnc.finish()
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
            ],
            "Demo Plate Tool Path",
        )
        print(f"Wrote {plot}", file=sys.stderr)

    # Model it, if asked to.
    if arguments:
        profiles: int = model(
            arguments[0],
            [plate, hole],
            pocket,
            (cnc.z_top, 0.5, 0.25),
            cnc,
        )
        print(f"{plate.name}: {profiles} profile(s)", file=sys.stderr)
        if profiles != 3:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
