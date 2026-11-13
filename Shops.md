# Shops: The Shop Description Files

This document is written by `scraftcam/shops.py` (`python3 -m
scraftcam.shops markdown > Shops.md`) from the schema that its reader
checks files against; a change is made there, never here.

A shop is a directory: its `shop.toml`, and one
[TOML](https://toml.io/en/v1.0.0) file per item (a machine, a tool, a
grid plate, a material) in the directories beside it.  The reader
reads them all into one data structure (JSON style dictionaries,
lists, strings, numbers and booleans), which the CNC side uses
without knowing how the files were split.  The GUI
(`python3 -m scraftcam.run`) writes these files; they may be edited
by hand as well, and are best kept under version control.

This document describes format version `0.0.1`, the version every
file carries in its `version` key.

In the tables, a row whose first cell is empty continues the row
above it, so that no line is too wide to read in a text editor.

## The Shop's Directory

```
shop/
  shop.toml                the shop (`shop`)
  controllers/linuxcnc.toml   a controller (`controller`)
  machines/shop_mill.toml     a machine, with its tool table (`machine`)
  tool_materials/carbide.toml what tools are made of (`tool_material`)
  tools/1_4_in_end_mill.toml  a tool (`end_mill`, `drill`, ...)
  tooling/grid_plate.toml     work holding (`grid_plate`)
  stock_materials/cutting_data.toml   how to cut (`materials`)
  stock_materials/6061_aluminum.toml  a material cut (`material`)
```

* `scraftcam` names the directories; the files in them are named
  as the user likes (the GUI names them after the item).
* Each file is one item, of a kind its directory holds; a file of
  another kind there is refused.
* No two items of a kind may share a name (no two tools at all).
* A machine names its controller by name (`controller = "LinuxCNC"`),
  and holds its tool table (`[tool_table.tools]`), which names tools
  by name.  Any other table is written in place.
* The reader fills in the shop's `machines`, `tools`, `tooling` and
  `materials` from the directories.
* The example shop is `examples/shop/`.

### The First Line

A file the GUI writes starts with a comment naming its kind's JSON
Schema, which editors such as VS Code (with Even Better TOML) use to
check it as it is typed:

```toml
#:schema https://raw.githubusercontent.com/.../schemas/machine.json
```

(`SCHEMA_URL` in `shop_schema.py` is the whole address.)

The schemas are written from the same descriptions as this document
(`python3 -m scraftcam.shop_schema`).  They check less than the
reader does.

### The Header Keys

Every file starts with the same keys:

| Key        | Value   | Required | Meaning                                   |
| ---------- | ------- | -------- | ----------------------------------------- |
| `name`     | string  | yes      | Unique among the things of its kind.      |
| `kind`     | string  | yes      | What the rest of the file is.             |
| `language` | string  | yes      | The language of the names and notes.      |
| `version`  | version | yes      | The format version, `MAJOR.MINOR.PATCH`.  |
| `notes`    | string  | no       | Anything worth writing down about it (the |
|            |         |          | GUI shows and edits it; `#` comments are  |
|            |         |          | not kept).                                |

* `name`: things refer to each other by name, so no two things of
  the same kind may share one.
* `kind`: one of the sections below; it says which keys the rest of
  the file has.
* `version`: a major version other than this document's is refused,
  and so is a newer minor version.
* `notes`: `#` comments are not kept when the GUI writes a file, so
  what is worth keeping goes here.  Any table may have `notes`.

A table written in place (not in a file of its own) needs none of
them, though it may have them; a `kind` there must fit where it is.

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

### Tool Holders

A tool's `holder` lists what holds it, from the spindle down to the
tool, ending in the bore, with its unit:

```toml
holder = ["tormach", "er16", "3/8 in"]  # A Tormach ER16 holder.
holder = ["tormach", "1/4 in"]          # A Tormach fixed bore holder.
holder = ["cat40", "er32", "1/2 in"]    # A CAT40 ER32 collet chuck.
holder = ["r8", "6 mm"]                 # A plain R8 collet.
holder = ["er20", "1/2 in"]             # A spindle that takes ER20.
```

