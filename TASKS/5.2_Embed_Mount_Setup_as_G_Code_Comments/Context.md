# LLM Agent Context Log

## 2026-11-04: Questions and the first answers

Claude asked 22 numbered questions (sticky numbers; new ones go on
from #23; the user answers about five at a time).  The user's answers:

* #1: Only RS-274 `( ... )` comments, no `;`.  A whole-line comment
  and a comment at the end of a command are to be told apart (the
  user's wording repeated itself; to confirm).
* #2: Open.  RS-274 is meant to be read by humans: pretty printed
  JSON is only semi-readable, TOML better, and a Python call has
  appeal because the Python code can be heavily documented.
* #3: Keep lines to PEP 8 lengths (79), for people reading them.
* #4: The user leans to Python (module, class, method).
* #5: Yes, versions are wanted.

Found by Claude: a `( ... )` comment can not hold `(` or `)`, so a
Python call can not be written as is (#23).

Still open: #6-#22 as first asked (self-contained vs by reference,
cache keys, the part, stock, coordinate frames, keep-outs, spindle
tools, display, operator steps, writer and reader, the rename,
foreign files, multi-setup).

## 2026-11-04: Second answers

* #1: Settled.  Setup data only in comment lines of their own.
* #23: Leaning to TOML (the only format without parentheses), though
  the user is not fond of it.  A `)` in a TOML string is still a
  problem.  (Claude: TOML's Unicode escapes, backslash-u 0028
  and 0029, get around it.)
* #4: Anything importable from `PYTHONPATH` can be used, and
  `PYTHONPATH` should be easy to set when running.  The user isn't sure
  this fully answers it.
* #5: Settled.  The version is the `scraftcnc` release number (the
  PyPI version, if it ever goes there).
* #6: Settled.  A `.nc` refers to the environment that built it and
  is not expected to work anywhere else.

## 2026-11-04: Third answers

* #4: A comment names `M.C.M` (module, class, method).  `importlib`
  imports M; the rest follows.
* #24: Read at most 5 files at a time, asked for as a top 5 item.
  `setups.py` and `tooling/mount.py` have been read.  `SCLayer`
  (`mount.py`) already has `name`, `seat()`, `model()`, `cacheable()`
  and `keep_out()`.  `SCPlacement` (`setups.py`) gives x, y, z and
  quarter turns.  `SCPlacedWork.work_origin()` is the middle of the
  part's top.
* #25: Settled.  `__version__` in `scraftcnc/__init__.py`.
* #10: Settled.  Everything is placed from the origin the operator
  sets.

Found: the layer constructors take objects and millimeter floats, not
TOML values (#26).  `examples/setup/*.json` overlaps the TOML (#27).

## 2026-11-04: Fourth answers, and five more files read

* #4: Settled, b.  `module:Class.method`, as in entry points.
* #26: The user suspects every class should take strings for lengths
  (`"3mm"`, `"1.2in"`, `".321m"`) and angles (`"12.3 deg"`), with
  spaces optional.  Not sure that fully answers it.
* #27: JSON and TOML are interchangeable the way they are used here,
  so maybe support both: TOML as a `str` or `Sequence[str]`, JSON as
  `dict[str, Any]`.
* #10: Origins are messy.  Two common ones: the fixed vise jaw, and a
  corner of the stock.

Read: `tooling/tools.py` (outline only, 3753 lines), `model_cache.py`,
`examples/setup/demo_stack.json`, `show_demo.py`, `hmi/lcnc_panel.py`
(docstring and outline).  Facts:
* `demo_stack.json` is already in the plate's (work) coordinates
  (`show_demo.py` `SCShow.model_stack()`).
* The panel has no SolidCraft link.  The watcher (`sim_linuxcnc
  --watch`, in the box) draws the tool and path, and `show_demo.py`
  draws the part (`demo.py`) and the stack (`SCSetup`).  Who draws
  the setup from the comments is #28.
* The cache hash is over a JSON shape tree, with `source_digest()` of
  `TOOLING_SOURCES`.  A miss just rebuilds.
* JSON has no parentheses either, and `)` works in it too.

## 2026-11-04: Fifth answers

* #26: Settled, b.  Fields take `str | float`, and each string is
  turned into the right float.
* #27: Settled.  One reader on `dict[str, Any]`, fed by TOML (`str`
  or `Sequence[str]`) or JSON.  The writer puts TOML in the `.nc`.
* #10: Settled.  `[work_zero]` names an item, one of its named points
  (`points()` on each layer class) and an offset.  The HMI moves the
  setup so that point is the operator's G54 zero.
* #28: Settled.  `lcnc_panel` (`lcnc_hmi.py`) gets a SolidCraft
  connection, perhaps headless too.
* #8: `demo.py` read (outline).  This code will change.  Some day
  `lcnc_hmi.py` reads a directory of numbered `.nc` files and works it
  all out; not to be pursued now.  Stay on what goes in the `.nc`.
  The part is `SCPart` plus the function `model()`
  (`demo.py:72`, `demo.py:216`).

## 2026-11-04: Sixth answers; where things stand

* #30: Settled.  The marker is `SCC:` (SolidCraft CNC), e.g.
  `(SCC: [[tooling]])`.
* "#12" (first of two; probably meant for #29 or #8, to confirm): the
  `.nc` must carry all the information it needs, so new code does not
  break existing files.  Incompatible changes to the Python APIs will
  still cause trouble.
* #12: Tools in the spindle belong to a bigger topic, tool
  management.  Deferred.
* #11: Settled, c.  Keep-outs are written outright; each is about 6
  numbers.

Settled so far: #1, #4 (`module:Class.method`), #5/#25
(`__version__` in `scraftcnc/__init__.py`), #6, #10 (`[work_zero]`
item + point + offset, from the operator's origin), #11c, #23 (TOML,
with backslash-u 0028/0029 escapes), #26b, #27, #28 (the panel connects
to SolidCraft, perhaps headless), #30.

Next round, still open: #8 (also allow `module:function`?), #29 (the
header skeleton: `version`, `[setup]`, `[[tooling]]`, `[[stock]]`,
`[[part]]`, `[work_zero]`, `[[tools]]`; each item has `call`,
`location`, `height`, `orientation` plus its own arguments), and the
first "#12" answer's meaning.  How does "all the information it needs"
square with `call` naming Python (#4): write every argument out, never
rely on shop lookups?  Then #7, #9, #13-#22 as first asked.  Nothing
has been coded.

## 2026-11-04: Seventh answers

Claude's round: #29 (header skeleton), #31 (new: self-contained vs
`call`), #8, #7, #9.

* #29: The origin moves up the stack as each assembly goes on.  Table:
  top, upper left corner.  Vise: fixed jaw top (Z), jaw left (X), jaw
  inner (Y).  Parallels: no change.  Tooling plate: top (Z), left (X),
  outer (Y).  The operator may move it to the stock's top/left/outer.
  (Claude: likely replaces #10's `[work_zero]` item + point + offset;
  asked as #32.)
* #31: Settled.  The arguments written are those in the hash that
  names the `.step` file; on a miss it is built.
* #8: Somehow capture all the parts a sub-assembly needs; maybe a
  Parts class that keeps track (a thought, #33).
* #7: Settled.  Anything, as long as the same part shows up after the
  cache is deleted; a change to the code that makes a part makes old
  copies of it not matter (source digest in the key).
* #9: Settled.  Stock is a rectangular prism for now (cylinders, tubes
  later), from a generic Stock class.

## 2026-11-04: Eighth answers

* #32: Settled for now.  Start with each item placed relative to the
  origin of the item below it (`origin()` per class), but the operator
  has the last word: all that matters is that the origin is right for
  the `.nc`; the file only guesses the operator's intent.
* #33: Settled, a.  An Assembly class (name not `SCPart`) lists the
  items in stacking order and is what a program hands the writer; it
  is populated from TOML.  Change it if it doesn't work out.
* #34: Agreed (`material`, `size` x y z with units; color and
  transparency passed in with defaults), but a recommended set of
  standard materials is needed, which also serves speeds and feeds
  (#35).
* #13: Settled, a.  Optional `color` and `transparency` per item,
  defaults by kind (tooling and stock translucent, part solid).
* #14: Settled, to try.  Optional `note` per item; the panel steps
  through the items in stacking order.

## 2026-11-04: Ninth answers

* #35: Settled.  A standard list ships with `scraftcnc`; a shop may
  define its own materials, and when it does not, the standard list is
  used.  The list is its own task under `T.ds~2`; 5.2 uses short names
  only.
* #36: Settled (messy, as origins are).  On an origin set, the panel
  shows the list of possible origins; the operator says where the tool
  is now, and the panel does the rest.
* #15: Settled.  One module with writer and reader, round-trip test (a
  nice end-to-end test).  Name `scraftcnc/setup_comments.py` assumed.
