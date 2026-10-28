#!/usr/bin/env python3
"""Install LinuxCNC's simulator in a Debian Trixie `distrobox`.

`T.il~3.1`.  LinuxCNC offers packages only for Debian 13 Trixie, so
on another Linux (such as Ubuntu 24.04) its simulator,
`linuxcnc-uspace`, is installed in a Debian Trixie box made by
`distrobox` on `podman`.  Each step is checked first and skipped when
it is already done, so running this again is safe.  A step that
needs the user (such as a `sudo` on the host, which asks for a
password) is shown as a command, also put on the clipboard when
there is a way to, and this waits for the user to run it and then
checks it:

```
./install_linuxcnc.py                  # The `lcnc` box.
./install_linuxcnc.py --box lcnc-test  # Another box.
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini
```

Only Linux is supported so far; macOS and Windows (WSL) are being
looked into (see `TASKS/3.1_Installing_LinuxCNC/`).
"""

import argparse
import base64
import hashlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# The Debian image of the box.
IMAGE: str = "docker.io/library/debian:trixie"

# Where LinuxCNC's Trixie packages are; `ARCH` is the box's Debian
# architecture (`amd64`, `arm64`, ...).
REPOSITORY: str = "https://linuxcnc.org/dists/trixie/2.9-uspace"
PACKAGE: str = "linuxcnc-uspace"

# Where the downloaded package is kept (the box shares the home
# directory, so it sees the same file).
CACHE: Path = Path.home() / ".cache" / "scraftcnc"

# LinuxCNC's sample configurations, and where they are copied to.
SAMPLES: str = "/usr/share/doc/linuxcnc/examples/sample-configs/sim"
CONFIGS: Path = Path.home() / "linuxcnc" / "configs"


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


# Function `run()`:
def run(command: list[str], *, quiet: bool = False) -> bool:
    """Run a command, showing it first.

    Arguments:
    * `command` (`list[str]`): The command and its arguments.
    * `quiet` (`bool`):
      True to hide the command and its output (for checks).

    Returns:
    * (`bool`): True if it succeeded.
    """
    # Show the command, then let it use the terminal (`sudo` may ask
    # for a password).
    if quiet:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        print(f"$ {shlex.join(command)}", flush=True)
        result = subprocess.run(command, check=False)
    return result.returncode == 0


# Function `output()`:
def output(command: list[str]) -> str:
    """Run a command quietly and return what it prints.

    Arguments:
    * `command` (`list[str]`): The command and its arguments.

    Returns:
    * (`str`): Its standard output, stripped, or `""` if it failed.
    """
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


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
def ask_user(why: str, command: list[str]) -> None:
    """Ask the user to run a command, and wait until they have.

    Arguments:
    * `why` (`str`): Why the user must run it.
    * `command` (`list[str]`): The command for the user to run.

    Raises:
    * `SystemExit`: If there is nobody to ask (standard input is not
      a terminal).
    """
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
    """Return a command that runs a command in the box.

    Arguments:
    * `box` (`str`): The box's name.
    * `command` (`list[str]`): The command to run in it.

    Returns:
    * (`list[str]`): The `distrobox enter` command.
    """
    return ["distrobox", "enter", box, "--", *command]


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
def download(url: str, sha256: str) -> Path:
    """Download a file into `CACHE`, unless it is there already.

    Arguments:
    * `url` (`str`): Where it is.
    * `sha256` (`str`): Its SHA-256, to check it against.

    Returns:
    * (`Path`): The file.

    Raises:
    * `SystemExit`: If the file's SHA-256 is wrong.
    """
    # Download it, unless a good copy is already there.
    path = CACHE / url.rsplit("/", 1)[1]
    if not path.exists() or file_sha256(path) != sha256:
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {url}", flush=True)
        partial = path.with_suffix(".part")
        urllib.request.urlretrieve(url, partial)
        partial.replace(path)

    # Check it.
    if file_sha256(path) != sha256:
        path.unlink()
        raise SystemExit(f"{url}: wrong SHA-256; removed the download.")
    return path


# Function `file_sha256()`:
def file_sha256(path: Path) -> str:
    """Return a file's SHA-256.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`str`): Its SHA-256, in hexadecimal.
    """
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


