#!/usr/bin/env python3
"""Shop descriptions: their schema, their reader, and `Shops.md`.

A shop (its machines, and later its tools, tooling and materials) is
described in Nested TOML files: TOML files that name each other with
`"@FILE_NAME"` strings.  This module holds the schema of every `kind`
of file (`KINDS`), reads a description into one JSON style data
structure (`read()`), checking it against the schema, and writes the
`Shops.md` document from the schema (`markdown()`), so the document
and the reader can not disagree.

Every problem is reported as `FILE:LINE: KEY: message` (the form that
compilers use, so editors can jump to it), and all of them are
reported at once.  `tomllib` gives the line of a syntax error; for the
rest, `_Scanner` finds the line of every key, since no TOML library
keeps line numbers once a file is parsed.

```
./shops.py check examples/shop/home_shop.toml
./shops.py json examples/shop/home_shop.toml
./shops.py markdown > Shops.md
```
"""

# The schema (`KINDS`) is long, but reads best in one place.
# pylint: disable=too-many-lines

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from scmachine import ANGLE, FEED, FRACTION, LENGTH, MEASUREMENT, SPEED

# The format version that this module reads and describes.
FORMAT_VERSION: str = "0.0.1"

# Where a value is in a file: its keys, and its indices in lists.
KeyPath: TypeAlias = tuple[str | int, ...]

# Units that `scmachine` does not have yet, in inches per second
# squared and degrees per minute.
ACCELERATION: dict[str, float] = {"in/s^2": 1.0, "mm/s^2": 1.0 / 25.4}
ROTARY_FEED: dict[str, float] = {"deg/min": 1.0, "deg/s": 60.0}

# The kinds of measurement, as `SCField.form` names them.
UNITS: dict[str, dict[str, float]] = {
    "length": LENGTH,
    "feed": FEED,
    "acceleration": ACCELERATION,
    "speed": SPEED,
    "angle": ANGLE,
    "rotary_feed": ROTARY_FEED,
    "fraction": FRACTION,
}

# The forms of value that are not measurements.
FORMS: tuple[str, ...] = (
    "string",
    "integer",
    "boolean",
    "choice",
    "version",
    "table",
    "list",
    "tool_table",
)

# The widest line in `Shops.md`.
MARKDOWN_WIDTH: int = 79

# A bare TOML key, and a version.
BARE_KEY: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]+")
VERSION: re.Pattern[str] = re.compile(r"(\d+)\.(\d+)\.(\d+)")


# Class `SCField`:
@dataclass(frozen=True, slots=True)
class SCField:
    """One key of a table, and what its value must be.

    Attributes:
    * `key` (`str`): The key (`snake_case`).
    * `form` (`str`):
      What its value is: a kind of measurement (a key of `UNITS`), or
      one of `FORMS`: `"table"` and `"list"` (of tables) take the kind
      named by `of`; `"choice"` is a string from `choices`;
      `"tool_table"` maps T numbers to tool names.
    * `meaning` (`str`): What it is, in Markdown.
    * `required` (`bool`): True if it must be there.
    * `of` (`str`): The kind of a `"table"` or `"list"`.
    * `choices` (`tuple[str, ...]`): The strings a `"choice"` takes.

    Constructor:
    * `SCField(key, form, meaning, required, of, choices)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    form: str = field(init=True)
    meaning: str = field(init=True)
    required: bool = field(init=True, default=False)
    of: str = field(init=True, default="")
    choices: tuple[str, ...] = field(init=True, default=())

    # Method `SCField.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the form is known.

        Raises:
        * `ValueError`: If `form`, `of` or `choices` do not fit.
        """
        if self.form not in UNITS and self.form not in FORMS:
            raise ValueError(f"{self.key}: unknown form {self.form!r}")
        if (self.form in ("table", "list")) != bool(self.of):
            raise ValueError(f"{self.key}: `of` is only for tables")
        if (self.form == "choice") != bool(self.choices):
            raise ValueError(f"{self.key}: `choices` is only for choices")

    # Method `SCField.shown()`:
    def shown(self) -> str:
        """Return what the value is, in Markdown, for `Shops.md`.

        Returns:
        * (`str`): Such as `length`, or ``list of `machine` ``.
        """
        shown: str = self.form.replace("_", " ")
        if self.form == "table":
            shown = f"`{self.of}`"
        elif self.form == "list":
            shown = f"list of `{self.of}`"
        elif self.form == "choice":
            shown = "one of " + ", ".join(f"`{c}`" for c in self.choices)
        elif self.form == "tool_table":
            shown = "T number to tool name"
        return shown


# Class `SCKind`:
@dataclass(frozen=True, slots=True)
class SCKind:
    """One kind of table, which may also be a file of its own.

    Attributes:
    * `kind` (`str`): Its name, the value of the `kind` key.
    * `summary` (`str`): What it is, in Markdown.
    * `fields` (`tuple[SCField, ...]`): Its keys (but not the header).
    * `named` (`bool`):
      True if it must have a `name` even when it is not a file of its
      own (things referred to by name).
    * `example` (`str`): An example file, in TOML.

    Constructor:
    * `SCKind(kind, summary, fields, named, example)`
    """

    # Constructor arguments:
    kind: str = field(init=True)
    summary: str = field(init=True)
    fields: tuple[SCField, ...] = field(init=True)
    named: bool = field(init=True)
    example: str = field(init=True)


