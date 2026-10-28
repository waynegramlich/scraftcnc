#!/usr/bin/env python3
"""Install LinuxCNC's simulator in Debian Trixie, on any computer.

`T.il~3.1`.  LinuxCNC offers packages only for Debian 13 Trixie, so
its simulator, `linuxcnc-uspace`, is installed in a Debian Trixie
system made for it, which this program calls the target:

* Linux (such as Ubuntu 24.04): a `distrobox` box (`lcnc`) on
  `podman`, sharing the home directory.
* Windows: WSL 2 with Debian (`Debian`, upgraded to Trixie if it is
  older), with the package installed in it directly.  This program
  runs in Windows' own Python and drives `wsl.exe`.
* macOS with a hypervisor (`sysctl kern.hv_support` is 1): a
  `debian:trixie` container (`lcnc`) in a Linux VM, made by `podman
  machine` on Apple Silicon and by `colima` (with `docker`) on Intel,
  where Homebrew no longer has `podman`.
* macOS without one (as on GitHub's Apple Silicon runners): a Debian
  Trixie cloud image run by QEMU in software emulation (TCG), reached
  by `ssh` on port 2222.  It is slow (hours), but needs nothing from
  the machine.

Each step is checked first and skipped when it is already done, so
running this again is safe.  A step that needs the user (installing
software, or a `sudo` that asks for a password) is shown as a
command, also put on the clipboard when there is a way to, and this
waits for the user to run it and then checks it; with `--yes` it
runs the command itself instead (for test machines such as GitHub's
runners).  Only the packages LinuxCNC needs are installed (`apt-get
--no-install-recommends`: no realtime kernel, no documentation), and
the number installed is printed.  The last steps check that `import
linuxcnc` works, that the AXIS screen's Python modules load (with no
display), and that LinuxCNC's realtime layer starts (`halrun`, as a
user that is not root).  Long commands print the time on every
line, and a progress line every few minutes.  `demo_linuxcnc.py`
then runs a program in LinuxCNC in the same target:

```
./install_linuxcnc.py                  # The `lcnc` box, on Linux.
./install_linuxcnc.py --box lcnc-test  # Another box.
./install_linuxcnc.py --yes            # Run the commands too.
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini
./demo_linuxcnc.py                     # Run the demo's G-code in it.
```
"""

# The steps are closures, whose many small functions count as
# locals.
# pylint: disable=too-many-lines,too-many-locals

import argparse
import base64
import contextlib
import getpass
import hashlib
import io
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# The Debian image of the box or container.
IMAGE: str = "docker.io/library/debian:trixie"

# Where LinuxCNC's Trixie packages are; `ARCH` is the target's Debian
# architecture (`amd64`, `arm64`, ...).
REPOSITORY: str = "https://linuxcnc.org/dists/trixie/2.9-uspace"
PACKAGE: str = "linuxcnc-uspace"

# Where downloads (and the QEMU VM) are kept.  A `distrobox` box
# shares the home directory, so it sees the same files.
CACHE: Path = Path.home() / ".cache" / "scraftcnc"

# LinuxCNC's sample configurations, and where (under the target
# user's home) they are copied to.
SAMPLES: str = "/usr/share/doc/linuxcnc/examples/sample-configs/sim"
CONFIGS: str = "linuxcnc/configs"

# Debian's package sources, changed when an older Debian is upgraded.
SOURCES: str = "/etc/apt/sources.list /etc/apt/sources.list.d/*"

# `wsl.exe --exec` runs a command with no login shell, so root's
# `PATH` lacks `/usr/sbin` (where `useradd` is); every WSL command
# gets Debian's own `PATH`.
WSL_ENV: tuple[str, ...] = (
    "/usr/bin/env",
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
)

# The user (not root) made in a container or WSL, and the container's
# name.
USER: str = "lcnc"
CONTAINER: str = "lcnc"

# The QEMU VM: Debian's cloud images, its directory, and its `ssh`
# port on this computer.
CLOUD: str = "https://cloud.debian.org/images/cloud/trixie/latest"
VM: Path = CACHE / "vm"
SSH_PORT: int = 2222

# How long to wait for the QEMU VM to answer `ssh` (seconds); TCG
# boots slowly.
VM_BOOT: float = 45 * 60.0

# How often a long command reports its progress (seconds).
HEARTBEAT: float = 300.0

# How LinuxCNC is installed: only what it needs (the user's choice).
# Its Recommends (the documentation, `librsvg2-dev`,
# `x11-xserver-utils`, `hostmot2-firmware-all`, the realtime kernel
# with its initramfs, `python3-pil`, `python3-pil.imagetk`) are left
# out: neither the AXIS screen nor its modules use `PIL` or `xset`
# (checked in `/usr/bin/axis` and LinuxCNC's Python modules), and
# the sample configurations come with `linuxcnc-uspace` itself.
INSTALL: tuple[str, ...] = ("install", "-y", "--no-install-recommends")

# Lists the installed packages, to count what `apt-get` added.
PACKAGES: list[str] = ["dpkg-query", "-W", "-f", "${Package}\\n"]

# What the AXIS screen (`/usr/bin/axis`) imports, which must load
# with no display.
AXIS_MODULES: tuple[str, ...] = (
    "tkinter",
    "OpenGL.GL",
    "OpenGL.GLU",
    "gcode",
    "rs274.OpenGLTk",
    "rs274.interpret",
    "rs274.glcanon",
    "rs274.options",
    "hershey",
    "propertywindow",
    "nf",
    "bwidget",
    "glnav",
    "hal",
    "linuxcnc",
)

