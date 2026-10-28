#!/usr/bin/env python3
"""Time revealing a hidden tool path, piece by piece, in SolidCraft.

A probe for the live trace (`T.s2~3`): instead of drawing the path as
the tool goes, which rebuilds the model on every edit, the path is
drawn beforehand as `--sketches` small 3D sketches (each `--segments`
straight pieces), all hidden, and each is shown (`browser.visibility`)
as a tool (a component, moved by `occurrence.move`) reaches it.  It
prints how long the building took and how long the shows and moves
took, at the start, middle and end of the reveal:

```
./probe_reveal.py headless --sketches 100
./probe_reveal.py 8080 --sketches 300 --keep
./probe_reveal.py headless --sketches 500 --cylinders
```

With `--cylinders`, each piece is a thin cylinder (`solid.cylinder`,
a body) from one corner of the path to the next instead, made with no
sketch, and all are hidden in one command; the building time is
printed every 100.

With `--live`, nothing is made beforehand: while the tool moves (at
`--rate`), a new 3D sketch of `--segments` pieces is made after every
`--every` moves (`sketch.create`, `sketch.options`, `sketch.line3d`,
`sketch.finish`, as the trace would as it went), up to `--sketches`.
It prints the sketch times, the move times and the largest gap
between the starts of two moves (the tool's stall), by thirds:

```
./probe_reveal.py 8080 --keep --live --sketches 300 --every 12
```

`--keep` adds to the design open in the GUI (e.g. the demonstration's
plate) instead of starting a new one.  It stops itself when a command
takes longer than `--slow` seconds, or the reveal runs past
`--limit` seconds.
"""

# `main()` builds and reveals in one place, so it has many locals and
# statements.
# pylint: disable=too-many-locals,too-many-statements

import argparse
import math
import statistics
import sys
import time
from collections.abc import Callable
from functools import partial

from scraftpybind import JSON, SolidCraftPyBind, connect


# Function `occurrence_of()`:
def occurrence_of(solidcraft: SolidCraftPyBind, body: str) -> str:
    """Make a body a component and return its occurrence's name.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `body` (`str`): The body.

    Returns:
    * (`str`): Its component's occurrence (e.g. `Tool:1`).
    """
    made: JSON = solidcraft.component.from_bodies(bodies=[body])
    assert isinstance(made, dict) and isinstance(made["components"], list)
    component: JSON = made["components"][0]
    assert isinstance(component, dict)
    listed: JSON = solidcraft.component.list(compact=True)
    assert isinstance(listed, dict) and isinstance(listed["components"], list)
    return next(
        str(occurrence["name"])
        for entry in listed["components"]
        if isinstance(entry, dict)
        and entry["id"] == component["component"]
        and isinstance(entry["occurrences"], list)
        for occurrence in entry["occurrences"]
        if isinstance(occurrence, dict)
    )


# Function `path_point()`:
def path_point(index: float) -> tuple[float, float, float]:
    """Return a corner of the probe's path (mm), a zigzag spiral.

    Arguments:
    * `index` (`float`): Which corner (a fraction is between two).

    Returns:
    * (`tuple[float, float, float]`): The corner.
    """
    angle: float = index * 0.3
    radius: float = 20.0 + index * 0.05
    return (
        radius * math.cos(angle),
        radius * math.sin(angle),
        -0.5 + 0.5 * math.cos(index * math.pi),
    )


# Function `cylinders()`:
def cylinders(
    solidcraft: SolidCraftPyBind, count: int, start: float
) -> list[str]:
    """Make the path's pieces as thin cylinders, then hide them all.

    Arguments:
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `count` (`int`): How many pieces.
    * `start` (`float`): When the building started (monotonic).

    Returns:
    * (`list[str]`): The cylinders' body names, in path order.
    """
    names: list[str] = []
    index: int
    for index in range(count):
        base: tuple[float, float, float] = path_point(index)
        end: tuple[float, float, float] = path_point(index + 1)
        axis: list[float] = [e - b for e, b in zip(end, base, strict=True)]
        name: str = f"Reveal {index + 1}"
        solidcraft.solid.cylinder(
            base=base,
            axis=axis,
            height=f"{math.hypot(*axis)} mm",
            diameter="0.5 mm",
            body_name=name,
        )
        names.append(name)
        if (index + 1) % 100 == 0:
            print(
                f"{index + 1} cylinders: {time.monotonic() - start:.1f} s",
                flush=True,
            )
    solidcraft.browser.visibility(visible=False, items=names)
    return names


