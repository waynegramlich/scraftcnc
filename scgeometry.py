"""Lines, arcs and rounded polygons in the XY plane.

`SCRoundPoly` is a polygon whose corners each have their own radius.
It computes its own outline as straight lines (`SCLine`) and tangent
arcs (`SCArc`), so the same geometry can be drawn into a SolidCraft
sketch (`SCRoundPoly.sketch()`) and followed by a tool.

`SCLoop` is any closed loop of lines and arcs, such as the paths that
`inset()` finds inside a region: the classic offset, which moves every
segment in, finds where the moved segments cross, drops the pieces
that came too close to the region's edge, and joins the rest into
loops (one region can become several).

This module only uses `scraftpybind` through the `SolidCraftPyBind`
that is handed to `SCRoundPoly.sketch()`, so it imports it only for
type checking.
"""

# Most of this module's lines are docstrings and comments, so it is
# longer than `pylint` likes.
# pylint: disable=too-many-lines

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from scraftpybind import JSON, SolidCraftPyBind

# A point in the XY plane, `(x, y)`.
Point: TypeAlias = tuple[float, float]

# Lengths shorter than this are treated as zero.
EPSILON: float = 1e-9

# Where two neighboring segments meet, a crossing found closer than
# this to the point they share is that point (rounding moves it a
# little, most where a line or arc only touches an arc).
TOUCH: float = 1e-6

# Where the pieces of an offset are joined, ends closer than this are
# the same point (crossings found near tangents are the least exact).
JOIN: float = 1e-5

