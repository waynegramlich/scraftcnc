"""Which editor [Edit] opens a file in, with no Qt in it (#77, #124).

In order:

1. The environment variable `VISUAL`: a GUI editor, run as it is.
2. The environment variable `EDITOR`: usually a terminal editor
   (`vi`, `nano`, `emacs -nw`), so it is run in a terminal window
   (`TERMINALS`); on Windows, as it is.
3. Neither: the desktop's default for the file (Qt's
   `QDesktopServices`, in `window.py`), with a hint, once a session,
   naming the environment variables so they can be looked up.
"""

import shlex
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

# Terminal windows to run `EDITOR` in, first found first, each with
# what comes before the command.
TERMINALS: tuple[tuple[str, ...], ...] = (
    ("x-terminal-emulator", "-e"),
    ("konsole", "-e"),
    ("gnome-terminal", "--"),
    ("xterm", "-e"),
)

# The hint when neither `VISUAL` nor `EDITOR` is set.
HINT: str = (
    "Opened with the desktop's default editor.  To choose one, set the "
    "environment variable VISUAL (a GUI editor, e.g. VISUAL=kate) or "
    "EDITOR (a terminal editor, e.g. EDITOR=nano)."
)


# Function `editor_command()`:
def editor_command(
    path: Path,
    environment: Mapping[str, str],
    which: Callable[[str], str | None],
) -> tuple[list[str], str]:
    """Return the command that edits a file, or why there is none.

    Arguments:
    * `path` (`Path`): The file.
    * `environment` (`Mapping[str, str]`): The environment variables
      (`os.environ`).
    * `which` (`Callable[[str], str | None]`): Finds a program
      (`shutil.which`).

    Returns:
    * (`tuple[list[str], str]`): The command, and ""; or an empty
      command, and "" for the desktop's default, or a problem.
    """
    # `VISUAL`: a GUI editor, as it is.
    visual: str = environment.get("VISUAL", "").strip()
    if visual:
        return [*shlex.split(visual), str(path)], ""

    # `EDITOR`: in a terminal window (Windows opens its own console).
    editor: str = environment.get("EDITOR", "").strip()
    if not editor:
        return [], ""
    command: list[str] = [*shlex.split(editor), str(path)]
    if sys.platform == "win32":
        return command, ""
    terminal: tuple[str, ...]
    for terminal in TERMINALS:
        if which(terminal[0]):
            return [*terminal, *command], ""
    return [], (
        f"No terminal window found to run EDITOR ({editor}) in; set the "
        "environment variable VISUAL to a GUI editor instead."
    )
