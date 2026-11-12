"""Show a running program in SolidCraft: the tool and its path.

The SolidCraft side of the simulation (`T.rlg~3.3`), split out of
`sim_linuxcnc.py`, which drives LinuxCNC and hands each position it
polls to listeners.  `SolidCraftDisplay` is such a listener: every
tool of a shop's machine is modeled (`cutter_models`), hidden, in a
SolidCraft session where `demo.py` has modeled the part,
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
python3 -m scraftcam.lcnc.serve_linuxcnc &
solidcraft --control 8080 &
python3 -m scraftcam.demo --no-path --opaque 8080 > demo.ngc
distrobox enter lcnc -- python3 -m scraftcam.lcnc.sim_linuxcnc demo.ngc \
    --solidcraft 8080
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

from ..carousel import Plan, gcode_sequence, plan, spoke_ends
from ..machine import Machine
from ..model_cache import ModelCache
from ..plot import PathMove, command_moves, read_gcode
from ..pybind.scraftpybind import (
    HeadlessTransport,
    PyBind,
    Transport,
    connect,
)
from ..shops import cnc_machine, loaded_tools, read
from ..tooling.cutter_models import (
    ModeledTool,
    add_holder,
    holder_tool_end_height,
    model_tool,
    occurrence_ids,
    unique_id_digits,
)
from .probe_batch import (
    InstallStep,
    path_steps,
    send_batch,
    sketch_steps,
)

# SolidCraft's coordinates are millimeters.
MM_PER_INCH: float = 25.4

# The material cut, by default, for the machine's drills (`--material`).
MATERIAL: str = "6061 aluminum"

# The tools' color in SolidCraft.
TOOL_COLOR: str = "#e07020"

# A position: X, Y and Z (inches, program coordinates).
Position = tuple[float, float, float]

# A `solidcraft-cli` extracted from SolidCraft's AppImage, for
# headless sessions (see `transport()`).
SOLIDCRAFT_CLI: Path = (
    Path(__file__).resolve().parents[2]
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
    * `origin` (`Position`): The work origin in machine coordinates
      (inches).
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

    # Property `Sample.origin`:
    @property
    def origin(self) -> Position:
        """The work origin in machine coordinates (inches)."""


# Class `ToolModel`:
# It keeps the last position between moves, so it is a class with
# one method.
class ToolModel:  # pylint: disable=too-few-public-methods
    """One tool in SolidCraft, made from its description in the shop.

    Its tip starts at the program's zero.  SolidCraft moves a
    component only by a step from where it is, so the position it was
    last sent to is kept, and each move sends the difference; a move
    is sent only when the tool has moved.  Its holder's color bands
    are in its component, so they move with it; it is shown and
    hidden whole (its occurrence), which leaves each band's own
    visibility to the HMI's Holders toggle.

    Attributes:
    * `base` (`float`): How far above its tip its holder's narrow
      (tool) end is (inches), where a carousel's spoke holds it.
    * `holder` (`list[str]`): Its holder's bands' body names.
    * `modeled` (`ModeledTool`): Its body, flute lines and occurrence.
    * `path` (`list[int]`): Its occurrence's id, for `paths`.
    * `position` (`Position`): Where its tip was last sent.
    * `solidcraft` (`PyBind`): The SolidCraft session.
    """

    # Method `ToolModel.__init__()`:
    def __init__(
        self,
        solidcraft: PyBind,
        number: int,
        tool: tuple[str, dict[str, object]],
        cache: ModelCache | None = None,
        digits: int = 1,
    ) -> None:
        """Model the tool and its holder, as a component, hidden.

        Arguments:
        * `solidcraft` (`PyBind`):
          The SolidCraft session.
        * `number` (`int`):
          Its T number, which names it (`T1`, ...).
        * `tool` (`tuple[str, dict[str, object]]`):
          Its list in the tools file, and its description (from
          `shops.loaded_tools()`).
        * `cache` (`ModelCache | None`):
          Where to keep its model between runs, or `None` to build it.
        * `digits` (`int`): How many holder bands (the shop's longest
          `unique_id`).
        """
        # The tool, standing on its tip at the program's zero.
        self.solidcraft: PyBind = solidcraft
        self.position: Position = (0.0, 0.0, 0.0)
        self.modeled: ModeledTool = model_tool(
            solidcraft, f"T{number}", tool, color=TOOL_COLOR, cache=cache
        )
        self.base: float = holder_tool_end_height(tool)
        self.holder: list[str] = add_holder(
            solidcraft, self.modeled, tool, digits, cache
        )
        self.path: list[int] = [
            occurrence_ids(solidcraft, self.modeled.occurrence)[1]
        ]
        self.show(False)

    # Method `ToolModel.show()`:
    def show(self, visible: bool) -> None:
        """Show or hide the whole tool: its occurrence, body and lines.

        Arguments:
        * `visible` (`bool`): True to show it.
        """
        self.solidcraft.browser.visibility(visible=visible, paths=[self.path])
        self.solidcraft.browser.visibility(
            visible=visible, items=self.modeled.items()
        )

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
            occurrence=self.modeled.occurrence,
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
    * `solidcraft` (`PyBind`): The SolidCraft session.
    * `tools` (`dict[int, ToolModel]`): The tools, by T number.
    """

    # Method `ToolRack.__init__()`:
    def __init__(
        self,
        solidcraft: PyBind,
        tools: dict[int, tuple[str, dict[str, object]]],
        cache: ModelCache | None = None,
        digits: int = 0,
    ) -> None:
        """Model every tool, hidden.

        Arguments:
        * `solidcraft` (`PyBind`):
          The SolidCraft session.
        * `tools` (`dict[int, tuple[str, dict[str, object]]]`):
          The tools, by T number (from `shops.loaded_tools()`).
        * `cache` (`ModelCache | None`):
          Where to keep their models between runs, or `None` to build
          them.
        * `digits` (`int`): How many holder bands (`Machine.id_digits`,
          from the whole shop), or 0 to count these tools' ids.
        """
        self.solidcraft: PyBind = solidcraft
        self.current: int = 0
        digits = digits or unique_id_digits(list(tools.values()))
        self.tools: dict[int, ToolModel] = {
            number: ToolModel(solidcraft, number, tool, cache, digits)
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
                self.tools[self.current].show(False)
            self.current = number
            if number in self.tools:
                self.tools[number].move_to(position)
                self.tools[number].show(True)
        if number in self.tools:
            self.tools[number].move_to(position)


# Class `PathRack`:
class PathRack:  # pylint: disable=too-few-public-methods
    """Each tool's planned path in SolidCraft; the one in use is shown.

    A path is drawn one tool ahead of the run: the first tool's before
    it starts, and the next tool's when a tool goes into the spindle,
    so no tool change waits for a drawing.  The first tool's path is
    shown from the start, so that there is something to see before a
    tool is in the spindle, and an empty spindle changes nothing.

    Attributes:
    * `current` (`int`): The T number whose path is shown (0 for none).
    * `moves` (`dict[int, list[PathMove]]`): Each tool's moves, by T
      number, in the order the tools are first used.
    * `session` (`Transport`): The transport, for the batches.
    * `sketches` (`dict[int, str]`): Each drawn path's sketch, by T
      number.
    * `solidcraft` (`PyBind`): The SolidCraft session.
    """

    # Method `PathRack.__init__()`:
    def __init__(
        self, solidcraft: PyBind, session: Transport, program: Path
    ) -> None:
        """Group the moves by tool, and draw the first tool's path.

        Arguments:
        * `solidcraft` (`PyBind`):
          The SolidCraft session.
        * `session` (`Transport`): Its transport, for the batches.
        * `program` (`Path`): The G-code file.
        """
        self.solidcraft: PyBind = solidcraft
        self.session: Transport = session
        self.current: int = 0
        self.sketches: dict[int, str] = {}

        # Group the moves by the tool in the spindle, in program order.
        moves: list[PathMove] = command_moves(
            read_gcode(program.read_text(encoding="utf-8"))
        )
        self.moves: dict[int, list[PathMove]] = {}
        move: PathMove
        for move in moves:
            self.moves.setdefault(move["tool"], []).append(move)

        # The first tool's path, shown ready for the start.
        tools: list[int] = [number for number in self.moves if number]
        if tools:
            self.show(tools[0])

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
        * `number` (`int`): The T number of the tool in the spindle (0
          for none, which leaves shown what is shown).
        """
        if number in (0, self.current):
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


# Class `CarouselView`:
# It holds the carousel's whole state (slots, turn, placing and its
# drawn sketches), which is more than seven attributes.
class CarouselView:  # pylint: disable=too-many-instance-attributes
    """A machine's tool carousel in SolidCraft: spokes and their tools.

    The spokes are one 3D sketch of lines from the hub, one per slot,
    with the slot in use at +X, where a tool goes in or out of the
    spindle; each slot's tool hangs with its holder's narrow end at
    its spoke's end.  A
    tool change turns the spokes (a sketch for each slot at +X, drawn
    when first needed, only one shown) and moves the tools with them,
    with no animation.  The hub is in machine coordinates, so the
    picture is placed again when the work origin changes.

    Attributes:
    * `front` (`int`): The slot at +X (from 1).
    * `hub` (`Position`): The hub (machine coordinates, inches).
    * `length` (`float`): The spokes' length (inches).
    * `origin` (`Position | None`): The work origin it was placed for,
      or `None` before the first sample.
    * `plan` (`Plan`): The program's slot plan.
    * `rack` (`ToolRack`): The tools, shared with the spindle.
    * `session` (`Transport`): The transport, for the batches.
    * `shown` (`str`): The spokes' sketch shown (`""` for none).
    * `sketches` (`dict[tuple[int, Position], str]`): Each drawn
      spokes' sketch, by front slot and hub (work inches).
    * `slots` (`dict[int, int]`): Each slot's tool (T number), by slot.
    * `solidcraft` (`PyBind`): The SolidCraft session.
    """

    # Method `CarouselView.__init__()`:
    def __init__(
        self,
        solidcraft: PyBind,
        session: Transport,
        machine: Machine,
        planned: Plan,
        rack: "ToolRack",
    ) -> None:
        """Keep the carousel; nothing is drawn before the first sample.

        Arguments:
        * `solidcraft` (`PyBind`): The SolidCraft session.
        * `session` (`Transport`): Its transport, for the batches.
        * `machine` (`Machine`): The machine, with its carousel.
        * `planned` (`Plan`): The program's slot plan.
        * `rack` (`ToolRack`): The tools.
        """
        self.solidcraft: PyBind = solidcraft
        self.session: Transport = session
        self.hub: Position = machine.carousel_hub
        self.length: float = machine.spoke_length
        self.plan: Plan = planned
        self.rack: ToolRack = rack
        self.slots: dict[int, int] = dict(planned.load)
        self.front: int = 1
        self.origin: Position | None = None
        self.shown: str = ""
        self.sketches: dict[tuple[int, Position], str] = {}

    # Method `CarouselView.work_hub()`:
    def work_hub(self) -> Position:
        """Return the hub in work coordinates.

        Returns:
        * (`Position`): The hub less the work origin (inches).
        """
        origin: Position = self.origin or (0.0, 0.0, 0.0)
        x, y, z = (
            round(hub - at, 6)
            for hub, at in zip(self.hub, origin, strict=True)
        )
        return (x, y, z)

    # Method `CarouselView.draw()`:
    def draw(self) -> None:
        """Show the spokes for the slot at +X, and the tools in place.

        The tool in the spindle is left to the rack.
        """
        # The spokes, drawn once for each slot at +X and hub.
        hub: Position = self.work_hub()
        ends: dict[int, Position] = spoke_ends(
            hub, self.length, len(self.slots) or 1, self.front
        )
        key: tuple[int, Position] = (self.front, hub)
        if key not in self.sketches:
            name: str = f"Carousel {len(self.sketches) + 1}"
            lines: list[InstallStep] = [
                {
                    "command": "sketch.line3d",
                    "params": {
                        "points": [
                            [value * MM_PER_INCH for value in hub],
                            [value * MM_PER_INCH for value in end],
                        ]
                    },
                }
                for end in ends.values()
            ]
            send_batch(self.session, sketch_steps(name, lines, True))
            self.sketches[key] = name
        if self.sketches[key] != self.shown:
            if self.shown:
                self.solidcraft.browser.visibility(
                    visible=False, items=[self.shown]
                )
            self.shown = self.sketches[key]
            self.solidcraft.browser.visibility(
                visible=True, items=[self.shown]
            )

        # Each slot's tool, but the one in use, hung by its holder's
        # narrow end at its spoke's end.
        slot: int
        number: int
        for slot, number in self.slots.items():
            if number == self.rack.current or number not in self.rack.tools:
                continue
            model: ToolModel = self.rack.tools[number]
            x, y, z = ends[slot]
            model.move_to((x, y, z - model.base))
            model.show(True)

    # Method `CarouselView.sample()`:
    def sample(self, sample: Sample, changed: bool) -> None:
        """Follow the work origin and tool changes.

        Arguments:
        * `sample` (`Sample`): Where the tool is.
        * `changed` (`bool`): True when the tool in the spindle has
          just changed (the rack has already shown the new one).
        """
        if not changed and sample.origin == self.origin:
            return
        self.origin = sample.origin
        number: int = sample.tool
        if changed and number:
            # A tool not in a slot comes in by the swap planned for it.
            if number not in self.slots.values():
                for swap in self.plan.swaps:
                    if (
                        swap.into == number
                        and self.slots.get(swap.slot) == swap.out
                    ):
                        self.slots[swap.slot] = number
                        if swap.out in self.rack.tools:
                            self.rack.tools[swap.out].show(False)
                        break
            # The slot in use turns to +X.
            for slot, held in self.slots.items():
                if held == number:
                    self.front = slot
        self.draw()


# Class `SolidCraftDisplay`:
class SolidCraftDisplay:
    """A `sim_linuxcnc.SampleListener` that shows the run in SolidCraft.

    Attributes:
    * `carousel` (`CarouselView | None`): The machine's tool carousel,
      or `None` for a machine whose tools are changed by hand.
    * `paths` (`PathRack`): Each tool's path; the one in the spindle
      is shown.
    * `rack` (`ToolRack`): The tools, whose one in the spindle
      follows the position.
    """

    # Method `SolidCraftDisplay.__init__()`:
    def __init__(
        self,
        solidcraft: PyBind,
        tools: dict[int, tuple[str, dict[str, object]]],
        paths: PathRack,
        carousel: tuple[Transport, Machine, Plan] | None = None,
        digits: int = 0,
    ) -> None:
        """Model the tools.

        Arguments:
        * `solidcraft` (`PyBind`):
          The SolidCraft session.
        * `tools` (`dict[int, tuple[str, dict[str, object]]]`):
          The tools, by T number (from `shops.loaded_tools()`).
        * `paths` (`PathRack`): Each tool's path, drawn.
        * `carousel` (`tuple[Transport, Machine, Plan] | None`):
          The session's transport, the machine and the program's slot
          plan, for a machine with a carousel; else `None`.
        * `digits` (`int`): How many holder bands (the whole shop's
          longest `unique_id`), or 0 to count the tools' ids.
        """
        self.rack: ToolRack = ToolRack(solidcraft, tools, ModelCache(), digits)
        self.paths: PathRack = paths
        self.carousel: CarouselView | None = (
            None
            if carousel is None
            else CarouselView(solidcraft, *carousel, self.rack)
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
        self.paths.show(sample.tool)
        changed: bool = sample.tool != self.rack.current
        self.rack.move_to(sample.tool, sample.position)
        if self.carousel is not None:
            self.carousel.sample(sample, changed)

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
    parser.add_argument(
        "--material",
        default=MATERIAL,
        help="the material cut, for the drills' speeds (default: %(default)s)",
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
    # A machine with a carousel gets it, planned for the program.
    shop: dict[str, object] = read(options.shop)
    machine: Machine = cnc_machine(
        shop, options.machine, getattr(options, "material", MATERIAL)
    )
    sequence: list[int] = gcode_sequence(
        program.read_text(encoding="utf-8").splitlines()
    )
    with transport(options.solidcraft) as session:
        solidcraft: PyBind = PyBind(session)
        yield SolidCraftDisplay(
            solidcraft,
            loaded_tools(shop, options.machine),
            PathRack(solidcraft, session, program),
            (
                (session, machine, plan(sequence, machine.carousel_slots))
                if machine.carousel_slots > 0 and sequence
                else None
            ),
            machine.id_digits,
        )