* #16: Settled, a.  Rename `lcnc_panel.py` to `lcnc_hmi.py` first, as
  its own step.
* #17: Settled.  No `SCC:` lines: run it anyway, the operator's
  responsibility; they see only the 3D path, as LinuxCNC's GUI shows.

## 2026-11-04: Tenth answers

* #37: Done.  `T.sm2~5.5` Standard Materials created, Pending, with a
  draft `Details.md`.  (Found: `T.msaf~2.1` Materials Speeds and Feeds
  is closed; not read.)
* #38: Settled.  GUI design: the operator sets the origin and picks
  it from a list (table corner, vise corner, jaw corner, material
  corner, ...).
* #39: Settled.  The coding order: rename, Stock and Assembly
  classes, `setup_comments.py` with round trip, `demo.py` writes,
  panel draws, origin pick, stepping with notes.
* #19-#22: Dropped.
* #18 (multi-setup) not answered yet.

## 2026-11-04: Eleventh answers; design done

* #18: Settled.  A Mount captures exactly one setup; each remount
  does all of this again (one `.nc` per setup).
* #40: Settled, a.  One ordered `[[item]]` list, each with a `kind`.
* #41: Settled, a.  Each item carries its own keep-outs.  A vertical
  cylinder keep-out will probably come some day.
* #42: Figure it out as we go (Claude starts from `demo_stack.json`).
* #43: Settled.  Done when `./show_demo.py` draws the whole setup
  (tooling, stock, part, keep-outs) from the `.nc`'s `SCC:` lines
  alone, the operator picks the origin from a list, the panel steps
  through the items with their notes, and the round trip test passes.

