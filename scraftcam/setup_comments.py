"""Setup comments: an assembly written into a `.nc` file, and read back.

A setup (`assembly.Assembly`) is written as whole-line RS-274
comments, `(SCC: ...)`, each holding one line of TOML.  The first one
is `version = "..."` (`scraftcam.__version__`), then the header: the
`shop` and the `machine` in it that the program is for (by their
names; either may be missing, as in files written before them), then
one `[[item]]` table per item, in stacking order.  A `( ... )`
comment can not hold a parenthesis, so `(` and `)` in TOML strings
are written as the escapes `\\u0028` and `\\u0029`.  `write()` makes
the lines, and `read()` (or `read_file()`) gets the assembly back
from a whole program, skipping its other lines.
"""

import math
import re
import tomllib
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import __version__
from .assembly import Assembly

# The marker that starts each setup comment.
MARKER: str = "SCC:"

# The longest line written, where it can be helped (PEP 8).
WIDTH: int = 79

# A whole-line setup comment; the text inside can not hold a `(` or `)`.
_LINE: re.Pattern[str] = re.compile(r"^\s*\(SCC:([^()]*)\)\s*$")

# The start of a setup comment, whole or not.
_START: re.Pattern[str] = re.compile(r"^\s*\(SCC:")

# A key that TOML takes without quotes.
_BARE_KEY: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")

# Where `tomllib` says a problem is.
_AT_LINE: re.Pattern[str] = re.compile(r"at line (\d+)")


# Class `SetupVersionWarning`:
class SetupVersionWarning(UserWarning):
    """Warned when a `.nc` file was written by a newer `scraftcam`.

    What can be read is still read; the rest is skipped.
    """


# Function `write()`:
def write(assembly: Assembly) -> list[str]:
    """Return an assembly as `.nc` setup comment lines.

    Arguments:
    * `assembly` (`Assembly`): The setup.

    Returns:
    * (`list[str]`): The `(SCC: ...)` lines, without line ends.
    """
    toml: list[str] = [f"version = {_value(__version__)}"]
    whole: dict[str, Any] = assembly.to_dict()
    key: str
    for key in ("shop", "machine"):
        if key in whole:
            toml.extend(_pair(key, whole[key]))
    table: dict[str, Any]
    for table in whole["item"]:
        toml.append("[[item]]")
        toml.extend(_table(table, "item"))
    return [f"({MARKER} {line})" for line in toml]


# Function `read()`:
def read(lines: Iterable[str]) -> Assembly | None:
    """Return the assembly in a program's setup comments.

    Only whole-line `(SCC: ...)` comments are read; every other line
    is skipped.  A program written by a newer `scraftcam` warns with
    `SetupVersionWarning` and is read as far as it can be.

    Arguments:
    * `lines` (`Iterable[str]`): The program's lines.

    Returns:
    * (`Assembly | None`):
      The assembly, or `None` when there are no setup comments.

    Raises:
    * `ValueError`: If the setup comments are wrong (the message says
      which program line).
    """
    # Collect the TOML, remembering where each line came from.
    toml: list[str] = []
    origins: list[int] = []
    number: int
    line: str
    for number, line in enumerate(lines, start=1):
        match: re.Match[str] | None = _LINE.match(line)
        if match is None:
            if _START.match(line):
                raise ValueError(
                    f"line {number}: setup comment {line.strip()!r} "
                    "is not one whole-line comment"
                )
            continue
        text: str = match.group(1)
        toml.append(text.removeprefix(" "))
        origins.append(number)
    if not toml:
        return None

    # Parse it, giving a problem's place as a program line.
    try:
        table: dict[str, Any] = tomllib.loads("\n".join(toml))
    except tomllib.TOMLDecodeError as error:
        at: re.Match[str] | None = _AT_LINE.search(str(error))
        where: str = "setup comments"
        if at is not None and 1 <= int(at.group(1)) <= len(origins):
            where = f"line {origins[int(at.group(1)) - 1]}"
        elif "end of document" in str(error):
            where = f"line {origins[-1]}"
        raise ValueError(f"{where}: {error}") from error

    # Check the version; a newer one is read as far as it goes.
    if "version" not in table:
        raise ValueError(f"line {origins[0]}: setup comments have no version")
    version: Any = table.pop("version")
    newer: bool = _newer(version, __version__)
    if newer:
        warnings.warn(
            f"setup comments are version {version}, newer than "
            f"scraftcam {__version__}; reading what can be read",
            SetupVersionWarning,
            stacklevel=2,
        )
    unknown: list[str] = sorted(set(table) - {"item", "shop", "machine"})
    if unknown and not newer:
        raise ValueError(f"setup comments: unknown keys {unknown}")
    return Assembly.from_dict(
        {
            "item": table.get("item", []),
            "shop": table.get("shop", ""),
            "machine": table.get("machine", ""),
        }
    )