# The `halrun` check: a thread loaded and listed.  `halrun` exits 0
# even when a component fails to load, so its output is checked.
HAL_THREAD: str = "probethread"
HALRUN: str = (
    "cd /tmp && printf '%s\\n'"
    f" 'loadrt threads name1={HAL_THREAD} period1=1000000'"
    " 'show thread' | timeout 120 halrun 2>&1"
)


# Class `Step`:
@dataclass(frozen=True, slots=True)
class Step:
    """One step of the installation.

    Attributes:
    * `title` (`str`): What the step does, shown to the user.
    * `done` (`Callable[[], bool]`): True when the step is done.
    * `act` (`Callable[[], None]`): Does the step (or asks the user to).

    Constructor:
    * `Step(title, done, act)`
    """

    # Constructor arguments:
    title: str = field(init=True)
    done: Callable[[], bool] = field(init=True)
    act: Callable[[], None] = field(init=True)


# Class `Target`:
@dataclass(frozen=True, slots=True)
class Target:
    """The Debian Trixie system that LinuxCNC is installed in.

    Attributes:
    * `name` (`str`): What it is, shown to the user.
    * `root` (`tuple[str, ...]`):
      The command prefix that runs a command in it as root.
    * `user` (`tuple[str, ...]`):
      The command prefix that runs a command in it as the user who
      runs LinuxCNC (not root).
    * `home` (`str`): That user's home directory in it.
    * `joined` (`bool`):
      True when the command after the prefix must be one shell
      string (`ssh`).
    * `shares_home` (`bool`):
      True when it sees this computer's files at the same paths
      (`distrobox`).
    * `enter` (`str`): How the user gets a shell in it.

    Constructor:
    * `Target(name, root, user, home, joined, shares_home, enter)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    root: tuple[str, ...] = field(init=True)
    user: tuple[str, ...] = field(init=True)
    home: str = field(init=True)
    joined: bool = field(init=True)
    shares_home: bool = field(init=True)
    enter: str = field(init=True)

    # Method `Target.command()`:
    def command(self, command: list[str], *, root: bool = False) -> list[str]:
        """Return a command that runs a command in the target.

        Arguments:
        * `command` (`list[str]`): The command to run in it.
        * `root` (`bool`): True to run it as root.

        Returns:
        * (`list[str]`): The command to run here.
        """
        prefix = self.root if root else self.user
        if self.joined:
            return [*prefix, shlex.join(command)]
        return [*prefix, *command]


# Class `Options`:
@dataclass(frozen=True, slots=True)
class Options:
    """What the command line asked for.

    Attributes:
    * `route` (`str`):
      How LinuxCNC is installed: `distrobox`, `wsl`, `podman`,
      `colima` or `qemu`.
    * `box` (`str`): The `distrobox` box's name.
    * `distribution` (`str`): The WSL distribution's name.
    * `yes` (`bool`):
      True to run the commands that the user would be asked to.

    Constructor:
    * `Options(route, box, distribution, yes)`
    """

    # Constructor arguments:
    route: str = field(init=True)
    box: str = field(init=True)
    distribution: str = field(init=True)
    yes: bool = field(init=True)


# Function `stamp()`:
def stamp() -> str:
    """Return the time of day, to start a line of output with.

    Returns:
    * (`str`): The time, as `[HH:MM:SS]`.
    """
    return time.strftime("[%H:%M:%S]")


# Function `run()`:
def run(
    command: list[str], *, quiet: bool = False, source: Path | None = None
) -> bool:
    """Run a command, showing it and its output with the time.

    While it runs, a progress line (how long, how many lines, how
    many packages `apt` has set up) is printed every `HEARTBEAT`
    seconds, so a log that ends early still shows how far it got.

    Arguments:
    * `command` (`list[str]`): The command and its arguments.
    * `quiet` (`bool`):
      True to hide the command and its output (for checks).
    * `source` (`Path | None`):
      A file for its standard input; otherwise it shares this
      program's (so `sudo` can ask for a password).

    Returns:
    * (`bool`): True if it succeeded.
    """
    # A check: no output at all.
    if quiet:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    # Show the command, then each line of its output with the time.
    print(f"{stamp()} $ {shlex.join(command)}", flush=True)
    counts: list[int] = [0, 0]  # Lines, and packages set up.
    finished = threading.Event()
    started = time.monotonic()

    def heartbeat() -> None:
        while not finished.wait(HEARTBEAT):
            minutes = (time.monotonic() - started) / 60.0
            print(
                f"{stamp()} ... still running after {minutes:.0f} min:"
                f" {counts[0]} lines, {counts[1]} packages set up",
                flush=True,
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with contextlib.ExitStack() as stack:
            stdin = stack.enter_context(source.open("rb")) if source else None
            process = stack.enter_context(
                subprocess.Popen(
                    command,
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            )
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.decode(errors="replace").rstrip()
                counts[0] += 1
                if line.startswith("Setting up "):
                    counts[1] += 1
                print(f"{stamp()} {line}", flush=True)
            returncode = process.wait()
    except OSError as error:
        print(f"{stamp()} {error}", flush=True)
        returncode = 127
    finally:
        finished.set()
    return returncode == 0


# Function `capture()`:
def capture(command: list[str]) -> tuple[int, str]:
    """Run a command quietly and return its status and output.

    Arguments:
    * `command` (`list[str]`): The command and its arguments.

    Returns:
    * (`tuple[int, str]`):
      Its exit status and everything it printed (standard output
      and error), or 127 and the error if it could not start.
    """
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as error:
        return 127, str(error)
    return result.returncode, result.stdout.decode(errors="replace")


# Function `output()`:
def output(command: list[str]) -> str:
    """Run a command quietly and return what it prints.

    Arguments:
    * `command` (`list[str]`): The command and its arguments.

    Returns:
    * (`str`): Its standard output, stripped, or `""` if it failed.
    """
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode(errors="replace").strip()


# Function `copy_to_clipboard()`:
def copy_to_clipboard(text: str) -> str:
    """Put text on the clipboard, if there is a way to.

    The clipboard programs of macOS, Wayland, X11 and Windows (also
    from WSL) are tried in turn; failing those, the terminal is asked
    to do it (the OSC 52 escape sequence, which many terminals honor
    and the rest ignore).

    Arguments:
    * `text` (`str`): The text.

    Returns:
    * (`str`): How it was copied (to tell the user).
    """
    # Try the clipboard programs.
    programs: list[list[str]] = [
        ["pbcopy"],
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["clip.exe"],
    ]
    for program in programs:
        name = program[0]
        if name == "wl-copy" and not os.environ.get("WAYLAND_DISPLAY"):
            continue
        if name.startswith("x") and not os.environ.get("DISPLAY"):
            continue
        if shutil.which(name):
            try:
                subprocess.run(
                    program,
                    input=text,
                    text=True,
                    check=True,
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return f"copied to the clipboard ({name})"
            except (OSError, subprocess.SubprocessError):
                pass

    # Ask the terminal.
    if sys.stdout.isatty():
        encoded = base64.b64encode(text.encode()).decode()
        sys.stdout.write(f"\033]52;c;{encoded}\a")
        sys.stdout.flush()
        return "sent to the terminal's clipboard, if it allows that"
    return "not copied (no clipboard found)"


# Function `ask_user()`:
def ask_user(why: str, command: list[str], *, yes: bool = False) -> None:
    """Ask the user to run a command, and wait until they have.

    Arguments:
    * `why` (`str`): Why the user must run it.
    * `command` (`list[str]`): The command for the user to run.
    * `yes` (`bool`):
      True to run it here instead of asking (`--yes`).

    Raises:
    * `SystemExit`: If there is nobody to ask (standard input is not
      a terminal, and `yes` is false).
    """
    # With `--yes`, just run it.
    if yes:
        print(f"\n{why}  Running it (--yes):")
        run(command)
        return

    # Show the command and copy it.
    text = shlex.join(command)
    print(f"\n{why}  Please run this in another terminal:\n")
    print(f"    {text}\n")
    print(f"({copy_to_clipboard(text)}.)")

    # Wait for the user.
    if not sys.stdin.isatty():
        raise SystemExit("Nobody to ask (input is not a terminal).")
    input("Press Enter when it is done: ")


# Function `in_box()`:
def in_box(box: str, command: list[str]) -> list[str]:
    """Return a command that runs a command in a `distrobox` box.

    Arguments:
    * `box` (`str`): The box's name.
    * `command` (`list[str]`): The command to run in it.

    Returns:
    * (`list[str]`): The `distrobox enter` command.
    """
    return ["distrobox", "enter", box, "--", *command]


# Function `choose_route()`:
def choose_route(system: str, machine: str, hv_support: str) -> str:
    """Choose how to install LinuxCNC on this computer.

    Arguments:
    * `system` (`str`): `platform.system()` (`Linux`, `Windows`,
      `Darwin`).
    * `machine` (`str`): `platform.machine()` (e.g. `arm64`).
    * `hv_support` (`str`):
      What `sysctl -n kern.hv_support` printed on macOS (`1` when
      there is a hypervisor).

    Returns:
    * (`str`): `distrobox`, `wsl`, `podman`, `colima` or `qemu`.

    Raises:
    * `SystemExit`: If the system is not supported.
    """
    if system == "Linux":
        return "distrobox"
    if system == "Windows":
        return "wsl"
    if system == "Darwin":
        if hv_support.strip() != "1":
            return "qemu"
        return "podman" if machine == "arm64" else "colima"
    raise SystemExit(f"{system} is not supported.")


# Function `halrun_ok()`:
def halrun_ok(text: str) -> bool:
    """Tell whether `halrun`'s output shows the realtime layer working.

    Arguments:
    * `text` (`str`): What `HALRUN` printed.

    Returns:
    * (`bool`): True if the thread was listed and nothing failed.
    """
    return HAL_THREAD in text and not re.search(r"failed|Refusing", text)


# Function `wsl_version()`:
def wsl_version(listing: str, name: str) -> int:
    """Find a distribution's WSL version in `wsl.exe -l -v`'s output.

    Arguments:
    * `listing` (`str`): The output (UTF-8, as with `WSL_UTF8=1`).
    * `name` (`str`): The distribution's name.

    Returns:
    * (`int`): Its WSL version, or 0 if it is not listed.
    """
    for line in listing.replace("\0", "").splitlines():
        words = line.replace("*", " ").split()
        if len(words) >= 3 and words[0] == name and words[-1].isdigit():
            return int(words[-1])
    return 0


# Function `version_key()`:
def version_key(version: str) -> tuple[int, tuple[int, ...]]:
    """Return a key that sorts Debian versions such as `1:2.9.10`.

    Only the epoch and the numbers are compared, which is enough for
    LinuxCNC's versions.

    Arguments:
    * `version` (`str`): The version.

    Returns:
    * (`tuple[int, tuple[int, ...]]`): The epoch and the numbers.
    """
    epoch, _, rest = version.rpartition(":")
    numbers = tuple(int(number) for number in re.findall(r"\d+", rest))
    return (int(epoch) if epoch else 0, numbers)


# Function `newest_package()`:
def newest_package(arch: str) -> tuple[str, str, str]:
    """Find the newest LinuxCNC package for an architecture.

    Arguments:
    * `arch` (`str`): The Debian architecture (e.g. `amd64`).

    Returns:
    * (`tuple[str, str, str]`): Its version, its URL and its SHA-256.

    Raises:
    * `SystemExit`: If the index has no package for `arch`.
    """
    # Read the index: one paragraph per package version.
    url = f"{REPOSITORY}/binary-{arch}/Packages"
    with urllib.request.urlopen(url, timeout=60) as response:
        index: str = response.read().decode()
    found: list[tuple[str, str, str]] = []
    for paragraph in index.split("\n\n"):
        fields: dict[str, str] = dict(
            line.split(": ", 1)
            for line in paragraph.splitlines()
            if ": " in line and not line.startswith(" ")
        )
        if fields.get("Package") == PACKAGE:
            found.append(
                (
                    fields["Version"],
                    f"https://linuxcnc.org/{fields['Filename']}",
                    fields["SHA256"],
                )
            )

    # Pick the newest.
    if not found:
        raise SystemExit(f"{url} has no {PACKAGE} package.")
    return max(found, key=lambda entry: version_key(entry[0]))


# Function `download()`:
def download(url: str, digest: str, *, algorithm: str = "sha256") -> Path:
    """Download a file into `CACHE`, unless it is there already.

    Arguments:
    * `url` (`str`): Where it is.
    * `digest` (`str`): Its hash, to check it against.
    * `algorithm` (`str`): The hash (`sha256` or `sha512`).

    Returns:
    * (`Path`): The file.

    Raises:
    * `SystemExit`: If the file's hash is wrong.
    """
    # Download it, unless a good copy is already there.
    path = CACHE / url.rsplit("/", 1)[1]
    if not path.exists() or file_hash(path, algorithm) != digest:
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"{stamp()} Downloading {url}", flush=True)
        partial = path.with_suffix(".part")
        urllib.request.urlretrieve(url, partial)
        partial.replace(path)

    # Check it.
    if file_hash(path, algorithm) != digest:
        path.unlink()
        raise SystemExit(f"{url}: wrong {algorithm}; removed the download.")
    return path


# Function `file_hash()`:
def file_hash(path: Path, algorithm: str = "sha256") -> str:
    """Return a file's hash.

    Arguments:
    * `path` (`Path`): The file.
    * `algorithm` (`str`): The hash (`sha256` or `sha512`).

    Returns:
    * (`str`): Its hash, in hexadecimal.
    """
    with path.open("rb") as file:
        return hashlib.file_digest(file, algorithm).hexdigest()


# Function `file_sha256()`:
def file_sha256(path: Path) -> str:
    """Return a file's SHA-256.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`str`): Its SHA-256, in hexadecimal.
    """
    return file_hash(path, "sha256")


# Function `send_file()`:
def send_file(target: Target, path: Path) -> str:
    """Put a file of this computer's into the target's `/tmp`.

    Arguments:
    * `target` (`Target`): The target.
    * `path` (`Path`): The file.

    Returns:
    * (`str`): Its path in the target.
    """
    # A box sees the file where it is.
    if target.shares_home:
        return str(path)

    # Otherwise send it through standard input.
    inside = f"/tmp/{path.name}"
    run(
        target.command(["sh", "-c", f"cat > {inside}"], root=True),
        source=path,
    )
    return inside


# Function `apt_get()`:
def apt_get(*arguments: str) -> list[str]:
    """Return an `apt-get` command that asks no questions.

    Arguments:
    * `arguments` (`str`): Its arguments.

    Returns:
    * (`list[str]`): The command.
    """
    return ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", *arguments]


# Function `box_steps()`:
def box_steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the `distrobox` target (Linux) and the steps making it.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and its steps.
    """
    box = options.box
    # Commands go in through `podman exec`, since `distrobox enter`
    # runs its command through `eval`, which breaks quoted arguments.
    home = str(Path.home())
    target = Target(
        name=f"the {box} box",
        root=("podman", "exec", "-i", "-u", "root", box),
        user=(
            "podman",
            "exec",
            "-i",
            "-u",
            getpass.getuser(),
            "-w",
            home,
            box,
        ),
        home=home,
        joined=False,
        shares_home=True,
        enter=f"distrobox enter {box} -- linuxcnc lcnc_sim/shop_mill.ini",
    )

    # The host's tools: installed by the user, since it needs `sudo`.
    def have_tools() -> bool:
        return bool(shutil.which("podman") and shutil.which("distrobox"))

    def install_tools() -> None:
        ask_user(
            "`podman` and `distrobox` are needed, and installing them"
            " needs `sudo`.",
            ["sudo", "apt-get", "install", "-y", "podman", "distrobox"],
            yes=options.yes,
        )

    # The box.  Its first `distrobox enter` sets it up; a second one
    # at the same time can hang, so it is entered once here.
    def have_box() -> bool:
        return run(["podman", "container", "exists", box], quiet=True)

    def make_box() -> None:
        run(
            [
                "distrobox",
                "create",
                "--yes",
                "--name",
                box,
                "--image",
                IMAGE,
            ]
        )
        run(in_box(box, ["true"]))

    return target, [
        Step("podman and distrobox", have_tools, install_tools),
        Step(f"the {box} box (Debian Trixie)", have_box, make_box),
    ]


