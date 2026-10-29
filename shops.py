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
import datetime
import json
import math
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias, cast

from scmachine import DrillCycle, SCMachine, SCTool, ToolKind

# The format version that this module reads and describes.
FORMAT_VERSION: str = "0.0.1"

# Where a value is in a file: its keys, and its indices in lists.
KeyPath: TypeAlias = tuple[str | int, ...]

# Every measurement in a shop file has a unit, such as "0.25 in" or
# "6 mm": these are the units each kind of measurement takes, and what
# each is in the units used inside (inches, inches per minute,
# revolutions per minute, degrees, and fractions).
LENGTH: dict[str, float] = {
    "in": 1.0,
    "inch": 1.0,
    "inches": 1.0,
    "ft": 12.0,
    "mm": 1.0 / 25.4,
    "cm": 10.0 / 25.4,
}
FEED: dict[str, float] = {
    "in/min": 1.0,
    "ipm": 1.0,
    "in/s": 60.0,
    "mm/min": 1.0 / 25.4,
    "mm/s": 60.0 / 25.4,
}
SPEED: dict[str, float] = {"rpm": 1.0}
ANGLE: dict[str, float] = {"deg": 1.0}
FRACTION: dict[str, float] = {"%": 0.01}

# Accelerations, in inches per second squared, and rotary feeds, in
# degrees per minute.
ACCELERATION: dict[str, float] = {"in/s^2": 1.0, "mm/s^2": 1.0 / 25.4}
ROTARY_FEED: dict[str, float] = {"deg/min": 1.0, "deg/s": 60.0}

# Surface speeds, in feet per minute, and feeds per revolution (for
# drills), in inches per revolution.
SURFACE_SPEED: dict[str, float] = {
    "sfm": 1.0,
    "ft/min": 1.0,
    "m/min": 1000.0 / 25.4 / 12.0,
}
FEED_PER_REV: dict[str, float] = {
    "in/rev": 1.0,
    "ipr": 1.0,
    "mm/rev": 1.0 / 25.4,
}

# Chip loads (the feed per tooth of an end mill), in inches per tooth.
CHIP_LOAD: dict[str, float] = {
    "in/tooth": 1.0,
    "ipt": 1.0,
    "mm/tooth": 1.0 / 25.4,
}

# Money: a few common currencies, though any ISO 4217 code (three
# capital letters) is taken.  Amounts are never converted between
# currencies.
MONEY: dict[str, float] = {"USD": 1.0, "CAD": 1.0, "EUR": 1.0, "GBP": 1.0}
CURRENCY: re.Pattern[str] = re.compile(r"[A-Z]{3}")

# The kinds of measurement, as `SCField.form` names them.
UNITS: dict[str, dict[str, float]] = {
    "length": LENGTH,
    "feed": FEED,
    "acceleration": ACCELERATION,
    "speed": SPEED,
    "angle": ANGLE,
    "rotary_feed": ROTARY_FEED,
    "surface_speed": SURFACE_SPEED,
    "feed_per_rev": FEED_PER_REV,
    "chip_load": CHIP_LOAD,
    "fraction": FRACTION,
    "money": MONEY,
}

# The forms of value that are not measurements.
FORMS: tuple[str, ...] = (
    "string",
    "integer",
    "boolean",
    "choice",
    "version",
    "date",
    "table",
    "list",
    "t_numbers",
    "by_material",
)

# The widest line in `Shops.md`.
MARKDOWN_WIDTH: int = 79

