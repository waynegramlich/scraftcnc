#!/usr/bin/env python3
"""Run the demonstration's G-code in LinuxCNC, in the installed target.

`T.il~3.1`.  After `install_linuxcnc.py` has installed LinuxCNC's
simulator in its Debian Trixie target (a `distrobox` box, WSL's
Debian, a container or a QEMU VM), this shows that LinuxCNC runs a
program there, as the user that `install_linuxcnc.py` made (not
root):

1. The project's files are put in the target: a box sees them where
   they are; any other target gets a copy (`~/scraftcnc_demo`), sent
   in as a `tar` file (line endings made Unix ones).
2. In the target, this program runs again (`--inside`): it writes
   `demo.ngc` (`solidcraftcnc_demo.py`), starts an X server with no
   screen (`Xvfb`, installed in the target when it is missing) unless
   `--display` names a real one, starts LinuxCNC with
   `lcnc_sim/shop_mill.ini` (the AXIS screen), runs `sim_linuxcnc.py
   demo.ngc` to the end, closes LinuxCNC with `stop_linuxcnc.py`, and
   checks that nothing is left running.
3. It passes when `sim_linuxcnc.py` exits 0 with its samples and
   LinuxCNC sent no error messages.  LinuxCNC's "Unexpected realtime
   delay" messages (its 1 ms thread running late, as it may on a
   slow or emulated computer) are counted and shown, but do not fail
   it.

It takes the same target arguments as `install_linuxcnc.py`:

```
./demo_linuxcnc.py                    # The `lcnc` box, on Linux.
./demo_linuxcnc.py --box lcnc-test    # Another box.
./demo_linuxcnc.py --display :0       # Watch it on a real screen.
./demo_linuxcnc.py --yes              # Install `Xvfb` if needed.
```
"""

import argparse
import io
import os
import re
import select
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import install_linuxcnc
from install_linuxcnc import Target, run, stamp

# This project's directory, and the copy's in a target that does not
# see it.
PROJECT: Path = Path(__file__).resolve().parent
COPY: str = "scraftcnc_demo"

# The project's files that the demonstration needs (`glob` patterns).
FILES: tuple[str, ...] = (
    "*.py",
    "scplot_template.html",
    "lcnc_sim/*.ini",
    "lcnc_sim/*.tbl",
    "examples/shop/*.toml",
)

# The X server with no screen, and the package it comes in.
XVFB: str = "/usr/bin/Xvfb"
XVFB_PACKAGE: str = "xvfb"

# How long to wait for the X server and for LinuxCNC's AXIS screen to
# start (seconds); an emulated computer is slow.
X_START: float = 300.0
AXIS_START: float = 900.0

# What LinuxCNC prints when its realtime thread runs late.
DELAY: str = "Unexpected realtime delay"


# Class `Result`:
@dataclass(frozen=True, slots=True)
class Result:
    """What `sim_linuxcnc.py` printed about its run.

    Attributes:
    * `samples` (`int`): How many samples it took (0 if not done).
    * `seconds` (`float`): How long the program ran (seconds).
    * `errors` (`list[str]`): LinuxCNC's error messages.

    Constructor:
    * `Result(samples, seconds, errors)`
    """

    # Constructor arguments:
    samples: int = field(init=True)
    seconds: float = field(init=True)
    errors: list[str] = field(init=True)


# Function `parse_result()`:
def parse_result(text: str) -> Result:
    """Find what `sim_linuxcnc.py`'s output says about its run.

    Arguments:
    * `text` (`str`): Its output.

    Returns:
    * (`Result`): What it found.
    """
    done = re.search(r"^done: (\d+) samples in ([\d.]+) s", text, re.MULTILINE)
    errors = re.findall(r"^error: (.*)$", text, re.MULTILINE)
    if done is None:
        return Result(0, 0.0, errors)
    return Result(int(done.group(1)), float(done.group(2)), errors)


# Function `pack()`:
def pack(project: Path, tarball: Path) -> int:
    """Put the demonstration's files in a `tar` file.

    Line endings become Unix ones (a Windows checkout may have
    `\\r\\n`, which LinuxCNC's INI and HAL files must not), and a
    symbolic link that a Windows checkout made into a small text file
    (such as `scraftpybind.py`, whose text is `../scraftpybind/...`)
    is replaced by the file it names.

    Arguments:
    * `project` (`Path`): The project's directory.
    * `tarball` (`Path`): The `tar` file to write.

    Returns:
    * (`int`): The number of files in it.
    """
    paths = sorted(
        {path for pattern in FILES for path in project.glob(pattern)},
        key=Path.as_posix,
    )
    with tarfile.open(tarball, "w") as tar:
        for path in paths:
            data = path.read_bytes()
            if len(data) < 200 and data.startswith(b"../"):
                data = (path.parent / data.decode().strip()).read_bytes()
            data = data.replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(path.relative_to(project).as_posix())
            info.size = len(data)
            info.mode = 0o644
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return len(paths)