# Function `container_step()`:
def container_step(cli: str) -> tuple[Target, Step]:
    """Return a container target (macOS) and the step that starts it.

    Arguments:
    * `cli` (`str`): The container program (`podman` or `docker`).

    Returns:
    * (`tuple[Target, Step]`): The target and its step.
    """
    target = Target(
        name=f"the {CONTAINER} container",
        root=(cli, "exec", "-i", CONTAINER),
        user=(cli, "exec", "-i", "-u", USER, CONTAINER),
        home=f"/home/{USER}",
        joined=False,
        shares_home=False,
        enter=f"{cli} exec -it -u {USER} {CONTAINER} bash",
    )

    # A Debian Trixie container that keeps running (`sleep`), so that
    # commands can be run in it.
    def running() -> bool:
        state = output(
            [
                cli,
                "container",
                "inspect",
                "-f",
                "{{.State.Running}}",
                CONTAINER,
            ]
        )
        return state == "true"

    def start() -> None:
        if run([cli, "container", "inspect", CONTAINER], quiet=True):
            run([cli, "start", CONTAINER])
        else:
            run(
                [
                    cli,
                    "run",
                    "-d",
                    "--name",
                    CONTAINER,
                    IMAGE,
                    "sleep",
                    "infinity",
                ]
            )

    return target, Step(
        f"the {CONTAINER} container (Debian Trixie)", running, start
    )


