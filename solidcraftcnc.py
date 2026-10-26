"""Generate 3-axis mill RS-274 (G-code) for shapes made in SolidCraft.

`SCCNC` collects RS-274 commands, each a plain dictionary of words
(e.g. `{"G": 1, "X": 1.0, "F": 12.0}`), and writes them as G-code.  It
works in inches, and cuts the shapes of `scgeometry` (such as
`SCRoundPoly`): along their outlines (`SCCNC.profile()`) and out of
their insides (`SCCNC.pocket()`).

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
    halves,
    inset,
    left,
    meet,
    start_tangent,
    turn_between,
    unit,
)

# One RS-274 command: its words, in order, keyed by letter (e.g.
# `{"G": 1, "X": 10.0}`).  The key `comment` holds a comment's text.
RS274: TypeAlias = dict[str, float | int | str]

# How a pocket's ring is cut at each depth: ramped down into along
# itself (nothing inside it is cut first), led into from inside (where
# its rings are cut first), or cut straight into (a ring too small to
# ramp into, cut after the ring around it).
CutMode: TypeAlias = Literal["ramp", "lead", "plain"]

# A smallest ring shorter than this many tool diameters is too small to
# ramp into well (going around it would be little better than plunging
# straight down), so it is cut after the ring around it, which is
# ramped into instead.
SMALL_RING: float = 2.0


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

    Attributes:
    * `loop` (`SCLoop`):
      The path the tool's center follows, counter-clockwise (so that
      it climb mills, with the material it cuts on its right).
    * `children` (`list[SCRing]`): The rings just inside this one.
    * `spurs` (`list[SCLine]`):
      Short cuts straight out from sharp corners of `loop` (and back),
      into the corners between it and the rings around it, which would
      otherwise be left uncut.

    Constructor:
    * `SCRing(loop)`
    """

    # Constructor arguments:
    loop: SCLoop = field(init=True)

    # Attributes filled in by `plan_pocket()` (alphabetized):
    children: list["SCRing"] = field(init=False, default_factory=list)
    spurs: list[SCLine] = field(init=False, default_factory=list)

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
        if not child.children and child.loop.length() < SMALL_RING * diameter
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
    boundary: SCLoop, diameter: float, stepover: float
) -> list[SCRing]:
    """Plan the rings that clear a pocket.

    The outermost rings follow the pocket's wall, a tool radius in
    from it.  Inside each ring are the rings `stepover` of the tool's
    diameter in from it, until they vanish; where the last rings would
    leave the middle uncut, one more set follows the outline of what is
    left.

    Arguments:
    * `boundary` (`SCLoop`): The pocket's wall, counter-clockwise.
    * `diameter` (`float`): The tool's diameter.
    * `stepover` (`float`):
      How far apart the rings are, as a fraction of `diameter`.

    Returns:
    * (`list[SCRing]`): The outermost rings (more than one when the
      pocket narrows to less than the tool's diameter somewhere).

    Raises:
    * `ValueError`: If the tool does not fit in the pocket.
    """
    walls: list[SCLoop] = inset([boundary], diameter / 2.0, boundary.name)
    if not walls:
        raise ValueError(f"{boundary.name}: the tool does not fit in it")
    roots: list[SCRing] = [SCRing(loop) for loop in walls]
    root: SCRing
    for root in roots:
        _grow(root, diameter, stepover * diameter, 1)
    return roots


# Function `_grow()`:
def _grow(ring: SCRing, diameter: float, step: float, level: int) -> None:
    """Fill in the rings inside a ring, and theirs, and so on.

    Arguments:
    * `ring` (`SCRing`): The ring.
    * `diameter` (`float`): The tool's diameter.
    * `step` (`float`): How far in each ring is from the one around it.
    * `level` (`int`): How many rings `ring` is inside of.
    """
    # The rings a step in, or the last ones a smaller step in.
    name: str = f"{ring.loop.name.split(' ring ')[0]} ring {level}"
    loops: list[SCLoop] = inset([ring.loop], step, name)
    if loops:
        ring.children = [SCRing(loop) for loop in loops]
        child: SCRing
        for child in ring.children:
            _grow(child, diameter, step, level + 1)
    else:
        ring.children = [
            SCRing(loop) for loop in _last_rings(ring.loop, diameter, step)
        ]

    # Reach into the corners the rings leave uncut.
    nearby: list[SCLoop] = [
        ring.loop,
        *(child.loop for child in ring.children),
    ]
    for child in ring.children:
        child.spurs = _spurs(
            child.loop,
            [loop for loop in nearby if loop is not child.loop],
            diameter,
        )


