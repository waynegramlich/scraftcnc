"""A cache of SolidCraft models, as STEP files, to start up faster.

A model that takes many SolidCraft commands to build is built once and
exported to `~/.scraftcnc/tool_cache/MODEL_NAME__HASH.step`.  From then
on, and the first time as well, the file is what goes into the design.
It is built in a headless SolidCraft when `solidcraft-cli` is on the
`PATH`, which is several times faster, and otherwise in the design's own
session, where it is removed again after its export.

`HASH` is 16 hex digits worked out from a JSON tree of whatever affects
the model's shape (not its color), so anything that can describe itself
that way can be cached.  A model is built with its origin where it
should be placed from, and a matrix places it when it is inserted, so
where it goes is not part of the tree.

Using a file freshens it.  One not used for a week is deleted.  Nothing
in a file says how it was built, so a tree must change when the code
that builds its model does; `source_digest()` is a way to do that.

A design in a headless SolidCraft builds quickly anyway, and its session
reads and writes only where it is allowed to, so it has no cache
(`cache_for()`).

When anything goes wrong with the cache, a message is printed, the
cache is not used for the rest of the run, and `ModelCache.insert()`
returns `None`, so that the caller can build the model as if there were
no cache.  (SolidCraft may not be able to see the directory, if it runs
on another system, such as Windows with the caller in WSL.)
"""

import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .pybind.scraftpybind import (
    JSON,
    HeadlessTransport,
    PyBind,
    SolidCraftError,
)

if TYPE_CHECKING:
    from .assembly import AssemblyItem

# Where the files go.
CACHE_DIRECTORY: Path = Path.home() / ".scraftcnc" / "tool_cache"

# How long a file stays when it is not being used (seconds).
MAX_AGE: float = 7.0 * 24.0 * 60.0 * 60.0

# The program that makes files with no window, when it is on the `PATH`.
HEADLESS_CLI: str = "solidcraft-cli"

# How many hex digits of the hash go in a file name.
HASH_DIGITS: int = 16

# The code that builds an assembly's items from their `call` and
# `args`, name dictionaries included: a change to any of it changes
# every item's key, so old files no longer match.
_PACKAGE: Path = Path(__file__).resolve().parent
ITEM_SOURCES: tuple[Path, ...] = (
    _PACKAGE / "assembly.py",
    _PACKAGE / "geometry.py",
    _PACKAGE / "setups.py",
    _PACKAGE / "tooling" / "mount.py",
    _PACKAGE / "tooling" / "registry.py",
    _PACKAGE / "tooling" / "tools.py",
)

# A placement, for `file.insert_step`: rows of rotation and translation
# (millimeters).
Matrix = list[list[float]]


# Function `shape_hash()`:
def shape_hash(shape: JSON) -> str:
    """Return the hash of a tree, whatever order its keys are in.

    Arguments:
    * `shape` (`JSON`): The tree, of what affects a model's shape.

    Returns:
    * (`str`): `HASH_DIGITS` hex digits.
    """
    text: str = json.dumps(shape, sort_keys=True, separators=(",", ":"))
    digest: str = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:HASH_DIGITS]


# Function `source_digest()`:
def source_digest(paths: Sequence[Path]) -> str:
    """Return a digest of source files, for a tree to depend on them.

    Arguments:
    * `paths` (`Sequence[Path]`): The files that build the model.

    Returns:
    * (`str`): The digest, which changes when any of the files does.
    """
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


# Function `item_shape()`:
def item_shape(item: "AssemblyItem") -> JSON:
    """Return the tree an assembly item's models are hashed from.

    It is the item's `call` and `args`, as the setup comments write
    them, and the digest of `ITEM_SOURCES`, so where the item goes, its
    color and its note are no part of it.

    Arguments:
    * `item` (`AssemblyItem`): The item.

    Returns:
    * (`JSON`): The tree.
    """
    return {
        "args": cast(JSON, item.args),
        "call": item.call,
        "code": source_digest(ITEM_SOURCES),
    }


