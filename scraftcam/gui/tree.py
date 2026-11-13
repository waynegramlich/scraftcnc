"""The GUI's tree: the shop's and the design's files, with no Qt in it.

One tree with two roots (`T.osiade~5.1.9` #121):

* The shop: its directory, `shop.toml` being the root itself.  Each
  directory below is a branch, and each `.toml` file one item (#19),
  shown by its `name` (else its file name) and "(file)"; S3 brings
  the real kinds (#119).
* The design: a Python file, with the `.py` files and packages in its
  directory and below; or a package directory, with what is in it.
  A file with a top level `main()` is "(design)", any other
  "(python)" (#120).  Files are parsed, never imported, so none of
  the user's code runs.  At most `DESIGN_LIMIT` items (#126).

A file that does not read cleanly stays in the tree as "(error)",
with the problem and its line (#125).  Directories come first, then
files, each alphabetical, ignoring case (#127).  Hidden directories
and `__pycache__` are skipped.
"""

import ast
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The most items the design tree shows (#126).
DESIGN_LIMIT: int = 100

# The kinds of items.
SHOP: str = "shop"
DIRECTORY: str = "directory"
FILE: str = "file"
DESIGN: str = "design"
PYTHON: str = "python"
PACKAGE: str = "package"
ERROR: str = "error"

# Directories never shown.
SKIPPED: tuple[str, ...] = ("__pycache__",)


# Class `Node`:
@dataclass(slots=True)
class Node:
    """One item of the tree.

    Attributes:
    * `name` (`str`): What the tree shows, before its kind.
    * `kind` (`str`): `SHOP`, `DIRECTORY`, `FILE`, `DESIGN`,
      `PYTHON`, `PACKAGE` or `ERROR`.
    * `path` (`Path`): Its file or directory.
    * `error` (`str`): Why it does not read cleanly, or "".
    * `children` (`list[Node]`): The items under it.

    Constructor:
    * `Node(name, kind, path, error)`
    """

    # Constructor arguments:
    name: str = field(init=True)
    kind: str = field(init=True)
    path: Path = field(init=True)
    error: str = field(init=True, default="")

    # Remaining attributes (alphabetized):
    children: list["Node"] = field(init=False, default_factory=list)

    def label(self) -> str:
        """Return what the tree shows (#73).

        Returns:
        * (`str`): "NAME (KIND)".
        """
        return f"{self.name} ({self.kind})"

    def count(self) -> int:
        """Return how many items this is, with all under it.

        Returns:
        * (`int`): 1 plus the count of each child.
        """
        return 1 + sum(child.count() for child in self.children)


# Function `toml_problem()`:
def toml_problem(path: Path) -> str:
    """Say why a TOML file does not read cleanly.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`str`): E.g. "syntax error: Invalid value (at line 2,
      column 8)", or "" when it reads cleanly.
    """
    try:
        with path.open("rb") as file:
            tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        return f"syntax error: {error}"
    except OSError as error:
        return f"can not be read: {error}"
    return ""


# Function `python_module()`:
def python_module(path: Path) -> tuple[ast.Module | None, str]:
    """Parse a Python file, without running it.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`tuple[ast.Module | None, str]`): Its tree and "", or None and
      e.g. "syntax error at line 3: invalid syntax".
    """
    try:
        source: str = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(path)), ""
    except SyntaxError as error:
        return None, f"syntax error at line {error.lineno}: {error.msg}"
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return None, f"can not be read: {error}"


# Function `has_main()`:
def has_main(module: ast.Module) -> bool:
    """Tell whether a module defines `main()` at its top level.

    Arguments:
    * `module` (`ast.Module`): The parsed module.

    Returns:
    * (`bool`): True when it does.
    """
    return any(
        isinstance(statement, ast.FunctionDef) and statement.name == "main"
        for statement in module.body
    )


# Function `docstring()`:
def docstring(path: Path) -> str:
    """Return a Python file's or package's top docstring (#74).

    Arguments:
    * `path` (`Path`): A `.py` file, or a package directory (its
      `__init__.py`).

    Returns:
    * (`str`): The docstring, "(no docstring)", or the problem.
    """
    if path.is_dir():
        path = path / "__init__.py"
    module: ast.Module | None
    problem: str
    module, problem = python_module(path)
    if module is None:
        return problem
    return ast.get_docstring(module) or "(no docstring)"


# Function `shown()`:
def shown(path: Path) -> bool:
    """Tell whether a directory entry belongs in the tree at all.

    Arguments:
    * `path` (`Path`): The entry.

    Returns:
    * (`bool`): False for hidden entries and `SKIPPED` directories.
    """
    return not path.name.startswith(".") and path.name not in SKIPPED


# Function `order()`:
def order(path: Path) -> tuple[bool, str]:
    """Return a directory entry's place: directories first (#127).

    Arguments:
    * `path` (`Path`): The entry.

    Returns:
    * (`tuple[bool, str]`): False for a directory, then its name in
      lower case.
    """
    return (not path.is_dir(), path.name.lower())


# Function `entries()`:
def entries(directory: Path) -> list[Path]:
    """List a directory: directories first, then files (#127).

    Arguments:
    * `directory` (`Path`): The directory.

    Returns:
    * (`list[Path]`): Its shown entries, each group alphabetical,
      ignoring case; empty if it can not be read.
    """
    try:
        found: list[Path] = [
            path for path in directory.iterdir() if shown(path)
        ]
    except OSError:
        return []
    return sorted(found, key=order)


