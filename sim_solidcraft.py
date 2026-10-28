"""Show a running program in SolidCraft: the tool, and the path behind it.

The SolidCraft side of the simulation (`T.rlg~3.3`), split out of
`sim_linuxcnc.py`, which drives LinuxCNC and hands each position it
polls to listeners.  `SolidCraftDisplay` is such a listener: every
tool of a shop's machine is modeled (`sctoolmodel`), hidden, in a
SolidCraft session where `solidcraftcnc_demo.py` has modeled the part,
and the one in the spindle is shown, following the position; behind
it, the path it has taken is shown, sketched beforehand
(`RevealTrace`; unless `--no-trace`).  SolidCraft's coordinates are
the program's, in millimeters.

It is used through `sim_linuxcnc.py`'s `--solidcraft PORT` (or
`--solidcraft headless`), whose options `add_arguments()` adds:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
solidcraft --control 8080 &
./solidcraftcnc_demo.py 8080 > demo.ngc
distrobox enter lcnc -- ./sim_linuxcnc.py demo.ngc --solidcraft 8080
```

When SolidCraft fails or stops answering (as when its window is
closed), `SolidCraftDisplay.sample()` raises, and `sim_linuxcnc.py`
stops the program.  Nothing here needs LinuxCNC, so it runs anywhere
`scraftpybind` does.
"""

import argparse
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from scplot import Move, command_moves, draw_moves, read_gcode
from scraftpybind import (
    JSON,
    HeadlessTransport,
    SolidCraftPyBind,
    Transport,
    connect,
)
from sctoolmodel import model, profile
from shops import loaded_tools, read

# SolidCraft's coordinates are millimeters.
MM_PER_INCH: float = 25.4

# The tools' color in SolidCraft.
TOOL_COLOR: str = "#e07020"

# A position: X, Y and Z (inches, program coordinates).
Position = tuple[float, float, float]

# The trace's sketches are named this, then their G-code lines.
TRACE_NAME: str = "Trace"

# A `solidcraft-cli` extracted from SolidCraft's AppImage, for
# headless sessions (see `transport()`).
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parent
    / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
)


# Class `Sample`:
class Sample(Protocol):
    """What the display reads of a sample (`sim_linuxcnc.Sample`).

    Attributes:
    * `line` (`int`): The G-code line being run (from 1).
    * `tool` (`int`): The T number of the tool in the spindle (0 for
      none).
    * `position` (`Position`): The tool tip's X, Y and Z (inches,
      program coordinates).
    """

    # Property `Sample.line`:
    @property
    def line(self) -> int:
        """The G-code line being run (from 1)."""

    # Property `Sample.tool`:
    @property
    def tool(self) -> int:
        """The T number of the tool in the spindle (0 for none)."""

    # Property `Sample.position`:
    @property
    def position(self) -> Position:
        """The tool tip's X, Y and Z (inches, program coordinates)."""


# Class `ToolModel`:
# It keeps the last position between moves, so it is a class with
# one method.
class ToolModel:  # pylint: disable=too-few-public-methods
    """One tool in SolidCraft, made from its description in the shop.

    Its tip starts at the program's zero.  SolidCraft moves a
    component only by a step from where it is, so the position it was
    last sent to is kept, and each move sends the difference; a move
    is sent only when the tool has moved.

    Attributes:
    * `body` (`str`): Its body.
    * `occurrence` (`str`): Its component's occurrence.
    * `position` (`Position`): Where its tip was last sent.
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    """

    # Method `ToolModel.__init__()`:
    def __init__(
        self,
        solidcraft: SolidCraftPyBind,
        number: int,
        tool: tuple[str, dict[str, object]],
    ) -> None:
        """Model the tool, as a component of its own, hidden.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`):
          The SolidCraft session.
        * `number` (`int`):
          Its T number, which names it (`T1`, ...).
        * `tool` (`tuple[str, dict[str, object]]`):
          Its list in the tools file, and its description (from
          `shops.loaded_tools()`).
        """
        # The tool, standing on its tip at the program's zero.
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.position: Position = (0.0, 0.0, 0.0)
        self.body: str = model(solidcraft, f"T{number}", profile(*tool))
        solidcraft.appearance.assign(bodies=[self.body], color=TOOL_COLOR)

        # Make it a component, find its occurrence by name, and unground
        # it (a design's first component is grounded, and can not move).
        made: JSON = solidcraft.component.from_bodies(bodies=[self.body])
        assert isinstance(made, dict) and isinstance(made["components"], list)
        component: JSON = made["components"][0]
        assert isinstance(component, dict)
        listed: JSON = solidcraft.component.list(compact=True)
        assert isinstance(listed, dict) and isinstance(
            listed["components"], list
        )
        self.occurrence: str = next(
            str(occurrence["name"])
            for entry in listed["components"]
            if isinstance(entry, dict)
            and entry["id"] == component["component"]
            and isinstance(entry["occurrences"], list)
            for occurrence in entry["occurrences"]
            if isinstance(occurrence, dict)
        )
        solidcraft.occurrence.ground(
            occurrence=self.occurrence, grounded=False
        )
        solidcraft.browser.visibility(visible=False, items=[self.body])

    # Method `ToolModel.move_to()`:
    def move_to(self, position: Position) -> None:
        """Move the tip to a position, if it is not there already.

        Arguments:
        * `position` (`Position`): Where the tip goes.
        """
        if position == self.position:
            return
        dx, dy, dz = (
            (new - old) * MM_PER_INCH
            for new, old in zip(position, self.position, strict=True)
        )
        self.solidcraft.occurrence.move(
            occurrence=self.occurrence,
            space="world",
            translate=(dx, dy, dz),
            capture=False,
        )
        self.position = position


