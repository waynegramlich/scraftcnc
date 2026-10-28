"""Generate 3-axis mill RS-274 (G-code) for shapes made in SolidCraft.

`SCCNC` collects RS-274 commands, each a plain dictionary of words
(e.g. `{"G": 1, "X": 1.0, "F": 12.0}`), and writes them as G-code.  It
works in inches, with a machine and its tool table (`scmachine`), and
cuts the shapes of `scgeometry` (such as `SCRoundPoly`): along their
outlines (`SCCNC.profile()`) and out of their insides
(`SCCNC.pocket()`).  It drills (`SCCNC.drill()`) where they go down
(`SCCNC.pocket_entries()`, `SCCNC.profile_entry()`), so that an end
mill can go straight down a hole instead of into solid material.

A pocket is cleared by rings: the path along its wall, then smaller
and smaller rings inside that, each `stepover` of the tool's diameter
in from the last.  As they shrink the rings may come apart, so they
make a tree (`SCRing`), which is cut from the smallest rings out.
"""

# Most of this module's lines are docstrings and comments, so it is
# longer than `pylint` likes.
# pylint: disable=too-many-lines

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from scgeometry import (
    EPSILON,
    JOIN,
    TOUCH,
    Point,
    SCArc,
    SCLine,
    SCLoop,
    SCRoundPoly,
    SCSegment,
    beyond,
    distance_to,
    halves,
    inset,
    left,
    meet,
    point_at,
    start_tangent,
    turn_between,
    unit,
)
from scmachine import SCMachine, SCTool

# One RS-274 command: its words, in order, keyed by letter (e.g.
# `{"G": 1, "X": 10.0}`).  The key `comment` holds a comment line's
# text, and `note` a comment at the end of a line of words (e.g. the
# tool's name on its tool change).
RS274: TypeAlias = dict[str, float | int | str]

# How a pocket's ring is cut at each depth: ramped down into along
# itself (nothing inside it is cut first), plunged into down a drilled
# hole (likewise), led into from inside (where its rings are cut
# first), or cut straight into (a ring too small to ramp into, cut
# after the ring around it).
CutMode: TypeAlias = Literal["ramp", "drilled", "lead", "plain"]

# How much of a cut a pass makes: all of it, with one tool ("full"); or
# with a roughing end mill that leaves the machine's `finish_allowance`
# on the walls and floors ("rough"), and then an end mill that cuts
# them to size at full depth in one pass ("finish").
Stage: TypeAlias = Literal["full", "rough", "finish"]

# How many times a profile's leads may be halved to fit (see
# `_fitted_path()`).
LEAD_HALVINGS: int = 3

# The first words of a cut's comment, by stage ("P" or "p" follows).
STAGE_WORDS: dict[Stage, str] = {
    "full": "P",
    "rough": "Rough p",
    "finish": "Finish p",
}

# A chamfer bit's tip runs this far off the wall (beyond its own
# radius), so that it does not rub the wall below the bevel.
CHAMFER_CLEAR: float = 0.005

# Finding what a pocket's rings leave uncut, a point counts as reached
# when it is within a tool radius plus this of a ring's path.  At a
# stepover of 1, the next ring's reach ends exactly on the edge of what
# this ring leaves, and outlines lying exactly on each other cannot be
# sorted reliably; the margin moves one just past the other.
REACH_MARGIN: float = 1e-4

# A smallest ring shorter than this many tool diameters is too small to
# ramp into well (going around it would be little better than plunging
# straight down), so it is cut after the ring around it, which is
# ramped into instead.
SMALL_RING: float = 2.0

# The feed along an arc is scaled so that the cutting edge, not the
# tool's center, moves at the tool's feed, but never by less than
# `ARC_FEED_MIN` or more than `ARC_FEED_MAX` (a sharp corner would
# otherwise call for a feed near zero, or without limit).
ARC_FEED_MIN: float = 0.25
ARC_FEED_MAX: float = 2.0


# Function `_leads()`:
def _leads(
    path: SCLoop, radius: float
) -> tuple[SCArc, list[SCSegment], SCArc]:
    """Plan the lead-in, the loop and the lead-out around a path.

    The loop starts and ends in the middle of the path's longest
    segment, where the path is smooth.  The lead-in and lead-out are
    the two halves of a circle of `radius` touching the path there,
    on its left, both counter-clockwise.

    Arguments:
    * `path` (`SCLoop`): The path the tool's center follows.
    * `radius` (`float`): The radius of the lead-in and lead-out.

    Returns:
    * (`SCArc`): The lead-in, ending where the loop starts.
    * (`list[SCSegment]`): The loop, once around the path.
    * (`SCArc`): The lead-out, ending where the lead-in starts.

    Raises:
    * `ValueError`: If the lead-in or lead-out would cross the path.
    """
    # Start the loop in the middle of the longest segment.
    segments: tuple[SCSegment, ...] = path.segments
    longest: int = max(
        range(len(segments)), key=lambda index: segments[index].length()
    )
    first: SCSegment
    second: SCSegment
    first, second = halves(segments[longest])
    loop: list[SCSegment] = [
        second,
        *segments[longest + 1 :],
        *segments[:longest],
        first,
    ]

    # The circle touches the path at the loop's start, on its left.
    start: Point = second.start
    along: Point = start_tangent(second)
    center: Point = (
        start[0] - along[1] * radius,
        start[1] + along[0] * radius,
    )
    entry: Point = (
        start[0] - along[1] * 2.0 * radius,
        start[1] + along[0] * 2.0 * radius,
    )
    lead_in: SCArc = SCArc(entry, start, center, radius, math.pi)
    lead_out: SCArc = SCArc(start, entry, center, radius, math.pi)

    _check_leads(path, (lead_in, lead_out), start)
    return lead_in, loop, lead_out


# Function `_check_leads()`:
def _check_leads(
    path: SCLoop, leads: tuple[SCArc, SCArc], start: Point
) -> None:
    """Check that the leads meet the path only at `start`.

    Arguments:
    * `path` (`SCLoop`): The path the tool's center follows.
    * `leads` (`tuple[SCArc, SCArc]`): The lead-in and lead-out.
    * `start` (`Point`): Where they touch the path.

    Raises:
    * `ValueError`: If either meets the path anywhere else.
    """
    lead: SCArc
    segment: SCSegment
    point: Point
    for lead in leads:
        for segment in path.segments:
            for point in meet(lead, segment):
                if math.dist(point, start) > TOUCH:
                    raise ValueError(
                        f"{path.name}: the lead-in or lead-out crosses "
                        f"the path at ({point[0]:g}, {point[1]:g})"
                    )


# Function `_profile_path()`:
def _profile_path(
    poly: SCRoundPoly, inside: bool, offset: float, lead: float
) -> tuple[SCRoundPoly, tuple[SCArc, list[SCSegment], SCArc]]:
    """Return the path a tool follows to cut along an outline.

    Arguments:
    * `poly` (`SCRoundPoly`): The outline.
    * `inside` (`bool`): True to cut from inside the outline.
    * `offset` (`float`):
      How far off the outline the tool's center goes (its radius, for
      an end mill).
    * `lead` (`float`): The radius of the lead-in and lead-out.

    Returns:
    * (`SCRoundPoly`): The path of the tool's center: off the outline
      by `offset`, going the climb milling way around.
    * (`tuple[SCArc, list[SCSegment], SCArc]`): Its lead-in, loop and
      lead-out (see `_leads()`).
    """
    path: SCRoundPoly = poly.offset(-offset if inside else offset)
    if path.is_ccw() != inside:
        path = path.reversed()
    return path, _leads(SCLoop.from_poly(path), lead)


