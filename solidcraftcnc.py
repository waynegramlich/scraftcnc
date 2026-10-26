"""Generate 3-axis mill RS-274 (G-code) for shapes made in SolidCraft.

`SCRoundPoly` is a polygon in the XY plane whose corners each have
their own radius.  It computes its own outline as straight lines and
tangent arcs, so the same geometry can be drawn into a SolidCraft
sketch (`SCRoundPoly.sketch()`) and followed by a tool (`SCCNC`).

`SCCNC` collects RS-274 commands, each a plain dictionary of words
(e.g. `{"G": 1, "X": 1.0, "F": 12.0}`), and writes them as G-code.  It
works in inches.

This module only uses `pysolidcraft` through the `PySolidCraft` that
is handed to `SCRoundPoly.sketch()`, so it does not import it (or
carry the EZPkg bootstrap that a program importing it needs).
`solidcraftcnc_demo.py` is a program that uses both.
"""

# Most of this module's lines are docstrings and comments, so it is
# longer than `pylint` likes.
# pylint: disable=too-many-lines

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from pysolidcraft import JSON, PySolidCraft

# A point in the XY plane, `(x, y)`.
Point: TypeAlias = tuple[float, float]

# One RS-274 command: its words, in order, keyed by letter (e.g.
# `{"G": 1, "X": 10.0}`).  The key `comment` holds a comment's text.
RS274: TypeAlias = dict[str, float | int | str]

# Lengths shorter than this are treated as zero.
EPSILON: float = 1e-9

# Where two neighboring segments meet, a crossing found closer than
# this to the point they share is that point (rounding moves it a
# little, most where a line or arc only touches an arc).
TOUCH: float = 1e-6


# Class `SCLine`:
@dataclass(frozen=True, slots=True)
class SCLine:
    """A straight line segment in the XY plane.

    Attributes:
    * `start` (`Point`): Where the line starts.
    * `end` (`Point`): Where the line ends.

    Constructor:
    * `SCLine(start, end)`
    """

    # Constructor arguments:
    start: Point = field(init=True)
    end: Point = field(init=True)

    # Method `SCLine.length()`:
    def length(self) -> float:
        """Return the line's length.

        Returns:
        * (`float`): The distance from `start` to `end`.
        """
        return math.dist(self.start, self.end)


# Class `SCArc`:
@dataclass(frozen=True, slots=True)
class SCArc:
    """A circular arc in the XY plane.

    Attributes:
    * `start` (`Point`): Where the arc starts.
    * `end` (`Point`): Where the arc ends.
    * `center` (`Point`): The arc's center.
    * `radius` (`float`): The arc's radius.
    * `sweep` (`float`):
      The angle swept from `start` to `end` (radians): positive is
      counter-clockwise, negative is clockwise.

    Constructor:
    * `SCArc(start, end, center, radius, sweep)`
    """

    # Constructor arguments:
    start: Point = field(init=True)
    end: Point = field(init=True)
    center: Point = field(init=True)
    radius: float = field(init=True)
    sweep: float = field(init=True)

    # Method `SCArc.length()`:
    def length(self) -> float:
        """Return the arc's length.

        Returns:
        * (`float`): The distance along the arc from `start` to `end`.
        """
        return abs(self.sweep) * self.radius

    # Method `SCArc.contains()`:
    def contains(self, point: Point) -> bool:
        """Return whether a point on the arc's circle is on the arc.

        Arguments:
        * `point` (`Point`): A point on the circle.

        Returns:
        * (`bool`): True when it lies between `start` and `end` (or
          within `TOUCH` of either).
        """
        # Measure the point's angle from `start`, the way `sweep` goes.
        start: float = math.atan2(
            self.start[1] - self.center[1], self.start[0] - self.center[0]
        )
        angle: float = math.atan2(
            point[1] - self.center[1], point[0] - self.center[0]
        )
        turned: float = math.copysign(1.0, self.sweep) * (angle - start)
        turned %= 2.0 * math.pi
        slack: float = TOUCH / self.radius
        return turned <= abs(self.sweep) + slack or (
            turned >= 2.0 * math.pi - slack
        )


# One piece of an outline.
SCSegment: TypeAlias = SCLine | SCArc


