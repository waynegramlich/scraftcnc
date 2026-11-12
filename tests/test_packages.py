"""Tests for `scraftcam.packages`.

`pip` is never run, and nothing is fetched: `subprocess.run` and
`pip_wheel()` are replaced by stand-ins, and every directory is a
temporary one.
"""

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scraftcam import packages

# A `pins.toml` with a checked and an unchecked module.
PINS: str = """\
[checked]
"checked==1.0" = ["aa", "bb"]
"helper==2.0" = ["cc"]

[unchecked]
"unchecked>=1" = []

[mixed]
"one==1" = ["aa"]
"two==2" = []
"""


# Class `TestPackages`:
class TestPackages(unittest.TestCase):
    """Installing into a module's own directory, swapped in whole."""

    # Method `TestPackages.setUp()`:
    def setUp(self) -> None:
        """Point `packages` at temporary files, with a fake `pip`."""
        # Temporary pins and packages directory (`enterContext()` cleans
        # it up, which `pylint` does not know).
        directory: tempfile.TemporaryDirectory[str] = (
            tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        )
        self.top: Path = Path(self.enterContext(directory))
        pins_file: Path = self.top / "pins.toml"
        pins_file.write_text(PINS, encoding="utf-8")
        self.packages_directory: Path = self.top / "packages" / "tag"
        patches: list[Any] = [
            mock.patch.object(packages, "PINS_FILE", pins_file),
            mock.patch.object(
                packages, "PACKAGES_DIRECTORY", self.packages_directory
            ),
            mock.patch.object(packages, "make_directory", self.make_directory),
            mock.patch.object(
                packages, "pip_wheel", return_value=self.top / "pip.whl"
            ),
            mock.patch.object(subprocess, "run", self.run_pip),
            mock.patch.object(importlib, "import_module"),
            mock.patch.object(sys, "path", list(sys.path)),
            mock.patch.object(sys, "stderr"),
        ]
        patch: Any
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

        # What the fake `pip` was asked, and how it ends.
        self.calls: list[list[str]] = []
        self.failing: bool = False

    # Method `TestPackages.make_directory()`:
    def make_directory(self, directory: Path) -> Path:
        """Make `directory` (stands in for `home.make_directory()`).

        Arguments:
        * `directory` (`Path`):
          The directory.

        Returns:
        * (`Path`): `directory`.
        """
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    # Method `TestPackages.run_pip()`:
    def run_pip(
        self, command: list[str], **_options: Any
    ) -> subprocess.CompletedProcess[str]:
        """Pretend to be `pip`: write a file named for the requirements.

        Arguments:
        * `command` (`list[str]`):
          The command `install()` runs.
        * `_options` (`Any`):
          `subprocess.run()`'s options (ignored).

        Returns:
        * (`subprocess.CompletedProcess[str]`): Success, or a failure
          when `self.failing` is set.
        """
        # Write one file into the target, named for this install.
        self.calls.append(command)
        target: Path = Path(command[command.index("--target") + 1])
        requirements: Path = Path(command[command.index("-r") + 1])
        (target / f"installed{len(self.calls)}").write_text(
            requirements.read_text(encoding="utf-8"), encoding="utf-8"
        )
        if self.failing:
            return subprocess.CompletedProcess(command, 1, "", "ERROR: no")
        return subprocess.CompletedProcess(command, 0, "", "")

    # Method `TestPackages.test_requirements()`:
    def test_requirements(self) -> None:
        """A requirements line per key, with its digests."""
        self.assertEqual(
            packages.requirements("checked"),
            "checked==1.0 --hash=sha256:aa --hash=sha256:bb\n"
            "helper==2.0 --hash=sha256:cc\n",
        )
        self.assertEqual(packages.requirements("unchecked"), "unchecked>=1\n")
        with self.assertRaises(ValueError):
            packages.requirements("mixed")

    # Method `TestPackages.test_install_once()`:
    def test_install_once(self) -> None:
        """Installed once, checked, then put first on `sys.path`."""
        # The first time, `pip` checks the digests and takes wheels.
        packages.require("checked")
        directory: Path = self.packages_directory / "checked"
        self.assertEqual(len(self.calls), 1)
        self.assertIn("--require-hashes", self.calls[0])
        self.assertIn("--only-binary=:all:", self.calls[0])
        self.assertTrue((directory / "installed1").is_file())
        self.assertEqual(
            (directory / packages.STAMP).read_text("utf-8"),
            packages.requirements("checked"),
        )
        self.assertEqual(sys.path[0], str(directory))

        # The second time, nothing is installed.
        packages.require("checked")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(
            sorted(path.name for path in self.packages_directory.iterdir()),
            ["checked"],
        )

    # Method `TestPackages.test_unchecked()`:
    def test_unchecked(self) -> None:
        """Without digests, `pip` is not asked to check any."""
        packages.require("unchecked")
        self.assertNotIn("--require-hashes", self.calls[0])
        self.assertNotIn("--only-binary=:all:", self.calls[0])

    # Method `TestPackages.test_new_pins()`:
    def test_new_pins(self) -> None:
        """Changed pins: a fresh directory, swapped in whole."""
        # Install, then change the module's table.
        packages.require("unchecked")
        pins_file: Path = packages.PINS_FILE
        pins_file.write_text(
            PINS.replace("unchecked>=1", "unchecked>=2"), encoding="utf-8"
        )

        # The old install's file is gone: nothing is mixed.
        packages.require("unchecked")
        directory: Path = self.packages_directory / "unchecked"
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(
            sorted(path.name for path in directory.iterdir()),
            ["installed2", packages.STAMP],
        )
        self.assertEqual(
            sorted(path.name for path in self.packages_directory.iterdir()),
            ["unchecked"],
        )

    # Method `TestPackages.test_failure_keeps_old()`:
    def test_failure_keeps_old(self) -> None:
        """A failed install leaves the old one as it was."""
        # Install, change the table, and fail the next install.
        packages.require("unchecked")
        packages.PINS_FILE.write_text(
            PINS.replace("unchecked>=1", "unchecked>=2"), encoding="utf-8"
        )
        self.failing = True
        with self.assertRaises(SystemExit):
            packages.require("unchecked")

        # The old install is still whole, with nothing beside it.
        directory: Path = self.packages_directory / "unchecked"
        self.assertEqual(
            sorted(path.name for path in directory.iterdir()),
            ["installed1", packages.STAMP],
        )
        self.assertEqual(
            sorted(path.name for path in self.packages_directory.iterdir()),
            ["unchecked"],
        )

    # Method `TestPackages.test_unknown_module()`:
    def test_unknown_module(self) -> None:
        """A module with no table in `pins.toml` stops the program."""
        with self.assertRaises(SystemExit):
            packages.require("nothing")

    # Method `TestPackages.test_old_layout()`:
    def test_old_layout(self) -> None:
        """Packages installed the old way are deleted, modules kept."""
        # The old layout, beside a module installed the new way.
        packages.require("checked")
        old: Path = self.packages_directory
        (old / "pdfplumber").mkdir()
        (old / "pdfplumber-0.11.dist-info").mkdir()
        (old / "_cffi_backend.so").write_text("", encoding="utf-8")

        # Only the module's directory is left.
        packages.drop_old_layout()
        self.assertEqual(
            sorted(path.name for path in old.iterdir()), ["checked"]
        )

    # Method `TestPackages.test_pins()`:
    def test_pins(self) -> None:
        """`pins()` lists the digest of every wheel of a release."""
        # PyPI's answer, with a wheel and a source archive.
        answer: bytes = (
            b'{"urls": ['
            b'{"filename": "a-1-py3-none-any.whl",'
            b' "digests": {"sha256": "aa"}},'
            b'{"filename": "a-1.tar.gz", "digests": {"sha256": "bb"}}]}'
        )
        with mock.patch.object(packages, "fetch", return_value=answer):
            self.assertEqual(
                packages.pins(["a==1"]), '"a==1" = [\n    "aa",\n]\n'
            )
            with self.assertRaises(ValueError):
                packages.pins(["a>=1"])


if __name__ == "__main__":
    unittest.main()