# Function `_fitted_path()`:
def _fitted_path(
    poly: SCRoundPoly, inside: bool, offset: float, lead: float
) -> tuple[SCRoundPoly, tuple[SCArc, list[SCSegment], SCArc]]:
    """Return a profile's path, with leads small enough to fit.

    The leads are halved (up to `LEAD_HALVINGS` times) until they do
    not cross the path, as in a narrow hole.

    Arguments:
    * `poly` (`SCRoundPoly`): The outline.
    * `inside` (`bool`): True to cut from inside the outline.
    * `offset` (`float`): How far off the outline the tool's center is.
    * `lead` (`float`): The largest radius for the leads.

    Returns:
    * (`SCRoundPoly`): The path (see `_profile_path()`).
    * (`tuple[SCArc, list[SCSegment], SCArc]`): Its leads and loop.

    Raises:
    * `ValueError`: If even the smallest leads cross the path.
    """
    halving: int
    for halving in range(LEAD_HALVINGS):
        try:
            return _profile_path(poly, inside, offset, lead / 2.0**halving)
        except ValueError:
            continue
    return _profile_path(poly, inside, offset, lead / 2.0**LEAD_HALVINGS)


# Function `_number()`:
def _number(value: float) -> str:
    """Format a coordinate or feed for G-code.

    Arguments:
    * `value` (`float`): The value.

    Returns:
    * (`str`): The value to 4 decimal places, without trailing zeros
      (e.g. `12.5`, `-3`, `0`).
    """
    text: str = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# Class `SCRing`:
@dataclass(slots=True)
class SCRing:
    """One ring of a pocket's tool path, and the rings inside it.

    A ring is a region's edge: its outer loop, and a loop around each
    island in it.  Each loop has the region on its left, so the tool
    goes counter-clockwise around the outer loop and clockwise around
    the islands, climb milling with the material it cuts on its right.

    Attributes:
    * `loops` (`list[SCLoop]`):
      The paths the tool's center follows: the outer loop first, then
      the loops around islands.
    * `children` (`list[SCRing]`): The rings just inside this one.
    * `spurs` (`list[SCLine]`):
      Short cuts straight out from sharp corners of `loops` (and back),
      into the corners between them and the rings around them, which
      would otherwise be left uncut.

    Constructor:
    * `SCRing(loops)`
    """

    # Constructor arguments:
    loops: list[SCLoop] = field(init=True)

    # Attributes filled in by `plan_pocket()` (alphabetized):
    children: list["SCRing"] = field(init=False, default_factory=list)
    spurs: list[SCLine] = field(init=False, default_factory=list)

    # Method `SCRing.length()`:
    def length(self) -> float:
        """Return the distance around all of the ring's loops.

        Returns:
        * (`float`): The total length.
        """
        return sum(loop.length() for loop in self.loops)

    # Method `SCRing.post_order()`:
    def post_order(self) -> Iterator["SCRing"]:
        """Yield the rings inside this one (smallest first), then it.

        Yields:
        * (`SCRing`): Each ring, after all of the rings inside it.
        """
        child: SCRing
        for child in self.children:
            yield from child.post_order()
        yield self


# Function `cut_order()`:
def cut_order(
    ring: SCRing, diameter: float
) -> Iterator[tuple[SCRing, CutMode]]:
    """Yield a pocket's rings in the order to cut them at one depth.

    Each ring comes after the rings inside it (smallest first), except
    that a small smallest ring (shorter than `SMALL_RING` tool
    diameters) comes right after the ring around it.

    Arguments:
    * `ring` (`SCRing`): The outermost ring.
    * `diameter` (`float`): The tool's diameter.

    Yields:
    * (`tuple[SCRing, CutMode]`): Each ring, and how to cut it.
    """
    small: list[SCRing] = [
        child
        for child in ring.children
        if not child.children and child.length() < SMALL_RING * diameter
    ]
    child: SCRing
    for child in ring.children:
        if child not in small:
            yield from cut_order(child, diameter)
    yield ring, "ramp" if len(small) == len(ring.children) else "lead"
    for child in small:
        yield child, "plain"


# Function `plan_pocket()`:
def plan_pocket(
    region: Sequence[SCLoop], diameter: float, stepover: float
) -> list[SCRing]:
    """Plan the rings that clear a pocket.

    The outermost rings follow the pocket's wall (and its islands'), a
    tool radius in from them.  Inside each ring are the rings `stepover`
    of the tool's diameter in from it, until they vanish; where the
    last rings would leave the middle uncut, one more set follows the
    outline of what is left.

    Arguments:
    * `region` (`Sequence[SCLoop]`):
      The pocket's wall (counter-clockwise), then its islands
      (clockwise), so the pocket is on the left of each.
    * `diameter` (`float`): The tool's diameter.
    * `stepover` (`float`):
      How far apart the rings are, as a fraction of `diameter`.

    Returns:
    * (`list[SCRing]`): The outermost rings (more than one when the
      pocket narrows to less than the tool's diameter somewhere).

    Raises:
    * `ValueError`: If the tool does not fit in the pocket.
    """
    name: str = region[0].name
    roots: list[SCRing] = [
        SCRing(loops)
        for loops in _regions(inset(region, diameter / 2.0, name))
    ]
    if not roots:
        raise ValueError(f"{name}: the tool does not fit in it")
    root: SCRing
    for root in roots:
        _grow(root, diameter, stepover * diameter, 1)
    return roots


# Function `_regions()`:
def _regions(loops: Sequence[SCLoop]) -> list[list[SCLoop]]:
    """Sort loops into regions: each outer loop, and the islands in it.

    Arguments:
    * `loops` (`Sequence[SCLoop]`):
      Loops with their regions on their left: counter-clockwise outer
      loops, and clockwise loops around islands.

    Returns:
    * (`list[list[SCLoop]]`): Each region's loops, outer loop first.
      An island's loop goes with the smallest outer loop around it.
    """
    outers: list[SCLoop] = [loop for loop in loops if loop.is_ccw()]
    regions: list[list[SCLoop]] = [[outer] for outer in outers]
    island: SCLoop
    for island in loops:
        if island.is_ccw():
            continue
        around: list[int] = [
            index
            for index, outer in enumerate(outers)
            if outer.contains(island.segments[0].start)
        ]
        if around:
            smallest: int = min(
                around, key=lambda index: outers[index].signed_area()
            )
            regions[smallest].append(island)
    return regions