# A measurement: a number, then its unit.  The number may be a
# decimal (`0.5`, `1e-3`), a fraction (`1/2`), or a whole number and a
# fraction joined by `-` (`1-1/2`), as catalogs in inches write them.
MEASUREMENT: re.Pattern[str] = re.compile(
    r"\s*([-+]?)"
    r"(?:(?:(\d+)-)?(\d+)/(\d+)|((?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?))"
    r"\s*(\S+)\s*"
)

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
      `"t_numbers"` maps T numbers to tool names; `"by_material"`
      maps material names to tables of the kind named by `of`.
    * `meaning` (`str`): What it is, in Markdown.
    * `required` (`bool`): True if it must be there.
    * `of` (`str`): The kind of a `"table"` or `"list"`.
    * `choices` (`tuple[str, ...]`):
      The strings a `"choice"` takes, whatever their capitals.
    * `open` (`bool`):
      True if `choices` are only the common ones, so that a string
      ending in `!` is taken without a check (`"HSK63!"`).

    Constructor:
    * `SCField(key, form, meaning, required, of, choices, open)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    form: str = field(init=True)
    meaning: str = field(init=True)
    required: bool = field(init=True, default=False)
    of: str = field(init=True, default="")
    choices: tuple[str, ...] = field(init=True, default=())
    open: bool = field(init=True, default=False)

    # Method `SCField.__post_init__()`:
    def __post_init__(self) -> None:
        """Check that the form is known.

        Raises:
        * `ValueError`: If `form`, `of` or `choices` do not fit.
        """
        if self.form not in UNITS and self.form not in FORMS:
            raise ValueError(f"{self.key}: unknown form {self.form!r}")
        if (self.form in ("table", "list", "by_material")) != bool(self.of):
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
            if self.open:
                shown += ", or another ending in `!`"
        elif self.form == "t_numbers":
            shown = "T number to tool name"
        elif self.form == "by_material":
            shown = f"material name to `{self.of}`"
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

# The common spindle interfaces (a router's spindle may take ER
# collets itself), collets and tool materials.
INTERFACES: tuple[str, ...] = (
    "R8",
    "BT30",
    "BT40",
    "BT50",
    "CAT30",
    "CAT40",
    "CAT50",
    "NMTB30",
    "NMTB40",
    "HSK63A",
    "ER11",
    "ER16",
    "ER20",
    "ER25",
    "ER32",
    "ER40",
)
COLLETS: tuple[str, ...] = (
    "ER8",
    "ER11",
    "ER16",
    "ER20",
    "ER25",
    "ER32",
    "ER40",
    "ER50",
    "R8",
    "5C",
)
MATERIALS: tuple[str, ...] = (
    "HSS",
    "cobalt",
    "carbide",
    "cermet",
    "ceramic",
    "CBN",
    "PCD",
)

# The kinds of tools, which a machine's `tool_table` names.
TOOL_KINDS: tuple[str, ...] = (
    "end_mill",
    "drill",
    "chamfer_mill",
    "corner_rounding_mill",
    "double_angle_cutter",
)


# Function `_tool_fields()`:
def _tool_fields(*special: SCField) -> tuple[SCField, ...]:
    """Return the keys of a kind of tool.

    Arguments:
    * `special` (`SCField`): The keys only this kind of tool has.

    Returns:
    * (`tuple[SCField, ...]`):
      `special` (its sizes first), then what every kind of tool has:
      its shank and length, what it is made of, where it came from,
      and how to cut with it.
    """
    return (
        SCField("description", "string", "What it is, in a few words."),
        *special,
        SCField("shank", "length", "The shank diameter, if not `diameter`."),
        SCField("overall_length", "length", "Its whole length (OAL).", True),
        SCField(
            "material",
            "choice",
            "What it is made of.",
            required=True,
            choices=MATERIALS,
            open=True,
        ),
        SCField("grade", "string", "The grade (`M2`, `M42`, ...)."),
        SCField("coating", "string", "Its coating or finish (`AlTiN`, ...)."),
        SCField("manufacturer", "string", "Who made it."),
        SCField("manufacturer_pn", "string", "The maker's part number."),
        SCField("vendor", "string", "Who sold it."),
        SCField("vendor_pn", "string", "The vendor's part number."),
        SCField("cost", "money", "What it cost."),
        SCField("acquired", "date", "When it was bought (`2026-10-27`)."),
        SCField("rpm", "speed", "The spindle speed to cut at."),
        SCField("feed", "feed", "The feed to cut at."),
        SCField("plunge", "feed", "The feed going straight down."),
    )


# Function `_size_fields()`:
def _size_fields(*, length_of_cut: bool = True) -> tuple[SCField, ...]:
    """Return the `diameter` and `length_of_cut` keys of a tool.

    Arguments:
    * `length_of_cut` (`bool`): False to leave out `length_of_cut`.

    Returns:
    * (`tuple[SCField, ...]`): The keys.
    """
    diameter: SCField = SCField(
        "diameter", "length", "The cutting diameter.", True
    )
    if not length_of_cut:
        return (diameter,)
    return (
        diameter,
        SCField("length_of_cut", "length", "How deep it can cut (LOC).", True),
    )


# Function `_collet_field()`:
def _collet_field(*, required: bool) -> SCField:
    """Return the `collet` key of a kind of tool.

    Arguments:
    * `required` (`bool`):
      True if the tool is always held in a collet (a drill).

    Returns:
    * (`SCField`): The key.
    """
    return SCField(
        "collet",
        "choice",
        "The collet it is held in, if it is.",
        required=required,
        choices=COLLETS,
        open=True,
    )


# Function `_cutting_field()`:
def _cutting_field() -> SCField:
    """Return the `cutting` field of a drill or an end mill.

    Returns:
    * (`SCField`): The field.
    """
    return SCField(
        "cutting",
        "by_material",
        "Its own speed and feed for a material, which win over those "
        "worked out from `materials` (and are needed for a tool that "
        "is not HSS, cobalt or carbide).",
        of="cutting",
    )


# Every kind, in the order `Shops.md` describes them.
KINDS: dict[str, SCKind] = {
    kind.kind: kind
    for kind in (
        SCKind(
            "shops",
            "Every shop: the top of a description.  Each shop may be "
            "written in place, or kept in its own file.",
            (
                SCField(
                    "shops",
                    "list",
                    "The shops.",
                    required=True,
                    of="shop",
                ),
            ),
            True,
            """\
name = "Example shops"
kind = "shops"
language = "English"
version = "0.0.1"
shops = ["@home_shop.toml"]
""",
        ),
        SCKind(
            "shop",
            "A shop: its name, where it is, its machines and its tools.",
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
                SCField(
                    "tools",
                    "list",
                    "The tools on hand, shared by the machines.",
                    of="tools",
                ),
                SCField(
                    "materials",
                    "table",
                    "The materials it cuts, and how to drill them.",
                    of="materials",
                ),
            ),
            True,
            """\
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
machines = ["@shop_mill.toml"]
tools = ["@tools.toml"]

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
                    "table",
                    "The tools loaded.",
                    of="tool_table",
                ),
                SCField(
                    "preferences",
                    "table",
                    "How it is run.",
                    of="preferences",
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
tool_table = "@shop_mill_tools.toml"

[spindle]
interface = "R8"
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
                SCField(
                    "interface",
                    "choice",
                    "What its tool holders fit.",
                    required=True,
                    choices=INTERFACES,
                    open=True,
                ),
                SCField("min_rpm", "speed", "Its slowest speed."),
                SCField("max_rpm", "speed", "Its fastest speed.", True),
                SCField("reversible", "boolean", "True if it runs backwards."),
                SCField("flood", "boolean", "True if it has flood coolant."),
                SCField("mist", "boolean", "True if it has mist coolant."),
                SCField("air", "boolean", "True if it has an air blast."),
            ),
            False,
            """\
interface = "R8"
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
        SCKind(
            "preferences",
            "How a machine is run: heights, speeds and how pockets and "
            "holes are cut.  (These are kept with the machine for now; "
            "some may belong to the shop or to the job.)",
            (
                SCField(
                    "z_safe",
                    "length",
                    "Above all of the hold down tooling.",
                    True,
                ),
                SCField(
                    "clearance",
                    "length",
                    "Rapids down stop this far above the work.",
                    True,
                ),
                SCField(
                    "tool_change_z",
                    "length",
                    "Rise here before every tool change.",
                    True,
                ),
                SCField(
                    "rapid_speed",
                    "feed",
                    "The rapid speed, for estimating run times.",
                    True,
                ),
                SCField(
                    "drill_cycle",
                    "choice",
                    "How holes are drilled (`moves`: no canned cycle).",
                    required=True,
                    choices=("G81", "G73", "G83", "moves"),
                ),
                SCField(
                    "through_overcut",
                    "fraction",
                    "How much deeper a cut through the part goes, of its "
                    "thickness.",
                    True,
                ),
                SCField(
                    "stepover",
                    "fraction",
                    "How far apart pocket rings are, of the tool's diameter.",
                    True,
                ),
                SCField(
                    "ramp_angle",
                    "angle",
                    "The steepest ramp into a pocket that is not drilled.",
                    True,
                ),
                SCField(
                    "finish_allowance",
                    "length",
                    "What a roughing end mill leaves on walls and floors "
                    "for the end mill that finishes them.",
                    True,
                ),
            ),
            False,
            """\
z_safe = "1 in"
clearance = "0.05 in"
tool_change_z = "2 in"
rapid_speed = "60 in/min"
drill_cycle = "G83"
through_overcut = "10 %"
stepover = "90 %"
ramp_angle = "3 deg"
finish_allowance = "0.05 in"
""",
        ),
        SCKind(
            "tool_table",
            "The tools loaded in one machine: T numbers (1 to 99) and "
            "the names of the tools in them.  Each is unique: no T "
            "number twice, and no tool twice, here or in any other "
            "machine's tool table (a tool is in one machine at a time). "
            " Tools are loaded and unloaded far more often than a "
            "machine changes, so the tool table is usually a file of "
            "its own.",
            (
                SCField(
                    "tools",
                    "t_numbers",
                    "The tools, by T number.",
                    required=True,
                ),
            ),
            True,
            """\
name = "Shop mill tools"
kind = "tool_table"
language = "English"
version = "0.0.1"

[tools]
1 = "1/4 in 2 flute carbide end mill"
4 = "15/64 in HSS jobber drill"
""",
        ),
        SCKind(
            "tools",
            "Tools: the bits that go in a holder in the spindle.  How "
            "to cut with each (`rpm`, `feed`, `plunge`) is given with "
            "the tool for now, until it can be worked out from the "
            "material being cut.  Only "
            "the bits are described, not their holders (a drill goes in "
            "a collet; an end mill in a collet or an end mill holder of "
            "its shank's size).  Tools are shared by machines, so they "
            "are not listed by machine: a machine's `tool_table` names "
            "the ones it has loaded, and every tool's `name` is unique "
            "among all the tools (T numbers are only unique within one "
            "machine).",
            (
                SCField("end_mills", "list", "The end mills.", of="end_mill"),
                SCField("drills", "list", "The drills.", of="drill"),
                SCField(
                    "chamfer_mills",
                    "list",
                    "The chamfer mills.",
                    of="chamfer_mill",
                ),
                SCField(
                    "corner_rounding_mills",
                    "list",
                    "The corner rounding mills.",
                    of="corner_rounding_mill",
                ),
                SCField(
                    "double_angle_cutters",
                    "list",
                    "The double angle shank cutters.",
                    of="double_angle_cutter",
                ),
            ),
            True,
            """\
name = "Tools"
kind = "tools"
language = "English"
version = "0.0.1"

[[end_mills]]
name = "1/4 in 2 flute carbide end mill"
diameter = "1/4 in"
length_of_cut = "3/4 in"
overall_length = "2-1/2 in"
flutes = 2
end = "square"
material = "carbide"

[[drills]]
name = "15/64 in HSS jobber drill"
diameter = "15/64 in"
length_of_cut = "2-5/8 in"
overall_length = "3-7/8 in"
point_angle = "118 deg"
collet = "ER32"
material = "HSS"
""",
        ),
        SCKind(
            "end_mill",
            "An end mill: square, ball or bull nose (a square end with "
            "rounded corners), and perhaps a rougher.",
            _tool_fields(
                *_size_fields(),
                SCField("flutes", "integer", "How many flutes.", True),
                SCField(
                    "end",
                    "choice",
                    "The shape of its end.",
                    required=True,
                    choices=("square", "ball", "bull_nose"),
                ),
                SCField("corner_radius", "length", "A bull nose's corners."),
                SCField(
                    "center_cutting",
                    "boolean",
                    "True if it can plunge straight down.",
                ),
                SCField(
                    "roughing",
                    "boolean",
                    "True for a rougher (serrated flutes).",
                ),
                _collet_field(required=False),
                _cutting_field(),
            ),
            True,
            """\
name = "1/2 in 2 flute carbide end mill"
diameter = "1/2 in"
length_of_cut = "1 in"
overall_length = "3 in"
flutes = 2
end = "square"
center_cutting = true
material = "carbide"
coating = "uncoated"
vendor = "Shars Tool"
vendor_pn = "415-0998"
cost = "47.02 USD"
acquired = 2026-10-27
""",
        ),
        SCKind(
            "drill",
            "A twist drill.",
            _tool_fields(
                *_size_fields(),
                SCField(
                    "flutes", "integer", "How many flutes (2 if not given)."
                ),
                SCField("point_angle", "angle", "The included angle.", True),
                _collet_field(required=True),
                SCField(
                    "split_point", "boolean", "True if it has a split point."
                ),
                SCField(
                    "peck_depth",
                    "length",
                    "How deep each peck goes (0 for none).",
                ),
                _cutting_field(),
            ),
            True,
            """\
name = "1/8 in cobalt jobber drill"
diameter = "1/8 in"
length_of_cut = "1-5/8 in"
overall_length = "2-3/4 in"
point_angle = "135 deg"
split_point = true
collet = "ER32"
material = "cobalt"
grade = "M42"
coating = "straw"
vendor = "Shars Tool"
vendor_pn = "415-8998"
cost = "2.67 USD"

[cutting."6061 aluminum"]
rpm = "1200 rpm"
feed = "4 in/min"
""",
        ),
        SCKind(
            "cutting",
            "A tool's own speed and feed for one material.",
            (
                SCField("rpm", "speed", "The spindle speed.", True),
                SCField("feed", "feed", "The feed.", True),
                SCField(
                    "plunge",
                    "feed",
                    "The feed going straight down (a drill's `feed`, or "
                    "an end mill's `feed` times `plunge_factor`, if not "
                    "given).",
                ),
            ),
            False,
            """\
rpm = "1200 rpm"
feed = "4 in/min"
""",
        ),
        SCKind(
            "chamfer_mill",
            "A chamfer mill (a V-bit), which bevels top edges.",
            _tool_fields(
                *_size_fields(length_of_cut=False),
                SCField(
                    "tip_diameter", "length", "The diameter at its tip.", True
                ),
                SCField(
                    "angle",
                    "angle",
                    "The included angle (90 deg makes 45 deg bevels).",
                    True,
                ),
                SCField("flutes", "integer", "How many flutes."),
                _collet_field(required=False),
            ),
            True,
            """\
name = "1/8 in 90 deg carbide chamfer mill"
diameter = "1/8 in"
tip_diameter = "0.020 in"
angle = "90 deg"
flutes = 2
overall_length = "1-1/2 in"
material = "carbide"
vendor = "Shars Tool"
vendor_pn = "416-3509"
""",
        ),
        SCKind(
            "corner_rounding_mill",
            "A corner rounding mill, which rounds top edges over to its "
            "radius.  Its tip (a pilot) rides along the wall below.",
            _tool_fields(
                SCField(
                    "radius", "length", "The radius it rounds edges to.", True
                ),
                SCField(
                    "tip_diameter", "length", "The diameter at its tip.", True
                ),
                SCField("flutes", "integer", "How many flutes."),
                _collet_field(required=False),
            ),
            True,
            """\
name = "1/16 in radius carbide corner rounding mill"
radius = "0.0625 in"
tip_diameter = "0.0469 in"
flutes = 2
shank = "3/16 in"
overall_length = "2 in"
material = "carbide"
vendor = "Shars Tool"
vendor_pn = "417-1112"
""",
        ),
        SCKind(
            "double_angle_cutter",
            "A pointed double angle shank cutter: a cone above and a "
            "cone below its widest point, on a thin neck, so it can "
            "chamfer bottom edges (back chamfering) as well as top ones.",
            _tool_fields(
                *_size_fields(length_of_cut=False),
                SCField(
                    "angle",
                    "angle",
                    "The included angle of the two cones together.",
                    True,
                ),
                SCField(
                    "width",
                    "length",
                    "The height of the cutter (L2), point to point.",
                    True,
                ),
                SCField("neck_diameter", "length", "The neck's diameter."),
                SCField(
                    "neck_length",
                    "length",
                    "How far below the shank the cutter reaches (L3).",
                ),
                SCField("flutes", "integer", "How many flutes."),
                _collet_field(required=False),
            ),
            True,
            """\
name = "1/4 in 90 deg double angle shank cutter"
diameter = "1/4 in"
angle = "90 deg"
width = "0.125 in"
neck_diameter = "1/8 in"
neck_length = "0.625 in"
flutes = 4
shank = "1/4 in"
overall_length = "2-1/2 in"
material = "carbide"
vendor = "Shars Tool"
vendor_pn = "436-4296"
""",
        ),
        SCKind(
            "materials",
            "The materials a shop cuts, and how to drill and mill them.  "
            "Speeds and feeds worked out from these are only starting "
            "points; a tool's own `cutting` entries win.",
            (
                SCField(
                    "carbide_speed_factor",
                    "fraction",
                    "A carbide tool's surface speed, as a share of HSS's.",
                    True,
                ),
                SCField(
                    "cobalt_speed_factor",
                    "fraction",
                    "A cobalt tool's surface speed, as a share of HSS's.",
                    True,
                ),
                SCField(
                    "end_milling",
                    "table",
                    "How end mills feed.",
                    True,
                    of="end_milling",
                ),
                SCField(
                    "drilling",
                    "table",
                    "How drills feed.",
                    True,
                    of="drilling",
                ),
                SCField(
                    "groups",
                    "list",
                    "The groups of materials that cut alike.",
                    True,
                    of="material_group",
                ),
                SCField(
                    "materials",
                    "list",
                    "The materials, each in a group.",
                    True,
                    of="material",
                ),
            ),
            True,
            """\
name = "Materials"
kind = "materials"
language = "English"
version = "0.0.1"
carbide_speed_factor = "250 %"
cobalt_speed_factor = "110 %"

[end_milling]
plunge_factor = "50 %"

[[end_milling.chip_loads]]
below = "1/4 in"
chip_load = "0.001 in/tooth"

[drilling]

[[drilling.feed_ranges]]
below = "1/8 in"
feed = "0.002 in/rev"

[[groups]]
name = "soft"
hss_surface_speed = "250 sfm"
feed_factor = "150 %"

[[materials]]
name = "6061 aluminum"
group = "soft"
""",
        ),
        SCKind(
            "drilling",
            "How drills feed: the feed per revolution by drill diameter "
            "(the middle of the catalog ranges), times the group's "
            "`feed_factor`.",
            (
                SCField(
                    "feed_ranges",
                    "list",
                    "The feeds per revolution, smallest drills first.",
                    True,
                    of="feed_range",
                ),
            ),
            False,
            """\
[[feed_ranges]]
below = "1/8 in"
feed = "0.002 in/rev"
""",
        ),
        SCKind(
            "end_milling",
            "How end mills feed: the chip load by diameter, times the "
            "group's `feed_factor`, times the flutes and the RPM.",
            (
                SCField(
                    "plunge_factor",
                    "fraction",
                    "The plunge feed, as a share of the feed.",
                    True,
                ),
                SCField(
                    "chip_loads",
                    "list",
                    "The chip loads, smallest end mills first.",
                    True,
                    of="chip_load",
                ),
            ),
            False,
            """\
plunge_factor = "50 %"

[[chip_loads]]
below = "1/4 in"
chip_load = "0.001 in/tooth"
""",
        ),
        SCKind(
            "chip_load",
            "The chip load of end mills below a diameter.",
            (
                SCField(
                    "below",
                    "length",
                    "The end mills it is for are smaller than this.",
                    True,
                ),
                SCField(
                    "chip_load",
                    "chip_load",
                    "Their feed per tooth.",
                    True,
                ),
            ),
            False,
            """\
below = "1/4 in"
chip_load = "0.001 in/tooth"
""",
        ),
        SCKind(
            "feed_range",
            "The feed per revolution of drills below a diameter.",
            (
                SCField(
                    "below",
                    "length",
                    "The drills it is for are smaller than this.",
                    True,
                ),
                SCField(
                    "feed",
                    "feed_per_rev",
                    "Their feed per revolution.",
                    True,
                ),
            ),
            False,
            """\
below = "1/8 in"
feed = "0.002 in/rev"
""",
        ),
        SCKind(
            "material_group",
            "A group of materials that cut alike.",
            (
                SCField("description", "string", "What is in it."),
                SCField(
                    "hss_surface_speed",
                    "surface_speed",
                    "The surface speed of an HSS tool.",
                    True,
                ),
                SCField(
                    "feed_factor",
                    "fraction",
                    "The feed, as a share of `feed_ranges` and `chip_loads`.",
                    True,
                ),
            ),
            True,
            """\
name = "soft"
description = "Aluminum, brass, acetal"
hss_surface_speed = "250 sfm"
feed_factor = "150 %"
""",
        ),
        SCKind(
            "material",
            "A material the shop cuts.",
            (SCField("group", "string", "The group it cuts with.", True),),
            True,
            """\
name = "6061 aluminum"
group = "soft"
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

The number may be a decimal (`"0.5 in"`), a fraction (`"1/2 in"`), or
a whole number and a fraction joined by `-` (`"1-1/2 in"`).

{units}

### Keys and Problems

* Keys are `snake_case`.
* An unknown key is refused (a misspelled key is a mistake, not a
  comment).
* A choice (`"one of ..."` in the tables) may be written in any
  capitals (`"r8"` is `"R8"`).  Where a table says "or another ending
  in `!`", the list is only the common ones, and a value ending in
  `!` is taken without a check (`interface = "HSK100A!"`).
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


# Function `_measurement()`:
def _measurement(value: object, units: dict[str, float]) -> tuple[float, str]:
    """Return a measurement's value, or what is wrong with it.

    Arguments:
    * `value` (`object`): The value, from TOML.
    * `units` (`dict[str, float]`): The units it may be in.

    Returns:
    * (`tuple[float, str]`):
      Its value in the units used inside (as for `scmachine`) and
      `""`, or `0.0` and the problem.
    """
    # It must be a string, of a number and a unit.
    allowed: str = ", ".join(units)
    if units is MONEY:
        allowed += ", or any ISO 4217 code"
    if not isinstance(value, str):
        return 0.0, (
            f"{value!r} needs a unit, as a string such as "
            f'"{value} {next(iter(units))}" (it may be in {allowed})'
        )
    found: re.Match[str] | None = MEASUREMENT.fullmatch(value)
    if found is None:
        return 0.0, f"{value!r} is not a number and a unit"
    sign, whole, numerator, denominator, decimal, unit = found.groups()
    if units is MONEY and CURRENCY.fullmatch(unit):
        units = {unit: 1.0}
    if unit not in units:
        return 0.0, (
            f"{value!r}: {unit!r} is the wrong unit here "
            f"(it may be in {allowed})"
        )

    # Work out the number: a decimal, or a fraction.
    number: float
    if decimal is not None:
        number = float(decimal)
    elif int(denominator) == 0:
        return 0.0, f"{value!r} divides by zero"
    else:
        number = int(whole or "0") + int(numerator) / int(denominator)
    if sign == "-":
        number = -number
    return number * units[unit], ""


# Function `measurement_problem()`:
def measurement_problem(value: object, units: dict[str, float]) -> str:
    """Return what is wrong with a measurement, if anything.

    Arguments:
    * `value` (`object`): The value, from TOML.
    * `units` (`dict[str, float]`): The units it may be in.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    return _measurement(value, units)[1]


# Function `measure()`:
def measure(value: object, units: dict[str, float]) -> float:
    """Return a measurement in the units used inside.

    Arguments:
    * `value` (`object`): The value (such as `"1-1/2 in"`).
    * `units` (`dict[str, float]`): The units it may be in.

    Returns:
    * (`float`): Its value (inches, inches per minute, ...).

    Raises:
    * `ValueError`: If it is not a measurement in one of `units`.
    """
    number: float
    problem: str
    number, problem = _measurement(value, units)
    if problem:
        raise ValueError(problem)
    return number


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
    * `machine_tables` (`list[tuple[str, _Source, KeyPath, object]]`):
      Every machine's name, where its `tool_table` is, and the table.
    * `tool_uses` (`list[tuple[_Source, KeyPath, str]]`):
      Every tool named in a `tool_table`: where, and its name.
    * `tools` (`dict[str, tuple[_Source, KeyPath]]`):
      Every tool read, by name: where it is.

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
    machine_tables: list[tuple[str, _Source, KeyPath, object]] = field(
        init=False, default_factory=list
    )
    reading: list[Path] = field(init=False, default_factory=list)
    tool_uses: list[tuple[_Source, KeyPath, str]] = field(
        init=False, default_factory=list
    )
    tools: dict[str, tuple[_Source, KeyPath]] = field(
        init=False, default_factory=dict
    )

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

        # Note where each tool is, so `tool_table`s can name it, and
        # each machine's tool table, which no other machine may share.
        if kind.kind in TOOL_KINDS:
            self.name_tool(value.get("name"), path, source)
        elif kind.kind == "machine" and "tool_table" in contents:
            self.machine_tables.append(
                (
                    str(contents.get("name")),
                    source,
                    path + ("tool_table",),
                    contents["tool_table"],
                )
            )
        return contents

    # Method `_Reader.name_tool()`:
    def name_tool(self, name: object, path: KeyPath, source: _Source) -> None:
        """Note where a tool is, refusing a name already taken.

        Arguments:
        * `name` (`object`): Its `name` (checked already as a string).
        * `path` (`KeyPath`): Where the tool is.
        * `source` (`_Source`): The file it is in.
        """
        if not isinstance(name, str):
            return
        if name in self.tools:
            other: _Source
            where: KeyPath
            other, where = self.tools[name]
            line: int = locate(other.lines, where)
            self.problem(
                source,
                path + ("name",),
                f'"{name}" is also the name of the tool at '
                f"{other.shown}:{line}",
            )
        else:
            self.tools[name] = (source, path)

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
        if form == "by_material":
            if not isinstance(value, dict):
                self.problem(source, path, f"{value!r} is not a table")
                return {}
            return {
                material: self.table(
                    item, KINDS[schema.of], path + (material,), source
                )
                for material, item in value.items()
            }
        if form == "list":
            if not isinstance(value, list):
                self.problem(source, path, f"{value!r} is not a list")
                return []
            return [
                self.table(item, KINDS[schema.of], path + (index,), source)
                for index, item in enumerate(value)
            ]

        # Everything else is checked as it is; the tools a
        # `tool_table` names are checked once every file is read.
        problem: str = _scalar_problem(value, schema)
        if problem:
            self.problem(source, path, problem)
        elif form == "choice" and isinstance(value, str):
            value = _chosen(value, schema)
        elif form == "t_numbers" and isinstance(value, dict):
            for number, name in value.items():
                self.tool_uses.append((source, path + (number,), name))
        return value

    # Method `_Reader.check_tool_uses()`:
    def check_tool_uses(self) -> None:
        """Note every tool named in a tool table that was not read.

        A tool is in one machine at a time, so a tool named twice (in
        one tool table or two), and a tool table file named by two
        machines, are noted as well.
        """
        # Each tool table belongs to one machine.
        owners: dict[int, str] = {}
        for machine, source, path, table in self.machine_tables:
            if id(table) in owners:
                self.problem(
                    source,
                    path,
                    f'is also the tool table of "{owners[id(table)]}" '
                    "(a tool is in one machine at a time)",
                )
            else:
                owners[id(table)] = machine

        # Each tool named is a tool, and is named once.
        first: dict[str, tuple[_Source, KeyPath]] = {}
        for source, path, name in self.tool_uses:
            if name not in self.tools:
                self.problem(source, path, f'no tool named "{name}"')
            elif name in first:
                other: _Source
                where: KeyPath
                other, where = first[name]
                self.problem(
                    source,
                    path,
                    f'"{name}" is also loaded at {other.shown}:'
                    f"{locate(other.lines, where)} (a tool is in one "
                    "place at a time)",
                )
            else:
                first[name] = (source, path)


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
    elif form == "date":
        if not isinstance(value, datetime.date) or isinstance(
            value, datetime.datetime
        ):
            problem = f"{value!r} is not a date (such as 2026-10-27)"
    elif form == "t_numbers":
        problem = _t_numbers_problem(value)
    return problem


# Function `_chosen()`:
def _chosen(value: str, schema: SCField) -> str:
    """Return a choice as `schema` spells it.

    Arguments:
    * `value` (`str`): The choice, as written.
    * `schema` (`SCField`): The `"choice"` it must be.

    Returns:
    * (`str`):
      The choice as `choices` spells it, `value` itself if it ends in
      `!` and the list is open, or `""` if it is not a choice.
    """
    if schema.open and value.endswith("!"):
        return value
    return next((c for c in schema.choices if c.lower() == value.lower()), "")


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

    # A choice is one of its choices (whatever its capitals), or ends
    # in `!` if the list is open.
    if schema.form == "choice" and not _chosen(value, schema):
        also: str = ", or another ending in !" if schema.open else ""
        return (
            f'"{value}" is not one of '
            + ", ".join(f'"{choice}"' for choice in schema.choices)
            + also
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


# Function `_t_numbers_problem()`:
def _t_numbers_problem(value: object) -> str:
    """Return what is wrong with a table of T numbers to tool names.

    Arguments:
    * `value` (`object`): The value.

    Returns:
    * (`str`): The problem, or `""` if there is none.
    """
    if not isinstance(value, dict):
        return f"{value!r} is not a table of T numbers to tool names"
    numbers: set[int] = set()
    for number, name in value.items():
        if not number.isdigit() or not 1 <= int(number) <= 99:
            return f'"{number}" is not a T number (1 to 99)'
        if int(number) in numbers:
            return f"T{int(number)} is given twice"
        numbers.add(int(number))
        if not isinstance(name, str):
            return f"T{number}: {name!r} is not a tool name"
    return ""


# Function `read()`:
def read(file: Path) -> dict[str, object]:
    """Read and check a Nested TOML description.

    The tools named in tool tables are checked only when the top file
    is a `shop` or `shops`, which has the tools.

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
    # Read every file.
    reader: _Reader = _Reader(file.parent)
    contents: dict[str, object] | None = reader.file(file, file.as_posix())

    # A shop (or shops) has its tools, so its machines' tool tables
    # can be checked; a machine read alone can not be.
    if contents is not None and contents.get("kind") in ("shop", "shops"):
        reader.check_tool_uses()
    if reader.problems or contents is None:
        raise SCShopError(reader.problems)
    return contents


# Function `tool_number()`:
def tool_number(machine: dict[str, object], tool: str) -> int:
    """Return the T number of a tool loaded in a machine.

    Arguments:
    * `machine` (`dict[str, object]`): The machine, from `read()`.
    * `tool` (`str`): The tool's name.

    Returns:
    * (`int`): Its T number.

    Raises:
    * `ValueError`: If the tool is not loaded in the machine.
    """
    table: object = machine.get("tool_table", {})
    tools: object = table.get("tools", {}) if isinstance(table, dict) else {}
    if isinstance(tools, dict):
        for number, name in tools.items():
            if name == tool:
                return int(number)
    raise ValueError(f'"{tool}" is not loaded in "{machine.get("name")}"')


# Function `loaded_in()`:
def loaded_in(shop: dict[str, object], tool: str) -> tuple[str, int] | None:
    """Return which machine of a shop has a tool loaded, and where.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.
    * `tool` (`str`): The tool's name.

    Returns:
    * (`tuple[str, int] | None`):
      The machine's name and the tool's T number, or `None` if no
      machine has it loaded (a tool is in one machine at a time).
    """
    machines: object = shop.get("machines", [])
    for machine in machines if isinstance(machines, list) else []:
        try:
            return str(machine.get("name")), tool_number(machine, tool)
        except ValueError:
            continue
    return None


# The CNC kind of each list of tools in a `tools` file.
CNC_KINDS: dict[str, ToolKind] = {
    "end_mills": "end mill",
    "drills": "drill",
    "chamfer_mills": "chamfer",
    "corner_rounding_mills": "corner round",
    "double_angle_cutters": "double angle",
}


# Function `_machine()`:
def _machine(shop: dict[str, object], name: str) -> dict[str, object]:
    """Return a machine of a shop.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.
    * `name` (`str`): The machine's name.

    Returns:
    * (`dict[str, object]`): The machine, from `read()`.

    Raises:
    * `ValueError`: If the shop has no such machine.
    """
    machines: list[dict[str, object]] = cast(
        list[dict[str, object]], shop.get("machines", [])
    )
    machine: dict[str, object] | None = next(
        (m for m in machines if m.get("name") == name), None
    )
    if machine is None:
        raise ValueError(f'no machine named "{name}" in "{shop.get("name")}"')
    return machine


# Function `loaded_tools()`:
def loaded_tools(
    shop: dict[str, object], name: str
) -> dict[int, tuple[str, dict[str, object]]]:
    """Return the tools loaded in a machine of a shop, by T number.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.
    * `name` (`str`): The machine's name.

    Returns:
    * (`dict[int, tuple[str, dict[str, object]]]`): Each tool's list
      in the tools files (a key of `CNC_KINDS`, such as `"drills"`),
      and its description, from `read()`.

    Raises:
    * `ValueError`: If the shop has no such machine.
    """
    # Every tool of the shop, by name, with the list it is in.
    tools: dict[str, tuple[str, dict[str, object]]] = {}
    for tools_file in cast(list[dict[str, object]], shop.get("tools", [])):
        for key in CNC_KINDS:
            for tool in cast(list[dict[str, object]], tools_file.get(key, [])):
                tools[str(tool["name"])] = (key, tool)

    # The loaded tools, by T number.
    table: dict[str, object] = cast(
        dict[str, object],
        _machine(shop, name).get("tool_table", {"tools": {}}),
    )
    loaded: dict[str, str] = cast(dict[str, str], table["tools"])
    return {
        int(number): tools[tool_name] for number, tool_name in loaded.items()
    }


# Function `cnc_machine()`:
def cnc_machine(
    shop: dict[str, object], name: str, material: str = ""
) -> SCMachine:
    """Return a machine of a shop, with its loaded tools, for `SCCNC`.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.
    * `name` (`str`): The machine's name.
    * `material` (`str`):
      The material being cut, from which drills get their speeds and
      feeds (see `tool_cutting()`); needed if a drill is loaded.

    Returns:
    * (`SCMachine`): Its preferences and its tool table.

    Raises:
    * `ValueError`:
      If the shop has no such machine, the machine has no
      `preferences`, a loaded tool other than a drill has no `rpm`,
      `feed` or `plunge`, or a drill has no speed and feed for the
      material.
    """
    # Find the machine and its preferences.
    machine: dict[str, object] = _machine(shop, name)
    if "preferences" not in machine:
        raise ValueError(f'"{name}" has no preferences')
    preferences: dict[str, object] = cast(
        dict[str, object], machine["preferences"]
    )
    controller: dict[str, object] = cast(
        dict[str, object], machine["controller"]
    )

    # The loaded tools, with drill speeds and feeds for the material.
    tools: list[SCTool] = []
    for number, (key, tool) in loaded_tools(shop, name).items():
        if key in CUT_KEYS:
            if not material:
                raise ValueError(f'"{tool["name"]}" needs a material to cut')
            rpm: float
            feed: float
            plunge: float
            rpm, feed, plunge = tool_cutting(shop, machine, tool, material)
            tool = {
                **tool,
                "rpm": f"{rpm} rpm",
                "feed": f"{feed} in/min",
                "plunge": f"{plunge} in/min",
            }
        tools.append(_cnc_tool(number, CNC_KINDS[key], tool))

    # The machine, with its loaded tools.
    return SCMachine(
        name=name,
        z_safe=measure(preferences["z_safe"], LENGTH),
        clearance=measure(preferences["clearance"], LENGTH),
        tool_change_z=measure(preferences["tool_change_z"], LENGTH),
        tool_change=str(controller.get("tool_change", "T{number:02d}")),
        rapid_speed=measure(preferences["rapid_speed"], FEED),
        drill_cycle=cast(DrillCycle, preferences["drill_cycle"]),
        through_overcut=measure(preferences["through_overcut"], FRACTION),
        stepover=measure(preferences["stepover"], FRACTION),
        ramp_angle=measure(preferences["ramp_angle"], ANGLE),
        finish_allowance=measure(preferences["finish_allowance"], LENGTH),
        tools=tuple(tools),
    )


# The tool materials with speeds and feeds worked out from
# `materials`: their surface speed factor's key (`None` for HSS).
SPEED_FACTORS: dict[str, str | None] = {
    "HSS": None,
    "cobalt": "cobalt_speed_factor",
    "carbide": "carbide_speed_factor",
}

# The tool lists whose speeds and feeds come from `materials`.
CUT_KEYS: tuple[str, ...] = (
    "drills",
    "end_mills",
    "chamfer_mills",
    "corner_rounding_mills",
    "double_angle_cutters",
)


# Function `tool_cutting()`:
def tool_cutting(
    shop: dict[str, object],
    machine: dict[str, object],
    tool: dict[str, object],
    material: str,
) -> tuple[float, float, float]:
    """Return the speed and feeds of a tool in a material.

    The tool's own `cutting` entry for the material wins.  Otherwise,
    RPM = 12 SFM / (pi D), at its widest diameter D, held to the
    spindle's range.  A drill (one
    with a `point_angle`) feeds at the middle of
    the catalog range for D per revolution; an end mill at the chip
    load for D per tooth; both times the group's `feed_factor`, at the
    RPM actually used.  A feed (or plunge) faster than the axes can go
    is brought down to their limit, with the RPM brought down with it,
    so the chip load stays the same.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.
    * `machine` (`dict[str, object]`): The machine it is in.
    * `tool` (`dict[str, object]`): The tool, from `read()`.
    * `material` (`str`): The material being cut.

    Returns:
    * (`tuple[float, float, float]`):
      The RPM, the feed and the plunge feed (in/min).

    Raises:
    * `ValueError`:
      If the shop has no `materials`, the material is not one of them,
      the tool has no `cutting` entry for it and is not HSS, cobalt or
      carbide, or it is larger than every range.
    """
    # Find the material, and the tool's own entry for it.
    materials: dict[str, Any] = _materials(shop)
    found: dict[str, Any] = _material(materials, material)
    drill: bool = "point_angle" in tool
    own: tuple[float, float, float] | None = _own_cutting(
        tool, str(found["name"]), drill, materials
    )
    if own is not None:
        return own
    if tool["material"] not in SPEED_FACTORS:
        raise ValueError(
            f'"{tool["name"]}" needs a `cutting."{found["name"]}"` '
            "entry (its `rpm` and `feed`)"
        )
    group: dict[str, Any] = next(
        entry
        for entry in materials["groups"]
        if entry["name"] == found["group"]
    )

    # The speed, held to the spindle's range.
    diameter: float = _widest(tool)
    surface_speed: float = measure(group["hss_surface_speed"], SURFACE_SPEED)
    factor_key: str | None = SPEED_FACTORS[str(tool["material"])]
    if factor_key is not None:
        surface_speed *= measure(materials[factor_key], FRACTION)
    spindle: dict[str, Any] = cast(dict[str, Any], machine["spindle"])
    rpm: float = 12.0 * surface_speed / (math.pi * diameter)
    rpm = min(rpm, measure(spindle["max_rpm"], SPEED))
    rpm = max(rpm, measure(spindle.get("min_rpm", "0 rpm"), SPEED))

    # The feed, at the RPM actually used.
    feed: float = (
        rpm
        * _per_rev(tool, diameter, drill, materials)
        * measure(group["feed_factor"], FRACTION)
    )
    return _axis_limited(machine, rpm, feed, _plunge(feed, drill, materials))


# Function `_widest()`:
def _widest(tool: dict[str, object]) -> float:
    """Return a tool's widest cutting diameter.

    Arguments:
    * `tool` (`dict[str, object]`): The tool, from `read()`.

    Returns:
    * (`float`):
      Its `diameter`, or for a corner rounding mill (which has none)
      its tip diameter plus twice its radius (inches).
    """
    if "diameter" in tool:
        return measure(tool["diameter"], LENGTH)
    return measure(tool["tip_diameter"], LENGTH) + 2.0 * measure(
        tool["radius"], LENGTH
    )


# Function `_axis_limited()`:
def _axis_limited(
    machine: dict[str, object], rpm: float, feed: float, plunge: float
) -> tuple[float, float, float]:
    """Return a speed and feeds brought down to what the axes can do.

    Arguments:
    * `machine` (`dict[str, object]`): The machine.
    * `rpm` (`float`): The spindle speed.
    * `feed` (`float`): The feed in X and Y (in/min).
    * `plunge` (`float`): The feed down in Z (in/min).

    Returns:
    * (`tuple[float, float, float]`):
      The RPM, feed and plunge, all scaled down by the same share if
      the feed is faster than the slower of X and Y, or the plunge
      faster than Z (so the chip load stays the same).
    """
    # The axes' top feeds; a missing axis sets no limit.
    limits: dict[str, float] = {
        str(axis["letter"]): measure(axis["max_feed"], FEED)
        for axis in cast(list[dict[str, Any]], machine.get("axes", []))
        if "max_feed" in axis
    }
    xy: float = min(limits.get("X", math.inf), limits.get("Y", math.inf))
    scale: float = min(1.0, xy / feed, limits.get("Z", math.inf) / plunge)
    return rpm * scale, feed * scale, plunge * scale


# Function `_per_rev()`:
def _per_rev(
    tool: dict[str, object],
    diameter: float,
    drill: bool,
    materials: dict[str, Any],
) -> float:
    """Return a tool's feed per revolution, before the group's factor.

    Arguments:
    * `tool` (`dict[str, object]`): The tool, from `read()`.
    * `diameter` (`float`): Its diameter (inches).
    * `drill` (`bool`): True for a drill (else an end mill).
    * `materials` (`dict[str, Any]`): The shop's `materials`.

    Returns:
    * (`float`):
      A drill's feed per revolution, or an end mill's chip load times
      its flutes, from the first range it is in (inches).

    Raises:
    * `ValueError`: If it is larger than every range.
    """
    # A drill feeds per revolution, an end mill per tooth.
    key: str = "feed_ranges" if drill else "chip_loads"
    table: str = "drilling" if drill else "end_milling"
    for entry in materials[table][key]:
        if diameter < measure(entry["below"], LENGTH):
            if drill:
                return measure(entry["feed"], FEED_PER_REV)
            return measure(entry["chip_load"], CHIP_LOAD) * int(
                cast(int, tool.get("flutes", 2))
            )
    raise ValueError(f'"{tool["name"]}" is larger than every `{key}`')


# Function `_materials()`:
def _materials(shop: dict[str, object]) -> dict[str, Any]:
    """Return a shop's `materials`.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `read()`.

    Returns:
    * (`dict[str, Any]`): Its `materials`.

    Raises:
    * `ValueError`: If it has none.
    """
    if "materials" not in shop:
        raise ValueError("the shop has no `materials`")
    return cast(dict[str, Any], shop["materials"])


# Function `_material()`:
def _material(materials: dict[str, Any], material: str) -> dict[str, Any]:
    """Return a material, whatever its capitals.

    Arguments:
    * `materials` (`dict[str, Any]`): The shop's `materials`.
    * `material` (`str`): The material's name.

    Returns:
    * (`dict[str, Any]`): The material.

    Raises:
    * `ValueError`: If it is not one of them (listing them).
    """
    for entry in materials["materials"]:
        if str(entry["name"]).lower() == material.lower():
            return cast(dict[str, Any], entry)
    known: str = ", ".join(
        str(entry["name"]) for entry in materials["materials"]
    )
    raise ValueError(f'"{material}" is not one of: {known}')


# Function `_plunge()`:
def _plunge(feed: float, drill: bool, materials: dict[str, Any]) -> float:
    """Return the plunge feed for a feed.

    Arguments:
    * `feed` (`float`): The feed (in/min).
    * `drill` (`bool`): True for a drill, which plunges at its feed.
    * `materials` (`dict[str, Any]`): The shop's `materials`.

    Returns:
    * (`float`): The plunge feed (in/min).
    """
    if drill:
        return feed
    return feed * measure(materials["end_milling"]["plunge_factor"], FRACTION)


# Function `_own_cutting()`:
def _own_cutting(
    tool: dict[str, object],
    material: str,
    drill: bool,
    materials: dict[str, Any],
) -> tuple[float, float, float] | None:
    """Return a tool's own speed and feeds for a material, if it has them.

    Arguments:
    * `tool` (`dict[str, object]`): The tool, from `read()`.
    * `material` (`str`): The material, as the shop names it.
    * `drill` (`bool`): True for a drill.
    * `materials` (`dict[str, Any]`): The shop's `materials`.

    Returns:
    * (`tuple[float, float, float] | None`):
      The RPM, the feed and the plunge feed (in/min), or `None` if it
      has none.
    """
    # Material names match whatever their capitals.
    cutting: dict[str, Any] = cast(dict[str, Any], tool.get("cutting", {}))
    for key, entry in cutting.items():
        if key.lower() == material.lower():
            feed: float = measure(entry["feed"], FEED)
            plunge: float = (
                measure(entry["plunge"], FEED)
                if "plunge" in entry
                else _plunge(feed, drill, materials)
            )
            return measure(entry["rpm"], SPEED), feed, plunge
    return None


# Function `_cnc_tool()`:
def _cnc_tool(number: int, kind: ToolKind, tool: dict[str, object]) -> SCTool:
    """Return a loaded tool, for `SCCNC`.

    Arguments:
    * `number` (`int`): Its T number.
    * `kind` (`ToolKind`): Its CNC kind (from the list it is in).
    * `tool` (`dict[str, object]`): The tool, from `read()`.

    Returns:
    * (`SCTool`): The tool.

    Raises:
    * `ValueError`:
      If it has no `rpm`, `feed` or `plunge`.
    """
    # How to cut with it must be given, for now (a drill's comes from
    # `tool_cutting()`).
    name: str = str(tool["name"])
    for key in ("rpm", "feed", "plunge"):
        if key not in tool:
            raise ValueError(f'"{name}" has no `{key}` to cut with')

    # A bit that cuts along an edge is placed by its tip.
    if kind == "end mill" and tool.get("end") == "ball":
        kind = "ball end mill"
    elif kind == "end mill" and tool.get("roughing") is True:
        kind = "roughing end mill"
    diameter: object = tool.get("tip_diameter", tool.get("diameter"))
    return SCTool(
        number=number,
        name=name,
        kind=kind,
        diameter=measure(diameter, LENGTH),
        rpm=measure(tool["rpm"], SPEED),
        feed=measure(tool["feed"], FEED),
        plunge=measure(tool["plunge"], FEED),
        peck=measure(tool.get("peck_depth", "0 in"), LENGTH),
        angle=measure(tool.get("angle", "0 deg"), ANGLE),
        radius=measure(tool.get("radius", "0 in"), LENGTH),
    )


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
        if table is MONEY:
            shown += ", or any ISO 4217 code"
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
            print(json.dumps(contents, indent=2, default=str))
        else:
            print(f"{file.as_posix()}: OK")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
