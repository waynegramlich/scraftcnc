#!/usr/bin/env python3
"""Build a rectangular plate with a hole in each corner.

The plate is drawn live in a SolidCraft GUI started with `solidcraft
--control PORT`, or in a headless session (no window), and then
exported as a STEP file:

```
python3 -m scraftcnc.pybind.examples.plate_with_holes 8080 plate.step
python3 -m scraftcnc.pybind.examples.plate_with_holes headless plate.step
```

Run it from the root of the `scraftcnc` repository (or with
`PYTHONPATH` set to it).

It is the first `scraftpybind` example; in CadQuery the same plate is

```
cq.Workplane("XY").box(100, 60, 10).faces(">Z").workplane()
    .rect(80, 40, forConstruction=True).vertices().hole(8)
```
"""

# The example ends the way `scraftpybind.main()` does, since it is
# meant to be read on its own.
# pylint: disable=duplicate-code

import sys
from pathlib import Path

from ..scraftpybind import JSON, PyBind, connect


# Function `plate_with_holes()`:
# Each dimension is its own keyword-only argument, as in CadQuery.
def plate_with_holes(  # pylint: disable=too-many-arguments  # pragma: no cover
    solidcraft: PyBind,
    *,
    length: float,
    width: float,
    thickness: float,
    hole_diameter: float,
    inset: float,
) -> JSON:
    """Build a plate with a through hole near each corner.

    The plate is centered on the origin of the XY plane and extruded up
    from it.

    Arguments:
    * `solidcraft` (`PyBind`): Where to build it.
    * `length` (`float`): The plate's length, along X (mm).
    * `width` (`float`): Its width, along Y (mm).
    * `thickness` (`float`): Its thickness, along Z (mm).
    * `hole_diameter` (`float`): Each hole's diameter (mm).
    * `inset` (`float`):
      How far each hole's center is from the two nearest edges (mm).

    Returns:
    * (`JSON`): The extrusion's result (the feature and the body).

    Raises:
    * `ValueError`: If the holes do not fit inside the plate.
    """
    # The holes must lie inside the plate without touching each other.
    if not hole_diameter / 2 < inset < min(length, width) / 2:
        raise ValueError(f"{inset=} does not fit {hole_diameter=}")

    # Sketch the outline and one circle per corner.
    solidcraft.sketch.create(plane="XY", name="Plate")
    outline: JSON = solidcraft.sketch.rectangle_center(
        center=(0, 0), corner=(length / 2, width / 2)
    )
    x: float = length / 2 - inset
    y: float = width / 2 - inset
    corner: tuple[float, float]
    for corner in ((-x, -y), (x, -y), (x, y), (-x, y)):
        solidcraft.sketch.circle_center(center=corner, diameter=hole_diameter)
    solidcraft.sketch.finish()

    # Extrude only the profile inside the outline, so that the circles
    # stay holes instead of being extruded as well.
    assert isinstance(outline, dict)
    return solidcraft.solid.extrude(
        distance=thickness,
        profiles=[{"curves": outline["curves"]}],
        body_name="Plate",
    )


# Function `main()`:
def main() -> int:  # pragma: no cover
    """Build the plate, show it in the GUI, and export it.

    The arguments are the GUI's control port (or `headless`) and the
    STEP file to write (default `plate_with_holes.step`).

    Returns:
    * (`int`): The exit status.
    """
    # Read the arguments.
    if len(sys.argv) not in (2, 3):
        print(
            f"usage: {sys.argv[0]} PORT|headless [FILE.step]", file=sys.stderr
        )
        return 2
    step: Path = Path(
        sys.argv[2] if len(sys.argv) == 3 else "plate_with_holes.step"
    ).resolve()

    # Build the plate, colour it and show it (headless, the view is
    # still set, though nobody sees it).
    with connect(sys.argv[1]) as transport:
        solidcraft: PyBind = PyBind(transport)
        plate_with_holes(
            solidcraft,
            length=100,
            width=60,
            thickness=10,
            hole_diameter=8,
            inset=10,
        )
        solidcraft.appearance.assign(bodies=["Plate"], color="#ADD8E6")
        solidcraft.view.apply(view="iso")

        # Export it.
        solidcraft.file.export(path=str(step))
    print(f"Wrote {step}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
