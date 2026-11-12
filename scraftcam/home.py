"""The `~/.scraftcam/` directory, where `scraftcam` keeps what it caches.

The package itself is treated as read only, so everything that
`scraftcam` writes for itself (models of tools, fetched packages, ...)
goes into a directory under `~/.scraftcam/`.  The first time that
directory is needed it is created (hidden, on Windows), with a message
on standard error; or, when the package's old name left a
`~/.scraftcnc/`, that one is moved to `~/.scraftcam/` instead.
"""

import subprocess
import sys
from pathlib import Path

# The directory that holds everything `scraftcam` caches.
HOME_DIRECTORY: Path = Path.home() / ".scraftcam"

# The same directory under the package's old name, `scraftcnc`.
OLD_HOME_DIRECTORY: Path = Path.home() / ".scraftcnc"


# Function `make_directory()`:
def make_directory(directory: Path) -> Path:
    """Create `directory`, and its parents, if they are not there yet.

    When `directory` is inside `HOME_DIRECTORY`, and `HOME_DIRECTORY`
    does not exist yet, a message on standard error says that it was
    created, or that `OLD_HOME_DIRECTORY` was moved there.

    Arguments:
    * `directory` (`Path`):
      The directory to create.

    Returns:
    * (`Path`): `directory`.

    Raises:
    * `OSError`: If the directory can not be created.
    """
    # Move `~/.scraftcnc/` from the package's old name, once.
    if (
        directory.is_relative_to(HOME_DIRECTORY)
        and not HOME_DIRECTORY.is_dir()
        and OLD_HOME_DIRECTORY.is_dir()
    ):
        OLD_HOME_DIRECTORY.rename(HOME_DIRECTORY)
        print(
            "Moved ~/.scraftcnc/ to ~/.scraftcam/ (the package's new name).",
            file=sys.stderr,
        )

    # Say so when `~/.scraftcam/` itself is new.
    if (
        directory.is_relative_to(HOME_DIRECTORY)
        and not HOME_DIRECTORY.is_dir()
    ):
        HOME_DIRECTORY.mkdir(parents=True, exist_ok=True)

        # Hide it on Windows, as a leading `.` hides it elsewhere.
        if sys.platform == "win32":
            subprocess.run(
                ["attrib", "+h", str(HOME_DIRECTORY)],
                capture_output=True,
                check=False,
            )
        print(
            "Created ~/.scraftcam/ directory to cache information.",
            file=sys.stderr,
        )

    # Then the directory asked for.
    directory.mkdir(parents=True, exist_ok=True)
    return directory
