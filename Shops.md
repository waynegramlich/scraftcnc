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

The number may be a decimal (`"0.5 in"`), a fraction (`"1/2 in"`), or
a whole number and a fraction joined by `-` (`"1-1/2 in"`).

| Measurement   | Units                                            |
| ------------- | ------------------------------------------------ |
| length        | `in`, `inch`, `inches`, `ft`, `mm`, `cm`         |
| feed          | `in/min`, `ipm`, `in/s`, `mm/min`, `mm/s`        |
| acceleration  | `in/s^2`, `mm/s^2`                               |
| speed         | `rpm`                                            |
| angle         | `deg`                                            |
| rotary feed   | `deg/min`, `deg/s`                               |
| surface speed | `sfm`, `ft/min`, `m/min`                         |
| feed per rev  | `in/rev`, `ipr`, `mm/rev`                        |
| chip load     | `in/tooth`, `ipt`, `mm/tooth`                    |
| fraction      | `%`                                              |
| money         | `USD`, `CAD`, `EUR`, `GBP`, or any ISO 4217 code |

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

## `shops`

Every shop: the top of a description.  Each shop may be written in
place, or kept in its own file.  It has a `name` even when it is not a
file of its own.

| Key     | Value          | Required | Meaning    |
| ------- | -------------- | -------- | ---------- |
| `shops` | list of `shop` | yes      | The shops. |

```toml
name = "Example shops"
kind = "shops"
language = "English"
version = "0.0.1"
shops = ["@home_shop.toml"]
```

## `shop`

A shop: its name, where it is, its machines and its tools.  It has a
`name` even when it is not a file of its own.

| Key         | Value             | Required | Meaning                        |
| ----------- | ----------------- | -------- | ------------------------------ |
| `location`  | `location`        | no       | Where the shop is.             |
| `machines`  | list of `machine` | yes      | The machines in the shop.      |
| `tools`     | list of `tools`   | no       | The tools on hand, shared by   |
|             |                   |          | the machines.                  |
| `materials` | `materials`       | no       | The materials it cuts, and how |
|             |                   |          | to drill them.                 |

```toml
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

| Key           | Value                  | Required | Meaning                 |
| ------------- | ---------------------- | -------- | ----------------------- |
| `machine`     | one of `mill`,         | yes      | What sort of machine it |
|               | `router`               |          | is.                     |
| `axes`        | list of `axis`         | yes      | One per axis.           |
| `table`       | `machine_table`        | no       | The table that the work |
|               |                        |          | is held on.             |
| `spindle`     | `spindle`              | yes      | The spindle.            |
| `controller`  | `controller`           | yes      | The controller.         |
| `tool_table`  | `tool_table`           | no       | The tools loaded.       |
| `preferences` | `preferences`          | no       | How it is run.          |

```toml
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

| Key          | Value                   | Required | Meaning                 |
| ------------ | ----------------------- | -------- | ----------------------- |
| `interface`  | one of `R8`, `BT30`,    | yes      | What its tool holders   |
|              | `BT40`, `BT50`,         |          | fit.                    |
|              | `CAT30`, `CAT40`,       |          |                         |
|              | `CAT50`, `NMTB30`,      |          |                         |
|              | `NMTB40`, `HSK63A`,     |          |                         |
|              | `ER11`, `ER16`, `ER20`, |          |                         |
|              | `ER25`, `ER32`, `ER40`, |          |                         |
|              | or another ending in    |          |                         |
|              | `!`                     |          |                         |
| `min_rpm`    | speed                   | no       | Its slowest speed.      |
| `max_rpm`    | speed                   | yes      | Its fastest speed.      |
| `reversible` | boolean                 | no       | True if it runs         |
|              |                         |          | backwards.              |
| `flood`      | boolean                 | no       | True if it has flood    |
|              |                         |          | coolant.                |
| `mist`       | boolean                 | no       | True if it has mist     |
|              |                         |          | coolant.                |
| `air`        | boolean                 | no       | True if it has an air   |
|              |                         |          | blast.                  |

