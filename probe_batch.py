#!/usr/bin/env python3
"""Time drawing a program's planned path as one 3D sketch per tool.

A probe for showing the planned tool path in SolidCraft (`T.rlg~3.3`):
the moves of a G-code file (read by `scplot.read_gcode()` and
`scplot.command_moves()`) are grouped by the tool in the spindle, and
each tool's cuts and its rapids become a 3D sketch, built with one
`engine.batch` request: `sketch.create`, `sketch.options` (3D, points,
profile, constraints and dimensions not shown), one `sketch.line3d` per
polyline of up to `MAX_POINTS` points (a new one wherever the path
jumps), `sketch.finish`, and (with `--hide`) `browser.visibility`.  It
prints each request's time, as measured here and as SolidCraft
measured it, and the wires made:

```
./probe_batch.py headless --plate
./probe_batch.py 8080 --plate --toggle
./probe_batch.py 8080 --keep --ngc demo.ngc --arcs
```

With `--arcs`, an arc in one plane is an exact `sketch.arc3d` (a whole
circle as two), and only helices are broken into lines.  With
`--mixed`, a tool's cuts and rapids share one sketch.

With `--plate`, the demonstration's plate is modeled first (by
`solidcraftcnc_demo.py`, with its own drawing of the path left out),
in the same session, and its G-code is the one drawn unless `--ngc`
is given.  A new design is started first unless `--keep` is given.
With `--toggle`, each sketch is then hidden and shown again
(`browser.visibility`), timed.

Headless, the batch goes to the `batch` tool of `solidcraft-cli`'s MCP
server, which runs the steps one at a time in its own process; in the
GUI, `engine.batch` runs them all in one frame.
"""

# `main()` sets up, builds and reports in one place, so it has many
# locals.
# pylint: disable=too-many-locals

import argparse
import contextlib
import io
import json
import math
import shutil
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

import solidcraftcnc_demo
from scplot import Move, SpacePoint, command_moves, read_gcode
from scraftpybind import (
    JSON,
    HeadlessTransport,
    SolidCraftError,
    SolidCraftPyBind,
    Transport,
    connect,
)

# The most points `sketch.line3d` takes in one call.
MAX_POINTS: int = 500

# Points closer than this (mm) are the same point.
SAME: float = 1e-6

# SolidCraft's world coordinates are millimeters.
MM_PER_INCH: float = 25.4

# One step of an `engine.batch`: `{"command": ..., "params": {...}}`.
Step: TypeAlias = dict[str, JSON]


# Function `group_moves()`:
def group_moves(moves: Sequence[Move], mixed: bool) -> dict[str, list[Move]]:
    """Group a program's moves by tool, and into cuts and rapids.

    Arguments:
    * `moves` (`Sequence[Move]`): The moves, in program order.
    * `mixed` (`bool`): True to keep a tool's cuts and rapids together.

    Returns:
    * (`dict[str, list[Move]]`): The moves of each group, in order,
      named like `T08 cuts`, `T08 rapids` or (mixed) `T08 path`, in
      the order the groups first appear.
    """
    groups: dict[str, list[Move]] = {}
    move: Move
    for move in moves:
        kind: str = "path" if mixed else "rapids" if move["g"] == 0 else "cuts"
        groups.setdefault(f"T{move['tool']:02d} {kind}", []).append(move)
    return groups


# Function `_planar()`:
def _planar(move: Move) -> bool:
    """Return whether a move is an arc in one plane (no change in Z).

    Arguments:
    * `move` (`Move`): The move.

    Returns:
    * (`bool`): True for a `G2` or `G3` whose points share their Z.
    """
    return move["g"] in (2, 3) and all(
        abs(point[2] - move["pts"][0][2]) < SAME for point in move["pts"]
    )