# Class `ToolRack`:
# It keeps the tool shown between moves, so it is a class with one
# method.
class ToolRack:  # pylint: disable=too-few-public-methods
    """Every tool of a machine in SolidCraft; the one in use is shown.

    Attributes:
    * `current` (`int`): The T number of the tool shown (0 for none).
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    * `tools` (`dict[int, ToolModel]`): The tools, by T number.
    """

    # Method `ToolRack.__init__()`:
    def __init__(
        self,
        solidcraft: SolidCraftPyBind,
        tools: dict[int, tuple[str, dict[str, object]]],
    ) -> None:
        """Model every tool, hidden.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`):
          The SolidCraft session.
        * `tools` (`dict[int, tuple[str, dict[str, object]]]`):
          The tools, by T number (from `shops.loaded_tools()`).
        """
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.current: int = 0
        self.tools: dict[int, ToolModel] = {
            number: ToolModel(solidcraft, number, tool)
            for number, tool in sorted(tools.items())
        }

    # Method `ToolRack.move_to()`:
    def move_to(self, number: int, position: Position) -> None:
        """Show the tool in the spindle, at a position.

        Arguments:
        * `number` (`int`):
          The T number of the tool in the spindle (0 for none, or
          one the rack does not have, which shows none).
        * `position` (`Position`): Where its tip is.
        """
        # On a tool change, hide the old tool, and move the new one
        # into place before showing it.
        if number != self.current:
            if self.current in self.tools:
                self.solidcraft.browser.visibility(
                    visible=False, items=[self.tools[self.current].body]
                )
            self.current = number
            if number in self.tools:
                self.tools[number].move_to(position)
                self.solidcraft.browser.visibility(
                    visible=True, items=[self.tools[number].body]
                )
        if number in self.tools:
            self.tools[number].move_to(position)


# Class `RevealTrace`:
# It keeps which sketches are shown between samples, so it is a class
# with one method.
class RevealTrace:  # pylint: disable=too-few-public-methods
    """The planned path, shown in SolidCraft as the tool reaches it.

    Drawing the path as the tool goes is slow, since every change to a
    sketch makes SolidCraft (0.25) refresh the whole design, while
    showing a hidden sketch is cheap (4 to 8 ms beside the demo's plate,
    by `probe_reveal.py`).  So the path is drawn beforehand, a hidden
    3D sketch for each G-code line that moves (`TRACE_NAME` and the
    line: "Trace 27"), and each is shown when LinuxCNC's `motion_line`
    reaches its line (a long move shows all at once, as it starts).
    Sketch lines all look alike, so the planned path's own sketches
    (`scplot.sketch_path()`) would hide it: every sketch is hidden
    first, and they can be shown again from the browser.  The program
    is taken to be in inches.

    Attributes:
    * `next` (`int`): The index in `sketches` of the first not shown.
    * `sketches` (`list[tuple[int, str]]`): Each sketch's G-code line
      (from 1, as `motion_line` counts) and name, in order.
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    """

    # Method `RevealTrace.__init__()`:
    def __init__(self, solidcraft: SolidCraftPyBind, program: Path) -> None:
        """Hide every sketch, and draw the program's path, hidden.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `program` (`Path`): The G-code file (as `SCCNC` writes it).
        """
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.next: int = 0
        self.sketches: list[tuple[int, str]] = []
        solidcraft.browser.visibility(visible=False, folder="sketches")

        # Gather the moves by line, and draw each line's moves.
        lines: dict[int, list[Move]] = {}
        move: Move
        for move in command_moves(
            read_gcode(program.read_text(encoding="utf-8"))
        ):
            lines.setdefault(move["line"] + 1, []).append(move)
        line: int
        moves: list[Move]
        for line, moves in lines.items():
            name: str = f"{TRACE_NAME} {line}"
            solidcraft.sketch.create(plane="XY", name=name)
            solidcraft.sketch.options(
                sketch_3d=True,
                show_points=False,
                show_profile=False,
                show_constraints=False,
                show_dimensions=False,
            )
            draw_moves(solidcraft, moves, MM_PER_INCH)
            solidcraft.sketch.finish()
            solidcraft.browser.visibility(visible=False, items=[name])
            self.sketches.append((line, name))

    # Method `RevealTrace.reveal()`:
    def reveal(self, line: int) -> None:
        """Show every sketch of the path up to a line, in one command.

        Arguments:
        * `line` (`int`): The G-code line being run (from 1).
        """
        names: list[str] = []
        while (
            self.next < len(self.sketches)
            and self.sketches[self.next][0] <= line
        ):
            names.append(self.sketches[self.next][1])
            self.next += 1
        if names:
            self.solidcraft.browser.visibility(visible=True, items=names)