# Function `toml_node()`:
def toml_node(path: Path) -> Node:
    """Make a shop file's item: its `name`, else its file name.

    Arguments:
    * `path` (`Path`): A `.toml` file.

    Returns:
    * (`Node`): A `FILE`, or an `ERROR` saying why.
    """
    problem: str = toml_problem(path)
    if problem:
        return Node(path.name, ERROR, path, problem)
    with path.open("rb") as file:
        name: object = tomllib.load(file).get("name", "")
    if isinstance(name, str) and name.strip():
        return Node(" ".join(name.split()), FILE, path)
    return Node(path.stem, FILE, path)


# Function `edit_path()`:
def edit_path(node: Node) -> Path | None:
    """Return the file [Edit] opens for an item, if any (#122).

    Python files, a package's `__init__.py`, and any file that does
    not read cleanly (it must be fixed by hand, #18).

    Arguments:
    * `node` (`Node`): The item.

    Returns:
    * (`Path | None`): The file, or None when there is none to edit.
    """
    if node.kind in (DESIGN, PYTHON) or (
        node.kind == ERROR and node.path.is_file()
    ):
        return node.path
    init: Path = node.path / "__init__.py"
    if node.kind == PACKAGE and init.is_file():
        return init
    return None


# Function `shop_tree()`:
def shop_tree(shop: Path) -> Node:
    """Read a shop's tree.

    Arguments:
    * `shop` (`Path`): Its `shop.toml`.

    Returns:
    * (`Node`): The root (the shop itself, from `shop.toml`), with its
      directories and `.toml` files under it.
    """
    root: Node = toml_node(shop)
    root.kind = ERROR if root.error else SHOP
    root.children = shop_children(shop.parent, skip=shop)
    return root


# Function `shop_children()`:
def shop_children(directory: Path, skip: Path | None = None) -> list[Node]:
    """Read the items in one of the shop's directories.

    Arguments:
    * `directory` (`Path`): The directory.
    * `skip` (`Path | None`): A file not to list (`shop.toml`).

    Returns:
    * (`list[Node]`): Its directories and `.toml` files.
    """
    children: list[Node] = []
    path: Path
    for path in entries(directory):
        if path.is_dir():
            branch: Node = Node(path.name, DIRECTORY, path)
            branch.children = shop_children(path)
            children.append(branch)
        elif path.suffix == ".toml" and path != skip:
            children.append(toml_node(path))
    return children


# Function `python_node()`:
def python_node(path: Path) -> Node:
    """Make a Python file's item: "(design)" when it has `main()`.

    Arguments:
    * `path` (`Path`): A `.py` file.

    Returns:
    * (`Node`): A `DESIGN`, a `PYTHON`, or an `ERROR` saying why.
    """
    module: ast.Module | None
    problem: str
    module, problem = python_module(path)
    if module is None:
        return Node(path.stem, ERROR, path, problem)
    return Node(path.stem, DESIGN if has_main(module) else PYTHON, path)


# Class `DesignReader`:
@dataclass(slots=True)
class DesignReader:
    """Reads a design's tree, stopping at `limit` items (#126).

    Attributes:
    * `limit` (`int`): The most items read.
    * `count` (`int`): How many have been read.
    * `clipped` (`bool`): True when some were left out.

    Constructor:
    * `DesignReader(limit)`
    """

    # Constructor arguments:
    limit: int = field(init=True)

    # Remaining attributes (alphabetized):
    clipped: bool = field(init=False, default=False)
    count: int = field(init=False, default=0)

    def room(self) -> bool:
        """Count one more item, if there is room for it.

        Returns:
        * (`bool`): True when it may be added.
        """
        if self.count >= self.limit:
            self.clipped = True
            return False
        self.count += 1
        return True

    def children(
        self, directory: Path, skip: Path | None = None
    ) -> list[Node]:
        """Read the Python files and packages in a directory.

        Arguments:
        * `directory` (`Path`): The directory.
        * `skip` (`Path | None`): A file not to list (the design).

        Returns:
        * (`list[Node]`): Its packages, directories holding Python,
          and `.py` files.
        """
        found: list[Node] = []
        path: Path
        for path in entries(directory):
            if path.is_dir():
                kind: str = (
                    PACKAGE if (path / "__init__.py").is_file() else DIRECTORY
                )
                if not self.room():
                    break
                branch: Node = Node(path.name, kind, path)
                branch.children = self.children(path)
                if branch.children or kind == PACKAGE:
                    found.append(branch)
                else:
                    self.count -= 1
            elif path.suffix == ".py" and path != skip:
                if not self.room():
                    break
                found.append(python_node(path))
        return found


# Function `design_tree()`:
def design_tree(design: Path, limit: int = DESIGN_LIMIT) -> tuple[Node, bool]:
    """Read a design's tree.

    Arguments:
    * `design` (`Path`): A Python file, or a package directory.
    * `limit` (`int`): The most items read (#126).

    Returns:
    * (`tuple[Node, bool]`): The root (the design itself), with the
      Python under it; and True when items were left out.
    """
    reader: DesignReader = DesignReader(limit)
    root: Node
    if design.is_dir():
        root = Node(design.name, PACKAGE, design)
        root.children = reader.children(design)
    else:
        root = python_node(design)
        root.children = reader.children(design.parent, skip=design)
    return root, reader.clipped