Every entry but the last is one of these, in any capitals, or another
ending in `!`.  The last is a length.  Nothing else is checked: not
whether a holder fits the spindle, nor a bore the collet or the tool.

* `tormach`: The Tormach Tooling System, a 3/4 in straight shank held
  in a 3/4 in R8 collet.  Fixed bores and set screw holders, or ER16,
  ER20 and ER32 collets.
* `r8`, `5c`: A collet of that kind, or anything with that shank.
* `cat40`, `cat50`: CAT V-flange tapers (ANSI/ASME B5.50).
* `bt30`, `bt40`, `bt50`: BT tapers (the Japanese MAS standard).
* `sk40`, `sk50`: SK tapers (DIN 69871).
* `hsk-a63`, `hsk-a100`: HSK form A hollow tapers (ISO 12164, DIN
  69893).
* `er8` to `er50`: ER collets.  By one vendor's chart, the largest bores
  are 5, 7, 10, 13, 16, 20, 26 and 34 mm, for `er8`, `er11`, `er16`,
  `er20`, `er25`, `er32`, `er40` and `er50`.
* `drill-chuck`, `shell-mill`: A drill chuck; a shell mill arbor.

### Keys and Problems

* Keys are `snake_case`.
* An unknown key is refused (a misspelled key is a mistake, not a
  comment).
* A choice (`"one of ..."` in the tables) may be written in any
  capitals (`"r8"` is `"R8"`).  Where a table says "or another ending
  in `!`", the list is only the common ones, and a value ending in
  `!` is taken without a check (`interface = "HSK100A!"`).
* Every problem is reported with its file, line and key, e.g.
  `machines/shop_mill.toml:12: spindle.max_rpm: "5000" needs a
  unit`.  Every problem found is reported, not only the first.

## `shop`

A shop: `shop.toml`, at the top of the shop's directory.  Its machines,
tools, tooling and materials are the files in the directories beside it
(`SHOP_DIRECTORIES`); the reader fills in `machines`, `tools`, `tooling`
and `materials` from them, so `shop.toml` itself has none of them.  It
has a `name` even when it is not a file of its own.

| Key              | Value                 | Required | Meaning               |
| ---------------- | --------------------- | -------- | --------------------- |
| `location`       | `location`            | no       | Where the shop is.    |
| `units`          | one of `in`, `mm`     | no       | The units the shop    |
|                  |                       |          | prefers: `in`         |
|                  |                       |          | (imperial) or `mm`    |
|                  |                       |          | (metric).             |
| `machine_kinds`  | list of `cnc_mill`,   | no       | The kinds of machines |
|                  | `cnc_router`,         |          | the shop has,         |
|                  | `cnc_lathe`,          |          | computer controlled   |
|                  | `laser_cutter`,       |          | or manual (for prep   |
|                  | `3d_printer`,         |          | work).                |
|                  | `manual_mill`,        |          |                       |
|                  | `manual_lathe`,       |          |                       |
|                  | `manual_drill_press`, |          |                       |
|                  | `manual_bandsaw`      |          |                       |
| `machines`       | list of `machine`     | no       | The machines in the   |
|                  |                       |          | shop: the files in    |
|                  |                       |          | `machines/`.          |
| `tools`          | list of `tools`       | no       | The tools on hand,    |
|                  |                       |          | shared by the         |
|                  |                       |          | machines: the files   |
|                  |                       |          | in `tools/`.          |
| `tooling`        | list of `tooling`     | no       | The work holding on   |
|                  |                       |          | hand (grid plates for |
|                  |                       |          | now), shared by the   |
|                  |                       |          | machines: the files   |
|                  |                       |          | in `tooling/`.        |
| `materials`      | `materials`           | no       | The materials it      |
|                  |                       |          | cuts, and how to      |
|                  |                       |          | drill and mill them:  |
|                  |                       |          | the files in          |
|                  |                       |          | `stock_materials/`.   |
| `tool_materials` | list of               | no       | What its tools are    |
|                  | `tool_material`       |          | made of, and how fast |
|                  |                       |          | each cuts: the files  |
|                  |                       |          | in `tool_materials/`. |

