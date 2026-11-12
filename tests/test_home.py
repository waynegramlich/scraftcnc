"""Tests of `scraftcam.home`."""

import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scraftcam import home


class MakeDirectoryTest(unittest.TestCase):
    """Tests of `make_directory()`."""

    def setUp(self) -> None:
        """Keep every test away from the real `~/.scraftcnc/`."""
        patcher = mock.patch.object(
            home, "OLD_HOME_DIRECTORY", Path("/nonexistent/.scraftcnc")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_creates_home_with_message(self) -> None:
        """A new home directory is announced once, and hidden on Windows."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary) / ".scraftcam"
            inside: Path = top / "packages" / "x"
            with mock.patch.object(home, "HOME_DIRECTORY", top):
                # The first call creates it, with the message.
                errors: io.StringIO = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    self.assertEqual(home.make_directory(inside), inside)
                self.assertTrue(inside.is_dir())
                self.assertIn("Created ~/.scraftcam/", errors.getvalue())

                # Hidden on Windows (GitHub Actions runs this there).
                if sys.platform == "win32":
                    attributes: int = os.stat(top).st_file_attributes
                    self.assertTrue(attributes & stat.FILE_ATTRIBUTE_HIDDEN)

                # The second call says nothing.
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    home.make_directory(top / "other")
                self.assertEqual(errors.getvalue(), "")

    def test_moves_old_home(self) -> None:
        """A `~/.scraftcnc/` from the old name is moved, with a message."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary) / ".scraftcam"
            old: Path = Path(temporary) / ".scraftcnc"
            (old / "tool_cache").mkdir(parents=True)
            (old / "tool_cache" / "a.step").write_text("x")
            with (
                mock.patch.object(home, "HOME_DIRECTORY", top),
                mock.patch.object(home, "OLD_HOME_DIRECTORY", old),
            ):
                errors: io.StringIO = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    home.make_directory(top / "packages")
                self.assertFalse(old.exists())
                self.assertEqual(
                    (top / "tool_cache" / "a.step").read_text(), "x"
                )
                self.assertTrue((top / "packages").is_dir())
                self.assertIn("Moved ~/.scraftcnc/", errors.getvalue())
                self.assertNotIn("Created", errors.getvalue())

    def test_outside_home_is_quiet(self) -> None:
        """A directory outside the home directory gets no message."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary) / ".scraftcam"
            outside: Path = Path(temporary) / "elsewhere"
            with mock.patch.object(home, "HOME_DIRECTORY", top):
                errors: io.StringIO = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    home.make_directory(outside)
                self.assertTrue(outside.is_dir())
                self.assertFalse(top.exists())
                self.assertEqual(errors.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
