# Shops: The Shop Description Files

A shop is described in Nested TOML files: what machines it has, the
tools that cut, the tooling that holds the material, and the materials
it cuts.  This document describes every kind of file a shop can refer
to, not only the shop file itself, since a tools or materials file can
stand alone and be shared by several machines or shops.

This document describes format version `0.0.1`, the version every
file carries in its `version` key.  A change to the format changes
this document and the version together.

## Nested TOML

A Nested TOML description is kept in more than one `.toml` file.  The
reader reads them all and splices them together into one data
structure (JSON style dictionaries, lists, strings, numbers and
booleans), which the CNC side uses without knowing how the files were
split.

### The Header Keys

Every file starts with the same four keys:

```toml
name = "Home shop"
kind = "shop"           # Or "machine", "tools", "tooling", ...
language = "English"    # Of the names and notes in the file.
version = "0.0.1"       # The file format's version (semantic).
```

* `name`: unique among the things of its kind, since things refer to
  each other by name.
* `kind`: what the rest of the file is (one of the sections below), so
  the reader knows which keys to expect.
* `language`: the language of the names and notes in the file.
* `version`: the format version, `MAJOR.MINOR.PATCH`.  The reader
  refuses a major version it does not know, and a newer minor version
  than its own.

### Joining Files with `@`

A string `"@FILE_NAME"` stands for the contents of that file, in any
place that takes a table or a list of them:

```toml
machines = ["@shop_mill.toml", "@router.toml"]
```

* The file must be in the same directory as the file that names it (a
  bare file name, with no `/`).
* Its `kind` must fit where it is named (a `tools` file can not go in
  `machines`).
* A file is read once, however often it is named; its contents are
  spliced in at every place that names it.
* A missing file, and a loop (a file that names itself, directly or
  not), are refused.

### Units

Every measurement is a string with its unit (`"0.25 in"`, `"12
in/min"`); a bare number is refused, and so is a unit of the wrong
kind (a feed where a length belongs).  Plain counts (the number of
T-slots) and yes/no facts (`true`/`false`) have no unit.

| Kind | Units |
| --- | --- |
| Length | `in`, `inch`, `inches`, `ft`, `mm`, `cm` |
| Feed | `in/min`, `ipm`, `in/s`, `mm/min`, `mm/s` |
| Acceleration | `in/s^2`, `mm/s^2` |
| Speed | `rpm` |
| Angle | `deg` |
| Rotary feed | `deg/min` |
| Fraction | `%` |

### Keys and Errors

* Keys are `snake_case` (still to be confirmed: `T.si~2.1` #0).
* An unknown key is refused (a misspelled key is a mistake, not a
  comment).
* Every problem names the file and the entry, e.g. `shop_mill.toml:
  tool_table.4: no tool named "15/64 drill"`.

## `shop`

A shop: its name, where it is, and its machines.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `location` | table | no | Where the shop is (below). |
| `machines` | list of `machine` | yes | The machines in the shop. |
| `tools` | list of `tools` | no | The tools on hand. |
| `tooling` | list of `tooling` | no | The work holding on hand. |
| `materials` | list of `materials` | no | The materials on hand. |

`location` (every key optional; a shop on a boat may have none):

| Key | Type | Meaning |
| --- | --- | --- |
| `latitude` | angle | |
| `longitude` | angle | |
| `address` | string | One string, or separate lines (`T.si~2.1` #3). |

```toml
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
location = { latitude = "37.37066 deg", longitude = "-122.04002 deg",
             address = "700 All American Way, Sunnyvale, CA 94086" }
machines = ["@shop_mill.toml"]
tools = ["@end_mills.toml", "@drills.toml"]
```

## `machine`

A CNC mill or router (lathes, lasers and 3D printers later): its axes,
table, spindle, controller and tool table.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `machine` | string | yes | `"mill"` or `"router"`. |
| `axes` | list of tables | yes | One per axis (below). |
| `table` | table | no | The table and its T-slots. |
| `spindle` | table | yes | Taper, RPM range, coolant. |
| `controller` | `controller` | yes | The controller (its own section). |
| `tool_table` | table | no | T number to tool name. |

TODO: the keys of an axis (letter, linear or rotary, travel, maximum
feed, acceleration, limit switches, brake), the table (length, width,
T-slots: count, pitch, width, depth) and the spindle (taper, minimum
and maximum RPM, reversible, flood, mist, air).

```toml
name = "Shop mill"
kind = "machine"
language = "English"
version = "0.0.1"
machine = "mill"
spindle = { taper = "R8", max_rpm = "5000 rpm" }
controller = "@linuxcnc.toml"
tool_table = { 1 = "1/4 inch 2 flute end mill", 4 = "15/64 inch drill" }
```

## `controller`

The controller (e.g. LinuxCNC): the G-code dialect it reads, and every
code (G, M, ...) it accepts, since not all controllers accept all of
them.  LinuxCNC is the baseline.

TODO: the codes accepted, canned cycles, how a tool change is written
(`tool_change` in `machine.toml` today), tool length offsets.

## `tools`

Tools go in the spindle and cut the material.  A tools file may be
shared by several machines; each machine's `tool_table` gives the T
numbers of the ones it uses.

TODO: the families (flat end mill, ball nose, bull nose, chamfer and
V-bit, drill, corner rounding, dovetail, roughing, ...) and their
dimensions (cutting diameter, flutes, length of cut, overall length,
shank diameter, center cutting, coating, tool material).

## `tooling`

Tooling holds the material in place.

TODO: vises (jaw width, opening, height), parallels, tooling plates
(size, grid of screw holes, thread), clamps and hold downs (where they
sit, how tall they are).

## `materials`

The materials that are cut (6061 aluminum, acrylic, ...).

TODO: stock sizes and thicknesses on hand, and cutting data (surface
speed and chip load per tool material and diameter).
