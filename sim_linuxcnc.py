#!/usr/bin/env python3
"""Run a program in the LinuxCNC simulator and poll the tool position.

The tracking side of the simulation (`T.tl~3.2`).  It takes a running
LinuxCNC out of E-stop, turns it on and homes it, gives it the tool
table of a shop's machine (`--shop`, `--machine`; each tool's length
is its overall length), sets the work origin (`--origin`, the machine
coordinates of the program's zero for a tool of no length, as G54),
runs a program (the one it has loaded, or `PROGRAM`) at a feed
override (`--speed`, 10 times the programmed feeds by default; rapids
stay at the machine's), and polls the position 20 times a second,
printing a line every second and writing every sample (time, G-code
line, X, Y, Z) to `--out`.  Each sample (a `Sample`, which also has
the tool in the spindle) is handed to listeners (`Listener`); when one
fails, or on Ctrl-C, the program is stopped.

The one listener so far is `sim_solidcraft.py`'s `SolidCraftDisplay`
(`T.rlg~3.3`), turned on by `--solidcraft PORT` (or `headless`):
every tool of the machine is modeled in SolidCraft, where
`solidcraftcnc_demo.py` has modeled the part, and the one in the
spindle follows the position; the whole planned path is the
demo's own sketches:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
solidcraft --control 8080 &
./solidcraftcnc_demo.py --no-path 8080 > demo.ngc
distrobox enter lcnc -- ./sim_linuxcnc.py demo.ngc --solidcraft 8080
distrobox enter lcnc -- ./stop_linuxcnc.py    # Close LinuxCNC quietly.
```

`lcnc_sim/shop_mill.ini` simulates the example shop's mill.  The
`linuxcnc` module comes with LinuxCNC, which is installed only in the
`lcnc` Debian Trixie box (see `TASKS/3_Simulation/Context.md`), so
this runs there.  The positions are work coordinates (the program's,
of the tool's tip), in the machine's units.
"""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from operator import methodcaller
from pathlib import Path
from typing import Protocol

# The `linuxcnc` module has no type hints, so it is `Any` to `mypy`,
# and it is only in the `lcnc` box, so the checkers on the host do
# not find it.
# pylint: disable-next=import-error
import linuxcnc  # type: ignore[import-not-found]

import sim_solidcraft
from scraftpybind import SolidCraftError
from shops import LENGTH, cnc_machine, loaded_tools, measure, read

# How often to poll (seconds).
POLL: float = 0.05

# The feed override, by default: as fast as `lcnc_sim/shop_mill.ini`
# allows (its `MAX_FEED_OVERRIDE`), which is pleasant to watch (the
# demo takes about 5 minutes instead of 20).
SPEED: float = 10.0

# The shop and machine whose tools are loaded, by default.
SHOP_FILE: Path = (
    Path(__file__).resolve().parent / "examples/shop/home_shop.toml"
)
MACHINE: str = "Shop mill"

# The machine coordinates (inches) of the program's zero, by default:
# well inside `lcnc_sim/shop_mill.ini`'s travel (X 0 to 18, Y 0 to 9,
# Z -16 to 0), with room above the work for a 2 inch tool change
# height with the longest tool (3-7/8 in).
ORIGIN: tuple[float, float, float] = (4.0, 3.0, -6.0)

# A position: X, Y and Z (inches, program coordinates).
Position = tuple[float, float, float]


# Class `Sample`:
@dataclass(frozen=True, slots=True)
class Sample:
    """One poll of LinuxCNC: where the tool was, and when.

    Attributes:
    * `time` (`float`): Seconds since the program started.
    * `line` (`int`): The G-code line being run (`motion_line`,
      from 1).
    * `position` (`Position`): The tool tip's X, Y and Z (work
      coordinates, in the machine's units).
    * `tool` (`int`): The T number of the tool in the spindle (0 for
      none).

    Constructor:
    * `Sample(time, line, position, tool)`
    """

    # Constructor arguments:
    time: float = field(init=True)
    line: int = field(init=True)
    position: Position = field(init=True)
    tool: int = field(init=True)

    # Method `Sample.text()`:
    def text(self) -> str:
        """Return the sample as a line of `--out` (no tool).

        Returns:
        * (`str`): Time, line, X, Y and Z, in columns.
        """
        x, y, z = self.position
        return f"{self.time:8.3f} {self.line:5d} {x:9.4f} {y:9.4f} {z:9.4f}"


# Class `Listener`:
class Listener(Protocol):
    """Something that follows the samples (such as a display).

    An exception from either method stops the program.
    """

    # Method `Listener.sample()`:
    def sample(self, sample: Sample) -> None:
        """Take one sample.

        Arguments:
        * `sample` (`Sample`): The sample.
        """

    # Method `Listener.finish()`:
    def finish(self) -> None:
        """Take the end of the program (after its last sample)."""


