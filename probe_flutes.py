#!/usr/bin/env python3
"""Move one tool of each kind, with lines in place of its flutes.

A probe of tools as plain bodies with their flutes only drawn on them,
each body and its lines in one component (`sctoolmodel.model_tool()`,
and for the countersink `sctoolmodel.as_component()`).  They stand in a
row along X, and each moves up and down in a small circle, in one
`engine.batch` per frame, until SolidCraft closes or `LIMIT` seconds
pass:

```
./probe_flutes.py 8080
```

It prints each tool's time to model, and the frames' times as it runs.
"""

import argparse
import math
import time

from scplot import SCStep, send_batch
from scraftpybind import SCPyBind, SCSolidCraftError, connect
from sctoolmodel import (
    EXAMPLE_SHOP,
    MM_PER_INCH,
    as_component,
    model_tool,
    shop_tools,
)
from shops import read
from tools import DOUBLE_END_COUNTERSINKS, DRILL_COLOR

# One tool of each kind, by `unique_id`: a square end mill, a ball end
# mill, a 4 flute rougher, a drill, a chamfer mill, a corner rounding
# mill and a double angle cutter.
EXAMPLES: tuple[int, ...] = (1, 3, 4, 5, 7, 8, 9)

# The double end countersink to show.
COUNTERSINK: str = "421-0261"

# How far apart the tools stand (inches).
SPACING: float = 1.5

# The motion: updates a second, seconds around, and how far (mm).
RATE: float = 20.0
PERIOD: float = 6.0
BOB: float = 30.0
CIRCLE: float = 8.0

# The longest run (seconds).
LIMIT: float = 300.0


# Function `model_examples()`:
def model_examples(solidcraft: SCPyBind) -> list[str]:
    """Model the examples, each as a component with its lines.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.

    Returns:
    * (`list[str]`): The occurrences' names.
    """
    occurrences: list[str] = []

    # The tools of the shop.
    tools = {
        tool["unique_id"]: (key, tool)
        for key, tool in shop_tools(read(EXAMPLE_SHOP))
    }
    for index, unique_id in enumerate(EXAMPLES):
        start: float = time.perf_counter()
        key, tool = tools[unique_id]
        at: tuple[float, float, float] = (index * SPACING, 0.0, 0.0)
        occurrences.append(
            model_tool(
                solidcraft, f"Tool {unique_id}", (key, tool), at, DRILL_COLOR
            ).occurrence
        )
        print(f"{tool['name']}: {time.perf_counter() - start:.2f} s")

    # The double end countersink, whose sizes are in millimeters.
    start = time.perf_counter()
    countersink = DOUBLE_END_COUNTERSINKS[COUNTERSINK]
    tip: tuple[float, float, float] = (
        len(EXAMPLES) * SPACING * MM_PER_INCH,
        0.0,
        0.0,
    )
    body: str = countersink.model(solidcraft, tip)
    occurrences.append(
        as_component(solidcraft, body, f"{countersink.name()} flutes")
    )
    print(f"{countersink.name()}: {time.perf_counter() - start:.2f} s")
    return occurrences


# Function `offset()`:
def offset(index: int, seconds: float) -> tuple[float, float, float]:
    """Return how far a tool is from its start.

    Arguments:
    * `index` (`int`): Which tool, which sets its phase.
    * `seconds` (`float`): The time since the motion started.

    Returns:
    * (`tuple[float, float, float]`): The offset (millimeters).
    """
    angle: float = 2.0 * math.pi * seconds / PERIOD + index * 0.6
    start: float = index * 0.6
    return (
        CIRCLE * (math.cos(angle) - math.cos(start)),
        CIRCLE * (math.sin(angle) - math.sin(start)),
        BOB * (math.sin(angle) - math.sin(start)),
    )


# Function `move_until_closed()`:
def move_until_closed(solidcraft: SCPyBind, occurrences: list[str]) -> None:
    """Move the tools until SolidCraft closes, or `LIMIT` seconds pass.

    Arguments:
    * `solidcraft` (`SCPyBind`): The SolidCraft session.
    * `occurrences` (`list[str]`): The occurrences to move.
    """
    began: float = time.perf_counter()
    last: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(
        occurrences
    )
    frames: int = 0
    total: float = 0.0
    worst: float = 0.0
    try:
        while (now := time.perf_counter() - began) < LIMIT:
            new: list[tuple[float, float, float]] = [
                offset(index, now) for index in range(len(occurrences))
            ]
            steps: list[SCStep] = [
                {
                    "command": "occurrence.move",
                    "params": {
                        "occurrence": occurrence,
                        "space": "world",
                        "translate": [
                            value - old
                            for value, old in zip(there, here, strict=True)
                        ],
                        "capture": False,
                    },
                }
                for occurrence, there, here in zip(
                    occurrences, new, last, strict=True
                )
            ]
            sent: float = time.perf_counter()
            send_batch(solidcraft, steps)
            took: float = time.perf_counter() - sent
            total += took
            worst = max(worst, took)
            frames += 1
            last = new
            if frames % 100 == 0:
                print(
                    f"{now:.0f} s: {frames} frames, mean "
                    f"{1000 * total / frames:.1f} ms, "
                    f"worst {1000 * worst:.0f} ms",
                    flush=True,
                )
            spent: float = time.perf_counter() - began - now
            time.sleep(max(0.0, 1.0 / RATE - spent))
    except (SCSolidCraftError, OSError) as error:
        print(f"Stopped: {type(error).__name__}", flush=True)
    print(
        f"End: {frames} frames in {time.perf_counter() - began:.0f} s, mean "
        f"{1000 * total / max(frames, 1):.1f} ms, worst {1000 * worst:.0f} ms"
    )


# Function `main()`:
def main() -> None:
    """Show the examples moving in the SolidCraft at a port."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Move one tool of each kind, with lines for flutes."
    )
    parser.add_argument("target", nargs="?", default="8080")
    arguments: argparse.Namespace = parser.parse_args()
    with connect(arguments.target) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.file.new()
        move_until_closed(solidcraft, model_examples(solidcraft))


if __name__ == "__main__":
    main()