# Function `arc_steps()`:
def arc_steps(points: Sequence[SpacePoint]) -> list[Step]:
    """Return `sketch.arc3d` steps for an arc in one plane.

    The arc's points (`scplot`'s, evenly spaced) give its middle; a
    whole circle (ending where it starts) is drawn as two halves, since
    three points can not name it.

    Arguments:
    * `points` (`Sequence[SpacePoint]`): Points along the arc (mm).

    Returns:
    * (`list[Step]`): One step, or two for a whole circle.
    """
    # The points that split it: the middle, or the quarters of a circle.
    last: int = len(points) - 1
    marks: list[int] = (
        [0, last // 4, last // 2, 3 * last // 4, last]
        if math.dist(points[0], points[last]) < SAME
        else [0, last // 2, last]
    )
    steps: list[Step] = []
    index: int
    for index in range(0, len(marks) - 1, 2):
        start: list[JSON] = list(points[marks[index]])
        through: list[JSON] = list(points[marks[index + 1]])
        end: list[JSON] = list(points[marks[index + 2]])
        steps.append(
            {
                "command": "sketch.arc3d",
                "params": {"start": start, "through": through, "end": end},
            }
        )
    return steps


# Function `path_steps()`:
def path_steps(moves: Sequence[Move], scale: float, arcs: bool) -> list[Step]:
    """Return the steps that draw moves into an open 3D sketch.

    Moves that follow on from each other make one polyline (a
    `sketch.line3d`), broken into calls of at most `MAX_POINTS` points
    that share their ends; a jump starts a new one.  Points that repeat
    the one before are left out.

    Arguments:
    * `moves` (`Sequence[Move]`): The moves, in order.
    * `scale` (`float`): Millimeters per program unit.
    * `arcs` (`bool`): True to draw arcs in one plane as `sketch.arc3d`.

    Returns:
    * (`list[Step]`): The `sketch.line3d` (and `sketch.arc3d`) steps.
    """
    steps: list[Step] = []
    run: list[SpacePoint] = []

    # Function `flush()`:
    def flush() -> None:
        """Add steps for the polyline so far, and start a new one."""
        start: int = 0
        while start < len(run) - 1:
            piece: list[SpacePoint] = run[start : start + MAX_POINTS]
            steps.append(
                {
                    "command": "sketch.line3d",
                    "params": {"points": [list(p) for p in piece]},
                }
            )
            start += MAX_POINTS - 1
        run.clear()

    # Add each move to the polyline, or start a new one where it jumps.
    move: Move
    for move in moves:
        points: list[SpacePoint] = [
            [value * scale for value in point] for point in move["pts"]
        ]
        if run and math.dist(run[-1], points[0]) >= SAME:
            flush()
        if arcs and _planar(move):
            flush()
            steps += arc_steps(points)
            run.append(points[-1])
            continue
        point: SpacePoint
        for point in points:
            if not run or math.dist(run[-1], point) >= SAME:
                run.append(point)
    flush()
    return steps


# Function `sketch_steps()`:
def sketch_steps(name: str, drawing: list[Step], hide: bool) -> list[Step]:
    """Return the steps of one batch: a whole 3D sketch.

    Arguments:
    * `name` (`str`): The sketch's name.
    * `drawing` (`list[Step]`): Its drawing steps (`path_steps()`).
    * `hide` (`bool`): True to hide it at the end.

    Returns:
    * (`list[Step]`): Create, options, the drawing, finish (and hide).
    """
    steps: list[Step] = [
        {"command": "sketch.create", "params": {"plane": "XY", "name": name}},
        {
            "command": "sketch.options",
            "params": {
                "sketch_3d": True,
                "show_points": False,
                "show_profile": False,
                "show_constraints": False,
                "show_dimensions": False,
            },
        },
        *drawing,
        {"command": "sketch.finish", "params": {}},
    ]
    if hide:
        steps.append(
            {
                "command": "browser.visibility",
                "params": {"visible": False, "items": [name]},
            }
        )
    return steps


# Function `send_batch()`:
def send_batch(transport: Transport, steps: list[Step]) -> dict[str, JSON]:
    """Run steps as one batch, with no rollback, and return the reply.

    Arguments:
    * `transport` (`Transport`): The session.
    * `steps` (`list[Step]`): The steps.

    Returns:
    * (`dict[str, JSON]`): The reply: `completed`, `results`,
      `timings`, `total_ms`.

    Raises:
    * `SolidCraftError`: If a step failed (or the batch was refused).
    """
    # The GUI's `engine.batch`, or the headless MCP `batch` tool.
    commands: list[JSON] = list(steps)
    params: dict[str, JSON] = {
        "commands": commands,
        "rollback": False,
        "timings": True,
    }
    reply: JSON
    if isinstance(transport, HeadlessTransport):
        if transport.process is None:
            transport.start()
        result: JSON = transport.call(
            "tools/call", {"name": "batch", "arguments": params}
        )
        assert isinstance(result, dict)
        content: JSON = result["content"]
        assert isinstance(content, list) and isinstance(content[0], dict)
        reply = json.loads(str(content[0]["text"]))
    else:
        reply = transport.request("engine.batch", params)

    # Every step must have run.
    if (
        not isinstance(reply, dict)
        or "failed" in reply
        or reply.get("completed") != len(steps)
    ):
        raise SolidCraftError("engine.batch", str(reply)[:2000], False, False)
    return reply


# Function `wires_made()`:
def wires_made(reply: Mapping[str, JSON]) -> int:
    """Count the wires a batch's drawing steps made.

    Arguments:
    * `reply` (`Mapping[str, JSON]`): The batch's reply.

    Returns:
    * (`int`): How many curves its steps reported.
    """
    results: JSON = reply["results"]
    assert isinstance(results, list)
    return sum(
        len(result["curves"])
        for result in results
        if isinstance(result, dict) and isinstance(result.get("curves"), list)
    )


# Class `_Shared`:
@dataclass(slots=True)
class _Shared(Transport):
    """A transport that passes requests on, and never closes it.

    So that `solidcraftcnc_demo.model()`, which closes the transport it
    makes, models the plate in the probe's own session.

    Attributes:
    * `inner` (`Transport`): The probe's transport.

    Constructor:
    * `_Shared(inner)`
    """

    # Constructor arguments:
    inner: Transport = field(init=True)

    # Method `_Shared.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Pass a request on.

        Arguments:
        * `method` (`str`): The method.
        * `params` (`Mapping[str, JSON]`): Its parameters.

        Returns:
        * (`JSON`): The result.
        """
        return self.inner.request(method, params)


# Function `model_plate()`:
def model_plate(transport: Transport) -> str:
    """Model the demonstration's plate, with no tool path drawn.

    Arguments:
    * `transport` (`Transport`): The session to model it in.

    Returns:
    * (`str`): The demonstration's G-code.

    Raises:
    * `RuntimeError`: If the demonstration failed.
    """
    # The demonstration, with its path drawing left out, in this
    # session, its G-code caught.
    shared: _Shared = _Shared(transport)
    names: dict[str, object] = vars(solidcraftcnc_demo)
    saved: dict[str, object] = {
        "sketch_path": names["sketch_path"],
        "connect": names["connect"],
    }
    arguments: list[str] = sys.argv
    gcode: io.StringIO = io.StringIO()
    status: int
    try:
        names.update(sketch_path=lambda *_: [], connect=lambda _: shared)
        sys.argv = ["solidcraftcnc_demo.py", "shared"]
        with contextlib.redirect_stdout(gcode):
            status = solidcraftcnc_demo.main()
    finally:
        names.update(saved)
        sys.argv = arguments
    if status != 0:
        raise RuntimeError(f"the demonstration failed ({status=})")
    return gcode.getvalue()


# Function `report()`:
def report(label: str, times: list[float]) -> str:
    """Summarize command times.

    Arguments:
    * `label` (`str`): What was timed.
    * `times` (`list[float]`): The times (seconds).

    Returns:
    * (`str`): Their count, mean and largest, in milliseconds.
    """
    if not times:
        return f"{label}: none"
    return (
        f"{label}: {len(times)}, mean {statistics.mean(times) * 1e3:.1f} "
        f"ms, max {max(times) * 1e3:.1f} ms"
    )


# Function `toggle()`:
def toggle(solidcraft: SolidCraftPyBind, names: list[str]) -> None:
    """Hide and show each sketch again, timing each, and print them.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The session.
    * `names` (`list[str]`): The sketches.
    """
    hides: list[float] = []
    shows: list[float] = []
    name: str
    for name in names:
        visible: bool
        for visible in (False, True):
            start: float = time.monotonic()
            solidcraft.browser.visibility(visible=visible, items=[name])
            (shows if visible else hides).append(time.monotonic() - start)
    print(f"{report('hides', hides)}; {report('shows', shows)}")


# Function `main()`:
def main() -> int:
    """Draw the path as one sketch per group, timing each batch.

    Returns:
    * (`int`): The exit status.
    """
    # The arguments.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Time drawing a G-code path as a sketch per tool."
    )
    parser.add_argument("where", help="a control port, or headless")
    parser.add_argument("--ngc", type=Path, help="the G-code (inches)")
    parser.add_argument("--plate", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--arcs", action="store_true")
    parser.add_argument("--mixed", action="store_true")
    parser.add_argument("--hide", action="store_true")
    parser.add_argument("--toggle", action="store_true")
    options: argparse.Namespace = parser.parse_args()
    if options.ngc is None and not options.plate:
        options.ngc = Path("demo.ngc")

    # A headless session uses the extracted `solidcraft-cli` when none
    # is on the `PATH`.
    transport: Transport = connect(options.where)
    if (
        isinstance(transport, HeadlessTransport)
        and shutil.which(transport.cli) is None
        and solidcraftcnc_demo.SOLIDCRAFT_CLI.exists()
    ):
        transport = HeadlessTransport(
            cli=str(solidcraftcnc_demo.SOLIDCRAFT_CLI)
        )

    with transport:
        # A new design, and the plate, as asked.
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
        if not options.keep:
            solidcraft.file.new(name="Batch probe")
        gcode: str = ""
        if options.plate:
            start: float = time.monotonic()
            gcode = model_plate(transport)
            print(f"plate: {time.monotonic() - start:.1f} s", flush=True)
        if options.ngc is not None:
            gcode = options.ngc.read_text(encoding="utf-8")

        # One batch per group.
        groups: dict[str, list[Move]] = group_moves(
            command_moves(read_gcode(gcode)), options.mixed
        )
        began: float = time.monotonic()
        total: tuple[int, int, int] = (0, 0, 0)
        name: str
        moves: list[Move]
        for name, moves in groups.items():
            drawing: list[Step] = path_steps(moves, MM_PER_INCH, options.arcs)
            steps: list[Step] = sketch_steps(name, drawing, options.hide)
            points: int = sum(
                len(params["points"])
                for step in drawing
                if isinstance(params := step["params"], dict)
                and isinstance(params.get("points"), list)
            )
            start = time.monotonic()
            reply: dict[str, JSON] = send_batch(transport, steps)
            took: float = time.monotonic() - start
            wires: int = wires_made(reply)
            print(
                f"{name}: {len(moves)} moves, {len(drawing)} drawing "
                f"steps, {points} points, {wires} wires: {took * 1e3:.0f} "
                f"ms ({reply.get('total_ms')} ms in SolidCraft)",
                flush=True,
            )
            total = (
                total[0] + len(drawing),
                total[1] + points,
                total[2] + wires,
            )
        print(
            f"{len(groups)} sketches, {total[0]} drawing steps, {total[1]} "
            f"points, {total[2]} wires: "
            f"{time.monotonic() - began:.2f} s",
            flush=True,
        )

        # Hide and show each sketch, timed.
        if options.toggle:
            toggle(solidcraft, list(groups))
    return 0


if __name__ == "__main__":
    sys.exit(main())