# Function `report()`:
def report(label: str, times: list[float]) -> str:
    """Summarize command times.

    Arguments:
    * `label` (`str`): What was timed.
    * `times` (`list[float]`): The times (seconds).

    Returns:
    * (`str`): Its count, mean and largest, in milliseconds.
    """
    if not times:
        return f"{label}: none"
    return (
        f"{label}: {len(times)}, mean {statistics.mean(times) * 1e3:.1f} "
        f"ms, max {max(times) * 1e3:.1f} ms"
    )


# Class `Probe`:
# It only carries the timings and limits between its steps.
class Probe:  # pylint: disable=too-few-public-methods
    """The probe's session, timings and limits.

    Attributes:
    * `limit` (`float`): When the reveal must end (monotonic seconds).
    * `slow` (`float`): The longest a command may take (seconds).
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    """

    # Method `Probe.__init__()`:
    def __init__(self, solidcraft: SolidCraftPyBind, slow: float) -> None:
        """Start the probe.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `slow` (`float`): The longest a command may take (seconds).
        """
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.slow: float = slow
        self.limit: float = math.inf

    # Method `Probe.timed()`:
    def timed(
        self, times: list[float], what: str, command: Callable[[], JSON]
    ) -> None:
        """Run a command, adding its time, and stop if it is too slow.

        Arguments:
        * `times` (`list[float]`): Where its time goes.
        * `what` (`str`): What it does (`show`, `move` or `sketch`).
        * `command` (`Callable[[], JSON]`): The command.

        Raises:
        * `SystemExit`: If it took too long, or the time is up.
        """
        start: float = time.monotonic()
        command()
        took: float = time.monotonic() - start
        times.append(took)
        if took > self.slow:
            sys.exit(f"stopped: a {what} took {took:.2f} s")
        if time.monotonic() > self.limit:
            sys.exit("stopped: out of time")