# Class `SolidCraftDisplay`:
class SolidCraftDisplay:
    """A `sim_linuxcnc.Listener` that shows the run in SolidCraft.

    Attributes:
    * `rack` (`ToolRack`): The tools, whose one in the spindle
      follows the position.
    * `trace` (`RevealTrace | None`): The path, shown as the tool
      reaches it, if any.
    """

    # Method `SolidCraftDisplay.__init__()`:
    def __init__(
        self,
        solidcraft: SolidCraftPyBind,
        tools: dict[int, tuple[str, dict[str, object]]],
        program: Path | None,
    ) -> None:
        """Model the tools, and draw the program's path (if any).

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`):
          The SolidCraft session.
        * `tools` (`dict[int, tuple[str, dict[str, object]]]`):
          The tools, by T number (from `shops.loaded_tools()`).
        * `program` (`Path | None`):
          The G-code file whose path is traced, or `None` for no
          trace.
        """
        self.rack: ToolRack = ToolRack(solidcraft, tools)
        self.trace: RevealTrace | None = None
        if program is not None:
            start: float = time.monotonic()
            self.trace = RevealTrace(solidcraft, program)
            print(
                f"trace: {len(self.trace.sketches)} sketches in "
                f"{time.monotonic() - start:.1f} s",
                flush=True,
            )

    # Method `SolidCraftDisplay.sample()`:
    def sample(self, sample: Sample) -> None:
        """Show the tool in the spindle where it is, and its path.

        Arguments:
        * `sample` (`Sample`): Where the tool is.

        Raises:
        * `SolidCraftError` or `OSError`: If SolidCraft fails or stops
          answering.
        """
        self.rack.move_to(sample.tool, sample.position)
        if self.trace is not None:
            self.trace.reveal(sample.line)

    # Method `SolidCraftDisplay.finish()`:
    def finish(self) -> None:
        """Show all of the path, when the program is done."""
        if self.trace is not None:
            self.trace.reveal(sys.maxsize)


# Function `add_arguments()`:
def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the display's options to a command line.

    Arguments:
    * `parser` (`argparse.ArgumentParser`): The command line.
    """
    parser.add_argument(
        "--solidcraft",
        metavar="PORT",
        default="",
        help="a SolidCraft GUI's control port (or `headless`), "
        "where a tool follows",
    )
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="do not show the path in SolidCraft as the tool goes",
    )


# Function `transport()`:
def transport(where: str) -> Transport:
    """Return a transport to SolidCraft.

    A headless session uses the extracted `solidcraft-cli`
    (`SOLIDCRAFT_CLI`) when it exists, even when another is on the
    `PATH`: the one the AppImage puts there (`~/.local/bin`) runs the
    AppImage, which needs FUSE, and the `lcnc` box has no `fusermount`
    ("No suitable fusermount binary found").

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.

    Returns:
    * (`Transport`): The transport, which connects on first use.

    Raises:
    * `ValueError`: If `where` is neither.
    """
    found: Transport = connect(where)
    if isinstance(found, HeadlessTransport) and SOLIDCRAFT_CLI.exists():
        found = HeadlessTransport(cli=str(SOLIDCRAFT_CLI))
    return found


# Function `display()`:
@contextmanager
def display(
    options: argparse.Namespace, program: Path
) -> Iterator[SolidCraftDisplay]:
    """Connect to SolidCraft and set the display up, for the run.

    Arguments:
    * `options` (`argparse.Namespace`): The command line, with
      `solidcraft` and `no_trace` (from `add_arguments()`), and
      `shop` and `machine`.
    * `program` (`Path`): The G-code file that runs.

    Yields:
    * (`SolidCraftDisplay`): The display, to hand the samples to.

    Raises:
    * `SolidCraftError` or `OSError`: If SolidCraft fails or is not
      there.
    """
    with transport(options.solidcraft) as session:
        yield SolidCraftDisplay(
            SolidCraftPyBind(session),
            loaded_tools(read(options.shop), options.machine),
            None if options.no_trace else program,
        )
