"""Tests of `show_demo.py` that start nothing."""

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import show_demo


class TestLeftovers(unittest.TestCase):
    """What may be removed of a SolidCraft that has gone."""

    def setUp(self) -> None:
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)

    def test_recovery_files_of_one_only(self) -> None:
        """Another SolidCraft's recovery files are left alone."""
        for name in (
            "100-386091-10.json",
            "100-386091-10.sc",
            "100-3860-10.sc",
            "386091.sc",
        ):
            (self.directory / name).write_text("", encoding="utf-8")
        found = show_demo.recovery_files(self.directory, 386091)
        self.assertEqual(
            sorted(path.name for path in found),
            ["100-386091-10.json", "100-386091-10.sc"],
        )

    def test_no_recovery_directory(self) -> None:
        """No directory means no files."""
        self.assertEqual(
            show_demo.recovery_files(self.directory / "none", 1), []
        )

    def test_stale_pid_file(self) -> None:
        """A dead process's file is stale; a living one's is not."""
        pid_file = self.directory / "8080.pid"
        pid_file.write_text("999999999 1\n", encoding="utf-8")
        self.assertEqual(
            show_demo.stale_pid_files(self.directory, 8080), [pid_file]
        )
        pid_file.write_text(f"{os.getpid()} 1\n", encoding="utf-8")
        self.assertEqual(show_demo.stale_pid_files(self.directory, 8080), [])
        self.assertEqual(show_demo.stale_pid_files(self.directory, 1), [])


class TestChecks(unittest.TestCase):
    """What stops a show before anything starts."""

    def test_port_in_use(self) -> None:
        """A port in use is refused, by name."""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with (
                mock.patch.dict(os.environ, {"DISPLAY": ":0"}),
                mock.patch("shutil.which", return_value="/x"),
                mock.patch.object(
                    show_demo,
                    "SERVER_PROJECT",
                    Path(__file__).parent,
                ),
                self.assertRaisesRegex(
                    show_demo.SCShowFailed, "for SolidCraft"
                ),
            ):
                show_demo.check_ready({"SolidCraft": port})

    def test_no_display(self) -> None:
        """With no display, nothing can be shown."""
        with (
            mock.patch.dict(os.environ, clear=True),
            self.assertRaisesRegex(show_demo.SCShowFailed, "no display"),
        ):
            show_demo.check_ready({})

    def test_no_solidcraft(self) -> None:
        """A missing SolidCraft says where it looked."""
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch.object(show_demo, "SOLIDCRAFT_BESIDE", Path("/no/x")),
            self.assertRaisesRegex(show_demo.SCShowFailed, "No SolidCraft"),
        ):
            show_demo.find_solidcraft("")


if __name__ == "__main__":
    unittest.main()
