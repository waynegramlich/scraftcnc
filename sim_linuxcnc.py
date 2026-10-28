#!/usr/bin/env python3
"""Run a program in the LinuxCNC simulator and poll the tool position.

The simulation (`T.s2~3`).  It takes a running LinuxCNC out of
E-stop, turns it on and homes it, gives it the tool table of a shop's
machine (`--shop`, `--machine`), sets the work origin (`--origin`, the
machine coordinates of the program's zero, as G54), runs a program
(the one it has loaded, or `PROGRAM`) at a feed override
(`--speed`), and polls the position 20 times a second, printing a
line every second and writing every sample (time, G-code line, X, Y,
Z) to `--out`.  With `--solidcraft PORT`, every tool of the machine is
modeled (`sctoolmodel`) in a SolidCraft GUI, where
`solidcraftcnc_demo.py` has modeled the part, and the one in the
spindle is shown, following the position; behind it, the path it has
taken is shown, sketched beforehand (`RevealTrace`; unless
`--no-trace`).  SolidCraft's coordinates are the program's, in
millimeters:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
solidcraft --control 8080 &
./solidcraftcnc_demo.py 8080 > demo.ngc
distrobox enter lcnc -- ./sim_linuxcnc.py demo.ngc --speed 5 \
    --solidcraft 8080
```

`lcnc_sim/shop_mill.ini` simulates the example shop's mill.  The
`linuxcnc` module comes with LinuxCNC, which is installed only in the
`lcnc` Debian Trixie box (see `TASKS/3_Simulation/Context.md`), so
this runs there.  The positions are work coordinates (the program's),
in the machine's units.
"""

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path

# The `linuxcnc` module has no type hints, so it is `Any` to `mypy`,
# and it is only in the `lcnc` box, so the checkers on the host do
# not find it.
# pylint: disable-next=import-error
import linuxcnc  # type: ignore[import-not-found]

from scplot import Move, command_moves, draw_moves, read_gcode
from scraftpybind import JSON, SolidCraftError, SolidCraftPyBind, connect
from sctoolmodel import model, profile
from shops import cnc_machine, loaded_tools, read

# How often to poll (seconds).
POLL: float = 0.05

# The shop and machine whose tools are loaded, by default.
SHOP_FILE: Path = (
    Path(__file__).resolve().parent / "examples/shop/home_shop.toml"
)
MACHINE: str = "Shop mill"

# The machine coordinates (inches) of the program's zero, by default:
# well inside `lcnc_sim/shop_mill.ini`'s travel (X 0 to 18, Y 0 to 9,
# Z -16 to 0), with room above the work for a 2 inch tool change
# height.
ORIGIN: tuple[float, float, float] = (4.0, 3.0, -6.0)

# SolidCraft's coordinates are millimeters.
MM_PER_INCH: float = 25.4

# The tools' color in SolidCraft.
TOOL_COLOR: str = "#e07020"

# A position: X, Y and Z (inches, program coordinates).
Position = tuple[float, float, float]

# The trace's sketches are named this, then their G-code lines.
TRACE_NAME: str = "Trace"


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