# Function `podman_steps()`:
def podman_steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the `podman machine` target (Apple Silicon) and steps.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and its steps.
    """

    # `podman`, from Homebrew.
    def have_podman() -> bool:
        return bool(shutil.which("podman"))

    def install_podman() -> None:
        ask_user(
            "`podman` is needed (from Homebrew).",
            ["brew", "install", "podman"],
            yes=options.yes,
        )

    # Its Linux VM, made once and started.
    def machine_running() -> bool:
        state = output(
            ["podman", "machine", "inspect", "--format", "{{.State}}"]
        )
        return state == "running"

    def start_machine() -> None:
        if not run(["podman", "machine", "inspect"], quiet=True):
            run(["podman", "machine", "init"])
        run(["podman", "machine", "start"])

    target, container = container_step("podman")
    return target, [
        Step("podman", have_podman, install_podman),
        Step(
            "the podman machine (a Linux VM)", machine_running, start_machine
        ),
        container,
    ]


# Function `colima_steps()`:
def colima_steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the `colima` target (Intel macOS) and its steps.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and its steps.
    """

    # `colima` and `docker`, from Homebrew.
    def have_colima() -> bool:
        return bool(shutil.which("colima") and shutil.which("docker"))

    def install_colima() -> None:
        ask_user(
            "`colima` and `docker` are needed (from Homebrew, which has"
            " no `podman` for Intel Macs).",
            ["brew", "install", "colima", "docker"],
            yes=options.yes,
        )

    # Its Linux VM, started.
    def colima_running() -> bool:
        return run(["colima", "status"], quiet=True)

    def start_colima() -> None:
        run(["colima", "start", "--cpu", "2", "--memory", "4"])

    target, container = container_step("docker")
    return target, [
        Step("colima and docker", have_colima, install_colima),
        Step("colima (a Linux VM)", colima_running, start_colima),
        container,
    ]


