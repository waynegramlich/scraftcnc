# 2.2 Shop Information

The first step of `T.ds~2` (Document a Shop): a shop described in
TOML files, ported from `../Fab/FabShops.py` (2022), with a loader
that checks everything and tests.  This sub-task sets how the files
look and fit together, and fills in the shop and its machines; the
details of tools, tooling and materials come in later sub-tasks, but
their places are set here.

## What Fab Had (`FabShops.py`)

* `FabShops`: every shop.  `FabShop`: a name, a `FabLocation` and its
  machines (names unique within the shop).
* `FabLocation`: all optional strings: country code, state/province,
  county, city, two street address lines, unit, zip code, latitude,
  longitude, phone number, URL.  A shop on a boat may have none.
* `FabMachine`: a name and a placement in the shop.  `FabCNC` (with
  `FabCNCMill` and `FabCNCRouter`, which differ only in their kind):
  * `FabAxis` per axis: name, letter, linear or rotary, range, maximum
    feed, maximum acceleration (0 if unknown), end sensors, brake.
  * `FabTable`: name, length, width, height, number of T-slots, slot
    pitch, slot width and depth, keyway width and height.
  * `FabSpindle`: type (R8, CAT40, ...), maximum RPM, reversible,
    flood and mist cooling.
  * `FabController`: name and post processor (e.g. `linuxcnc`).
  * Rapid feeds come from the axes: X/Y is the slower of the two, Z
    its own.
* `Fab_ShopBit`: a bit on a machine in a shop, with a tool number and
  a priority for choosing it.

## The Things Described

* A **shop** has a name, a location and its machines.
* A **machine** (a CNC mill or router for now) has axes, a table, a
  spindle (its taper: R8, CAT40, ...), a controller (e.g. LinuxCNC)
  and a tool table.
* **Tools** go in the spindle and cut the material (end mills, drills,
  chamfer mills, ...).  A set of tools may be shared by several
  machines; each machine's tool table gives the T numbers (`T01`, ...)
  of the ones it uses, so T numbers are allocated per machine.
* **Tooling** holds the material in place (vises, parallels, tooling
  plates, clamps and hold downs).
* **Materials** are what is actually cut (6061 aluminum, acrylic,
  ...).

## The Files

* Many files, organized as the user wants.  Every file starts with the
  same four keys:

  ```toml
  name = "Home shop"
  kind = "shop"           # Or "machine", "tools", "tooling", ...
  language = "English"    # Of the names and notes in the file.
  version = "0.0.1"       # The file format's version (semantic).
  ```
* `kind` says what the rest of the file is, so the loader knows which
  keys to expect.
* `version` follows semantic versioning (`MAJOR.MINOR.PATCH`): the
  loader refuses a major version it does not know, and a newer minor
  version than its own.