# Function `place_project()`:
def place_project(target: Target) -> str:
    """Make the project's files visible in the target.

    Arguments:
    * `target` (`Target`): The target.

    Returns:
    * (`str`): The directory in the target that has them.

    Raises:
    * `SystemExit`: If they could not be copied in.
    """
    # A box that sees this directory uses it.
    if target.shares_home and run(
        target.command(["test", "-f", str(PROJECT / "sim_linuxcnc.py")]),
        quiet=True,
    ):
        print(f"{stamp()} {target.name} sees {PROJECT}", flush=True)
        return str(PROJECT)

    # Otherwise send a copy.
    where = f"{target.home}/{COPY}"
    install_linuxcnc.CACHE.mkdir(parents=True, exist_ok=True)
    tarball = install_linuxcnc.CACHE / f"{COPY}.tar"
    count = pack(PROJECT, tarball)
    print(f"{stamp()} Copying {count} files to {where}", flush=True)
    sent = install_linuxcnc.send_file(target, tarball)
    unpack = (
        f"rm -rf {shlex.quote(where)} && mkdir -p {shlex.quote(where)}"
        f" && tar -xf {shlex.quote(sent)} -C {shlex.quote(where)}"
    )
    if not run(target.command(["sh", "-c", unpack])):
        raise SystemExit(f"Could not copy the files to {where}.")
    return where


# Function `ensure_xvfb()`:
def ensure_xvfb(target: Target, yes: bool) -> None:
    """Install `Xvfb` in the target, unless it is there.

    AXIS needs an X server; `Xvfb` is one with no screen.  A computer
    with a screen does not need it (`--display`), so the installer
    leaves it out; this is for test machines such as GitHub's runners.

    Arguments:
    * `target` (`Target`): The target.
    * `yes` (`bool`): True to install it rather than ask the user to.

    Raises:
    * `SystemExit`: If it is still missing.
    """

    def have() -> bool:
        return run(target.command(["test", "-x", XVFB]), quiet=True)

    if have():
        return
    script = (
        "apt-get update && apt-get install -y --no-install-recommends"
        f" {XVFB_PACKAGE}"
    )
    install_linuxcnc.ask_user(
        f"`Xvfb` (an X server with no screen, for AXIS) is not in"
        f" {target.name}.",
        target.command(
            ["env", "DEBIAN_FRONTEND=noninteractive", "sh", "-c", script],
            root=True,
        ),
        yes=yes,
    )
    if not have():
        raise SystemExit(f"`Xvfb` is still not in {target.name}.")


# Function `outside()`:
def outside(arguments: argparse.Namespace) -> int:
    """Run the demonstration in the target that LinuxCNC is in.

    Arguments:
    * `arguments` (`argparse.Namespace`): The command line.

    Returns:
    * (`int`): The exit status of the run in the target.
    """
    options = install_linuxcnc.target_options(arguments)
    target, _ = install_linuxcnc.steps(options)
    print(f"{stamp()} Running the demonstration in {target.name}.")

    # The X server, and the files.
    if not arguments.display:
        ensure_xvfb(target, options.yes)
    where = place_project(target)

    # This program, again, in the target as the user.
    command = [
        "python3",
        "-u",
        "demo_linuxcnc.py",
        "--inside",
        "--speed",
        str(arguments.speed),
        "--timeout",
        str(arguments.timeout),
    ]
    if arguments.display:
        command += ["--display", arguments.display]
    script = f"cd {shlex.quote(where)} && exec {shlex.join(command)}"
    started = time.monotonic()
    ok = run(target.command(["sh", "-c", script]))
    minutes = (time.monotonic() - started) / 60.0
    print(
        f"{stamp()} The demonstration {'passed' if ok else 'FAILED'} in"
        f" {target.name} ({options.route}), {minutes:.1f} min.",
        flush=True,
    )
    return 0 if ok else 1


