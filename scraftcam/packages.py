"""Packages from PyPI, fetched the first time they are needed.

`scraftcam` needs nothing outside the standard library, except for a
few parts (such as the catalog extractor, which needs `pdfplumber`,
and the HMI, which needs `PySide6`).  What each needs is listed in
`pins.toml`.  Each module's packages are installed by `pip` into a
directory of their own, `~/.scraftcam/packages/TAG/MODULE/` (`TAG` is
e.g. `cpython-312`, since some packages are compiled for one Python),
never into the Python installation.  `pip` itself can not be assumed
(Ubuntu's Python has none), so its wheel is fetched from PyPI too,
checked against its SHA-256 digest, and run straight from the wheel.

A module's directory is never installed into twice: when its table in
`pins.toml` changes, a fresh directory is made beside it, and swapped
in whole once `pip` has finished, so two versions are never mixed.

Typical use:

    require("pdfplumber")
    import pdfplumber

Run as a program, it prints the `pins.toml` lines (with the SHA-256
digests of every wheel on PyPI) for the requirements it is given:

    python3 -m scraftcam.packages PySide6-Essentials==6.12.0 ...
"""

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .home import HOME_DIRECTORY, make_directory

# Where the packages for this Python go.
PACKAGES_DIRECTORY: Path = (
    HOME_DIRECTORY / "packages" / sys.implementation.cache_tag
)

# What `require()` installs for each module.
PINS_FILE: Path = Path(__file__).parent / "pins.toml"

# The file in a module's directory that says what is installed there,
# written last, once `pip` has finished.
STAMP: str = "requirements.txt"

# Where `pip`'s wheel goes.
PIP_DIRECTORY: Path = HOME_DIRECTORY / "pip"

# PyPI's description of `pip`'s releases, and of one release.
PIP_JSON_URL: str = "https://pypi.org/pypi/pip/json"
RELEASE_JSON_URL: str = "https://pypi.org/pypi/{name}/{version}/json"


