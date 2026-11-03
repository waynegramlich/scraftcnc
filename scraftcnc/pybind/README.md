# `scraftpybind`: Python Bindings for SolidCraft

[SolidCraft](https://github.com/tangency-labs/solidcraft) is an open
source CAD program in which every action is a command, reachable from
`solidcraft-cli`, a JSON control port and an MCP server.  `scraftpybind`
turns each of those commands into a typed Python method, so a design
can be written as an ordinary Python program:

```python
from scraftcnc.pybind.scraftpybind import SCPyBind, connect

# A GUI started with `solidcraft --control 8080`; or "headless".
with connect("8080") as transport:
    solidcraft = SCPyBind(transport)

    # A 100 x 60 mm rectangle with a 20 mm hole, extruded 10 mm.
    solidcraft.sketch.create(plane="XY", name="Plate")
    rectangle = solidcraft.sketch.rectangle_center(
        center=(0, 0), corner=(50, 30)
    )
    solidcraft.sketch.circle_center(center=(0, 0), diameter=20)
    solidcraft.sketch.finish()
    solidcraft.solid.extrude(
        distance=10,
        profiles=[{"curves": rectangle["curves"]}],
        body_name="Plate",
    )
```

This is what `python3 -m scraftcnc.pybind.scraftpybind 8080` runs;
`examples/plate_with_holes.py` is a longer example
(`python3 -m scraftcnc.pybind.examples.plate_with_holes headless
plate.step`, from the repository root).

## Status

An early, unofficial project, not affiliated with the SolidCraft
developers.  It is published to see whether other SolidCraft users want
Python bindings; comments are welcome in the issues.

## How It Works

* `SCPyBind` holds one object per command namespace:
  `sketch.rectangle.center` is `SCPyBind.sketch.rectangle_center()`.
  Parameters left at `None` are not sent, so SolidCraft uses its own
  defaults.
* An `SCTransport` carries the requests:
  * `SCControlTransport` talks to a running SolidCraft GUI started with
    `solidcraft --control PORT`, so the design can be watched as it is
    built.
  * `SCHeadlessTransport` runs `solidcraft-cli mcp --headless`, a design
    session with no window (useful with `file.export`).
* `connect("8080")` or `connect("headless")` picks one.
* The command classes are generated: `scraftpybind_generate.py` reads
  the command list from `solidcraft-cli` (or the cached
  `scraftpybind_commands.json`) and rewrites the generated region of
  `scraftpybind.py`.

## Requirements

* Python 3.11 or newer; nothing outside the standard library.
* SolidCraft: the GUI for `SCControlTransport`, and `solidcraft-cli` on
  the `PATH` for `SCHeadlessTransport`.  The commands were generated from
  `solidcraft-cli` 0.20.0.

## Trying It

In a GUI, which must be running first, so that the plate can be
watched as it is built:

```
solidcraft --control 8080 &         # Start a GUI with control port 8080.
python3 -m scraftcnc.pybind.scraftpybind 8080      # Build the plate.
kill %1                             # Close the GUI when done.
```

Or headless, with no GUI at all:

```
python3 -m scraftcnc.pybind.scraftpybind headless  # Writes a STEP file.
```

## Testing

```
python3 -m unittest -v tests.test_scraftpybind
```

The offline tests use a fake control port and a fake `solidcraft-cli`.
With `solidcraft-cli` on the `PATH`, the live tests also build plates
headless and measure the STEP files; with `SCRAFTPYBIND_TEST_PORT` set
to the port of a GUI started with `--control PORT`, one more test adds
a plate to its design.

The lines that the offline tests do not reach end with
`# pragma: no cover` (`grep -rn "pragma: no cover" .` lists them).  As
in `coverage.py`, a mark on a `def`, `class` or `if` line covers its
whole block.

## License

MIT No Attribution (`LICENSE`).  SolidCraft itself is MIT licensed.
