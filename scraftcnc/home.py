"""The `~/.scraftcnc/` directory, where `scraftcnc` keeps what it caches.

The package itself is treated as read only, so everything that
`scraftcnc` writes for itself (models of tools, fetched packages, ...)
goes into a directory under `~/.scraftcnc/`.  The first time that
directory is needed it is created (hidden, on Windows), with a message
on standard error.
"""

import subprocess
import sys
from pathlib import Path

# The directory that holds everything `scraftcnc` caches.
HOME_DIRECTORY: Path = Path.home() / ".scraftcnc"


# Function `make_directory()`:
def make_directory(directory: Path) -> Path:
    """Create `directory`, and its parents, if they are not there yet.

    When `directory` is inside `HOME_DIRECTORY`, and `HOME_DIRECTORY`
    does not exist yet, a message on standard error says that it was
    created.

    Arguments:
    * `directory` (`Path`):
      The directory to create.

    Returns:
    * (`Path`): `directory`.

    Raises:
    * `OSError`: If the directory can not be created.
    """
    # Say so when `~/.scraftcnc/` itself is new.
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
            "Created ~/.scraftcnc/ directory to cache information.",
            file=sys.stderr,
        )

    # Then the directory asked for.
    directory.mkdir(parents=True, exist_ok=True)
    return directory