# Function `item_key()`:
def item_key(item: "AssemblyItem") -> str:
    """Return the hash an assembly item's models are cached under.

    Arguments:
    * `item` (`AssemblyItem`): The item.

    Returns:
    * (`str`): `HASH_DIGITS` hex digits, from `item_shape()`.
    """
    return shape_hash(item_shape(item))


# Function `keyed_by_item()`:
def keyed_by_item(model: "Cacheable", item: "AssemblyItem") -> "Cacheable":
    """Return a model of an item, cached by the item's key.

    The model's own tree is replaced by `item_shape()`.  A model made
    in sections (a vise's fixed and movable parts) keeps them apart by
    their names, which start their file names.

    Arguments:
    * `model` (`Cacheable`): A model built from `resolve(item)`.
    * `item` (`AssemblyItem`): The item.

    Returns:
    * (`Cacheable`): The model, with the item's tree.
    """
    return replace(model, shape=item_shape(item))


# Function `safe_name()`:
def safe_name(name: str) -> str:
    """Return a model's name as it can appear in a file name.

    Arguments:
    * `name` (`str`): The name (such as `1/4 in end mill`).

    Returns:
    * (`str`): The name with only letters, digits, `.`, `-` and `_`.
    """
    return re.sub(r"[^A-Za-z0-9.-]+", "_", name).strip("_")


# Function `no_color()`:
def no_color(_body: str) -> str:
    """Return no color for a body, for models colored by their callers.

    Arguments:
    * `_body` (`str`): The body's name.

    Returns:
    * (`str`): An empty string.
    """
    return ""