# Segments meeting at an angle smaller than this (radians) meet
# smoothly (tangent), with no corner between them.
ANGLE: float = 1e-6


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
        arriving: Point = unit(corner.x - previous.x, corner.y - previous.y)
        leaving: Point = unit(following.x - corner.x, following.y - corner.y)
        if arriving == (0.0, 0.0) or leaving == (0.0, 0.0):
            raise ValueError(
                f"{self.name}: corner {index} is in the same place as "
                "a neighbor"
            )

        # Measure the turn, which must be neither none nor a reversal.
        turn: float = math.atan2(
            cross(arriving, leaving), dot(arriving, leaving)
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
                for point in meet(segments[first], segments[second]):
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
            scale: float = distance / (1.0 + dot(before, after))
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
            if dot(old, new) <= 0.0:
                raise ValueError(
                    f"{name}: the edge from corner {index} collapses"
                )

    # Method `SCRoundPoly.sketch()`:
    def sketch(
        self, solidcraft: "SolidCraftPyBind", mm_per_unit: float = 1.0
    ) -> list[str]:
        """Draw the outline into SolidCraft's open sketch.

        The caller creates the sketch first (`sketch.create`) and
        finishes it afterwards (`sketch.finish`).  Each segment's ends
        are sent exactly as computed, so SolidCraft joins them into one
        closed profile.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): Where to draw it.
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


# Function `unit()`:
def unit(dx: float, dy: float) -> Point:
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


# Function `dot()`:
def dot(a: Point, b: Point) -> float:
    """Return the dot product of two vectors.

    Arguments:
    * `a` (`Point`): One vector.
    * `b` (`Point`): The other.

    Returns:
    * (`float`): The dot product.
    """
    return a[0] * b[0] + a[1] * b[1]


# Function `cross()`:
def cross(a: Point, b: Point) -> float:
    """Return the cross product of two vectors (its Z).

    Arguments:
    * `a` (`Point`): One vector.
    * `b` (`Point`): The other.

    Returns:
    * (`float`): Positive when `b` is to the left of `a`.
    """
    return a[0] * b[1] - a[1] * b[0]


# Function `meet()`:
def meet(a: SCSegment, b: SCSegment) -> list[Point]:
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
            return meet_lines(a, b)
        return meet_line_arc(a, b)
    if isinstance(b, SCLine):
        return meet_line_arc(b, a)
    return meet_arcs(a, b)


# Function `meet_lines()`:
def meet_lines(a: SCLine, b: SCLine) -> list[Point]:
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
    denominator: float = cross(along, other)

    # Parallel lines meet only when they are on the same line, where
    # they overlap.
    if abs(denominator) <= EPSILON * lengths:
        if abs(cross(gap, along)) > TOUCH * a.length():
            return []
        squared: float = dot(along, along)
        ts: tuple[float, float] = (
            dot(gap, along) / squared,
            dot((gap[0] + other[0], gap[1] + other[1]), along) / squared,
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
    t: float = cross(gap, other) / denominator
    u: float = cross(gap, along) / denominator
    if not -slack <= t <= 1.0 + slack:
        return []
    if not -TOUCH / b.length() <= u <= 1.0 + TOUCH / b.length():
        return []
    return [(a.start[0] + along[0] * t, a.start[1] + along[1] * t)]


# Function `meet_line_arc()`:
def meet_line_arc(line: SCLine, arc: SCArc) -> list[Point]:
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
    nearest: float = dot(gap, along)
    distance: float = abs(cross(along, gap))
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


# Function `meet_arcs()`:
def meet_arcs(a: SCArc, b: SCArc) -> list[Point]:
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


# Function `halves()`:
def halves(segment: SCSegment) -> tuple[SCSegment, SCSegment]:
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


# Function `start_tangent()`:
def start_tangent(segment: SCSegment) -> Point:
    """Return the direction a segment starts in.

    Arguments:
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`Point`): The unit direction at its start.
    """
    if isinstance(segment, SCLine):
        return unit(
            segment.end[0] - segment.start[0],
            segment.end[1] - segment.start[1],
        )
    out: Point = unit(
        segment.start[0] - segment.center[0],
        segment.start[1] - segment.center[1],
    )
    turn: float = math.copysign(1.0, segment.sweep)
    return -out[1] * turn, out[0] * turn


# Function `reverse_segment()`:
def reverse_segment(segment: SCSegment) -> SCSegment:
    """Return a segment going the other way.

    Arguments:
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`SCSegment`): The same segment from its end to its start.
    """
    if isinstance(segment, SCLine):
        return SCLine(segment.end, segment.start)
    return SCArc(
        segment.end,
        segment.start,
        segment.center,
        segment.radius,
        -segment.sweep,
    )


# Function `end_tangent()`:
def end_tangent(segment: SCSegment) -> Point:
    """Return the direction a segment ends in.

    Arguments:
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`Point`): The unit direction at its end.
    """
    back: Point = start_tangent(reverse_segment(segment))
    return -back[0], -back[1]


# Function `left()`:
def left(direction: Point) -> Point:
    """Return a direction turned a quarter turn to the left.

    Arguments:
    * `direction` (`Point`): The direction.

    Returns:
    * (`Point`): It turned 90 degrees counter-clockwise.
    """
    return -direction[1], direction[0]


# Function `turn_between()`:
def turn_between(before: Point, after: Point) -> float:
    """Return the angle turned from one direction to another.

    Arguments:
    * `before` (`Point`): The first direction.
    * `after` (`Point`): The second direction.

    Returns:
    * (`float`): The angle (radians, from -pi to pi), positive to the
      left.
    """
    return math.atan2(cross(before, after), dot(before, after))


# Function `point_at()`:
def point_at(segment: SCSegment, fraction: float) -> Point:
    """Return the point a fraction of the way along a segment.

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `fraction` (`float`): 0 for its start, 1 for its end.

    Returns:
    * (`Point`): The point.
    """
    if isinstance(segment, SCLine):
        return (
            segment.start[0] + (segment.end[0] - segment.start[0]) * fraction,
            segment.start[1] + (segment.end[1] - segment.start[1]) * fraction,
        )
    angle: float = (
        math.atan2(
            segment.start[1] - segment.center[1],
            segment.start[0] - segment.center[0],
        )
        + segment.sweep * fraction
    )
    return (
        segment.center[0] + segment.radius * math.cos(angle),
        segment.center[1] + segment.radius * math.sin(angle),
    )


# Function `fraction_of()`:
def fraction_of(segment: SCSegment, point: Point) -> float:
    """Return how far along a segment a point on it is.

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `point` (`Point`): A point on the segment (or its circle).

    Returns:
    * (`float`): 0 at its start and 1 at its end (a little outside
      that range for a point just beyond an end).
    """
    if isinstance(segment, SCLine):
        along: Point = (
            segment.end[0] - segment.start[0],
            segment.end[1] - segment.start[1],
        )
        gap: Point = (point[0] - segment.start[0], point[1] - segment.start[1])
        return dot(gap, along) / dot(along, along)

    # Measure the angle the way the arc goes; an angle past the arc is
    # taken as before its start when it is nearer that end.
    start: float = math.atan2(
        segment.start[1] - segment.center[1],
        segment.start[0] - segment.center[0],
    )
    angle: float = math.atan2(
        point[1] - segment.center[1], point[0] - segment.center[0]
    )
    sweep: float = abs(segment.sweep)
    turned: float = math.copysign(1.0, segment.sweep) * (angle - start)
    turned %= 2.0 * math.pi
    if turned > sweep + (2.0 * math.pi - sweep) / 2.0:
        turned -= 2.0 * math.pi
    return turned / sweep


# Function `piece_of()`:
def piece_of(
    segment: SCSegment, ends: tuple[Point, Point], fractions: Point
) -> SCSegment:
    """Return the piece of a segment between two of its points.

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `ends` (`tuple[Point, Point]`): The piece's start and end.
    * `fractions` (`Point`): How far along `segment` they are.

    Returns:
    * (`SCSegment`): The piece.
    """
    if isinstance(segment, SCLine):
        return SCLine(ends[0], ends[1])
    return SCArc(
        ends[0],
        ends[1],
        segment.center,
        segment.radius,
        segment.sweep * (fractions[1] - fractions[0]),
    )


# Function `split_at()`:
def split_at(segment: SCSegment, points: Sequence[Point]) -> list[SCSegment]:
    """Split a segment at points on it.

    Points within `TOUCH` of an end, or of another point, are left out.

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `points` (`Sequence[Point]`): Points on the segment.

    Returns:
    * (`list[SCSegment]`): The pieces, in order.
    """
    # Find where along the segment each point is.
    length: float = segment.length()
    cuts: list[tuple[float, Point]] = []
    point: Point
    for point in points:
        fraction: float = fraction_of(segment, point)
        if TOUCH < fraction * length < length - TOUCH:
            cuts.append((fraction, point))
    cuts.sort()

    # Cut it there.
    pieces: list[SCSegment] = []
    done: float = 0.0
    start: Point = segment.start
    for fraction, point in cuts:
        if (fraction - done) * length > TOUCH:
            pieces.append(piece_of(segment, (start, point), (done, fraction)))
            done, start = fraction, point
    pieces.append(piece_of(segment, (start, segment.end), (done, 1.0)))
    return pieces


# Function `distance_to()`:
def distance_to(point: Point, segment: SCSegment) -> float:
    """Return the distance from a point to a segment.

    Arguments:
    * `point` (`Point`): The point.
    * `segment` (`SCSegment`): The segment.

    Returns:
    * (`float`): The distance.
    """
    if isinstance(segment, SCLine):
        fraction: float = min(max(fraction_of(segment, point), 0.0), 1.0)
        return math.dist(point, point_at(segment, fraction))
    apart: float = math.dist(point, segment.center)
    if apart < EPSILON:
        return segment.radius
    nearest: Point = (
        segment.center[0]
        + (point[0] - segment.center[0]) * segment.radius / apart,
        segment.center[1]
        + (point[1] - segment.center[1]) * segment.radius / apart,
    )
    if segment.contains(nearest):
        return abs(apart - segment.radius)
    return min(math.dist(point, segment.start), math.dist(point, segment.end))


# Class `SCLoop`:
@dataclass(frozen=True, slots=True)
class SCLoop:
    """A closed loop of lines and arcs in the XY plane.

    Each segment starts where the one before it ends, and the last ends
    where the first starts.  Unlike an `SCRoundPoly`, two segments may
    meet at an angle anywhere (such as two arcs meeting at a point).

    Attributes:
    * `name` (`str`): The loop's name.
    * `segments` (`tuple[SCSegment, ...]`): The segments, in order.

    Constructor:
    * `SCLoop(name, segments)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    segments: tuple[SCSegment, ...] = field(init=True)

    # Method `SCLoop.from_poly()`:
    @staticmethod
    def from_poly(poly: SCRoundPoly) -> "SCLoop":
        """Return a rounded polygon's outline as a loop.

        Arguments:
        * `poly` (`SCRoundPoly`): The polygon.

        Returns:
        * (`SCLoop`): Its outline, with its name.
        """
        return SCLoop(poly.name, poly.segments)

    # Method `SCLoop.signed_area()`:
    def signed_area(self) -> float:
        """Return the area inside the loop.

        Returns:
        * (`float`): The area: positive when the loop goes
          counter-clockwise, negative when it goes clockwise.
        """
        # Green's theorem: each segment's chord, plus the sliver
        # between each arc and its chord.
        area: float = 0.0
        segment: SCSegment
        for segment in self.segments:
            area += 0.5 * cross(segment.start, segment.end)
            if isinstance(segment, SCArc):
                area += (
                    0.5
                    * segment.radius**2
                    * (segment.sweep - math.sin(segment.sweep))
                )
        return area

    # Method `SCLoop.is_ccw()`:
    def is_ccw(self) -> bool:
        """Return whether the loop goes counter-clockwise.

        Returns:
        * (`bool`): True when it goes counter-clockwise.
        """
        return self.signed_area() > 0.0

    # Method `SCLoop.length()`:
    def length(self) -> float:
        """Return the distance once around the loop.

        Returns:
        * (`float`): The total length of its segments.
        """
        return sum(segment.length() for segment in self.segments)

    # Method `SCLoop.reversed()`:
    def reversed(self) -> "SCLoop":
        """Return the loop going around the other way.

        Returns:
        * (`SCLoop`): The reversed loop, with the same name.
        """
        return SCLoop(
            self.name,
            tuple(reverse_segment(segment) for segment in self.segments[::-1]),
        )

    # Method `SCLoop.distance()`:
    def distance(self, point: Point) -> float:
        """Return the distance from a point to the loop.

        Arguments:
        * `point` (`Point`): The point.

        Returns:
        * (`float`): The distance.
        """
        return min(distance_to(point, segment) for segment in self.segments)

    # Method `SCLoop.contains()`:
    def contains(self, point: Point) -> bool:
        """Return whether a point is inside the loop (either way round).

        A ray from the point toward +X crosses the loop an odd number
        of times when the point is inside.  The ray is moved up by a
        hair, so that it does not pass exactly through a joint.

        Arguments:
        * `point` (`Point`): The point (not on the loop itself).

        Returns:
        * (`bool`): True when it is inside.
        """
        x: float = point[0]
        y: float = point[1] + math.pi * 1e-8
        crossings: int = 0
        segment: SCSegment
        for segment in self.segments:
            if isinstance(segment, SCLine):
                (x1, y1), (x2, y2) = segment.start, segment.end
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (
                    y2 - y1
                ):
                    crossings += 1
                continue
            rise: float = y - segment.center[1]
            if abs(rise) >= segment.radius:
                continue
            across: float = math.sqrt(segment.radius**2 - rise**2)
            side: float
            for side in (-across, across):
                meeting: Point = (segment.center[0] + side, y)
                if (
                    meeting[0] > x
                    and 0.0 <= fraction_of(segment, meeting) <= 1.0
                ):
                    crossings += 1
        return crossings % 2 == 1

    # Method `SCLoop.corners()`:
    def corners(self) -> list[tuple[Point, Point, Point]]:
        """Return where the loop turns sharply between two segments.

        Returns:
        * (`list[tuple[Point, Point, Point]]`): For each sharp corner,
          its point, the direction arriving and the direction leaving.
        """
        corners: list[tuple[Point, Point, Point]] = []
        index: int
        segment: SCSegment
        for index, segment in enumerate(self.segments):
            following: SCSegment = self.segments[
                (index + 1) % len(self.segments)
            ]
            arriving: Point = end_tangent(segment)
            leaving: Point = start_tangent(following)
            if abs(turn_between(arriving, leaving)) > ANGLE:
                corners.append((segment.end, arriving, leaving))
        return corners


# Function `offset_segment()`:
def offset_segment(segment: SCSegment, distance: float) -> SCSegment | None:
    """Return a segment moved to its left by a distance.

    A line moves sideways; an arc keeps its center and changes its
    radius.  An arc whose radius would go below zero turns inside out,
    and is returned as the line between its moved ends (which the
    trimming in `inset()` always drops).

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `distance` (`float`): How far to move it.

    Returns:
    * (`SCSegment | None`): The moved segment, or `None` when an arc
      shrinks to a point.
    """
    # A line moves sideways.
    if isinstance(segment, SCLine):
        side: Point = left(start_tangent(segment))
        return SCLine(
            (
                segment.start[0] + side[0] * distance,
                segment.start[1] + side[1] * distance,
            ),
            (
                segment.end[0] + side[0] * distance,
                segment.end[1] + side[1] * distance,
            ),
        )

    # A counter-clockwise arc's center is on its left, so it shrinks.
    radius: float = segment.radius - math.copysign(distance, segment.sweep)
    if abs(radius) < EPSILON:
        return None
    ends: list[Point] = []
    end: Point
    for end in (segment.start, segment.end):
        out: Point = unit(
            end[0] - segment.center[0], end[1] - segment.center[1]
        )
        ends.append(
            (
                segment.center[0] + out[0] * radius,
                segment.center[1] + out[1] * radius,
            )
        )
    if radius < 0.0:
        return SCLine(ends[0], ends[1])
    return SCArc(ends[0], ends[1], segment.center, radius, segment.sweep)


# Function `inset()`:
def inset(loops: Sequence[SCLoop], distance: float, name: str) -> list[SCLoop]:
    """Return the loops a distance inside a region.

    The region is on the left of each of its loops (counter-clockwise
    around its outside, clockwise around any islands).  This is the
    classic offset: move every segment `distance` to its left, join
    the moved segments around each corner, split them wherever they
    cross, drop the pieces nearer than `distance` to the region's edge,
    and join what is left into loops.  The region may come apart into
    several, or vanish.

    Arguments:
    * `loops` (`Sequence[SCLoop]`): The loops around the region.
    * `distance` (`float`): How far in to go (positive).
    * `name` (`str`): The name of the loops found (numbered when there
      are several).

    Returns:
    * (`list[SCLoop]`): The loops, with the region still on their left.
    """
    assert distance > 0.0, f"{distance=} must be positive"
    # Move the segments in, and keep the pieces that are far enough in.
    kept: list[SCSegment] = _trim(_moved(loops, distance), loops, distance)

    # Join the pieces into loops.
    return _loops(kept, name)


# Function `beyond()`:
def beyond(
    region: Sequence[SCLoop],
    inner: Sequence[SCLoop],
    distance: float,
    name: str,
) -> list[SCLoop]:
    """Return the part of a region farther than a distance from another.

    `inner` is a region inside `region` (both with their regions on
    the left of their loops).  The result is what is left of `region`
    once everything within `distance` of `inner` (or inside it) is
    taken away: `inner` is grown by `distance` (an inset of its
    outside), the two outlines are split where they cross, and the
    pieces of `region`'s outline far enough from `inner`, with the
    pieces of the grown outline inside `region`, are joined into loops.

    Arguments:
    * `region` (`Sequence[SCLoop]`): The region's loops.
    * `inner` (`Sequence[SCLoop]`): The inner region's loops.
    * `distance` (`float`): How far from `inner` to take away.
    * `name` (`str`): The name of the loops found (numbered when there
      are several).

    Returns:
    * (`list[SCLoop]`): The loops of what is left, with it on their
      left.
    """
    # Grow the inner region: an inset of its outside.
    if not inner:
        return list(region)
    grown: list[SCLoop] = inset(
        [loop.reversed() for loop in inner], distance, name
    )
    outline: list[SCSegment] = [
        segment for loop in region for segment in loop.segments
    ]
    edge: list[SCSegment] = [
        segment for loop in grown for segment in loop.segments
    ]

    # Keep the region's outline where it is far from the inner region,
    # and the grown outline where it is inside the region.
    kept: list[SCSegment] = []
    segment: SCSegment
    for segment in outline:
        piece: SCSegment
        for piece in _split_by(segment, edge):
            middle: Point = point_at(piece, 0.5)
            if all(loop.distance(middle) > distance + TOUCH for loop in inner):
                kept.append(piece)
    for segment in edge:
        for piece in _split_by(segment, outline):
            middle = point_at(piece, 0.5)
            if sum(loop.contains(middle) for loop in region) % 2 == 1:
                kept.append(piece)
    return _loops(kept, name)


# Function `_split_by()`:
def _split_by(
    segment: SCSegment, others: Sequence[SCSegment]
) -> list[SCSegment]:
    """Split a segment wherever other segments cross it.

    Arguments:
    * `segment` (`SCSegment`): The segment.
    * `others` (`Sequence[SCSegment]`): The segments that may cross it.

    Returns:
    * (`list[SCSegment]`): Its pieces (longer than `TOUCH`), in order.
    """
    crossings: list[Point] = [
        point for other in others for point in meet(segment, other)
    ]
    return [
        piece
        for piece in split_at(segment, crossings)
        if piece.length() > TOUCH
    ]


# Function `_loops()`:
def _loops(pieces: list[SCSegment], name: str) -> list[SCLoop]:
    """Join pieces into named loops, dropping any with no area.

    Arguments:
    * `pieces` (`list[SCSegment]`): The pieces, in any order.
    * `name` (`str`): The loops' name (numbered when there are
      several).

    Returns:
    * (`list[SCLoop]`): The loops.
    """
    found: list[SCLoop] = []
    chain: list[SCSegment]
    for chain in _chain(pieces):
        result: SCLoop = SCLoop(name, tuple(_merge(chain)))
        if abs(result.signed_area()) > EPSILON:
            found.append(result)
    if len(found) > 1:
        found = [
            SCLoop(f"{name} {number}", result.segments)
            for number, result in enumerate(found, 1)
        ]
    return found


# Function `_moved()`:
def _moved(loops: Sequence[SCLoop], distance: float) -> list[SCSegment]:
    """Return the segments of a region's loops moved in, and joined.

    Each corner is joined by an arc around it when it turns right
    (away from the region), and by a line across it when it turns left
    (which `_trim()` always drops).

    Arguments:
    * `loops` (`Sequence[SCLoop]`): The loops around the region.
    * `distance` (`float`): How far in to move them.

    Returns:
    * (`list[SCSegment]`): The moved segments and the joins.
    """
    raw: list[SCSegment] = []
    loop: SCLoop
    for loop in loops:
        count: int = len(loop.segments)
        index: int
        segment: SCSegment
        for index, segment in enumerate(loop.segments):
            # Move the segment.
            moved: SCSegment | None = offset_segment(segment, distance)
            if moved is not None and moved.length() > EPSILON:
                raw.append(moved)

            # Join it to the next one, unless they meet smoothly.
            arriving: Point = end_tangent(segment)
            leaving: Point = start_tangent(loop.segments[(index + 1) % count])
            turn: float = turn_between(arriving, leaving)
            if abs(turn) <= ANGLE:
                continue
            corner: Point = segment.end
            ends: list[Point] = [
                (
                    corner[0] + side[0] * distance,
                    corner[1] + side[1] * distance,
                )
                for side in (left(arriving), left(leaving))
            ]
            if turn < 0.0:
                raw.append(SCArc(ends[0], ends[1], corner, distance, turn))
            else:
                raw.append(SCLine(ends[0], ends[1]))
    return raw


# Function `_trim()`:
def _trim(
    raw: list[SCSegment], loops: Sequence[SCLoop], distance: float
) -> list[SCSegment]:
    """Return the pieces of moved segments that are far enough in.

    Arguments:
    * `raw` (`list[SCSegment]`): The moved segments and joins.
    * `loops` (`Sequence[SCLoop]`): The loops around the region.
    * `distance` (`float`): How far in they were moved.

    Returns:
    * (`list[SCSegment]`): The pieces, split wherever the moved
      segments cross, that are `distance` from the region's edge.
    """
    edge: list[SCSegment] = [
        segment for loop in loops for segment in loop.segments
    ]
    kept: list[SCSegment] = []
    index: int
    segment: SCSegment
    for index, segment in enumerate(raw):
        crossings: list[Point] = [
            point
            for other, against in enumerate(raw)
            if other != index
            for point in meet(segment, against)
        ]
        piece: SCSegment
        for piece in split_at(segment, crossings):
            middle: Point = point_at(piece, 0.5)
            if piece.length() > TOUCH and all(
                distance_to(middle, bound) >= distance - TOUCH
                for bound in edge
            ):
                kept.append(piece)
    return kept


# Function `_chain()`:
def _chain(pieces: list[SCSegment]) -> list[list[SCSegment]]:
    """Join pieces end to start into closed chains.

    Arguments:
    * `pieces` (`list[SCSegment]`): The pieces, in any order.

    Returns:
    * (`list[list[SCSegment]]`): The closed chains (pieces that do not
      close up are dropped).
    """
    chains: list[list[SCSegment]] = []
    unused: list[SCSegment] = list(pieces)
    while unused:
        # Follow the chain until it comes back to its start.
        chain: list[SCSegment] = [unused.pop(0)]
        while True:
            end: Point = chain[-1].end
            if len(chain) > 1 and math.dist(end, chain[0].start) <= JOIN:
                chains.append(chain)
                break
            if not unused:
                break
            nearest: int = min(
                range(len(unused)),
                key=lambda index: math.dist(unused[index].start, end),
            )
            if math.dist(unused[nearest].start, end) > JOIN:
                break
            chain.append(unused.pop(nearest))
    return chains


# Function `_merge()`:
def _merge(chain: list[SCSegment]) -> list[SCSegment]:
    """Close a chain's gaps, and rejoin pieces split from one segment.

    Arguments:
    * `chain` (`list[SCSegment]`): A closed chain of pieces.

    Returns:
    * (`list[SCSegment]`): The same loop, each segment starting exactly
      where the one before ends, with lines that continue each other
      (and arcs of one circle going the same way) made one.
    """
    # Rejoin pieces that continue each other.
    merged: list[SCSegment] = []
    segment: SCSegment
    for segment in chain:
        joined: SCSegment | None = (
            _join(merged[-1], segment) if merged else None
        )
        if joined is None:
            merged.append(segment)
        else:
            merged[-1] = joined
    if len(merged) > 2:
        wrapped: SCSegment | None = _join(merged[-1], merged[0])
        if wrapped is not None:
            merged = [wrapped, *merged[1:-1]]

    # Make each segment start exactly where the one before ends.
    closed: list[SCSegment] = []
    index: int
    for index, segment in enumerate(merged):
        start: Point = merged[index - 1].end
        if isinstance(segment, SCLine):
            closed.append(SCLine(start, segment.end))
        else:
            closed.append(
                SCArc(
                    start,
                    segment.end,
                    segment.center,
                    segment.radius,
                    segment.sweep,
                )
            )
    return closed


# Function `_join()`:
def _join(first: SCSegment, second: SCSegment) -> SCSegment | None:
    """Return two segments as one, when the second continues the first.

    Arguments:
    * `first` (`SCSegment`): The first segment.
    * `second` (`SCSegment`): The segment after it.

    Returns:
    * (`SCSegment | None`): The two as one, or `None` when they meet at
      an angle or are not alike.
    """
    if abs(turn_between(end_tangent(first), start_tangent(second))) > ANGLE:
        return None
    if isinstance(first, SCLine) and isinstance(second, SCLine):
        return SCLine(first.start, second.end)
    if (
        isinstance(first, SCArc)
        and isinstance(second, SCArc)
        and _same_circle(first, second)
    ):
        return SCArc(
            first.start,
            second.end,
            first.center,
            first.radius,
            first.sweep + second.sweep,
        )
    return None


# Function `_same_circle()`:
def _same_circle(first: SCArc, second: SCArc) -> bool:
    """Return whether two arcs can be one arc.

    Arguments:
    * `first` (`SCArc`): One arc.
    * `second` (`SCArc`): The other.

    Returns:
    * (`bool`): True when they share a circle and a direction, and
      together go less than once around it.
    """
    return (
        math.dist(first.center, second.center) <= JOIN
        and abs(first.radius - second.radius) <= JOIN
        and first.sweep * second.sweep > 0.0
        and abs(first.sweep + second.sweep) < 2.0 * math.pi - ANGLE
    )