The user: the design finish line is crossed.  Next, coding, in #39's
order: 1. rename `lcnc_panel.py` to `lcnc_hmi.py` (headless panel to
`lcnc_hmi_headless.py`); 2. Stock and Assembly classes; 3.
`scraftcnc/setup_comments.py` (writer, reader, round trip test); 4.
`demo.py` writes the `SCC:` lines; 5. the panel reads them and draws
the setup in SolidCraft; 6. origin pick (#36, #38); 7. stepping with
notes (#14).

Settled design, in one place: `(SCC: ...)` whole-line comments
holding TOML (`(`/`)` as backslash-u 0028/0029); `version` from
`scraftcnc.__version__`; items in stacking order, each with `kind`,
`name`, `call` (`module:Class.method` or `module:function`), the
hashed arguments written in full (strings with units allowed),
`location` relative to the origin of the item below, `orientation`,
optional `color`, `transparency`, `note`, and its `keep_out` list;
each class has `origin()`; stock is a generic Stock class (prism,
`material` short name from `T.sm2~5.5`, `size`); an Assembly class
lists the items and is handed to the writer; the reader feeds a
`dict` (TOML or JSON) back to it.  Spindle tools deferred (#12).

## 2026-11-04: Step 2

Done: `scraftcnc/assembly.py` with `SCStock` (prism; `material`,
`size` as `str | float`, through `shops.measure(..., LENGTH)`; `seat()`,
`origin()` = top, smallest X, smallest Y taken as "outer", the side
facing the operator; `keep_out()` empty), `SCItem` (one `[[item]]`)
and `SCAssembly` (`to_dict()` / `from_dict()`, errors name the item
as `item N ('name')`).  `tests/test_assembly.py` (5 tests).  Checkers
clean.  `SCStock` follows `SCLayer` only in part: no `model()` or
`cacheable()` yet (no SolidCraft model).  Left to confirm: outer = -Y,
`orientation` as quarter turns 0-3, keep-out boxes as low/high X Y Z
from the item's origin, floats meaning millimeters.  Next: step 3,
`scraftcnc/setup_comments.py`.

## 2026-11-04: Step 3

Done: `scraftcnc/setup_comments.py`: `write(assembly)` gives the
`(SCC: ...)` lines (first `version = "..."`, then `[[item]]` tables,
plain keys first and `[item.args]` sub-tables last; inline tables
inside lists; a list too long for 79 columns wraps one element a
line).  Strings escape `(`, `)`, quotes, backslashes, control
characters and everything outside printable ASCII as backslash-u.
`read(lines)` takes only whole-line `(SCC: ...)` comments (leading
spaces allowed), raises `ValueError` for a line that starts `(SCC:`
but is not one, gives `None` with no setup lines, and names the
program line in errors (`read_file(path)` adds the file).  Version:
missing or not dotted numbers is a `ValueError`; newer than
`__version__` warns `SCSetupVersionWarning` (`warnings.warn`), skips
unknown top-level keys and reads on (unknown keys inside items are
still errors).  `__version__ = "0.1.0"` added to
`scraftcnc/__init__.py`.  `tests/test_setup_comments.py` (8 tests);
checkers clean.  Left: a single string longer than a line is not
split.  Next: step 4, `demo.py` writes the `SCC:` lines.

## 2026-11-04: Answers on step 2's choices

* #44: Settled.  +Y is away from the operator, -Y closer; -X left, +X
  right.  So "outer" is -Y (smallest Y), as step 2's `SCStock.origin()`
  has it.

## 2026-11-04: Step 4

Done: `scraftcnc/demo.py` has `demo_assembly(material)` (built from
`demo_stack.json`'s five layers, then `SCStock` "aluminum_6061"
4-1/2 x 3-1/2 x 1/2 in, then the part `scraftcnc.demo:model`) and
`with_setup(gcode, assembly)`, which puts the `(SCC: ...)` lines after
the leading `%`/comment lines; `main()` prints it (67 lines).  Test
`TestDemoSetup` in `tests/test_setup_comments.py` (round trip).
Checkers clean; `tests.test_setup_comments`, `tests.test_assembly` pass.
Shortcuts: `call` names the layer classes in `tooling/mount.py`
(`SCTableLayer`, `SCMachineViseLayer`, `SCParallelLayer`, `SCPlate`),
which take objects, not names: `args` holds the shop `type` names
(and the vise's `opening`), so step 5 needs factories taking names.
Locations are still `demo_stack.json`'s work coordinates (absolute,
the bottom's Z), not relative to the item below (#32), and written as
millimeter floats with long tails (`38.099999999999994`).  No
keep-outs yet.  The part's `args` (`material`, `thickness`) are
placeholders; `model()` takes objects.  Orientation -90 deg is 3.
* #45: Settled.  Stock never has a 3D model: it is shown as a wire
  outline only, with the finished part shown inside it.
* #46: Settled.  `orientation` is quarter turns about Z, right hand
  rule: the item's +Y points to +Y at 0, -X at 1, -Y at 2, +X at 3.
* #47: Settled.  Keep-out boxes: six lengths, low X Y Z then high X Y
  Z, from the item's origin; a vertical cylinder later.
* #48: Settled.  A number with no unit is a count.  Every length and
  angle must carry a unit name; a plain number for one is an error.
* #49: Each object instance has a name; keep a dictionary of them and
  use it to get to the basic object (`call` + `args` refer to named
  objects, not to objects themselves).  Will change the code somewhat.
  (Claude's reading: a name -> object registry; `args` name the shop
  entries / objects; the reader resolves names through it.)
* Step 4 shortcuts to fix: `args` not the real cache-key arguments
  (#49), locations absolute mm floats (to be relative, #32, with
  units, #48), no keep-outs (#47).
* #46 corrected by the user: quarter turns counterclockwise about Z,
  the item's +X pointing to +X at 0, +Y at 1, -X at 2, -Y at 3, and
  repeating.  (Replaces the "+Y at 0" wording above.)

## 2026-11-04: Step 4b, part 1

* `scraftcnc/assembly.py`: a length with no unit is an error (#48: a
  number with no unit is a count); `millimeters()` raises
  `TypeError`.  `length_text(mm)` writes inches to 4 places when
  exact, else millimeters to 4 places; `SCItem.to_dict()` uses it for
  `location` and `keep_out`.  A missing `location` is `"0 in"` x3.
* `orientation` documented (#46, the user's correction): quarter
  turns counterclockwise about Z; the item's +X axis points to +X at
  0, +Y at 1, -X at 2, -Y at 3.
* Tests: lengths are strings with units; round trips compare lengths
  to 1e-6 mm (`tests/test_assembly.py` `assert_same()`); plain
  numbers are checked to be refused.  `demo_assembly()` already used
  units, unchanged.  `tests.test_assembly` and
  `tests.test_setup_comments`: 14 tests OK; checkers clean.

Left: demo locations relative to the item below, with units (#32);
keep-outs (#47); the #49 name dictionary.  Open question:
`setups.py` line 13 says counterclockwise is positive, but the
`SCPlacement` docstring (lines 116-117) says clockwise; #46 is now
counterclockwise, so `SCPlacement` needs checking.

## 2026-11-04: Step 4c

* Turn direction checked, no code changed.  `SCPrism.quarter_turned()`
  (`tooling/tools.py:437-451`) turns clockwise (+X to -Y), and
  `_SCReader.turns()` (`setups.py:458-476`) makes
  `round(-degrees / 90) % 4`.  So the JSON's degrees are
  counterclockwise (`setups.py:13` is right) while `SCPlacement.turns`
  counts clockwise (`setups.py:116-117` is right too).  `demo.py`'s
  `_TOOLING` copies `SCPlacement`'s clockwise turns (vise 3 for
  "-90 deg", grid plate 1 for "90 deg"), which is the opposite of #46.
  For the user: flip `_TOOLING`'s turns (to 1 and 3) or convert where
  the assembly is read.
* #32 (relative locations) not started: it needs the X/Y extents of
  the table, the vise's fixed jaw and the grid plate (only their
  heights / `seat()`s are in `mount.py`), which ran past the time
  limit.  `seat()`: table `(0, 0, thickness)`; vise
  `(0, -gap_center, bed_top)` when turned; parallel and plate
  `(0, 0, height)`.

## 2026-11-04: Answers #49-#51

* #50: Settled, a.  Every rotation about an axis follows the right
  hand rule.  Fix everything (`SCPrism.quarter_turned()`,
  `SCPlacement`, `setups.py`'s reader, `demo.py`'s `_TOOLING`) to
  count quarter turns counterclockwise (#46).
* #51: Settled for now.  A script builds the table, vise and grid
  plate layers without SolidCraft and prints their sizes, for the
  relative locations (#32); revisit when the HMI is updated (next
  phase).
* #49: Each class has a dictionary mapping a name to the object.
  Same-name objects: disallow or disambiguate (NAME1, NAME2); the user
  left the choice to Claude.  Claude's choice: disallow (a duplicate
  name in a class is an error naming both), since silent renaming
  would make `args` refer to the wrong object.

## 2026-11-04: Step 4d

Quarter turns now follow the right hand rule about +Z (the user's
#50/#46): one turn sends +X to +Y.  Only the count flipped; the
geometry built is meant to stay the same.  Changed:
`SCPrism.quarter_turned()` (counterclockwise, new `turns` argument),
`placement_matrix()`, `_turned_pair()` (`SCCNC.remap()`),
`_SCReader.turns()` (`round(degrees / 90.0)`), the SolidCraft move
angle and the report's degrees in `setups.py`, the turned vise's
keep-out in `tooling/mount.py` (3 turns), `demo.py` `_TOOLING`
(1 <-> 3), and the tests' literal counts.  The JSON examples (in
degrees, counterclockwise positive) are unchanged.  The user should
check the vise and grid plate in SolidCraft.

## 2026-11-04: Step 4e

Sizes found (script builds `SCSetup` from `demo_stack.json`, no
`model()`): table 762 x 266.7 x 63.5 mm (30 x 10.5 x 2.5 in); vise
Kurt D688: base 400.05 x 152.4, bed top 67.056 (base 12.7 + body
35.306 + rails 19.05), jaws 25.4 x 152.4 x 44.069, jaw plate 18.415,
`gap_center(5.5 in)` -86.36 (grows with the opening, so the movable
jaw is +X unturned, the fixed jaw -X); parallels 152.4 x 3.175 x
38.1; grid plate 139.7 x 266.7 x 12.7 (turned 1).  Origins (work mm):
table (-330.2, 171.45, -130.556); vise fixed jaw (-25.4, 107.95,
-38.481); grid plate (-82.55, -31.75, -12.7).  Relative locations:
table 2, 1.5, -7.64 in (absolute); vise 15, -8.65, 0 in; parallel A
3, -0.0625, -0.985 in; B 3, -5.4375, -0.985 in; grid plate 3, -2.75,
0.515 in; stock 3.25, 1.25, 0 in.  Assumed: fixed jaw sits on the
body (top 92.075 mm above the base bottom); its inner face is the jaw
plate's face (`gap_center - opening/2`); turn 3 sends unturned -X to
+Y.  `demo.py` not changed yet (time limit).

## 2026-11-04: Step 4e, part 2

`demo.py`'s `_TOOLING` now holds the relative locations above (it is
used only for the `.nc` comments; the models are still drawn from
`demo_stack.json`'s absolute positions, unchanged).  The stock's
location is (3.25, 1.25, 0) in.  The comment over `_TOOLING` and
`demo_assembly()`'s docstring say locations are the center of the
item's bottom from the origin handed up by the item below (#32), and
that the vise's origin assumes the fixed jaw's top 92.075 mm above
its bottom (unverified; 111.125 mm on rails).  Left: the part's
location is still `(0, 0, -1/2 in)` (work frame); what it should be
relative to the stock is to decide.  Checkers clean;
`test_setup_comments`, `test_assembly` pass (14).

## 2026-11-04: Step 4f plan (#49)

Found: `setups.py:82-98` already has hand-built name dictionaries
(`TABLES`, `MACHINE_VISES`, `PARALLEL_TYPES`, `PARTS`), built by
comprehensions, so a duplicate name silently wins.  The grid plate
is an `SCGridPlate` (`PARTS`), not the `SCPlate` that `_TOOLING`
names.  The cache key is `tooling_shape(object)` (the whole object),
not its name.

Plan:
* Registry: `SCMillTable`, `SCMachineVise`, `SCParallel`,
  `SCGridPlate` each get a class-level `dict[str, Self]`, filled in
  `__post_init__()` on construction (the module-level constants
  register themselves on import), and a class method `named(name)`.
  A duplicate raises `ValueError` naming both (the repr of each).
  `setups.py`'s four dictionaries become these registries.
* Calls: a class method on each layer that takes strings:
  `mount:SCTableLayer.named` `{table = "Mikini 1610L"}`;
  `mount:SCMachineViseLayer.named` `{vise = "Kurt D688", opening =
  "5-1/2 in"}` (`turned` comes from `orientation`, not `args`);
  `mount:SCParallelLayer.named` `{parallel = "..."}`;
  `tools:SCGridPlate.named` `{name = "Grid plate"}`.
* Reader: `importlib` the module, `getattr` down `Class.method`, call
  with `**args`; `named()` does the lookup.  An unknown name raises
  `KeyError` listing the known names.
* #31: if the hash stays `tooling_shape(object)`, `args` are not
  what is hashed (#57).
* Tests: duplicate name error (both named); `named()` round trip
  for each class; unknown name message; each `_TOOLING` call
  resolves to a layer equal to the one `demo_stack.json` gives.
* Steps (~3 min each): (a) registry mixin plus tests; (b) apply to
  the four classes, `setups.py` uses it; (c) layer `named()` methods;
  (d) `_TOOLING` and the reader's resolution, tests; (e) #57.

Questions:
* #57: Cache key: (a) keep hashing the full object, and write the
  full object's fields as `args`; or (b) hash `call` + `args` plus the
  source digest (the definitions in `setups.py` must then be in
  `TOOLING_SOURCES`)?
* #58: Registry key: the `name` field as is (e.g. "Kurt D688"), or
  a short identifier (`kurt_d688`)?
* #59: Should cutters (`tools.toml` kinds) get the same registry now,
  or later with tool management (#12)?

## 2026-11-04: Answers #57-#59

* #57: Settled, b.  The cache key hashes `call` + `args` plus the
  source digest; the name dictionaries in `setups.py` join the digested
  sources.
* #58: Settled, a compromise: keys are short identifiers with
  underscores (`kurt_d688`); the user interface shows each underscore
  as a space.
* "#59" answer: "Consistent: the children use the parent origin; see
  if it eventually breaks."  Claude takes this as #56 (the part is
  located from the stock's origin), to confirm; #59 (cutter
  dictionaries now or later) still open, as is #55.

## 2026-11-04: Answers #52-#54

* #52: The user asked for a recommendation (Claude: a headless
  `solidcraft-cli` test that turns an asymmetric box a quarter turn
  and checks where it lands).
* #53: Yes: run `TestLive.test_units_only_to_build` against the last
  git commit, to see whether it failed before today.
* #54: Agents may run up to 8 minutes, and should estimate how far
  they are from done.
* #49: Go ahead with the name dictionary, in the five steps of the
  step 4f plan.

## 2026-11-04: #49 steps a-b

* (a) `scraftcnc/tooling/registry.py`: `key(name)` (lower case, each
  run of other characters one underscore: "Kurt D688" is
  `kurt_d688`) and `SCRegistry[T]` (`add()`, `named()`).  The key is
  derived from `name`, no new field.  `named()` takes a key or a
  display name, so `examples/setup/*.json` ("Mikini 1610L") still
  works.  A different object under a key already used is a
  `ValueError` naming both; an equal one is kept as the first (the
  shop's "Grid plate" equals `tools.GRID_PLATE`).  Unknown names are
  a `KeyError` listing the keys.  Tests: `tests/test_registry.py`.
* (b) `SCMillTable`, `SCMachineVise`, `SCParallel`, `SCGridPlate`
  each have `REGISTRY: ClassVar[SCRegistry[...]]` and a class method
  `named()`; the registries are filled explicitly after `GRID_PLATE`
  in `tools.py` (not in `__post_init__()`, so `dataclasses.replace()`
  copies, as the tests' `FLAT_PLATE`, do not collide).  `setups.py`'s
  `TABLES`, `MACHINE_VISES`, `PARALLEL_TYPES`, `PARTS` are gone; the
  shop's grid plates join `SCGridPlate.REGISTRY`.  `test_setups` and
  `test_model_cache` patch `SCGridPlate.REGISTRY.items` with key
  `grid_plate`.
* Next: (c) layer `named()` methods, (d) `_TOOLING` and the reader,
  (e) #57.

## 2026-11-04: #53 result, and answers

* #53: `TestLive.test_units_only_to_build` passes at the last git
  commit and in today's tree (11 s each); not reproduced.  Likely the
  headless `solidcraft-cli` build failed once (load, or another
  SolidCraft running) and the code quietly built in-session (2 unit
  changes).  #60 (new): warn on that fallback; Claude's default:
  later.
* #52: Yes: a headless turn direction test is being added
  (`tests/test_turn_direction.py`).
* #55: The user has no data; Claude keeps 92.075 mm (the fixed jaw on
  the body); the user will say if it looks wrong.
* #59: Settled.  Cutters get name dictionaries now (after #49 a-b).
* #56: Asked again (the part located from the stock's origin).
* Step (d) writer: each registered object gets a `key` property
  (`registry.key(name)`), written in `args` (Claude's choice).

## 2026-11-04: #52 result

* #52: Settled.  SolidCraft's Z rotation is counterclockwise-positive
  (right hand rule): a 30 x 10 x 5 mm box along +X, turned with
  `setups.py`'s `solid.move(..., angle="90 deg")`, runs along +Y.
  `placement_matrix(1)` maps +X to +Y.  No sign needs to change.
  `tests/test_turn_direction.py` checks both (the SolidCraft part is
  skipped without `solidcraft-cli`; 0.2 s).
* #56: Settled, yes: the part is located from the stock's origin.  The
  user's caveat: in an assembly of parts, a child/parent relationship
  is not always discernible (#61, later).
* #60: The user has no view; Claude's choice: yes, print a one-line
  warning when the headless build falls back to the design's session
  (small step, after #59).
* #55: The user will say when something looks off.

## 2026-11-04: #49 steps c-d

* (c) `SCMillTable`, `SCMachineVise`, `SCParallel`, `SCGridPlate`
  have a `key` property (`registry.key(name)`).  `SCTableLayer.named(
  table)`, `SCMachineViseLayer.named(vise, opening)` (`opening` a
  unit string or millimeters; checked against `max_opening`, a
  `ValueError` naming the vise) and `SCParallelLayer.named(parallel)`
  in `tooling/mount.py`.  The vise is never `turned` by `named()`:
  the item's quarter turns turn it, as `setups.py` builds it.  The
  grid plate uses `SCGridPlate.named(name)` as is (the JSON builds
  the `SCGridPlate` itself as the layer).
* (d) `demo.py` `_TOOLING` calls these, with keys (`mikini_1610l`,
  `kurt_d688`, `parallel_1_1_2_in_a`, `grid_plate`); the wrong
  `mount:SCPlate` is now `tools:SCGridPlate.named`.
  `assembly.resolve(item)` imports the module, follows `Class.method`
  and calls with `**args`; failures are a `ValueError` naming the
  item.  Test (`tests/test_assembly.py` `TestResolve`): each tooling
  call equals the layer `demo_stack.json` gives; the stock resolves
  to `SCStock`; the part's `scraftcnc.demo:model` (needs SolidCraft)
  is only checked to import.  Tests for `named()` in
  `tests/test_mount.py`, `key` in `tests/test_registry.py`.
* Next: (e) #57 (cache key from `call` + `args` + source digest).

## 2026-11-04: #56 done

The part's `location` in `demo_assembly()` (`scraftcnc/demo.py`) is now
measured from the stock's origin (top, left, outer corner), like every
other item: `("2-1/4 in", "1-3/4 in", "-1/2 in")`, in millimeters.  It
assumes the part is centered in the stock in X and Y and as thick as it.

## 2026-11-04: #57 cache key

* (e) `model_cache.py`: `ITEM_SOURCES` (`assembly.py`, `geometry.py`,
  `setups.py`, `tooling/mount.py`, `tooling/registry.py`,
  `tooling/tools.py`), `item_shape(item)` (`call`, `args`, and
  `source_digest(ITEM_SOURCES)`), `item_key(item)` (its hash) and
  `keyed_by_item(model, item)` (the model with `item_shape()` as its
  tree, so `SCModelCache.path()` files it as `NAME__ITEM_KEY.step`;
  a vise's two sections stay apart by name).  Location, orientation,
  color and note are no part of the key.
* No caller uses it yet: nothing inserts `resolve()`d items into the
  cache.  `show_demo.py`, `setups.py`, `mount.py`, `tools.py` and
  `cutter_models.py` still hash the object (`tooling_shape()`, with
  `tools.TOOLING_SOURCES`, which lacks `setups.py` and `registry.py`).
* Tests: `tests/test_model_cache.py` `TestItemKey` (same key for
  same call+args, different for other args, changes with the digest,
  sources listed, path from `keyed_by_item()`).
* Next: the reader (HMI) builds each item's models with `resolve()`
  and inserts them with `keyed_by_item()`.

## 2026-11-04: #60 fallback warning

`SCModelCache.create_headless()` (`model_cache.py`) now warns on `stderr`, "model_cache: headless build of NAME failed (REASON); building in this session", when `solidcraft-cli` is on the `PATH` but fails.  With no CLI the fallback stays quiet (expected; the live tests use `no-such-program`).  Tested by `TestHeadlessFallback` in `tests/test_model_cache.py`, with no SolidCraft.

## 2026-11-04: #59 cutter dictionaries

* Cutters had no class: each tool of the tools files is a `dict`
  (`shops.read()`, listed by `cutter_models.shop_tools()`).  New
  frozen dataclass `SCCutter(kind, tool)` in
  `tooling/cutter_models.py`, with `REGISTRY` (`SCRegistry("cutter")`),
  `named()`, and `name`/`key` properties; `register_cutters(shop,
  registry)` adds every tool of a shop.
* Scope: one registry for all kinds (the names in
  `examples/shop/tools.toml` are unique across kinds), global, filled
  at import from `EXAMPLE_SHOP`, as `setups.py` fills
  `SCGridPlate.REGISTRY`.  Not per machine: `SCTool` (`machine.py`)
  is the per-tool-table object (T number, feeds for a material), and
  `SCMachine.named()` already finds those.
* Tests: `tests/test_registry.py` `TestCutters` (round trip for every
  tool, unknown name, duplicate key).

## 2026-11-04: #62 answer

* #62: Settled, a.  Shops are independent: neither knows about
  another, and different tools change everything, so no cross feed.
  The name dictionaries are filled from the shop in use only (not
  always from the example shop; never two shops mixed).  To do before
  step 5.

## 2026-11-04: #62 per-shop dictionaries

* New `scraftcnc/tooling/shop_registries.py`, `use_shop(shop)`: empties
  every registry (`SCCutter`, `SCMillTable`, `SCMachineVise`,
  `SCParallel`, `SCGridPlate`) and fills them from one shop: cutters
  and grid plates from the shop files; tables, the vise, parallels and
  `tools.GRID_PLATE` still from the built-in constants (no kinds for
  them in the shop files yet).
* No filling at import any more (`tools.py`, `cutter_models.py`,
  `setups.py`).  Called by `demo.cut_demo()` (its `SHOP_FILE`) and
  `SCSetup(setup_json, *, shop_file=SHOP)` (so `show_demo.py` too).
  `lcnc_hmi.py` names no tooling yet, so it does not call it.
* Tests: `setUpModule()` with the example shop in `test_registry`,
  `test_assembly`, `test_setup_comments`, `test_mount`,
  `test_cutter_models`, `test_tools`; `TestUseShop` checks nothing of
  an earlier shop is left.  `Tool_Models.md` regenerated.

## 2026-11-04: Answers #63-#64; one agent at a time

* The user: one sub-agent at a time (tokens).
* Test suite: drop the grid (tooling) plate's chamfers in the tests;
  they add no value there and cost ~5 minutes to rebuild after each
  change to `tools.py` / `mount.py`.
* #63: A big issue.  The user's long-term goal: someone sends their
  design and shop description to another shop, and a reconciliation
  changes the tooling and process so the design can be made there.
  For now (Claude's interim): the caller chooses the shop once;
  `SCSetup` stops calling `use_shop()` itself.
* #64: Settled.  Only the shop's own tools are shown.  Development
  works in the "Developers Shop" (today's example shop); the built-in
  objects (tables, vise, parallels, `GRID_PLATE`) belong in its files
  eventually.
* #63: `T.ipfds~5.6` Import a Project from a Different Shop created,
  Pending, with a draft `Details.md`.

## 2026-11-04: Chamfer-free plate in tests

* `tests/flat_plate.py` holds `FLAT_PLATE` and `use_flat_plate()`
  (patches `SCGridPlate.REGISTRY`), shared by `test_setups` and
  `test_model_cache` (removes their R0801 duplicate).
* No other test models `GRID_PLATE` (the `use_shop` modules only
  read it); `test_mount`'s `SMALL_PLATE` keeps its 25 small chamfers
  for its volume check (needs SolidCraft).
* `test_setups` still took over 4 minutes with the flat plate (not
  the chamfers); its slow test is still to be found.

## 2026-11-04: SCSetup no longer picks a shop

* #63: `SCSetup(setup_json)` lost `shop_file` and its `use_shop()`
  call, which refilled the chamfered plate over `use_flat_plate()`
  (`tests.test_setups` went from over 240 s to 5 s).  `setups.main()`,
  `keepout.main()` and `show_demo.py`'s `main()` call `use_shop()`
  once; `demo.cut_demo()` already did.  `test_setups`,
  `test_model_cache` and `test_keepout` call it in `setUpModule()`.
* #64: `use_shop()` registers only the shop's grid plates (the
  built-in `GRID_PLATE` only when the shop lists none).

## 2026-11-04: Full suite

* `python3 -m unittest discover -s tests -t .`: 557 tests, OK (12
  skipped), 183 s wall clock, load under 1.  No failures, no errors,
  so no fixes were needed.
* Per-module times are not in the log (unittest prints none); not
  rerun to measure them.

## 2026-11-04: Step 5 plan

Plan only, nothing coded.  Facts found:
* Only `SCStock` has `origin()` (`assembly.py:146`).  The mount
  layers (`tooling/mount.py`, five `seat()`s) and `SCGridPlate`
  (`tools.py:3481`) have `seat()` only.  `demo.py`'s locations are
  still absolute work coordinates (#32 not done, step 4c), and its
  turns are clockwise (#46 not applied).
* `lcnc_hmi.py` has no SolidCraft link; programs open through
  `SCPanel.open()` (`lcnc_hmi.py:1069-1078`), used by `main()`, Open
  and the command port.  `show_demo.py` connects with
  `connect(str(port))` + `SCPyBind(transport)` (`model_stack()`).
* Wire outline: `sketch.line3d(points=[[x,y,z],...])` (one line per
  segment; `plot.py:711` already uses it).  12 edges = two closed
  loops of 5 points plus 4 verticals.
* Item colors: no color/transparency call was searched for (only
  sketch/line calls, as asked); `setups.py` `SCSetup.model()` already
  draws translucent tooling, so step (c) reuses whatever it calls.

Design:
* New module `scraftcnc/setup_view.py`: `place(assembly)` (pure math:
  absolute `(x, y, z, turns)` per item, chaining each item's location
  from the origin of the item below, turns counterclockwise) and
  `draw(assembly, solidcraft, cache)` (tooling through `resolve()` +
  `SCModelCache` with `keyed_by_item()`, stock as `line3d` outline,
  part through its `call`).  `lcnc_hmi.py` only calls it.
* Panel flags: `--solidcraft PORT` (none: no drawing, as today) and
  `--shop FILE` (default the example shop; `use_shop()` once in
  `main()`, #63).  In `SCPanel.open()`: `read_file()`; `None` -> run
  without a setup (#17); a `ValueError` -> shown in the message area,
  the program still opens.  Drawing runs in a thread so the window
  stays live; the panel stays stopped (the user starts runs).
* `origin()` to add (point on top of each, in the item's own frame):
  `SCTableLayer`, `SCMachineViseLayer` (fixed jaw top inner corner?),
  `SCParallelLayer`, `SCGridPlate`/`SCPlate`; then `demo.py` writes
  relative locations with units and counterclockwise turns.
* Part: `scraftcnc.demo:model` needs a live SolidCraft; called with
  the session, placed at the stock's origin.  Its `args` are still
  placeholders (step 4), so it needs a name-taking wrapper.
* Tests (no SolidCraft): `place()` on a hand-built assembly (turns
  0-3, chained offsets); `draw()` with a fake `SCPyBind` recording
  calls (one `line3d` set for stock, one insert per tooling item,
  defaults: tooling/stock translucent, part solid, #13a); panel
  `--headless --dry-run` opening a `.nc` with and without `SCC:`
  lines.  One optional live check: `SCRAFTCNC_SOLIDCRAFT=1`, the demo
  `.nc` drawn in `solidcraft-cli`.

Steps (~8 min each, one agent at a time):
* (a) `origin()` on the four tooling classes, tests.
* (b) `demo.py` writes relative, unit-carrying locations and
  counterclockwise turns; round trip test still passes.
* (c) `setup_view.place()` + tests.
* (d) `setup_view.draw()` with the fake session + tests.
* (e) part wrapper (`module:function` taking names) + test.
* (f) `lcnc_hmi.py` flags, `open()` hook, thread + headless tests.
* (g) optional live check; `show_demo.py` passes `--solidcraft`
  and drops `model_stack()` (#43).

Questions:
* #66: Who draws, the panel (`--solidcraft PORT`) or still
  `show_demo.py`?  (a) the panel, `show_demo.py` only passes the
  port; (b) both, during a changeover.
* #67: The vise's origin: (a) the fixed jaw's top inner edge, middle
  of its width; (b) its corner nearest the operator?
* #68: Opening a second `.nc` in the panel: (a) clear the old setup
  from SolidCraft first (a new design); (b) draw on top?

Correction (Claude, checked `demo.py:384-`): the plan's finding 2 is
wrong.  `_TOOLING` already has relative locations with units (step
4e) and counterclockwise turns (step 4d, the vise is 1), so plan step
(b) is dropped.  #67 is already settled by #29: the vise's origin is
the fixed jaw's top (Z), left (X), inner (Y) corner.

## 2026-11-04: Answers #66, #68

* #66: Settled, a.  Only the panel draws the setup; `show_demo.py`
  passes the port.  The user's aim: `show_demo.py` gets much simpler
  once this works, just starting the panel (the user wrote
  `sc_lcnc.py`, confirmed to mean `lcnc_hmi.py`) and letting
  it build the mounts.
* #68: Settled, "do it right": opening a `.nc` computes the set of
  keys it needs; keys already shown in SolidCraft are kept, those no
  longer needed are removed, new ones added (Python set operations).
  Claude's detail: two identical parallels share an `item_key`, so a
  shown body's key is `item_key` plus its placement (and color,
  transparency); a moved item is then a remove plus an add.  Goes
  into step (d) `draw()` (keep a dict key -> SolidCraft body), and
  step (f) calls it on every open.

## 2026-11-04: Step 5a

* `origin(turns=0)` on `SCTableLayer` (`tooling/mount.py:172`, top,
  min X, max Y), `SCMachineViseLayer` (`mount.py:326`, fixed jaw top
  92.075 mm, inner face `gap_center - opening/2`, left end; `turned`
  adds 3 turns), `SCParallelLayer` (`mount.py:457`, middle of its top
  edge) and `SCGridPlate` (`tooling/tools.py:3532`, top, min X, min
  Y).  Helpers `quarter_turn()` and `left_corner()`
  (`tools.py:509-550`).  Unlike `SCStock.origin()`, each takes the
  item's quarter turns and returns the point in the setup frame
  (turned), since "left" and "outer" are setup directions.
* Tests: `tests/test_mount.py` `TestOrigins` (5); `test_mount` and
  `test_tools` pass (95); checkers clean.
* Agree with step 4e's numbers when the JSON's turns are used (vise 3,
  grid plate 1).  Disagreements (not changed): (1) `demo.py`
  `_TOOLING` turns are vise 1, parallels 1, grid plate 3, the opposite
  of `demo_stack.json` read by `_SCReader.turns()` (vise 3, grid plate
  1); with vise 1 the fixed jaw would be at -Y and the vise origin
  would not match the step 4e locations.  (2) Parallels pass the
  origin through (#29): `_TOOLING` places the grid plate from the
  vise's origin, so step 5c's `place()` must skip parallels when
  chaining; `SCParallelLayer.origin()` is not in the chain.

## 2026-11-04: `_TOOLING` turns fixed

Step 5a found `_TOOLING`'s quarter turns opposite to
`demo_stack.json` (step 4d flipped them, wrongly: the JSON's degrees
are already counterclockwise, so "-90 deg" is 3).  Now vise 3,
parallels 3, grid plate 1, which is what the step 4e locations were
measured with.  Also for step 5c: parallels pass the origin through,
so `place()` chains the grid plate from the vise's origin.

## 2026-11-04: Step 5c

* `scraftcnc/setup_view.py`: `SCPlaced` (item, absolute x, y, z of
  the bottom's center in mm, turns) and `place(assembly, resolver=
  resolve)` (`setup_view.py:50`).  The first location is absolute;
  each later one adds to the origin handed up (absolute position +
  `origin(turns)`).  Parallels are recognized as `SCParallelLayer`
  objects (all items are kind `"tooling"`; there is no parallel kind)
  and hand up nothing new.  The top item (the part) is never resolved,
  so no SolidCraft is needed.
* `SCStock.origin(turns=0)` (`assembly.py:146`) now takes turns and
  uses `left_corner()`, like the step 5a methods (same at 0).
* `tests/test_setup_view.py` (4 tests): turns 0-3, chaining,
  parallels passing through, and the demo: all five tooling items
  land on `demo_stack.json`'s locations and heights; stock and part
  bottoms both at (0, 0, -1/2 in).  No mismatch found.  Checkers
  clean.
* Next: step 5d, `setup_view.draw()`.

## 2026-11-04: Step 5d

* `scraftcnc/setup_view.py`: `SCSetupView(solidcraft, cache=None,
  resolver=resolve)` (`setup_view.py:225`).  `show(assembly)`
  (`:253`) places the items, keys each with `display_keys()` (`:141`:
  kind, `item_key()`, x y z rounded to 1e-6 mm, turns, color,
  transparency, and a count so twins differ), removes `shown -
  needed`, draws `needed - shown`, keeps the rest; `counts` is
  (added, kept, removed).  `shown` maps key to `SCShown` (bodies,
  curves, `:124`).
* Drawing (`draw()`, `:294`): stock is a 3D sketch of 12 edges
  (`box_edges()`, `:192`; 6 `sketch.line3d` calls); tooling goes in
  through `cache.insert(keyed_by_item(...), placement_matrix(...))`
  (`inserted()`, `:351`), else built at the origin and moved
  (`built()`, `:386`, as `SCPlacement.model()`); the part takes the
  build path (`thing.model(solidcraft, (0, 0, z))`).  Then
  `appearance.assign(opacity=..., color=...)`: `opacity()` (`:174`)
  is tooling/stock 0.35, part 1.0, unless the item's `transparency`
  is above 0.  Removal: `solid.remove(bodies)`,
  `sketch.delete(entities=curves)`.
* Tests: `tests/test_setup_view.py` `TestSetupView` (5, fake
  session, cache and resolver); 9 tests OK; checkers clean.
* Open: (1) a `transparency` of 0.0 means "kind default", so an item
  can not ask for fully solid tooling; (2) `sketch.delete` leaves an
  empty stock sketch behind (no sketch-delete command looked for);
  (3) moving a lower item moves everything chained above it, so all
  of those are redrawn (correct, but not "one item"); (4) the part's
  object must have `model(solidcraft, point)` (step 5e); (5) the
  stock sketch has no color or opacity.  Next: step 5e.

## 2026-11-04: Step 5e

* `scraftcnc/demo.py`: the part item's `call` is now
  `scraftcnc.demo:demo_part` (`material`, `thickness` as a unit
  string), giving a frozen `SCDemoPart(material, thickness mm)`;
  making one touches no session.  `SCDemoPart.model(solidcraft,
  point)` (what `SCSetupView.built()` calls) reads the shop for the
  corner rounding radius, builds the plate with its top at
  `point z + thickness`, moves the outline's middle (2, 1.5 in) onto
  the point, and returns `["Plate"]`.  `model()`'s building moved to
  `_build(solidcraft, part)`; `demo_shape(top, thickness, rounding)`
  makes the `SCPart` (also used by `main()`).  No units command or
  appearance in `SCDemoPart.model()` (the view assigns opacity).
* Tests: `TestResolve` now resolves the part (`SCDemoPart`,
  "6061 aluminum", 12.7 mm); `TestSetupView.test_demo_part` shows
  `demo_assembly()` on the fake session with `SCDemoPart.model`
  patched, and checks it is reached once with opacity 1.0.  27 tests
  OK; checkers clean; `python3 -m scraftcnc.demo` still runs.
* Open: `SCDemoPart.model()` never run in a real SolidCraft (its
  move and Z untested live); `material` is the display name ("6061
  aluminum"), not the stock's short name.  Next: step 5f
  (`lcnc_hmi.py` flags, `open()` hook, thread).

## 2026-11-04: Step 5f

* `scraftcnc/hmi/lcnc_hmi.py`: flags `--solidcraft PORT` (absent:
  no drawing, as before) and `--shop FILE` (default `SHOP_FILE`,
  `examples/shop/home_shop.toml`, as `demo.py`); `main()` calls
  `use_shop()` once (#63; a `SCShopError` exits 1).  With
  `--solidcraft`, one long-lived `SCSetupDrawer(SCSetupView(SCPyBind(
  connect(port)), SCModelCache()))` is made at start and set as
  `panel.drawer` (#68's set difference works across opens).
* `SCSetupDrawer` (dataclass): `draw(assembly)` puts it as `pending`
  and starts a daemon thread if none is busy; the thread draws until
  nothing is pending, so a newer open replaces older waiting ones.
  Errors go into a `queue.SimpleQueue`; `SCPanel.poll()` shows the
  newest in the message line (Tk only touched on the main thread).
  `wait()` for tests.  `SCView` is a `Protocol` (`show()`).
* `SCPanel.open()` (main, Open button, command port) now calls
  `open_setup(path)`: `read_file()`; `None` -> nothing (#17);
  `OSError`/`ValueError` -> "Setup not read: ..." in the message
  line, the program stays open.  Never starts a run.  The headless
  panel is the same `SCPanel` (its fake `tk`), so it works there too.
* Tests: `tests/test_lcnc_hmi.py` `TestSetupDrawing` (5: drawn, no
  setup, bad line, draw error to poll, newest only) and
  `TestMainSolidCraft` (2: no view without the flag, one with it;
  SolidCraft mocked).  42 tests OK; checkers clean.
* Not done: never run against a live SolidCraft; `show_demo.py` still
  draws with `model_stack()` and does not pass `--solidcraft` (step
  5g).  The Tools window still reads `SHOP_FILE`, not `--shop`.

## 2026-11-04: Step 5g

* `show_demo.py`: `model_part()` and `model_stack()` are gone (with
  `STACK` and the `json`, `SCSetup`, `SCModelCache`, `SCPyBind`,
  `connect`, `use_shop` imports); `write_program()` runs
  `python3 -m scraftcnc.demo` (no port: G-code only, with the
  `with_setup()` `(SCC: ...)` lines), and the panel is started with
  `--solidcraft PORT`, so the whole setup comes from the `.nc` alone
  (#43, #66a).  Not run (the user runs it).
* Lost on the way: `view.apply(view="iso")` after drawing, the
  `--opaque` plate; and the panel comes up (Start pressable) before
  its drawing thread is done, while the watcher uses the same
  SolidCraft port at the same time (two clients; untried).
* `tests/test_setup_view.py` `TestLive` (skipped unless
  `SCRAFTCNC_SOLIDCRAFT=1` and `solidcraft-cli` on the `PATH`):
  `demo_assembly()` in a headless session, with the flat grid plate.
  Passed in 29 s: every item drawn, "Plate" among the bodies, the
  plate's face centroids inside the stock's box on all three axes
  (step 5e's move and Z hold), and a second show keeps everything
  (counts `(0, n, 0)`).  No `solidcraft-cli` left running.
* `tests.test_setup_view tests.test_lcnc_hmi tests.test_show_demo`:
  59 OK (1 skipped).  Checkers clean (`show_demo.py`'s two C0413s
  were there before, from its `sys.path` insert).

## 2026-11-04: First `./show_demo.py` run

The user's run: "Setup not drawn: ... invalid parameters for
`solid.chamfer`: [75.40625, 76.2, 0] where 2 edges meet".  From the
demo part (`demo.py` `_edges()`), not the grid plate.  The headless
live test passes, so likely the panel's part build picked an edge of
something else drawn at the same point (the watcher's tool path,
#77): `_edges()` named no body.  Fix: `_edges()` now passes the
plate's body to `solid.chamfer` / `solid.fillet`.  Headless live test
still passes.  Not yet confirmed in the GUI.  #78 (to check): the
part is built at (0..4, 0..3) in and moved to center on the stock,
but if the G-code's zero is the plate's corner, the tool path and the
drawn part will not line up.

## 2026-11-04: Headless demo (`T.hlp~3.3.1`, closed); step 6 next

`./show_demo.py --headless` runs everything with no window and prints
every body's box (see `T.hlp~3.3.1`'s summary).  #78 fixed: the table
is at (4, 3) in in `_TOOLING`, so the plate spans the G-code's 0..4 x
0..3 in.  Open: #75 iso view, #76 Start before the drawing ends, #77
GUI interleaving (the user's GUI run checks the chamfer fix), #80 the
stock overhangs the grid plate at -Y.  Next, step 6 (#36, #38): Set
Origin offers the setup's origins (each item's handed-up origin, from
`place()`), the operator picks where the tool is now, and the panel
sets G54 so that point reads its work coordinates (`G10 L20 P1`).

## 2026-11-04: Step 6, origin pick (#36, #38)

* `setup_view.named_origins(assembly)`: each item's handed-up origin
  (from `place()` + `origin(turns)`, parallels and the part left
  out), named `"<item name>: <what>"` (`ORIGIN_NAMES` by class), then
  `"work zero"`; the setup frame is the work frame.  Demo (mm): mill
  table top upper left (-279.4, 209.55, -130.556); vise fixed jaw top
  left inner (25.4, 146.05, -38.481); grid plate top left outer
  (-31.75, 6.35, -12.7); stock top left outer (-6.35, -6.35, 0);
  work zero.
* `lcnc_hmi.py`: `open_setup()` keeps `origins` and `inches` (the
  program's first `G20`/`G21`, `program_inches()`).  Set Origin with
  origins: `ask_choice()` (a Toplevel with a read-only Combobox, OK,
  Cancel; headless: `lcnc_hmi_headless.askchoice()` from `answer`),
  then `askyesno` (default No) showing the line, then MDI
  `origin_lines()`: `G20`/`G21` then `G10 L20 P1 X.. Y.. Z..`.
  Without a setup, as before.  `show` gains `origins`; a new port
  command `log`.  The GUI window is untried (no display run).
* `show_demo.py --headless --origin NAME`: before Start, MDI-moves
  to the origin's work point (as an operator jogs), presses Set
  Origin, answers.  First try without the move failed as it should:
  Z set to 0 at the top of travel, "work Z can reach only 0.0000".
* Run (20:13-20:15): `mdi G10 L20 P1 X-0.2500 Y-0.2500 Z0.0000`,
  status x=-0.25 y=-0.25 z=0 before and after, program 96 s to the
  end, total 104 s, exit 0, nothing left.  Boxes unchanged.
* Tests: `tests/test_setup_view.py` `test_named_origins`;
  `tests/test_lcnc_hmi.py` `TestSetOrigin` (pick, cancel / No, no
  setup, lines).  58 + show_demo tests OK; checkers clean.
* Open: the vise's origin Z (-38.481 mm, #55's 92.075 mm jaw top)
  is 19.05 mm below the modeled fixed jaw's top (-19.43 mm, the jaw
  on the rails); the grid plate is placed from it.

## 2026-11-04: #55 settled; step 7 (#14) stepping, one bug left

* #55: `SCMachineViseLayer.origin()` Z is now `vise.bed_top() +
  fixed_jaw.height` (the modeled jaw on the rails, 111.125 mm for the
  Kurt D688).  `_TOOLING`: parallels Z -0.985 -> -1.735 in, grid
  plate 0.515 -> -0.235 in; comments updated.  Nothing moved: grid
  plate still [-31.75 6.35 -25.40] .. [234.95 146.05 -12.70].
  `tests/test_mount.py` `TestOrigins.test_vise` expects 111.125.
  The changed `mount.py` changed the item-key source digest, so the
  next draw rebuilt everything (267 s, the chamfered grid plate).
* Step 7: `lcnc_hmi.py` "Next Step" button (before Set Origin):
  step N shows "Step N/7, <name>: <note>" and draws items 1..N
  (`SCAssembly(items[:N])` to the drawer); the press after the last
  shows "Setup: all 7 items." and the whole setup.  `show` gains
  `setup_step`.  Part note now "Cut the plate; G54 zero is its lower
  left top corner."  `show_demo.py --headless --steps`.  Tests:
  `TestSetupDrawing.test_next_step`, `test_no_steps`;
  `TestSetupView.test_steps` (counts (1, N-1, 0)).
* Run (20:18-20:24, `--steps --origin "stock: top left outer"`):
  steps 2-7 and "all" shown with their notes; Set Origin and the run
  fine; exit 0, nothing left.  Bug: step 1 failed with "Setup not
  drawn: ... `sketch.delete` is not available right now: no sketch
  is being edited" (erasing the stock outline,
  `SCSetupView.erase()`), so step 1's message was replaced by the
  error and the old outline stayed: the report shows `stock_1` and
  `stock_2`, and two empty `Plate` sketches (the part's build
  sketch survives `solid.remove`).  Next: erase a whole sketch (edit
  it first, or delete its timeline feature), and remove the part's
  sketches with its body; keep `shown` consistent when an erase
  fails.

## 2026-11-04: Step 7 erase fixed

* `SCShown(bodies, sketches)`: `curves` replaced by whole sketches
  (timeline names or ids).  `erase()` removes the bodies, then
  `timeline.delete(features=sketches)` (a sketch takes its dependent
  features with it; tried headless: by name and by id).  The stock
  outline records its sketch name `stock_N`; a built item (the part)
  records the sketch ids that appeared while it was built
  (`sketch_ids()`, from `document.inspect`).
* `show()`: an item whose erase fails stays in `shown` (key kept,
  what did go cleared from its `SCShown`), the rest still drawn, then
  `RuntimeError("not taken out: ...")`.  The panel keeps the step's
  note first: "<note> (Setup not drawn: ...)" (`SCPanel.note`).
* Tests: `test_erase_fails`, `test_stock_sketch_deleted`
  (`tests/test_setup_view.py`, fake session gains `document`,
  `timeline`); `test_step_error` (`tests/test_lcnc_hmi.py`).
* Run (20:27-20:29, `--steps --origin "stock: top left outer"`):
  steps 1-7 and "Setup: all 7 items." shown with their notes, no
  errors; final sketches: one `stock_2`, the part's own `Plate` and
  `Pocket` (its current body's build sketches; 0 wires, 2D curves),
  and the paths/flutes; 25 bodies; exit 0, 121 s, nothing left.

## 2026-11-04: Keep-outs (#47, #41a), the last of #43

* `assembly.keep_out_boxes(thing)`: the layer's own `keep_out((0,0,0))`
  prisms, less `origin(0)`: six lengths from the item's origin,
  unturned (cylinders left out).  `demo_assembly()` fills every
  tooling item's `keep_out` with it.  The `.nc` writer
  (`setup_comments._wrapped()`) now wraps nested lists too, one
  element a line, so every `SCC:` line is <= 79 columns (a box takes
  8 lines; verbose but valid).  The round trip test compares with
  `assert_same()` (floats) and checks line lengths and keep-outs.
* `setup_view`: `prism_edges()`, `keep_out_prisms(here, origin)`
  (work-frame boxes), `SCSetupView.keep_outs` (off by default): each
  item with keep-outs gets a second display key `("keep_out", ...)`
  and one sketch `keep_out_N` of wire boxes; off removes them
  (`timeline.delete`).  Panel: "Keep-outs" button toggles
  `SCSetupDrawer.keep_outs` and redraws what was last drawn
  (`SCPanel.drawn`).  `show_demo.py --headless --keep-outs`.
* `keepout.assembly_zones(assembly)`: zones from the `.nc` setup's
  boxes (setup frame = work frame).  `keepout.main()` prints it too.
  The demo program breaks 51 times, all the grid plate (drills and
  through cuts 0.05 in below the plate into the grid plate's 1/8 in
  margin), the same 51 lines as `demo_stack.json`'s zones with the
  program moved by (-2, -1.5) in (`TestAssemblyZones`).  The 0
  `keepout.py` printed for the demo is `demo_plate.json`, which has
  no grid plate.
* Run (20:33-20:40; `assembly.py` changed the cache key, so 277 s
  rebuild): keep-outs on, Set Origin, program, exit 0, nothing
  left.  Keep-out boxes (work mm): table [-282.58 -60.33 -197.23] ..
  [485.77 212.72 -127.38]; vise base [22.23 -238.76 -133.73] ..
  [180.98 193.04 -60.32], fixed jaw [22.23 142.87 -66.67] .. [180.98
  193.04 -16.26], movable jaw [22.23 -238.76 -66.67] .. [180.98 9.52
  -16.26]; parallel A [22.23 139.70 -66.67] .. [180.98 149.22
  -22.22]; parallel B [22.23 3.17 -66.67] .. [180.98 12.70 -22.22];
  grid plate [-34.92 3.17 -28.57] .. [238.13 149.22 -9.52].
* Tests: `test_keep_outs`, `test_keep_out_prisms`
  (`test_setup_view`), `test_keep_outs` (`test_lcnc_hmi`),
  `TestAssemblyZones` (`test_keepout`); 7 modules OK.

## 2026-11-04: Full suite; answers #75-#82

Full suite: 600 tests, 1 failure (`Tool_Models.md` stale; regenerated).
The user's GUI run "looked exactly the same" (meaning to confirm).
* #75: Not iso; a more realistic view if SolidCraft has one.  Claude:
  the operator's view (from the front, -Y, a little above, perspective
  if available).
* #76: Grey out Start while drawing, plus a completion bar.
* #80: A bug.  The grid plate already abuts both jaws' inner faces (Y
  6.35..146.05); the stock is what is off center on it (by 2 in X,
  1.5 in Y).  Fix: center the stock on the grid plate and move the
  table back to (2, 1.5) in, so the plate stays on the G-code's zero.
* #81: Fix if easy (keep-out cylinders in the `.nc`).
* #82: Fix now: each keep-out box one string with one unit
  (`"x0 y0 z0 x1 y1 z1 in"`), one line; avoid wrapping generally.

## 2026-11-04: #80, #82, #81, #76, #75

* #80: `_TOOLING` table back to (2, 1.5) in; the stock at (5.25,
  2.75) in from the grid plate's origin, so the stock, the plate and
  the grid plate share a middle, (2, 1.5) in in work coordinates,
  and the plate stays at 0..4 x 0..3 in.  The tooling is now exactly
  where `demo_stack.json` puts it (`test_demo`, no shift; table and
  grid plate origins in `test_named_origins` moved by (-2, -1.5) in).
  `keepout`: the demo now breaks the grid plate's zone 64 times (51
  before, with the plate off center); `TestAssemblyZones` compares
  with `demo_stack.json`'s zones, program unmoved.
* #82: `assembly.lengths_text()`: a keep-out box is one string, six
  numbers and one unit (inches when all exact to 4 places, else mm);
  `_box()` still reads six strings.  Demo `SCC:` lines 133 -> 76;
  only the vise's three boxes still wrap (one box a line); no other
  wrapping in the demo.  Test `test_old_box_form`.
* #81: skipped.  No mount layer makes keep-out cylinders (only drills
  and cutters do, `tools.py`), and cylinders would need a field of
  their own in `SCItem`, the reader, the writer, the view and
  `assembly_zones()`.
* #76: `SCSetupView.progress` (done, total changes of a `show()`),
  `SCPanel.drawing` (Start greyed while drawing, through
  `set_running()`), a `ttk.Progressbar` on the message row; `show`
  has `setup_progress`.  Headless `Progressbar` stand-in.  Test
  `test_start_waits`.
* #75: after the first show, `SCSetupView.operator_view()`:
  `view.apply(camera={target: stock's top middle, yaw 0 (front,
  -Y), pitch 0.35 rad, distance 700 mm, fov 0.7 rad})`; probed: front
  is yaw 0 pitch 0, top pitch +pi/2, fov 0 is orthographic.  Test
  `test_operator_view`.
* Run (21:03-21:10, rebuild 278 s after the `assembly.py` change):
  keep-outs on, Set Origin, program, exit 0, nothing left.  Grid
  plate [-82.55 -31.75 -25.40] .. [184.15 107.95 -12.70], middle
  (50.8, 38.1) = the plate's ([0 0] .. [101.6 76.2]) and the stock's
  ([-6.35 -6.35] .. [107.95 82.55]).  The camera call raised nothing
  headless (not seen; GUI to check).

## 2026-11-04: #83 grid plate chamfer flag

`SCGridPlate.named(name, chamfer=True)`; `chamfer=False` gives the
plate with `chamfer_depth` 0.  The demo's `_TOOLING` passes
`chamfer = false` (in `args`, so in the cache key).  `Tool_Models.md`
(Grid Plate section, from `tool_models.py`) says chamfering is very
slow and recommends turning it off.  `test_assembly` expects the
unchamfered plate.  Timing, headless, new cache key (a cold build):
setup drawn in 10 s (was 267-278 s with chamfers), total 103 s, wall
110 s, exit 0.

## 2026-11-04: Lead-in/out half circles "missing" (the user, GUI)

The user's GUI run "looks great", but the half circle lead-ins and
lead-outs are missing.  Checked: the demo's G-code is identical to the
last git commit's apart from the `(SCC:` lines (208 G2/G3 both); the
watcher's path (`SCPathRack`, `plot.command_moves` + `path_steps`) is
identical for both programs (T1: 3 `line3d`s of 500/442/202 points,
arcs as points); `sim_linuxcnc.py` / `sim_solidcraft.py` unchanged
apart from names.  So the drawn path data has not changed; asked the
user where the half circles are missing.
* Found (the outer contour, T1 finish): not a regression of today.
  `SCCNC._stage_offsets()` (`gcode.py:1212-1235`) gives a finishing
  pass leads of `finish_allowance / 2` (0.025 in) so they stay in the
  rougher's slot; the roughing pass (T8) gets the tool's radius (0.125
  in).  The finish profile's half circles are 0.6 mm, too small to see
  (G-code line ~674, `G3 Y-0.125 I0 J0.025`).  In since commit
  `fc1a3e3` (2026-10-27), when roughing/finishing came in.  Asked the
  user (#86).
* #86: Settled, a (for now).  `_stage_offsets()` gives every stage
  leads of the tool's radius (halved where they don't fit).  Demo:
  outside finish lead `G3 Y-0.125 I0 J0.125`, plunging at Y -0.375 in
  (outside the stock, in air); the hole's finish lead is full size too
  and sweeps through the hole's slug at full depth (the drilled entry
  moved with it).  `test_profile_stages` now expects the entry a tool
  diameter off the finish path.  `test_gcode`, `test_keepout`,
  `test_setup_comments` pass.  Run time estimate 11.8 min.
* Through cuts (the user): must go below the part, 1 mm is fine, or
  the metal bows out.  Profiles already went `through_overcut` (10%,
  0.05 in on the demo).  Fixed: `SCCNC.below()` gives at least
  `MIN_THROUGH_OVERCUT` (1 mm) for thin parts; `drill(through=True)`
  adds the drill's point length (`SCTool.angle`, now filled from a
  drill's `point_angle` in `shops.py`), since only the full diameter
  cuts free: the demo's 15/64 in 118 deg drill went to Z-0.55 with its
  full diameter only to Z-0.48 (above the bottom); now Z-0.6204.
  Tests in `test_gcode` (`test_through`).  The deeper drill reaches
  0.12 in into the grid plate (the known through cut problem).
* The user: spacers are not in the mount yet; through cuts into the
  grid plate will fault once keep-out checking is enabled, which will
  force adding them.  Later.  Full suite run once; fixes not rerun.
* Full suite (21:45): 603 tests OK, 13 skipped, 189 s.  Nothing to fix.