# The keys that start every file.
HEADER: tuple[SCField, ...] = (
    SCField(
        "name",
        "string",
        "Unique among the things of its kind.",
    ),
    SCField(
        "kind",
        "string",
        "What the rest of the file is.",
    ),
    SCField("language", "string", "The language of the names and notes."),
    SCField(
        "version",
        "version",
        "The format version, `MAJOR.MINOR.PATCH`.",
    ),
)

# Every kind, in the order `Shops.md` describes them.
KINDS: dict[str, SCKind] = {
    kind.kind: kind
    for kind in (
        SCKind(
            "shop",
            "A shop: its name, where it is, and its machines.",
            (
                SCField(
                    "location", "table", "Where the shop is.", of="location"
                ),
                SCField(
                    "machines",
                    "list",
                    "The machines in the shop.",
                    required=True,
                    of="machine",
                ),
            ),
            True,
            """\
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
machines = ["@shop_mill.toml"]

[location]
latitude = "37.37066 deg"
longitude = "-122.04002 deg"
address = "700 All American Way, Sunnyvale, CA 94086"
""",
        ),
        SCKind(
            "location",
            "Where a shop is.  Every key is optional, since a shop on a "
            "boat may have none.",
            (
                SCField("latitude", "angle", "North is positive."),
                SCField("longitude", "angle", "East is positive."),
                SCField("address", "string", "The street address."),
            ),
            False,
            """\
latitude = "37.37066 deg"
longitude = "-122.04002 deg"
address = "700 All American Way, Sunnyvale, CA 94086"
""",
        ),
        SCKind(
            "machine",
            "A CNC mill or router (lathes, lasers and 3D printers "
            "later): its axes, table, spindle, controller and tool "
            "table.",
            (
                SCField(
                    "machine",
                    "choice",
                    "What sort of machine it is.",
                    required=True,
                    choices=("mill", "router"),
                ),
                SCField(
                    "axes",
                    "list",
                    "One per axis.",
                    required=True,
                    of="axis",
                ),
                SCField(
                    "table",
                    "table",
                    "The table that the work is held on.",
                    of="machine_table",
                ),
                SCField(
                    "spindle",
                    "table",
                    "The spindle.",
                    required=True,
                    of="spindle",
                ),
                SCField(
                    "controller",
                    "table",
                    "The controller.",
                    required=True,
                    of="controller",
                ),
                SCField(
                    "tool_table",
                    "tool_table",
                    "The tools loaded, by T number (1 to 99).",
                ),
            ),
            True,
            """\
name = "Shop mill"
kind = "machine"
language = "English"
version = "0.0.1"
machine = "mill"
controller = "@linuxcnc.toml"
tool_table = { 1 = "1/4 inch 2 flute end mill", 4 = "15/64 inch drill" }

[spindle]
taper = "R8"
max_rpm = "5000 rpm"

[[axes]]
letter = "X"
travel = "18 in"
max_feed = "110 in/min"
""",
        ),
        SCKind(
            "axis",
            "One linear axis of a machine (rotary axes later).",
            (
                SCField(
                    "letter",
                    "choice",
                    "Its letter in G-code.",
                    required=True,
                    choices=("X", "Y", "Z"),
                ),
                SCField("travel", "length", "How far it moves.", True),
                SCField("max_feed", "feed", "Its fastest feed.", True),
                SCField(
                    "max_acceleration",
                    "acceleration",
                    "Its greatest acceleration.",
                ),
                SCField(
                    "limit_switches",
                    "boolean",
                    "True if it has end of travel switches.",
                ),
                SCField("brake", "boolean", "True if it has a brake."),
            ),
            False,
            """\
letter = "Z"
travel = "16 in"
max_feed = "90 in/min"
max_acceleration = "10 in/s^2"
limit_switches = true
brake = false
""",
        ),
        SCKind(
            "machine_table",
            "The table of a machine, and its T-slots.",
            (
                SCField("length", "length", "Along X.", True),
                SCField("width", "length", "Along Y.", True),
                SCField("t_slots", "integer", "How many T-slots."),
                SCField("t_slot_pitch", "length", "Between T-slots."),
                SCField("t_slot_width", "length", "At the top."),
                SCField("t_slot_depth", "length", "From the table top."),
            ),
            False,
            """\
length = "34 in"
width = "9.5 in"
t_slots = 3
t_slot_pitch = "2.5 in"
t_slot_width = "0.625 in"
t_slot_depth = "0.75 in"
""",
        ),
        SCKind(
            "spindle",
            "The spindle of a machine.",
            (
                SCField("taper", "string", "Its taper (`R8`, `CAT40`, ...)."),
                SCField("min_rpm", "speed", "Its slowest speed."),
                SCField("max_rpm", "speed", "Its fastest speed.", True),
                SCField("reversible", "boolean", "True if it runs backwards."),
                SCField("flood", "boolean", "True if it has flood coolant."),
                SCField("mist", "boolean", "True if it has mist coolant."),
                SCField("air", "boolean", "True if it has an air blast."),
            ),
            False,
            """\
taper = "R8"
min_rpm = "100 rpm"
max_rpm = "5000 rpm"
reversible = true
flood = true
mist = false
air = false
""",
        ),
        SCKind(
            "controller",
            "The controller of a machine (e.g. LinuxCNC), and how its "
            "G-code is written.  LinuxCNC is the baseline.  (To come: "
            "every code it accepts, its canned cycles, and tool length "
            "offsets.)  `tool_change` is a Python `str.format()` "
            "template, filled in with the tool's `number`.",
            (
                SCField(
                    "post_processor",
                    "choice",
                    "Which dialect of G-code it reads.",
                    required=True,
                    choices=("linuxcnc",),
                ),
                SCField(
                    "tool_change",
                    "string",
                    "The words that change the tool.",
                ),
            ),
            True,
            """\
name = "LinuxCNC"
kind = "controller"
language = "English"
version = "0.0.1"
post_processor = "linuxcnc"
tool_change = "T{number:02d} M6"
""",
        ),
    )
}