# Function `start_xvfb()`:
def start_xvfb(log: Path) -> tuple[subprocess.Popen[bytes], str]:
    """Start `Xvfb` on a free display.

    Arguments:
    * `log` (`Path`): Where its messages go.

    Returns:
    * (`tuple[subprocess.Popen[bytes], str]`): It, and its display
      (such as `:1`).

    Raises:
    * `SystemExit`: If it does not say which display it took in time.
    """
    # `-displayfd 1` makes it pick a free display, and print its number
    # once it is ready.
    with log.open("wb") as messages:
        xvfb = subprocess.Popen(  # pylint: disable=consider-using-with
            [XVFB, "-displayfd", "1", "-screen", "0", "1280x1024x24",
             "-nolisten", "tcp"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=messages,
            start_new_session=True,
        )  # fmt: skip
    assert xvfb.stdout is not None
    ready, _, _ = select.select([xvfb.stdout], [], [], X_START)
    number = xvfb.stdout.readline().decode().strip() if ready else ""
    if not number.isdigit():
        xvfb.kill()
        print(log.read_text(errors="replace"), file=sys.stderr)
        raise SystemExit("Xvfb did not start.")
    return xvfb, f":{number}"


# Function `wait_for_axis()`:
def wait_for_axis(lcnc: subprocess.Popen[bytes], env: dict[str, str]) -> bool:
    """Wait until the AXIS screen answers, or LinuxCNC exits.

    Arguments:
    * `lcnc` (`subprocess.Popen[bytes]`): The `linuxcnc` script.
    * `env` (`dict[str, str]`): Its environment (with `DISPLAY`).

    Returns:
    * (`bool`): True when AXIS answered `axis-remote --ping`.
    """
    end = time.monotonic() + AXIS_START
    while time.monotonic() < end and lcnc.poll() is None:
        ping = subprocess.run(
            ["axis-remote", "--ping"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if ping.returncode == 0:
            return True
        time.sleep(2.0)
    return False


# Function `follow()`:
def follow(command: list[str], env: dict[str, str], timeout: float) -> str:
    """Run a command, printing its output with the time, with a limit.

    Arguments:
    * `command` (`list[str]`): The command.
    * `env` (`dict[str, str]`): Its environment.
    * `timeout` (`float`): How long it may run (seconds).

    Returns:
    * (`str`): Its output, followed by `exit N` on a line of its own.
    """
    print(f"$ {shlex.join(command)}", flush=True)
    lines: list[str] = []
    with subprocess.Popen(
        command,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        timer = threading.Timer(timeout, process.kill)
        timer.start()
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.decode(errors="replace").rstrip()
            lines.append(line)
            print(f"{line}", flush=True)
        returncode = process.wait()
        timer.cancel()
    if returncode < 0:
        lines.append(f"killed after {timeout:.0f} s")
    lines.append(f"exit {returncode}")
    return "\n".join(lines)


# Function `inside()`:
def inside(arguments: argparse.Namespace) -> int:
    """Run the demonstration here, in the target (`--inside`).

    Its lines have no time: the half outside adds it to every line.

    Arguments:
    * `arguments` (`argparse.Namespace`): The command line.

    Returns:
    * (`int`): The exit status (0 when it passed).
    """
    # Imported here: they are only needed in the target, and `pwd` is
    # not on Windows, where the other half of this program may run.
    # pylint: disable-next=import-outside-toplevel
    import pwd

    # pylint: disable-next=import-outside-toplevel
    import stop_linuxcnc

    # A command run by `wsl.exe --exec` or `docker exec` may have no
    # `HOME`, which LinuxCNC needs.
    env = dict(os.environ)
    env["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    logs = Path(tempfile.mkdtemp(prefix="lcnc_demo_"))
    print(f"In {os.getcwd()} as {pwd.getpwuid(os.getuid())[0]}")

    # No LinuxCNC may be running, and none may have been left killed.
    if stop_linuxcnc.running():
        raise SystemExit("LinuxCNC is already running; not starting it.")
    if stop_linuxcnc.LOCK.exists():
        stop_linuxcnc.kill_and_clean()

    # The program.
    with Path("demo.ngc").open("wb") as ngc:
        made = subprocess.run(
            [sys.executable, "solidcraftcnc_demo.py"],
            stdout=ngc,
            stderr=subprocess.PIPE,
            check=False,
        )
    print(f"demo.ngc: {made.stderr.decode().strip()}", flush=True)
    if made.returncode != 0:
        return 1

    # The X server: a real one, or `Xvfb`.
    xvfb: subprocess.Popen[bytes] | None = None
    if arguments.display:
        env["DISPLAY"] = arguments.display
    else:
        xvfb, env["DISPLAY"] = start_xvfb(logs / "xvfb.log")
    print(f"DISPLAY={env['DISPLAY']}", flush=True)

    # LinuxCNC, with its output in a log.
    started = time.monotonic()
    log = logs / "linuxcnc.log"
    with log.open("wb") as messages:
        lcnc = subprocess.Popen(  # pylint: disable=consider-using-with
            ["linuxcnc", "lcnc_sim/shop_mill.ini"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=messages,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    # Reap the `linuxcnc` script as soon as it exits: until then it is
    # a zombie still named `linuxcnc`, which `stop_linuxcnc.py` takes
    # for a LinuxCNC still running (and can not kill).
    threading.Thread(target=lcnc.wait, daemon=True).start()
    text = ""
    try:
        # Wait for AXIS, then run the program to its end.
        if wait_for_axis(lcnc, env):
            seconds = time.monotonic() - started
            print(f"AXIS answered after {seconds:.0f} s", flush=True)
            text = follow(
                [sys.executable, "-u", "sim_linuxcnc.py", "demo.ngc",
                 "--speed", str(arguments.speed)],
                env,
                arguments.timeout * 60.0,
            )  # fmt: skip
        else:
            print("AXIS did not answer", flush=True)
    finally:
        # Close LinuxCNC, then the X server.
        follow([sys.executable, "stop_linuxcnc.py"], env, 120.0)
        try:
            lcnc.wait(timeout=60.0)
        except subprocess.TimeoutExpired:
            lcnc.kill()
        if xvfb is not None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=30.0)
            except subprocess.TimeoutExpired:
                xvfb.kill()

    # What was left, what LinuxCNC said, and the verdict.
    return verdict(text, log, stop_linuxcnc.running(), xvfb)


# Function `verdict()`:
def verdict(
    text: str,
    log: Path,
    left: list[int],
    xvfb: subprocess.Popen[bytes] | None,
) -> int:
    """Report the run, and decide whether it passed.

    Arguments:
    * `text` (`str`): `sim_linuxcnc.py`'s output (from `follow()`).
    * `log` (`Path`): LinuxCNC's log.
    * `left` (`list[int]`): LinuxCNC's processes still running.
    * `xvfb` (`subprocess.Popen[bytes] | None`): `Xvfb`, if started.

    Returns:
    * (`int`): 0 when it passed.
    """
    # LinuxCNC's own messages: the realtime delays, and the end of its
    # log when the run failed.
    messages = log.read_text(errors="replace")
    delays = [line for line in messages.splitlines() if DELAY in line]
    for line in delays[:5]:
        print(f"linuxcnc: {line}")
    result = parse_result(text)
    passed = (
        text.endswith("\nexit 0")
        and result.samples > 0
        and not result.errors
        and not left
        and (xvfb is None or xvfb.poll() is not None)
    )
    if not passed:
        print(f"The end of {log}:")
        for line in messages.splitlines()[-60:]:
            print(f"linuxcnc: {line}")

    # One line that says it all.
    exit_line = text.rsplit("\n", 1)[-1] if text else "not run"
    print(
        f"demo: sim_linuxcnc.py {exit_line}, {result.samples}"
        f" samples in {result.seconds:.1f} s, {len(result.errors)} errors,"
        f" {len(delays)} realtime delay messages, left running: {left},"
        f" Xvfb stopped: {xvfb is None or xvfb.poll() is not None}"
        f" -> {'PASS' if passed else 'FAIL'}",
        flush=True,
    )
    return 0 if passed else 1


# Function `main()`:
def main() -> int:
    """Run the demonstration in LinuxCNC's target, or (`--inside`) here.

    Returns:
    * (`int`): The exit status.
    """
    parser = argparse.ArgumentParser(
        description="Run the demonstration's G-code in LinuxCNC, in the"
        " target that install_linuxcnc.py made."
    )
    install_linuxcnc.add_target_arguments(parser)
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="sim_linuxcnc.py's feed override (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="minutes the program may run (default: %(default)s)",
    )
    parser.add_argument(
        "--display",
        default="",
        help="an X display to show AXIS on (default: Xvfb, no screen)",
    )
    parser.add_argument("--inside", action="store_true", help="(internal)")
    arguments = parser.parse_args()
    try:
        return inside(arguments) if arguments.inside else outside(arguments)
    except KeyboardInterrupt:
        print(
            "\nStopped (Ctrl-C); LinuxCNC may be left running.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    sys.exit(main())
