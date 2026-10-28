"""Tests for `install_linuxcnc.py` that need no network or box."""

import io
import unittest
from unittest import mock

import install_linuxcnc

# A small `Packages` index with three versions and another package.
INDEX: str = """Package: linuxcnc-uspace
Version: 1:2.9.9
Filename: dists/trixie/2.9-uspace/binary-amd64/linuxcnc-uspace_2.9.9_amd64.deb
SHA256: 99

Package: linuxcnc-uspace
Version: 1:2.9.10
Depends: python3 (<< 3.14),
 libc6 (>= 2.38)
Filename: dists/trixie/2.9-uspace/binary-amd64/linuxcnc-uspace_2.9.10_amd64.deb
SHA256: 10

Package: linuxcnc-doc-en
Version: 1:2.9.11
Filename: dists/trixie/2.9-uspace/binary-all/linuxcnc-doc-en_2.9.11_all.deb
SHA256: 11

Package: linuxcnc-uspace
Version: 1:2.9.2
Filename: dists/trixie/2.9-uspace/binary-amd64/linuxcnc-uspace_2.9.2_amd64.deb
SHA256: 2
"""


class TestInstallLinuxCNC(unittest.TestCase):
    """The parts of the installer that can be tested offline."""

    def test_version_key(self) -> None:
        """Versions sort by epoch, then numerically."""
        versions = ["1:2.9.9", "2.10.0", "1:2.9.10", "1:2.9.2"]
        self.assertEqual(
            sorted(versions, key=install_linuxcnc.version_key),
            ["2.10.0", "1:2.9.2", "1:2.9.9", "1:2.9.10"],
        )

    def test_newest_package(self) -> None:
        """The newest `linuxcnc-uspace` is found, not another package."""
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(INDEX.encode())
        with mock.patch("urllib.request.urlopen", return_value=response):
            version, url, sha256 = install_linuxcnc.newest_package("amd64")
        self.assertEqual(version, "1:2.9.10")
        self.assertTrue(url.endswith("linuxcnc-uspace_2.9.10_amd64.deb"))
        self.assertTrue(url.startswith("https://linuxcnc.org/dists/"))
        self.assertEqual(sha256, "10")

    def test_in_box(self) -> None:
        """A command in the box goes through `distrobox enter`."""
        self.assertEqual(
            install_linuxcnc.in_box("b", ["true"]),
            ["distrobox", "enter", "b", "--", "true"],
        )

    def test_clipboard_fallback(self) -> None:
        """With no clipboard program and no terminal, nothing is copied."""
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch("sys.stdout", new=io.StringIO()),
        ):
            how = install_linuxcnc.copy_to_clipboard("ls")
        self.assertIn("not copied", how)

    def test_ask_user_without_terminal(self) -> None:
        """With nobody to ask, the installer stops."""
        with (
            mock.patch("sys.stdin", new=io.StringIO()),
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch("shutil.which", return_value=None),
            self.assertRaises(SystemExit),
        ):
            install_linuxcnc.ask_user("Why.", ["sudo", "true"])


if __name__ == "__main__":
    unittest.main()