# Function `live()`:
def live(probe: Probe, tool: str, options: argparse.Namespace) -> None:
    """Move the tool, making a sketch after every `--every` moves.

    Arguments:
    * `probe` (`Probe`): The probe (its session and limits).
    * `tool` (`str`): The tool's occurrence.
    * `options` (`argparse.Namespace`): The command line arguments.
    """
    solidcraft: SolidCraftPyBind = probe.solidcraft

    # Function `sketch()`:
    def sketch(number: int) -> JSON:
        """Make one sketch, as a live trace would.

        Arguments:
        * `number` (`int`): Which sketch (from 0).

        Returns:
        * (`JSON`): What `sketch.finish` answered.
        """
        solidcraft.sketch.create(plane="XY", name=f"Live {number + 1}")
        solidcraft.sketch.options(
            sketch_3d=True,
            show_points=False,
            show_profile=False,
            show_constraints=False,
            show_dimensions=False,
        )
        first: int = number * options.every
        solidcraft.sketch.line3d(
            points=[
                list(
                    path_point(
                        first + piece * options.every / options.segments
                    )
                )
                for piece in range(options.segments + 1)
            ]
        )
        return solidcraft.sketch.finish()

    # Move at the rate; a sketch after every `--every` moves.
    probe.limit = time.monotonic() + options.limit
    sketches: list[float] = []
    moves: list[float] = []
    gap: float = 0.0
    last: float = time.monotonic()
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    period: float = 1.0 / options.rate
    due: float = time.monotonic()
    third: int = max(1, options.sketches // 3)
    index: int
    for index in range(options.sketches * options.every):
        now: float = time.monotonic()
        gap = max(gap, now - last)
        last = now
        target: tuple[float, float, float] = path_point(index + 1)
        step_mm: tuple[float, float, float] = (
            target[0] - position[0],
            target[1] - position[1],
            target[2] - position[2],
        )
        probe.timed(
            moves,
            "move",
            partial(
                solidcraft.occurrence.move,
                occurrence=tool,
                space="world",
                translate=step_mm,
                capture=False,
            ),
        )
        position = target

        # A sketch of the pieces just passed, and a report by thirds.
        if (index + 1) % options.every == 0:
            number: int = index // options.every
            probe.timed(sketches, "sketch", partial(sketch, number))
            if (number + 1) % third == 0 or number + 1 == options.sketches:
                print(
                    f"to sketch {number + 1}: "
                    f"{report('sketches', sketches)}; "
                    f"{report('moves', moves)}; largest gap "
                    f"{gap * 1e3:.0f} ms",
                    flush=True,
                )
                sketches, moves, gap = [], [], 0.0
        due += period
        time.sleep(max(0.0, due - time.monotonic()))


# Function `main()`:
def main() -> None:
    """Build the hidden path, then reveal it, timing every command."""
    # The arguments.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Time revealing a hidden path in SolidCraft."
    )
    parser.add_argument("where", help="a control port, or headless")
    parser.add_argument("--sketches", type=int, default=100)
    parser.add_argument("--segments", type=int, default=5)
    parser.add_argument("--moves", type=int, default=4)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--slow", type=float, default=2.0)
    parser.add_argument("--limit", type=float, default=120.0)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--cylinders", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--every", type=int, default=12)
    options: argparse.Namespace = parser.parse_args()

    with connect(options.where) as transport:
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
        probe: Probe = Probe(solidcraft, options.slow)
        if not options.keep:
            solidcraft.file.new(name="Reveal probe")

        # The tool: a 1/4 x 1.5 inch cylinder, a component, ungrounded
        # (the first component of a design is grounded).
        start: float = time.monotonic()
        solidcraft.solid.cylinder(
            height="1.5 in", diameter="0.25 in", body_name="Probe tool"
        )
        tool: str = occurrence_of(solidcraft, "Probe tool")
        solidcraft.occurrence.ground(occurrence=tool, grounded=False)
        if options.live:
            live(probe, tool, options)
            return

        # The path, as hidden 3D sketches (or cylinders).
        names: list[str] = (
            cylinders(solidcraft, options.sketches, start)
            if options.cylinders
            else []
        )
        sketch: int
        for sketch in range(0 if options.cylinders else options.sketches):
            name: str = f"Reveal {sketch + 1}"
            solidcraft.sketch.create(plane="XY", name=name)
            solidcraft.sketch.options(sketch_3d=True)
            first: int = sketch * options.segments
            solidcraft.sketch.line3d(
                points=[
                    list(path_point(index))
                    for index in range(first, first + options.segments + 1)
                ]
            )
            solidcraft.sketch.finish()
            solidcraft.browser.visibility(visible=False, items=[name])
            names.append(name)
        print(
            f"built {options.sketches} sketches in "
            f"{time.monotonic() - start:.1f} s",
            flush=True,
        )

        # Reveal each sketch, then move the tool along it, at the rate.
        probe.limit = time.monotonic() + options.limit
        shows: list[float] = []
        moves: list[float] = []
        position: tuple[float, float, float] = (0.0, 0.0, 0.0)
        period: float = 1.0 / options.rate
        due: float = time.monotonic()
        third: int = max(1, options.sketches // 3)
        for sketch, name in enumerate(names):
            probe.timed(
                shows,
                "show",
                partial(
                    solidcraft.browser.visibility, visible=True, items=[name]
                ),
            )
            step: int
            for step in range(options.moves):
                target: tuple[float, float, float] = path_point(
                    sketch * options.segments
                    + (step + 1) * options.segments // options.moves
                )
                step_mm: tuple[float, float, float] = (
                    target[0] - position[0],
                    target[1] - position[1],
                    target[2] - position[2],
                )
                probe.timed(
                    moves,
                    "move",
                    partial(
                        solidcraft.occurrence.move,
                        occurrence=tool,
                        space="world",
                        translate=step_mm,
                        capture=False,
                    ),
                )
                position = target
                due += period
                time.sleep(max(0.0, due - time.monotonic()))
            if (sketch + 1) % third == 0 or sketch + 1 == len(names):
                print(
                    f"to sketch {sketch + 1}: {report('shows', shows)}; "
                    f"{report('moves', moves)}",
                    flush=True,
                )
                shows, moves = [], []


if __name__ == "__main__":
    main()
