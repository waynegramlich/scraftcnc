# Shops: The Shop Description Files

This document is written by `shops.py` (`./shops.py markdown >
Shops.md`) from the schema that its reader checks files against; a
change is made there, never here.

A shop is described in Nested TOML files: what machines it has (and,
to come, the tools that cut, the tooling that holds the material, and
the materials it cuts).  This document describes every kind of file a
shop can refer to, not only the shop file itself, since a file can
stand alone and be shared by several machines or shops.

This document describes format version `0.0.1`, the version every
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

| Key        | Value   | Required | Meaning                                  |
| ---------- | ------- | -------- | ---------------------------------------- |
| `name`     | string  | yes      | Unique among the things of its kind.     |
| `kind`     | string  | yes      | What the rest of the file is.            |
| `language` | string  | yes      | The language of the names and notes.     |
| `version`  | version | yes      | The format version, `MAJOR.MINOR.PATCH`. |

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

| Measurement  | Units                                     |
| ------------ | ----------------------------------------- |
| length       | `in`, `inch`, `inches`, `ft`, `mm`, `cm`  |
| feed         | `in/min`, `ipm`, `in/s`, `mm/min`, `mm/s` |
| acceleration | `in/s^2`, `mm/s^2`                        |
| speed        | `rpm`                                     |
| angle        | `deg`                                     |
| rotary feed  | `deg/min`, `deg/s`                        |
| fraction     | `%`                                       |

### Keys and Problems

* Keys are `snake_case`.
* An unknown key is refused (a misspelled key is a mistake, not a
  comment).
* Every problem is reported with its file, line and key, e.g.
  `shop_mill.toml:12: spindle.max_rpm: "5000" needs a unit`.  Every
  problem found is reported, not only the first.

## `shop`

A shop: its name, where it is, and its machines.  It has a `name` even
when it is not a file of its own.

| Key        | Value             | Required | Meaning                   |
| ---------- | ----------------- | -------- | ------------------------- |
| `location` | `location`        | no       | Where the shop is.        |
| `machines` | list of `machine` | yes      | The machines in the shop. |

```toml
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
machines = ["@shop_mill.toml"]

[location]
latitude = "37.37066 deg"
longitude = "-122.04002 deg"
address = "700 All American Way, Sunnyvale, CA 94086"
```

## `location`

Where a shop is.  Every key is optional, since a shop on a boat may have
none.

| Key         | Value  | Required | Meaning             |
| ----------- | ------ | -------- | ------------------- |
| `latitude`  | angle  | no       | North is positive.  |
| `longitude` | angle  | no       | East is positive.   |
| `address`   | string | no       | The street address. |

```toml
latitude = "37.37066 deg"
longitude = "-122.04002 deg"
address = "700 All American Way, Sunnyvale, CA 94086"
```

## `machine`

A CNC mill or router (lathes, lasers and 3D printers later): its axes,
table, spindle, controller and tool table.  It has a `name` even when it
is not a file of its own.

| Key          | Value                   | Required | Meaning                 |
| ------------ | ----------------------- | -------- | ----------------------- |
| `machine`    | one of `mill`, `router` | yes      | What sort of machine it |
|              |                         |          | is.                     |
| `axes`       | list of `axis`          | yes      | One per axis.           |
| `table`      | `machine_table`         | no       | The table that the work |
|              |                         |          | is held on.             |
| `spindle`    | `spindle`               | yes      | The spindle.            |
| `controller` | `controller`            | yes      | The controller.         |
| `tool_table` | T number to tool name   | no       | The tools loaded, by T  |
|              |                         |          | number (1 to 99).       |

```toml
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
```

## `axis`

One linear axis of a machine (rotary axes later).

| Key                | Value                | Required | Meaning              |
| ------------------ | -------------------- | -------- | -------------------- |
| `letter`           | one of `X`, `Y`, `Z` | yes      | Its letter in        |
|                    |                      |          | G-code.              |
| `travel`           | length               | yes      | How far it moves.    |
| `max_feed`         | feed                 | yes      | Its fastest feed.    |
| `max_acceleration` | acceleration         | no       | Its greatest         |
|                    |                      |          | acceleration.        |
| `limit_switches`   | boolean              | no       | True if it has end   |
|                    |                      |          | of travel switches.  |
| `brake`            | boolean              | no       | True if it has a     |
|                    |                      |          | brake.               |

```toml
letter = "Z"
travel = "16 in"
max_feed = "90 in/min"
max_acceleration = "10 in/s^2"
limit_switches = true
brake = false
```

## `machine_table`

The table of a machine, and its T-slots.

| Key            | Value   | Required | Meaning             |
| -------------- | ------- | -------- | ------------------- |
| `length`       | length  | yes      | Along X.            |
| `width`        | length  | yes      | Along Y.            |
| `t_slots`      | integer | no       | How many T-slots.   |
| `t_slot_pitch` | length  | no       | Between T-slots.    |
| `t_slot_width` | length  | no       | At the top.         |
| `t_slot_depth` | length  | no       | From the table top. |

```toml
length = "34 in"
width = "9.5 in"
t_slots = 3
t_slot_pitch = "2.5 in"
t_slot_width = "0.625 in"
t_slot_depth = "0.75 in"
```

## `spindle`

The spindle of a machine.

| Key          | Value   | Required | Meaning                         |
| ------------ | ------- | -------- | ------------------------------- |
| `taper`      | string  | no       | Its taper (`R8`, `CAT40`, ...). |
| `min_rpm`    | speed   | no       | Its slowest speed.              |
| `max_rpm`    | speed   | yes      | Its fastest speed.              |
| `reversible` | boolean | no       | True if it runs backwards.      |
| `flood`      | boolean | no       | True if it has flood coolant.   |
| `mist`       | boolean | no       | True if it has mist coolant.    |
| `air`        | boolean | no       | True if it has an air blast.    |

```toml
taper = "R8"
min_rpm = "100 rpm"
max_rpm = "5000 rpm"
reversible = true
flood = true
mist = false
air = false
```

## `controller`

The controller of a machine (e.g. LinuxCNC), and how its G-code is
written.  LinuxCNC is the baseline.  (To come: every code it accepts,
its canned cycles, and tool length offsets.)  `tool_change` is a Python
`str.format()` template, filled in with the tool's `number`.  It has a
`name` even when it is not a file of its own.

| Key              | Value             | Required | Meaning                   |
| ---------------- | ----------------- | -------- | ------------------------- |
| `post_processor` | one of `linuxcnc` | yes      | Which dialect of G-code   |
|                  |                   |          | it reads.                 |
| `tool_change`    | string            | no       | The words that change the |
|                  |                   |          | tool.                     |

```toml
name = "LinuxCNC"
kind = "controller"
language = "English"
version = "0.0.1"
post_processor = "linuxcnc"
tool_change = "T{number:02d} M6"
```