# Function `qemu_command()`:
def qemu_command(machine: str, accelerated: bool, firmware: str) -> list[str]:
    """Return the command that starts the QEMU VM in the background.

    Arguments:
    * `machine` (`str`): `platform.machine()` (`arm64` or `x86_64`).
    * `accelerated` (`bool`):
      True to use the hypervisor (`hvf`), false for software
      emulation (TCG).
    * `firmware` (`str`): The UEFI firmware (ARM only).

    Returns:
    * (`list[str]`): The command.
    """
    # The machine, and how its processor is made.
    accel = "hvf" if accelerated else "tcg,thread=multi"
    cpus = str(min(4, os.cpu_count() or 2))
    if machine == "arm64":
        cpu = "host" if accelerated else "max,pauth-impdef=on"
        command = [
            "qemu-system-aarch64",
            "-machine",
            "virt",
            "-bios",
            firmware,
        ]
    else:
        cpu = "host" if accelerated else "max"
        command = ["qemu-system-x86_64", "-machine", "q35"]

    # Its disk, its cloud-init seed, `ssh` on `SSH_PORT`, and a serial
    # console log.
    return [
        *command,
        "-accel",
        accel,
        "-cpu",
        cpu,
        "-smp",
        cpus,
        "-m",
        "4096",
        "-drive",
        f"if=virtio,format=qcow2,file={VM / 'disk.qcow2'}",
        "-drive",
        f"if=virtio,format=raw,readonly=on,file={VM / 'seed.iso'}",
        "-netdev",
        f"user,id=net0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-:22",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-display",
        "none",
        "-serial",
        f"file:{VM / 'console.log'}",
        "-daemonize",
        "-pidfile",
        str(VM / "qemu.pid"),
    ]