# The general part of `Shops.md`, before the units and the kinds.
INTRODUCTION: str = """\
# Shops: The Shop Description Files

This document is written by `shops.py` (`./shops.py markdown >
Shops.md`) from the schema that its reader checks files against; a
change is made there, never here.

A shop is described in Nested TOML files: what machines it has (and,
to come, the tools that cut, the tooling that holds the material, and
the materials it cuts).  This document describes every kind of file a
shop can refer to, not only the shop file itself, since a file can
stand alone and be shared by several machines or shops.

This document describes format version `{version}`, the version every
file carries in its `version` key.

In the tables, a row whose first cell is empty continues the row
above it, so that no line is too wide to read in a text editor.

## Nested TOML

A Nested TOML description is kept in one or more
[TOML](https://toml.io/en/v1.0.0) files.  The reader reads them all
and splices them together into one data structure (JSON style
dictionaries, lists, strings, numbers and booleans), which the CNC
side uses without knowing how the files were split.

### The Header Keys

Every file starts with the same four keys:

{header}

* `name`: things refer to each other by name, so no two things of
  the same kind may share one.
* `kind`: one of the sections below; it says which keys the rest of
  the file has.
* `version`: a major version other than this document's is refused,
  and so is a newer minor version.

A table written in place (not in a file of its own) needs none of
them, though it may have them; a `kind` there must fit where it is.

### Joining Files with `@`

A string `"@FILE_NAME"` stands for the contents of that file, in any
place that takes a table (or a list of them):

```toml
machines = ["@shop_mill.toml", "@router.toml"]
```

* The file must be in the same directory as the file that names it (a
  bare file name ending in `.toml`, with no `/`).
* Its `kind` must fit where it is named (a `controller` file can not
  go in `machines`).
* A file is read once, however often it is named; its contents are
  spliced in at every place that names it.
* A missing file, and a loop (a file that names itself, directly or
  not), are refused.

### Units

Every measurement is a string of a number and its unit (`"0.25 in"`,
`"12 in/min"`); a bare number is refused, and so is a unit of the
wrong kind (a feed where a length belongs).  Plain counts (the number
of T-slots) and yes/no facts (`true`/`false`) have no unit.

{units}

### Keys and Problems

* Keys are `snake_case`.
* An unknown key is refused (a misspelled key is a mistake, not a
  comment).
* Every problem is reported with its file, line and key, e.g.
  `shop_mill.toml:12: spindle.max_rpm: "5000" needs a unit`.  Every
  problem found is reported, not only the first.
"""


# Class `SCShopError`:
class SCShopError(ValueError):
    """The problems found in a shop description.

    Attributes:
    * `problems` (`list[str]`):
      Each problem, as `FILE:LINE: KEY: message`.

    Constructor:
    * `SCShopError(problems)`
    """

    # Method `SCShopError.__init__()`:
    def __init__(self, problems: list[str]) -> None:
        """Hold the problems; the message is all of them, one a line.

        Arguments:
        * `problems` (`list[str]`): The problems.
        """
        super().__init__("\n".join(problems))
        self.problems: list[str] = problems