```toml
interface = "R8"
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

## `preferences`

How a machine is run: heights, speeds and how pockets and holes are cut.
(These are kept with the machine for now; some may belong to the shop or
to the job.)

| Key                | Value                | Required | Meaning              |
| ------------------ | -------------------- | -------- | -------------------- |
| `z_safe`           | length               | yes      | Above all of the     |
|                    |                      |          | hold down tooling.   |
| `clearance`        | length               | yes      | Rapids down stop     |
|                    |                      |          | this far above the   |
|                    |                      |          | work.                |
| `tool_change_z`    | length               | yes      | Rise here before     |
|                    |                      |          | every tool change.   |
| `rapid_speed`      | feed                 | yes      | The rapid speed, for |
|                    |                      |          | estimating run       |
|                    |                      |          | times.               |
| `drill_cycle`      | one of `G81`, `G73`, | yes      | How holes are        |
|                    | `G83`, `moves`       |          | drilled (`moves`: no |
|                    |                      |          | canned cycle).       |
| `through_overcut`  | fraction             | yes      | How much deeper a    |
|                    |                      |          | cut through the part |
|                    |                      |          | goes, of its         |
|                    |                      |          | thickness.           |
| `stepover`         | fraction             | yes      | How far apart pocket |
|                    |                      |          | rings are, of the    |
|                    |                      |          | tool's diameter.     |
| `ramp_angle`       | angle                | yes      | The steepest ramp    |
|                    |                      |          | into a pocket that   |
|                    |                      |          | is not drilled.      |
| `finish_allowance` | length               | yes      | What a roughing end  |
|                    |                      |          | mill leaves on walls |
|                    |                      |          | and floors for the   |
|                    |                      |          | end mill that        |
|                    |                      |          | finishes them.       |

```toml
z_safe = "1 in"
clearance = "0.05 in"
tool_change_z = "2 in"
rapid_speed = "60 in/min"
drill_cycle = "G83"
through_overcut = "10 %"
stepover = "90 %"
ramp_angle = "3 deg"
finish_allowance = "0.05 in"
```

## `tool_table`

The tools loaded in one machine: T numbers (1 to 99) and the names of
the tools in them.  Each is unique: no T number twice, and no tool
twice, here or in any other machine's tool table (a tool is in one
machine at a time).  Tools are loaded and unloaded far more often than a
machine changes, so the tool table is usually a file of its own.  It has
a `name` even when it is not a file of its own.

| Key     | Value                 | Required | Meaning                 |
| ------- | --------------------- | -------- | ----------------------- |
| `tools` | T number to tool name | yes      | The tools, by T number. |

```toml
name = "Shop mill tools"
kind = "tool_table"
language = "English"
version = "0.0.1"