# Function `qemu_steps()`:
def qemu_steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the QEMU VM target (macOS with no hypervisor) and steps.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and its steps.
    """
    machine = platform.machine()
    arch = "arm64" if machine == "arm64" else "amd64"
    emulator = (
        "qemu-system-aarch64" if machine == "arm64" else "qemu-system-x86_64"
    )
    image_name = f"debian-13-genericcloud-{arch}.qcow2"
    key = VM / "id_ed25519"
    ssh = (
        "ssh",
        "-p",
        str(SSH_PORT),
        "-i",
        str(key),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=20",
        "debian@127.0.0.1",
    )
    target = Target(
        name="the QEMU VM",
        root=(*ssh, "sudo"),
        user=ssh,
        home="/home/debian",
        joined=True,
        shares_home=False,
        enter=shlex.join(ssh),
    )

    # QEMU, from Homebrew.
    def have_qemu() -> bool:
        return bool(shutil.which(emulator) and shutil.which("qemu-img"))

    def install_qemu() -> None:
        ask_user(
            "QEMU is needed (from Homebrew), since this Mac has no"
            " hypervisor for a VM (`kern.hv_support` is 0).",
            ["brew", "install", "qemu"],
            yes=options.yes,
        )

    # Debian's cloud image, checked against its SHA-512.
    def image() -> Path:
        return CACHE / image_name

    def have_image() -> bool:
        return image().exists() and (VM / "image.ok").exists()

    def get_image() -> None:
        with urllib.request.urlopen(f"{CLOUD}/SHA512SUMS", timeout=60) as (
            response
        ):
            sums: str = response.read().decode()
        digest = next(
            line.split()[0]
            for line in sums.splitlines()
            if line.endswith(f" {image_name}")
        )
        download(f"{CLOUD}/{image_name}", digest, algorithm="sha512")
        VM.mkdir(parents=True, exist_ok=True)
        (VM / "image.ok").write_text(digest + "\n", encoding="utf-8")

    # The VM's own disk (on top of the image), an `ssh` key, and the
    # cloud-init seed that lets the key in.
    def have_disk() -> bool:
        return all((VM / name).exists() for name in ("disk.qcow2", "seed.iso"))

    def make_disk() -> None:
        VM.mkdir(parents=True, exist_ok=True)
        if not key.exists():
            run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "lcnc-vm",
                    "-f",
                    str(key),
                ]
            )
        public = key.with_suffix(".pub").read_text(encoding="utf-8")
        seed = VM / "seed"
        seed.mkdir(exist_ok=True)
        (seed / "meta-data").write_text(
            "instance-id: lcnc\nlocal-hostname: lcnc\n", encoding="utf-8"
        )
        (seed / "user-data").write_text(
            f"#cloud-config\nssh_authorized_keys:\n  - {public.strip()}\n",
            encoding="utf-8",
        )
        (VM / "seed.iso").unlink(missing_ok=True)
        run(
            [
                "hdiutil",
                "makehybrid",
                "-o",
                str(VM / "seed.iso"),
                "-iso",
                "-joliet",
                "-iso-volume-name",
                "cidata",
                "-joliet-volume-name",
                "cidata",
                str(seed),
            ]
        )
        run(
            [
                "qemu-img",
                "create",
                "-q",
                "-f",
                "qcow2",
                "-F",
                "qcow2",
                "-b",
                str(image()),
                str(VM / "disk.qcow2"),
                "20G",
            ]
        )

    # The VM, started in the background and answering `ssh`.
    def answers() -> bool:
        return run([*ssh, "true"], quiet=True)

    def start_vm() -> None:
        pid_file = VM / "qemu.pid"
        if not (pid_file.exists() and pid_alive(pid_file)):
            prefix = Path(shutil.which(emulator) or emulator).resolve()
            firmware = str(
                prefix.parent.parent / "share/qemu/edk2-aarch64-code.fd"
            )
            hv = output(["sysctl", "-n", "kern.hv_support"]) == "1"
            run(qemu_command(machine, hv, firmware))
        print(f"{stamp()} Waiting for the VM to answer ssh (TCG is slow).")
        deadline = time.monotonic() + VM_BOOT
        while time.monotonic() < deadline and not answers():
            print(f"{stamp()} ... not yet", flush=True)
            time.sleep(30)
        if not answers():
            console = VM / "console.log"
            if console.exists():
                text = console.read_text(encoding="utf-8", errors="replace")
                print("\n".join(text.splitlines()[-40:]))
            return
        run([*ssh, "sudo cloud-init status --wait || true"])

    return target, [
        Step("QEMU", have_qemu, install_qemu),
        Step("Debian's cloud image", have_image, get_image),
        Step("the VM's disk, key and seed", have_disk, make_disk),
        Step(f"the QEMU VM (ssh port {SSH_PORT})", answers, start_vm),
    ]


# Function `pid_alive()`:
def pid_alive(pid_file: Path) -> bool:
    """Tell whether the process in a PID file is running.

    Arguments:
    * `pid_file` (`Path`): The file.

    Returns:
    * (`bool`): True if it is.
    """
    try:
        os.kill(int(pid_file.read_text(encoding="utf-8").strip()), 0)
    except (OSError, ValueError):
        return False
    return True


# Function `wsl_steps()`:
def wsl_steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the WSL target (Windows) and the steps making it.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and its steps.
    """
    name = options.distribution
    target = Target(
        name=f"WSL's {name}",
        root=("wsl.exe", "-d", name, "-u", "root", "--exec", *WSL_ENV),
        user=("wsl.exe", "-d", name, "-u", USER, "--exec", *WSL_ENV),
        home=f"/home/{USER}",
        joined=False,
        shares_home=False,
        enter=f"wsl.exe -d {name} -u {USER}",
    )

    # WSL 2 with the distribution; installing it may need an
    # administrator.
    def have_wsl() -> bool:
        version = wsl_version(output(["wsl.exe", "-l", "-v"]), name)
        return version == 2 and run(
            ["wsl.exe", "-d", name, "-u", "root", "--exec", "true"],
            quiet=True,
        )

    def install_wsl() -> None:
        version = wsl_version(output(["wsl.exe", "-l", "-v"]), name)
        if version == 0:
            ask_user(
                f"WSL 2 with {name} is needed; installing it may need"
                " an administrator (and, the first time, a restart).",
                [
                    "wsl.exe",
                    "--install",
                    "-d",
                    name,
                    "--no-launch",
                    "--web-download",
                ],
                yes=options.yes,
            )
        elif version != 2:
            ask_user(
                f"{name} runs on WSL {version}; LinuxCNC needs WSL 2.",
                ["wsl.exe", "--set-version", name, "2"],
                yes=options.yes,
            )

    return target, [
        Step(f"WSL 2 with {name}", have_wsl, install_wsl),
    ]


