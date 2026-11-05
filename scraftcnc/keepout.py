#!/usr/bin/env python3
"""Check a program's moves against where the tool must not go.

The zones are the keep-outs of a `Setup`'s tooling, as root
`RoundedPolygon`s moved into the G-code's coordinates (inches, from
the middle of the material's top).  Tooling is checked and material is
not, since material is what gets cut.

`check_program()` walks the finished `CNC.commands`, so it does not
depend on how they were made, and reports every violation:

* `keep out`: the tool, a vertical cylinder of its widest radius
  reaching up forever, touches a zone.  A move is tested at its lowest Z.
* `rapid`: a `G0` breaks the rule that rapids belong at `z_safe`.  One
  going up is always fine, and a drill may rapid down to above `z_top`.
* `unchecked`: something the checker does not understand, so that an
  empty list means that everything really was checked.

Run it to check the demonstration plate (which should have no keep out
violations) and the grid plate (whose long edges should).
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, TypeAlias

from .assembly import Assembly, resolve
from .demo import (
    END_MILL,
    MACHINE,
    MATERIAL,
    SHOP_FILE,
    cut_demo,
    demo_assembly,
)
from .gcode import CNC, RS274
from .geometry import (
    ArcSegment,
    Corner,
    LineSegment,
    RoundedPolygon,
    XYSegment,
)
from .machine import Machine, ToolEntry
from .setup_view import PlacedItem, keep_out_prisms, place
from .setups import EXAMPLE, PlacedWork, Setup
from .shops import cnc_machine, read
from .tooling.cutter_models import MM_PER_INCH
from .tooling.shop_registries import use_shop
from .tooling.tools import GRID_PLATE, Cylinder, Point, Prism

# What a violation can be.
ViolationKind: TypeAlias = Literal["keep out", "rapid", "unchecked"]

# The demonstration plate's setup.
DEMO_SETUP: Path = Path(__file__).resolve().parents[1] / (
    "examples/setup/demo_plate.json"
)

# The canned drilling cycles, and the `G` codes that do not move.
CYCLES: tuple[int, ...] = (73, 81, 83)
NOT_MOVES: tuple[int, ...] = (17, 20, 43, 80, 90, 94, 98)

# How far apart two heights may be and still be the same (inches).
SAME: float = 1e-9

# The drill for the grid plate's holes (`tools.SCREW_FITS`: #6,
# close).
HOLE_DRILL: ToolEntry = ToolEntry(
    50, "#27 drill", "drill", 0.144, 3000, 6.0, 6.0, 0.05
)


# Class `Violation`:
@dataclass(frozen=True, slots=True)
class Violation:
    """Something wrong with one line of a program.

    Attributes:
    * `line` (`int`): The G-code line, counting from 1.
    * `kind` (`ViolationKind`): What sort of problem it is.
    * `zone` (`str`): The zone it enters (empty if not a `keep out`).
    * `text` (`str`): What the problem is.

    Constructor:
    * `Violation(line, kind, zone, text)`
    """

    # Constructor arguments:
    line: int = field(init=True)
    kind: ViolationKind = field(init=True)
    zone: str = field(init=True)
    text: str = field(init=True)


# Function `prism_zone()`:
def prism_zone(prism: Prism, origin: Point) -> RoundedPolygon:
    """Return a prism as a zone in the G-code's coordinates.

    Arguments:
    * `prism` (`Prism`): The prism (millimeters, in the setup).
    * `origin` (`Point`): Where the G-code's origin is (same).

    Returns:
    * (`RoundedPolygon`): The zone (inches), going up, sharp cornered.
    """
    x0, y0, z0 = (
        (low - zero) / MM_PER_INCH
        for low, zero in zip(prism.low, origin, strict=True)
    )
    x1, y1, z1 = (
        (high - zero) / MM_PER_INCH
        for high, zero in zip(prism.high, origin, strict=True)
    )
    return RoundedPolygon(
        prism.name,
        [
            Corner(x0, y0),
            Corner(x1, y0),
            Corner(x1, y1),
            Corner(x0, y1),
        ],
        z0,
        z1,
    )


# Function `cylinder_zone()`:
def cylinder_zone(cylinder: Cylinder, origin: Point) -> RoundedPolygon:
    """Return a cylinder as a zone in the G-code's coordinates.

    Arguments:
    * `cylinder` (`Cylinder`):
      The cylinder (millimeters, in the setup).
    * `origin` (`Point`): Where the G-code's origin is (same).

    Returns:
    * (`RoundedPolygon`): The zone (inches), going up.
    """
    return RoundedPolygon.circle(
        cylinder.name,
        (cylinder.center[0] - origin[0]) / MM_PER_INCH,
        (cylinder.center[1] - origin[1]) / MM_PER_INCH,
        cylinder.radius / MM_PER_INCH,
        (cylinder.low - origin[2]) / MM_PER_INCH,
        (cylinder.high - origin[2]) / MM_PER_INCH,
    )


# Function `work_zones()`:
def work_zones(setup: Setup, material: PlacedWork) -> list[RoundedPolygon]:
    """Return a setup's zones, from the middle of a material's top.

    Overlapping zones are left that way, since a move is bad if it
    enters any of them, so each can simply be tested in turn.

    Arguments:
    * `setup` (`Setup`): The setup.
    * `material` (`PlacedWork`): The material being cut.

    Returns:
    * (`list[RoundedPolygon]`): The zones, as roots.
    """
    origin: Point = material.work_origin()
    regions = setup.keep_out()
    return [prism_zone(prism, origin) for prism in regions.prisms] + [
        cylinder_zone(cylinder, origin) for cylinder in regions.cylinders
    ]


# Function `assembly_zones()`:
def assembly_zones(assembly: Assembly) -> list[RoundedPolygon]:
    """Return the zones of an assembly's own keep-outs (`.nc` setups).

    The setup frame is the work frame, so no origin is moved.

    Arguments:
    * `assembly` (`Assembly`): The setup, as written to the `.nc`.

    Returns:
    * (`list[RoundedPolygon]`): The zones, as roots.
    """
    zones: list[RoundedPolygon] = []
    here: PlacedItem
    for here in place(assembly):
        if not here.item.keep_out:
            continue
        origin: Point = resolve(here.item).origin(0)
        low: Point
        high: Point
        for low, high in keep_out_prisms(here, origin):
            zones.append(
                prism_zone(Prism(here.item.name, low, high), (0, 0, 0))
            )
    return zones


# Function `_word()`:
def _word(command: RS274, letter: str) -> float | None:
    """Return a word of a command as a number.

    Arguments:
    * `command` (`RS274`): The command.
    * `letter` (`str`): The word's letter.

    Returns:
    * (`float | None`): Its value (`None` when it is not there).
    """
    value: float | int | str | None = command.get(letter)
    return None if value is None else float(value)


# Function `arc_segments()`:
def arc_segments(
    start: tuple[float, float],
    end: tuple[float, float],
    offset: tuple[float, float],
    code: int,
) -> list[XYSegment]:
    """Return the arcs of a `G2` or `G3`, with a whole circle in halves.

    Arguments:
    * `start` (`tuple[float, float]`): Where it starts.
    * `end` (`tuple[float, float]`): Where it ends.
    * `offset` (`tuple[float, float]`): Its `I` and `J`.
    * `code` (`int`): 2 for clockwise, 3 for counter-clockwise.

    Returns:
    * (`list[XYSegment]`): One arc, or two for a whole circle.
    """
    center: tuple[float, float] = (start[0] + offset[0], start[1] + offset[1])
    radius: float = math.hypot(*offset)
    turn: float = 2.0 * math.pi
    sign: float = 1.0 if code == 3 else -1.0
    if math.dist(start, end) < SAME:
        far: tuple[float, float] = (
            2.0 * center[0] - start[0],
            2.0 * center[1] - start[1],
        )
        return [
            ArcSegment(start, far, center, radius, sign * math.pi),
            ArcSegment(far, start, center, radius, sign * math.pi),
        ]
    first: float = math.atan2(start[1] - center[1], start[0] - center[0])
    last: float = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep: float = sign * ((sign * (last - first)) % turn)
    return [ArcSegment(start, end, center, radius, sweep)]


# Class `_Checker`:
@dataclass(slots=True)
class _Checker:
    """Walks a program, keeping track of where the tool is.

    Attributes:
    * `cnc` (`CNC`): The program.
    * `zones` (`Sequence[RoundedPolygon]`):
      Where the tool must not go.
    * `position` (`list[float | None]`): Where the tool is (X, Y, Z).
    * `tool` (`ToolEntry | None`): The tool in the spindle.
    * `violations` (`list[Violation]`): What has been found so far.

    Constructor:
    * `_Checker(cnc, zones)`
    """

    # Constructor arguments:
    cnc: CNC = field(init=True)
    zones: Sequence[RoundedPolygon] = field(init=True)

    # The program's state (alphabetized):
    position: list[float | None] = field(
        init=False, default_factory=lambda: [None, None, None]
    )
    tool: ToolEntry | None = field(init=False, default=None)
    violations: list[Violation] = field(init=False, default_factory=list)

    # Method `_Checker.problem()`:
    def problem(
        self, line: int, kind: ViolationKind, text: str, zone: str = ""
    ) -> None:
        """Save a violation.

        Arguments:
        * `line` (`int`): The G-code line.
        * `kind` (`ViolationKind`): What sort of problem it is.
        * `text` (`str`): What the problem is.
        * `zone` (`str`): The zone it enters, if any.
        """
        self.violations.append(Violation(line, kind, zone, text))

    # Method `_Checker.run()`:
    def run(self) -> list[Violation]:
        """Check every command of the program.

        Returns:
        * (`list[Violation]`): Everything found, in program order.
        """
        line: int
        command: RS274
        for line, command in enumerate(self.cnc.commands, 1):
            if "comment" in command:
                continue
            tool: float | None = _word(command, "T")
            if tool is not None:
                self.tool = self.cnc.machine.tool(int(tool))
                continue
            code: float | None = _word(command, "G")
            moves: bool = any(letter in command for letter in "XYZIJ")
            if code in (0, 1, 2, 3):
                self.move(line, command, int(code or 0))
            elif code in CYCLES:
                self.cycle(line, command)
            elif moves or (code is not None and code not in NOT_MOVES):
                self.problem(line, "unchecked", f"not understood: {command}")
        return self.violations

    # Method `_Checker.enter()`:
    def enter(self, line: int, moves: Sequence[XYSegment], z: float) -> None:
        """Test moves at a height against every zone.

        Arguments:
        * `line` (`int`): The G-code line.
        * `moves` (`Sequence[XYSegment]`):
          The path of the tool's center.
        * `z` (`float`): The lowest height of its tip.
        """
        tool: ToolEntry | None = self.tool
        if tool is None:
            self.problem(line, "unchecked", "no tool is known")
            return
        radius: float = tool.widest_radius()
        zone: RoundedPolygon
        for zone in self.zones:
            if any(zone.hits(move, z, radius) for move in moves):
                self.problem(
                    line,
                    "keep out",
                    f"T{tool.number} ({tool.name}, radius {radius:g}) at "
                    f"Z{z:g} enters {zone.name}",
                    zone.name,
                )

    # Method `_Checker.move()`:
    def move(self, line: int, command: RS274, code: int) -> None:
        """Check a `G0`, `G1`, `G2` or `G3`.

        Arguments:
        * `line` (`int`): The G-code line.
        * `command` (`RS274`): The move.
        * `code` (`int`): Its `G` code.
        """
        # Where it goes.
        x0, y0, z0 = self.position
        x1: float | None = _word(command, "X")
        y1: float | None = _word(command, "Y")
        z1: float | None = _word(command, "Z")
        x1 = x0 if x1 is None else x1
        y1 = y0 if y1 is None else y1
        z1 = z0 if z1 is None else z1
        self.position = [x1, y1, z1]
        if code == 0:
            self.rapid_rule(line, (x0, y0, z0), (x1, y1, z1))

        # Until its X and Y are known, it must be above everything.
        if x1 is None or y1 is None or z1 is None:
            if z1 is None or z1 < self.cnc.z_safe - SAME:
                self.problem(line, "unchecked", "where it is, is not known")
            return
        if x0 is None or y0 is None or z0 is None:
            if z1 < self.cnc.z_safe - SAME:
                self.problem(line, "unchecked", "where it was, is not known")
            elif self.tool is not None:
                self.enter(line, [LineSegment((x1, y1), (x1, y1))], z1)
            return

        # Test its whole path at its lowest height.
        moves: list[XYSegment] = [LineSegment((x0, y0), (x1, y1))]
        if code in (2, 3):
            offset: tuple[float, float] = (
                _word(command, "I") or 0.0,
                _word(command, "J") or 0.0,
            )
            moves = arc_segments((x0, y0), (x1, y1), offset, code)
        self.enter(line, moves, min(z0, z1))

    # Method `_Checker.rapid_rule()`:
    def rapid_rule(
        self,
        line: int,
        old: tuple[float | None, float | None, float | None],
        new: tuple[float | None, float | None, float | None],
    ) -> None:
        """Check that a `G0` is one that belongs in a program.

        Arguments:
        * `line` (`int`): The G-code line.
        * `old` (`tuple[float | None, float | None, float | None]`):
          Where it starts.
        * `new` (`tuple[float | None, float | None, float | None]`):
          Where it ends.
        """
        z_safe: float = self.cnc.z_safe - SAME
        z0: float | None = old[2]
        z1: float | None = new[2]
        if z1 is None:
            return
        sideways: bool = old[:2] != new[:2]
        if sideways and (z1 < z_safe or (z0 is not None and z0 < z_safe)):
            self.problem(line, "rapid", f"sideways below z_safe, at Z{z1:g}")
        elif not sideways and z0 is not None and z1 < z0 and z1 < z_safe:
            drill: bool = self.tool is not None and self.tool.kind == "drill"
            if not (drill and z1 > self.cnc.z_top + SAME):
                self.problem(
                    line, "rapid", f"going down below z_safe to Z{z1:g}"
                )

    # Method `_Checker.cycle()`:
    def cycle(self, line: int, command: RS274) -> None:
        """Check a canned cycle: a vertical move at the tool's X and Y.

        Its rapids back into the hole between pecks are allowed, and
        with `G98` it ends where it started.

        Arguments:
        * `line` (`int`): The G-code line.
        * `command` (`RS274`): The cycle.
        """
        x, y, _ = self.position
        bottom: float | None = _word(command, "Z")
        retract: float | None = _word(command, "R")
        combined: bool = "X" in command or "Y" in command
        if combined or None in (x, y, bottom, retract):
            self.problem(line, "unchecked", f"cycle not understood: {command}")
            return
        assert x is not None and y is not None
        assert bottom is not None and retract is not None
        if retract <= self.cnc.z_top:
            self.problem(
                line,
                "rapid",
                f"the cycle's R{retract:g} is not above the work",
            )
        self.enter(line, [LineSegment((x, y), (x, y))], bottom)


# Function `check_program()`:
def check_program(
    cnc: CNC, zones: Sequence[RoundedPolygon]
) -> list[Violation]:
    """Return everything wrong with a program.

    Arguments:
    * `cnc` (`CNC`): The program, in the zones' coordinates.
    * `zones` (`Sequence[RoundedPolygon]`):
      Where the tool must not go.

    Returns:
    * (`list[Violation]`): Every violation, in program order.
    """
    return _Checker(cnc, zones).run()


# Function `report()`:
def report(cnc: CNC, violations: Sequence[Violation]) -> str:
    """Return a report of a program's violations.

    Arguments:
    * `cnc` (`CNC`): The program.
    * `violations` (`Sequence[Violation]`): What was found.

    Returns:
    * (`str`): A count by kind and zone, then each with its G-code line.
    """
    lines: list[str] = cnc.gcode().splitlines()
    counts: dict[tuple[str, str], int] = {}
    violation: Violation
    for violation in violations:
        key: tuple[str, str] = (violation.kind, violation.zone)
        counts[key] = counts.get(key, 0) + 1
    text: list[str] = [f"{cnc.name}: {len(violations)} violations"]
    text += [
        f"  {count} {kind}" + (f": {zone}" if zone else "")
        for (kind, zone), count in sorted(counts.items())
    ]
    text += [
        f"  line {violation.line}: {violation.kind}: {violation.text}: "
        f"{lines[violation.line - 1]}"
        for violation in violations
    ]
    return "\n".join(text)


# Function `grid_plate_program()`:
def grid_plate_program(turns: int, machine: Machine) -> CNC:
    """Return a program that drills and cuts out the grid plate.

    `CNC` does not cut an `RoundedPolygon`'s children yet, so it
    drills the holes and profiles the outline directly.

    Arguments:
    * `turns` (`int`): The part's quarter turns counterclockwise.
    * `machine` (`Machine`): The machine, with `HOLE_DRILL` loaded.

    Returns:
    * (`CNC`): The program, from the middle of the plate's top.
    """
    half_x: float = GRID_PLATE.length / 2.0 / MM_PER_INCH
    half_y: float = GRID_PLATE.width / 2.0 / MM_PER_INCH
    radius: float = GRID_PLATE.corner_radius / MM_PER_INCH
    bottom: float = -GRID_PLATE.height / MM_PER_INCH
    outline: RoundedPolygon = RoundedPolygon(
        GRID_PLATE.name,
        [
            Corner(-half_x, -half_y, radius),
            Corner(half_x, -half_y, radius),
            Corner(half_x, half_y, radius),
            Corner(-half_x, half_y, radius),
        ],
        bottom,
        0.0,
    )
    cnc: CNC = CNC("Grid plate", machine)
    cnc.change_tool(HOLE_DRILL.number)
    cnc.drill(
        [
            (x / MM_PER_INCH, y / MM_PER_INCH)
            for x, y in GRID_PLATE.hole_centers()
        ],
        bottom,
        through=True,
    )
    cnc.change_tool(machine.named(END_MILL).number)
    cnc.profile(outline, bottom, 0.125, through=True)
    cnc.finish()
    cnc.remap(turns)
    return cnc


# Function `shop_machine_with_hole_drill()`:
def shop_machine_with_hole_drill() -> Machine:
    """Return the example shop's mill with `HOLE_DRILL` loaded as well.

    Returns:
    * (`Machine`): The machine.
    """
    machine: Machine = cnc_machine(read(SHOP_FILE), MACHINE, MATERIAL)
    return replace(machine, tools=(*machine.tools, HOLE_DRILL))


# Function `main()`:
def main() -> int:
    """Check the demonstration plate and the grid plate.

    Returns:
    * (`int`): The exit status.
    """
    # The example shop is the one in use.
    use_shop(read(SHOP_FILE))

    # The demonstration plate's corner is at the origin, so it is moved.
    demo: Setup = Setup(json.loads(DEMO_SETUP.read_text(encoding="utf-8")))
    cnc: CNC = cut_demo()[0]
    cnc.remap(0, -2.0, -1.5)
    print(report(cnc, check_program(cnc, work_zones(demo, demo.materials[0]))))

    # The same program against the `.nc` setup's own keep-outs.
    plate: CNC = cut_demo()[0]
    plate.name = "Demo plate, setup keep-outs"
    print(report(plate, check_program(plate, assembly_zones(demo_assembly()))))

    # The grid plate is placed turned.
    setup: Setup = Setup(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    material: PlacedWork = setup.materials[0]
    cnc = grid_plate_program(
        material.parts[0].placement.turns, shop_machine_with_hole_drill()
    )
    print(report(cnc, check_program(cnc, work_zones(setup, material))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