# Class `ListenerFailed`:
class ListenerFailed(Exception):
    """A listener failed, so the program was stopped."""


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
        INI file, and read back in.  Each tool's length (its `Z`,
        which `G43` takes off) is its overall length from the tools
        files.

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

        # Write it, and read it back in.  The real length (the gauge
        # length) is how far the tip sticks out of the spindle, which
        # depends on the holder and on how far the tool sticks out of
        # it; the shop files do not have those yet, so the tool's
        # overall length stands in for it.
        described: dict[str, object] = read(shop)
        lengths: dict[int, float] = {
            number: measure(tool["overall_length"], LENGTH)
            for number, (_, tool) in loaded_tools(described, machine).items()
        }
        lines: list[str] = [
            f"T{tool.number} P{tool.number} Z{lengths[tool.number]:.4f} "
            f"D{tool.diameter:.4f} ;{tool.name}"
            for tool in cnc_machine(described, machine).tools
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
    def follow(self, out: Path, listeners: Sequence[Listener]) -> int:
        """Poll the position until the program ends.

        The polls keep to a fixed schedule, so that the time each one
        takes (a listener moving the tool in SolidCraft can take
        50 ms) does not slow them down; a late poll is not made up.

        Arguments:
        * `out` (`Path`):
          The file every sample is written to.
        * `listeners` (`Sequence[Listener]`):
          What each sample is handed to, in order.

        Returns:
        * (`int`): The number of samples.

        Raises:
        * `ListenerFailed`: If a listener raised an exception.
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
                sample: Sample = Sample(
                    time.monotonic() - start,
                    self.stat.motion_line,
                    self.work_position(),
                    self.stat.tool_in_spindle,
                )
                samples_file.write(sample.text() + "\n")
                samples += 1
                if samples % round(1.0 / POLL) == 0:
                    print(sample.text(), flush=True)
                _tell(listeners, methodcaller("sample", sample))

                # Stop when the program is done, and say so.
                self.report_errors()
                if self.stat.interp_state == linuxcnc.INTERP_IDLE:
                    _tell(listeners, methodcaller("finish"))
                    return samples
                tick = max(tick + POLL, time.monotonic())
                time.sleep(max(0.0, tick - time.monotonic()))


# Function `_tell()`:
def _tell(
    listeners: Sequence[Listener], call: Callable[[Listener], None]
) -> None:
    """Call each listener, turning its failure into `ListenerFailed`.

    Arguments:
    * `listeners` (`Sequence[Listener]`): The listeners.
    * `call` (`Callable[[Listener], None]`): What to call on each.

    Raises:
    * `ListenerFailed`: If a listener raised an exception (any kind,
      since whatever it is, the program must stop).
    """
    for listener in listeners:
        try:
            call(listener)
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise ListenerFailed(
                f"{type(listener).__name__} failed "
                f"({type(error).__name__}: {error})"
            ) from error


# Function `run()`:
def run(options: argparse.Namespace, listeners: Sequence[Listener]) -> int:
    """Set the simulator up, run the program and follow it.

    When a listener fails (as `sim_solidcraft.SolidCraftDisplay` does
    when SolidCraft stops answering, or its window is closed), when the
    samples can not be written, or on Ctrl-C, the program is stopped.

    Arguments:
    * `options` (`argparse.Namespace`):
      The command line arguments.
    * `listeners` (`Sequence[Listener]`):
      What each sample is handed to.

    Returns:
    * (`int`): The exit status.
    """
    simulator: Simulator = Simulator()
    simulator.home()
    print("tools:", simulator.load_tools(options.shop, options.machine))
    simulator.set_origin(tuple(options.origin))
    print("running", simulator.start(options.program, options.speed))
    start: float = time.monotonic()

    # A failed listener (or Ctrl-C) stops the program too.
    try:
        samples: int = simulator.follow(options.out, listeners)
    except (ListenerFailed, OSError, KeyboardInterrupt) as error:
        simulator.stop()
        why: str = (
            "interrupted"
            if isinstance(error, KeyboardInterrupt)
            else str(error)
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
        default=SPEED,
        help="feed override (default: %(default)s, the most "
        "shop_mill.ini allows; 1 for the programmed feeds)",
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
    sim_solidcraft.add_arguments(parser)
    options: argparse.Namespace = parser.parse_args()

    # Run it, with the tool in SolidCraft if asked to.  A LinuxCNC or a
    # SolidCraft that is not there is reported in one line.
    try:
        if not options.solidcraft:
            return run(options, [])
        with sim_solidcraft.display(
            options, program_file(options.program)
        ) as display:
            return run(options, [display])
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
