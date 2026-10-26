#!/usr/bin/env python3
# Part 1: These lines look like `#` comments, but they are Python's inline
# script metadata (PEP 723) that the EZPkg bootstrap needs.  Never remove them.
# /// script
# requires-python = ">=3.11"
# dependencies = ["ezpkg>=0.0.1.dev0,<0.1"]
# ///
"""Cut and model a demonstration shape with `solidcraftcnc`.

It prints the G-code for a notched plate, with a hole through it, whose
corners each have their own radius.  With a SolidCraft GUI's control
port (`solidcraft --control PORT`) or `headless`, it also models the
plate in SolidCraft:

```
./solidcraftcnc_demo.py > demo.ngc
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
from solidcraftcnc import SCCNC, SCCorner, SCRoundPoly

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

    It is a 3 x 2 inch notched rectangle, going counter-clockwise, with
    a different radius at each corner; the notch's inner corner turns
    the other way.

    Returns:
    * (`SCRoundPoly`): The outline.
    """
    return SCRoundPoly(
        "Plate",
        [
            SCCorner(0.0, 0.0, 0.25),
            SCCorner(3.0, 0.0, 0.375),
            SCCorner(3.0, 2.0, 0.125),
            SCCorner(1.5, 2.0, 0.0625),
            SCCorner(1.5, 1.25, 0.1875),
            SCCorner(0.75, 1.25, 0.0),
            SCCorner(0.0, 2.0, 0.25),
        ],
    )


# Function `demo_hole()`:
def demo_hole() -> SCRoundPoly:
    """Return the outline of the hole through the demonstration plate.

    Returns:
    * (`SCRoundPoly`): A rounded 0.6 x 0.9 inch rectangle.
    """
    return SCRoundPoly(
        "Hole",
        [
            SCCorner(2.0, 0.5, 0.1875),
            SCCorner(2.6, 0.5, 0.1875),
            SCCorner(2.6, 1.4, 0.1875),
            SCCorner(2.0, 1.4, 0.1875),
        ],
    )


# Function `model()`:
def model(
    where: str, outlines: list[SCRoundPoly], top: float, thickness: float
) -> int:
    """Model a plate in SolidCraft, in inches.

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.
    * `outlines` (`list[SCRoundPoly]`):
      The plate's outline, then the outlines of its holes.
    * `top` (`float`): The Z of the plate's top.
    * `thickness` (`float`): The plate's thickness.

    Returns:
    * (`int`): The number of closed profiles the sketch made (one per
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
    with transport:
        solidcraft: PySolidCraft = PySolidCraft(transport)
        solidcraft.document.units(units="in")
        bottom: float = (top - thickness) * MM_PER_INCH
        solidcraft.sketch.create(
            plane={
                "origin": [0.0, 0.0, bottom],
                "x_dir": [1.0, 0.0, 0.0],
                "y_dir": [0.0, 1.0, 0.0],
            },
            name=outlines[0].name,
        )
        curves: list[str] = outlines[0].sketch(solidcraft, MM_PER_INCH)
        outline: SCRoundPoly
        for outline in outlines[1:]:
            outline.sketch(solidcraft, MM_PER_INCH)
        finished: JSON = solidcraft.sketch.finish()
        solidcraft.solid.extrude(
            distance=f"{thickness} in",
            profiles=[{"curves": curves}],
            body_name=outlines[0].name,
        )
        solidcraft.view.apply(view="iso")
    assert isinstance(finished, dict)
    profiles: JSON = finished["profiles"]
    assert isinstance(profiles, int)
    return profiles


# Function `main()`:
def main() -> int:
    """Print the demonstration's G-code, and model it in SolidCraft.

    The one optional argument is a SolidCraft GUI's control port, or
    `headless`.

    Returns:
    * (`int`): The exit status.
    """
    # Read the arguments.
    if len(sys.argv) > 2:
        print(f"usage: {sys.argv[0]} [PORT|headless]", file=sys.stderr)
        return 2

    # Cut the hole, then the plate out, through a 0.5 inch plate, 0.125
    # inch at a time, with the default 0.25 inch end mill.
    plate: SCRoundPoly = demo_plate()
    hole: SCRoundPoly = demo_hole()
    cnc: SCCNC = SCCNC("SolidCraftCNC demo")
    cnc.profile(hole, -0.5, 0.125, inside=True)
    cnc.profile(plate, -0.5, 0.125)
    cnc.finish()
    print(cnc.gcode(), end="")
    print(f"About {cnc.minutes:.1f} minutes", file=sys.stderr)

    # Model it, if asked to.
    if len(sys.argv) == 2:
        profiles: int = model(sys.argv[1], [plate, hole], cnc.z_top, 0.5)
        print(f"{plate.name}: {profiles} profile(s)", file=sys.stderr)
        if profiles != 2:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
