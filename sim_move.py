#!/usr/bin/env python3
"""Slide a cube back and forth in SolidCraft, to see how it animates.

The first step of the simulation (`T.s2~3`): a 20 mm cube, made a
component, moves along X by its own width and back, in steps of
`--step` millimeters `--interval` seconds apart, beside a reference
cube (40 mm along +Y) that never moves, so that it is clear on the
screen which one moved.  It prints how long each move took to answer:

```
./sim_move.py 8080                      # 1 mm steps, 40 a second
./sim_move.py 8080 --step 20 --interval 1 --report
./sim_move.py headless --method solid
```

The methods are `pending` (`occurrence.move` with `capture=False`,
which adds nothing to the design's timeline: the one to use),
`captured` (`occurrence.move`) and `solid` (`solid.move`, which adds a
timeline feature per move).  A SolidCraft GUI answers about 20 moves
a second however fast they are sent.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

from scraftpybind import (
    HeadlessTransport,
    SolidCraftPyBind,
    Transport,
    connect,
)

# A `solidcraft-cli` extracted from SolidCraft's AppImage, for
# headless sessions when none is on the `PATH` (as in
# `solidcraftcnc_demo.py`).
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parent
    / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
)

# The cubes' size (mm); the moving one goes this far and back.
SIZE: float = 20.0


# Function `arguments()`:
def arguments() -> argparse.Namespace:
    """Read the command line.

    Returns:
    * (`argparse.Namespace`): The arguments.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Slide a cube back and forth in SolidCraft."
    )
    parser.add_argument(
        "where", help="a SolidCraft GUI's control port, or `headless`"
    )
    parser.add_argument(
        "--method",
        choices=("pending", "captured", "solid"),
        default="pending",
        help="how to move the cube (default: pending)",
    )
    parser.add_argument(
        "--step", type=float, default=1.0, help="mm per move (default: 1)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.025,
        help="seconds between moves (default: 0.025)",
    )
    parser.add_argument(
        "--trips", type=int, default=10, help="round trips (default: 10)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print every move, with the cube's X read back",
    )
    return parser.parse_args()


# Function `setup()`:
def setup(solidcraft: SolidCraftPyBind, method: str) -> None:
    """Make the moving cube and the reference cube, and fix the view.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`):
      The SolidCraft session.
    * `method` (`str`):
      The move method; all but `solid` move a component.
    """
    # The moving cube, made a component (`Cube:1`) unless it is moved
    # as a body.
    solidcraft.solid.box(
        length=SIZE, width=SIZE, height=SIZE, body_name="Cube"
    )
    if method != "solid":
        solidcraft.component.from_bodies(bodies=["Cube"])

    # The reference cube, and a view that does not follow anything.
    solidcraft.solid.box(
        length=SIZE,
        width=SIZE,
        height=SIZE,
        corner=[0, 2 * SIZE, 0],
        body_name="Reference",
    )
    solidcraft.view.apply(view="iso")


# Function `move()`:
def move(solidcraft: SolidCraftPyBind, method: str, dx: float) -> None:
    """Move the cube along X.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`):
      The SolidCraft session.
    * `method` (`str`):
      `pending`, `captured` or `solid`.
    * `dx` (`float`):
      How far to move it (mm).
    """
    if method == "solid":
        solidcraft.solid.move(bodies=["Cube"], translate=(dx, 0, 0))
    else:
        solidcraft.occurrence.move(
            occurrence="Cube:1",
            space="world",
            translate=(dx, 0, 0),
            capture=method == "captured",
        )


# Function `cube_x()`:
def cube_x(solidcraft: SolidCraftPyBind, method: str) -> str:
    """Read the moving cube's lowest X back from SolidCraft.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`):
      The SolidCraft session.
    * `method` (`str`):
      The move method; a body (`solid`) is not read back.

    Returns:
    * (`str`): The X (mm), or `?` for a body.
    """
    if method == "solid":
        return "?"
    properties = solidcraft.occurrence.properties(occurrence="Cube:1")
    assert isinstance(properties, dict)
    total = properties["total"]
    assert isinstance(total, dict)
    bbox = total["bbox"]
    assert isinstance(bbox, dict)
    low = bbox["min"]
    assert isinstance(low, list)
    return f"{low[0]:.3f}"


# Function `run()`:
def run(solidcraft: SolidCraftPyBind, options: argparse.Namespace) -> None:
    """Slide the cube back and forth, and print the timing.

    Each move is sent on a fixed schedule, so slow answers do not
    stretch the run; a move sent after its time is counted as late.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`):
      The SolidCraft session.
    * `options` (`argparse.Namespace`):
      The command line arguments.
    """
    # Set up, and give the GUI a moment to draw it.
    method: str = options.method
    setup(solidcraft, method)
    time.sleep(1.0)

    # Move it, timing each move's answer.
    steps: int = max(1, round(SIZE / options.step))
    times: list[float] = []
    late: int = 0
    start: float = time.monotonic()
    tick: float = start
    for _ in range(options.trips):
        for direction in (1, -1):
            for _ in range(steps):
                before: float = time.monotonic()
                move(solidcraft, method, direction * options.step)
                times.append(time.monotonic() - before)
                if options.report:
                    print(
                        f"move {len(times):4d} "
                        f"{times[-1] * 1000:7.1f} ms "
                        f"x={cube_x(solidcraft, method)}",
                        flush=True,
                    )
                tick += options.interval
                pause: float = tick - time.monotonic()
                if pause > 0:
                    time.sleep(pause)
                else:
                    late += 1

    # Report.
    total: float = time.monotonic() - start
    times.sort()
    print(
        f"{len(times)} moves in {total:.2f} s "
        f"({len(times) / total:.1f} a second), {late} late"
    )
    print(
        f"answer: median {times[len(times) // 2] * 1000:.1f} ms, "
        f"max {times[-1] * 1000:.1f} ms; "
        f"cube x {cube_x(solidcraft, method)} (started at 0)"
    )


# Function `main()`:
def main() -> int:
    """Run the test.

    Returns:
    * (`int`): The exit status.
    """
    # Connect, using the extracted `solidcraft-cli` when there is none
    # on the `PATH`.
    options: argparse.Namespace = arguments()
    transport: Transport = connect(options.where)
    if (
        isinstance(transport, HeadlessTransport)
        and shutil.which(transport.cli) is None
        and SOLIDCRAFT_CLI.exists()
    ):
        transport = HeadlessTransport(cli=str(SOLIDCRAFT_CLI))

    # A SolidCraft that is not there is reported in one line.
    try:
        with transport:
            run(SolidCraftPyBind(transport), options)
    except OSError as error:
        print(f"sim_move.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
