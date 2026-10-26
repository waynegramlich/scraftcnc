"""The machine's preferences and its tool table, read from a TOML file.

A machine file (such as `machine.toml`) has a `[machine]` table of
preferences and one `[[tools]]` table per tool:

```
[machine]
name = "Shop mill"
z_safe = 1.0            # Above all of the hold down tooling.
clearance = 0.05        # Rapids down stop this far above the work.
tool_change_z = 2.0     # Rise here before every tool change.
tool_change = "T{number:02d}"   # The words that change the tool.
rapid_speed = 60.0      # Inches per minute (for time estimates).
drill_cycle = "G83"     # G81, G73, G83, or "moves".
stepover = 0.9          # Pocket rings apart, in tool diameters.
ramp_angle = 3.0        # Degrees, when a pocket is not drilled.

[[tools]]
number = 1
name = "1/4 inch 2 flute end mill"
kind = "end mill"       # Or "drill".
diameter = 0.25
rpm = 1200
feed = 12.0             # Inches per minute, cutting.
plunge = 6.0            # Inches per minute, going straight down.
peck = 0.0              # Drills: how deep each peck goes.
```

Some machines do not rise to a safe height for a tool change on their
own, so the program always rises to `tool_change_z` first.  The
`tool_change` template is filled in with Python's `str.format()`, with
`number` the tool's number (most changers hold fewer than 100 tools,
so two digits is usual).
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar, cast

# The kinds of tools.
ToolKind: TypeAlias = Literal["end mill", "drill"]

# How holes are drilled: a canned cycle (straight, chip breaking, or
# pecking with full retracts), or the pecks written out as moves.
DrillCycle: TypeAlias = Literal["G81", "G73", "G83", "moves"]

# The types of settings a machine file holds.
Setting = TypeVar("Setting", str, int, float)


# Class `SCTool`:
# Each attribute is a setting of the tool table, so there are more
# than `pylint` likes.
@dataclass(frozen=True, slots=True)
class SCTool:  # pylint: disable=too-many-instance-attributes
    """One tool of the tool table.

    Attributes:
    * `number` (`int`): Its pocket in the tool changer (`T` number).
    * `name` (`str`): What it is (shown in a comment).
    * `kind` (`ToolKind`): `"end mill"` or `"drill"`.
    * `diameter` (`float`): Its cutting diameter (inches).
    * `rpm` (`float`): The spindle's speed for it.
    * `feed` (`float`): Its cutting feed (inches per minute).
    * `plunge` (`float`): Its feed going straight down.
    * `peck` (`float`):
      For a drill, how deep each peck goes (0 for one pass).

    Constructor:
    * `SCTool(number, name, kind, diameter, rpm, feed, plunge, peck)`
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

    # Method `SCTool.__post_init__()`:
    def __post_init__(self) -> None:
        """Validate the tool.

        Raises:
        * `ValueError`:
          If its number is not positive, its kind is unknown, or a size
          or speed is not positive (or the peck is negative).
        """
        where: str = f"tool {self.number}"
        if self.number <= 0:
            raise ValueError(f"{where}: its number must be positive")
        if self.kind not in ("end mill", "drill"):
            raise ValueError(f"{where}: unknown kind {self.kind!r}")
        name: str
        for name in ("diameter", "rpm", "feed", "plunge"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{where}: {name} must be positive")
        if self.peck < 0.0:
            raise ValueError(f"{where}: peck must not be negative")


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
    * `stepover` (`float`):
      How far apart a pocket's rings are, in tool diameters.
    * `ramp_angle` (`float`):
      The steepest angle (degrees) a tool goes down at into a pocket
      that has not been drilled.
    * `tools` (`tuple[SCTool, ...]`): The tool table.

    Constructor:
    * `SCMachine(name, z_safe, clearance, tool_change_z, tool_change,
      rapid_speed, drill_cycle, stepover, ramp_angle, tools)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    z_safe: float = field(init=True)
    clearance: float = field(init=True)
    tool_change_z: float = field(init=True)
    tool_change: str = field(init=True)
    rapid_speed: float = field(init=True)
    drill_cycle: DrillCycle = field(init=True)
    stepover: float = field(init=True)
    ramp_angle: float = field(init=True)
    tools: tuple[SCTool, ...] = field(init=True)

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
        if not 0.0 < self.stepover <= 1.0:
            raise ValueError(f"{self.stepover=} must be in (0, 1]")
        if not 0.0 < self.ramp_angle <= 90.0:
            raise ValueError(f"{self.ramp_angle=} must be in (0, 90]")

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


# Function `load_machine()`:
def load_machine(path: Path) -> SCMachine:
    """Read a machine file.

    Arguments:
    * `path` (`Path`): The TOML file.

    Returns:
    * (`SCMachine`): The machine and its tool table.

    Raises:
    * `ValueError`:
      If the file is not valid TOML, a setting is missing or has the
      wrong type, or the machine or a tool makes no sense.
    """
    # Read the file.
    try:
        data: dict[str, object] = tomllib.loads(path.read_text("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path}: {error}") from error
    machine: object = data.get("machine")
    tools: object = data.get("tools", [])
    # Every problem with the file is a `ValueError` (not a `TypeError`
    # for a wrong type), so a caller has one error to catch.
    if not isinstance(machine, dict) or not isinstance(tools, list):
        raise ValueError(  # noqa: TRY004
            f"{path}: needs a [machine] table and [[tools]]"
        )

    # Build the tools, then the machine, with the file named in any
    # error.
    try:
        return SCMachine(
            name=_get(machine, "name", str),
            z_safe=_get(machine, "z_safe", float),
            clearance=_get(machine, "clearance", float),
            tool_change_z=_get(machine, "tool_change_z", float),
            tool_change=_get(machine, "tool_change", str),
            rapid_speed=_get(machine, "rapid_speed", float),
            drill_cycle=cast(DrillCycle, _get(machine, "drill_cycle", str)),
            stepover=_get(machine, "stepover", float),
            ramp_angle=_get(machine, "ramp_angle", float),
            tools=tuple(_tool(entry) for entry in tools),
        )
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


# Function `_tool()`:
def _tool(entry: object) -> SCTool:
    """Return a tool from its `[[tools]]` table.

    Arguments:
    * `entry` (`object`): The table.

    Returns:
    * (`SCTool`): The tool.

    Raises:
    * `ValueError`: If a setting is missing or has the wrong type.
    """
    if not isinstance(entry, dict):
        raise ValueError(  # noqa: TRY004 (a file problem; see above)
            f"a [[tools]] entry is not a table: {entry!r}"
        )
    return SCTool(
        number=_get(entry, "number", int),
        name=_get(entry, "name", str),
        kind=cast(ToolKind, _get(entry, "kind", str)),
        diameter=_get(entry, "diameter", float),
        rpm=_get(entry, "rpm", float),
        feed=_get(entry, "feed", float),
        plunge=_get(entry, "plunge", float),
        peck=_get(entry, "peck", float, 0.0),
    )


# Function `_get()`:
def _get(
    table: dict[str, object],
    key: str,
    kind: type[Setting],
    default: Setting | None = None,
) -> Setting:
    """Return one setting from a table, checking its type.

    Arguments:
    * `table` (`dict[str, object]`): The table.
    * `key` (`str`): The setting's name.
    * `kind` (`type[Setting]`):
      Its type (an integer is taken as a float).
    * `default` (`Setting | None`): Its value when it is missing, or `None`
      when it is required.

    Returns:
    * (`Setting`): Its value.

    Raises:
    * `ValueError`: If it is missing (and required) or of another type.
    """
    value: object = table.get(key, default)
    if value is None:
        raise ValueError(f"{key} is missing")
    if (
        kind is float
        and isinstance(value, int)
        and not isinstance(value, bool)
    ):
        value = float(value)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 (a file problem)
            f"{key} = {value!r} is not a {kind.__name__}"
        )
    return value