# Function `steps()`:
def steps(box: str) -> list[Step]:
    """Return the steps that install LinuxCNC in a box.

    Arguments:
    * `box` (`str`): The box's name.

    Returns:
    * (`list[Step]`): The steps, in order.
    """

    # The host's tools: installed by the user, since it needs `sudo`.
    def have_tools() -> bool:
        return bool(shutil.which("podman") and shutil.which("distrobox"))

    def install_tools() -> None:
        ask_user(
            "`podman` and `distrobox` are needed, and installing them"
            " needs `sudo`.",
            ["sudo", "apt-get", "install", "-y", "podman", "distrobox"],
        )

    # The box.  Its first `distrobox enter` sets it up; a second one
    # at the same time can hang, so it is entered once here.
    def have_box() -> bool:
        return run(["podman", "container", "exists", box], quiet=True)

    def make_box() -> None:
        run(
            [
                "distrobox", "create", "--yes",
                "--name", box, "--image", IMAGE,
            ]
        )  # fmt: skip
        run(in_box(box, ["true"]))

    # LinuxCNC, from the newest package for the box's architecture.
    def have_linuxcnc() -> bool:
        return run(in_box(box, ["dpkg-query", "-W", PACKAGE]), quiet=True)

    def install_linuxcnc() -> None:
        arch = output(in_box(box, ["dpkg", "--print-architecture"]))
        version, url, sha256 = newest_package(arch)
        print(f"{PACKAGE} {version} for {arch}")
        path = download(url, sha256)
        run(in_box(box, ["sudo", "apt-get", "update"]))
        run(in_box(box, ["sudo", "apt-get", "install", "-y", str(path)]))

    # `rtapi_app` is set user ID root, but the box's root is not
    # really root under rootless `podman`, so it can not open the
    # shared memory the rest of LinuxCNC makes.  A simulator needs no
    # realtime priority, so the bit is cleared.  (An upgrade of the
    # package sets it again; this step then clears it again.)
    def rtapi_fixed() -> bool:
        return run(
            in_box(box, ["test", "!", "-u", "/usr/bin/rtapi_app"]),
            quiet=True,
        )

    def fix_rtapi() -> None:
        run(in_box(box, ["sudo", "chmod", "u-s", "/usr/bin/rtapi_app"]))

    # LinuxCNC's sample simulator configurations, in the home
    # directory (which the box shares), unless they are there.
    def have_samples() -> bool:
        return (CONFIGS / "sim").exists()

    def copy_samples() -> None:
        CONFIGS.mkdir(parents=True, exist_ok=True)
        run(in_box(box, ["cp", "-r", SAMPLES, str(CONFIGS)]))

    # The check: Python in the box can use LinuxCNC.
    def can_import() -> bool:
        return run(
            in_box(box, ["python3", "-c", "import linuxcnc"]), quiet=True
        )

    def cannot_import() -> None:
        raise SystemExit("`import linuxcnc` fails in the box.")

    return [
        Step("podman and distrobox", have_tools, install_tools),
        Step(f"the {box} box (Debian Trixie)", have_box, make_box),
        Step(f"{PACKAGE} in the box", have_linuxcnc, install_linuxcnc),
        Step("rtapi_app not set user ID root", rtapi_fixed, fix_rtapi),
        Step(f"sample configurations in {CONFIGS}", have_samples,
             copy_samples),
        Step("import linuxcnc in the box", can_import, cannot_import),
    ]  # fmt: skip


# Function `install()`:
def install(box: str) -> int:
    """Do every step that is not already done, checking each.

    Arguments:
    * `box` (`str`): The box's name.

    Returns:
    * (`int`): The exit status (0 when everything is done).
    """
    # Do (or ask for) each step, then check that it is done.
    all_steps = steps(box)
    for number, step in enumerate(all_steps, 1):
        heading = f"[{number}/{len(all_steps)}] {step.title}"
        if step.done():
            print(f"{heading}: already done.")
            continue
        print(f"{heading}: ...", flush=True)
        step.act()
        if not step.done():
            print(f"{heading}: FAILED.", file=sys.stderr)
            return 1
        print(f"{heading}: done.")

    # Say how to start it.
    print(
        f"\nLinuxCNC is installed in the {box} box.  To start the"
        f" example shop's mill:\n\n"
        f"    distrobox enter {box} -- linuxcnc lcnc_sim/shop_mill.ini"
    )
    return 0


# Function `main()`:
def main() -> int:
    """Install LinuxCNC's simulator, as the command line asks.

    Returns:
    * (`int`): The exit status.
    """
    # Read the command line.
    parser = argparse.ArgumentParser(
        description="Install LinuxCNC's simulator in a Debian Trixie"
        " distrobox."
    )
    parser.add_argument(
        "--box", default="lcnc", help="the box's name (default: lcnc)"
    )
    arguments = parser.parse_args()
    box: str = arguments.box

    # Only Linux so far.
    system = platform.system()
    if system != "Linux":
        print(
            f"{system} is not supported yet (only Linux).",
            file=sys.stderr,
        )
        return 1

    # Install it.
    try:
        return install(box)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
