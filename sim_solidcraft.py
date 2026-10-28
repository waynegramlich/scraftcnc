"""Show a running program in SolidCraft: the tool and its path.

The SolidCraft side of the simulation (`T.rlg~3.3`), split out of
`sim_linuxcnc.py`, which drives LinuxCNC and hands each position it
polls to listeners.  `SolidCraftDisplay` is such a listener: every
tool of a shop's machine is modeled (`sctoolmodel`), hidden, in a
SolidCraft session where `solidcraftcnc_demo.py` has modeled the part,
and the one in the spindle is shown, following the position.  Each
tool's planned path is drawn from the program, one tool ahead of the
run, as a hidden 3D sketch built with one batch (`probe_batch`), and
only the path of the tool in the spindle is shown, whole (the user's
choice, 2026-10-28; an earlier `RevealTrace` showed the path line by
line as the tool reached it, but took 48 s to set up).  SolidCraft's
coordinates are the program's, in millimeters.

It is used through `sim_linuxcnc.py`'s `--solidcraft PORT` (or
`--solidcraft headless`), whose options `add_arguments()` adds:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
solidcraft --control 8080 &
./solidcraftcnc_demo.py --no-path 8080 > demo.ngc
distrobox enter lcnc -- ./sim_linuxcnc.py demo.ngc --solidcraft 8080
```

When SolidCraft fails or stops answering (as when its window is
closed), `SolidCraftDisplay.sample()` raises, and `sim_linuxcnc.py`
stops the program.  Nothing here needs LinuxCNC, so it runs anywhere
`scraftpybind` does.
"""

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from probe_batch import path_steps, send_batch, sketch_steps
from scplot import Move, command_moves, read_gcode
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


# Class `PathRack`:
class PathRack:  # pylint: disable=too-few-public-methods
    """Each tool's planned path in SolidCraft; the one in use is shown.

    A path is drawn one tool ahead of the run: the first tool's before
    it starts, and the next tool's when a tool goes into the spindle,
    so no tool change waits for a drawing.

    Attributes:
    * `current` (`int`): The T number whose path is shown (0 for none).
    * `moves` (`dict[int, list[Move]]`): Each tool's moves, by T
      number, in the order the tools are first used.
    * `session` (`Transport`): The transport, for the batches.
    * `sketches` (`dict[int, str]`): Each drawn path's sketch, by T
      number.
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    """

    # Method `PathRack.__init__()`:
    def __init__(
        self, solidcraft: SolidCraftPyBind, session: Transport, program: Path
    ) -> None:
        """Group the moves by tool, and draw the first tool's path.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`):
          The SolidCraft session.
        * `session` (`Transport`): Its transport, for the batches.
        * `program` (`Path`): The G-code file.
        """
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.session: Transport = session
        self.current: int = 0
        self.sketches: dict[int, str] = {}

        # Group the moves by the tool in the spindle, in program order.
        moves: list[Move] = command_moves(
            read_gcode(program.read_text(encoding="utf-8"))
        )
        self.moves: dict[int, list[Move]] = {}
        move: Move
        for move in moves:
            self.moves.setdefault(move["tool"], []).append(move)

        # The first tool's path, ready for the start.
        if self.moves:
            self.draw(next(iter(self.moves)))

    # Method `PathRack.draw()`:
    def draw(self, number: int) -> None:
        """Draw a tool's whole path as a hidden 3D sketch (one batch).

        Arguments:
        * `number` (`int`): The T number; nothing is done when its
          path is drawn already, or it has no moves.
        """
        if number in self.sketches or number not in self.moves:
            return
        name: str = f"T{number:02d} path"
        send_batch(
            self.session,
            sketch_steps(
                name, path_steps(self.moves[number], MM_PER_INCH, False), True
            ),
        )
        self.sketches[number] = name

    # Method `PathRack.show()`:
    def show(self, number: int) -> None:
        """Show only the path of the tool in the spindle.

        Arguments:
        * `number` (`int`): The T number of the tool in the spindle.
        """
        if number == self.current:
            return
        if self.current in self.sketches:
            self.solidcraft.browser.visibility(
                visible=False, items=[self.sketches[self.current]]
            )
        self.current = number
        self.draw(number)
        if number in self.sketches:
            self.solidcraft.browser.visibility(
                visible=True, items=[self.sketches[number]]
            )

        # The next tool's path, drawn now, while this tool cuts.
        order: list[int] = list(self.moves)
        if number in order and order.index(number) + 1 < len(order):
            self.draw(order[order.index(number) + 1])


# Class `SolidCraftDisplay`:
class SolidCraftDisplay:
    """A `sim_linuxcnc.Listener` that shows the run in SolidCraft.

    Attributes:
    * `paths` (`PathRack`): Each tool's path; the one in the spindle
      is shown.
    * `rack` (`ToolRack`): The tools, whose one in the spindle
      follows the position.
    """

    # Method `SolidCraftDisplay.__init__()`:
    def __init__(
        self,
        solidcraft: SolidCraftPyBind,
        tools: dict[int, tuple[str, dict[str, object]]],
        paths: PathRack,
    ) -> None:
        """Model the tools.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`):
          The SolidCraft session.
        * `tools` (`dict[int, tuple[str, dict[str, object]]]`):
          The tools, by T number (from `shops.loaded_tools()`).
        * `paths` (`PathRack`): Each tool's path, drawn.
        """
        self.rack: ToolRack = ToolRack(solidcraft, tools)
        self.paths: PathRack = paths

    # Method `SolidCraftDisplay.sample()`:
    def sample(self, sample: Sample) -> None:
        """Show the tool in the spindle where it is, and its path.

        Arguments:
        * `sample` (`Sample`): Where the tool is.

        Raises:
        * `SolidCraftError` or `OSError`: If SolidCraft fails or stops
          answering.
        """
        self.paths.show(sample.tool)
        self.rack.move_to(sample.tool, sample.position)

    # Method `SolidCraftDisplay.finish()`:
    def finish(self) -> None:
        """Do nothing: the last tool and its path stay shown."""


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
      `solidcraft` (from `add_arguments()`), `shop` and `machine`.
    * `program` (`Path`): The G-code file, whose paths are drawn.

    Yields:
    * (`SolidCraftDisplay`): The display, to hand the samples to.

    Raises:
    * `SolidCraftError` or `OSError`: If SolidCraft fails or is not
      there.
    """
    with transport(options.solidcraft) as session:
        solidcraft: SolidCraftPyBind = SolidCraftPyBind(session)
        yield SolidCraftDisplay(
            solidcraft,
            loaded_tools(read(options.shop), options.machine),
            PathRack(solidcraft, session, program),
        )