```toml
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
units = "in"
machine_kinds = ["cnc_mill", "cnc_router"]

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
| `controller`  | `controller`           | yes      | The controller, by its  |
|               |                        |          | name (a file in         |
|               |                        |          | `controllers/`).        |
| `tool_table`  | `tool_table`           | no       | The tools loaded.       |
| `preferences` | `preferences`          | no       | How it is run.          |
| `carousel`    | `carousel`             | no       | Its tool changer's      |
|               |                        |          | carousel, if it has     |
|               |                        |          | one.                    |

```toml
name = "Shop mill"
kind = "machine"
language = "English"
version = "0.0.1"
machine = "mill"
controller = "LinuxCNC"

[tool_table.tools]
1 = "1/4 in 2 flute carbide end mill"

[spindle]
interface = "R8"
max_rpm = "5000 rpm"

[[axes]]
letter = "X"
travel = "18 in"
max_feed = "110 in/min"
```

## `carousel`

A machine's tool carousel: its slots, on spokes from a hub.  A tool is
put in or taken out at the +X spoke.  A program with more tools than
slots stops to swap them (`carousel.py`).

| Key            | Value   | Required | Meaning                               |
| -------------- | ------- | -------- | ------------------------------------- |
| `slots`        | integer | yes      | How many tools it holds (0: every     |
|                |         |          | change by hand).                      |
| `x`            | length  | no       | The hub's machine X.                  |
| `y`            | length  | no       | The hub's machine Y.                  |
| `z`            | length  | no       | The hub's machine Z.                  |
| `spoke_length` | length  | no       | From the hub to a slot.               |

```toml
slots = 4
x = "-3 in"
y = "4.5 in"
z = "-2 in"
spoke_length = "2.5 in"
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

| Key            | Value   | Required | Meaning                               |
| -------------- | ------- | -------- | ------------------------------------- |
| `length`       | length  | yes      | Along X.                              |
| `width`        | length  | yes      | Along Y.                              |
| `t_slots`      | integer | no       | How many T-slots.                     |
| `t_slot_pitch` | length  | no       | Between T-slots.                      |
| `t_slot_width` | length  | no       | At the top.                           |
| `t_slot_depth` | length  | no       | From the table top.                   |
| `x`            | length  | no       | Where the table sits in the machine:  |
|                |         |          | the machine X of the point a setup    |
|                |         |          | places the table by (its location in  |
|                |         |          | the setup's `(SCC: ...)` comments).   |
|                |         |          | With `y` and `z`, it gives the work   |
|                |         |          | origin (G54).                         |
| `y`            | length  | no       | The same, along Y.                    |
| `z`            | length  | no       | The same, along Z.                    |

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
`str.format()` template, filled in with the tool's `number` and
`description`; it may hold several lines, each words or a whole-line
comment, such as a `(MSG, ...)` line and `M0`, so the operator is told
which tool to put in.  It has a `name` even when it is not a file of its
own.

| Key              | Value             | Required | Meaning                   |
| ---------------- | ----------------- | -------- | ------------------------- |
| `post_processor` | one of `linuxcnc` | yes      | Which dialect of G-code   |
|                  |                   |          | it reads.                 |
| `tool_change`    | string            | no       | The lines that change the |
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
machine at a time).  It is in its machine's file, as
`[tool_table.tools]`.

| Key     | Value                 | Required | Meaning                 |
| ------- | --------------------- | -------- | ----------------------- |
| `tools` | T number to tool name | yes      | The tools, by T number. |

```toml
[tools]
1 = "1/4 in 2 flute carbide end mill"
4 = "15/64 in HSS jobber drill"
```

## `tools`

Tools: the bits that go in a holder in the spindle.  How to cut with
each (`rpm`, `feed`, `plunge`) is given with the tool for now, until it
can be worked out from the material being cut.  Only the bits are
described; `holder` only says what holds each one.  Tools are shared by
machines, so they are not listed by machine: a machine's `tool_table`
names the ones it has loaded, and every tool's `name` and `unique_id`
are unique among all the tools (T numbers are only unique within one
machine).  It has a `name` even when it is not a file of its own.

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
| `single_countersinks`   | list of                | no       | The single    |
|                         | `single_countersink`   |          | end           |
|                         |                        |          | countersinks. |
| `double_countersinks`   | list of                | no       | The double    |
|                         | `double_countersink`   |          | end           |
|                         |                        |          | countersinks. |