# Function `_last_rings()`:
def _last_rings(loop: SCLoop, diameter: float, step: float) -> list[SCLoop]:
    """Return the rings needed to clear the middle of a smallest ring.

    A ring clears a tool radius on either side, so the part of its
    middle more than a tool radius in is left uncut.  That part is less
    than `step` across, so following its outline clears it.

    Arguments:
    * `loop` (`SCLoop`): The smallest ring (nothing is `step` in).
    * `diameter` (`float`): The tool's diameter.
    * `step` (`float`): The usual distance between rings.

    Returns:
    * (`list[SCLoop]`): The outlines of what is left uncut (none when
      nothing is).
    """
    radius: float = diameter / 2.0
    if step <= radius:
        return []
    return inset([loop], radius, f"{loop.name.split(' ring ')[0]} ring last")


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
# The machine's settings are all constructor arguments, so this class
# has more attributes than `pylint` likes.
@dataclass(slots=True)
class SCCNC:  # pylint: disable=too-many-instance-attributes
    """RS-274 (G-code) for a 3-axis mill, built one command at a time.

    The program works in inches and absolute coordinates, in the XY
    plane, with feeds per minute; arc centers (`I`, `J`) are relative
    to each arc's start.  It starts the spindle clockwise (`M3`) at its
    start, and cuts with an end mill of `tool_diameter`, climb milling:
    the material being cut is always to the right of the cutter.

    The tool moves across the work only at `z_safe` (above all of the
    hold down tooling), and comes down at the rapid speed to
    `clearance` above `z_top` (the top of the material, which may not
    be flat).  Below that, where it may be removing material, it moves
    at `work_speed`.

    Attributes:
    * `name` (`str`): The program's name (its first comment).
    * `z_top` (`float`): The Z of the material's top surface.
    * `z_safe` (`float`):
      The Z above all of the hold down tooling, for moving across.
    * `clearance` (`float`):
      How far above `z_top` rapid moves down stop.
    * `tool_diameter` (`float`): The end mill's diameter.
    * `rapid_speed` (`float`):
      The speed of rapid (`G0`) moves, in inches per minute.  The
      machine sets it, so it is used only to estimate `minutes`.
    * `work_speed` (`float`):
      The feed of moves that may cut (`G1`, `G2`, `G3`), in inches per
      minute.
    * `spindle_rpm` (`float`): The spindle's speed (`S`), in RPM.
    * `stepover` (`float`):
      How far apart a pocket's rings are, as a fraction of
      `tool_diameter`.
    * `ramp_angle` (`float`):
      The steepest angle (degrees) the tool goes down at into uncut
      material in a pocket.
    * `commands` (`list[RS274]`): The program so far.
    * `minutes` (`float`):
      The time the moves so far take, at `rapid_speed` and
      `work_speed` (not counting acceleration).
    * `position` (`tuple[float | None, float | None, float | None]`):
      Where the tool was last sent (X, Y, Z); `None` until that axis
      first moves.

    Constructor:
    * `SCCNC(name, z_top, z_safe, clearance, tool_diameter,
      rapid_speed, work_speed, spindle_rpm, stepover, ramp_angle)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    z_top: float = field(init=True, default=0.0)
    z_safe: float = field(init=True, default=1.0)
    clearance: float = field(init=True, default=0.05)
    tool_diameter: float = field(init=True, default=0.25)
    rapid_speed: float = field(init=True, default=60.0)  # 1 in/s.
    work_speed: float = field(init=True, default=12.0)  # 0.2 in/s.
    spindle_rpm: float = field(init=True, default=1200.0)
    stepover: float = field(init=True, default=0.9)
    ramp_angle: float = field(init=True, default=3.0)

    # Program state (alphabetized):
    commands: list[RS274] = field(init=False, default_factory=list)
    minutes: float = field(init=False, default=0.0)
    position: tuple[float | None, float | None, float | None] = field(
        init=False, default=(None, None, None)
    )

    # Method `SCCNC.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the settings, and start the program.

        The program starts with its name, the machine's modes, a rise
        to `z_safe` and the spindle starting.

        Raises:
        * `ValueError`:
          If `z_safe` is not above `clearance` above `z_top`,
          `clearance` is negative, a size or speed is not positive,
          `stepover` is not above 0 and at most 1, or `ramp_angle` is
          not above 0 and at most 90.
        """
        # Validate the settings.
        if self.clearance < 0.0:
            raise ValueError(f"{self.clearance=} must not be negative")
        if self.z_safe <= self.z_top + self.clearance:
            raise ValueError(
                f"{self.z_safe=} must be above {self.z_top=} "
                f"+ {self.clearance=}"
            )
        name: str
        for name in ("tool_diameter", "rapid_speed", "work_speed"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.spindle_rpm <= 0.0:
            raise ValueError(f"{self.spindle_rpm=} must be positive")
        if not 0.0 < self.stepover <= 1.0:
            raise ValueError(f"{self.stepover=} must be in (0, 1]")
        if not 0.0 < self.ramp_angle <= 90.0:
            raise ValueError(f"{self.ramp_angle=} must be in (0, 90]")

        # Start the program.
        self.comment(self.name)
        self.add({"G": 20})  # Inches.
        self.add({"G": 90})  # Absolute coordinates.
        self.add({"G": 17})  # The XY plane.
        self.add({"G": 94})  # Feeds per minute.
        self.rapid(z=self.z_safe)
        self.add({"M": 3, "S": self.spindle_rpm})

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
    ) -> None:
        """Append a move, leaving out unchanged axes and feeds.

        A rapid or line that would not move is left out entirely.

        Arguments:
        * `code` (`int`): The move's `G` code.
        * `axes` (`tuple[float | None, float | None, float | None]`):
          The X, Y and Z to move to; `None` stays where it is.
        * `arc` (`SCArc | None`): The arc, for `G2` and `G3`.
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
        speed: float = self.rapid_speed
        if code != 0:
            speed = self.work_speed
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
        """Cut in a straight line at `work_speed` (`G1`).

        Arguments:
        * `x` (`float | None`): The X to move to, or `None` to stay.
        * `y` (`float | None`): The Y to move to, or `None` to stay.
        * `z` (`float | None`): The Z to move to, or `None` to stay.
        """
        self._move(1, (x, y, z))

    # Method `SCCNC.arc()`:
    def arc(self, arc: SCArc, z: float | None = None) -> None:
        """Cut along an XY arc at `work_speed` (`G2` or `G3`).

        The tool must already be at the arc's start.  With `z`, it goes
        down (or up) as it goes around (a helix).

        Arguments:
        * `arc` (`SCArc`): The arc.
        * `z` (`float | None`): The Z to end at, or `None` to stay.
        """
        self._move(
            3 if arc.sweep > 0.0 else 2, (arc.end[0], arc.end[1], z), arc
        )

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
                self.arc(segment)
            spur: SCLine
            for spur in spurs:
                if math.dist(spur.start, segment.end) <= JOIN:
                    self.linear(x=spur.end[0], y=spur.end[1])
                    self.linear(x=spur.start[0], y=spur.start[1])

    # Method `SCCNC.profile()`:
    def profile(
        self,
        poly: SCRoundPoly,
        bottom: float,
        step: float,
        inside: bool = False,
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

        The tool rises to `z_safe`, moves over the lead-in's start,
        comes down to `clearance` above `z_top`, and then at each depth
        (`step` or less below the last) goes down, in along the
        lead-in, once around, and out along the lead-out; finally it
        rises to `z_safe`.

        Arguments:
        * `poly` (`SCRoundPoly`): The outline to cut along.
        * `bottom` (`float`): The deepest Z to cut to.
        * `step` (`float`): The most to go down between passes.
        * `inside` (`bool`): True to cut from inside the outline.

        Returns:
        * (`SCRoundPoly`): The path the tool's center followed.

        Raises:
        * `ValueError`:
          If `bottom` is not below `z_top`, `step` is not positive, or
          the tool cannot follow the outline.
        """
        # Move the tool's center off the outline by its radius, and go
        # the climb milling way around.
        depths: list[float] = self._depths(bottom, step)
        radius: float = self.tool_diameter / 2.0
        path: SCRoundPoly = poly.offset(-radius if inside else radius)
        if path.is_ccw() != inside:
            path = path.reversed()

        # Go over the lead-in's start, then down to just above the top.
        side: str = "inside" if inside else "outside"
        self.comment(f"Profile {poly.name} {side} to Z{_number(bottom)}")
        lead_in: SCArc
        loop: list[SCSegment]
        lead_out: SCArc
        lead_in, loop, lead_out = _leads(SCLoop.from_poly(path), radius)
        self.rapid(z=self.z_safe)
        self.rapid(x=lead_in.start[0], y=lead_in.start[1])
        self.rapid(z=self.z_top + self.clearance)

        # At each depth, go down, in, once around, and out.
        z: float
        for z in depths:
            self.linear(z=z)
            self._follow([lead_in, *loop, lead_out], [])
        self.rapid(z=self.z_safe)
        return path

    # Method `SCCNC.pocket()`:
    def pocket(
        self, poly: SCRoundPoly, bottom: float, step: float
    ) -> list[SCRing]:
        """Clear the inside of a polygon, from `z_top` down to `bottom`.

        The pocket is cleared by rings (see `plan_pocket()`), at each
        depth in turn (`step` or less below the last).  At each depth
        the rings are cut from the smallest out, each ring after all of
        the rings inside it, so each ring's lead-in starts where they
        have already cut (see `cut_order()`).  The smallest rings have
        nothing cut inside them, so the tool ramps down into them along
        the ring itself, going around as many times as needed to go no
        steeper than `ramp_angle`.

        Between rings, the tool stays in the pocket when the way there
        crosses no wall: going up to the last depth (where the pocket
        is clear) before going over to a smallest ring.  Otherwise it
        rises to `z_safe`, goes over, and comes back down.

        Arguments:
        * `poly` (`SCRoundPoly`): The pocket's outline.
        * `bottom` (`float`): The pocket's floor.
        * `step` (`float`): The most to go down between depths.

        Returns:
        * (`list[SCRing]`): The outermost rings (with the rest inside).

        Raises:
        * `ValueError`:
          If `bottom` is not below `z_top`, `step` is not positive, or
          the tool does not fit in the pocket.
        """
        # Plan the rings.
        depths: list[float] = self._depths(bottom, step)
        boundary: SCLoop = SCLoop.from_poly(poly)
        if not boundary.is_ccw():
            boundary = boundary.reversed()
        roots: list[SCRing] = plan_pocket(
            boundary, self.tool_diameter, self.stepover
        )
        walls: list[SCLoop] = [root.loop for root in roots]

        # Cut every ring at each depth, smallest rings first.
        self.comment(f"Pocket {poly.name} to Z{_number(bottom)}")
        self.rapid(z=self.z_safe)
        above: float = self.z_top + self.clearance
        z: float
        for z in depths:
            root: SCRing
            for root in roots:
                ring: SCRing
                mode: CutMode
                for ring, mode in cut_order(root, self.tool_diameter):
                    self._cut_ring(ring, mode, (above, z), walls)
            above = z
        self.rapid(z=self.z_safe)
        return roots

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
        # itself; a small one is cut straight into.
        above: float
        z: float
        above, z = heights
        if mode != "lead":
            self._arrive(
                ring.loop.segments[0].start,
                above if mode == "ramp" else z,
                walls,
            )
            if mode == "ramp":
                self._ramp(ring.loop, above, z)
            self._follow(ring.loop.segments, ring.spurs)
            return

        # Another ring is led into from inside it, where it is cut.
        try:
            lead_in: SCArc
            loop: list[SCSegment]
            lead_out: SCArc
            lead_in, loop, lead_out = _leads(
                ring.loop, self.tool_diameter / 2.0
            )
        except ValueError:
            self._arrive(ring.loop.segments[0].start, z, walls)
            self._follow(ring.loop.segments, ring.spurs)
            return
        self._arrive(lead_in.start, z, walls)
        self.arc(lead_in)
        self._follow(loop, ring.spurs)
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
        run: float = drop / math.tan(math.radians(self.ramp_angle))
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
                if isinstance(value, str):
                    words.append(f"{letter}{value}")
                elif letter in "GM":
                    words.append(f"{letter}{value:g}")
                else:
                    words.append(f"{letter}{_number(value)}")
            lines.append(" ".join(words))
        return "".join(f"{line}\n" for line in lines)
