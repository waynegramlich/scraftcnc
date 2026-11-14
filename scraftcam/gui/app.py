"""The GUI's model: everything its windows show, with no Qt in it.

Every window of the GUI draws from one `App`, and redraws when it
changes, so two windows showing the same thing always agree
(`T.osiade~5.1.9` #3).  Keeping Qt out of it lets the tests run with
no display.  It holds:

* The shop: the `shop.toml` named with `--shop`, or else the first one
  found in the current directory or one of its parents (#83), and the
  shop's name (#100).
* The design: a Python file, or a package directory, and its name.
* The machines running, which decide when [Stop All] shows (#2) and
  when a window may not close (#67).
* The messages, the latest one shown on the top line (#95).
* The tree of the shop's and the design's files (`tree.py`), read
  again by `reload_tree()` whenever they change.

With no shop, a new one can be made from a few answers (#97, #98,
#104): its name, its units, and the kinds of machines it has, which
`new_shop_text()` writes with the shop writer (`shop_writer.py`).
"""

import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..shop_writer import item_text
from ..shops import FORMAT_VERSION, SHOP_FILE
from .tree import DESIGN_LIMIT, Node, design_tree, shop_tree

# What the top line shows for a shop or a design that is missing.
NONE_NAME: str = "(none)"

# The units a shop may prefer, and how the GUI names them.
UNITS: tuple[str, ...] = ("in", "mm")
UNIT_LABELS: dict[str, str] = {"in": "Imperial (in)", "mm": "Metric (mm)"}

# The kinds of machines a new shop is asked about (#104, #118): each
# kind's key (one of `shops.SHOP_MACHINE_KINDS`), its label, and
# whether `scraftcam` can drive it yet.
# Computer controlled machines first; then manual ones, for the prep
# work before a CNC job, their keys starting with `MANUAL_PREFIX`.
MACHINE_KINDS: tuple[tuple[str, str, bool], ...] = (
    ("cnc_mill", "CNC mill", True),
    ("cnc_router", "CNC router", False),
    ("cnc_lathe", "CNC lathe", False),
    ("laser_cutter", "Laser cutter", False),
    ("3d_printer", "3D printer", False),
    ("manual_mill", "Manual mill", False),
    ("manual_lathe", "Manual lathe", False),
    ("manual_drill_press", "Manual drill press", False),
    ("manual_bandsaw", "Manual bandsaw", False),
)

MANUAL_PREFIX: str = "manual_"

# The directory a new shop is offered in, under the current one.
NEW_SHOP_DIRECTORY: str = "shop"

# The version control systems the GUI suggests (#99), and the
# directory each keeps at the top of a repository.
VERSION_CONTROLS: tuple[tuple[str, str], ...] = (
    ("git", ".git"),
    ("hg", ".hg"),
)


# Class `Message`:
@dataclass(frozen=True, slots=True)
class Message:
    """One message for the top line.

    Attributes:
    * `text` (`str`): What it says, one line.
    * `problem` (`bool`): True for a problem (shown in red).

    Constructor:
    * `Message(text, problem)`
    """

    # Constructor arguments:
    text: str = field(init=True)
    problem: bool = field(init=True)


# Function `find_shop()`:
def find_shop(start: Path) -> Path | None:
    """Find the shop for a directory, as `git` finds its repository.

    Arguments:
    * `start` (`Path`):
      The directory to look in first; then each of its parents.

    Returns:
    * (`Path | None`): The first `shop.toml` found, or None.
    """
    directory: Path
    for directory in (start.resolve(), *start.resolve().parents):
        candidate: Path = directory / SHOP_FILE
        if candidate.is_file():
            return candidate
    return None


# Function `shop_name()`:
def shop_name(shop: Path) -> str:
    """Return a shop's name: its `name`, or its directory's name.

    Arguments:
    * `shop` (`Path`): The shop's `shop.toml`.

    Returns:
    * (`str`): The name to show.

    Raises:
    * `OSError`: If the file can not be read.
    * `tomllib.TOMLDecodeError`: If it does not read as TOML.
    """
    with shop.open("rb") as file:
        table: dict[str, object] = tomllib.load(file)
    name: object = table.get("name", "")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return shop.resolve().parent.name


# Function `design_name()`:
def design_name(design: Path) -> str:
    """Return a design's name: its file's, less `.py`, or its package's.

    Arguments:
    * `design` (`Path`): A Python file, or a package directory.

    Returns:
    * (`str`): The name to show.
    """
    if design.is_dir():
        return design.resolve().name
    return design.stem


# Function `in_repository()`:
def in_repository(directory: Path) -> bool:
    """Tell whether a directory is inside a `git` or `hg` repository.

    Arguments:
    * `directory` (`Path`): The directory.

    Returns:
    * (`bool`): True when it, or a parent, holds `.git` or `.hg`.
    """
    top: Path
    for top in (directory.resolve(), *directory.resolve().parents):
        marker: str
        for _command, marker in VERSION_CONTROLS:
            if (top / marker).exists():
                return True
    return False


