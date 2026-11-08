"""Tests of `scraftcnc.home`."""

import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scraftcnc import home


class MakeDirectoryTest(unittest.TestCase):
    """Tests of `make_directory()`."""

    def test_creates_home_with_message(self) -> None:
        """A new home directory is announced once, and hidden on Windows."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary) / ".scraftcnc"
            inside: Path = top / "packages" / "x"
            with mock.patch.object(home, "HOME_DIRECTORY", top):
                # The first call creates it, with the message.
                errors: io.StringIO = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    self.assertEqual(home.make_directory(inside), inside)
                self.assertTrue(inside.is_dir())
                self.assertIn("Created ~/.scraftcnc/", errors.getvalue())

                # Hidden on Windows (GitHub Actions runs this there).
                if sys.platform == "win32":
                    attributes: int = os.stat(top).st_file_attributes
                    self.assertTrue(attributes & stat.FILE_ATTRIBUTE_HIDDEN)

                # The second call says nothing.
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    home.make_directory(top / "other")
                self.assertEqual(errors.getvalue(), "")

    def test_outside_home_is_quiet(self) -> None:
        """A directory outside the home directory gets no message."""
        with tempfile.TemporaryDirectory() as temporary:
            top: Path = Path(temporary) / ".scraftcnc"
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