* Keys have no `SC` (or other) prefix.  Their style (proposed:
  `snake_case`) is waiting for the user; what is common:
  * The TOML specification sets no style (bare keys may use letters,
    digits, `_` and `-`), but its own example uses `snake_case`
    (`connection_max`).
  * `kebab-case`: Cargo (`rust-version`), `pyproject.toml`'s
    `[project]` (`requires-python`), and tools that follow it (`ruff`,
    `black`: `line-length`).
  * `snake_case`: `rustfmt.toml` (`max_width`), `mypy` and `pytest`
    in `pyproject.toml` (`warn_return_any`, `ini_options`), Alacritty,
    Starship, and this project's `machine.toml`.
  * `camelCase`: rarer (Hugo's `baseURL`).
  * `snake_case` keys are also Python's own attribute names, so the
    loader maps them with no translation.
* Every measurement carries its unit, as in `machine.toml`.  New kinds
  of unit: angles and rotary feeds (`deg`, `deg/min`) for rotary
  axes, and acceleration (`in/s^2`, `mm/s^2`).  Plain counts (number
  of T-slots) and yes/no facts (`true`/`false`) have none.

### Nested TOML: Joining Files with `@` (Agreed)

"Nested TOML" is the name for a description kept in more than one
`.toml` file.  A string `"@FILE_NAME"` stands for the contents of that
file, in any place that takes a table or a list of them, so the same
thing can be written in place or kept in its own file.  The reader
reads every file and splices them together into one big data
structure (plain JSON style dictionaries, lists, strings, numbers and
booleans), which the CNC side digests without knowing how the files
were split:

```toml
# home_shop.toml
name = "Home shop"
kind = "shop"
language = "English"
version = "0.0.1"
location = { latitude = "37.37066 deg", longitude = "-122.04002 deg",
             address = "700 All American Way, Sunnyvale, CA 94086" }
machines = ["@shop_mill.toml", "@router.toml"]
tools = ["@end_mills.toml", "@drills.toml"]

# shop_mill.toml
name = "Shop mill"
kind = "machine"
language = "English"
version = "0.0.1"
machine = "mill"
spindle = { taper = "R8", max_rpm = "5000 rpm", ... }
controller = { name = "LinuxCNC", ... }
tool_table = { 1 = "1/4 inch 2 flute end mill", 4 = "15/64 inch drill" }
```

* A named file must be in the same directory as the file that names
  it (a bare file name, no `/`); the loader refuses anything else, a
  missing file, a loop (a file that names itself, directly or not),
  and a file whose `kind` does not fit where it is named (e.g. a
  `tools` file in `machines`).
* Each file is read once, however often it is named, and its contents
  are spliced in at every place that names it, so one tools file can
  serve several machines (or shops).
* Things refer to each other by name (a tool table names tools), so
  names must be unique within their kind; every problem names the
  file and the entry (e.g. `shop_mill.toml: tool_table.4: no tool
  named "15/64 drill"`).
* Why `@` in a value rather than an `include = [...]` key: the
  reference sits where its contents belong, so nothing has to say
  where an included file's contents go.

### The Description: `Shops.md` (Agreed)

One file, `Shops.md` (at the top level, beside `README.md`), describes
the files; the user edits it:

* It covers everything a shop can refer to, not only the shop itself,
  since a tools or materials file can stand alone and be shared.
* Its first section describes Nested TOML in general (the four header
  keys, versions, `@` references, units, unknown keys, error
  messages), so that it could later move to its own `Nested_TOML.md`.
* Then one section per `kind`, headed by the `kind` value itself, each
  listing its keys (type or kind of unit, required or not, meaning)
  and ending with a short example.
* It states the format version it describes, the same one the files
  carry in `version`; a change to the format changes both together.

## The Code

* Python class names are `CamelCase` starting with `SC` (e.g.
  `SCShop`, `SCLocation`, `SCMill`, `SCAxis`, `SCSpindle`,
  `SCController`), and collide with nothing in `scraftpybind` (none
  of its classes start with `SC`) or in this project (`SCMachine` and
  `SCTool` are taken by `scmachine.py`, so the machine class needs
  another name).  A new module (e.g. `scshop.py`).
* The controller lists every CNC code (G, M, ...) it accepts, since
  not all controllers implement all of them; LinuxCNC is the
  baseline, and what `machine.toml` holds now (canned cycles, tool
  change words) moves there.
* A loader that follows the `@` references and reports every problem
  as a `ValueError` naming the file and the entry, and refuses unknown
  keys (a misspelled key is a mistake, not a comment).
* Frozen `@dataclass(slots=True)` classes, as the Python rules ask,
  with the questions Fab asked of them (`lookup(name)`, the rapid
  feeds, the maximum RPM).
* Only example files are kept in this repository (e.g.
  `examples/shop/`), with every entry filled in, and tests built on
  them; their location is a public one (Fab used the Sunnyvale police
  station).  The user's own shop files live elsewhere.
* `machine.toml` keeps working; the demo moves to the shop files when
  the tools sub-task is done (`T.ds~2`, "Done When").

## Questions

The user's numbering of 2026-10-27 (the earlier numbers in brackets):

0. TOML key style: researched above; `snake_case` recommended, waiting
   for the user's choice.
1. [1] Class names: `CamelCase` with `SC`, colliding with nothing in
   `scraftpybind`.  Still to choose: the machine class name
   (`SCMachine` is taken).
2. [4] Answered: the controller lists all the CNC codes it accepts;
   LinuxCNC is the baseline.
3. [6] TBD: the address as one string, or Fab's separate lines
   (street, city, state, zip code, country)?
4. [7] Answered: `@FILE_NAME` agreed, with the file in the same
   directory.
5. [2] Open: how the files are split up is left to the user (the `@`
   references allow any split).

Settled earlier: no prefix on TOML keys; only examples in this
repository; a machine has a spindle and a tool table of T numbers,
with tools shared between machines; the shop has a name and a
location (latitude, longitude, address); every file starts with
`name`, `kind`, `language`, `version`.