# Class `RevealTrace`:
# It keeps which sketches are shown between samples, so it is a class
# with one method.
class RevealTrace:  # pylint: disable=too-few-public-methods
    """The planned path, shown in SolidCraft as the tool reaches it.

    Drawing the path as the tool goes is slow, since every change to a
    sketch makes SolidCraft (0.25) refresh the whole design, while
    showing a hidden sketch is cheap (4 to 8 ms beside the demo's plate,
    by `probe_reveal.py`).  So the path is drawn beforehand, a hidden
    3D sketch for each G-code line that moves (`TRACE_NAME` and the
    line: "Trace 27"), and each is shown when LinuxCNC's `motion_line`
    reaches its line (a long move shows all at once, as it starts).
    Sketch lines all look alike, so the planned path's own sketches
    (`scplot.sketch_path()`) would hide it: every sketch is hidden
    first, and they can be shown again from the browser.  The program
    is taken to be in inches.

    Attributes:
    * `next` (`int`): The index in `sketches` of the first not shown.
    * `sketches` (`list[tuple[int, str]]`): Each sketch's G-code line
      (from 1, as `motion_line` counts) and name, in order.
    * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
    """

    # Method `RevealTrace.__init__()`:
    def __init__(self, solidcraft: SolidCraftPyBind, program: Path) -> None:
        """Hide every sketch, and draw the program's path, hidden.

        Arguments:
        * `solidcraft` (`SolidCraftPyBind`): The SolidCraft session.
        * `program` (`Path`): The G-code file (as `SCCNC` writes it).
        """
        self.solidcraft: SolidCraftPyBind = solidcraft
        self.next: int = 0
        self.sketches: list[tuple[int, str]] = []
        solidcraft.browser.visibility(visible=False, folder="sketches")

        # Gather the moves by line, and draw each line's moves.
        lines: dict[int, list[Move]] = {}
        move: Move
        for move in command_moves(
            read_gcode(program.read_text(encoding="utf-8"))
        ):
            lines.setdefault(move["line"] + 1, []).append(move)
        line: int
        moves: list[Move]
        for line, moves in lines.items():
            name: str = f"{TRACE_NAME} {line}"
            solidcraft.sketch.create(plane="XY", name=name)
            solidcraft.sketch.options(
                sketch_3d=True,
                show_points=False,
                show_profile=False,
                show_constraints=False,
                show_dimensions=False,
            )
            draw_moves(solidcraft, moves, MM_PER_INCH)
            solidcraft.sketch.finish()
            solidcraft.browser.visibility(visible=False, items=[name])
            self.sketches.append((line, name))

    # Method `RevealTrace.reveal()`:
    def reveal(self, line: int) -> None:
        """Show every sketch of the path up to a line, in one command.

        Arguments:
        * `line` (`int`): The G-code line being run (from 1).
        """
        names: list[str] = []
        while (
            self.next < len(self.sketches)
            and self.sketches[self.next][0] <= line
        ):
            names.append(self.sketches[self.next][1])
            self.next += 1
        if names:
            self.solidcraft.browser.visibility(visible=True, items=names)