```toml
name = "Tools"
kind = "tools"
language = "English"
version = "0.0.1"

[[end_mills]]
name = "1/4 in 2 flute carbide end mill"
unique_id = 1
diameter = "1/4 in"
length_of_cut = "3/4 in"
overall_length = "2-1/2 in"
flutes = 2
end = "square"
material = "carbide"

[[drills]]
name = "15/64 in HSS jobber drill"
unique_id = 5
diameter = "15/64 in"
length_of_cut = "2-5/8 in"
overall_length = "3-7/8 in"
point_angle = "118 deg"
holder = ["r8", "er32", "1/4 in"]
material = "HSS"
```

## `end_mill`

An end mill: square, ball or bull nose (a square end with rounded
corners), and perhaps a rougher.  It has a `name` even when it is not a
file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
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
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
unique_id = 2
diameter = "1/2 in"
length_of_cut = "1 in"
overall_length = "3 in"
flutes = 2
end = "square"
center_cutting = true
material = "carbide"
finish = "uncoated"
vendor = "Shars Tool"
vendor_pn = "415-0998"
cost = "47.02 USD"
acquired = 2026-10-27
```

## `drill`

A twist drill.  It has a `name` even when it is not a file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `length_of_cut`   | length               | yes      | How deep it can cut   |
|                   |                      |          | (LOC).                |
| `flutes`          | integer              | no       | How many flutes (2 if |
|                   |                      |          | not given).           |
| `point_angle`     | angle                | yes      | The included angle.   |
| `shank_length`    | length               | no       | How far its shank     |
|                   |                      |          | comes down from its   |
|                   |                      |          | top; if not given, a  |
|                   |                      |          | `shank` starts where  |
|                   |                      |          | its flutes stop.      |
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
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
unique_id = 6
diameter = "1/8 in"
length_of_cut = "1-5/8 in"
overall_length = "2-3/4 in"
point_angle = "135 deg"
split_point = true
holder = ["r8", "er32", "1/8 in"]
material = "cobalt"
grade = "M42"
finish = "straw"
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
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `tip_diameter`    | length               | yes      | The diameter at its   |
|                   |                      |          | tip.                  |
| `angle`           | angle                | yes      | The included angle    |
|                   |                      |          | (90 deg makes 45 deg  |
|                   |                      |          | bevels).              |
| `flutes`          | integer              | no       | How many flutes.      |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
unique_id = 7
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
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `radius`          | length               | yes      | The radius it rounds  |
|                   |                      |          | edges to.             |
| `tip_diameter`    | length               | yes      | The diameter at its   |
|                   |                      |          | tip.                  |
| `flutes`          | integer              | no       | How many flutes.      |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
unique_id = 8
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
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
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
| `neck_length`     | length               | no       | The neck's length     |
|                   |                      |          | (L3), from the shank  |
|                   |                      |          | to the cutter.        |
| `flutes`          | integer              | no       | How many flutes.      |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
unique_id = 9
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

## `single_countersink`

A combined drill and countersink on a shank: a small drill at its tip,
joined to its body by a cone.  It can not go in a `tool_table` yet.  It
has a `name` even when it is not a file of its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `drill_diameter`  | length               | yes      | The diameter of the   |
|                   |                      |          | small drill at its    |
|                   |                      |          | tip.                  |
| `drill_length`    | length               | no       | How far the small     |
|                   |                      |          | drill reaches from    |
|                   |                      |          | its tip (its diameter |
|                   |                      |          | if not given).        |
| `angle`           | angle                | yes      | The countersink's     |
|                   |                      |          | included angle.       |
| `point_angle`     | angle                | no       | The included angle of |
|                   |                      |          | the small drill's     |
|                   |                      |          | point (90 deg if not  |
|                   |                      |          | given).               |
| `flutes`          | integer              | no       | How many flutes (2 if |
|                   |                      |          | not given).           |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
name = "1/4 in 60 deg single end countersink"
unique_id = 10
diameter = "1/4 in"
drill_diameter = "3/32 in"
angle = "60 deg"
overall_length = "2 in"
material = "HSS"
```