# Class `_Scanner`:
class _Scanner:
    """Find the line of every key and list item in a TOML file.

    The file has already been read by `tomllib`, so it is known to be
    good TOML, and the scanner only needs to follow its structure:
    table headers, keys, inline tables, lists and strings (whose
    contents may look like structure).

    Attributes:
    * `text` (`str`): The file.
    * `at` (`int`): Where the scanner is in `text`.
    * `starts` (`list[int]`): Where each line starts in `text`.
    * `lines` (`dict[KeyPath, int]`): The line of each key path found.
    * `arrays` (`dict[KeyPath, int]`):
      The index of the last table in each array of tables
      (`[[NAME]]`), where later headers refer to it.

    Constructor:
    * `_Scanner(text)`
    """

    # Method `_Scanner.__init__()`:
    def __init__(self, text: str) -> None:
        """Get ready to scan a file.

        Arguments:
        * `text` (`str`): The file, already known to be good TOML.
        """
        self.text: str = text
        self.at: int = 0
        self.starts: list[int] = [0] + [
            found.end() for found in re.finditer("\n", text)
        ]
        self.lines: dict[KeyPath, int] = {}
        self.arrays: dict[KeyPath, int] = {}

    # Method `_Scanner.line()`:
    def line(self) -> int:
        """Return the line the scanner is on.

        Returns:
        * (`int`): The line number (from 1).
        """
        return bisect.bisect_right(self.starts, self.at)

    # Method `_Scanner.peek()`:
    def peek(self) -> str:
        """Return the next character.

        Returns:
        * (`str`): The next character, or `""` at the end.
        """
        return self.text[self.at : self.at + 1]

    # Method `_Scanner.skip()`:
    def skip(self, newlines: bool) -> None:
        """Skip white space and comments.

        Arguments:
        * `newlines` (`bool`): True to skip line ends as well.
        """
        while (character := self.peek()) != "":
            if character in " \t\r" or (newlines and character == "\n"):
                self.at += 1
            elif character == "#":
                end: int = self.text.find("\n", self.at)
                self.at = len(self.text) if end < 0 else end
            else:
                return

    # Method `_Scanner.string()`:
    def string(self) -> str:
        """Skip the string that starts here.

        Returns:
        * (`str`): Its text in the file, quotes and all.
        """
        # Find which of the four quotes it is.
        start: int = self.at
        quote: str = next(
            quote
            for quote in ('"""', "'''", '"', "'")
            if self.text.startswith(quote, self.at)
        )
        self.at += len(quote)

        # Skip to the closing quote; a multi-line string may end with
        # one or two more quote characters, which belong to it.
        while not self.text.startswith(quote, self.at):
            self.at += 2 if quote[0] == '"' and self.peek() == "\\" else 1
        self.at += len(quote)
        extra: int = 0
        while len(quote) == 3 and extra < 2 and self.peek() == quote[0]:
            self.at += 1
            extra += 1
        return self.text[start : self.at]

    # Method `_Scanner.key()`:
    def key(self) -> list[str]:
        """Read a key (dotted or not) that starts here.

        Returns:
        * (`list[str]`): Its parts.
        """
        parts: list[str] = []
        while True:
            # Read one part, bare or quoted.
            self.skip(newlines=False)
            if self.peek() in ('"', "'"):
                quoted: str = self.string()
                parts.append(str(tomllib.loads(f"k = {quoted}")["k"]))
            else:
                bare: re.Match[str] | None = BARE_KEY.match(self.text, self.at)
                assert bare is not None, "tomllib accepted the file"
                parts.append(bare.group())
                self.at = bare.end()

            # A dot means another part follows.
            self.skip(newlines=False)
            if self.peek() != ".":
                return parts
            self.at += 1

    # Method `_Scanner.pair()`:
    def pair(self, table: KeyPath) -> None:
        """Read a `key = value` pair that starts here.

        Arguments:
        * `table` (`KeyPath`): The path of the table it is in.
        """
        # Note the line of the key, and of each table a dotted key
        # makes.
        line: int = self.line()
        path: KeyPath = table
        for part in self.key():
            path += (part,)
            self.lines.setdefault(path, line)

        # Skip the `=` and read the value.
        self.skip(newlines=False)
        self.at += 1
        self.skip(newlines=False)
        self.value(path)

    # Method `_Scanner.value()`:
    def value(self, path: KeyPath) -> None:
        """Read the value that starts here.

        Arguments:
        * `path` (`KeyPath`): Its path.
        """
        character: str = self.peek()
        if character in ("{", "["):
            self.at += 1
            self.items(path, inline_table=character == "{")
        elif character in ('"', "'"):
            self.string()
        else:
            # A number, boolean or date, which ends at one of these.
            while self.peek() not in ("", ",", "]", "}", "#", "\n"):
                self.at += 1

    # Method `_Scanner.items()`:
    def items(self, path: KeyPath, *, inline_table: bool) -> None:
        """Read the items of an inline table or list, after its `{` or `[`.

        Arguments:
        * `path` (`KeyPath`): Its path.
        * `inline_table` (`bool`):
          True for an inline table (pairs), false for a list (values,
          each at its index).
        """
        end: str = "}" if inline_table else "]"
        index: int = 0
        while True:
            self.skip(newlines=True)
            if self.peek() == end:
                self.at += 1
                return
            if self.peek() == ",":
                self.at += 1
            elif inline_table:
                self.pair(path)
            else:
                self.lines[path + (index,)] = self.line()
                self.value(path + (index,))
                index += 1

    # Method `_Scanner.header()`:
    def header(self, parts: list[str]) -> KeyPath:
        """Return the path that a table header names.

        Arguments:
        * `parts` (`list[str]`): The parts of its key.

        Returns:
        * (`KeyPath`):
          Its path, with each array of tables in it replaced by that
          array's last table.
        """
        path: KeyPath = ()
        for part in parts:
            path += (part,)
            if path in self.arrays:
                path += (self.arrays[path],)
        return path

    # Method `_Scanner.document()`:
    def document(self) -> dict[KeyPath, int]:
        """Scan the whole file.

        Returns:
        * (`dict[KeyPath, int]`): The line of every key path in it.
        """
        table: KeyPath = ()
        while True:
            self.skip(newlines=True)
            if self.peek() == "":
                return self.lines
            line: int = self.line()
            if self.text.startswith("[[", self.at):
                # A table in an array of tables: `[[NAME]]`.
                self.at += 2
                parts: list[str] = self.key()
                self.at += 2
                array: KeyPath = self.header(parts[:-1]) + (parts[-1],)
                self.lines.setdefault(array, line)
                self.arrays[array] = self.arrays.get(array, -1) + 1
                table = array + (self.arrays[array],)
                self.lines[table] = line
            elif self.peek() == "[":
                # A table: `[NAME]`.
                self.at += 1
                table = self.header(self.key())
                self.at += 1
                self.lines[table] = line
            else:
                self.pair(table)


