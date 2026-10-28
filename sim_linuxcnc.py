#!/usr/bin/env python3
"""Run a program in the LinuxCNC simulator and poll the tool position.

The third step of the simulation (`T.s2~3`).  It takes a running
LinuxCNC out of E-stop, turns it on, homes it, runs a program (the one
it has loaded, or `PROGRAM`), and polls the position 20 times a
second, printing a line every second and writing every sample (time,
G-code line, X, Y, Z) to `--out`:

```
distrobox enter lcnc -- linuxcnc ~/linuxcnc/configs/sim/axis/axis.ini &
distrobox enter lcnc -- ./sim_linuxcnc.py [PROGRAM] [--out FILE]
```

The `linuxcnc` module comes with LinuxCNC, which is installed only in
the `lcnc` Debian Trixie box (see `TASKS/3_Simulation/Context.md`), so
this runs there.  The positions are machine coordinates, in the
machine's units.
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

# How often to poll (seconds).
POLL: float = 0.05


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

    # Method `Simulator.start()`:
    def start(self, program: str) -> str:
        """Load a program and start running it.

        Arguments:
        * `program` (`str`):
          The G-code file, or `""` for the one already loaded.

        Returns:
        * (`str`): The file that runs.
        """
        self.command.mode(linuxcnc.MODE_AUTO)
        self.command.wait_complete()
        self.stat.poll()
        path: str = program or str(self.stat.file)
        self.command.program_open(path)
        self.command.wait_complete()
        self.command.auto(linuxcnc.AUTO_RUN, 0)
        return path

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
                x, y, z = self.stat.actual_position[:3]
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
    options: argparse.Namespace = parser.parse_args()

    # Run it.
    try:
        simulator: Simulator = Simulator()
        simulator.home()
        print("homed; running", simulator.start(options.program))
        start: float = time.monotonic()
        samples: int = simulator.follow(options.out)
    except (linuxcnc.error, TimeoutError) as error:
        print(f"sim_linuxcnc.py: {error}", file=sys.stderr)
        return 1
    print(
        f"done: {samples} samples in {time.monotonic() - start:.1f} s, "
        f"in {options.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