# Function `fetch()`:
def fetch(url: str) -> bytes:
    """Fetch `url`, with `curl` when Python has no certificates.

    Some Pythons (e.g. python.org's on macOS) have no certificates
    until the user installs them, so `curl` is tried when `urllib`
    fails.

    Arguments:
    * `url` (`str`):
      The URL to fetch.

    Returns:
    * (`bytes`): What the URL holds.

    Raises:
    * `urllib.error.URLError`: If neither `urllib` nor `curl` can
      fetch it.
    """
    # Try `urllib` first.
    try:
        with urllib.request.urlopen(url, None, 60) as response:
            return bytes(response.read())
    except urllib.error.URLError as error:
        # Then `curl`; report the first error if it fails too.
        try:
            completed: subprocess.CompletedProcess[bytes] = subprocess.run(
                ["curl", "-fsSL", url], capture_output=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            raise error from None
        return completed.stdout


# Function `pip_wheel()`:
def pip_wheel() -> Path:
    """Return `pip`'s wheel, fetching it from PyPI the first time.

    Returns:
    * (`Path`): The wheel, in `PIP_DIRECTORY`.

    Raises:
    * `urllib.error.URLError`: If PyPI can not be reached.
    * `ValueError`: If the wheel fails its SHA-256 check.
    """
    # Use the wheel fetched before, if there is one.
    wheels: list[Path] = sorted(PIP_DIRECTORY.glob("pip-*.whl"))
    if wheels:
        return wheels[-1]

    # Find the newest wheel on PyPI and fetch it.
    print("Fetching pip from PyPI.", file=sys.stderr)
    description: dict[str, Any] = json.loads(fetch(PIP_JSON_URL))
    entry: dict[str, Any] = next(
        entry
        for entry in description["urls"]
        if str(entry["filename"]).endswith(".whl")
    )
    data: bytes = fetch(str(entry["url"]))
    if hashlib.sha256(data).hexdigest() != entry["digests"]["sha256"]:
        raise ValueError(f"{entry['filename']} fails its SHA-256 check")

    # Write it under a temporary name first, so a half written wheel
    # is never used.
    make_directory(PIP_DIRECTORY)
    wheel: Path = PIP_DIRECTORY / str(entry["filename"])
    partial: Path = wheel.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(wheel)
    return wheel


# Function `requirements()`:
def requirements(module: str) -> str:
    """Return the `pip` requirements file for `module`.

    Arguments:
    * `module` (`str`):
      The module to import, a table of `PINS_FILE`.

    Returns:
    * (`str`): One line per requirement, with its `--hash` options.

    Raises:
    * `KeyError`: If `PINS_FILE` has no table for `module`.
    * `ValueError`: If only some of its requirements have digests.
    """
    # Read the module's table.
    with PINS_FILE.open("rb") as pins_file:
        table: dict[str, list[str]] = tomllib.load(pins_file)[module]

    # All requirements are checked, or none.
    checked: set[bool] = {bool(digests) for digests in table.values()}
    if len(checked) > 1:
        raise ValueError(
            f"{PINS_FILE}: [{module}]: some requirements have no digests"
        )

    # One line each.
    lines: list[str] = [
        " ".join(
            [requirement] + [f"--hash=sha256:{digest}" for digest in digests]
        )
        for requirement, digests in table.items()
    ]
    return "".join(f"{line}\n" for line in lines)


# Function `install()`:
def install(module: str, text: str) -> None:
    """Install the packages for `module` into a fresh directory.

    `pip` installs into `.MODULE.part`, which is then swapped in whole
    for `MODULE`, so a failed install leaves the old one as it was.

    Arguments:
    * `module` (`str`):
      The module to import, a table of `PINS_FILE`.
    * `text` (`str`):
      Its requirements file (from `requirements()`).

    Raises:
    * `OSError`: If a file can not be written, or `pip` not run.
    * `SystemExit`: If `pip` fails.
    * `urllib.error.URLError`: If PyPI can not be reached.
    * `ValueError`: If `pip`'s wheel fails its SHA-256 check.
    """
    # Start from empty directories and a requirements file beside them.
    make_directory(PACKAGES_DIRECTORY)
    directory: Path = PACKAGES_DIRECTORY / module
    partial: Path = PACKAGES_DIRECTORY / f".{module}.part"
    old: Path = PACKAGES_DIRECTORY / f".{module}.old"
    for leftover in (partial, old):
        shutil.rmtree(leftover, ignore_errors=True)
    partial.mkdir()
    requirements_file: Path = PACKAGES_DIRECTORY / f".{module}.txt"
    requirements_file.write_text(text, encoding="utf-8")

    # With digests, `pip` checks every download, and takes wheels only.
    checked: list[str] = (
        ["--require-hashes", "--only-binary=:all:"]
        if "--hash=" in text
        else []
    )

    # Install it with `pip`, run from its wheel.
    wheel: Path = pip_wheel()
    print(f"Installing {module} into {directory}.", file=sys.stderr)
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            str(wheel / "pip"),
            "install",
            "--quiet",
            "--disable-pip-version-check",
            # After installing, `pip` checks every package it can
            # see, including those already installed in this Python
            # (e.g. by `apt` in `/usr/lib/python3/`), and writes an
            # `ERROR:` report to standard error when one of those is
            # missing a dependency.  On the author's machine, an
            # unrelated system package (`sacad`) set it off, though
            # `pdfplumber` installed fine.  Those packages are not
            # ours to fix, and since anything on standard error is
            # treated as a failure below, the report would stop every
            # install.  This flag turns off only that report; a real
            # failure still writes errors and exits with a nonzero
            # status.
            "--no-warn-conflicts",
            *checked,
            "--target",
            str(partial),
            "-r",
            str(requirements_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    requirements_file.unlink()

    # For now, anything `pip` writes to standard error is an error.
    if completed.returncode != 0 or completed.stderr.strip():
        sys.stderr.write(completed.stderr)
        shutil.rmtree(partial, ignore_errors=True)
        raise SystemExit(
            f"Could not install {module} "
            f"(pip exit status {completed.returncode})"
        )

    # Mark it finished, then swap it in, and drop the old one.
    (partial / STAMP).write_text(text, encoding="utf-8")
    if directory.exists():
        directory.rename(old)
    partial.rename(directory)
    shutil.rmtree(old, ignore_errors=True)


# Function `drop_old_layout()`:
def drop_old_layout() -> None:
    """Delete packages installed the old way, all in one directory.

    Before each module had a directory of its own, everything was
    installed straight into `PACKAGES_DIRECTORY`; those packages are
    deleted (the modules' own directories are kept), and installed
    again when they are next needed.
    """
    # The old layout has `pip`'s `.dist-info` directories at the top
    # (`make_directory()` first moves an old home into place).
    make_directory(PACKAGES_DIRECTORY)
    if next(PACKAGES_DIRECTORY.glob("*.dist-info"), None) is None:
        return
    print(
        f"Deleting the old packages in {PACKAGES_DIRECTORY}.",
        file=sys.stderr,
    )

    # Everything but the modules' directories, and installs under way.
    entry: Path
    for entry in PACKAGES_DIRECTORY.iterdir():
        if entry.name.startswith(".") or (entry / STAMP).is_file():
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


# Function `require()`:
def require(module: str) -> None:
    """Make `module` importable, installing its packages if need be.

    Its directory is put first on `sys.path`; when it does not hold
    what `PINS_FILE` asks for, `pip` installs that first.

    Arguments:
    * `module` (`str`):
      The module to import, a table of `PINS_FILE` (e.g.
      `pdfplumber`).

    Raises:
    * `SystemExit`: If the packages can not be fetched or installed.
    """
    try:
        # Install it, unless it is there already.
        drop_old_layout()
        text: str = requirements(module)
        directory: Path = PACKAGES_DIRECTORY / module
        stamp: Path = directory / STAMP
        if not stamp.is_file() or stamp.read_text("utf-8") != text:
            install(module, text)

        # Import it from its directory.
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
        importlib.invalidate_caches()
        importlib.import_module(module)
    except (
        ImportError,
        KeyError,
        OSError,
        ValueError,
        urllib.error.URLError,
    ) as error:
        raise SystemExit(f"Could not install {module}: {error}") from error


# Function `pins()`:
def pins(specifications: list[str]) -> str:
    """Return `PINS_FILE` lines for exact requirements, from PyPI.

    Arguments:
    * `specifications` (`list[str]`):
      Requirements of the form `NAME==VERSION`.

    Returns:
    * (`str`): A key per requirement, listing the SHA-256 digest of
      every wheel PyPI has for it.

    Raises:
    * `urllib.error.URLError`: If PyPI can not be reached.
    * `ValueError`: If a requirement is not `NAME==VERSION`, or has no
      wheels.
    """
    # One key per requirement.
    lines: list[str] = []
    specification: str
    for specification in specifications:
        name: str
        version: str
        name, separator, version = specification.partition("==")
        if not separator or not name or not version:
            raise ValueError(f"{specification}: not NAME==VERSION")

        # Every wheel of the release.
        url: str = RELEASE_JSON_URL.format(name=name, version=version)
        description: dict[str, Any] = json.loads(fetch(url))
        digests: list[str] = [
            str(entry["digests"]["sha256"])
            for entry in description["urls"]
            if str(entry["filename"]).endswith(".whl")
        ]
        if not digests:
            raise ValueError(f"{specification}: PyPI has no wheels")
        lines.append(f'"{specification}" = [')
        lines.extend(f'    "{digest}",' for digest in digests)
        lines.append("]")
    return "".join(f"{line}\n" for line in lines)


# Function `main()`:
def main() -> None:
    """Print `PINS_FILE` lines for the requirements on the command line."""
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python3 -m scraftcam.packages NAME==VERSION ..."
        )
    sys.stdout.write(pins(sys.argv[1:]))


if __name__ == "__main__":
    main()