# Function `locate()`:
def locate(lines: dict[KeyPath, int], path: KeyPath) -> int:
    """Return the line of a key path, or of the nearest table above it.

    Arguments:
    * `lines` (`dict[KeyPath, int]`): From `_Scanner.document()`.
    * `path` (`KeyPath`):
      The path (which may not be in the file, as for a missing key).

    Returns:
    * (`int`): Its line, or 1 if nothing above it has one.
    """
    while path and path not in lines:
        path = path[:-1]
    return lines.get(path, 1)


# Function `shown_path()`:
def shown_path(path: KeyPath) -> str:
    """Return a key path the way TOML users write it.

    Arguments:
    * `path` (`KeyPath`): The path.

    Returns:
    * (`str`): Such as `axes[2].max_feed`.
    """
    shown: str = ""
    for part in path:
        if isinstance(part, int):
            shown += f"[{part}]"
        else:
            shown += f".{part}" if shown else part
    return shown


# Function `measurement_problem()`:
def measurement_problem(value: object, units: dict[str, float]) -> str:
    """Return what is wrong with a measurement, if anything.

    Arguments:
    * `value` (`object`): The value, from TOML.
    * `units` (`dict[str, float]`): The units it may be in.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    allowed: str = ", ".join(units)
    if not isinstance(value, str):
        return (
            f"{value!r} needs a unit, as a string such as "
            f'"{value} {next(iter(units))}" (it may be in {allowed})'
        )
    found: re.Match[str] | None = MEASUREMENT.fullmatch(value)
    if found is None:
        return f"{value!r} is not a number and a unit"
    if found.group(2) not in units:
        return (
            f"{value!r}: {found.group(2)!r} is the wrong unit here "
            f"(it may be in {allowed})"
        )
    return ""


# Class `_Source`:
@dataclass(frozen=True, slots=True)
class _Source:
    """One file being read.

    Attributes:
    * `shown` (`str`): Its path, as problems show it.
    * `lines` (`dict[KeyPath, int]`): The line of every key path.

    Constructor:
    * `_Source(shown, lines)`
    """

    # Constructor arguments:
    shown: str = field(init=True)
    lines: dict[KeyPath, int] = field(init=True)


# Class `_Reader`:
@dataclass(slots=True)
class _Reader:
    """Read Nested TOML files, checking them against `KINDS`.

    Attributes:
    * `directory` (`Path`): Where the files are.
    * `files` (`dict[Path, dict[str, object]]`):
      Every file read so far, checked, by its path.
    * `problems` (`list[str]`): Every problem found so far.
    * `reading` (`list[Path]`):
      The files being read, each named by the one before it, to find
      loops.

    Constructor:
    * `_Reader(directory)`
    """

    # Constructor arguments:
    directory: Path = field(init=True)

    # Remaining attributes (alphabetized):
    files: dict[Path, dict[str, object]] = field(
        init=False, default_factory=dict
    )
    problems: list[str] = field(init=False, default_factory=list)
    reading: list[Path] = field(init=False, default_factory=list)

    # Method `_Reader.problem()`:
    def problem(self, source: _Source, path: KeyPath, message: str) -> None:
        """Note a problem.

        Arguments:
        * `source` (`_Source`): The file it is in.
        * `path` (`KeyPath`): Where in the file.
        * `message` (`str`): What is wrong.
        """
        where: str = f"{source.shown}:{locate(source.lines, path)}"
        key: str = f" {shown_path(path)}:" if path else ""
        self.problems.append(f"{where}:{key} {message}")

    # Method `_Reader.file()`:
    def file(self, file: Path, shown: str) -> dict[str, object] | None:
        """Read and check one file, the first time it is named.

        Arguments:
        * `file` (`Path`): The file.
        * `shown` (`str`): Its path, as problems show it.

        Returns:
        * (`dict[str, object] | None`):
          Its contents, checked against its `kind`, or `None` if it
          could not be read or has no known `kind` (both noted).
        """
        # Hand back a file read before.
        if file in self.files:
            return self.files[file]

        # Read it as TOML, noting a syntax error as FILE:LINE:COLUMN.
        try:
            text: str = file.read_text(encoding="utf-8")
            data: dict[str, object] = tomllib.loads(text)
        except OSError as error:
            self.problems.append(f"{shown}: {error.strerror}")
            return None
        except tomllib.TOMLDecodeError as error:
            message: str = str(error)
            found: re.Match[str] | None = re.fullmatch(
                r"(.*) \(at line (\d+), column (\d+)\)", message
            )
            if found is not None:
                message = (
                    f"{found.group(2)}:{found.group(3)}: {found.group(1)}"
                )
            self.problems.append(f"{shown}:{message}")
            return None
        source: _Source = _Source(shown, _Scanner(text).document())

        # Check it against its own kind.
        kind: object = data.get("kind")
        if kind not in KINDS:
            known: str = ", ".join(KINDS)
            self.problem(source, ("kind",), f"is not one of {known}")
            return None
        self.reading.append(file)
        contents: dict[str, object] = self.table(
            data, KINDS[str(kind)], (), source, whole=True
        )
        self.reading.pop()
        self.files[file] = contents
        return contents

    # Method `_Reader.reference()`:
    def reference(
        self, name: str, kind: SCKind, path: KeyPath, source: _Source
    ) -> dict[str, object]:
        """Return the contents of a file named by `"@FILE_NAME"`.

        Arguments:
        * `name` (`str`): The file name (after the `@`).
        * `kind` (`SCKind`): The kind of table that belongs here.
        * `path` (`KeyPath`): Where it is named.
        * `source` (`_Source`): The file that names it.

        Returns:
        * (`dict[str, object]`):
          The file's contents, or `{}` if there is a problem (noted).
        """
        # Find the file, refusing names outside this directory.
        if "/" in name or "\\" in name or not name.endswith(".toml"):
            self.problem(
                source,
                path,
                f'"@{name}" must name a `.toml` file in this directory',
            )
            return {}
        file: Path = self.directory / name
        if file in self.reading:
            loop: list[str] = [
                named.name
                for named in self.reading[self.reading.index(file) :]
            ]
            loop.append(name)
            self.problem(source, path, "a loop: " + " -> ".join(loop))
            return {}

        # Read it (once), and check that it fits here.
        if not file.is_file():
            self.problem(source, path, f'no file "{name}"')
            return {}
        contents: dict[str, object] | None = self.file(file, file.as_posix())
        if contents is None:
            return {}
        if contents.get("kind") != kind.kind:
            self.problem(
                source,
                path,
                f'"{name}" is a `{contents.get("kind")}` file; '
                f"a `{kind.kind}` belongs here",
            )
            return {}
        return contents

    # Method `_Reader.table()`:
    def table(
        self,
        value: object,
        kind: SCKind,
        path: KeyPath,
        source: _Source,
        *,
        whole: bool = False,
    ) -> dict[str, object]:
        """Check a table, or follow a `"@FILE_NAME"` to one.

        Arguments:
        * `value` (`object`): The table, or a `"@FILE_NAME"` string.
        * `kind` (`SCKind`): What kind of table it must be.
        * `path` (`KeyPath`): Where it is.
        * `source` (`_Source`): The file it is in.
        * `whole` (`bool`): True if it is a whole file.

        Returns:
        * (`dict[str, object]`):
          The table, with every `"@FILE_NAME"` in it replaced by the
          file's contents.
        """
        # Follow a file name, and refuse anything else but a table.
        if isinstance(value, str) and value.startswith("@"):
            return self.reference(value[1:], kind, path, source)
        if not isinstance(value, dict):
            self.problem(
                source,
                path,
                f'{value!r} is not a `{kind.kind}` table (or "@FILE_NAME")',
            )
            return {}

        # Check every key.
        fields: dict[str, SCField] = {
            field.key: field for field in HEADER + kind.fields
        }
        contents: dict[str, object] = {}
        for key, item in value.items():
            if key not in fields:
                known: str = ", ".join(f.key for f in kind.fields)
                self.problem(
                    source,
                    path + (key,),
                    f"is not a key of `{kind.kind}` (its keys are {known})",
                )
            else:
                contents[key] = self.value(
                    item, fields[key], path + (key,), source
                )

        # Note the keys that are missing, and a `kind` that does not
        # fit.
        required: list[str] = [f.key for f in kind.fields if f.required]
        if whole:
            required = [f.key for f in HEADER] + required
        elif kind.named:
            required = ["name"] + required
        for key in required:
            if key not in value:
                self.problem(source, path, f"`{key}` is missing")
        if value.get("kind", kind.kind) != kind.kind:
            self.problem(
                source, path + ("kind",), f"a `{kind.kind}` belongs here"
            )
        return contents

    # Method `_Reader.value()`:
    def value(
        self, value: object, schema: SCField, path: KeyPath, source: _Source
    ) -> object:
        """Check one value.

        Arguments:
        * `value` (`object`): The value.
        * `schema` (`SCField`): What it must be.
        * `path` (`KeyPath`): Where it is.
        * `source` (`_Source`): The file it is in.

        Returns:
        * (`object`):
          The value, with every `"@FILE_NAME"` in it replaced by the
          file's contents.
        """
        # Tables and lists of them are checked a level down.
        form: str = schema.form
        if form == "table":
            return self.table(value, KINDS[schema.of], path, source)
        if form == "list":
            if not isinstance(value, list):
                self.problem(source, path, f"{value!r} is not a list")
                return []
            return [
                self.table(item, KINDS[schema.of], path + (index,), source)
                for index, item in enumerate(value)
            ]

        # Everything else is checked as it is.
        problem: str = _scalar_problem(value, schema)
        if problem:
            self.problem(source, path, problem)
        return value


# Function `_scalar_problem()`:
def _scalar_problem(value: object, schema: SCField) -> str:
    """Return what is wrong with a value that is not a table or list.

    Arguments:
    * `value` (`object`): The value.
    * `schema` (`SCField`): What it must be.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    form: str = schema.form
    problem: str = ""
    if form in UNITS:
        problem = measurement_problem(value, UNITS[form])
    elif form in ("string", "choice", "version"):
        problem = _string_problem(value, schema)
    elif form == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            problem = f"{value!r} is not a whole number"
    elif form == "boolean":
        if not isinstance(value, bool):
            problem = f"{value!r} is not `true` or `false`"
    elif form == "tool_table":
        problem = _tool_table_problem(value)
    return problem