# Class `Simulator`:
class Simulator:
    """A connection to a running LinuxCNC.

    Attributes:
    * `command` (`linuxcnc.command`): Sends commands.
    * `errors` (`linuxcnc.error_channel`): Its error messages.
    * `stat` (`linuxcnc.stat`): Its status, read by `stat.poll()`.
    """

    # Method `Simulator.__init__()`:
    def __init__(self) -> None:
        """Connect to the running LinuxCNC."""
        self.command = linuxcnc.command()
        self.errors = linuxcnc.error_channel()
        self.stat = linuxcnc.stat()

    # Method `Simulator.report_errors()`:
    def report_errors(self) -> None:
        """Print any error messages LinuxCNC has sent."""
        error = self.errors.poll()
        while error:
            print(f"error: {error[1]}", file=sys.stderr)
            error = self.errors.poll()

    # Method `Simulator.wait_for()`:
    def wait_for(
        self, test: Callable[[], bool], what: str, timeout: float = 60.0
    ) -> None:
        """Poll the status until `test()` is true.

        Arguments:
        * `test` (`Callable[[], bool]`):
          Checks the freshly polled `stat`.
        * `what` (`str`):
          What is waited for, for the error message.
        * `timeout` (`float`):
          How long to wait (seconds).

        Raises:
        * `TimeoutError`: If `test()` is not true in time.
        """
        end: float = time.monotonic() + timeout
        while time.monotonic() < end:
            self.stat.poll()
            if test():
                return
            self.report_errors()
            time.sleep(POLL)
        raise TimeoutError(f"timed out waiting for {what}")

    # Method `Simulator.home()`:
    def home(self) -> None:
        """Take it out of E-stop, turn it on, and home every joint.

        Raises:
        * `TimeoutError`: If it does not turn on or home in time.
        """
        # Out of E-stop, and on.
        self.command.state(linuxcnc.STATE_ESTOP_RESET)
        self.command.state(linuxcnc.STATE_ON)
        self.wait_for(
            lambda: bool(self.stat.task_state == linuxcnc.STATE_ON),
            "the machine to turn on",
        )

        # Home in joint mode, in the configuration's `HOME_SEQUENCE`,
        # unless it is already homed (it refuses, since it is then
        # sitting on its home switches).
        if all(self.stat.homed[: self.stat.joints]):
            return
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.wait_complete()
        self.command.teleop_enable(False)
        self.command.wait_complete()
        self.command.home(-1)
        self.wait_for(
            lambda: all(self.stat.homed[: self.stat.joints]),
            "homing",
        )

    # Method `Simulator.load_tools()`:
    def load_tools(self, shop: Path, machine: str) -> Path:
        """Give LinuxCNC the tool table of a shop's machine.

        It is written over the tool table file named in LinuxCNC's
        INI file, and read back in.  Tool lengths are all zero.

        Arguments:
        * `shop` (`Path`):
          The shop's file.
        * `machine` (`str`):
          The machine's name.

        Returns:
        * (`Path`): The tool table file.
        """
        # Find the tool table file.
        self.stat.poll()
        ini_file: Path = Path(self.stat.ini_filename)
        table: Path = ini_file.parent / str(
            linuxcnc.ini(str(ini_file)).find("EMCIO", "TOOL_TABLE")
        )

        # Write it, and read it back in.
        lines: list[str] = [
            f"T{tool.number} P{tool.number} Z0 D{tool.diameter:.4f} "
            f";{tool.name}"
            for tool in cnc_machine(read(shop), machine).tools
        ]
        table.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.command.load_tool_table()
        self.command.wait_complete()
        return table

    # Method `Simulator.set_origin()`:
    def set_origin(self, origin: tuple[float, float, float]) -> None:
        """Set the G54 work origin, as the operator would touch off.

        Arguments:
        * `origin` (`tuple[float, float, float]`):
          The machine coordinates (inches) of the program's zero.
        """
        x, y, z = origin
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete()
        # `G20` first: otherwise the numbers may be read as millimeters.
        self.command.mdi(f"G20 G10 L2 P1 X{x} Y{y} Z{z}")
        self.command.wait_complete()

    # Method `Simulator.start()`:
    def start(self, program: str, speed: float) -> str:
        """Load a program and start running it.

        Arguments:
        * `program` (`str`):
          The G-code file, or `""` for the one already loaded.
        * `speed` (`float`):
          The feed override (1 for the programmed feeds), limited by
          the INI file's `MAX_FEED_OVERRIDE` and the axes' speeds.

        Returns:
        * (`str`): The file that runs.
        """
        self.command.mode(linuxcnc.MODE_AUTO)
        self.command.wait_complete()
        self.stat.poll()
        path: str = str(Path(program).resolve()) if program else self.stat.file
        self.command.program_open(path)
        self.command.wait_complete()
        self.command.feedrate(speed)
        self.command.auto(linuxcnc.AUTO_RUN, 0)
        return path

    # Method `Simulator.stop()`:
    def stop(self) -> None:
        """Stop the program, as the operator's stop button would."""
        self.command.abort()
        self.command.wait_complete()

    # Method `Simulator.work_position()`:
    def work_position(self) -> tuple[float, float, float]:
        """Return the polled position in work (program) coordinates.

        Returns:
        * (`tuple[float, float, float]`): X, Y and Z: the machine
          position less the G54 (or other G5x), G92 and tool length
          offsets.
        """
        stat = self.stat
        x, y, z = (
            stat.actual_position[axis]
            - stat.g5x_offset[axis]
            - stat.g92_offset[axis]
            - stat.tool_offset[axis]
            for axis in range(3)
        )
        return (x, y, z)

    # Method `Simulator.follow()`:
    def follow(
        self, out: Path, rack: ToolRack | None, trace: RevealTrace | None
    ) -> int:
        """Poll the position until the program ends.

        The polls keep to a fixed schedule, so that the time each one
        takes (moving the tool in SolidCraft can take 50 ms) does not
        slow them down; a late poll is not made up.

        Arguments:
        * `out` (`Path`):
          The file every sample is written to.
        * `rack` (`ToolRack | None`):
          The tools in SolidCraft, whose one in the spindle follows
          the position, if any.
        * `trace` (`RevealTrace | None`):
          The path shown in SolidCraft as the tool reaches it, if any.

        Returns:
        * (`int`): The number of samples.
        """
        # Let the interpreter leave its idle state first.
        start: float = time.monotonic()
        tick: float = start
        samples: int = 0
        time.sleep(4 * POLL)
        with out.open("w", encoding="utf-8") as samples_file:
            while True:
                # Write a sample, and print one each second.
                self.stat.poll()
                now: float = time.monotonic() - start
                line: int = self.stat.motion_line
                x, y, z = self.work_position()
                sample: str = (
                    f"{now:8.3f} {line:5d} {x:9.4f} {y:9.4f} {z:9.4f}"
                )
                samples_file.write(sample + "\n")
                samples += 1
                if samples % round(1.0 / POLL) == 0:
                    print(sample, flush=True)
                if rack is not None:
                    rack.move_to(self.stat.tool_in_spindle, (x, y, z))
                if trace is not None:
                    trace.reveal(line)

                # Stop when the program is done, showing all its path.
                self.report_errors()
                if self.stat.interp_state == linuxcnc.INTERP_IDLE:
                    if trace is not None:
                        trace.reveal(sys.maxsize)
                    return samples
                tick = max(tick + POLL, time.monotonic())
                time.sleep(max(0.0, tick - time.monotonic()))