## `double_countersink`

A combined drill and countersink, cut at both ends (a center drill).
Its `shank` means nothing, since it is cut at both ends.  It can not go
in a `tool_table` yet.  It has a `name` even when it is not a file of
its own.

| Key               | Value                | Required | Meaning               |
| ----------------- | -------------------- | -------- | --------------------- |
| `unique_id`       | positive integer     | yes      | Its unique id, a      |
|                   |                      |          | number from 1, unique |
|                   |                      |          | among all the tools   |
|                   |                      |          | of the shop (this is  |
|                   |                      |          | not a T number).      |
| `description`     | string               | no       | What it is, in a few  |
|                   |                      |          | words.                |
| `diameter`        | length               | yes      | The cutting diameter. |
| `drill_diameter`  | length               | yes      | The diameter of the   |
|                   |                      |          | small drill at its    |
|                   |                      |          | tip.                  |
| `drill_length`    | length               | no       | How far the small     |
|                   |                      |          | drill reaches from    |
|                   |                      |          | its tip (its diameter |
|                   |                      |          | if not given).        |
| `angle`           | angle                | yes      | The countersink's     |
|                   |                      |          | included angle.       |
| `point_angle`     | angle                | no       | The included angle of |
|                   |                      |          | the small drill's     |
|                   |                      |          | point (90 deg if not  |
|                   |                      |          | given).               |
| `flutes`          | integer              | no       | How many flutes (2 if |
|                   |                      |          | not given).           |
| `shank`           | length               | no       | The shank diameter,   |
|                   |                      |          | if not `diameter`.    |
| `overall_length`  | length               | yes      | Its whole length      |
|                   |                      |          | (OAL).                |
| `holder`          | holder list          | no       | What holds it, from   |
|                   |                      |          | the spindle to its    |
|                   |                      |          | bore (see Tool        |
|                   |                      |          | Holders).             |
| `material`        | one of `HSS`,        | yes      | What it is made of.   |
|                   | `cobalt`, `carbide`, |          |                       |
|                   | `cermet`, `ceramic`, |          |                       |
|                   | `CBN`, `PCD`, or     |          |                       |
|                   | another ending in    |          |                       |
|                   | `!`                  |          |                       |
| `grade`           | string               | no       | The grade (`M2`,      |
|                   |                      |          | `M42`, ...).          |
| `finish`          | string               | no       | Its finish or coating |
|                   |                      |          | (`uncoated`, `AlTiN`, |
|                   |                      |          | ...).                 |
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
name = "#3 60 deg double end countersink"
unique_id = 11
diameter = "1/4 in"
drill_diameter = "7/64 in"
angle = "60 deg"
overall_length = "2 in"
material = "HSS"
```

## `tooling`

Tooling: what holds work on a machine, rather than cutting it.  Only
grid plates are described so far; vises, parallels and mill tables are
still in `tools.py`.  Every piece's `name` is unique among the shop's
tooling, so that a setup can name it.  It has a `name` even when it is
not a file of its own.

| Key           | Value                | Required | Meaning          |
| ------------- | -------------------- | -------- | ---------------- |
| `grid_plates` | list of `grid_plate` | no       | The grid plates. |

```toml
name = "Tooling"
kind = "tooling"
language = "English"
version = "0.0.1"

