"""Which tool goes in which slot of a tool carousel, and when to swap.

A machine with a carousel (`Machine.carousel_slots`) holds that many
tools.  Before a program starts, the slots are filled in the order
the program first uses its tools; when a tool is needed and every
slot is full, the tool whose next use is furthest away (or never) is
swapped out for it (Belady's rule, which swaps the fewest times).  A
tool is put in or taken out at the +X spoke.

`plan()` works from a program's tool sequence, the T numbers of its
changes in order, which `gcode_sequence()` finds in G-code text (a
prescan of a `.nc` file) and `CNC` keeps as it writes.  Messages name
a tool by its `unique_id` and its holder's color bands, the resistor
code of the id's digits (`cutter_models.py`), e.g. "Swap tool 23
(red/orange) with tool 43 (yellow/orange)"; in a G-code comment,
which can not hold parentheses, the colors go in brackets.
"""

import math
import re
from dataclasses import dataclass, field

from .machine import Machine, ToolEntry

# The resistor code's color of each digit, as `cutter_models.py` colors
# a holder's bands (`RESISTOR_COLORS`).
COLOR_NAMES: tuple[str, ...] = (
    "black",
    "brown",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "violet",
    "gray",
    "white",
)

# A tool change line: its `T` word and `M6`, outside a comment.
_CHANGE: re.Pattern[str] = re.compile(
    r"\bT0*(\d+)\b.*\bM0*6\b|\bM0*6\b.*\bT0*(\d+)\b"
)

# A comment, left out before a line is read.
_COMMENT: re.Pattern[str] = re.compile(r"\([^)]*\)")


# Class `Swap`:
@dataclass(frozen=True, slots=True)
class Swap:
    """One tool taken out of a slot, and another put in.

    Attributes:
    * `change` (`int`): Which change needs it (from 0, in the
      program's order).
    * `slot` (`int`): The slot (from 1).
    * `out` (`int`): The T number taken out.
    * `into` (`int`): The T number put in.

    Constructor:
    * `Swap(change, slot, out, into)`
    """

    # Constructor arguments:
    change: int = field(init=True)
    slot: int = field(init=True)
    out: int = field(init=True)
    into: int = field(init=True)


# Class `Plan`:
@dataclass(frozen=True, slots=True)
class Plan:
    """The slots to load before a program, and the swaps during it.

    Attributes:
    * `load` (`dict[int, int]`): Each slot's tool (T number), by slot
      (from 1), before the start.
    * `swaps` (`tuple[Swap, ...]`): The swaps, in order.

    Constructor:
    * `Plan(load, swaps)`
    """

    # Constructor arguments:
    load: dict[int, int] = field(init=True)
    swaps: tuple[Swap, ...] = field(init=True)


# Function `plan()`:
def plan(sequence: list[int], slots: int) -> Plan:
    """Plan a carousel's slots for a program's tool changes.

    Arguments:
    * `sequence` (`list[int]`): The T number of each change, in order.
    * `slots` (`int`): How many slots the carousel has (at least 1).

    Returns:
    * (`Plan`): The load, then the swaps.

    Raises:
    * `ValueError`: If there are no slots.
    """
    if slots < 1:
        raise ValueError(f"a carousel needs slots, not {slots}")

    # Fill the slots in first-use order.
    load: dict[int, int] = {}
    tool: int
    for tool in sequence:
        if tool not in load.values() and len(load) < slots:
            load[len(load) + 1] = tool

    # Then swap out the tool next used furthest away (or never).
    held: dict[int, int] = dict(load)
    swaps: list[Swap] = []
    index: int
    for index, tool in enumerate(sequence):
        if tool in held.values():
            continue
        later: list[int] = sequence[index + 1 :]

        def next_use(slot: int, later: list[int] = later) -> tuple[int, int]:
            used: int = held[slot]
            return (
                later.index(used) if used in later else len(later) + 1,
                -slot,
            )

        slot: int = max(held, key=next_use)
        swaps.append(Swap(index, slot, held[slot], tool))
        held[slot] = tool
    return Plan(load, tuple(swaps))