# Function `_string_problem()`:
def _string_problem(value: object, schema: SCField) -> str:
    """Return what is wrong with a string, a choice or a version.

    Arguments:
    * `value` (`object`): The value.
    * `schema` (`SCField`): What it must be.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    # Every one of them is a string.
    if not isinstance(value, str):
        return f"{value!r} is not a string"

    # A choice is one of its choices.
    if schema.form == "choice" and value not in schema.choices:
        return f'"{value}" is not one of ' + ", ".join(
            f'"{choice}"' for choice in schema.choices
        )

    # A version has the same major version, and no newer minor one.
    if schema.form == "version":
        found: re.Match[str] | None = VERSION.fullmatch(value)
        ours: re.Match[str] | None = VERSION.fullmatch(FORMAT_VERSION)
        assert ours is not None, "FORMAT_VERSION is a version"
        if found is None:
            return f'"{value}" is not a version (MAJOR.MINOR.PATCH)'
        if found.group(1) != ours.group(1) or int(found.group(2)) > int(
            ours.group(2)
        ):
            return f'version "{value}" can not be read (only {FORMAT_VERSION})'
    return ""


# Function `_tool_table_problem()`:
def _tool_table_problem(value: object) -> str:
    """Return what is wrong with a tool table.

    Arguments:
    * `value` (`object`): The value.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    if not isinstance(value, dict):
        return f"{value!r} is not a table of T numbers to tool names"
    for number, name in value.items():
        if not number.isdigit() or not 1 <= int(number) <= 99:
            return f'"{number}" is not a T number (1 to 99)'
        if not isinstance(name, str):
            return f"T{number}: {name!r} is not a tool name"
    return ""


