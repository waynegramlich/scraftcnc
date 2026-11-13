# Tool Models

This document is written by `scraftcam/tooling/tool_models.py`
(`python3 -m scraftcam.tooling.tool_models`), from the code; do not
edit it.

Each model below can be made from a description of it, in any of three
forms, which all have the same keys: JSON on a command line, a Python
dictionary, or an entry in a tools file (`Shops.md`).  The letters on
the sketches mean the same size on every sketch.  The tables give no
values: read a catalog for those, or make them up.  The sketches are of
one sample, so their proportions are only a guide.

A size is a string with its unit (`"1/2 in"`, `"12.7 mm"`).  A length
takes `in`, `inch`, `inches`, `ft`, `mm`, `cm`.

The JSON and Python forms need a SolidCraft to talk to: a port number,
from `solidcraft --control 8080`, or `headless` for `solidcraft-cli`.
They add the model to the design at the origin, standing on its tip.
A description with a problem is refused before SolidCraft is touched:
the JSON form prints every problem and exits with 1, and the Python
form raises `ShopError`.

## Contents

* [Python Interface](#python-interface)
* [End Mill](#end-mill)
* [Drill](#drill)
* [Chamfer Mill](#chamfer-mill)
* [Corner Rounding Mill](#corner-rounding-mill)
* [Double Angle Cutter](#double-angle-cutter)
* [Single End Countersink](#single-end-countersink)
* [Double End Countersink](#double-end-countersink)
* [Machine Vise](#machine-vise)
* [Jaw Plate](#jaw-plate)
* [Parallel](#parallel)
* [Grid Plate](#grid-plate)

## Python Interface

### `scraftcam.tooling.cutter_models.model_description`

```python
scraftcam.tooling.cutter_models.model_description(
    solidcraft: PyBind,
    description: dict[str, object],
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
    cache: ModelCache | None = None,
) -> ModeledTool
```

Model one tool from its description.

Arguments:
* `solidcraft` (`PyBind`): The SolidCraft session.
* `description` (`dict[str, object]`):
  The tool, with its `kind`, as `shops.check_tool()` takes it.  Its
  `name`, if any, names the body.
* `at` (`tuple[float, float, float]`):
  Where its tip goes (inches).
* `cache` (`ModelCache | None`):
  Where to keep its body between runs, or `None` to build it.

Returns:
* (`ModeledTool`): What was made, free to move.

Raises:
* `ShopError`:
  If the description has any problem, before SolidCraft is touched.
* `SolidCraftError`: If SolidCraft refuses a command.
* `FileNotFoundError`: If no SolidCraft has the port.
* `ConnectionError`:
  If nothing listens on the port, or SolidCraft goes away.

### `scraftcam.tooling.cutter_models.ModeledTool`

```python
scraftcam.tooling.cutter_models.ModeledTool(
    body: str,
    sketch: str,
    occurrence: str,
)
```

A tool in SolidCraft: a component with its body and flute lines.

Attributes:
* `body` (`str`): Its body's name.
* `sketch` (`str`): The name of its flute lines' sketch.
* `occurrence` (`str`): Its component's occurrence, for moving it.

```python
ModeledTool.items() -> list[str]
```

Return what `browser.visibility` shows or hides for the tool.

### `scraftcam.shops.check_tool`

```python
scraftcam.shops.check_tool(
    description: dict[str, object],
) -> tuple[str, dict[str, object]]
```

Check one tool's description, as for a model of it.

It takes the keys of its `kind` of tool (`Shops.md`), except that
`name` and `unique_id` get stand-ins, since a model does not need
them.

Arguments:
* `description` (`dict[str, object]`):
  The tool, with its `kind` (such as `"end_mill"`).

Returns:
* (`tuple[str, dict[str, object]]`):
  The list it goes in, in a tools file (a key of `CNC_KINDS`), and
  the tool, as `read()` gives it.

Raises:
* `ShopError`: With every problem found.

### `scraftcam.shops.ShopError`

```python
scraftcam.shops.ShopError(problems: list[str])
```

The problems found in a shop description.

Attributes:
* `problems` (`list[str]`):
  Each problem, as `FILE:LINE: KEY: message`.

### `scraftcam.pybind.scraftpybind.connect`

```python
scraftcam.pybind.scraftpybind.connect(where: str) -> Transport
```

Return a transport for a port number, or for `headless`.

Arguments:
* `where` (`str`):
  A GUI's control port (e.g. `8080`), or `headless` for a session
  with no window.

Returns:
* (`Transport`): The transport, which connects on first use.

Raises:
* `ValueError`: If `where` is neither.

### `scraftcam.pybind.scraftpybind.PyBind`

```python
scraftcam.pybind.scraftpybind.PyBind(transport: Transport)
```

The top level of `scraftpybind`: SolidCraft's commands.

### `scraftcam.pybind.scraftpybind.SolidCraftError`

```python
scraftcam.pybind.scraftpybind.SolidCraftError(
    method: str,
    error: str,
    running: bool,
    busy: bool,
)
```

A SolidCraft request that failed.

Attributes:
* `method` (`str`): The request's method (e.g. `engine.execute`).
* `error` (`str`): The error text SolidCraft sent back.
* `running` (`bool`):
  True when the request timed out but is still running in the app;
  it has not failed, so it must not simply be sent again.
* `busy` (`bool`):
  True when the request was refused, without running, because an
  earlier request on this connection is still running.

## End Mill

An end mill: square, ball or bull nose (a square end with rounded
corners), and perhaps a rougher.

![End Mill sketch](docs/tool_models/end_mill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `C`    | Length | `corner_radius`: Optional. A bull nose's corners.         |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `L`    | Length | `length_of_cut`: How deep it can cut (LOC).               |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |

Other keys:

* `flutes` (integer): How many flutes.
* `end` (one of `square`, `ball`, `bull_nose`): The shape of its end.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "end_mill",
  "material": "carbide",
  "finish": "uncoated",
  "diameter": "1/2 in",
  "shank": "3/8 in",
  "length_of_cut": "1 in",
  "overall_length": "3 in",
  "flutes": 4,
  "end": "bull_nose",
  "corner_radius": "1/8 in"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "end_mill",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "1/2 in",
            "shank": "3/8 in",
            "length_of_cut": "1 in",
            "overall_length": "3 in",
            "flutes": 4,
            "end": "bull_nose",
            "corner_radius": "1/8 in",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample end mill"
kind = "end_mill"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "1/2 in"
length_of_cut = "1 in"
flutes = 4
end = "bull_nose"
corner_radius = "1/8 in"
shank = "3/8 in"
overall_length = "3 in"
material = "carbide"
finish = "uncoated"
```

## Drill

A twist drill.

![Drill sketch](docs/tool_models/drill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `L`    | Length | `length_of_cut`: How deep it can cut (LOC).               |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `P`    | Angle  | `point_angle`: The included angle.                        |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `Sl`   | Length | `shank_length`: Optional. How far its shank comes down    |
|        |        | from its top; if not given, a `shank` starts where its    |
|        |        | flutes stop.                                              |

Other keys:

* `flutes` (integer): How many flutes (2 if not given).
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "drill",
  "material": "HSS",
  "finish": "black oxide",
  "diameter": "5/8 in",
  "shank": "1/2 in",
  "shank_length": "1-1/2 in",
  "length_of_cut": "2-1/2 in",
  "overall_length": "4-1/2 in",
  "point_angle": "118 deg"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "drill",
            "material": "HSS",
            "finish": "black oxide",
            "diameter": "5/8 in",
            "shank": "1/2 in",
            "shank_length": "1-1/2 in",
            "length_of_cut": "2-1/2 in",
            "overall_length": "4-1/2 in",
            "point_angle": "118 deg",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample drill"
kind = "drill"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "5/8 in"
length_of_cut = "2-1/2 in"
point_angle = "118 deg"
shank_length = "1-1/2 in"
shank = "1/2 in"
overall_length = "4-1/2 in"
material = "HSS"
finish = "black oxide"
```

## Chamfer Mill

A chamfer mill (a V-bit), which bevels top edges.

![Chamfer Mill sketch](docs/tool_models/chamfer_mill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The included angle (90 deg makes 45 deg bevels). |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `T`    | Length | `tip_diameter`: The diameter at its tip.                  |

Other keys:

* `flutes` (integer): How many flutes.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "chamfer_mill",
  "material": "carbide",
  "finish": "uncoated",
  "diameter": "1/2 in",
  "shank": "1/2 in",
  "tip_diameter": "1/4 in",
  "overall_length": "2 in",
  "angle": "90 deg"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "chamfer_mill",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "1/2 in",
            "shank": "1/2 in",
            "tip_diameter": "1/4 in",
            "overall_length": "2 in",
            "angle": "90 deg",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample chamfer mill"
kind = "chamfer_mill"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "1/2 in"
tip_diameter = "1/4 in"
angle = "90 deg"
shank = "1/2 in"
overall_length = "2 in"
material = "carbide"
finish = "uncoated"
```

## Corner Rounding Mill

A corner rounding mill, which rounds top edges over to its radius.  Its
tip (a pilot) rides along the wall below.

![Corner Rounding Mill sketch](docs/tool_models/corner_rounding_mill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `R`    | Length | `radius`: The radius it rounds edges to.                  |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `T`    | Length | `tip_diameter`: The diameter at its tip.                  |

Other keys:

* `flutes` (integer): How many flutes.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "corner_rounding_mill",
  "material": "carbide",
  "finish": "uncoated",
  "radius": "1/4 in",
  "tip_diameter": "1/4 in",
  "shank": "3/4 in",
  "overall_length": "2-1/2 in"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "corner_rounding_mill",
            "material": "carbide",
            "finish": "uncoated",
            "radius": "1/4 in",
            "tip_diameter": "1/4 in",
            "shank": "3/4 in",
            "overall_length": "2-1/2 in",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample corner rounding mill"
kind = "corner_rounding_mill"
language = "English"
version = "0.0.1"
unique_id = 1
radius = "1/4 in"
tip_diameter = "1/4 in"
shank = "3/4 in"
overall_length = "2-1/2 in"
material = "carbide"
finish = "uncoated"
```

## Double Angle Cutter

A pointed double angle shank cutter: a cone above and a cone below its
widest point, on a thin neck, so it can chamfer bottom edges (back
chamfering) as well as top ones.

![Double Angle Cutter sketch](docs/tool_models/double_angle_cutter.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The included angle of the two cones together.    |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `N`    | Length | `neck_diameter`: Optional. The neck's diameter.           |
| `Nl`   | Length | `neck_length`: Optional. The neck's length (L3), from the |
|        |        | shank to the cutter.                                      |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `W`    | Length | `width`: The height of the cutter (L2), point to point.   |

Other keys:

* `flutes` (integer): How many flutes.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "double_angle_cutter",
  "material": "carbide",
  "finish": "uncoated",
  "diameter": "3/4 in",
  "shank": "1/2 in",
  "width": "3/8 in",
  "neck_diameter": "1/4 in",
  "neck_length": "1/2 in",
  "overall_length": "2-1/2 in",
  "angle": "90 deg"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "double_angle_cutter",
            "material": "carbide",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "shank": "1/2 in",
            "width": "3/8 in",
            "neck_diameter": "1/4 in",
            "neck_length": "1/2 in",
            "overall_length": "2-1/2 in",
            "angle": "90 deg",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample double angle cutter"
kind = "double_angle_cutter"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "3/4 in"
angle = "90 deg"
width = "3/8 in"
neck_diameter = "1/4 in"
neck_length = "1/2 in"
shank = "1/2 in"
overall_length = "2-1/2 in"
material = "carbide"
finish = "uncoated"
```

## Single End Countersink

A combined drill and countersink on a shank: a small drill at its tip,
joined to its body by a cone.  It can not go in a `tool_table` yet.

![Single End Countersink sketch](docs/tool_models/single_countersink.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The countersink's included angle.                |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `Dd`   | Length | `drill_diameter`: The diameter of the small drill at its  |
|        |        | tip.                                                      |
| `Dl`   | Length | `drill_length`: Optional. How far the small drill reaches |
|        |        | from its tip (its diameter if not given).                 |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `P`    | Angle  | `point_angle`: Optional. The included angle of the small  |
|        |        | drill's point (90 deg if not given).                      |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |

Other keys:

* `flutes` (integer): How many flutes (2 if not given).
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "single_countersink",
  "material": "HSS",
  "finish": "uncoated",
  "diameter": "3/4 in",
  "shank": "3/4 in",
  "drill_diameter": "3/8 in",
  "drill_length": "1/2 in",
  "overall_length": "2-1/2 in",
  "angle": "60 deg",
  "point_angle": "90 deg"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "single_countersink",
            "material": "HSS",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "shank": "3/4 in",
            "drill_diameter": "3/8 in",
            "drill_length": "1/2 in",
            "overall_length": "2-1/2 in",
            "angle": "60 deg",
            "point_angle": "90 deg",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample single end countersink"
kind = "single_countersink"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "3/4 in"
drill_diameter = "3/8 in"
drill_length = "1/2 in"
angle = "60 deg"
point_angle = "90 deg"
shank = "3/4 in"
overall_length = "2-1/2 in"
material = "HSS"
finish = "uncoated"
```

## Double End Countersink

A combined drill and countersink, cut at both ends (a center drill).
Its `shank` means nothing, since it is cut at both ends.  It can not go
in a `tool_table` yet.

![Double End Countersink sketch](docs/tool_models/double_countersink.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The countersink's included angle.                |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `Dd`   | Length | `drill_diameter`: The diameter of the small drill at its  |
|        |        | tip.                                                      |
| `Dl`   | Length | `drill_length`: Optional. How far the small drill reaches |
|        |        | from its tip (its diameter if not given).                 |
| `O`    | Length | `overall_length`: Its whole length (OAL).                 |
| `P`    | Angle  | `point_angle`: Optional. The included angle of the small  |
|        |        | drill's point (90 deg if not given).                      |

Other keys:

* `flutes` (integer): How many flutes (2 if not given).
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
python3 -m scraftcam.tooling.cutter_models 8080 '{
  "kind": "double_countersink",
  "material": "HSS",
  "finish": "uncoated",
  "diameter": "3/4 in",
  "drill_diameter": "3/8 in",
  "drill_length": "1/2 in",
  "overall_length": "3 in",
  "angle": "60 deg",
  "point_angle": "90 deg"
}'
```

Python:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.cutter_models import model_description

with connect("8080") as transport:
    model_description(
        PyBind(transport),
        {
            "kind": "double_countersink",
            "material": "HSS",
            "finish": "uncoated",
            "diameter": "3/4 in",
            "drill_diameter": "3/8 in",
            "drill_length": "1/2 in",
            "overall_length": "3 in",
            "angle": "60 deg",
            "point_angle": "90 deg",
        },
    )
```

A tool's file, in a shop's `tools/`:

```toml
name = "Sample double end countersink"
kind = "double_countersink"
language = "English"
version = "0.0.1"
unique_id = 1
diameter = "3/4 in"
drill_diameter = "3/8 in"
drill_length = "1/2 in"
angle = "60 deg"
point_angle = "90 deg"
overall_length = "3 in"
material = "HSS"
finish = "uncoated"
```

## Machine Vise

A machine vise, of the kind that Kurt makes.

A picture rather than a true vise: enough to know what it is.  A real
Kurt is one casting; the model stacks it in layers, named from the
bottom up: the base, the body and the bed.  On the bed sit the fixed jaw
and the movable jaw, each with a jaw plate on its clamping face.

The base and the body are blocks, stacked and centered on one another.
They have notches in both sides that line up, for hold downs: the body's
are bigger, so that a box wrench fits around the nut.  The bed is two
rails that run the whole length, with an end block between them at each
end.  Under the opening that leaves, the body has a pocket down to the
base, where the lead screw shows.

The lead screw is a cylinder along X, from the pocket's -X end out
through a hole in the body's +X end, ending in an extruded hexagon.

The jaws sit on the bed: the fixed jaw at the -X end, away from the
hexagon, and the movable jaw opening toward +X.  Under the movable jaw,
a slider fits between the rails and reaches down through the pocket,
with a hole that the lead screw goes through.  It starts at the jaw's
clamping face and is shorter than the jaw by an end block's length, so
that the jaw reaches the bed's +X end as the slider meets the end block.
The jaw plates do the actual clamping; each has two holes for the screws
that hold it on.

All lengths are in millimeters.

The sketches are of `tools.KURT_D688`, opened as far as it goes.
Hidden edges are dashed.  Its jaw plates are separate parts,
described in [Jaw Plate](#jaw-plate).

Top:

![Machine vise, top](docs/tool_models/machine_vise_top.svg)

Back (the hexagon's end):

![Machine vise, back](docs/tool_models/machine_vise_back.svg)

Side (from -Y):

![Machine vise, side](docs/tool_models/machine_vise_side.svg)

| Letter | Units   | Description                                              |
| ------ | ------- | -------------------------------------------------------- |
| Fl     | Length  | `fixed_jaw.length`: The jaw that stays put: its size     |
|        |         | along X, the lead screw's direction.                     |
| Mo     | Length  | `max_opening`: The largest gap between the jaw plates.   |
| Ml     | Length  | `movable_jaw.length`: The jaw that the lead screw moves: |
|        |         | its size along X, the lead screw's direction.            |
| Lo     | Length  | `lead_screw_stick_out`: How far the lead screw's         |
|        |         | cylinder reaches past the body's +X end.                 |
| H      | Length  | `hex_length`: The hexagon's size along X.                |
| Bl     | Length  | `base.length`: The bottom layer: its size along X, the   |
|        |         | lead screw's direction.                                  |
| Bonw   | Length  | `body_notches.width`: The notches in the body, at the    |
|        |         | same places but bigger: a notch's size along X.          |
| Bnw    | Length  | `base_notches.width`: The notches in the base: a notch's |
|        |         | size along X.                                            |
| E      | Length  | `end_block_length`: An end block's size along X.         |
| Bonc   | Lengths | `body_notches.centers`: The notches in the body, at the  |
|        |         | same places but bigger: the X of each notch's center     |
|        |         | (X1, X2, ...), from the block's center, from most        |
|        |         | negative up. Empty, the sides are plain.                 |
| Bnc    | Lengths | `base_notches.centers`: The notches in the base: the X   |
|        |         | of each notch's center (X1, X2, ...), from the block's   |
|        |         | center, from most negative up. Empty, the sides are      |
|        |         | plain.                                                   |
| Bol    | Length  | `body.length`: The layer on the base: its size along X,  |
|        |         | the lead screw's direction.                              |
| Bnd    | Length  | `base_notches.depth`: The notches in the base: how far a |
|        |         | notch reaches in from the side.                          |
| Bond   | Length  | `body_notches.depth`: The notches in the body, at the    |
|        |         | same places but bigger: how far a notch reaches in from  |
|        |         | the side.                                                |
| R      | Length  | `rail_width`: A bed rail's size along Y.                 |
| Rg     | Length  | `rail_gap`: The distance between the rails.              |
| Fw     | Length  | `fixed_jaw.width`: The jaw that stays put: its size      |
|        |         | along Y.                                                 |
| Bni    | Length  | `base_notches.inner_radius`: The notches in the base:    |
|        |         | the radius of its two corners farthest in.               |
| Bno    | Length  | `base_notches.outer_radius`: The notches in the base:    |
|        |         | the radius of its two corners where it meets the side.   |
| Bc     | Length  | `base.corner_radius`: The bottom layer: the radius of    |
|        |         | its four corners.                                        |
| Boni   | Length  | `body_notches.inner_radius`: The notches in the body, at |
|        |         | the same places but bigger: the radius of its two        |
|        |         | corners farthest in.                                     |
| Bono   | Length  | `body_notches.outer_radius`: The notches in the body, at |
|        |         | the same places but bigger: the radius of its two        |
|        |         | corners where it meets the side.                         |
| Boc    | Length  | `body.corner_radius`: The layer on the base: the radius  |
|        |         | of its four corners.                                     |
| Mw     | Length  | `movable_jaw.width`: The jaw that the lead screw moves:  |
|        |         | its size along Y.                                        |
| Bw     | Length  | `base.width`: The bottom layer: its size along Y.        |
| Bow    | Length  | `body.width`: The layer on the base: its size along Y.   |
| L      | Length  | `lead_screw_height`: The height of the lead screw's axis |
|        |         | above the base's bottom.                                 |
| Hs     | Length  | `hex_size`: The size across the flats of the hexagon on  |
|        |         | the lead screw's end.                                    |
| Ls     | Length  | `lead_screw_diameter`: The lead screw's diameter.        |
| Lh     | Length  | `lead_screw_hole_diameter`: The diameter of the hole for |
|        |         | the lead screw in the body's end.                        |
| Bh     | Length  | `base.height`: The bottom layer: its size along Z.       |
| Boh    | Length  | `body.height`: The layer on the base: its size along Z.  |
| Rh     | Length  | `rail_height`: The height of the bed: its rails and end  |
|        |         | blocks.                                                  |
| Fh     | Length  | `fixed_jaw.height`: The jaw that stays put: its size     |
|        |         | along Z.                                                 |
| Mh     | Length  | `movable_jaw.height`: The jaw that the lead screw moves: |
|        |         | its size along Z.                                        |

Not drawn (square on the sample): `fixed_jaw.corner_radius`,
`movable_jaw.corner_radius`.

A machine vise has no tools file entry yet, so it is made in
Python, in millimeters, like `tools.KURT_D688`:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.tools import KURT_D688

with connect("8080") as transport:
    KURT_D688.model(PyBind(transport), opening=76.2)
```

A setup file (`examples/setup/`) names one by its `type`:

```json
{
  "kind": "machine_vise",
  "type": "Kurt D688",
  "opening": "6 in",
  "location": [
    "0 in",
    "-3.15 in"
  ],
  "height": "0 in",
  "orientation": "-90 deg"
}
```

### `scraftcam.tooling.tools.MachineVise`

```python
scraftcam.tooling.tools.MachineVise(
    name: str,
    base: ViseBlock,
    body: ViseBlock,
    base_notches: ViseNotches,
    body_notches: ViseNotches,
    rail_width: float,
    rail_height: float,
    rail_gap: float,
    end_block_length: float,
    fixed_jaw: ViseBlock,
    movable_jaw: ViseBlock,
    jaw_plate: JawPlate,
    max_opening: float,
    lead_screw_diameter: float,
    lead_screw_stick_out: float,
    lead_screw_height: float,
    lead_screw_hole_diameter: float,
    hex_size: float,
    hex_length: float,
)
```

A machine vise, of the kind that Kurt makes.

A picture rather than a true vise: enough to know what it is.  A real
Kurt is one casting; the model stacks it in layers, named from the
bottom up: the base, the body and the bed.  On the bed sit the fixed
jaw and the movable jaw, each with a jaw plate on its clamping face.

The base and the body are blocks, stacked and centered on one
another.  They have notches in both sides that line up, for hold
downs: the body's are bigger, so that a box wrench fits around the
nut.  The bed is two rails that run the whole length, with an end
block between them at each end.  Under the opening that leaves, the
body has a pocket down to the base, where the lead screw shows.

The lead screw is a cylinder along X, from the pocket's -X end out
through a hole in the body's +X end, ending in an extruded hexagon.

The jaws sit on the bed: the fixed jaw at the -X end, away from the
hexagon, and the movable jaw opening toward +X.  Under the movable
jaw, a slider fits between the rails and reaches down through the
pocket, with a hole that the lead screw goes through.  It starts at
the jaw's clamping face and is shorter than the jaw by an end block's
length, so that the jaw reaches the bed's +X end as the slider meets
the end block.  The jaw plates do the actual clamping; each has two
holes for the screws that hold it on.

All lengths are in millimeters.

Attributes:
* `name` (`str`): What it is.
* `base` (`ViseBlock`): The bottom layer.
* `body` (`ViseBlock`): The layer on the base.
* `base_notches` (`ViseNotches`): The notches in the base.
* `body_notches` (`ViseNotches`):
  The notches in the body, at the same places but bigger.
* `rail_width` (`float`): A bed rail's size along Y.
* `rail_height` (`float`): The height of the bed: its rails and end
  blocks.
* `rail_gap` (`float`): The distance between the rails.
* `end_block_length` (`float`): An end block's size along X.
* `fixed_jaw` (`ViseBlock`): The jaw that stays put.
* `movable_jaw` (`ViseBlock`): The jaw that the lead screw moves.
* `jaw_plate` (`JawPlate`): The jaw plate on each jaw.
* `max_opening` (`float`): The largest gap between the jaw plates.
* `lead_screw_diameter` (`float`): The lead screw's diameter.
* `lead_screw_stick_out` (`float`):
  How far the lead screw's cylinder reaches past the body's +X end.
* `lead_screw_height` (`float`):
  The height of the lead screw's axis above the base's bottom.
* `lead_screw_hole_diameter` (`float`):
  The diameter of the hole for the lead screw in the body's end.
* `hex_size` (`float`):
  The size across the flats of the hexagon on the lead screw's end.
* `hex_length` (`float`): The hexagon's size along X.

```python
MachineVise.named(name: str) -> 'MachineVise'
```

Return the machine vise with a key or name.

```python
MachineVise.key() -> str
```

Return its key in `REGISTRY` (e.g. `kurt_d688`).

```python
MachineVise.bed_top() -> float
```

Return the height of the top of the bed, above the base's bottom.

```python
MachineVise.overall_length() -> float
```

Return the vise's length, out to the end of the hexagon.

```python
MachineVise.opening_length() -> float
```

Return the length of the opening between the end blocks.

```python
MachineVise.slider() -> ViseBlock
```

Return the block under the movable jaw, between the rails.

```python
MachineVise.slider_volume() -> float
```

Return the volume the slider's model should have.

```python
MachineVise.jaw_plate_volume() -> float
```

Return the volume a jaw plate's model should have.

```python
MachineVise.movable_face(opening: float) -> float
```

Return the X of the movable jaw's clamping face, behind its plate.

```python
MachineVise.gap_center(opening: float) -> float
```

Return the X of the middle of the gap between the jaw plates.

```python
MachineVise.hexagon() -> list[tuple[float, float]]
```

Return the corners of the lead screw's hexagon, flats up and down.

```python
MachineVise.body_volume() -> float
```

Return the volume the body's model should have.

```python
MachineVise.lead_screw_volume() -> float
```

Return the volume the lead screw's model should have.

```python
MachineVise.keep_out(
    center: Point = (0.0, 0.0, 0.0),
    opening: float = 0.0,
    margin: str = VISE_MARGIN,
) -> KeepOut
```

Return the regions around the vise that a tool must not enter.

```python
MachineVise.model(
    solidcraft: PyBind,
    center: Point = (0.0, 0.0, 0.0),
    opening: float = 0.0,
    lift: float = 0.0,
) -> list[str]
```

Model the vise, up from the center of the base's bottom face.

```python
MachineVise.cacheable(opening: float) -> tuple[Cacheable, ...]
```

Return the vise as models that can be cached.

### `scraftcam.tooling.tools.ViseBlock`

```python
scraftcam.tooling.tools.ViseBlock(
    length: float,
    width: float,
    height: float,
    corner_radius: float,
)
```

A block of a vise: a layer of its base, or a jaw.

Its outline is a rectangle with rounded corners, and perhaps notches
in its sides, extruded straight up.  All lengths are in millimeters.

Attributes:
* `length` (`float`): Its size along X, the lead screw's direction.
* `width` (`float`): Its size along Y.
* `height` (`float`): Its size along Z.
* `corner_radius` (`float`): The radius of its four corners.

```python
ViseBlock.outline(
    name: str,
    center: tuple[float, float] = (0.0, 0.0),
    notches: ViseNotches | None = None,
) -> RoundedPolygon
```

Return the block's outline, as seen from above.

```python
ViseBlock.volume(notches: ViseNotches | None = None) -> float
```

Return the volume the model should have.

```python
ViseBlock.model(
    solidcraft: PyBind,
    name: str,
    center: Point = (0.0, 0.0, 0.0),
    notches: ViseNotches | None = None,
) -> str
```

Model the block, up from the center of its bottom face.

### `scraftcam.tooling.tools.ViseNotches`

```python
scraftcam.tooling.tools.ViseNotches(
    centers: tuple[float, ...],
    width: float,
    depth: float,
    inner_radius: float,
    outer_radius: float,
)
```

The notches in both sides of one layer of a vise's base.

Each side has one rectangular notch per center, so the notches on
the two sides line up.  All four of a notch's corners are rounded.
All lengths are in millimeters.

Attributes:
* `centers` (`tuple[float, ...]`):
  The X of each notch's center (X1, X2, ...), from the block's
  center, from most negative up.  Empty, the sides are plain.
* `width` (`float`): A notch's size along X.
* `depth` (`float`): How far a notch reaches in from the side.
* `inner_radius` (`float`): The radius of its two corners farthest in.
* `outer_radius` (`float`):
  The radius of its two corners where it meets the side.

```python
ViseNotches.side_corners(edge_y: float, direction: int) -> list[Corner]
```

Return the corners of the notches along one side of a block.

```python
ViseNotches.area() -> float
```

Return the area that all of the notches remove from a block.

## Jaw Plate

A jaw plate: the replaceable part of a vise's jaw that clamps.

A machine vise's jaw plates are separate parts, each held to its jaw by
two socket head cap screws.  Each screw goes through a counterbore in
the clamping face, so that its head sits below the face.  The hole
patterns are standard enough that plates from one maker fit another's
vises: a 6 in vise has holes on 3.875 in centers, for 1/2-13 screws.

The plate is a block: `length` is its thickness, from its clamping face
back to its jaw; `width` runs across the vise, and `height` up. All
lengths are in millimeters.

The sketches are of `tools.KURT_JAW_PLATE`, the plate on
`tools.KURT_D688`.  Hidden edges are dashed.

Top (clamping face down):

![Jaw plate, top](docs/tool_models/jaw_plate_top.svg)

Clamping face:

![Jaw plate, face](docs/tool_models/jaw_plate_face.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| L      | Length | `length`: Its thickness, from its clamping face back.     |
| C      | Length | `counterbore_depth`: How deep the counterbores reach in   |
|        |        | from the clamping face.                                   |
| W      | Length | `width`: Its size across the vise.                        |
| Hs     | Length | `hole_spacing`: The distance between its two holes.       |
| H      | Length | `height`: Its size up.                                    |
| Hh     | Length | `hole_height`: The height of its holes' centers above its |
|        |        | bottom.                                                   |
| Cd     | Length | `counterbore_diameter`: The diameter of the counterbores, |
|        |        | for the screws' heads.                                    |
| Hd     | Length | `hole_diameter`: The diameter of its holes.               |

Not a size:

* `screw`: The screws that hold it on (e.g. `1/2-13 SHCS`).

Like the vise, it is made in Python, in millimeters:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.tools import KURT_JAW_PLATE

with connect("8080") as transport:
    KURT_JAW_PLATE.model(PyBind(transport), "Jaw plate")
```

### `scraftcam.tooling.tools.JawPlate`

```python
scraftcam.tooling.tools.JawPlate(
    screw: str,
    length: float,
    width: float,
    height: float,
    hole_spacing: float,
    hole_diameter: float,
    hole_height: float,
    counterbore_diameter: float,
    counterbore_depth: float,
)
```

A jaw plate: the replaceable part of a vise's jaw that clamps.

A machine vise's jaw plates are separate parts, each held to its jaw
by two socket head cap screws.  Each screw goes through a counterbore
in the clamping face, so that its head sits below the face.  The
hole patterns are standard enough that plates from one maker fit
another's vises: a 6 in vise has holes on 3.875 in centers, for
1/2-13 screws.

The plate is a block: `length` is its thickness, from its clamping
face back to its jaw; `width` runs across the vise, and `height` up.
All lengths are in millimeters.

Attributes:
* `screw` (`str`): The screws that hold it on (e.g. `1/2-13 SHCS`).
* `length` (`float`): Its thickness, from its clamping face back.
* `width` (`float`): Its size across the vise.
* `height` (`float`): Its size up.
* `hole_spacing` (`float`): The distance between its two holes.
* `hole_diameter` (`float`): The diameter of its holes.
* `hole_height` (`float`):
  The height of its holes' centers above its bottom.
* `counterbore_diameter` (`float`):
  The diameter of the counterbores, for the screws' heads.
* `counterbore_depth` (`float`):
  How deep the counterbores reach in from the clamping face.

```python
JawPlate.block() -> ViseBlock
```

Return the plate without its holes.

```python
JawPlate.volume() -> float
```

Return the volume its model should have.

```python
JawPlate.model(
    solidcraft: PyBind,
    name: str,
    center: Point = (0.0, 0.0, 0.0),
    facing: float = 1.0,
) -> str
```

Model the plate, with its holes and counterbores.

## Parallel

A parallel: a thin steel bar that work sits on in a vise.

Parallels come in matched pairs, one under each side of the work. Most
have two round holes through them, which make them lighter and easier to
pick up; the holes are optional.

It stands on edge, with its length along Y, the way it lies along the
jaws of a vise whose lead screw runs along X.  Its holes go through it
along X, halfway up, the same distance either side of its middle.  All
lengths are in millimeters.

The sketches are of `Parallel 3/4 in A`, from `tools.PARALLELS`.
Hidden edges are dashed.

Side:

![Parallel, side](docs/tool_models/parallel_side.svg)

End:

![Parallel, end](docs/tool_models/parallel_end.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| L      | Length | `length`: Its size along Y.                               |
| Hs     | Length | `hole_spacing`: Optional. The distance between its two    |
|        |        | holes' centers; 0 for no holes.                           |
| H      | Length | `height`: Its size along Z.                               |
| Hd     | Length | `hole_diameter`: Optional. The diameter of its holes; 0   |
|        |        | for no holes.                                             |
| T      | Length | `thickness`: Its size along X.                            |

`tools.PARALLELS` is a set of two of each of the standard imperial
heights, in inches: 1/2, 5/8, 3/4, 7/8, 1, 1-1/8, 1-1/4, 1-3/8, 1-1/2,
1-5/8.  Each is 1/8 in thick and 6 in long, with two holes 3 in apart,
half as wide as the parallel is tall.  Each is named for its height and
A or B (`Parallel 3/4 in A`).

It is made in Python, in millimeters:

```python
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.tools import Parallel

# Its sizes in millimeters; the holes are optional.
parallel = Parallel(
    "Parallel 3/4 in",
    height=19.050,
    thickness=3.175,
    length=152.4,
    hole_spacing=76.2,
    hole_diameter=9.525,
)
with connect("8080") as transport:
    parallel.model(PyBind(transport), (0.0, 0.0, 0.0))
```

A setup file (`examples/setup/`) names one of the set by its
`type`:

```json
{
  "kind": "parallel",
  "type": "Parallel 1-1/2 in A",
  "location": [
    "0 in",
    "2.9375 in"
  ],
  "height": "2.64 in",
  "orientation": "-90 deg"
}
```

### `scraftcam.tooling.tools.Parallel`

```python
scraftcam.tooling.tools.Parallel(
    name: str,
    height: float,
    thickness: float,
    length: float,
    hole_spacing: float,
    hole_diameter: float,
)
```

A parallel: a thin steel bar that work sits on in a vise.

Parallels come in matched pairs, one under each side of the work.
Most have two round holes through them, which make them lighter and
easier to pick up; the holes are optional.

It stands on edge, with its length along Y, the way it lies along
the jaws of a vise whose lead screw runs along X.  Its holes go
through it along X, halfway up, the same distance either side of its
middle.  All lengths are in millimeters.

Attributes:
* `name` (`str`): What it is.
* `height` (`float`): Its size along Z.
* `thickness` (`float`): Its size along X.
* `length` (`float`): Its size along Y.
* `hole_spacing` (`float`):
  Optional.  The distance between its two holes' centers; 0 for no
  holes.
* `hole_diameter` (`float`):
  Optional.  The diameter of its holes; 0 for no holes.

```python
Parallel.named(name: str) -> 'Parallel'
```

Return the parallel with a key or name.

```python
Parallel.key() -> str
```

Return its key in `REGISTRY` (e.g. `kurt_d688`).

```python
Parallel.has_holes() -> bool
```

Return True if the parallel has holes.

```python
Parallel.volume() -> float
```

Return the volume its model should have.

```python
Parallel.block() -> ViseBlock
```

Return the parallel's shape.

```python
Parallel.prism(center: Point) -> Prism
```

Return the rectangular prism that just encloses the parallel.

```python
Parallel.model(solidcraft: PyBind, center: Point) -> str
```

Model the parallel, up from the center of its bottom edge.

## Grid Plate

A grid plate: a plate with a grid of holes, for holding work down.

The grid is `rows` by `columns` holes, with the same pitch along X and
Y, its outer holes `edge` in from all four sides; the plate's length and
width follow (`T.osiade~5.1.9` #29).  Each hole's top edge may be
chamfered at 45 degrees, `chamfer_width` wide, and the plate's top outer
edge too, `edge_chamfer` wide (#37).

It may also have tooling holes, on a square pattern `tooling_pitch`
apart, centered on the plate, each one dead center between four of the
grid's holes, as many as fit inside the grid's outer holes (#30).  They
come in two sizes, a tap drill for a thread and a close fit for the same
screw, in a checkerboard: a tooling hole's neighbors along X and Y are
the other size.  With them, grid plates are easy to make in pairs in a
home shop, and pairs of them hold many parts made at the same time.

Its outline is an `RoundedPolygon` with its four corners rounded and all
of the holes inside, so that one extrude makes the plate; one chamfer
command then does every chamfer.  All lengths are in millimeters.

Chamfers take a lot of computing, once.  `GRID_PLATE`'s 200 took
SolidCraft about 4-1/2 minutes, keeping four processors busy, against 2
seconds without them.  The model cache (`model_cache.py`, which
`setups.py` and `show_demo.py` use) keeps the plate as a STEP file in
`~/.scraftcam/tool_cache/`, which loads in about a second, so the cost
comes again only when the plate's numbers change, or `tools.py`,
`mount.py` or `geometry.py` does.  `model()` called directly does not
use the cache.

The sketches are of `tools.GRID_PLATE`.  Its tap drill tooling
holes are filled, and its close fit ones open.

Chamfering the grid's holes is currently very slow to compute
(about 4-1/2 minutes for `tools.GRID_PLATE`'s 200, against
seconds without them), and is done again whenever the cache
key changes.  Turning it off is recommended:
`GridPlate.named(name, chamfer=False)` (in a setup's
`args`, `chamfer = false`), as the demonstration does.

Top:

![Grid plate, top](docs/tool_models/grid_plate_top.svg)

Section A-A, across the upper left corner (2 times size):

![Grid plate, section](docs/tool_models/grid_plate_section.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| E      | Length | `edge`: The distance from a side to the nearest holes.    |
| P      | Length | `pitch`: The distance between grid holes, along X and Y.  |
| C      | Count  | `columns`: The number of columns of grid holes (along X). |
| R      | Count  | `rows`: The number of rows of grid holes (along Y).       |
| H      | Length | `hole_diameter`: The diameter of the grid's holes.        |
| Cr     | Length | `corner_radius`: Optional. The radius of its corners.     |
| Tp     | Length | `tooling_pitch`: Optional. The distance between tooling   |
|        |        | holes, along X and Y; 0 for none.                         |
| Tc     | Length | `tooling_close_diameter`: Optional. The diameter of the   |
|        |        | close fit tooling holes.                                  |
| Tt     | Length | `tooling_tap_diameter`: Optional. The diameter of the     |
|        |        | tooling holes to be threaded (the tap drill).             |
| T      | Length | `thickness`: Its size along Z.                            |
| Ec     | Length | `edge_chamfer`: Optional. How wide (and deep) the 45      |
|        |        | degree chamfer on the plate's top outer edge is; 0 for    |
|        |        | none. Square corners, or corners rounded at least that    |
|        |        | much.                                                     |
| Cw     | Length | `chamfer_width`: Optional. How wide (and so how deep) the |
|        |        | 45 degree chamfer on each grid hole's top edge is; 0 for  |
|        |        | none. Slow to model the first time (above).               |

Not a size:

* `name`: What it is.
* `length`: Its size along X, from the grid.
* `width`: Its size along Y, from the grid.

A shop describes each grid plate in a file in its `tooling/`
(`Shops.md`), as `examples/shop/tooling/grid_plate.toml`
describes `tools.GRID_PLATE`:

```toml
name = "Grid plate"
kind = "grid_plate"
language = "English"
version = "0.0.1"
notes = """\
  The example shop's work holding.  The grid plate is \
  `tools.GRID_PLATE`, so that a setup naming it uses the same cached \
  model."""
description = "Aluminum, made in the shop, with tooling holes for #10-32"
rows = 20
columns = 10
pitch = "1/2 in"
edge = "1/2 in"
thickness = "1/2 in"
hole_diameter = "0.144 in"
corner_radius = "1/4 in"
chamfer_width = "1/32 in"
edge_chamfer = "1/32 in"
tooling_pitch = "3 in"
tooling_tap_diameter = "0.159 in"
tooling_close_diameter = "0.196 in"
```

Or it is made in Python, in millimeters:

```python
from scraftcam.model_cache import ModelCache
from scraftcam.pybind.scraftpybind import PyBind, connect
from scraftcam.tooling.tools import GRID_PLATE

# Through the cache: slow the first time, then about a second.
with connect("8080") as transport:
    (plate,) = GRID_PLATE.cacheable()
    ModelCache().insert(PyBind(transport), plate)
```

A setup file (`examples/setup/`) names one by its `type`, from
the shop's tooling files or `tools.py`:

```json
{
  "kind": "grid_plate",
  "type": "Grid plate",
  "location": [
    "2 in",
    "1-1/2 in"
  ],
  "height": "-1 in",
  "orientation": "90 deg"
}
```

### `scraftcam.tooling.tools.GridPlate`

```python
scraftcam.tooling.tools.GridPlate(
    name: str,
    rows: int,
    columns: int,
    pitch: float,
    edge: float,
    thickness: float,
    hole_diameter: float,
    corner_radius: float,
    chamfer_width: float,
    edge_chamfer: float,
    tooling_pitch: float,
    tooling_tap_diameter: float,
    tooling_close_diameter: float,
)
```

A grid plate: a plate with a grid of holes, for holding work down.

The grid is `rows` by `columns` holes, with the same pitch along X
and Y, its outer holes `edge` in from all four sides; the plate's
length and width follow (`T.osiade~5.1.9` #29).  Each hole's top
edge may be chamfered at 45 degrees, `chamfer_width` wide, and the
plate's top outer edge too, `edge_chamfer` wide (#37).

It may also have tooling holes, on a square pattern `tooling_pitch`
apart, centered on the plate, each one dead center between four of
the grid's holes, as many as fit inside the grid's outer holes
(#30).  They come in two sizes, a tap drill for a thread and a
close fit for the same screw, in a checkerboard: a tooling hole's
neighbors along X and Y are the other size.  With them, grid
plates are easy to make in pairs in a home shop, and pairs of them
hold many parts made at the same time.

Its outline is an `RoundedPolygon` with its four corners rounded
and all of the holes inside, so that one extrude makes the plate;
one chamfer command then does every chamfer.  All lengths are in
millimeters.

Chamfers take a lot of computing, once.  `GRID_PLATE`'s 200 took
SolidCraft about 4-1/2 minutes, keeping four processors busy,
against 2 seconds without them.  The model cache (`model_cache.py`,
which `setups.py` and `show_demo.py` use) keeps the plate as a STEP
file in `~/.scraftcam/tool_cache/`, which loads in about a second,
so the cost comes again only when the plate's numbers change, or
`tools.py`, `mount.py` or `geometry.py` does.  `model()` called
directly does not use the cache.

Attributes:
* `name` (`str`): What it is.
* `rows` (`int`): The number of rows of grid holes (along Y).
* `columns` (`int`): The number of columns of grid holes (along X).
* `pitch` (`float`): The distance between grid holes, along X and Y.
* `edge` (`float`): The distance from a side to the nearest holes.
* `thickness` (`float`): Its size along Z.
* `hole_diameter` (`float`): The diameter of the grid's holes.
* `corner_radius` (`float`): Optional.  The radius of its corners.
* `chamfer_width` (`float`):
  Optional.  How wide (and so how deep) the 45 degree chamfer on
  each grid hole's top edge is; 0 for none.  Slow to model the
  first time (above).
* `edge_chamfer` (`float`):
  Optional.  How wide (and deep) the 45 degree chamfer on the
  plate's top outer edge is; 0 for none.  Square corners, or
  corners rounded at least that much.
* `tooling_pitch` (`float`):
  Optional.  The distance between tooling holes, along X and Y; 0
  for none.
* `tooling_tap_diameter` (`float`):
  Optional.  The diameter of the tooling holes to be threaded (the
  tap drill).
* `tooling_close_diameter` (`float`):
  Optional.  The diameter of the close fit tooling holes.
* `length` (`float`): Its size along X, from the grid.
* `width` (`float`): Its size along Y, from the grid.

```python
GridPlate.named(name: str, chamfer: bool = True) -> 'GridPlate'
```

Return the grid plate with a key or name.

```python
GridPlate.key() -> str
```

Return its key in `REGISTRY` (e.g. `kurt_d688`).

```python
GridPlate.from_shop(plate: dict[str, object]) -> 'GridPlate'
```

Return a grid plate described in a shop's tooling file.

```python
GridPlate.chamfered_diameter() -> float
```

Return the diameter of a grid hole at the plate's top.

```python
GridPlate.hole_centers() -> list[tuple[float, float]]
```

Return where the grid's holes are, from the plate's center.

```python
GridPlate.tooling_holes() -> list[tuple[float, float, float]]
```

Return where the tooling holes are, and their sizes.

```python
GridPlate.volume() -> float
```

Return the volume the model should have.

```python
GridPlate.seat() -> Point
```

Return the middle of the plate's top.

```python
GridPlate.origin(turns: int = 0) -> Point
```

Return the point handed up to the next item.

```python
GridPlate.outline(center: tuple[float, float]) -> RoundedPolygon
```

Return the plate's outline and holes, as seen from above.

```python
GridPlate.model(solidcraft: PyBind, center: Point) -> list[str]
```

Model the plate, up from the center of its bottom face.

```python
GridPlate.cacheable() -> tuple[Cacheable, ...]
```

Return the plate as a model that can be cached.

```python
GridPlate.prism(center: Point) -> Prism
```

Return the rectangular prism that just encloses the plate.

```python
GridPlate.keep_out(center: Point) -> KeepOut
```

Return the prism around the plate.
