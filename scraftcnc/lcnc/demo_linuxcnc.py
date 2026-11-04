#!/usr/bin/env python3
"""Run a program in LinuxCNC's simulator from start to finish, as a test.

This runs on this computer, outside the target, and uses only what any
other program would: it starts `serve_linuxcnc.py`, connects to the
port, and through JSON turns the machine on, homes it, moves it by
MDI, and runs a G-code program, checking where the machine ends up.  It
then asks the bridge to shut down, and checks that LinuxCNC has gone:

```
install_linuxcnc
demo_linuxcnc
```
"""

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from . import install_linuxcnc
from .install_linuxcnc import stamp
from .lcnc_client import SCBridgeError, SCClient, constant
from .serve_linuxcnc import serving

# How long LinuxCNC may take to start, and to shut down (seconds).
START_TIME: float = 300.0
STOP_TIME: float = 120.0

# How long the machine may take to do what it is told (seconds).
MOVE_TIME: float = 120.0

# How near a position must be (inches).
NEAR: float = 0.0001

# The program, where it must end, and how far along X the samples must
# see it go on the way.
PROGRAM: str = """G20 G90
G0 X1 Y2
G1 Z-0.5 F600
G1 X5 Y3 F600
G0 Z0
G0 X3 Y4
M2
"""
PROGRAM_END: tuple[float, float, float] = (3.0, 4.0, 0.0)
PROGRAM_FAR_X: float = 4.0


# Function `wait_for()`:
def wait_for(what: str, ready: Callable[[], bool]) -> None:
    """Wait until something is true.

    Arguments:
    * `what` (`str`): What is being waited for, to report it.
    * `ready` (`Callable[[], bool]`): Tells whether it is true yet.

    Raises:
    * `RuntimeError`: If it does not become true in `MOVE_TIME`.
    """
    end: float = time.monotonic() + MOVE_TIME
    while not ready():
        if time.monotonic() > end:
            raise RuntimeError(f"Timed out waiting for {what}.")
        time.sleep(0.05)


# Function `check_position()`:
def check_position(lcnc: SCClient, wanted: tuple[float, float, float]) -> None:
    """Check where the machine is.

    Arguments:
    * `lcnc` (`SCClient`): The connection.
    * `wanted` (`tuple[float, float, float]`): Its X, Y and Z.

    Raises:
    * `RuntimeError`: If it is somewhere else.
    """
    # LinuxCNC gives all nine axes (X Y Z A B C U V W); X, Y, Z are checked.
    position: list[float] = lcnc.stat("actual_position")["actual_position"]
    if any(
        abs(a - b) > NEAR for a, b in zip(position[:3], wanted, strict=True)
    ):
        raise RuntimeError(f"At {position[:3]}, not {wanted}.")


# Function `check_protocol()`:
def check_protocol(lcnc: SCClient) -> None:
    """Check the calls that do not move the machine.

    Arguments:
    * `lcnc` (`SCClient`): The connection.

    Raises:
    * `RuntimeError`: If an answer is wrong.
    """
    # What it is, and what it knows.
    print(f"{stamp()} ping: {lcnc.call('ping')}", flush=True)
    constants: dict[str, Any] = lcnc.call("constants")
    if "MODE_MDI" not in constants:
        raise RuntimeError("The constants have no MODE_MDI.")
    print(f"{stamp()} {len(constants)} constants", flush=True)

    # Every `stat` attribute must get through JSON.
    stat: dict[str, Any] = lcnc.stat()
    print(f"{stamp()} {len(stat)} stat attributes", flush=True)
    if stat.get("joints") != 3:
        raise RuntimeError(f"Expected 3 joints: {stat.get('joints')}.")
    if lcnc.call("ini.find", "KINS", "JOINTS") != "3":
        raise RuntimeError("`ini.find` did not read the INI file.")

    # What must be refused, with the connection still good afterwards.
    for name in ("command.__class__", "command.nope", "eval", "stat.poll"):
        try:
            lcnc.call(name)
        except SCBridgeError:
            continue
        raise RuntimeError(f"{name} was not refused.")
    try:
        lcnc.call("program.write", "../escaped.ngc", "M2\n")
    except SCBridgeError:
        pass
    else:
        raise RuntimeError("A path outside `programs/` was not refused.")


# Function `prepare()`:
def prepare(lcnc: SCClient) -> None:
    """Turn the machine on and home it.

    Arguments:
    * `lcnc` (`SCClient`): The connection.
    """
    # On.
    constants: dict[str, Any] = lcnc.call("constants")
    lcnc.call("command.state", constant("STATE_ESTOP_RESET"))
    lcnc.call("command.state", constant("STATE_ON"))
    wait_for(
        "the machine to turn on",
        lambda: lcnc.stat("task_state")["task_state"] == constants["STATE_ON"],
    )

    # Homed.
    lcnc.call("command.mode", constant("MODE_MANUAL"))
    lcnc.call("command.wait_complete")
    lcnc.call("command.teleop_enable", False)
    lcnc.call("command.wait_complete")
    lcnc.call("command.home", -1)

    def homed() -> bool:
        stat: dict[str, Any] = lcnc.stat("homed", "joints")
        return all(stat["homed"][: stat["joints"]])

    wait_for("the machine to home", homed)
    print(f"{stamp()} On and homed.", flush=True)


