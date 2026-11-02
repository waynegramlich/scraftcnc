"""Tests for `install_linuxcnc.py` that need no network or box."""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scraftlinuxcnc import install_linuxcnc

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

    def test_newest_package_retries(self) -> None:
        """A timeout of the index is tried again."""
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(INDEX.encode())
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[TimeoutError("slow"), response],
            ),
            mock.patch("time.sleep") as sleep,
            mock.patch("sys.stdout", new=io.StringIO()),
        ):
            version, _, _ = install_linuxcnc.newest_package("amd64")
        self.assertEqual(version, "1:2.9.10")
        sleep.assert_called_once_with(install_linuxcnc.RETRY_WAIT)

    def test_retry_gives_up(self) -> None:
        """The last failure is passed on, after `TRIES` tries."""
        action = mock.Mock(side_effect=TimeoutError("slow"))
        with (
            mock.patch("time.sleep"),
            mock.patch("sys.stdout", new=io.StringIO()),
            self.assertRaises(TimeoutError),
        ):
            install_linuxcnc.retry("it", action)
        self.assertEqual(action.call_count, install_linuxcnc.TRIES)

    def test_sim_text(self) -> None:
        """What goes into the target has Unix line endings."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.ini"
            path.write_bytes(b"[A]\r\nB = 1\r\n")
            self.assertEqual(install_linuxcnc.sim_text(path), b"[A]\nB = 1\n")

    def test_sim_files_exist(self) -> None:
        """Every file that goes into the target is in the package."""
        for path in install_linuxcnc.SIM_FILES:
            self.assertTrue(path.is_file(), path)

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

    def test_choose_route(self) -> None:
        """Each operating system gets its route; macOS has none."""
        choose = install_linuxcnc.choose_route
        self.assertEqual(choose("Linux"), "distrobox")
        self.assertEqual(choose("Windows"), "wsl")
        with self.assertRaises(SystemExit):
            choose("Darwin")
        with self.assertRaises(SystemExit):
            choose("FreeBSD")

    def test_halrun_ok(self) -> None:
        """Only a listed thread with no failure counts."""
        good = "Realtime Threads:\n  1000000  YES  probethread ( 0, 0 )\n"
        root = (
            "Refusing to run as root without fallback UID specified\n"
            "<stdin>:1: insmod for threads failed, returned -1\n"
            "Realtime Threads:\n"
        )
        self.assertTrue(install_linuxcnc.halrun_ok(good))
        self.assertFalse(install_linuxcnc.halrun_ok(root))
        self.assertFalse(install_linuxcnc.halrun_ok(""))

    def test_wsl_version(self) -> None:
        """The version column of `wsl -l -v`, also in UTF-16 debris."""
        listing = (
            "  NAME          STATE           VERSION\n"
            "* Debian        Running         2\n"
            "  Ubuntu-24.04  Stopped         1\n"
        )
        version = install_linuxcnc.wsl_version
        self.assertEqual(version(listing, "Debian"), 2)
        self.assertEqual(version(listing, "Ubuntu-24.04"), 1)
        self.assertEqual(version(listing, "Debian-13"), 0)
        self.assertEqual(version("\0".join(listing), "Debian"), 2)

    def test_ask_user_yes(self) -> None:
        """With `--yes`, the command is run, not asked for."""
        with (
            mock.patch("scraftlinuxcnc.install_linuxcnc.run") as run,
            mock.patch("sys.stdin", new=io.StringIO()),
            mock.patch("sys.stdout", new=io.StringIO()),
        ):
            install_linuxcnc.ask_user("Why.", ["true"], yes=True)
        run.assert_called_once_with(["true"])

    def test_target_command(self) -> None:
        """Commands are prefixed, as root or as the user."""
        options = install_linuxcnc.SCOptions("wsl", "lcnc", "Debian", False)
        wsl = install_linuxcnc.wsl_steps(options)[0]
        command = wsl.command(["id", "-u"], root=True)
        self.assertEqual(
            command[:5], ["wsl.exe", "-d", "Debian", "-u", "root"]
        )
        self.assertEqual(command[-2:], ["id", "-u"])
        self.assertEqual(wsl.command(["id"])[3:5], ["-u", "lcnc"])

    def test_steps(self) -> None:
        """Every route ends with the same seven steps, `halrun` last."""
        for route, setup in (("distrobox", 2), ("wsl", 1)):
            options = install_linuxcnc.SCOptions(route, "b", "Debian", True)
            _, all_steps = install_linuxcnc.steps(options)
            self.assertEqual(len(all_steps), setup + 7, route)
            self.assertIn("import linuxcnc", all_steps[-2].title)
            self.assertIn("halrun", all_steps[-1].title)

    def test_install_without_recommends(self) -> None:
        """Only what LinuxCNC needs is installed, asking nothing."""
        command = install_linuxcnc.apt_get(
            *install_linuxcnc.INSTALL, "/tmp/p.deb"
        )
        self.assertEqual(
            command[:2], ["env", "DEBIAN_FRONTEND=noninteractive"]
        )
        self.assertIn("--no-install-recommends", command)

    def test_trim_commands(self) -> None:
        """The package is rebuilt with only what the simulator needs."""
        commands = install_linuxcnc.trim_commands("/tmp/p.deb")
        self.assertEqual(commands[1][:3], ["dpkg-deb", "-R", "/tmp/p.deb"])
        edit = commands[2][2]
        self.assertIn("libepoxy0", edit)
        self.assertIn("libxinerama1", edit)
        self.assertIn("tk8.6", edit)
        self.assertNotIn("pyqt5", edit)
        self.assertNotIn("python3-tk", edit)
        self.assertNotIn("&", edit)
        self.assertEqual(edit.count("|"), 3)
        self.assertEqual(commands[-1][-1], install_linuxcnc.TRIMMED_PACKAGE)

    def test_send_file_shared(self) -> None:
        """A box sees the file where it is; nothing is sent."""
        options = install_linuxcnc.SCOptions("distrobox", "b", "Debian", True)
        target = install_linuxcnc.box_steps(options)[0]
        path = Path("/x/p.deb")
        with mock.patch("scraftlinuxcnc.install_linuxcnc.run") as run:
            inside = install_linuxcnc.send_file(target, path)
        self.assertEqual(inside, str(path))
        run.assert_not_called()

    def test_run_streams_with_time(self) -> None:
        """`run()` prints each line with the time, and its status."""
        out = io.StringIO()
        with mock.patch("sys.stdout", new=out):
            ok = install_linuxcnc.run(
                [sys.executable, "-c", "print('Setting up x')"]
            )
        self.assertTrue(ok)
        self.assertRegex(out.getvalue(), r"\[\d\d:\d\d:\d\d\] Setting up x")
        with mock.patch("sys.stdout", new=io.StringIO()):
            self.assertFalse(install_linuxcnc.run(["/no/such/program"]))


if __name__ == "__main__":
    unittest.main()