# Function `common_steps()`:
def common_steps(target: Target) -> list[Step]:
    """Return the steps that install LinuxCNC in a target.

    Arguments:
    * `target` (`Target`): The target.

    Returns:
    * (`list[Step]`): The steps, in order.
    """
    # The user comes first, since the other checks run as the user.
    # Debian Trixie: an older Debian (WSL's) is upgraded.
    codename = ["sh", "-c", ". /etc/os-release; echo $VERSION_CODENAME"]

    def is_trixie() -> bool:
        return output(target.command(codename)) == "trixie"

    def upgrade() -> None:
        old = output(target.command(codename, root=True))
        if not re.fullmatch(r"[a-z]+", old):
            raise SystemExit(f"Not Debian, or not reachable ({old!r}).")
        run(
            target.command(
                [
                    "sh",
                    "-c",
                    f"sed -i 's/\\b{old}\\b/trixie/g' {SOURCES} || true",
                ],
                root=True,
            )
        )
        run(target.command(apt_get("update"), root=True))
        run(target.command(apt_get("-y", "full-upgrade"), root=True))

    # A user who is not root, who runs LinuxCNC (`rtapi_app` refuses
    # root).  A box and the VM already have one.
    def have_user() -> bool:
        uid = output(target.command(["id", "-u"]))
        return uid.isdigit() and uid != "0"

    def make_user() -> None:
        run(
            target.command(
                ["useradd", "-m", "-s", "/bin/bash", USER], root=True
            )
        )

    # LinuxCNC, from the newest package for the target's architecture.
    def have_linuxcnc() -> bool:
        status = output(
            target.command(["dpkg-query", "-W", "-f", "${Status}", PACKAGE])
        )
        return status == "install ok installed"

    def install_linuxcnc() -> None:
        arch = output(target.command(["dpkg", "--print-architecture"]))
        version, url, sha256 = newest_package(arch)
        print(f"{stamp()} {PACKAGE} {version} for {arch}")
        inside = send_file(target, download(url, sha256))
        before = len(output(target.command(PACKAGES, root=True)).split())
        run(target.command(apt_get("update"), root=True))
        run(target.command(apt_get(*INSTALL, inside), root=True))
        after = len(output(target.command(PACKAGES, root=True)).split())
        print(f"{stamp()} apt installed {after - before} packages.")

    # `rtapi_app` is set user ID root, but a box's root is not really
    # root under rootless `podman`, so it can not open the shared
    # memory the rest of LinuxCNC makes.  A simulator needs no
    # realtime priority, so the bit is cleared everywhere.  (An
    # upgrade of the package sets it again; this step then clears it
    # again.)
    def rtapi_fixed() -> bool:
        return run(
            target.command(["test", "!", "-u", "/usr/bin/rtapi_app"]),
            quiet=True,
        )

    def fix_rtapi() -> None:
        run(target.command(["chmod", "u-s", "/usr/bin/rtapi_app"], root=True))

    # LinuxCNC's sample simulator configurations, in the user's home
    # directory, unless they are there.
    configs = f"{target.home}/{CONFIGS}"

    def have_samples() -> bool:
        return run(
            target.command(["test", "-d", f"{configs}/sim"]), quiet=True
        )

    def copy_samples() -> None:
        run(target.command(["mkdir", "-p", configs]))
        run(target.command(["cp", "-r", SAMPLES, configs]))

    # The checks: Python can use LinuxCNC, and its realtime layer
    # starts.  (When LinuxCNC is running, it has started; `halrun`
    # would stop it, so it is not run then.)
    def can_import() -> bool:
        return run(
            target.command(["python3", "-c", "import linuxcnc"]),
            quiet=True,
        )

    def cannot_import() -> None:
        raise SystemExit(f"`import linuxcnc` fails in {target.name}.")

    def axis_loads() -> bool:
        return run(
            target.command(["env", "-u", "DISPLAY", "python3", "-c",
                            f"import {', '.join(AXIS_MODULES)}"]),
            quiet=True,
        )  # fmt: skip

    def axis_fails() -> None:
        for module in AXIS_MODULES:
            run(target.command(["python3", "-c", f"import {module}"]))
        raise SystemExit(f"AXIS's modules do not load in {target.name}.")

    def realtime_starts() -> bool:
        if run(target.command(["pgrep", "-x", "rtapi_app"]), quiet=True):
            print(f"{stamp()} LinuxCNC is running, so halrun is not run.")
            return True
        _, text = capture(target.command(["sh", "-c", HALRUN]))
        return halrun_ok(text)

    def realtime_fails() -> None:
        _, text = capture(target.command(["sh", "-c", HALRUN]))
        print(text)
        raise SystemExit(f"LinuxCNC's realtime layer fails in {target.name}.")

    return [
        Step("a user who is not root", have_user, make_user),
        Step(f"Debian Trixie in {target.name}", is_trixie, upgrade),
        Step(f"{PACKAGE} in {target.name}", have_linuxcnc, install_linuxcnc),
        Step("rtapi_app not set user ID root", rtapi_fixed, fix_rtapi),
        Step(
            f"sample configurations in {configs}", have_samples, copy_samples
        ),
        Step(f"import linuxcnc in {target.name}", can_import, cannot_import),
        Step("the AXIS screen's Python modules load", axis_loads, axis_fails),
        Step(
            "LinuxCNC's realtime layer starts (halrun)",
            realtime_starts,
            realtime_fails,
        ),
    ]