# Function `_grow()`:
def _grow(ring: SCRing, diameter: float, step: float, level: int) -> None:
    """Fill in the rings inside a ring, and theirs, and so on.

    Arguments:
    * `ring` (`SCRing`): The ring.
    * `diameter` (`float`): The tool's diameter.
    * `step` (`float`): How far in each ring is from the one around it.
    * `level` (`int`): How many rings `ring` is inside of.
    """
    # The rings a step in, and theirs; and spurs into the corners they
    # leave uncut.
    radius: float = diameter / 2.0
    base: str = ring.loops[0].name.split(" ring ")[0]
    inner: list[SCLoop] = inset(ring.loops, step, f"{base} ring {level}")
    ring.children = [SCRing(loops) for loops in _regions(inner)]
    child: SCRing
    for child in ring.children:
        _grow(child, diameter, step, level + 1)
    _add_spurs(ring, ring.children, diameter)

    # Where neither this ring's cut nor theirs (nor their spurs)
    # reaches (the part more than a tool radius in from this ring, and
    # more than a tool radius from theirs), a last ring follows the
    # outline of what is left.  It is less than `step` minus a tool
    # radius from that outline, so following it clears it.
    if step > radius:
        uncut: list[SCLoop] = beyond(
            inset(ring.loops, radius, f"{base} ring last"),
            inner,
            radius + REACH_MARGIN,
            f"{base} ring last",
        )
        spurs: list[SCLine] = [
            spur for child in ring.children for spur in child.spurs
        ]
        last: list[SCRing] = [
            SCRing(loops)
            for loops in _regions(uncut)
            if not _reached(loops, spurs, radius)
        ]
        ring.children += last
        _add_spurs(ring, last, diameter)


# Function `_add_spurs()`:
def _add_spurs(
    ring: SCRing, children: Sequence[SCRing], diameter: float
) -> None:
    """Add spurs to the corners of rings, into what they leave uncut.

    Arguments:
    * `ring` (`SCRing`): The ring around them.
    * `children` (`Sequence[SCRing]`): The rings to add spurs to.
    * `diameter` (`float`): The tool's diameter.
    """
    nearby: list[SCLoop] = [
        *ring.loops,
        *(loop for child in ring.children for loop in child.loops),
    ]
    child: SCRing
    for child in children:
        child.spurs = [
            spur
            for loop in child.loops
            for spur in _spurs(
                loop,
                [other for other in nearby if other is not loop],
                diameter,
            )
        ]


# Function `_reached()`:
def _reached(
    loops: Sequence[SCLoop], spurs: Sequence[SCLine], radius: float
) -> bool:
    """Return whether spurs' cuts reach all around some loops.

    Arguments:
    * `loops` (`Sequence[SCLoop]`): The loops (of a small region).
    * `spurs` (`Sequence[SCLine]`): The spurs.
    * `radius` (`float`): The tool's radius.

    Returns:
    * (`bool`): True when every point tried along the loops is within
      a tool radius of a spur.
    """
    return bool(spurs) and all(
        min(distance_to(point_at(segment, fraction), spur) for spur in spurs)
        <= radius
        for loop in loops
        for segment in loop.segments
        for fraction in (0.0, 0.25, 0.5, 0.75)
    )


# Function `_spurs()`:
def _spurs(
    loop: SCLoop, others: Sequence[SCLoop], diameter: float
) -> list[SCLine]:
    """Return the spurs that reach into corners left uncut.

    Outside a ring's sharp corner, the ring around it can be more than
    a tool's diameter away, leaving a cusp uncut.  Each corner is
    checked by walking straight out from it (along the line halving
    its angle) until the cut of another ring is reached; a spur goes
    out as far as needed for the tool to reach any point found on the
    way that no ring's cut reaches.

    Arguments:
    * `loop` (`SCLoop`): The ring's path.
    * `others` (`Sequence[SCLoop]`): The paths of the rings near it.
    * `diameter` (`float`): The tool's diameter.

    Returns:
    * (`list[SCLine]`): The spurs, each from a corner of `loop` out.
    """
    spurs: list[SCLine] = []
    corner: Point
    arriving: Point
    leaving: Point
    for corner, arriving, leaving in loop.corners():
        # Only a corner turning left points out of the ring.
        if turn_between(arriving, leaving) <= 0.0:
            continue
        inward: Point = (
            left(arriving)[0] + left(leaving)[0],
            left(arriving)[1] + left(leaving)[1],
        )
        out: Point = unit(-inward[0], -inward[1])
        reach: float = _uncut_reach(corner, out, loop, others, diameter)
        if reach > 0.0:
            spurs.append(
                SCLine(
                    corner,
                    (corner[0] + out[0] * reach, corner[1] + out[1] * reach),
                )
            )
    return spurs


# Function `_uncut_reach()`:
def _uncut_reach(
    corner: Point,
    out: Point,
    loop: SCLoop,
    others: Sequence[SCLoop],
    diameter: float,
) -> float:
    """Return how far a spur must go out from a corner.

    Arguments:
    * `corner` (`Point`): The corner of `loop`.
    * `out` (`Point`): The unit direction out of the corner.
    * `loop` (`SCLoop`): The ring's path.
    * `others` (`Sequence[SCLoop]`): The paths of the rings near it.
    * `diameter` (`float`): The tool's diameter.

    Returns:
    * (`float`): The spur's length, or 0 when no spur is needed (or
      no other ring's cut is found within 4 diameters).
    """
    # Walk out until another ring's cut is reached, remembering the
    # last point that no cut reaches.
    radius: float = diameter / 2.0
    stride: float = diameter / 100.0
    farthest: float = 0.0
    along: float = radius + stride
    while along < 4.0 * diameter:
        point: Point = (corner[0] + out[0] * along, corner[1] + out[1] * along)
        if any(other.distance(point) <= radius for other in others):
            return farthest - radius + stride if farthest > 0.0 else 0.0
        if loop.distance(point) > radius:
            farthest = along
        along += stride
    return 0.0