# Function `move_by_mdi()`:
def move_by_mdi(lcnc: SCClient) -> None:
    """Move the machine with one line of G-code, and check it.

    Arguments:
    * `lcnc` (`SCClient`): The connection.
    """
    lcnc.call("command.mode", constant("MODE_MDI"))
    lcnc.call("command.wait_complete")
    # LinuxCNC keeps G54 from its last run, whoever set it.
    lcnc.call("command.mdi", "G20 G10 L2 P1 X0 Y0 Z0")
    lcnc.call("command.wait_complete")
    lcnc.call("command.mdi", "G20 G90 G0 X1 Y1")
    lcnc.call("command.wait_complete", MOVE_TIME)
    check_position(lcnc, (1.0, 1.0, 0.0))
    print(f"{stamp()} MDI moved it.", flush=True)


# Function `run_program()`:
def run_program(lcnc: SCClient) -> None:
    """Send and run the G-code program, following the machine.

    Arguments:
    * `lcnc` (`SCClient`): The connection.

    Raises:
    * `RuntimeError`: If the machine did not go where it should.
    """
    # Send and start it.
    constants: dict[str, Any] = lcnc.call("constants")
    path: str = lcnc.call("program.write", "demo.ngc", PROGRAM)
    print(f"{stamp()} Sent {path}", flush=True)
    lcnc.call("command.mode", constant("MODE_AUTO"))
    lcnc.call("command.wait_complete")
    lcnc.call("command.program_open", path)
    lcnc.call("command.wait_complete")
    lcnc.call("command.auto", constant("AUTO_RUN"), 0)

    # Follow it to its end.
    samples: list[float] = []
    started: bool = False

    def finished() -> bool:
        nonlocal started
        stat: dict[str, Any] = lcnc.stat("actual_position", "interp_state")
        samples.append(stat["actual_position"][0])
        idle: bool = stat["interp_state"] == constants["INTERP_IDLE"]
        started = started or not idle
        return started and idle

    wait_for("the program to finish", finished)

    # Check where it went.
    print(f"{stamp()} {len(samples)} samples", flush=True)
    if max(samples) < PROGRAM_FAR_X:
        raise RuntimeError(f"X only reached {max(samples)}.")
    check_position(lcnc, PROGRAM_END)
    print(f"{stamp()} The program ran.", flush=True)


# Function `exercise()`:
def exercise() -> None:
    """Do the whole test through one connection.

    Raises:
    * `RuntimeError`: If anything is wrong, or LinuxCNC reports errors.
    """
    with SCClient() as lcnc:
        check_protocol(lcnc)
        prepare(lcnc)
        move_by_mdi(lcnc)
        run_program(lcnc)

        # LinuxCNC must have nothing to complain about.
        errors: list[Any] = []
        while (error := lcnc.call("error_channel.poll")) is not None:
            errors.append(error)
        if errors:
            raise RuntimeError(f"LinuxCNC reported errors: {errors}")
        lcnc.call("shutdown")


# Function `stop_server()`:
def stop_server(server: subprocess.Popen[bytes]) -> None:
    """Stop `serve_linuxcnc.py` after a failure.

    The bridge is asked first, since on Windows `terminate()` leaves
    no chance to stop LinuxCNC in the target.

    Arguments:
    * `server` (`subprocess.Popen[bytes]`): The server.
    """
    try:
        with SCClient(timeout=10.0) as lcnc:
            lcnc.call("shutdown")
        server.wait(timeout=STOP_TIME)
    except (OSError, SCBridgeError, subprocess.TimeoutExpired):
        server.terminate()


# Function `demonstrate()`:
def demonstrate(target_arguments: list[str]) -> int:
    """Start the server, run the test, and check that it stopped.

    Arguments:
    * `target_arguments` (`list[str]`):
      The arguments that `serve_linuxcnc.py` needs to find the target.

    Returns:
    * (`int`): The exit status (0 when it passed).
    """
    command: list[str] = [
        sys.executable,
        "-u",
        "-m",
        "scraftcnc.lcnc.serve_linuxcnc",
        *target_arguments,
    ]
    started: float = time.monotonic()
    with subprocess.Popen(command) as server:
        failure: str = ""
        try:
            # It is ready when its port answers.
            end: float = started + START_TIME
            while not serving():
                if server.poll() is not None:
                    raise RuntimeError("LinuxCNC stopped while starting.")
                if time.monotonic() > end:
                    raise RuntimeError("The port never answered.")
                time.sleep(1.0)
            seconds: float = time.monotonic() - started
            print(f"{stamp()} The port answered in {seconds:.0f} s.")

            # The test, and LinuxCNC's own shut down.
            exercise()
            status: int = server.wait(timeout=STOP_TIME)
            if status != 0:
                failure = f"serve_linuxcnc.py exited with {status}."
            elif serving():
                failure = "The port still answers after the shutdown."
        except (RuntimeError, OSError, SCBridgeError) as error:
            failure = str(error)
        except subprocess.TimeoutExpired:
            failure = "LinuxCNC did not shut down."
        finally:
            if server.poll() is None:
                stop_server(server)

    # The verdict.
    minutes: float = (time.monotonic() - started) / 60.0
    if failure:
        print(f"{stamp()} demo FAILED: {failure}", file=sys.stderr)
        return 1
    print(f"{stamp()} demo PASSED in {minutes:.1f} min.", flush=True)
    return 0


# Function `main()`:
def main() -> int:
    """Run the demonstration, as the command line asks.

    Returns:
    * (`int`): The exit status (0 when it passed).
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run a program in LinuxCNC's simulator, as a test."
    )
    install_linuxcnc.add_target_arguments(parser)
    arguments: argparse.Namespace = parser.parse_args()
    target_arguments: list[str] = [
        "--box",
        arguments.box,
        "--distribution",
        arguments.distribution,
    ]
    if arguments.route:
        target_arguments += ["--route", arguments.route]
    return demonstrate(target_arguments)


if __name__ == "__main__":
    sys.exit(main())