# Function `read()`:
def read(file: Path) -> dict[str, object]:
    """Read and check a Nested TOML description.

    Arguments:
    * `file` (`Path`):
      Its top file (such as a shop); the files it names are in the
      same directory.

    Returns:
    * (`dict[str, object]`):
      Its contents, with every `"@FILE_NAME"` replaced by that file's
      contents.

    Raises:
    * `SCShopError`: With every problem found.
    """
    reader: _Reader = _Reader(file.parent)
    contents: dict[str, object] | None = reader.file(file, file.as_posix())
    if reader.problems or contents is None:
        raise SCShopError(reader.problems)
    return contents


# Function `_words()`:
def _words(cell: str) -> list[str]:
    """Return the words of a table cell, keeping code spans whole.

    Arguments:
    * `cell` (`str`): The cell, in Markdown.

    Returns:
    * (`list[str]`):
      Its words; a code span (`` `like this` ``) and anything stuck
      to it (a comma) is one word, since a code span can not be split
      across rows.
    """
    return re.findall(r"(?:`[^`]*`|[^\s`])+", cell)


# Function `_wrap()`:
def _wrap(cell: str, width: int) -> list[str]:
    """Return a table cell wrapped to a width.

    Arguments:
    * `cell` (`str`): The cell, in Markdown.
    * `width` (`int`): The width (no less than its longest word).

    Returns:
    * (`list[str]`): Its lines (at least one, which may be empty).
    """
    lines: list[str] = []
    line: str = ""
    for word in _words(cell):
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    lines.append(line)
    return lines