# Function `gcode_sequence()`:
def gcode_sequence(lines: list[str]) -> list[int]:
    """Return the T number of each tool change in a program's text.

    Arguments:
    * `lines` (`list[str]`): The program's lines.

    Returns:
    * (`list[int]`): The T numbers, in order.
    """
    found: list[int] = []
    line: str
    for line in lines:
        match: re.Match[str] | None = _CHANGE.search(_COMMENT.sub("", line))
        if match is not None:
            found.append(int(match.group(1) or match.group(2)))
    return found


# Function `colors()`:
def colors(unique_id: int, digits: int) -> str:
    """Return a tool's holder colors, as the bands read from its base.

    Arguments:
    * `unique_id` (`int`): The tool's `unique_id`.
    * `digits` (`int`): How many bands (the shop's longest id).

    Returns:
    * (`str`): E.g. `red/orange` for 23.
    """
    return "/".join(
        COLOR_NAMES[int(digit)] for digit in f"{unique_id:0{digits}d}"
    )


# Function `tool_text()`:
def tool_text(unique_id: int, digits: int) -> str:
    """Return how a message names a tool.

    Arguments:
    * `unique_id` (`int`): The tool's `unique_id`.
    * `digits` (`int`): How many color bands.

    Returns:
    * (`str`): E.g. `tool 23 (red/orange)`.
    """
    return f"tool {unique_id} ({colors(unique_id, digits)})"


# Function `swap_message()`:
def swap_message(out: int, into: int, digits: int) -> str:
    """Return the message for a swap, by the tools' unique ids.

    Arguments:
    * `out` (`int`): The `unique_id` of the tool taken out.
    * `into` (`int`): The `unique_id` of the tool put in.
    * `digits` (`int`): How many color bands.

    Returns:
    * (`str`): E.g. `Swap tool 23 (red/orange) with tool 43
      (yellow/orange)`.
    """
    return f"Swap {tool_text(out, digits)} with {tool_text(into, digits)}"


# Function `plan_text()`:
def plan_text(machine: Machine, sequence: list[int]) -> list[str]:
    """Return a machine's carousel plan for a program, to be read.

    Arguments:
    * `machine` (`Machine`): The machine, with its carousel and tools.
    * `sequence` (`list[int]`): The program's tool changes (T numbers).

    Returns:
    * (`list[str]`): The slots to load before Start, then the swaps;
      nothing for a machine without a carousel or a program without
      tool changes.
    """
    if machine.carousel_slots < 1 or not sequence:
        return []
    digits: int = machine.id_digits
    planned: Plan = plan(sequence, machine.carousel_slots)
    lines: list[str] = ["Load the carousel before Start (+X spoke):"]
    slot: int
    number: int
    for slot, number in sorted(planned.load.items()):
        tool: ToolEntry = machine.tool(number)
        lines.append(
            f"  slot {slot}: {tool_text(tool.unique_id, digits)} "
            f"T{number:02d} {tool.name}"
        )
    lines.append(
        f"Swaps during the run: {len(planned.swaps)}"
        if planned.swaps
        else "No swaps during the run."
    )
    swap: Swap
    for swap in planned.swaps:
        text: str = swap_message(
            machine.tool(swap.out).unique_id,
            machine.tool(swap.into).unique_id,
            digits,
        )
        lines.append(f"  change {swap.change + 1}, slot {swap.slot}: {text}")
    return lines


# Function `spoke_ends()`:
def spoke_ends(
    hub: tuple[float, float, float], length: float, slots: int, front: int
) -> dict[int, tuple[float, float, float]]:
    """Return where each slot's spoke ends, with one slot at +X.

    The slots go around counterclockwise (seen from above) in order,
    evenly spaced, with `front` on the +X spoke, where a tool is put
    in or taken out.

    Arguments:
    * `hub` (`tuple[float, float, float]`): The hub's center.
    * `length` (`float`): From the hub to each slot.
    * `slots` (`int`): How many slots (at least 1).
    * `front` (`int`): The slot at +X (from 1).

    Returns:
    * (`dict[int, tuple[float, float, float]]`): Each slot's end, by
      slot (from 1), at the hub's height.
    """
    x, y, z = hub
    ends: dict[int, tuple[float, float, float]] = {}
    slot: int
    for slot in range(1, slots + 1):
        angle: float = 2.0 * math.pi * (slot - front) / slots
        ends[slot] = (
            x + length * math.cos(angle),
            y + length * math.sin(angle),
            z,
        )
    return ends