[tools]
1 = "1/4 in 2 flute carbide end mill"
4 = "15/64 in HSS jobber drill"
```

## `tools`

Tools: the bits that go in a holder in the spindle.  How to cut with
each (`rpm`, `feed`, `plunge`) is given with the tool for now, until it
can be worked out from the material being cut.  Only the bits are
described, not their holders (a drill goes in a collet; an end mill in a
collet or an end mill holder of its shank's size).  Tools are shared by
machines, so they are not listed by machine: a machine's `tool_table`
names the ones it has loaded, and every tool's `name` is unique among
all the tools (T numbers are only unique within one machine).  It has a
`name` even when it is not a file of its own.

| Key                     | Value                  | Required | Meaning       |
| ----------------------- | ---------------------- | -------- | ------------- |
| `end_mills`             | list of `end_mill`     | no       | The end       |
|                         |                        |          | mills.        |
| `drills`                | list of `drill`        | no       | The drills.   |
| `chamfer_mills`         | list of `chamfer_mill` | no       | The chamfer   |
|                         |                        |          | mills.        |
| `corner_rounding_mills` | list of                | no       | The corner    |
|                         | `corner_rounding_mill` |          | rounding      |
|                         |                        |          | mills.        |
| `double_angle_cutters`  | list of                | no       | The double    |
|                         | `double_angle_cutter`  |          | angle shank   |
|                         |                        |          | cutters.      |

```toml
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
```

## `end_mill`

An end mill: square, ball or bull nose (a square end with rounded
corners), and perhaps a rougher.  It has a `name` even when it is not a
file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `length_of_cut`   | length               | yes      | How deep it can cut   |
|                   |                      |          | (LOC).                |
| `flutes`          | integer              | yes      | How many flutes.      |
| `end`             | one of `square`,     | yes      | The shape of its end. |
|                   | `ball`, `bull_nose`  |          |                       |
| `corner_radius`   | length               | no       | A bull nose's         |
|                   |                      |          | corners.              |
| `center_cutting`  | boolean              | no       | True if it can plunge |
|                   |                      |          | straight down.        |
| `roughing`        | boolean              | no       | True for a rougher    |
|                   |                      |          | (serrated flutes).    |
| `collet`          | one of `ER8`,        | no       | The collet it is held |
|                   | `ER11`, `ER16`,      |          | in, if it is.         |
|                   | `ER20`, `ER25`,      |          |                       |
|                   | `ER32`, `ER40`,      |          |                       |
|                   | `ER50`, `R8`, `5C`,  |          |                       |
|                   | or another ending in |          |                       |
|                   | `!`                  |          |                       |
| `cutting`         | material name to     | no       | Its own speed and     |
|                   | `cutting`            |          | feed for a material,  |
|                   |                      |          | which win over those  |
|                   |                      |          | worked out from       |
|                   |                      |          | `materials` (and are  |
|                   |                      |          | needed for a tool     |
|                   |                      |          | that is not HSS,      |
|                   |                      |          | cobalt or carbide).   |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `coating`         | string               | no       | Its coating or finish |
|                   |                      |          | (`AlTiN`, ...).       |
| `manufacturer`    | string               | no       | Who made it.          |
| `manufacturer_pn` | string               | no       | The maker's part      |
|                   |                      |          | number.               |
| `vendor`          | string               | no       | Who sold it.          |
| `vendor_pn`       | string               | no       | The vendor's part     |
|                   |                      |          | number.               |
| `cost`            | money                | no       | What it cost.         |
| `acquired`        | date                 | no       | When it was bought    |
|                   |                      |          | (`2026-10-27`).       |
| `rpm`             | speed                | no       | The spindle speed to  |
|                   |                      |          | cut at.               |
| `feed`            | feed                 | no       | The feed to cut at.   |
| `plunge`          | feed                 | no       | The feed going        |
|                   |                      |          | straight down.        |

```toml
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
```

## `drill`

A twist drill.  It has a `name` even when it is not a file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `length_of_cut`   | length               | yes      | How deep it can cut   |
|                   |                      |          | (LOC).                |
| `flutes`          | integer              | no       | How many flutes (2 if |
|                   |                      |          | not given).           |
| `point_angle`     | angle                | yes      | The included angle.   |
| `collet`          | one of `ER8`,        | yes      | The collet it is held |
|                   | `ER11`, `ER16`,      |          | in, if it is.         |
|                   | `ER20`, `ER25`,      |          |                       |
|                   | `ER32`, `ER40`,      |          |                       |
|                   | `ER50`, `R8`, `5C`,  |          |                       |
|                   | or another ending in |          |                       |
|                   | `!`                  |          |                       |
| `split_point`     | boolean              | no       | True if it has a      |
|                   |                      |          | split point.          |
| `peck_depth`      | length               | no       | How deep each peck    |
|                   |                      |          | goes (0 for none).    |
| `cutting`         | material name to     | no       | Its own speed and     |
|                   | `cutting`            |          | feed for a material,  |
|                   |                      |          | which win over those  |
|                   |                      |          | worked out from       |
|                   |                      |          | `materials` (and are  |
|                   |                      |          | needed for a tool     |
|                   |                      |          | that is not HSS,      |
|                   |                      |          | cobalt or carbide).   |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `coating`         | string               | no       | Its coating or finish |
|                   |                      |          | (`AlTiN`, ...).       |
| `manufacturer`    | string               | no       | Who made it.          |
| `manufacturer_pn` | string               | no       | The maker's part      |
|                   |                      |          | number.               |
| `vendor`          | string               | no       | Who sold it.          |
| `vendor_pn`       | string               | no       | The vendor's part     |
|                   |                      |          | number.               |
| `cost`            | money                | no       | What it cost.         |
| `acquired`        | date                 | no       | When it was bought    |
|                   |                      |          | (`2026-10-27`).       |
| `rpm`             | speed                | no       | The spindle speed to  |
|                   |                      |          | cut at.               |
| `feed`            | feed                 | no       | The feed to cut at.   |
| `plunge`          | feed                 | no       | The feed going        |
|                   |                      |          | straight down.        |

```toml
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
```

## `cutting`

A tool's own speed and feed for one material.

| Key      | Value | Required | Meaning                                       |
| -------- | ----- | -------- | --------------------------------------------- |
| `rpm`    | speed | yes      | The spindle speed.                            |
| `feed`   | feed  | yes      | The feed.                                     |
| `plunge` | feed  | no       | The feed going straight down (a drill's       |
|          |       |          | `feed`, or an end mill's `feed` times         |
|          |       |          | `plunge_factor`, if not given).               |

```toml
rpm = "1200 rpm"
feed = "4 in/min"
```

## `chamfer_mill`

A chamfer mill (a V-bit), which bevels top edges.  It has a `name` even
when it is not a file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `tip_diameter`    | length               | yes      | The diameter at its   |
|                   |                      |          | tip.                  |
| `angle`           | angle                | yes      | The included angle    |
|                   |                      |          | (90 deg makes 45 deg  |
|                   |                      |          | bevels).              |
| `flutes`          | integer              | no       | How many flutes.      |
| `collet`          | one of `ER8`,        | no       | The collet it is held |
|                   | `ER11`, `ER16`,      |          | in, if it is.         |
|                   | `ER20`, `ER25`,      |          |                       |
|                   | `ER32`, `ER40`,      |          |                       |
|                   | `ER50`, `R8`, `5C`,  |          |                       |
|                   | or another ending in |          |                       |
|                   | `!`                  |          |                       |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `coating`         | string               | no       | Its coating or finish |
|                   |                      |          | (`AlTiN`, ...).       |
| `manufacturer`    | string               | no       | Who made it.          |
| `manufacturer_pn` | string               | no       | The maker's part      |
|                   |                      |          | number.               |
| `vendor`          | string               | no       | Who sold it.          |
| `vendor_pn`       | string               | no       | The vendor's part     |
|                   |                      |          | number.               |
| `cost`            | money                | no       | What it cost.         |
| `acquired`        | date                 | no       | When it was bought    |
|                   |                      |          | (`2026-10-27`).       |
| `rpm`             | speed                | no       | The spindle speed to  |
|                   |                      |          | cut at.               |
| `feed`            | feed                 | no       | The feed to cut at.   |
| `plunge`          | feed                 | no       | The feed going        |
|                   |                      |          | straight down.        |

```toml
name = "1/8 in 90 deg carbide chamfer mill"
diameter = "1/8 in"
tip_diameter = "0.020 in"
angle = "90 deg"
flutes = 2
overall_length = "1-1/2 in"
material = "carbide"
vendor = "Shars Tool"
vendor_pn = "416-3509"
```

## `corner_rounding_mill`

A corner rounding mill, which rounds top edges over to its radius.  Its
tip (a pilot) rides along the wall below.  It has a `name` even when it
is not a file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `radius`          | length               | yes      | The radius it rounds  |
|                   |                      |          | edges to.             |
| `tip_diameter`    | length               | yes      | The diameter at its   |
|                   |                      |          | tip.                  |
| `flutes`          | integer              | no       | How many flutes.      |
| `collet`          | one of `ER8`,        | no       | The collet it is held |
|                   | `ER11`, `ER16`,      |          | in, if it is.         |
|                   | `ER20`, `ER25`,      |          |                       |
|                   | `ER32`, `ER40`,      |          |                       |
|                   | `ER50`, `R8`, `5C`,  |          |                       |
|                   | or another ending in |          |                       |
|                   | `!`                  |          |                       |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `coating`         | string               | no       | Its coating or finish |
|                   |                      |          | (`AlTiN`, ...).       |
| `manufacturer`    | string               | no       | Who made it.          |
| `manufacturer_pn` | string               | no       | The maker's part      |
|                   |                      |          | number.               |
| `vendor`          | string               | no       | Who sold it.          |
| `vendor_pn`       | string               | no       | The vendor's part     |
|                   |                      |          | number.               |
| `cost`            | money                | no       | What it cost.         |
| `acquired`        | date                 | no       | When it was bought    |
|                   |                      |          | (`2026-10-27`).       |
| `rpm`             | speed                | no       | The spindle speed to  |
|                   |                      |          | cut at.               |
| `feed`            | feed                 | no       | The feed to cut at.   |
| `plunge`          | feed                 | no       | The feed going        |
|                   |                      |          | straight down.        |

```toml
name = "1/16 in radius carbide corner rounding mill"
radius = "0.0625 in"
tip_diameter = "0.0469 in"
flutes = 2
shank = "3/16 in"
overall_length = "2 in"
material = "carbide"
vendor = "Shars Tool"
vendor_pn = "417-1112"
```

## `double_angle_cutter`

A pointed double angle shank cutter: a cone above and a cone below its
widest point, on a thin neck, so it can chamfer bottom edges (back
chamfering) as well as top ones.  It has a `name` even when it is not a
file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `angle`           | angle                | yes      | The included angle of |
|                   |                      |          | the two cones         |
|                   |                      |          | together.             |
| `width`           | length               | yes      | The height of the     |
|                   |                      |          | cutter (L2), point to |
|                   |                      |          | point.                |
| `neck_diameter`   | length               | no       | The neck's diameter.  |
| `neck_length`     | length               | no       | How far below the     |
|                   |                      |          | shank the cutter      |
|                   |                      |          | reaches (L3).         |
| `flutes`          | integer              | no       | How many flutes.      |
| `collet`          | one of `ER8`,        | no       | The collet it is held |
|                   | `ER11`, `ER16`,      |          | in, if it is.         |
|                   | `ER20`, `ER25`,      |          |                       |
|                   | `ER32`, `ER40`,      |          |                       |
|                   | `ER50`, `R8`, `5C`,  |          |                       |
|                   | or another ending in |          |                       |
|                   | `!`                  |          |                       |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `coating`         | string               | no       | Its coating or finish |
|                   |                      |          | (`AlTiN`, ...).       |
| `manufacturer`    | string               | no       | Who made it.          |
| `manufacturer_pn` | string               | no       | The maker's part      |
|                   |                      |          | number.               |
| `vendor`          | string               | no       | Who sold it.          |
| `vendor_pn`       | string               | no       | The vendor's part     |
|                   |                      |          | number.               |
| `cost`            | money                | no       | What it cost.         |
| `acquired`        | date                 | no       | When it was bought    |
|                   |                      |          | (`2026-10-27`).       |
| `rpm`             | speed                | no       | The spindle speed to  |
|                   |                      |          | cut at.               |
| `feed`            | feed                 | no       | The feed to cut at.   |
| `plunge`          | feed                 | no       | The feed going        |
|                   |                      |          | straight down.        |

```toml
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
```

## `materials`

The materials a shop cuts, and how to drill and mill them.  Speeds and
feeds worked out from these are only starting points; a tool's own
`cutting` entries win.  It has a `name` even when it is not a file of
its own.

| Key                    | Value              | Required | Meaning            |
| ---------------------- | ------------------ | -------- | ------------------ |
| `carbide_speed_factor` | fraction           | yes      | A carbide tool's   |
|                        |                    |          | surface speed, as  |
|                        |                    |          | a share of HSS's.  |
| `cobalt_speed_factor`  | fraction           | yes      | A cobalt tool's    |
|                        |                    |          | surface speed, as  |
|                        |                    |          | a share of HSS's.  |
| `end_milling`          | `end_milling`      | yes      | How end mills      |
|                        |                    |          | feed.              |
| `drilling`             | `drilling`         | yes      | How drills feed.   |
| `groups`               | list of            | yes      | The groups of      |
|                        | `material_group`   |          | materials that cut |
|                        |                    |          | alike.             |
| `materials`            | list of `material` | yes      | The materials,     |
|                        |                    |          | each in a group.   |

```toml
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
```

## `drilling`

How drills feed: the feed per revolution by drill diameter (the middle
of the catalog ranges), times the group's `feed_factor`.

| Key           | Value                | Required | Meaning                   |
| ------------- | -------------------- | -------- | ------------------------- |
| `feed_ranges` | list of `feed_range` | yes      | The feeds per revolution, |
|               |                      |          | smallest drills first.    |

```toml
[[feed_ranges]]
below = "1/8 in"
feed = "0.002 in/rev"
```

## `end_milling`

How end mills feed: the chip load by diameter, times the group's
`feed_factor`, times the flutes and the RPM.

| Key             | Value               | Required | Meaning                  |
| --------------- | ------------------- | -------- | ------------------------ |
| `plunge_factor` | fraction            | yes      | The plunge feed, as a    |
|                 |                     |          | share of the feed.       |
| `chip_loads`    | list of `chip_load` | yes      | The chip loads, smallest |
|                 |                     |          | end mills first.         |

```toml
plunge_factor = "50 %"