# The routes, and the functions that give their targets and steps.
ROUTES: dict[str, Callable[[Options], tuple[Target, list[Step]]]] = {
    "distrobox": box_steps,
    "wsl": wsl_steps,
    "podman": podman_steps,
    "colima": colima_steps,
    "qemu": qemu_steps,
}


# Function `steps()`:
def steps(options: Options) -> tuple[Target, list[Step]]:
    """Return the target and every step that installs LinuxCNC in it.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`tuple[Target, list[Step]]`): The target and the steps, in
      order.
    """
    target, setup = ROUTES[options.route](options)
    return target, [*setup, *common_steps(target)]


# Function `install()`:
def install(options: Options) -> int:
    """Do every step that is not already done, checking each.

    Arguments:
    * `options` (`Options`): The command line.

    Returns:
    * (`int`): The exit status (0 when everything is done).
    """
    # Do (or ask for) each step, then check that it is done.
    target, all_steps = steps(options)
    print(
        f"{stamp()} Installing {PACKAGE} in {target.name} ({options.route})."
    )
    for number, step in enumerate(all_steps, 1):
        heading = f"[{number}/{len(all_steps)}] {step.title}"
        if step.done():
            print(f"{stamp()} {heading}: already done.", flush=True)
            continue
        print(f"{stamp()} {heading}: ...", flush=True)
        step.act()
        if not step.done():
            print(f"{stamp()} {heading}: FAILED.", file=sys.stderr)
            return 1
        print(f"{stamp()} {heading}: done.", flush=True)

    # Say how to reach it.
    print(
        f"\n{stamp()} LinuxCNC is installed in {target.name}.  To reach"
        f" it:\n\n    {target.enter}"
    )
    return 0


# Function `add_target_arguments()`:
def add_target_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the arguments that choose the target and how it is reached.

    `demo_linuxcnc.py` takes the same ones, so that it finds the
    target this program made.

    Arguments:
    * `parser` (`argparse.ArgumentParser`): The parser to add them to.
    """
    parser.add_argument(
        "--box", default="lcnc", help="the box's name (default: lcnc)"
    )
    parser.add_argument(
        "--distribution",
        default="Debian",
        help="the WSL distribution's name (default: Debian)",
    )
    parser.add_argument(
        "--route",
        choices=sorted(ROUTES),
        help="how to install it (default: chosen for this computer)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="run the commands the user would be asked to (for tests)",
    )


# Function `target_options()`:
def target_options(arguments: argparse.Namespace) -> Options:
    """Return the options that `add_target_arguments()` read.

    Output that the console can not show (Windows) is replaced from
    now on, not an error, and `wsl.exe` is asked to print UTF-8.

    Arguments:
    * `arguments` (`argparse.Namespace`): The parsed command line.

    Returns:
    * (`Options`): The options, with the route chosen for this
      computer unless `--route` named one.
    """
    # Output that the console can not show is replaced.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")

    # Choose the route; `wsl.exe` prints UTF-8 when asked to.
    system = platform.system()
    os.environ["WSL_UTF8"] = "1"
    route: str = arguments.route or choose_route(
        system,
        platform.machine(),
        output(["sysctl", "-n", "kern.hv_support"])
        if system == "Darwin"
        else "",
    )
    return Options(
        route=route,
        box=arguments.box,
        distribution=arguments.distribution,
        yes=arguments.yes,
    )


# Function `main()`:
def main() -> int:
    """Install LinuxCNC's simulator, as the command line asks.

    Returns:
    * (`int`): The exit status.
    """
    # Read the command line.
    parser = argparse.ArgumentParser(
        description="Install LinuxCNC's simulator in Debian Trixie: a"
        " distrobox (Linux), WSL 2 (Windows), or a container or QEMU VM"
        " (macOS)."
    )
    add_target_arguments(parser)
    options = target_options(parser.parse_args())

    # Install it.
    try:
        return install(options)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
