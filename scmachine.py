"""The machine and its tools, as the G-code side (`SCCNC`) sees them.

`SCMachine` holds a machine's preferences and its loaded tools
(`SCTool`), in inches, inches per minute, revolutions per minute,
degrees and fractions.  They are built from a shop's description by
`shops.cnc_machine()`, which reads the units each file gives.

Some machines do not rise to a safe height for a tool change on their
own, so the program always rises to `tool_change_z` first.  The
`tool_change` template is filled in with Python's `str.format()`, with
`number` the tool's number (most changers hold fewer than 100 tools,
so two digits is usual).
"""

from dataclasses import dataclass, field
from typing import Literal, TypeAlias, get_args

# The kinds of tools.
ToolKind: TypeAlias = Literal[
    "end mill",
    "roughing end mill",
    "ball end mill",
    "drill",
    "chamfer",
    "corner round",
    "double angle",
]

# How holes are drilled: a canned cycle (straight, chip breaking, or
# pecking with full retracts), or the pecks written out as moves.
DrillCycle: TypeAlias = Literal["G81", "G73", "G83", "moves"]


# Class `SCTool`:
# Each attribute is a setting of the tool table, so there are more
# than `pylint` likes.
@dataclass(frozen=True, slots=True)
class SCTool:  # pylint: disable=too-many-instance-attributes
    """One tool of the tool table.

    Attributes:
    * `number` (`int`): Its pocket in the tool changer (`T` number).
    * `name` (`str`): What it is (shown in a comment).
    * `kind` (`ToolKind`):
      `"end mill"`, `"roughing end mill"`, `"ball end mill"`,
      `"drill"`, `"chamfer"` (a V-bit, which bevels edges), `"corner
      round"` (which rounds edges over) or `"double angle"` (a double
      angle shank cutter, which can bevel bottom edges too).
    * `diameter` (`float`):
      Its cutting diameter (inches); for a chamfer or corner rounding
      bit, its diameter at the tip.
    * `rpm` (`float`): The spindle's speed for it.
    * `feed` (`float`): Its cutting feed (inches per minute).
    * `plunge` (`float`): Its feed going straight down.
    * `peck` (`float`):
      For a drill, how deep each peck goes (0 for one pass).
    * `angle` (`float`):
      For a chamfer bit or double angle cutter, its included angle
      (degrees; 90 makes 45 degree bevels).
    * `radius` (`float`):
      For a corner rounding bit, the radius it rounds edges to.

    Constructor:
    * `SCTool(number, name, kind, diameter, rpm, feed, plunge, peck,
      angle, radius)`
    """

    # Constructor arguments:
    number: int = field(init=True)
    name: str = field(init=True)
    kind: ToolKind = field(init=True)
    diameter: float = field(init=True)
    rpm: float = field(init=True)
    feed: float = field(init=True)
    plunge: float = field(init=True)
    peck: float = field(init=True, default=0.0)
    angle: float = field(init=True, default=0.0)
    radius: float = field(init=True, default=0.0)

    # Method `SCTool.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the tool.

        Raises:
        * `ValueError`:
          If its number is not positive, its kind is unknown, a size
          or speed is not positive (or the peck is negative), a chamfer
          bit's angle is not between 0 and 180 degrees, or a corner
          rounding bit has no radius.
        """
        where: str = f"tool {self.number}"
        if self.number <= 0:
            raise ValueError(f"{where}: its number must be positive")
        if self.kind not in get_args(ToolKind):
            raise ValueError(f"{where}: unknown kind {self.kind!r}")
        name: str
        for name in ("diameter", "rpm", "feed", "plunge"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{where}: {name} must be positive")
        if self.peck < 0.0:
            raise ValueError(f"{where}: peck must not be negative")
        if self.kind in ("chamfer", "double angle") and not (
            0.0 < self.angle < 180.0
        ):
            raise ValueError(f"{where}: angle must be in (0, 180) deg")
        if self.kind == "corner round" and self.radius <= 0.0:
            raise ValueError(f"{where}: radius must be positive")


# Class `SCMachine`:
# Each attribute is a machine preference, so there are more than
# `pylint` likes.
@dataclass(frozen=True, slots=True)
class SCMachine:  # pylint: disable=too-many-instance-attributes
    """A machine's preferences and its tool table.

    Attributes:
    * `name` (`str`): The machine's name.
    * `z_safe` (`float`):
      The Z above all of the hold down tooling, for moving across.
    * `clearance` (`float`): How far above the work rapids down stop.
    * `tool_change_z` (`float`): The Z to rise to before a tool change.
    * `tool_change` (`str`):
      The words that change the tool, as a `str.format()` template of
      `number` (e.g. `"T{number:02d}"` or `"T{number:02d} M06"`).
    * `rapid_speed` (`float`):
      The machine's rapid speed (inches per minute), for estimating
      run times only.
    * `drill_cycle` (`DrillCycle`): How holes are drilled.
    * `through_overcut` (`float`):
      How much deeper than the part a cut through it goes, as a
      fraction of the part's thickness (so the metal does not stretch
      and bulge out at the bottom).
    * `stepover` (`float`):
      How far apart a pocket's rings are, in tool diameters.
    * `ramp_angle` (`float`):
      The steepest angle (degrees) a tool goes down at into a pocket
      that has not been drilled.
    * `tools` (`tuple[SCTool, ...]`): The tool table.
    * `finish_allowance` (`float`):
      How much a roughing end mill leaves on walls and floors for the
      end mill that finishes them.

    Constructor:
    * `SCMachine(name, z_safe, clearance, tool_change_z, tool_change,
      rapid_speed, drill_cycle, through_overcut, stepover, ramp_angle,
      tools, finish_allowance)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    z_safe: float = field(init=True)
    clearance: float = field(init=True)
    tool_change_z: float = field(init=True)
    tool_change: str = field(init=True)
    rapid_speed: float = field(init=True)
    drill_cycle: DrillCycle = field(init=True)
    through_overcut: float = field(init=True)
    stepover: float = field(init=True)
    ramp_angle: float = field(init=True)
    tools: tuple[SCTool, ...] = field(init=True)
    finish_allowance: float = field(init=True, default=0.05)

    # Method `SCMachine.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the preferences and the tool table.

        Raises:
        * `ValueError`:
          If a preference makes no sense, the tool change template
          does not work, or two tools share a number.
        """
        # The preferences.
        if self.clearance < 0.0:
            raise ValueError(f"{self.clearance=} must not be negative")
        if self.tool_change_z < self.z_safe:
            raise ValueError(
                f"{self.tool_change_z=} must not be below {self.z_safe=}"
            )
        if self.rapid_speed <= 0.0:
            raise ValueError(f"{self.rapid_speed=} must be positive")
        if self.drill_cycle not in ("G81", "G73", "G83", "moves"):
            raise ValueError(f"unknown {self.drill_cycle=}")
        if not 0.0 <= self.through_overcut <= 1.0:
            raise ValueError(f"{self.through_overcut=} must be in [0, 1]")
        if not 0.0 < self.stepover <= 1.0:
            raise ValueError(f"{self.stepover=} must be in (0, 1]")
        if not 0.0 < self.ramp_angle <= 90.0:
            raise ValueError(f"{self.ramp_angle=} must be in (0, 90]")
        if self.finish_allowance < 0.0:
            raise ValueError(f"{self.finish_allowance=} must not be negative")

        # The tool change words must be letters followed by values.
        words: list[str] = self.change_words(1)
        if not words or not all(
            len(word) > 1 and word[0].isalpha() for word in words
        ):
            raise ValueError(f"{self.tool_change=} makes {words}")

        # Each tool's number must be its own.
        numbers: list[int] = [tool.number for tool in self.tools]
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"tool numbers {numbers} are not all different")

    # Method `SCMachine.change_words()`:
    def change_words(self, number: int) -> list[str]:
        """Return the words that change to a tool.

        Arguments:
        * `number` (`int`): The tool's number.

        Returns:
        * (`list[str]`): The words (e.g. `["T02"]`).

        Raises:
        * `ValueError`: If the template does not fill in.
        """
        try:
            return self.tool_change.format(number=number).split()
        except (KeyError, IndexError, ValueError) as error:
            raise ValueError(f"{self.tool_change=}: {error}") from error

    # Method `SCMachine.tool()`:
    def tool(self, number: int) -> SCTool:
        """Return a tool by its number.

        Arguments:
        * `number` (`int`): The tool's number.

        Returns:
        * (`SCTool`): The tool.

        Raises:
        * `KeyError`: If the tool table has no such tool.
        """
        tool: SCTool
        for tool in self.tools:
            if tool.number == number:
                return tool
        raise KeyError(f"{self.name}: no tool {number} in the tool table")

    # Method `SCMachine.named()`:
    def named(self, name: str) -> SCTool:
        """Return a tool by its name.

        Arguments:
        * `name` (`str`): The tool's name.

        Returns:
        * (`SCTool`): The tool.

        Raises:
        * `KeyError`: If the tool table has no such tool.
        """
        tool: SCTool
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f'{self.name}: no tool "{name}" in the tool table')

    # Method `SCMachine.rougher_for()`:
    def rougher_for(self, end_mill: SCTool) -> SCTool | None:
        """Return the roughing end mill to use before an end mill.

        It is the largest roughing end mill no wider than the end mill,
        so it fits wherever the end mill finishes.

        Arguments:
        * `end_mill` (`SCTool`): The end mill that finishes.

        Returns:
        * (`SCTool | None`): The rougher, or `None` if there is none.
        """
        roughers: list[SCTool] = [
            tool
            for tool in self.tools
            if tool.kind == "roughing end mill"
            and tool.diameter <= end_mill.diameter
        ]
        return max(roughers, key=lambda tool: tool.diameter, default=None)

    # Method `SCMachine.drill_for()`:
    def drill_for(self, end_mill: SCTool) -> SCTool:
        """Return the drill to make entry holes for an end mill.

        It is the largest drill smaller than the end mill, so the end
        mill goes down the hole taking a light cut.

        Arguments:
        * `end_mill` (`SCTool`): The end mill.

        Returns:
        * (`SCTool`): The drill.

        Raises:
        * `ValueError`: If no drill is smaller than the end mill.
        """
        drills: list[SCTool] = [
            tool
            for tool in self.tools
            if tool.kind == "drill" and tool.diameter < end_mill.diameter
        ]
        if not drills:
            raise ValueError(
                f"{self.name}: no drill is smaller than tool "
                f"{end_mill.number} ({end_mill.diameter:g})"
            )
        return max(drills, key=lambda tool: tool.diameter)