# Class `SCCorner`:
@dataclass(frozen=True, slots=True)
class SCCorner:
    """A corner of an `SCRoundPoly`.

    Attributes:
    * `x` (`float`): The X of the (sharp) corner.
    * `y` (`float`): The Y of the (sharp) corner.
    * `radius` (`float`):
      The radius the corner is rounded to (0 for a sharp corner).

    Constructor:
    * `SCCorner(x, y, radius)`
    """

    # Constructor arguments:
    x: float = field(init=True)
    y: float = field(init=True)
    radius: float = field(init=True, default=0.0)

    # Method `SCCorner.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the radius.

        Raises:
        * `ValueError`: If `radius` is negative.
        """
        if self.radius < 0.0:
            raise ValueError(f"{self.radius=} must not be negative")


# Class `SCRoundPoly`:
@dataclass(slots=True)
class SCRoundPoly:
    """A polygon in the XY plane with a radius at each corner.

    Each corner is rounded by an arc tangent to its two edges, so the
    outline is a closed loop of lines and arcs (`segments`).  The
    corners may go around either way, and a polygon need not be convex:
    a corner that turns against the others is rounded the other way.
    The outline must not cross or touch itself.

    Attributes:
    * `name` (`str`): The polygon's name (used for its sketch).
    * `corners` (`Sequence[SCCorner]`):
      The corners, in order around the polygon (stored as a tuple).
    * `segments` (`tuple[SCSegment, ...]`):
      The outline, starting with the edge that leaves the first corner
      and ending with the first corner's arc.  An edge used up entirely
      by its corners' arcs has no line, and a sharp corner has no arc.
    * `signed_area` (`float`):
      The area of the sharp polygon: positive when the corners go
      counter-clockwise, negative when they go clockwise.

    Constructor:
    * `SCRoundPoly(name, corners)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    corners: Sequence[SCCorner] = field(init=True)

    # Attributes set by `__post_init__()` (alphabetized):
    segments: tuple[SCSegment, ...] = field(init=False, default=())
    signed_area: float = field(init=False, default=0.0)

    # Method `SCRoundPoly.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the corners; compute `segments` and `signed_area`.

        Raises:
        * `ValueError`:
          If there are fewer than 3 corners, two corners are in the same
          place, a corner is straight or turns back on itself, two
          corners' arcs do not fit on the edge between them, or the
          outline crosses or touches itself.
        """
        # Validate the corners.
        corners: tuple[SCCorner, ...] = tuple(self.corners)
        self.corners = corners
        count: int = len(corners)
        if count < 3:
            raise ValueError(f"{self.name}: {count} corners; 3 are needed")

        # The shoelace formula gives the area and the direction.
        self.signed_area = 0.5 * sum(
            corner.x * corners[(index + 1) % count].y
            - corners[(index + 1) % count].x * corner.y
            for index, corner in enumerate(corners)
        )

        # Round each corner, finding where its arc meets its two edges.
        index: int
        arcs: list[SCArc | None] = []
        entries: list[Point] = []
        exits: list[Point] = []
        for index in range(count):
            arc: SCArc | None
            entry: Point
            exit_: Point
            arc, entry, exit_ = self._round(index)
            arcs.append(arc)
            entries.append(entry)
            exits.append(exit_)

        # Join each corner's arc to the next one's with the line left
        # over from their edge, checking that the arcs fit on it.  The
        # outline starts with the edge leaving the first corner, so it
        # ends with the first corner's arc.
        segments: list[SCSegment] = []
        for index in range(count):
            following: int = (index + 1) % count
            edge: float = math.dist(
                (corners[index].x, corners[index].y),
                (corners[following].x, corners[following].y),
            )
            used: float = math.dist(
                (corners[index].x, corners[index].y), exits[index]
            ) + math.dist(
                entries[following],
                (corners[following].x, corners[following].y),
            )
            if used > edge + EPSILON:
                raise ValueError(
                    f"{self.name}: the arcs of corners {index} and "
                    f"{following} need {used:g} of an edge {edge:g} long"
                )
            if edge - used > EPSILON:
                segments.append(SCLine(exits[index], entries[following]))
            following_arc: SCArc | None = arcs[following]
            if following_arc is not None:
                segments.append(following_arc)
        self.segments = tuple(segments)
        self._check_crossings()

    # Method `SCRoundPoly._round()`:
    def _round(self, index: int) -> tuple[SCArc | None, Point, Point]:
        """Round one corner.

        Arguments:
        * `index` (`int`): The corner's index in `corners`.

        Returns:
        * (`SCArc | None`): The corner's arc (`None` when it is sharp).
        * (`Point`): Where the outline arrives at the corner (the arc's
          start, or the corner itself when it is sharp).
        * (`Point`): Where the outline leaves the corner.
        """
        # Find the directions of the edges arriving and leaving.
        corner: SCCorner = self.corners[index]
        arriving: Point
        leaving: Point
        turn: float
        arriving, leaving, turn = self._turn(index)

        # A sharp corner has no arc.
        radius: float = corner.radius
        if radius == 0.0:
            return None, (corner.x, corner.y), (corner.x, corner.y)

        # The arc meets each edge `tangent` from the corner, and its
        # center is `radius` from the arriving edge, on the inside of
        # the turn.
        tangent: float = radius * math.tan(abs(turn) / 2.0)
        entry: Point = (
            corner.x - arriving[0] * tangent,
            corner.y - arriving[1] * tangent,
        )
        exit_: Point = (
            corner.x + leaving[0] * tangent,
            corner.y + leaving[1] * tangent,
        )
        side: float = math.copysign(radius, turn)
        center: Point = (
            entry[0] - arriving[1] * side,
            entry[1] + arriving[0] * side,
        )
        return SCArc(entry, exit_, center, radius, turn), entry, exit_

    # Method `SCRoundPoly._turn()`:
    def _turn(self, index: int) -> tuple[Point, Point, float]:
        """Return how the outline turns at a (sharp) corner.

        Arguments:
        * `index` (`int`): The corner's index in `corners`.

        Returns:
        * (`Point`): The unit direction of the edge arriving.
        * (`Point`): The unit direction of the edge leaving.
        * (`float`): The angle turned (radians), positive to the left
          (counter-clockwise).

        Raises:
        * `ValueError`:
          If the corner is in the same place as a neighbor, is straight,
          or turns back on itself.
        """
        # Find the directions of the edges arriving and leaving.
        count: int = len(self.corners)
        previous: SCCorner = self.corners[index - 1]
        corner: SCCorner = self.corners[index]
        following: SCCorner = self.corners[(index + 1) % count]
        arriving: Point = _unit(corner.x - previous.x, corner.y - previous.y)
        leaving: Point = _unit(following.x - corner.x, following.y - corner.y)
        if arriving == (0.0, 0.0) or leaving == (0.0, 0.0):
            raise ValueError(
                f"{self.name}: corner {index} is in the same place as "
                "a neighbor"
            )

        # Measure the turn, which must be neither none nor a reversal.
        turn: float = math.atan2(
            _cross(arriving, leaving), _dot(arriving, leaving)
        )
        if abs(turn) < EPSILON:
            raise ValueError(f"{self.name}: corner {index} is straight")
        if math.pi - abs(turn) < EPSILON:
            raise ValueError(
                f"{self.name}: corner {index} turns back on itself"
            )
        return arriving, leaving, turn

    # Method `SCRoundPoly._check_crossings()`:
    def _check_crossings(self) -> None:
        """Check that no two segments of the outline cross or touch.

        Neighboring segments meet only at the point they share.

        Raises:
        * `ValueError`: If two segments cross or touch.
        """
        segments: tuple[SCSegment, ...] = self.segments
        count: int = len(segments)
        first: int
        second: int
        for first in range(count):
            for second in range(first + 1, count):
                # Neighbors (and the last and first) share a point.
                shared: list[Point] = []
                if second == first + 1:
                    shared.append(segments[first].end)
                if first == 0 and second == count - 1:
                    shared.append(segments[first].start)

                # Any other meeting is a crossing.
                point: Point
                for point in _meet(segments[first], segments[second]):
                    if all(math.dist(point, end) > TOUCH for end in shared):
                        raise ValueError(
                            f"{self.name}: segments {first} and {second} "
                            f"cross at ({point[0]:g}, {point[1]:g})"
                        )

    # Method `SCRoundPoly.is_ccw()`:
    def is_ccw(self) -> bool:
        """Return whether the corners go counter-clockwise.

        Returns:
        * (`bool`): True when the corners go counter-clockwise.
        """
        return self.signed_area > 0.0

    # Method `SCRoundPoly.reversed()`:
    def reversed(self) -> "SCRoundPoly":
        """Return the same polygon going around the other way.

        The first corner stays first.

        Returns:
        * (`SCRoundPoly`): The reversed polygon, with the same name.
        """
        corners: Sequence[SCCorner] = self.corners
        return SCRoundPoly(self.name, (corners[0], *corners[:0:-1]))

    # Method `SCRoundPoly.offset()`:
    def offset(self, distance: float) -> "SCRoundPoly":
        """Return the outline moved outward (or inward) by a distance.

        This is the path a tool's center follows to cut along the
        outline from outside it (or from inside it): each edge moves
        `distance` away from the polygon, a corner that bulges outward
        grows its radius by `distance`, and one that bulges inward
        shrinks its radius by `distance`.  A corner too tight for that
        becomes sharp, so the cut leaves it rounded to `distance`
        instead.

        Arguments:
        * `distance` (`float`): How far out to move (negative is in).

        Returns:
        * (`SCRoundPoly`): The moved outline, going around the same way,
          named after this one.

        Raises:
        * `ValueError`:
          If the moved outline cannot be made, such as when moving in
          collapses an edge or makes the outline cross itself.
        """
        # Outward is to the right going counter-clockwise, and to the
        # left going clockwise.
        sense: float = 1.0 if self.is_ccw() else -1.0
        corners: list[SCCorner] = []
        index: int
        corner: SCCorner
        for index, corner in enumerate(self.corners):
            arriving: Point
            leaving: Point
            turn: float
            arriving, leaving, turn = self._turn(index)

            # The moved corner is where the two moved edges meet.
            before: Point = (sense * arriving[1], -sense * arriving[0])
            after: Point = (sense * leaving[1], -sense * leaving[0])
            scale: float = distance / (1.0 + _dot(before, after))
            radius: float = corner.radius + (
                distance if turn * sense > 0.0 else -distance
            )
            corners.append(
                SCCorner(
                    corner.x + (before[0] + after[0]) * scale,
                    corner.y + (before[1] + after[1]) * scale,
                    max(radius, 0.0),
                )
            )
        name: str = f"{self.name} offset {distance:g}"
        self._check_moved(name, corners)
        return SCRoundPoly(name, corners)

    # Method `SCRoundPoly._check_moved()`:
    def _check_moved(self, name: str, moved: Sequence[SCCorner]) -> None:
        """Check that moving the corners turned no edge around.

        Moving in too far turns an edge around, which can still make a
        valid polygon (inside out), so it is refused here.

        Arguments:
        * `name` (`str`): The moved polygon's name.
        * `moved` (`Sequence[SCCorner]`): The moved corners, in order.

        Raises:
        * `ValueError`: If an edge points the other way once moved.
        """
        count: int = len(moved)
        index: int
        for index in range(count):
            following: int = (index + 1) % count
            old: Point = (
                self.corners[following].x - self.corners[index].x,
                self.corners[following].y - self.corners[index].y,
            )
            new: Point = (
                moved[following].x - moved[index].x,
                moved[following].y - moved[index].y,
            )
            if _dot(old, new) <= 0.0:
                raise ValueError(
                    f"{name}: the edge from corner {index} collapses"
                )

    # Method `SCRoundPoly.sketch()`:
    def sketch(
        self, solidcraft: "PySolidCraft", mm_per_unit: float = 1.0
    ) -> list[str]:
        """Draw the outline into SolidCraft's open sketch.

        The caller creates the sketch first (`sketch.create`) and
        finishes it afterwards (`sketch.finish`).  Each segment's ends
        are sent exactly as computed, so SolidCraft joins them into one
        closed profile.

        Arguments:
        * `solidcraft` (`PySolidCraft`): Where to draw it.
        * `mm_per_unit` (`float`):
          SolidCraft's sketch coordinates are millimeters, whatever the
          design's units, so this scales the outline's units to them
          (25.4 for inches).

        Returns:
        * (`list[str]`): The ids of the curves drawn, in order.
        """

        # Function `mm()`:
        def mm(point: Point) -> Point:
            """Return a point in millimeters.

            Arguments:
            * `point` (`Point`): The point in the outline's units.

            Returns:
            * (`Point`): The point in millimeters.
            """
            return point[0] * mm_per_unit, point[1] * mm_per_unit

        curves: list[str] = []
        segment: SCSegment
        for segment in self.segments:
            # SolidCraft's arcs go counter-clockwise from `start` to
            # `end`, so a clockwise arc is drawn from its end.
            result: JSON
            if isinstance(segment, SCLine):
                result = solidcraft.sketch.line(
                    points=[mm(segment.start), mm(segment.end)]
                )
            else:
                ends: tuple[Point, Point] = (segment.start, segment.end)
                if segment.sweep < 0.0:
                    ends = (segment.end, segment.start)
                result = solidcraft.sketch.arc_center_point(
                    center=mm(segment.center),
                    start=mm(ends[0]),
                    end=mm(ends[1]),
                )
            assert isinstance(result, dict)
            ids: JSON = result["curves"]
            assert isinstance(ids, list)
            curves += [str(curve) for curve in ids]
        return curves


# Function `_unit()`:
def _unit(dx: float, dy: float) -> Point:
    """Return a vector scaled to length 1.

    Arguments:
    * `dx` (`float`): The vector's X.
    * `dy` (`float`): The vector's Y.

    Returns:
    * (`Point`): The unit vector, or `(0.0, 0.0)` for a vector too short
      to have a direction.
    """
    length: float = math.hypot(dx, dy)
    if length < EPSILON:
        return 0.0, 0.0
    return dx / length, dy / length


# Function `_dot()`:
def _dot(a: Point, b: Point) -> float:
    """Return the dot product of two vectors.

    Arguments:
    * `a` (`Point`): One vector.
    * `b` (`Point`): The other.

    Returns:
    * (`float`): The dot product.
    """
    return a[0] * b[0] + a[1] * b[1]


# Function `_cross()`:
def _cross(a: Point, b: Point) -> float:
    """Return the cross product of two vectors (its Z).

    Arguments:
    * `a` (`Point`): One vector.
    * `b` (`Point`): The other.

    Returns:
    * (`float`): Positive when `b` is to the left of `a`.
    """
    return a[0] * b[1] - a[1] * b[0]


# Function `_meet()`:
def _meet(a: SCSegment, b: SCSegment) -> list[Point]:
    """Return where two segments meet.

    Arguments:
    * `a` (`SCSegment`): One segment.
    * `b` (`SCSegment`): The other.

    Returns:
    * (`list[Point]`): The points where they cross or touch (for
      segments that overlap, the ends of the overlap).
    """
    if isinstance(a, SCLine):
        if isinstance(b, SCLine):
            return _meet_lines(a, b)
        return _meet_line_arc(a, b)
    if isinstance(b, SCLine):
        return _meet_line_arc(b, a)
    return _meet_arcs(a, b)


# Function `_meet_lines()`:
def _meet_lines(a: SCLine, b: SCLine) -> list[Point]:
    """Return where two lines meet.

    Arguments:
    * `a` (`SCLine`): One line.
    * `b` (`SCLine`): The other.

    Returns:
    * (`list[Point]`): The crossing, the ends of their overlap, or
      nothing.
    """
    # Each line is `start + t * direction`, for `t` from 0 to 1.
    along: Point = (a.end[0] - a.start[0], a.end[1] - a.start[1])
    other: Point = (b.end[0] - b.start[0], b.end[1] - b.start[1])
    gap: Point = (b.start[0] - a.start[0], b.start[1] - a.start[1])
    lengths: float = a.length() * b.length()
    slack: float = TOUCH / a.length()
    denominator: float = _cross(along, other)

    # Parallel lines meet only when they are on the same line, where
    # they overlap.
    if abs(denominator) <= EPSILON * lengths:
        if abs(_cross(gap, along)) > TOUCH * a.length():
            return []
        squared: float = _dot(along, along)
        ts: tuple[float, float] = (
            _dot(gap, along) / squared,
            _dot((gap[0] + other[0], gap[1] + other[1]), along) / squared,
        )
        low: float = max(0.0, min(ts))
        high: float = min(1.0, max(ts))
        if low > high + slack:
            return []
        return [
            (a.start[0] + along[0] * t, a.start[1] + along[1] * t)
            for t in (low, high)
        ]

    # Other lines meet where they cross, if both reach it.
    t: float = _cross(gap, other) / denominator
    u: float = _cross(gap, along) / denominator
    if not -slack <= t <= 1.0 + slack:
        return []
    if not -TOUCH / b.length() <= u <= 1.0 + TOUCH / b.length():
        return []
    return [(a.start[0] + along[0] * t, a.start[1] + along[1] * t)]


# Function `_meet_line_arc()`:
def _meet_line_arc(line: SCLine, arc: SCArc) -> list[Point]:
    """Return where a line and an arc meet.

    Arguments:
    * `line` (`SCLine`): The line.
    * `arc` (`SCArc`): The arc.

    Returns:
    * (`list[Point]`): The points where they cross or touch.
    """
    # Find the point of the line's extension nearest the center, and
    # how far the circle reaches along the line from there.
    length: float = line.length()
    along: Point = (
        (line.end[0] - line.start[0]) / length,
        (line.end[1] - line.start[1]) / length,
    )
    gap: Point = (arc.center[0] - line.start[0], arc.center[1] - line.start[1])
    nearest: float = _dot(gap, along)
    distance: float = abs(_cross(along, gap))
    if distance > arc.radius + EPSILON:
        return []
    reach: float = 0.0
    if arc.radius - distance > EPSILON:
        reach = math.sqrt(arc.radius**2 - distance**2)

    # Keep the points on both the line and the arc.
    points: list[Point] = []
    offset: float
    for offset in (nearest - reach, nearest + reach)[: 2 if reach else 1]:
        if -TOUCH <= offset <= length + TOUCH:
            point: Point = (
                line.start[0] + along[0] * offset,
                line.start[1] + along[1] * offset,
            )
            if arc.contains(point):
                points.append(point)
    return points


# Function `_meet_arcs()`:
def _meet_arcs(a: SCArc, b: SCArc) -> list[Point]:
    """Return where two arcs meet.

    Arguments:
    * `a` (`SCArc`): One arc.
    * `b` (`SCArc`): The other.

    Returns:
    * (`list[Point]`): The points where they cross or touch (for arcs
      of the same circle, the ends of each that lie on the other).
    """
    # Arcs of the same circle meet where they overlap; concentric arcs
    # of different circles never meet.
    apart: float = math.dist(a.center, b.center)
    if apart < EPSILON:
        if abs(a.radius - b.radius) >= EPSILON:
            return []
        ends: list[Point] = [a.start, a.end, b.start, b.end]
        return [end for end in ends if a.contains(end) and b.contains(end)]

    # Circles too far apart (or one inside the other) never meet;
    # otherwise they meet on the line between them, `along` from `a`'s
    # center, and `across` either side of it (none when they touch).
    if apart > a.radius + b.radius + EPSILON:
        return []
    if apart < abs(a.radius - b.radius) - EPSILON:
        return []
    along: float = (a.radius**2 - b.radius**2 + apart**2) / (2.0 * apart)
    across: float = 0.0
    if (
        abs(apart - (a.radius + b.radius)) > EPSILON
        and abs(apart - abs(a.radius - b.radius)) > EPSILON
    ):
        across = math.sqrt(max(a.radius**2 - along**2, 0.0))
    direction: Point = (
        (b.center[0] - a.center[0]) / apart,
        (b.center[1] - a.center[1]) / apart,
    )
    middle: Point = (
        a.center[0] + direction[0] * along,
        a.center[1] + direction[1] * along,
    )

    # Keep the points on both arcs.
    points: list[Point] = []
    side: float
    for side in (-across, across)[: 2 if across else 1]:
        point: Point = (
            middle[0] - direction[1] * side,
            middle[1] + direction[0] * side,
        )
        if a.contains(point) and b.contains(point):
            points.append(point)
    return points


# Function `_split()`:
def _split(segment: SCSegment) -> tuple[SCSegment, SCSegment]:
    """Split a segment in half.

    Arguments:
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`SCSegment`): Its first half.
    * (`SCSegment`): Its second half.
    """
    if isinstance(segment, SCLine):
        middle: Point = (
            (segment.start[0] + segment.end[0]) / 2.0,
            (segment.start[1] + segment.end[1]) / 2.0,
        )
        return SCLine(segment.start, middle), SCLine(middle, segment.end)
    center: Point = segment.center
    angle: float = (
        math.atan2(segment.start[1] - center[1], segment.start[0] - center[0])
        + segment.sweep / 2.0
    )
    middle = (
        center[0] + segment.radius * math.cos(angle),
        center[1] + segment.radius * math.sin(angle),
    )
    half: float = segment.sweep / 2.0
    return (
        SCArc(segment.start, middle, center, segment.radius, half),
        SCArc(middle, segment.end, center, segment.radius, half),
    )


# Function `_tangent()`:
def _tangent(segment: SCSegment) -> Point:
    """Return the direction a segment starts in.

    Arguments:
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`Point`): The unit direction at its start.
    """
    if isinstance(segment, SCLine):
        return _unit(
            segment.end[0] - segment.start[0],
            segment.end[1] - segment.start[1],
        )
    out: Point = _unit(
        segment.start[0] - segment.center[0],
        segment.start[1] - segment.center[1],
    )
    turn: float = math.copysign(1.0, segment.sweep)
    return -out[1] * turn, out[0] * turn


# Function `_leads()`:
def _leads(
    path: SCRoundPoly, radius: float
) -> tuple[SCArc, list[SCSegment], SCArc]:
    """Plan the lead-in, the loop and the lead-out around a path.

    The loop starts and ends in the middle of the path's longest
    segment, where the path is smooth.  The lead-in and lead-out are
    the two halves of a circle of `radius` touching the path there,
    on its left, both counter-clockwise.

    Arguments:
    * `path` (`SCRoundPoly`): The path the tool's center follows.
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
    first, second = _split(segments[longest])
    loop: list[SCSegment] = [
        second,
        *segments[longest + 1 :],
        *segments[:longest],
        first,
    ]

    # The circle touches the path at the loop's start, on its left.
    start: Point = second.start
    along: Point = _tangent(second)
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
    path: SCRoundPoly, leads: tuple[SCArc, SCArc], start: Point
) -> None:
    """Check that the leads meet the path only at `start`.

    Arguments:
    * `path` (`SCRoundPoly`): The path the tool's center follows.
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
            for point in _meet(lead, segment):
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
    * `commands` (`list[RS274]`): The program so far.
    * `minutes` (`float`):
      The time the moves so far take, at `rapid_speed` and
      `work_speed` (not counting acceleration).
    * `position` (`tuple[float | None, float | None, float | None]`):
      Where the tool was last sent (X, Y, Z); `None` until that axis
      first moves.

    Constructor:
    * `SCCNC(name, z_top, z_safe, clearance, tool_diameter,
      rapid_speed, work_speed, spindle_rpm)`
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
          `clearance` is negative, or a size or speed is not positive.
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
    def arc(self, arc: SCArc) -> None:
        """Cut along an XY arc at `work_speed` (`G2` or `G3`).

        The tool must already be at the arc's start.

        Arguments:
        * `arc` (`SCArc`): The arc.
        """
        self._move(
            3 if arc.sweep > 0.0 else 2, (arc.end[0], arc.end[1], None), arc
        )

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
        # Validate the depths.
        if bottom >= self.z_top:
            raise ValueError(f"{bottom=} must be below {self.z_top=}")
        if step <= 0.0:
            raise ValueError(f"{step=} must be positive")

        # Move the tool's center off the outline by its radius, and go
        # the climb milling way around.
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
        lead_in, loop, lead_out = _leads(path, radius)
        self.rapid(z=self.z_safe)
        self.rapid(x=lead_in.start[0], y=lead_in.start[1])
        self.rapid(z=self.z_top + self.clearance)

        # At each depth, go down, in, once around, and out.
        passes: int = math.ceil((self.z_top - bottom) / step - EPSILON)
        index: int
        for index in range(1, passes + 1):
            self.linear(z=self.z_top - (self.z_top - bottom) * index / passes)
            segment: SCSegment
            for segment in [lead_in, *loop, lead_out]:
                if isinstance(segment, SCLine):
                    self.linear(x=segment.end[0], y=segment.end[1])
                else:
                    self.arc(segment)
        self.rapid(z=self.z_safe)
        return path

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