# Function `run()`:
def run(
    options: argparse.Namespace,
    rack: ToolRack | None,
    trace: RevealTrace | None,
) -> int:
    """Set the simulator up, run the program and follow it.

    When SolidCraft fails or stops answering (as when its window is
    closed), or on Ctrl-C, the program is stopped.

    Arguments:
    * `options` (`argparse.Namespace`):
      The command line arguments.
    * `rack` (`ToolRack | None`):
      The tools in SolidCraft, whose one in the spindle follows the
      position, if any.
    * `trace` (`RevealTrace | None`):
      The path shown in SolidCraft as the tool reaches it, if any.

    Returns:
    * (`int`): The exit status.
    """
    simulator: Simulator = Simulator()
    simulator.home()
    print("tools:", simulator.load_tools(options.shop, options.machine))
    simulator.set_origin(tuple(options.origin))
    print("running", simulator.start(options.program, options.speed))
    start: float = time.monotonic()

    # Closing SolidCraft (or Ctrl-C) stops the program too.
    try:
        samples: int = simulator.follow(options.out, rack, trace)
    except (SolidCraftError, OSError, KeyboardInterrupt) as error:
        simulator.stop()
        why: str = (
            "interrupted"
            if isinstance(error, KeyboardInterrupt)
            else (
                "SolidCraft failed or stopped answering "
                f"({type(error).__name__}: {error})"
            )
        )
        print(f"{why}: the program is stopped", file=sys.stderr)
        return 1
    print(
        f"done: {samples} samples in {time.monotonic() - start:.1f} s, "
        f"in {options.out}"
    )
    return 0


# Function `program_file()`:
def program_file(program: str) -> Path:
    """Return the program's file: the one named, or the one loaded.

    Arguments:
    * `program` (`str`): The G-code file named ("" for none).

    Returns:
    * (`Path`): The file.
    """
    if program:
        return Path(program)
    stat: linuxcnc.stat = linuxcnc.stat()
    stat.poll()
    return Path(stat.file)


# Function `main()`:
def main() -> int:
    """Home the simulator, run the program and follow it.

    Returns:
    * (`int`): The exit status.
    """
    # Read the arguments.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run a program in LinuxCNC and poll the position."
    )
    parser.add_argument(
        "program",
        nargs="?",
        default="",
        help="the G-code file (default: the one loaded)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sim_positions.txt"),
        help="where the samples go (default: sim_positions.txt)",
    )
    parser.add_argument(
        "--origin",
        type=float,
        nargs=3,
        default=ORIGIN,
        metavar=("X", "Y", "Z"),
        help="machine coordinates of the program's zero "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="feed override (default: 1; at most 10 in shop_mill.ini)",
    )
    parser.add_argument(
        "--shop",
        type=Path,
        default=SHOP_FILE,
        help="the shop whose machine's tools are loaded",
    )
    parser.add_argument(
        "--machine",
        default=MACHINE,
        help="that machine's name (default: %(default)s)",
    )
    parser.add_argument(
        "--solidcraft",
        metavar="PORT",
        default="",
        help="a SolidCraft GUI's control port, where a tool follows",
    )
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="do not show the path in SolidCraft as the tool goes",
    )
    options: argparse.Namespace = parser.parse_args()

    # Run it, with a tool in SolidCraft if asked to.  A LinuxCNC or a
    # SolidCraft that is not there is reported in one line.
    try:
        if not options.solidcraft:
            return run(options, None, None)
        with connect(options.solidcraft) as transport:
            solidcraft: SolidCraftPyBind = SolidCraftPyBind(transport)
            rack: ToolRack = ToolRack(
                solidcraft, loaded_tools(read(options.shop), options.machine)
            )
            if options.no_trace:
                return run(options, rack, None)
            start: float = time.monotonic()
            trace: RevealTrace = RevealTrace(
                solidcraft, program_file(options.program)
            )
            print(
                f"trace: {len(trace.sketches)} sketches in "
                f"{time.monotonic() - start:.1f} s",
                flush=True,
            )
            return run(options, rack, trace)
    except (
        linuxcnc.error,
        SolidCraftError,
        TimeoutError,
        OSError,
        ValueError,
    ) as error:
        print(f"sim_linuxcnc.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