[[grid_plates]]
name = "Small grid plate"
rows = 8
columns = 8
pitch = "1/2 in"
edge = "1/4 in"
thickness = "1/2 in"
hole_diameter = "0.144 in"
```

## `grid_plate`

A grid plate: a plate with a grid of holes, for holding work down,
perhaps with chamfered holes and tooling holes.  `Tool_Models.md` draws
one, with each size.  Chamfers take SolidCraft minutes to model, once;
the model cache keeps the result.  It has a `name` even when it is not a
file of its own.

| Key                      | Value   | Required | Meaning                     |
| ------------------------ | ------- | -------- | --------------------------- |
| `description`            | string  | no       | What it is, in a few words. |
| `rows`                   | integer | yes      | The number of rows of grid  |
|                          |         |          | holes (along Y).            |
| `columns`                | integer | yes      | The number of columns of    |
|                          |         |          | grid holes (along X).       |
| `pitch`                  | length  | yes      | The distance between grid   |
|                          |         |          | holes, along X and Y.       |
| `edge`                   | length  | yes      | The distance from a side to |
|                          |         |          | the nearest holes; the      |
|                          |         |          | plate's length and width    |
|                          |         |          | follow from the grid.       |
| `thickness`              | length  | yes      | Its size along Z.           |
| `hole_diameter`          | length  | yes      | The diameter of the grid's  |
|                          |         |          | holes.                      |
| `corner_radius`          | length  | no       | The radius of its four      |
|                          |         |          | corners (square if not      |
|                          |         |          | given).                     |
| `chamfer_width`          | length  | no       | How wide (and deep) the 45  |
|                          |         |          | degree chamfer on each grid |
|                          |         |          | hole's top edge is (none if |
|                          |         |          | not given).                 |
| `edge_chamfer`           | length  | no       | How wide (and deep) the 45  |
|                          |         |          | degree chamfer on the       |
|                          |         |          | plate's top outer edge is   |
|                          |         |          | (none if not given).        |
| `tooling_pitch`          | length  | no       | The distance between        |
|                          |         |          | tooling holes, along X and  |
|                          |         |          | Y, each midway between four |
|                          |         |          | grid holes, as many as fit, |
|                          |         |          | centered (none if not       |
|                          |         |          | given).                     |
| `tooling_tap_diameter`   | length  | no       | The diameter of the tooling |
|                          |         |          | holes to be threaded (the   |
|                          |         |          | tap drill); the lower left  |
|                          |         |          | one is one of these.        |
| `tooling_close_diameter` | length  | no       | The diameter of the close   |
|                          |         |          | fit tooling holes, in a     |
|                          |         |          | checkerboard with the       |
|                          |         |          | tapped ones.                |
| `manufacturer`           | string  | no       | Who made it.                |
| `vendor`                 | string  | no       | Who sold it.                |
| `cost`                   | money   | no       | What it cost.               |
| `acquired`               | date    | no       | When it was bought or made. |

```toml
name = "Grid plate"
description = "Aluminum, made in the shop"
rows = 20
columns = 10
pitch = "1/2 in"
edge = "1/2 in"
thickness = "1/2 in"
hole_diameter = "0.144 in"
corner_radius = "1/4 in"
chamfer_width = "1/32 in"
edge_chamfer = "1/32 in"
tooling_pitch = "3 in"
tooling_tap_diameter = "0.159 in"
tooling_close_diameter = "0.196 in"
```

## `materials`

The materials a shop cuts, and how to drill and mill them.  Speeds and
feeds worked out from these are only starting points; a tool's own
`cutting` entries win.  It has a `name` even when it is not a file of
its own.

| Key           | Value                  | Required | Meaning                 |
| ------------- | ---------------------- | -------- | ----------------------- |
| `end_milling` | `end_milling`          | yes      | How end mills feed.     |
| `drilling`    | `drilling`             | yes      | How drills feed.        |
| `groups`      | list of                | yes      | The groups of materials |
|               | `material_group`       |          | that cut alike.         |
| `materials`   | list of `material`     | no       | The materials, each in  |
|               |                        |          | a group: in a shop, the |
|               |                        |          | files in                |
|               |                        |          | `stock_materials/`      |
|               |                        |          | (other than this one).  |

```toml
name = "Materials"
kind = "materials"
language = "English"
version = "0.0.1"

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

## `tool_material`

What a tool is made of (a tool's `material` names one), and how fast it
cuts: speeds and feeds are worked out for a tool whose material is one
of these.  It has a `name` even when it is not a file of its own.

| Key            | Value    | Required | Meaning                              |
| -------------- | -------- | -------- | ------------------------------------ |
| `speed_factor` | fraction | yes      | Its surface speed, as a share of     |
|                |          |          | HSS's (HSS's own is 100 %).          |
| `description`  | string   | no       | What it is, in a few words.          |

```toml
name = "carbide"
speed_factor = "250 %"
```
