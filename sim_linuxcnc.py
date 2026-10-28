#!/usr/bin/env python3
"""Run a program in the LinuxCNC simulator and poll the tool position.

The simulation (`T.s2~3`).  It takes a running LinuxCNC out of
E-stop, turns it on and homes it, gives it the tool table of a shop's
machine (`--shop`, `--machine`), sets the work origin (`--origin`, the
machine coordinates of the program's zero, as G54), runs a program
(the one it has loaded, or `PROGRAM`) at a feed override
(`--speed`), and polls the position 20 times a second, printing a
line every second and writing every sample (time, G-code line, X, Y,
Z) to `--out`:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini &
./solidcraftcnc_demo.py > demo.ngc
distrobox enter lcnc -- ./sim_linuxcnc.py demo.ngc --speed 5
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

from shops import cnc_machine, read

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
    def follow(self, out: Path) -> int:
        """Poll the position until the program ends.

        Arguments:
        * `out` (`Path`):
          The file every sample is written to.

        Returns:
        * (`int`): The number of samples.
        """
        # Let the interpreter leave its idle state first.
        start: float = time.monotonic()
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

                # Stop when the program is done.
                self.report_errors()
                if self.stat.interp_state == linuxcnc.INTERP_IDLE:
                    return samples
                time.sleep(POLL)


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
    options: argparse.Namespace = parser.parse_args()

    # Run it.
    try:
        simulator: Simulator = Simulator()
        simulator.home()
        print("tools:", simulator.load_tools(options.shop, options.machine))
        simulator.set_origin(tuple(options.origin))
        print("running", simulator.start(options.program, options.speed))
        start: float = time.monotonic()
        samples: int = simulator.follow(options.out)
    except (linuxcnc.error, TimeoutError, OSError, ValueError) as error:
        print(f"sim_linuxcnc.py: {error}", file=sys.stderr)
        return 1
    print(
        f"done: {samples} samples in {time.monotonic() - start:.1f} s, "
        f"in {options.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