# Function `version_control_hint()`:
def version_control_hint(directory: Path) -> str:
    """Suggest version control for a shop, when it has none (#107).

    Arguments:
    * `directory` (`Path`): The shop's directory.

    Returns:
    * (`str`): One line suggesting `git` or `hg`, or "" when the shop
      is already in a repository.
    """
    # Already in a repository: nothing to say.
    if in_repository(directory):
        return ""

    # Not installed at all, or installed and not used yet.
    installed: list[str] = [
        command
        for command, _marker in VERSION_CONTROLS
        if shutil.which(command)
    ]
    if not installed:
        return (
            "No version control is installed; "
            "install git or hg to keep the shop's history."
        )
    return (
        f"The shop is not under version control; "
        f"e.g. `{installed[0]} init` in {directory}."
    )


# Function `new_shop_text()`:
def new_shop_text(name: str, units: str, machines: list[str]) -> str:
    """Write a new shop's `shop.toml`.

    Arguments:
    * `name` (`str`): The shop's name (not empty).
    * `units` (`str`): The units it prefers, one of `UNITS`.
    * `machines` (`list[str]`): The keys of its kinds of machines,
      from `MACHINE_KINDS`.

    Returns:
    * (`str`): The file's text.

    Raises:
    * `ValueError`: If an answer is not one of those allowed.
    """
    # Every answer must be one of those allowed.
    if not name.strip():
        raise ValueError("the shop needs a name")
    if units not in UNITS:
        raise ValueError(f"units must be one of {', '.join(UNITS)}")
    kinds: list[str] = [kind for kind, _label, _ready in MACHINE_KINDS]
    unknown: list[str] = [kind for kind in machines if kind not in kinds]
    if unknown:
        raise ValueError(f"unknown kinds of machines: {', '.join(unknown)}")

    # The shop file, as the GUI writes every shop file; the kinds in
    # their order.
    return item_text(
        {
            "name": " ".join(name.split()),
            "kind": "shop",
            "language": "English",
            "version": FORMAT_VERSION,
            "units": units,
            "machine_kinds": [kind for kind in kinds if kind in machines],
        }
    )


# Function `create_shop()`:
def create_shop(
    directory: Path, name: str, units: str, machines: list[str]
) -> Path:
    """Make a new shop: its directory and its `shop.toml`.

    Arguments:
    * `directory` (`Path`): The shop's directory (made if needed).
    * `name` (`str`): The shop's name.
    * `units` (`str`): The units it prefers, one of `UNITS`.
    * `machines` (`list[str]`): The keys of its kinds of machines.

    Returns:
    * (`Path`): The new `shop.toml`.

    Raises:
    * `ValueError`: If an answer is not allowed, or the directory
      already has a `shop.toml`.
    * `OSError`: If the directory or the file can not be made.
    """
    text: str = new_shop_text(name, units, machines)
    shop: Path = directory / SHOP_FILE
    if shop.exists():
        raise ValueError(f"{shop} already exists")
    directory.mkdir(parents=True, exist_ok=True)
    shop.write_text(text, encoding="utf-8")
    return shop.resolve()