[[chip_loads]]
below = "1/4 in"
chip_load = "0.001 in/tooth"
```

## `chip_load`

The chip load of end mills below a diameter.

| Key         | Value     | Required | Meaning                                |
| ----------- | --------- | -------- | -------------------------------------- |
| `below`     | length    | yes      | The end mills it is for are smaller    |
|             |           |          | than this.                             |
| `chip_load` | chip load | yes      | Their feed per tooth.                  |

```toml
below = "1/4 in"
chip_load = "0.001 in/tooth"
```

## `feed_range`

The feed per revolution of drills below a diameter.

| Key     | Value        | Required | Meaning                                 |
| ------- | ------------ | -------- | --------------------------------------- |
| `below` | length       | yes      | The drills it is for are smaller than   |
|         |              |          | this.                                   |
| `feed`  | feed per rev | yes      | Their feed per revolution.              |

```toml
below = "1/8 in"
feed = "0.002 in/rev"
```

## `material_group`

A group of materials that cut alike.  It has a `name` even when it is
not a file of its own.

| Key                 | Value         | Required | Meaning                    |
| ------------------- | ------------- | -------- | -------------------------- |
| `description`       | string        | no       | What is in it.             |
| `hss_surface_speed` | surface speed | yes      | The surface speed of an    |
|                     |               |          | HSS tool.                  |
| `feed_factor`       | fraction      | yes      | The feed, as a share of    |
|                     |               |          | `feed_ranges` and          |
|                     |               |          | `chip_loads`.              |

```toml
name = "soft"
description = "Aluminum, brass, acetal"
hss_surface_speed = "250 sfm"
feed_factor = "150 %"
```

## `material`

A material the shop cuts.  It has a `name` even when it is not a file of
its own.

| Key     | Value  | Required | Meaning                 |
| ------- | ------ | -------- | ----------------------- |
| `group` | string | yes      | The group it cuts with. |

```toml
name = "6061 aluminum"
group = "soft"
```