# Function `_markdown_table()`:
def _markdown_table(rows: list[list[str]], width: int = MARKDOWN_WIDTH) -> str:
    """Return a Markdown table whose `|`s line up in a text editor.

    A table wider than `width` has its wide cells wrapped; a row whose
    first cell is empty continues the row above it.

    Arguments:
    * `rows` (`list[list[str]]`):
      The heading row, then the other rows, each a list of cells.  The
      heading and first column are never wrapped.
    * `width` (`int`): The widest a line may be.

    Returns:
    * (`str`): The table, each column padded to its widest line.
    """
    # Each column is as wide as its widest cell (and the `---`), and
    # no narrower than its heading or its longest word.
    columns: range = range(len(rows[0]))
    widths: list[int] = [
        max(3, *(len(row[column]) for row in rows)) for column in columns
    ]
    narrowest: list[int] = [
        widths[0]
        if column == 0
        else max(
            3,
            len(rows[0][column]),
            *(len(word) for row in rows for word in _words(row[column])),
        )
        for column in columns
    ]

    # While the table is too wide, narrow its widest column that can be.
    while sum(widths) + 3 * len(widths) + 1 > width:
        column: int = max(
            (c for c in columns if widths[c] > narrowest[c]),
            key=lambda c: widths[c],
            default=-1,
        )
        if column < 0:
            break
        widths[column] -= 1

    # Wrap every cell to its column, and make each row into lines.
    table: list[list[str]] = [rows[0], ["-" * w for w in widths]]
    for row in rows[1:]:
        wrapped: list[list[str]] = [
            _wrap(cell, widths[column]) for column, cell in enumerate(row)
        ]
        for line in range(max(len(cell) for cell in wrapped)):
            table.append(
                [cell[line] if line < len(cell) else "" for cell in wrapped]
            )
    widths = [max(len(row[c]) for row in table) for c in columns]
    lines: list[str] = []
    for row in table:
        cells: str = " | ".join(
            cell.ljust(w) for cell, w in zip(row, widths, strict=True)
        )
        lines.append(f"| {cells} |")
    return "\n".join(lines)


# Function `_fields_table()`:
def _fields_table(
    fields: tuple[SCField, ...], *, all_required: bool = False
) -> str:
    """Return a Markdown table of some keys.

    Arguments:
    * `fields` (`tuple[SCField, ...]`): The keys.
    * `all_required` (`bool`):
      True if every one is required (as the header keys are, in a
      file).

    Returns:
    * (`str`): The table.
    """
    rows: list[list[str]] = [["Key", "Value", "Required", "Meaning"]]
    for schema in fields:
        required: str = "yes" if schema.required or all_required else "no"
        rows.append(
            [f"`{schema.key}`", schema.shown(), required, schema.meaning]
        )
    return _markdown_table(rows)


# Function `markdown()`:
def markdown() -> str:
    """Return `Shops.md`, which describes every kind of file.

    Returns:
    * (`str`): The document.
    """
    # The general part.
    units: list[list[str]] = [["Measurement", "Units"]]
    for form, table in UNITS.items():
        shown: str = ", ".join(f"`{unit}`" for unit in table)
        units.append([form.replace("_", " "), shown])
    sections: list[str] = [
        INTRODUCTION.format(
            version=FORMAT_VERSION,
            header=_fields_table(HEADER, all_required=True),
            units=_markdown_table(units),
        )
    ]

    # One section per kind.
    for kind in KINDS.values():
        named: str = (
            "  It has a `name` even when it is not a file of its own."
            if kind.named
            else ""
        )
        sections.append(
            f"## `{kind.kind}`\n\n"
            f"{textwrap.fill(kind.summary + named, 72)}\n\n"
            f"{_fields_table(kind.fields)}\n\n"
            f"```toml\n{kind.example}```\n"
        )
    return "\n".join(sections)


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Check files, show what they read as, or write `Shops.md`.

    Arguments:
    * `arguments` (`list[str]`): The command line, without the program.

    Returns:
    * (`int`): The exit status: 0 if all went well, 1 if not.
    """
    # The command line.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Check shop description files, or write Shops.md."
    )
    parser.add_argument(
        "command",
        choices=("check", "json", "markdown"),
        help="check FILEs; show FILEs as JSON; print Shops.md",
    )
    parser.add_argument("files", nargs="*", type=Path, metavar="FILE")
    options: argparse.Namespace = parser.parse_args(arguments)

    # Print `Shops.md`.
    if options.command == "markdown":
        print(markdown(), end="")
        return 0

    # Read each file, showing its problems, or what it reads as.
    status: int = 0
    for file in options.files:
        try:
            contents: dict[str, object] = read(file)
        except SCShopError as error:
            print(error, file=sys.stderr)
            status = 1
            continue
        if options.command == "json":
            print(json.dumps(contents, indent=2))
        else:
            print(f"{file.as_posix()}: OK")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
