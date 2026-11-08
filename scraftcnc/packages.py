"""Packages from PyPI, fetched the first time they are needed.

`scraftcnc` needs nothing outside the standard library, except for a
few optional parts (such as the catalog extractor, which needs
`pdfplumber`).  Those packages are installed by `pip` into
`~/.scraftcnc/packages/TAG/` (`TAG` is e.g. `cpython-312`, since some
packages are compiled for one Python), never into the Python
installation.  `pip` itself can not be assumed (Ubuntu's Python has
none), so its wheel is fetched from PyPI too, checked against its
SHA-256 digest, and run straight from the wheel.

Typical use:

    require("pdfplumber", "pdfplumber>=0.11")
    import pdfplumber
"""

import hashlib
import importlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .home import HOME_DIRECTORY, make_directory

# Where the packages for this Python go.
PACKAGES_DIRECTORY: Path = (
    HOME_DIRECTORY / "packages" / sys.implementation.cache_tag
)

# Where `pip`'s wheel goes.
PIP_DIRECTORY: Path = HOME_DIRECTORY / "pip"

# PyPI's description of `pip`'s releases.
PIP_JSON_URL: str = "https://pypi.org/pypi/pip/json"


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


# Function `require()`:
def require(module: str, requirement: str) -> None:
    """Make `module` importable, installing `requirement` if need be.

    `PACKAGES_DIRECTORY` is put on `sys.path`; when `module` still can
    not be imported, `pip` installs `requirement` there.

    Arguments:
    * `module` (`str`):
      The module to import (e.g. `pdfplumber`).
    * `requirement` (`str`):
      What `pip` installs (e.g. `pdfplumber>=0.11`).

    Raises:
    * `SystemExit`: If the package can not be fetched or installed.
    """
    # Look in `PACKAGES_DIRECTORY` (and the rest of `sys.path`).
    directory: str = str(PACKAGES_DIRECTORY)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    try:
        importlib.import_module(module)
        return
    except ImportError:
        pass

    # Install it with `pip`, run from its wheel.
    try:
        make_directory(PACKAGES_DIRECTORY)
        wheel: Path = pip_wheel()
        print(
            f"Installing {requirement} into {PACKAGES_DIRECTORY}.",
            file=sys.stderr,
        )
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [
                sys.executable,
                str(wheel / "pip"),
                "install",
                "--quiet",
                "--disable-pip-version-check",
                # After installing, `pip` checks every package it can
                # see, including those already installed in this
                # Python (e.g. by `apt` in `/usr/lib/python3/`), and
                # writes an `ERROR:` report to standard error when
                # one of those is missing a dependency.  On the
                # author's machine, an unrelated system package
                # (`sacad`) set it off, though `pdfplumber` installed
                # fine.  Those packages are not ours to fix, and
                # since anything on standard error is treated as a
                # failure below, the report would stop every install.
                # This flag turns off only that report; a real failure
                # still writes errors and exits with a nonzero status.
                "--no-warn-conflicts",
                "--target",
                directory,
                requirement,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        # For now, anything `pip` writes to standard error is an error.
        if completed.returncode != 0 or completed.stderr.strip():
            sys.stderr.write(completed.stderr)
            raise SystemExit(
                f"Could not install {requirement} "
                f"(pip exit status {completed.returncode})"
            )
        importlib.invalidate_caches()
        importlib.import_module(module)
    except (
        ImportError,
        OSError,
        ValueError,
    ) as error:
        raise SystemExit(
            f"Could not install {requirement}: {error}"
        ) from error