# Class `App`:
# The model holds everything every window shows.
@dataclass(slots=True)
class App:  # pylint: disable=too-many-instance-attributes
    """Everything the GUI's windows show, shared by all of them.

    Each window calls `listen()` once, and redraws from the `App`
    whenever its function is called.

    Attributes:
    * `shop` (`Path | None`): The shop's `shop.toml`, if any.
    * `design` (`Path | None`): The design, if any.
    * `listeners` (`list[Callable[[], None]]`): The functions called
      on each change.
    * `messages` (`list[Message]`): Every message, oldest first.
    * `running` (`set[str]`): The names of the machines running.
    * `shop_title` (`str`): The shop's name, or `NONE_NAME`.
    * `editor_hinted` (`bool`): True once the hint about `VISUAL` and
      `EDITOR` has been given (once a session, #124).
    * `design_root` (`Node | None`): The design's tree, if any.
    * `shop_root` (`Node | None`): The shop's tree, if any.
    * `tree_version` (`int`): Counts the times the trees were read,
      so windows rebuild their trees only when it changes.

    Constructor:
    * `App(shop, design)`
    """

    # Constructor arguments:
    shop: Path | None = field(init=True)
    design: Path | None = field(init=True)

    # Remaining attributes (alphabetized):
    editor_hinted: bool = field(init=False, default=False)
    listeners: list[Callable[[], None]] = field(
        init=False, default_factory=list
    )
    messages: list[Message] = field(init=False, default_factory=list)
    running: set[str] = field(init=False, default_factory=set)
    shop_title: str = field(init=False, default=NONE_NAME)

    # The trees (alphabetized):
    design_root: Node | None = field(init=False, default=None)
    shop_root: Node | None = field(init=False, default=None)
    tree_version: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        """Read the shop's name and the trees; say what is missing."""
        # Absolute paths, so the tree's items are found by them.
        if self.design is not None:
            self.design = self.design.resolve()
        if self.shop is None:
            self.reload_tree()
            self.say(f"No {SHOP_FILE} found here or above.", problem=True)
        else:
            self.use_shop(self.shop)

    def use_shop(self, shop: Path, done: str = "") -> None:
        """Show a shop: its name, or the problem reading it.

        Arguments:
        * `shop` (`Path`): Its `shop.toml`.
        * `done` (`str`): What was done, to say before the version
          control hint (e.g. "Created ...").
        """
        self.shop = shop.resolve()
        self.reload_tree()
        try:
            self.shop_title = shop_name(shop)
        except (OSError, tomllib.TOMLDecodeError) as error:
            self.shop_title = NONE_NAME
            self.say(f"{shop}: {error}", problem=True)
            return
        text: str = " ".join(
            part for part in (done, version_control_hint(shop.parent)) if part
        )
        if text:
            self.say(text)
        else:
            self.changed()

    def reload_tree(self) -> None:
        """Read the shop's and the design's trees again."""
        # The shop's.
        self.shop_root = None if self.shop is None else shop_tree(self.shop)

        # The design's, or why there is none.
        self.design_root = None
        if self.design is not None and not self.design.exists():
            self.say(f"No design at {self.design}.", problem=True)
        elif self.design is not None:
            clipped: bool
            self.design_root, clipped = design_tree(self.design)
            if clipped:
                self.say(
                    f"The design's directory has more than {DESIGN_LIMIT} "
                    "Python files; only the first are shown.  Give the "
                    "design a directory of its own."
                )
        self.tree_version += 1
        self.changed()

    def new_shop(
        self, directory: Path, name: str, units: str, machines: list[str]
    ) -> Path:
        """Make a new shop, and show it.

        Arguments:
        * `directory` (`Path`): The shop's directory (made if needed).
        * `name` (`str`): The shop's name.
        * `units` (`str`): The units it prefers, one of `UNITS`.
        * `machines` (`list[str]`): The keys of its kinds of machines.

        Returns:
        * (`Path`): The new `shop.toml`.

        Raises:
        * `ValueError`: If an answer is not allowed, or the shop is
          there already.
        * `OSError`: If it can not be written.
        """
        shop: Path = create_shop(directory, name, units, machines)
        self.use_shop(shop, f"Created {shop}.")
        return shop

    def listen(self, function: Callable[[], None]) -> None:
        """Call `function` after every change from now on.

        Arguments:
        * `function` (`Callable[[], None]`): Typically a window's
          redraw.
        """
        self.listeners.append(function)

    def forget(self, function: Callable[[], None]) -> None:
        """Stop calling `function` (its window has closed).

        Arguments:
        * `function` (`Callable[[], None]`): A function given to
          `listen()`.
        """
        if function in self.listeners:
            self.listeners.remove(function)

    def changed(self) -> None:
        """Tell every listener that something changed."""
        function: Callable[[], None]
        for function in list(self.listeners):
            function()

    def say(self, text: str, *, problem: bool = False) -> None:
        """Add a message for the top line.

        Arguments:
        * `text` (`str`): The message; white space runs become one
          space, so it fits on one line.
        * `problem` (`bool`): True for a problem (shown in red).
        """
        self.messages.append(Message(" ".join(text.split()), problem))
        self.changed()

    def latest(self) -> Message:
        """Return the latest message.

        Returns:
        * (`Message`): The latest message, or an empty one.
        """
        return self.messages[-1] if self.messages else Message("", False)

    def design_title(self) -> str:
        """Return the design's name for the top line.

        Returns:
        * (`str`): The design's name, or `NONE_NAME`.
        """
        return NONE_NAME if self.design is None else design_name(self.design)

    def title(self) -> str:
        """Return the window's title (#109).

        Returns:
        * (`str`): "scraftcam: SHOP (DESIGN)".
        """
        return f"scraftcam: {self.shop_title} ({self.design_title()})"

    def start_machine(self, name: str) -> None:
        """Note that a machine is running.

        Arguments:
        * `name` (`str`): The machine's name, e.g. "shop mill".
        """
        self.running.add(name)
        self.changed()

    def stop_machine(self, name: str) -> None:
        """Note that a machine has stopped.

        Arguments:
        * `name` (`str`): The machine's name.
        """
        self.running.discard(name)
        self.changed()

    def stop_all(self) -> None:
        """Stop every machine ([Stop All])."""
        self.running.clear()
        self.say("Stopped all machines.")

    def any_running(self) -> bool:
        """Tell whether [Stop All] is active: any machine runs (#100).

        Returns:
        * (`bool`): True while at least one machine runs.
        """
        return bool(self.running)

    def close_refusal(self, controls: set[str]) -> str:
        """Say why a window may not close, if it may not (#67).

        Arguments:
        * `controls` (`set[str]`): The machines the window controls.

        Returns:
        * (`str`): E.g. "Stop the shop mill first", or "" when the
          window may close.
        """
        busy: list[str] = sorted(controls & self.running)
        if not busy:
            return ""
        return f"Stop the {' and the '.join(busy)} first"
