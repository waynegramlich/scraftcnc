# Tool Models

This document is written by `tool_models.py` (`./tool_models.py`), from
the code; do not edit it.

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
form raises `SCShopError`.

## Contents

* [Python Interface](#python-interface)
* [End Mill](#end-mill)
* [Drill](#drill)
* [Chamfer Mill](#chamfer-mill)
* [Corner Rounding Mill](#corner-rounding-mill)
* [Double Angle Cutter](#double-angle-cutter)
* [Single End Countersink](#single-end-countersink)
* [Double End Countersink](#double-end-countersink)

## Python Interface

### `sctoolmodel.model_description`

```python
sctoolmodel.model_description(
    solidcraft: SCPyBind,
    description: dict[str, object],
    at: tuple[float, float, float] = (0.0, 0.0, 0.0),
    cache: SCModelCache | None = None,
) -> SCModeledTool
```

Model one tool from its description.

Arguments:
* `solidcraft` (`SCPyBind`): The SolidCraft session.
* `description` (`dict[str, object]`):
  The tool, with its `kind`, as `shops.check_tool()` takes it.  Its
  `name`, if any, names the body.
* `at` (`tuple[float, float, float]`):
  Where its tip goes (inches).
* `cache` (`SCModelCache | None`):
  Where to keep its body between runs, or `None` to build it.

Returns:
* (`SCModeledTool`): What was made, free to move.

Raises:
* `SCShopError`:
  If the description has any problem, before SolidCraft is touched.
* `SCSolidCraftError`: If SolidCraft refuses a command.
* `FileNotFoundError`: If no SolidCraft has the port.
* `ConnectionError`:
  If nothing listens on the port, or SolidCraft goes away.

### `sctoolmodel.SCModeledTool`

```python
sctoolmodel.SCModeledTool(body: str, sketch: str, occurrence: str)
```

A tool in SolidCraft: a component with its body and flute lines.

Attributes:
* `body` (`str`): Its body's name.
* `sketch` (`str`): The name of its flute lines' sketch.
* `occurrence` (`str`): Its component's occurrence, for moving it.

```python
SCModeledTool.items() -> list[str]
```

Return what `browser.visibility` shows or hides for the tool.

### `shops.check_tool`

```python
shops.check_tool(
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
* `SCShopError`: With every problem found.

### `shops.SCShopError`

```python
shops.SCShopError(problems: list[str])
```

The problems found in a shop description.

Attributes:
* `problems` (`list[str]`):
  Each problem, as `FILE:LINE: KEY: message`.

### `scraftpybind.connect`

```python
scraftpybind.connect(where: str) -> SCTransport
```

Return a transport for a port number, or for `headless`.

Arguments:
* `where` (`str`):
  A GUI's control port (e.g. `8080`), or `headless` for a session
  with no window.

Returns:
* (`SCTransport`): The transport, which connects on first use.

Raises:
* `ValueError`: If `where` is neither.

### `scraftpybind.SCPyBind`

```python
scraftpybind.SCPyBind(transport: SCTransport)
```

The top level of `scraftpybind`: SolidCraft's commands.

### `scraftpybind.SCSolidCraftError`

```python
scraftpybind.SCSolidCraftError(
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
| `B`    | Length | `corner_radius`: Optional. A bull nose's corners.         |
| `C`    | Length | `length_of_cut`: How deep it can cut (LOC).               |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |

Other keys:

* `flutes` (integer): How many flutes.
* `end` (one of `square`, `ball`, `bull_nose`): The shape of its end.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[end_mills]]
name = "Sample end mill"
unique_id = 1
material = "carbide"
finish = "uncoated"
diameter = "1/2 in"
shank = "3/8 in"
length_of_cut = "1 in"
overall_length = "3 in"
flutes = 4
end = "bull_nose"
corner_radius = "1/8 in"
```

## Drill

A twist drill.

![Drill sketch](docs/tool_models/drill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `C`    | Length | `length_of_cut`: How deep it can cut (LOC).               |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `K`    | Length | `shank_length`: Optional. How far its shank comes down    |
|        |        | from its top; if not given, a `shank` starts where its    |
|        |        | flutes stop.                                              |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
| `P`    | Angle  | `point_angle`: The included angle.                        |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |

Other keys:

* `flutes` (integer): How many flutes (2 if not given).
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[drills]]
name = "Sample drill"
unique_id = 1
material = "HSS"
finish = "black oxide"
diameter = "5/8 in"
shank = "1/2 in"
shank_length = "1-1/2 in"
length_of_cut = "2-1/2 in"
overall_length = "4-1/2 in"
point_angle = "118 deg"
```

## Chamfer Mill

A chamfer mill (a V-bit), which bevels top edges.

![Chamfer Mill sketch](docs/tool_models/chamfer_mill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The included angle (90 deg makes 45 deg bevels). |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `T`    | Length | `tip_diameter`: The diameter at its tip.                  |

Other keys:

* `flutes` (integer): How many flutes.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[chamfer_mills]]
name = "Sample chamfer mill"
unique_id = 1
material = "carbide"
finish = "uncoated"
diameter = "1/2 in"
shank = "1/2 in"
tip_diameter = "1/4 in"
overall_length = "2 in"
angle = "90 deg"
```

## Corner Rounding Mill

A corner rounding mill, which rounds top edges over to its radius.  Its
tip (a pilot) rides along the wall below.

![Corner Rounding Mill sketch](docs/tool_models/corner_rounding_mill.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
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
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[corner_rounding_mills]]
name = "Sample corner rounding mill"
unique_id = 1
material = "carbide"
finish = "uncoated"
radius = "1/4 in"
tip_diameter = "1/4 in"
shank = "3/4 in"
overall_length = "2-1/2 in"
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
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
| `M`    | Length | `neck_length`: Optional. The neck's length (L3), from the |
|        |        | shank to the cutter.                                      |
| `N`    | Length | `neck_diameter`: Optional. The neck's diameter.           |
| `S`    | Length | `shank`: Optional. The shank diameter, if not `diameter`. |
| `W`    | Length | `width`: The height of the cutter (L2), point to point.   |

Other keys:

* `flutes` (integer): How many flutes.
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[double_angle_cutters]]
name = "Sample double angle cutter"
unique_id = 1
material = "carbide"
finish = "uncoated"
diameter = "3/4 in"
shank = "1/2 in"
width = "3/8 in"
neck_diameter = "1/4 in"
neck_length = "1/2 in"
overall_length = "2-1/2 in"
angle = "90 deg"
```

## Single End Countersink

A combined drill and countersink on a shank: a small drill at its tip,
joined to its body by a cone.  It can not go in a `tool_table` yet.

![Single End Countersink sketch](docs/tool_models/single_countersink.svg)

| Letter | Units  | Description                                               |
| ------ | ------ | --------------------------------------------------------- |
| `A`    | Angle  | `angle`: The countersink's included angle.                |
| `D`    | Length | `diameter`: The cutting diameter.                         |
| `E`    | Length | `drill_diameter`: The diameter of the small drill at its  |
|        |        | tip.                                                      |
| `G`    | Length | `drill_length`: Optional. How far the small drill reaches |
|        |        | from its tip (its diameter if not given).                 |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
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
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[single_countersinks]]
name = "Sample single end countersink"
unique_id = 1
material = "HSS"
finish = "uncoated"
diameter = "3/4 in"
shank = "3/4 in"
drill_diameter = "3/8 in"
drill_length = "1/2 in"
overall_length = "2-1/2 in"
angle = "60 deg"
point_angle = "90 deg"
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
| `E`    | Length | `drill_diameter`: The diameter of the small drill at its  |
|        |        | tip.                                                      |
| `G`    | Length | `drill_length`: Optional. How far the small drill reaches |
|        |        | from its tip (its diameter if not given).                 |
| `L`    | Length | `overall_length`: Its whole length (OAL).                 |
| `P`    | Angle  | `point_angle`: Optional. The included angle of the small  |
|        |        | drill's point (90 deg if not given).                      |

Other keys:

* `flutes` (integer): How many flutes (2 if not given).
* `material` (one of `HSS`, `cobalt`, `carbide`, `cermet`, `ceramic`,
  `CBN`, `PCD`, or another ending in `!`): What it is made of.
* `finish` (string): Its finish or coating (`uncoated`, `AlTiN`, ...).

JSON:

```
./sctoolmodel.py 8080 '{
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
from scraftpybind import SCPyBind, connect
from sctoolmodel import model_description

with connect("8080") as transport:
    model_description(
        SCPyBind(transport),
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

A tools file:

```toml
[[double_countersinks]]
name = "Sample double end countersink"
unique_id = 1
material = "HSS"
finish = "uncoated"
diameter = "3/4 in"
drill_diameter = "3/8 in"
drill_length = "1/2 in"
overall_length = "3 in"
angle = "60 deg"
point_angle = "90 deg"
```