# Function `read_file()`:
def read_file(path: str | Path) -> Assembly | None:
    """Return the assembly in a `.nc` file's setup comments.

    Arguments:
    * `path` (`str | Path`): The `.nc` file.

    Returns:
    * (`Assembly | None`):
      The assembly, or `None` when there are no setup comments.

    Raises:
    * `OSError`: If the file can not be read.
    * `ValueError`: If the setup comments are wrong (the message
      names the file and line).
    """
    text: str = Path(path).read_text(encoding="utf-8")
    try:
        return read(text.splitlines())
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


# Function `_newer()`:
def _newer(version: object, current: str) -> bool:
    """Return whether a version is newer than the current one.

    Arguments:
    * `version` (`object`): The version read, such as `"0.2.0"`.
    * `current` (`str`): This code's version.

    Returns:
    * (`bool`): Whether `version` is newer.

    Raises:
    * `ValueError`: If `version` is not dotted numbers.
    """
    if not isinstance(version, str) or not re.fullmatch(
        r"\d+(\.\d+)*", version
    ):
        raise ValueError(f"setup comments: version {version!r} is wrong")
    read_parts: tuple[int, ...] = tuple(int(n) for n in version.split("."))
    code_parts: tuple[int, ...] = tuple(int(n) for n in current.split("."))
    return read_parts > code_parts


# Function `_table()`:
def _table(table: dict[str, Any], path: str) -> list[str]:
    """Return the TOML lines of a table's body, sub-tables last.

    Arguments:
    * `table` (`dict[str, Any]`): The table.
    * `path` (`str`): Its dotted name, for sub-table headers.

    Returns:
    * (`list[str]`): The lines.
    """
    lines: list[str] = []
    key: str
    value: Any
    for key, value in table.items():
        if not isinstance(value, dict):
            lines.extend(_pair(_key(key), value))
    for key, value in table.items():
        if isinstance(value, dict):
            name: str = f"{path}.{_key(key)}"
            lines.append(f"[{name}]")
            lines.extend(_table(value, name))
    return lines


# Function `_pair()`:
def _pair(key: str, value: Any) -> list[str]:
    """Return `key = value`, a list wrapped one element a line if long.

    Arguments:
    * `key` (`str`): The key, as TOML.
    * `value` (`Any`): The value.

    Returns:
    * (`list[str]`): The lines.
    """
    room: int = WIDTH - len(f"({MARKER} )")
    lines: list[str] = _wrapped(value, f"{key} = ", "", room)
    return lines


# Function `_wrapped()`:
def _wrapped(value: Any, head: str, tail: str, room: int) -> list[str]:
    """Return a value as lines, each list too long one element a line.

    Arguments:
    * `value` (`Any`): The value.
    * `head` (`str`): What goes before it (the key, or indentation).
    * `tail` (`str`): What goes after it (`,` in a list).
    * `room` (`int`): The longest a line may be.

    Returns:
    * (`list[str]`): The lines.
    """
    line: str = f"{head}{_value(value)}{tail}"
    if len(line) <= room or not isinstance(value, (list, tuple)):
        return [line]
    indent: str = " " * (len(head) - len(head.lstrip()) + 2)
    lines: list[str] = [f"{head}["]
    element: Any
    for element in value:
        lines.extend(_wrapped(element, indent, ",", room))
    lines.append(f"{indent[:-2]}]{tail}")
    return lines


# Function `_key()`:
def _key(key: str) -> str:
    """Return a key as TOML: bare, or quoted when it must be.

    Arguments:
    * `key` (`str`): The key.

    Returns:
    * (`str`): The key, as TOML.
    """
    return key if _BARE_KEY.match(key) else _string(key)


# Function `_value()`:
# One return per TOML type reads best:
def _value(value: Any) -> str:  # pylint: disable=too-many-return-statements
    """Return a value as inline TOML.

    Arguments:
    * `value` (`Any`): A string, number, bool, list or table.

    Returns:
    * (`str`): The value, as TOML.

    Raises:
    * `TypeError`: If TOML has no form for it (such as `None`).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return repr(value)  # `inf` and `-inf` are TOML as they are.
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(element) for element in value) + "]"
    if isinstance(value, dict):
        pairs: list[str] = [
            f"{_key(str(key))} = {_value(element)}"
            for key, element in value.items()
        ]
        return "{" + ", ".join(pairs) + "}"
    raise TypeError(f"{value!r} has no TOML form")


# Function `_string()`:
def _string(text: str) -> str:
    """Return a TOML basic string, safe in a `( ... )` comment.

    Parentheses, quotes, backslashes, control characters and anything
    outside printable ASCII are escaped.

    Arguments:
    * `text` (`str`): The string.

    Returns:
    * (`str`): The quoted string.
    """
    out: list[str] = []
    character: str
    for character in text:
        if character in '"\\':
            out.append("\\" + character)
        elif " " <= character <= "~" and character not in "()":
            out.append(character)
        elif ord(character) <= 0xFFFF:
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(f"\\U{ord(character):08x}")
    return '"' + "".join(out) + '"'