# Class `Cacheable`:
@dataclass(frozen=True, slots=True)
class Cacheable:
    """A model that can be cached.

    Attributes:
    * `name` (`str`): What it is; it starts the file's name.
    * `shape` (`JSON`): What affects its shape, for the hash.
    * `build` (`Callable[[PyBind], list[str]]`):
      Builds it in a SolidCraft session, around its origin, and returns
      the names of its bodies.
    * `offset` (`tuple[float, float, float]`):
      Where its origin goes, from where its owner's origin is (mm).
    * `color_of` (`Callable[[str], str]`):
      A body's color, from its name, or `""`.  A STEP file's colors do
      not come back, and a color is no part of the hash, so it is given
      each time the model is inserted.

    Constructor:
    * `Cacheable(name, shape, build, offset, color_of)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    shape: JSON = field(init=True)
    build: Callable[[PyBind], list[str]] = field(init=True)
    offset: tuple[float, float, float] = field(
        init=True, default=(0.0, 0.0, 0.0)
    )
    color_of: Callable[[str], str] = field(init=True, default=no_color)


# Function `export_model()`:
def export_model(
    solidcraft: PyBind, model: Cacheable, path: Path
) -> list[str]:
    """Build a model and export it to its file.

    The file appears only when it is whole, so that a failure, or
    another program using the cache, never sees part of one.

    Arguments:
    * `solidcraft` (`PyBind`): The session to build it in.
    * `model` (`Cacheable`): The model.
    * `path` (`Path`): Its file.

    Returns:
    * (`list[str]`): The names of the bodies built, still in the session.

    Raises:
    * `OSError`: If the file can not be written.
    * `SolidCraftError`: If SolidCraft fails.
    """
    bodies: list[str] = model.build(solidcraft)
    partial: Path = path.with_name(f"{path.stem}.{os.getpid()}.step")
    try:
        solidcraft.file.export(
            path=str(partial), format="step", bodies=cast(JSON, bodies)
        )
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return bodies


# Function `assign_colors()`:
def assign_colors(
    solidcraft: PyBind, model: Cacheable, bodies: list[str]
) -> None:
    """Give an inserted model's bodies their colors, one command a color.

    Arguments:
    * `solidcraft` (`PyBind`): The SolidCraft session.
    * `model` (`Cacheable`): The model.
    * `bodies` (`list[str]`): The names of its bodies.
    """
    by_color: dict[str, list[str]] = {}
    for body in bodies:
        by_color.setdefault(model.color_of(body), []).append(body)
    for color, colored in by_color.items():
        if color:
            solidcraft.appearance.assign(
                bodies=cast(JSON, colored), color=color
            )


# Class `InsertedModel`:
@dataclass(frozen=True, slots=True)
class InsertedModel:
    """A model in a design, in a component of its own, which is grounded.

    Attributes:
    * `bodies` (`list[str]`): The names of its bodies.
    * `component` (`int`): Its component's id.
    * `occurrence` (`int`): The id of its component's occurrence.

    Constructor:
    * `InsertedModel(bodies, component, occurrence)`
    """

    # Constructor arguments:
    bodies: list[str] = field(init=True)
    component: int = field(init=True)
    occurrence: int = field(init=True)


# Class `ModelCache`:
@dataclass(slots=True)
class ModelCache:
    """A directory of models as STEP files.

    Attributes:
    * `directory` (`Path`): Where the files are.
    * `broken` (`bool`): True once a failure has stopped it being used.
    * `swept` (`bool`): True once the old files have been deleted.

    Constructor:
    * `ModelCache(directory)`
    """

    # Constructor arguments:
    directory: Path = field(init=True, default=CACHE_DIRECTORY)

    # Attributes filled in later (alphabetized):
    broken: bool = field(init=False, default=False)
    swept: bool = field(init=False, default=False)

    # Method `ModelCache.path()`:
    def path(self, model: Cacheable) -> Path:
        """Return a model's file, which may not exist yet.

        Arguments:
        * `model` (`Cacheable`): The model.

        Returns:
        * (`Path`): `MODEL_NAME__HASH.step`, in the directory.
        """
        name: str = f"{safe_name(model.name)}__{shape_hash(model.shape)}.step"
        return self.directory / name

    # Method `ModelCache.sweep()`:
    def sweep(self) -> None:
        """Delete the files that have not been used for `MAX_AGE`, once.

        Raises:
        * `OSError`: If the directory can not be read or written.
        """
        if self.swept:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        oldest: float = time.time() - MAX_AGE
        for path in self.directory.glob("*.step"):
            if path.stat().st_mtime < oldest:
                path.unlink(missing_ok=True)
        self.swept = True

    # Method `ModelCache.create()`:
    def create(
        self,
        solidcraft: PyBind,
        model: Cacheable,
        path: Path,
        before_building: Callable[[], None],
    ) -> None:
        """Make a model's file, with no window if that can be done.

        Arguments:
        * `solidcraft` (`PyBind`): The session the model is wanted in.
        * `model` (`Cacheable`): The model.
        * `path` (`Path`): Its file.
        * `before_building` (`Callable[[], None]`):
          Called before it is built in `solidcraft`.

        Raises:
        * `OSError`: If the file can not be written.
        * `SolidCraftError`: If SolidCraft fails.
        """
        if self.create_headless(model, path):
            return
        before_building()
        bodies: list[str] = export_model(solidcraft, model, path)
        solidcraft.solid.remove(bodies=cast(JSON, bodies))

    # Method `ModelCache.create_headless()`:
    def create_headless(self, model: Cacheable, path: Path) -> bool:
        """Make a model's file in a headless session of its own.

        That is several times faster than in a window, starts in
        millimeters, and leaves nothing in the design.  A session starts
        in a few hundredths of a second, so none is kept.

        Arguments:
        * `model` (`Cacheable`): The model.
        * `path` (`Path`): Its file.

        Returns:
        * (`bool`):
          True if the file was made.  False if `HEADLESS_CLI` is not on
          the `PATH` (quietly, as that is expected), or if it failed
          (with a one-line warning on `stderr`), so that the design's
          own session builds it.
        """
        program: str | None = shutil.which(HEADLESS_CLI)
        if program is None:
            return False
        try:
            with HeadlessTransport(
                program, (str(self.directory),)
            ) as transport:
                export_model(PyBind(transport), model, path)
        except (OSError, SolidCraftError) as error:
            # Warn: the CLI is there, so building here is not expected.
            print(
                f"model_cache: headless build of {model.name} failed "
                f"({error}); building in this session",
                file=sys.stderr,
            )
            return False
        return True

    # Method `ModelCache.insert()`:
    def insert(
        self,
        solidcraft: PyBind,
        model: Cacheable,
        matrix: Matrix | None = None,
        before_building: Callable[[], None] = lambda: None,
    ) -> InsertedModel | None:
        """Put a model in the design, from its file.

        The file is made first if it does not exist, and freshened if
        it does.

        Arguments:
        * `solidcraft` (`PyBind`): The SolidCraft session.
        * `model` (`Cacheable`): The model.
        * `matrix` (`Matrix | None`):
          Where it goes, or `None` to leave it around the origin.
        * `before_building` (`Callable[[], None]`):
          Called before it is built in `solidcraft`, if it must be.

        Returns:
        * (`InsertedModel | None`):
          What was inserted, or `None` if the cache could not be used,
          so that the caller should build the model itself.
        """
        if self.broken:
            return None
        path: Path = self.path(model)
        try:
            self.sweep()
            if path.exists():
                os.utime(path)
            else:
                self.create(solidcraft, model, path, before_building)
            made: JSON = solidcraft.file.insert_step(
                path=str(path),
                name=model.name,
                matrix=cast(JSON, matrix),
            )
        except (OSError, SolidCraftError) as error:
            self.give_up(path, error)
            return None
        assert isinstance(made, dict)
        bodies: JSON = made["created_bodies"]
        component: JSON = made["component"]
        occurrence: JSON = made["occurrence"]
        assert isinstance(bodies, list)
        assert isinstance(component, int) and isinstance(occurrence, int)
        names: list[str] = [str(body) for body in bodies]
        assign_colors(solidcraft, model, names)
        return InsertedModel(names, component, occurrence)

    # Method `ModelCache.give_up()`:
    def give_up(self, path: Path, error: Exception) -> None:
        """Stop using the cache, and delete a file that may be bad.

        Arguments:
        * `path` (`Path`): The file being used.
        * `error` (`Exception`): What went wrong.
        """
        print(
            f"Not using the model cache, {self.directory}: {error}",
            file=sys.stderr,
        )
        self.broken = True
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


# Function `cache_for()`:
def cache_for(target: str) -> ModelCache | None:
    """Return the cache for a session, if it should have one.

    Arguments:
    * `target` (`str`): What `connect()` is given.

    Returns:
    * (`ModelCache | None`): The cache, or `None` for `headless`.
    """
    return None if target == "headless" else ModelCache()


# Function `placement_matrix()`:
def placement_matrix(
    turns: int,
    location: tuple[float, float, float],
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Matrix:
    """Return the matrix for a model turned and moved.

    Arguments:
    * `turns` (`int`): Quarter turns counterclockwise about Z
      (right hand rule: +X to +Y).
    * `location` (`tuple[float, float, float]`):
      Where its owner's origin goes (millimeters).
    * `offset` (`tuple[float, float, float]`):
      Where its origin is from its owner's, before the turn (mm).

    Returns:
    * (`Matrix`): The matrix, with exact quarter turns.
    """
    xx, xy = ((1.0, 0.0), (0.0, -1.0), (-1.0, 0.0), (0.0, 1.0))[turns % 4]
    return [
        [xx, xy, 0.0, location[0] + xx * offset[0] + xy * offset[1]],
        [-xy, xx, 0.0, location[1] - xy * offset[0] + xx * offset[1]],
        [0.0, 0.0, 1.0, location[2] + offset[2]],
    ]