# Class `SCCNC`:
@dataclass(slots=True)
class SCCNC:
    """RS-274 (G-code) for a 3-axis mill, built one command at a time.

    The program works in inches and absolute coordinates, in the XY
    plane, with feeds per minute; arc centers (`I`, `J`) are relative
    to each arc's start.  It cuts with the tool chosen by
    `change_tool()`, from the machine's tool table, climb milling: the
    material being cut is always to the right of the cutter.

    The tool moves across the work only at `z_safe` (above all of the
    hold down tooling), and comes down at the rapid speed to
    `clearance` above `z_top` (the top of the material, which may not
    be flat).  Below that, where it may be removing material, it moves
    at the tool's feed (or its plunge feed, going straight down).

    Attributes:
    * `name` (`str`): The program's name (its first comment).
    * `machine` (`SCMachine`): The machine and its tool table.
    * `z_top` (`float`): The Z of the material's top surface.
    * `commands` (`list[RS274]`): The program so far.
    * `minutes` (`float`):
      The time the moves so far take, at the machine's rapid speed and
      the tools' feeds (not counting acceleration or tool changes).
    * `position` (`tuple[float | None, float | None, float | None]`):
      Where the tool was last sent (X, Y, Z); `None` until that axis
      first moves.
    * `tool` (`SCTool | None`): The tool in the spindle, if any.

    Constructor:
    * `SCCNC(name, machine, z_top)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    machine: SCMachine = field(init=True)
    z_top: float = field(init=True, default=0.0)

    # Program state (alphabetized):
    commands: list[RS274] = field(init=False, default_factory=list)
    minutes: float = field(init=False, default=0.0)
    position: tuple[float | None, float | None, float | None] = field(
        init=False, default=(None, None, None)
    )
    tool: SCTool | None = field(init=False, default=None)

    # Method `SCCNC.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the heights, and start the program.

        The program starts with its name, the machine's modes and a rise
        to `z_safe`.

        Raises:
        * `ValueError`: If `z_safe` is not above `clearance` above `z_top`.
        """
        # Validate the heights.
        if self.z_safe <= self.z_top + self.clearance:
            raise ValueError(
                f"{self.z_safe=} must be above {self.z_top=} "
                f"+ {self.clearance=}"
            )

        # Start the program.
        self.comment(self.name)
        self.add({"G": 20})  # Inches.
        self.add({"G": 90})  # Absolute coordinates.
        self.add({"G": 17})  # The XY plane.
        self.add({"G": 94})  # Feeds per minute.
        self.rapid(z=self.z_safe)

    # Method `SCCNC.z_safe()`:
    @property
    def z_safe(self) -> float:
        """Return the Z above all of the hold down tooling.

        Returns:
        * (`float`): The machine's `z_safe`.
        """
        return self.machine.z_safe

    # Method `SCCNC.clearance()`:
    @property
    def clearance(self) -> float:
        """Return how far above `z_top` rapids down stop.

        Returns:
        * (`float`): The machine's `clearance`.
        """
        return self.machine.clearance

    # Method `SCCNC.cutter()`:
    @property
    def cutter(self) -> SCTool:
        """Return the tool in the spindle.

        Returns:
        * (`SCTool`): The tool.

        Raises:
        * `ValueError`: If no tool has been chosen yet.
        """
        if self.tool is None:
            raise ValueError(f"{self.name}: no tool yet (see change_tool())")
        return self.tool

    # Method `SCCNC.change_tool()`:
    def change_tool(self, number: int) -> SCTool:
        """Change to another tool from the tool table.

        The tool rises to the machine's `tool_change_z` first (some
        machines do not), the spindle stops, the machine's tool change
        words are written, and the spindle starts at the new tool's
        speed.

        Arguments:
        * `number` (`int`): The tool's number.

        Returns:
        * (`SCTool`): The tool.

        Raises:
        * `KeyError`: If the tool table has no such tool.
        """
        tool: SCTool = self.machine.tool(number)
        self.comment(f"Tool {number}: {tool.name}")
        self.rapid(z=self.machine.tool_change_z)
        if self.tool is not None:
            self.add({"M": 5})
        change: RS274 = {
            word[0].upper(): word[1:]
            for word in self.machine.change_words(number)
        }
        change["note"] = tool.name
        self.add(change)
        self.tool = tool
        self.add({"M": 3, "S": tool.rpm})
        return tool

    # Method `SCCNC.add()`:
    def add(self, command: RS274) -> None:
        """Append one command to the program.

        Arguments:
        * `command` (`RS274`): The command's words.
        """
        self.commands.append(command)

    # Method `SCCNC.comment()`:
    def comment(self, text: str) -> None:
        """Append a comment.

        Arguments:
        * `text` (`str`): The comment (without parentheses).

        Raises:
        * `ValueError`: If `text` contains a parenthesis.
        """
        if "(" in text or ")" in text:
            raise ValueError(f"{text=} must not contain parentheses")
        self.add({"comment": text})

    # Method `SCCNC._move()`:
    def _move(
        self,
        code: int,
        axes: tuple[float | None, float | None, float | None],
        arc: SCArc | None = None,
        feed: float | None = None,
    ) -> None:
        """Append a move, leaving out unchanged axes and feeds.

        A rapid or line that would not move is left out entirely.

        Arguments:
        * `code` (`int`): The move's `G` code.
        * `axes` (`tuple[float | None, float | None, float | None]`):
          The X, Y and Z to move to; `None` stays where it is.
        * `arc` (`SCArc | None`): The arc, for `G2` and `G3`.
        * `feed` (`float | None`):
          The feed of a `G1`, `G2` or `G3` (default: the tool's feed).
        """
        # Add each axis that moves, and remember where it goes.
        command: RS274 = {"G": code}
        old: tuple[float | None, float | None, float | None] = self.position
        new: list[float | None] = list(old)
        axis: int
        letter: str
        value: float | None
        for axis, (letter, value) in enumerate(zip("XYZ", axes)):
            if value is not None and value != old[axis]:
                command[letter] = value
                new[axis] = value
        self.position = (new[0], new[1], new[2])
        if arc is not None:
            command["I"] = arc.center[0] - arc.start[0]
            command["J"] = arc.center[1] - arc.start[1]
        if len(command) == 1:
            return

        # Add the feed when it is not the last one given.
        speed: float = self.machine.rapid_speed
        if code != 0:
            speed = self.cutter.feed if feed is None else feed
            if self._last_feed() != speed:
                command["F"] = speed
        self.add(command)

        # Count the time it takes, once every axis has a position.
        if None not in old:
            distance: float = math.dist(
                [float(value or 0.0) for value in old],
                [float(value or 0.0) for value in new],
            )
            if arc is not None:
                distance = arc.length()
            self.minutes += distance / speed

    # Method `SCCNC._last_feed()`:
    def _last_feed(self) -> float:
        """Return the last feed given (`F`).

        Returns:
        * (`float`): The feed, or 0 before the first.
        """
        command: RS274
        for command in reversed(self.commands):
            feed: float | int | str | None = command.get("F")
            if isinstance(feed, (int, float)):
                return float(feed)
        return 0.0

    # Method `SCCNC.rapid()`:
    def rapid(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Move as fast as the machine can (`G0`).

        Arguments:
        * `x` (`float | None`): The X to move to, or `None` to stay.
        * `y` (`float | None`): The Y to move to, or `None` to stay.
        * `z` (`float | None`): The Z to move to, or `None` to stay.
        """
        self._move(0, (x, y, z))

    # Method `SCCNC.linear()`:
    def linear(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Cut in a straight line at the tool's feed (`G1`).

        Arguments:
        * `x` (`float | None`): The X to move to, or `None` to stay.
        * `y` (`float | None`): The Y to move to, or `None` to stay.
        * `z` (`float | None`): The Z to move to, or `None` to stay.
        """
        self._move(1, (x, y, z))

    # Method `SCCNC.arc()`:
    def arc(
        self, arc: SCArc, z: float | None = None, *, edge: bool = False
    ) -> None:
        """Cut along an XY arc at the tool's feed (`G2` or `G3`).

        The tool must already be at the arc's start.  With `z`, it goes
        down (or up) as it goes around (a helix).

        With `edge`, the arc cuts a wall climb milled (the material on
        the tool's right, with the spindle turning clockwise), and the
        feed is scaled so that the cutting edge moves at the tool's
        feed, keeping the chip load the same.  Turning right (`G2`),
        the material is inside the curve, the edge goes around a
        smaller circle than the center and the feed goes up; turning
        left (`G3`), it goes down.

        Arguments:
        * `arc` (`SCArc`): The arc.
        * `z` (`float | None`): The Z to end at, or `None` to stay.
        * `edge` (`bool`): True to scale the feed for the cutting edge.
        """
        # Scale the feed by the center's radius over the edge's.
        feed: float | None = None
        if edge:
            tool_radius: float = self.cutter.diameter / 2.0
            edge_radius: float = arc.radius + (
                tool_radius if arc.sweep > 0.0 else -tool_radius
            )
            scale: float = ARC_FEED_MAX
            if edge_radius > EPSILON:
                scale = min(arc.radius / edge_radius, ARC_FEED_MAX)
            feed = self.cutter.feed * max(scale, ARC_FEED_MIN)
        self._move(
            3 if arc.sweep > 0.0 else 2,
            (arc.end[0], arc.end[1], z),
            arc,
            feed,
        )

    # Method `SCCNC.plunge()`:
    def plunge(self, z: float) -> None:
        """Go straight down (or up) at the tool's plunge feed (`G1`).

        Arguments:
        * `z` (`float`): The Z to go to.
        """
        self._move(1, (None, None, z), feed=self.cutter.plunge)

    # Method `SCCNC.drill()`:
    def drill(
        self, points: Sequence[Point], bottom: float, *, through: bool = False
    ) -> None:
        """Drill holes from `z_top` down to `bottom` with a drill.

        The machine's `drill_cycle` says how: a canned cycle (`G81`,
        `G73` or `G83`, returning to `z_safe` between holes with
        `G98`), or the pecks written out as moves.  Each peck goes the
        drill's `peck` deeper (all the way when it is 0).

        Arguments:
        * `points` (`Sequence[Point]`): Where the holes go.
        * `bottom` (`float`): How deep they go.
        * `through` (`bool`):
          True when `bottom` is the bottom of the part, so the holes go
          the machine's `through_overcut` deeper (see `below()`).

        Raises:
        * `ValueError`:
          If the tool is not a drill, or `bottom` is not below `z_top`.
        """
        # Validate the drill and the depth.
        tool: SCTool = self.cutter
        if tool.kind != "drill":
            raise ValueError(f"tool {tool.number} is not a drill")
        bottom = self.below(bottom, through)
        if not points:
            return
        cycle: str = self.machine.drill_cycle
        self.comment(f"Drill {len(points)} holes to Z{_number(bottom)}")
        self.rapid(z=self.z_safe)
        retract: float = self.z_top + self.clearance
        peck: float = tool.peck if tool.peck > 0.0 else retract - bottom

        # Pecks written out as moves.
        point: Point
        if cycle == "moves":
            for point in points:
                self._peck(point, bottom, retract)
            return

        # A canned cycle: one line for the first hole, then just where
        # each of the others is.
        self.add({"G": 98})
        index: int
        for index, point in enumerate(points):
            command: RS274 = {"X": point[0], "Y": point[1]}
            if index == 0:
                command = {"G": int(cycle[1:]), **command}
                command.update({"Z": bottom, "R": retract})
                if cycle != "G81":
                    command["Q"] = peck
                command["F"] = tool.plunge
            self.add(command)
            self._time_hole(point, (retract, bottom), peck)
        self.add({"G": 80})

    # Method `SCCNC._peck()`:
    def _peck(self, point: Point, bottom: float, retract: float) -> None:
        """Drill one hole, pecking, with ordinary moves.

        Arguments:
        * `point` (`Point`): Where the hole goes.
        * `bottom` (`float`): How deep it goes.
        * `retract` (`float`): The Z to rise to between pecks.
        """
        # Go over the hole and down to just above the work.
        tool: SCTool = self.cutter
        peck: float = tool.peck if tool.peck > 0.0 else retract - bottom
        self.rapid(x=point[0], y=point[1])
        self.rapid(z=retract)

        # Each peck goes back down quickly to just above the last one.
        depth: float = self.z_top
        while depth > bottom + EPSILON:
            if depth < self.z_top:
                self.rapid(z=min(depth + self.clearance, retract))
            depth = max(bottom, depth - peck)
            self.plunge(depth)
            self.rapid(z=retract)
        self.rapid(z=self.z_safe)

    # Method `SCCNC._time_hole()`:
    def _time_hole(
        self, point: Point, heights: tuple[float, float], peck: float
    ) -> None:
        """Count the time a canned cycle takes for one hole.

        Arguments:
        * `point` (`Point`): Where the hole is.
        * `heights` (`tuple[float, float]`):
          The cycle's `R` (retract) Z and its bottom.
        * `peck` (`float`): How deep each peck goes.
        """
        # Over to the hole at `z_safe`, then down, the pecks, and back.
        retract: float
        bottom: float
        retract, bottom = heights
        x: float | None
        y: float | None
        x, y, _ = self.position
        rapids: float = 2.0 * (self.z_safe - retract)
        if x is not None and y is not None:
            rapids += math.dist((x, y), point)
        pecks: int = max(1, math.ceil((retract - bottom) / peck - EPSILON))
        rapids += pecks * 2.0 * (retract - bottom) / 2.0
        self.minutes += rapids / self.machine.rapid_speed
        self.minutes += (retract - bottom) / self.cutter.plunge
        self.position = (point[0], point[1], self.z_safe)

    # Method `SCCNC.below()`:
    def below(self, bottom: float, through: bool = True) -> float:
        """Return how deep to cut to reach a bottom.

        A cut through the part goes the machine's `through_overcut`
        (a fraction of the part's thickness) deeper, so that the metal
        is cut cleanly instead of stretching and bulging out.

        Arguments:
        * `bottom` (`float`): The bottom (of the part, when `through`).
        * `through` (`bool`): True for a cut through the part.

        Returns:
        * (`float`): The Z to cut down to.

        Raises:
        * `ValueError`: If `bottom` is not below `z_top`.
        """
        if bottom >= self.z_top:
            raise ValueError(f"{bottom=} must be below {self.z_top=}")
        if not through:
            return bottom
        return bottom - self.machine.through_overcut * (self.z_top - bottom)

    # Method `SCCNC.chamfer()`:
    def chamfer(
        self, poly: SCRoundPoly, size: float = 0.0, *, inside: bool = False
    ) -> SCRoundPoly:
        """Bevel or round over the top edge of an outline.

        With a chamfer bit (a V-bit of included angle 2θ), the bevel is
        `size` wide across the top: the tip runs `CHAMFER_CLEAR` (plus
        its own radius) off the wall, `(size + CHAMFER_CLEAR) / tan θ`
        down, so the bit's flank lays the bevel across the edge (45
        degrees for a 90 degree bit).  With a corner rounding bit, the
        edge is rounded to the bit's radius (`size` is not used): its
        tip runs its own radius off the wall, the radius down.

        The tool climb mills (the part on its right), with half circle
        leads as a profile has, in one pass.

        Arguments:
        * `poly` (`SCRoundPoly`): The outline whose top edge to do.
        * `size` (`float`): The bevel's width across the top.
        * `inside` (`bool`):
          True for the edge of a hole or pocket (from inside the
          outline), False for the outside of the part (or an island).

        Returns:
        * (`SCRoundPoly`): The path the tool's center followed.

        Raises:
        * `ValueError`:
          If the tool is neither a chamfer nor a corner rounding bit,
          or a bevel's size is not positive.
        """
        # How far off the wall the tip goes, how deep, and how wide the
        # bit cuts at the top.
        tool: SCTool = self.cutter
        tip: float = tool.diameter / 2.0
        if tool.kind == "chamfer":
            if size <= 0.0:
                raise ValueError(f"chamfer {size=} must be positive")
            slope: float = math.tan(math.radians(tool.angle / 2.0))
            offset: float = tip + CHAMFER_CLEAR
            depth: float = (size + CHAMFER_CLEAR) / slope
            reach: float = offset + depth * slope
            what: str = f"Chamfer {poly.name} {_number(size)} wide"
        elif tool.kind == "corner round":
            offset = tip
            depth = tool.radius
            reach = tip + tool.radius
            what = f"Round over {poly.name} to {_number(tool.radius)}"
        else:
            raise ValueError(f"tool {tool.number} cannot chamfer")

        # Down at the lead-in's start, in, once around, out, and up.
        path: SCRoundPoly
        lead_in: SCArc
        loop: list[SCSegment]
        lead_out: SCArc
        path, (lead_in, loop, lead_out) = _profile_path(
            poly, inside, offset, reach
        )
        self.comment(f"{what} {'inside' if inside else 'outside'}")
        self.rapid(z=self.z_safe)
        self.rapid(x=lead_in.start[0], y=lead_in.start[1])
        self.rapid(z=self.z_top + self.clearance)
        self.plunge(self.z_top - depth)
        self._follow([lead_in, *loop, lead_out], [])
        self.rapid(z=self.z_safe)
        return path

    # Method `SCCNC._stage_depths()`:
    def _stage_depths(
        self, bottom: float, step: float, through: bool, stage: Stage
    ) -> list[float]:
        """Return the depths a stage of a cut goes to.

        Arguments:
        * `bottom` (`float`): The cut's bottom.
        * `step` (`float`): The most to go down between depths.
        * `through` (`bool`): True when `bottom` is the part's bottom.
        * `stage` (`Stage`): The stage.

        Returns:
        * (`list[float]`):
          The depths: down to `finish_allowance` above `bottom` when
          roughing (never through, so the part is not cut free), only
          the full depth when finishing, and every depth otherwise.
        """
        if stage == "rough":
            return self._depths(bottom + self.machine.finish_allowance, step)
        bottom = self.below(bottom, through)
        if stage == "finish":
            return [bottom]
        return self._depths(bottom, step)

    # Method `SCCNC._stage_offsets()`:
    def _stage_offsets(
        self, tool: SCTool, stage: Stage
    ) -> tuple[float, float]:
        """Return how far off an outline a profile goes, and its leads.

        Arguments:
        * `tool` (`SCTool`): The tool.
        * `stage` (`Stage`): The stage.

        Returns:
        * (`tuple[float, float]`):
          How far the tool's center is off the outline (its radius,
          plus `finish_allowance` when roughing), and the radius of its
          leads.  A finishing pass's leads start where the rougher's
          center went (`finish_allowance` off the path), in the slot
          it cut.
        """
        radius: float = tool.diameter / 2.0
        allowance: float = self.machine.finish_allowance
        if stage == "rough":
            return radius + allowance, radius
        if stage == "finish" and allowance > 0.0:
            return radius, allowance / 2.0
        return radius, radius

    # Method `SCCNC._depths()`:
    def _depths(self, bottom: float, step: float) -> list[float]:
        """Return the depths to cut at, from just below `z_top` down.

        Arguments:
        * `bottom` (`float`): The deepest Z to cut to.
        * `step` (`float`): The most to go down between depths.

        Returns:
        * (`list[float]`): Equally spaced depths, ending at `bottom`.

        Raises:
        * `ValueError`:
          If `bottom` is not below `z_top`, or `step` is not positive.
        """
        if bottom >= self.z_top:
            raise ValueError(f"{bottom=} must be below {self.z_top=}")
        if step <= 0.0:
            raise ValueError(f"{step=} must be positive")
        passes: int = math.ceil((self.z_top - bottom) / step - EPSILON)
        return [
            self.z_top - (self.z_top - bottom) * index / passes
            for index in range(1, passes + 1)
        ]

    # Method `SCCNC._follow()`:
    def _follow(
        self, segments: Sequence[SCSegment], spurs: Sequence[SCLine]
    ) -> None:
        """Cut along segments at the current Z, with any spurs.

        Arguments:
        * `segments` (`Sequence[SCSegment]`): The segments, in order.
        * `spurs` (`Sequence[SCLine]`):
          Spurs to cut out and back wherever a segment ends at one's
          start.
        """
        segment: SCSegment
        for segment in segments:
            if isinstance(segment, SCLine):
                self.linear(x=segment.end[0], y=segment.end[1])
            else:
                self.arc(segment, edge=True)
            spur: SCLine
            for spur in spurs:
                if math.dist(spur.start, segment.end) <= JOIN:
                    self.linear(x=spur.end[0], y=spur.end[1])
                    self.linear(x=spur.start[0], y=spur.start[1])

    # Method `SCCNC.profile()`:
    # Each argument is part of saying what to cut, and the optional
    # ones are keyword-only, so there are more than `pylint` likes.
    def profile(  # pylint: disable=too-many-arguments
        self,
        poly: SCRoundPoly,
        bottom: float,
        step: float,
        *,
        inside: bool = False,
        through: bool = False,
        stage: Stage = "full",
    ) -> SCRoundPoly:
        """Cut along a polygon's outline, from `z_top` down to `bottom`.

        The tool's edge follows the outline from outside it (cutting
        the polygon out) or, when `inside`, from inside it (cutting a
        hole or a pocket's wall).  It climb mills, so it goes clockwise
        around the outside and counter-clockwise around the inside.

        The cut starts and ends in the middle of the path's longest
        segment, with a half circle lead-in and lead-out whose diameter
        is the tool's: they join the path along its tangent, from the
        cutter's left (away from the material being cut), and together
        make one circle, so the lead-out ends where the lead-in starts.

        The tool rises to `z_safe`, moves over the lead-in's start (see
        `profile_entry()`), comes down to `clearance` above `z_top`, and
        then at each depth (`step` or less below the last) goes down at
        the plunge feed, in along the lead-in, once around, and out
        along the lead-out; finally it rises to `z_safe`.

        Arguments:
        * `poly` (`SCRoundPoly`): The outline to cut along.
        * `bottom` (`float`): The deepest Z to cut to.
        * `step` (`float`): The most to go down between passes.
        * `inside` (`bool`): True to cut from inside the outline.
        * `through` (`bool`):
          True when `bottom` is the bottom of the part, so the cut goes
          the machine's `through_overcut` deeper (see `below()`).
        * `stage` (`Stage`):
          `"rough"` to leave the machine's `finish_allowance` on the
          wall and floor (and not cut through), `"finish"` to cut them
          to size in one pass at full depth, or `"full"`.

        Returns:
        * (`SCRoundPoly`): The path the tool's center followed.

        Raises:
        * `ValueError`:
          If `bottom` is not below `z_top`, `step` is not positive, or
          the tool cannot follow the outline.
        """
        # Plan the path and its leads.
        depths: list[float] = self._stage_depths(bottom, step, through, stage)
        path: SCRoundPoly
        lead_in: SCArc
        loop: list[SCSegment]
        lead_out: SCArc
        path, (lead_in, loop, lead_out) = _fitted_path(
            poly, inside, *self._stage_offsets(self.cutter, stage)
        )

        # Go over the lead-in's start, then down to just above the top.
        side: str = "inside" if inside else "outside"
        self.comment(
            f"{STAGE_WORDS[stage]}rofile {poly.name} {side} "
            f"to Z{_number(depths[-1])}"
        )
        self.rapid(z=self.z_safe)
        self.rapid(x=lead_in.start[0], y=lead_in.start[1])
        self.rapid(z=self.z_top + self.clearance)

        # At each depth, go down, in, once around, and out.
        z: float
        for z in depths:
            self.plunge(z)
            self._follow([lead_in, *loop, lead_out], [])
        self.rapid(z=self.z_safe)
        return path

    # Method `SCCNC.profile_entry()`:
    def profile_entry(
        self,
        poly: SCRoundPoly,
        tool: SCTool,
        *,
        inside: bool = False,
        stage: Stage = "full",
    ) -> Point:
        """Return where a profile cut with a tool goes down.

        This is where to drill, so that the tool goes down a hole.

        Arguments:
        * `poly` (`SCRoundPoly`): The outline.
        * `tool` (`SCTool`): The tool that will cut it.
        * `inside` (`bool`): True to cut from inside the outline.
        * `stage` (`Stage`): The stage of the cut (see `profile()`).

        Returns:
        * (`Point`): The start of the profile's lead-in.
        """
        offsets: tuple[float, float] = self._stage_offsets(tool, stage)
        return _fitted_path(poly, inside, *offsets)[1][0].start

    # Method `SCCNC.pocket()`:
    # Each argument is part of saying what to cut, and the optional
    # ones are keyword-only, so there are more than `pylint` likes.
    def pocket(  # pylint: disable=too-many-arguments
        self,
        poly: SCRoundPoly,
        bottom: float,
        step: float,
        *,
        islands: Sequence[SCRoundPoly] = (),
        drilled: bool = False,
        through: bool = False,
        stage: Stage = "full",
    ) -> list[SCRing]:
        """Clear the inside of a polygon, from `z_top` down to `bottom`.

        The pocket is cleared by rings (see `plan_pocket()`), at each
        depth in turn (`step` or less below the last).  At each depth
        the rings are cut from the smallest out, each ring after all of
        the rings inside it, so each ring's lead-in starts where they
        have already cut (see `cut_order()`).  The smallest rings have
        nothing cut inside them, so the tool goes down into them at
        their starts (see `pocket_entries()`): straight down at the
        plunge feed when holes have been drilled there, or else ramping
        down along the ring itself, going around as many times as
        needed to go no steeper than the machine's `ramp_angle`.

        Between rings, the tool stays in the pocket when the way there
        crosses no wall: going up to the last depth (where the pocket
        is clear) before going over to a smallest ring.  Otherwise it
        rises to `z_safe`, goes over, and comes back down.

        Arguments:
        * `poly` (`SCRoundPoly`): The pocket's outline.
        * `bottom` (`float`): The pocket's floor.
        * `step` (`float`): The most to go down between depths.
        * `islands` (`Sequence[SCRoundPoly]`):
          Outlines inside the pocket to leave standing.
        * `drilled` (`bool`):
          True when holes have been drilled at `pocket_entries()`.
        * `through` (`bool`):
          True when `bottom` is the bottom of the part, so the cut goes
          the machine's `through_overcut` deeper (see `below()`).
        * `stage` (`Stage`):
          `"rough"` to leave the machine's `finish_allowance` on the
          walls, islands and floor, `"finish"` to cut every ring once
          at full depth (going straight down into what the rougher
          cleared), or `"full"`.

        Returns:
        * (`list[SCRing]`): The outermost rings (with the rest inside).

        Raises:
        * `ValueError`:
          If `bottom` is not below `z_top`, `step` is not positive, the
          islands are not inside the pocket and apart, or the tool does
          not fit in the pocket.
        """
        # Plan the rings, then cut them.
        depths: list[float] = self._stage_depths(bottom, step, through, stage)
        roots: list[SCRing] = self._plan(
            poly, islands, self.cutter.diameter, stage
        )
        around: str = f" around {len(islands)} islands" if islands else ""
        word: str = STAGE_WORDS[stage]
        self.comment(
            f"{word}ocket {poly.name}{around} to Z{_number(depths[-1])}"
        )
        self._clear(roots, depths, drilled or stage == "finish")
        return roots

    # Method `SCCNC._clear()`:
    def _clear(
        self, roots: Sequence[SCRing], depths: Sequence[float], drilled: bool
    ) -> None:
        """Cut every ring of a pocket at each depth, smallest first.

        Arguments:
        * `roots` (`Sequence[SCRing]`): The outermost rings.
        * `depths` (`Sequence[float]`): The depths, from the top down.
        * `drilled` (`bool`): True when the entries have been drilled.
        """
        walls: list[SCLoop] = [loop for root in roots for loop in root.loops]
        self.rapid(z=self.z_safe)
        above: float = self.z_top + self.clearance
        z: float
        for z in depths:
            root: SCRing
            for root in roots:
                ring: SCRing
                mode: CutMode
                for ring, mode in cut_order(root, self.cutter.diameter):
                    if drilled and mode == "ramp":
                        mode = "drilled"
                    self._cut_ring(ring, mode, (above, z), walls)
            above = z
        self.rapid(z=self.z_safe)

    # Method `SCCNC._plan()`:
    def _plan(
        self,
        poly: SCRoundPoly,
        islands: Sequence[SCRoundPoly],
        diameter: float,
        stage: Stage = "full",
    ) -> list[SCRing]:
        """Plan the rings that clear a pocket with a tool.

        Arguments:
        * `poly` (`SCRoundPoly`): The pocket's outline.
        * `islands` (`Sequence[SCRoundPoly]`): Outlines to leave.
        * `diameter` (`float`): The tool's diameter.
        * `stage` (`Stage`):
          `"rough"` to keep the machine's `finish_allowance` away from
          the walls and islands.

        Returns:
        * (`list[SCRing]`): The outermost rings.

        Raises:
        * `ValueError`:
          If an island is not inside the pocket, or two outlines cross
          or touch.
        """
        # The pocket's wall goes counter-clockwise, and its islands
        # clockwise, so the pocket is on the left of each.
        wall: SCLoop = SCLoop.from_poly(poly)
        if not wall.is_ccw():
            wall = wall.reversed()
        region: list[SCLoop] = [wall]
        island: SCRoundPoly
        for island in islands:
            loop: SCLoop = SCLoop.from_poly(island)
            region.append(loop.reversed() if loop.is_ccw() else loop)
            if not wall.contains(loop.segments[0].start):
                raise ValueError(f"{island.name} is not inside {poly.name}")

        # No two outlines may cross or touch.
        index: int
        for index, loop in enumerate(region):
            other: SCLoop
            for other in region[index + 1 :]:
                if any(
                    meet(first, second)
                    for first in loop.segments
                    for second in other.segments
                ):
                    raise ValueError(f"{loop.name} meets {other.name}")

        # A rougher clears what is left once the walls and islands are
        # moved in by the allowance.
        allowance: float = self.machine.finish_allowance
        if stage == "rough" and allowance > 0.0:
            region = inset(region, allowance, poly.name)
        return plan_pocket(region, diameter, self.machine.stepover)

    # Method `SCCNC.pocket_entries()`:
    def pocket_entries(
        self,
        poly: SCRoundPoly,
        tool: SCTool,
        islands: Sequence[SCRoundPoly] = (),
        stage: Stage = "full",
    ) -> list[Point]:
        """Return where a pocket cut with a tool goes down into it.

        These are where to drill, so that the tool goes down holes
        (with `pocket(..., drilled=True)`): the start of each loop of
        the rings that have nothing cut inside them.

        Arguments:
        * `poly` (`SCRoundPoly`): The pocket's outline.
        * `tool` (`SCTool`): The tool that will clear it.
        * `islands` (`Sequence[SCRoundPoly]`): Outlines to leave.
        * `stage` (`Stage`): The stage of the cut (see `pocket()`).

        Returns:
        * (`list[Point]`): The points, in the order they are cut.
        """
        return [
            loop.segments[0].start
            for root in self._plan(poly, islands, tool.diameter, stage)
            for ring, mode in cut_order(root, tool.diameter)
            if mode == "ramp"
            for loop in ring.loops
        ]

    # Method `SCCNC._cut_ring()`:
    def _cut_ring(
        self,
        ring: SCRing,
        mode: CutMode,
        heights: tuple[float, float],
        walls: Sequence[SCLoop],
    ) -> None:
        """Cut once around a pocket's ring at one depth.

        Arguments:
        * `ring` (`SCRing`): The ring.
        * `mode` (`CutMode`): How to cut it (see `cut_order()`).
        * `heights` (`tuple[float, float]`):
          The Z the pocket is clear down to (or just above `z_top`, at
          the first depth), and the Z to cut at.
        * `walls` (`Sequence[SCLoop]`): The pocket's outermost rings.
        """
        # A ring with nothing cut inside it is ramped down into, along
        # each of its loops (or plunged into, down a drilled hole at
        # each); a small one is cut straight into.
        above: float
        z: float
        above, z = heights
        loop: SCLoop
        if mode != "lead":
            for loop in ring.loops:
                self._arrive(
                    loop.segments[0].start,
                    z if mode == "plain" else above,
                    walls,
                )
                if mode == "ramp":
                    self._ramp(loop, above, z)
                elif mode == "drilled":
                    self.plunge(z)
                self._follow(loop.segments, ring.spurs)
            return

        # Another ring is led into from inside it, where it is cut.
        for loop in ring.loops:
            self._cut_loop(loop, ring.spurs, z, walls)

    # Method `SCCNC._cut_loop()`:
    def _cut_loop(
        self,
        loop: SCLoop,
        spurs: Sequence[SCLine],
        z: float,
        walls: Sequence[SCLoop],
    ) -> None:
        """Cut once around a loop at one depth, led in from its left.

        Arguments:
        * `loop` (`SCLoop`): The loop (with what is cut on its left).
        * `spurs` (`Sequence[SCLine]`): Spurs from its corners.
        * `z` (`float`): The Z to cut at.
        * `walls` (`Sequence[SCLoop]`): The pocket's outermost rings.
        """
        try:
            lead_in: SCArc
            path: list[SCSegment]
            lead_out: SCArc
            lead_in, path, lead_out = _leads(loop, self.cutter.diameter / 2.0)
        except ValueError:
            self._arrive(loop.segments[0].start, z, walls)
            self._follow(loop.segments, spurs)
            return
        self._arrive(lead_in.start, z, walls)
        self.arc(lead_in)
        self._follow(path, spurs)
        self.arc(lead_out)

    # Method `SCCNC._arrive()`:
    def _arrive(
        self, target: Point, z: float, walls: Sequence[SCLoop]
    ) -> None:
        """Move the tool to a point in a pocket, at a clear Z.

        Arguments:
        * `target` (`Point`): Where to go.
        * `z` (`float`): The Z to arrive at.
        * `walls` (`Sequence[SCLoop]`): The pocket's outermost rings.
        """
        # Stay in the pocket when the way there crosses no wall.
        x: float | None
        y: float | None
        height: float | None
        x, y, height = self.position
        if x is not None and y is not None and height is not None:
            here: Point = (x, y)
            way: list[SCLine] = (
                [SCLine(here, target)]
                if math.dist(here, target) > EPSILON
                else []
            )
            if height < self.z_top and not any(
                meet(line, segment)
                for line in way
                for wall in walls
                for segment in wall.segments
            ):
                # Above the material the way over is a rapid.
                if height < z:
                    self.rapid(z=z)
                if z >= self.z_top + self.clearance:
                    self.rapid(x=target[0], y=target[1])
                else:
                    self.linear(x=target[0], y=target[1])
                self.linear(z=z)
                return

        # Otherwise go up, over, and down.
        self.rapid(z=self.z_safe)
        self.rapid(x=target[0], y=target[1])
        self.rapid(z=self.z_top + self.clearance)
        self.linear(z=z)

    # Method `SCCNC._ramp()`:
    def _ramp(self, loop: SCLoop, above: float, z: float) -> None:
        """Go down along a loop, no steeper than `ramp_angle`.

        The tool starts at the loop's start, at `above`, and goes around
        as many whole times as it needs, ending back at the start, at
        `z`.

        Arguments:
        * `loop` (`SCLoop`): The loop.
        * `above` (`float`): The Z to start at.
        * `z` (`float`): The Z to end at.
        """
        # A loop too small to go around is just plunged into.
        drop: float = above - z
        lap: float = loop.length()
        if lap < EPSILON:
            self.linear(z=z)
            return
        run: float = drop / math.tan(math.radians(self.machine.ramp_angle))
        laps: int = max(1, math.ceil(run / lap - EPSILON))

        # Go down evenly along the way around.
        total: float = laps * lap
        done: float = 0.0
        for _ in range(laps):
            segment: SCSegment
            for segment in loop.segments:
                done += segment.length()
                height: float = above - drop * done / total
                if done >= total * (1.0 - EPSILON):
                    height = z
                if isinstance(segment, SCLine):
                    self.linear(x=segment.end[0], y=segment.end[1], z=height)
                else:
                    self.arc(segment, z=height)

    # Method `SCCNC.finish()`:
    def finish(self) -> None:
        """End the program: rise to `z_safe`, stop the spindle, `M2`."""
        self.rapid(z=self.z_safe)
        self.add({"M": 5})
        self.add({"M": 2})

    # Method `SCCNC.gcode()`:
    def gcode(self) -> str:
        """Return the program as G-code text.

        Returns:
        * (`str`): One line per command, each ending with a newline.
        """
        lines: list[str] = []
        command: RS274
        for command in self.commands:
            if "comment" in command:
                lines.append(f"({command['comment']})")
                continue
            words: list[str] = []
            letter: str
            value: float | int | str
            for letter, value in command.items():
                if letter == "note":
                    continue
                if isinstance(value, str):
                    words.append(f"{letter}{value}")
                elif letter in "GM":
                    words.append(f"{letter}{value:g}")
                else:
                    words.append(f"{letter}{_number(value)}")
            if "note" in command:
                words.append(f"({command['note']})")
            lines.append(" ".join(words))
        return "".join(f"{line}\n" for line in lines)
