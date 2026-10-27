# LLM Agent Context Log

## 2026-10-27: Created; `Details.md` drafted with the user

* Created as sub-task 2.1 of `T.ds~2` (both Open) instead of a new
  top-level task, since `T.ds~2` already planned this (its
  `Context.md` summarizes `../Fab/`).  `Details.md` was drafted by
  Claude at the user's request and revised from the user's answers;
  it holds every decision so far and the open questions (the user's
  numbering 0-5).
* Read in full: `../Fab/FabShops.py` (1032 lines; summarized in
  `Details.md`).  Not yet reread: `../Fab/FabTools.py`,
  `FabToolBits.py`, `FabSolids.py` (`FabStock`), `docs/FabShops.md`.
* User decisions: many TOML files, each starting with `name`, `kind`,
  `language`, `version` (semantic); `"@FILE_NAME"` stands for another
  file's contents, which must be in the same directory; tools are
  shared between machines, T numbers allocated per machine (a tool
  table); the controller lists all the codes it accepts, LinuxCNC the
  baseline; Python classes `SC` + `CamelCase`, no collision with
  `scraftpybind` (none of its classes start with `SC`; this project
  has `SCMachine` and `SCTool` already); only example files in this
  repository; shop location is latitude, longitude and address.
* Waiting on the user: #0 TOML key style (research in `Details.md`,
  `snake_case` recommended); #1 the machine class name; #3 address as
  one string or separate fields; #5 how the files are split (left to
  the user).
* Next: once #0 is settled, write example files (e.g.
  `examples/shop/`) and the loader (`scshop.py`?), with tests.

## 2026-10-27: Nested TOML and `Shops.md`

* User decisions: "Nested TOML" is a description in more than one
  `.toml` file, joined by `"@FILE_NAME"`; the reader splices them into
  one JSON style data structure for the CNC side.  One top-level
  `Shops.md` describes it: a general Nested TOML section first, then a
  section per `kind`, and the format version it describes.
* Done: `Details.md` updated; `Shops.md` created as a skeleton (keys
  `snake_case` pending #0, TODOs for the kinds not yet worked out).
  The user is now editing `Shops.md`.
* Not answered yet: a test that keeps `Shops.md` and the loader's keys
  in step.

## 2026-10-27: Where things stand (end of session)

* The user is editing `Shops.md` for a while, then commits and pushes
  in git.  Next session: read `Shops.md` as the user left it (it is
  now the user's document; Claude edits it only when asked), and pick
  up the open questions: #0 key style, #1 machine class name, #3
  address, #5 file split, #6 `Shops.md` at the top level (done that
  way, not yet confirmed), #7 a test keeping `Shops.md` and the
  loader's keys in step.
* To do once `Shops.md` settles: a pointer to it in `README.md`
  ("The Files"); then example files (`examples/shop/`) and the loader.
* `#README.md#` (an Emacs autosave) is lying in the project directory;
  it is not Claude's.

## 2026-10-27: New plan: `shops.py` writes `Shops.md`

User decision: `Shops.md` is no longer written by hand.  `shops.py`
holds the schema, reads and checks the files, and writes `Shops.md`;
TOML problems must be reported at their line.

Done (first cut, all checkers clean, 64 tests pass):
* `shops.py`: `SCField`/`SCKind` schema (`KINDS`: shop, location,
  machine, axis, machine_table, spindle, controller), `read(path)`
  (Nested TOML, `@FILE_NAME` spliced, each file read once, loops and
  wrong kinds refused), `SCShopError.problems` as `FILE:LINE: KEY:
  message` (every problem, not just the first), `markdown()`.  CLI:
  `./shops.py check|json FILE...`, `./shops.py markdown`.
* Line numbers: `tomllib` (and `tomlkit`) give lines only for syntax
  errors; neither keeps positions of parsed values.  `_Scanner` walks
  the already-parsed text to map every key path to its line.  Stays
  standard library only, as `README.md` promises.
* Units imported from `scmachine` plus new `ACCELERATION`,
  `ROTARY_FEED`.  Values are kept as the strings written (`"5000
  rpm"`), checked but not converted.
* `examples/shop/`: `home_shop.toml`, `shop_mill.toml`,
  `linuxcnc.toml`.  `test_shops.py`.
* Found: the old `Shops.md` example's inline `location = { ... }`
  spread over two lines is not legal TOML 1.0.
* `Shops.md` itself NOT overwritten: the user had it open in Emacs
  with unsaved edits.  A generated copy was left in scratch.

## 2026-10-27: `Shops.md` generated

* Markdown tables have their `|`s lined up (`_markdown_table()`);
  long explanations moved out of the tables into bullets and summaries
  (wrapped at 72).  Widest line 97 (the `axis` table).
* User agreed (#9): `Shops.md` overwritten by `./shops.py markdown >
  Shops.md`; `test_shops_md_is_current` fails when it is stale.  The
  hand-written version is in `hg` and in `git` HEAD.

## 2026-10-27: Answers; table rows wrapped

The user renumbered the open questions 0-8 (old numbers in brackets):
0 [0] `snake_case`: yes.  1 [1] machine class name not needed yet: yes.
2 [3] address one string: yes.  3 [5] file split: up to the end user
(us included).  4 [7] agreed.  5 [8] measurements stay strings for
now (the conversions needed are not known yet).  6 [9] `Shops.md`
looks good.  7 [10] where the units live: user does not know; wants
every error found long before anything reaches CNC path generation.
8 (new) no lines wider than 79 in `Shops.md`.

Done for #8: `_markdown_table()` wraps wide cells (never inside a
code span) into continuation rows whose first cell is empty; the
intro of `Shops.md` says so.  `MARKDOWN_WIDTH = 79`;
`test_no_wide_lines`, `test_wrap`.  68 tests pass.

## 2026-10-27: `shops` kind; Shars catalog mapped

* New `kind = "shops"` (a list of shops, the top of a description);
  `examples/shop/shops.toml` writes the whole example shop in place
  (`[[shops.machines.axes]]` etc.); a test checks it reads the same as
  the split files.  69 tests pass.
* `shars_catalog.md` (an agent's map of `2026_Shars_Catalog.pdf`) is
  in `.gitignore` and `.hgignore`, at the user's request.  Key facts:
  no table of contents and no bookmarks (the agent built the section
  list from the running page headers); printed page = PDF page;
  `pdftotext -q -f N -l N -layout` gives good, column-aligned tables
  (images only on 335 and 375).  Pulling specs will need parsing by
  column position (blank cells, side-by-side tables, group labels
  printed once, inch fractions with `"` only on the first row, prices
  and part numbers mixed in).

## 2026-10-27: Router; fractions

* `examples/shop/shop_router.toml` (5 x 10 ft table, 6 in Z, 1/2 in
  collet; RPM, feeds and accelerations guessed); shares
  `@linuxcnc.toml` with the mill.  New spindle key `collet` (length).
* `shops.toml` keeps the shop in place but names its machines'
  files (`machines = ["@shop_mill.toml", "@shop_router.toml"]`), at
  the user's request.
* Measurements may be fractions (`"1/2 in"`, `"1-1/2 in"`), as US
  catalogs write them; `shops.MEASUREMENT` replaces the `scmachine`
  pattern here, and `measure()` converts (tested).  71 tests pass.

## 2026-10-27: Tools, first cut

User: a tool is a bit in a holder; the holder is not recorded, only
the bit's type and its facts; tools are shared by machines; optional
manufacturer, manufacturer PN, vendor, vendor PN, material, cost,
acquisition date.  Spindle interfaces: R8, BT30/40/50, CAT40/50, ...;
collets ER16-ER40, ...

Done: kinds `tools` (lists `end_mills`, `drills`), `end_mill`,
`drill` (common keys from `_tool_fields()`); a shop has `tools`;
forms `money` (`"15.18 USD"`) and `date` (a TOML date); tool names
are unique over everything read, and when the top file is a `shop` or
`shops` every `tool_table` name must be a tool read.
`examples/shop/tools.toml`: Shars 415-0982 and 415-0998 (page 71),
415-7938 and 415-8998 (page 3).  The mill's tool table is now a
`[tool_table]` section (the inline one was 121 wide).  75 tests pass.
Questions for the user: #9-#16 in the session's last answer.

## 2026-10-27: Answers on tools

User: #9 interfaces checked, any capitals, a value ending in `!` not
checked; collets recorded whenever a tool is held in one (always for
drills); the machine does not care about collets.  #11 tool types as
separate lists, more to come.  #12 "USA Made"/"Import" fine as
manufacturer.  #13 materials checked the same way.  #14 any currency.
#15 a `description` key.  #16 more tool types later; pause on them.
Next: "the tool mapping part": every tool has a unique name, since T
numbers are not unique (per machine).

Done: `SCField.open` (choices in any capitals; `!` skips the check
only for open lists; the reader returns the schema's spelling);
`INTERFACES`, `COLLETS`, `MATERIALS`; spindle `taper` renamed
`interface` (the router's is `ER20`), spindle `collet` removed; tool
`collet` (required on drills); `description`; money in any ISO 4217
code (never converted).  75 tests pass.

## 2026-10-27: Tool tables

User: #17 a tool is in one machine at a time; #18 `tool_number` /
`loaded_in` on the right track; #19 two digit T numbers (1-99) are
fine for now (some machines have hundreds); #20 the tool table is its
own file: T number (unique) to tool name (unique).

Done: kind `tool_table` (`[tools]` maps T numbers to tool names; the
form is now `t_numbers`), named by `machine.tool_table`;
`examples/shop/shop_mill_tools.toml`, `shop_router_tools.toml`.
Refused: a T number twice (`"1"` and `"01"`), a tool named twice
(in one table or two), and two machines naming one tool table file.
`tool_number(machine, tool)` and `loaded_in(shop, tool)`.  Tests copy
the examples without editor files (`.#*`, `#*#`, `*~`).  78 tests.

## 2026-10-27: Demo runs from the shop

User: find the demo's tools in the catalog (90 deg chamfer, ball nose
"page 45", roughing mill, double ended shank cutter page 112 for
bottom chamfers) and hook them up to the demo.

Found: page 45 is taps; ball nose is on page 54 (HSS, 404-5952) and
page 71 (carbide).  Page 112's double angle table runs to 55 deg; 90
deg is on pages 113-114 (1/4 in, 436-4296, neck 0.625).

Done: tool kinds `chamfer_mill`, `corner_rounding_mill`,
`double_angle_cutter`; end mill `roughing`; drill `peck`; every tool
optional `rpm`, `feed`, `plunge` (until materials); each kind has its
own sizes (`_size_fields()`).  Machine `preferences` (the old
`machine.toml` `[machine]` settings).  `shops.cnc_machine(shop,
name)` builds `SCMachine` (tip diameters for chamfer and rounding
bits); `scmachine` kinds `ball end mill`, `double angle`,
`SCMachine.named()`.  Demo reads `examples/shop/home_shop.toml`,
names its tools.  `linuxcnc.toml` `tool_change` is `T{number:02d}`
(the user's earlier rule).  G-code differs only in tool names and the
round-over pass (real tip 0.0469 in, was 0.125).  Headless and
`--plot` work.  Tests now find expected lines by text (`at()`).  78
tests.  The demo does not use the ball, roughing or double angle
tools yet (no operations for them).

## 2026-10-27: `machine.toml` removed

User: #21 bottom chamfers need "mounting" (table, vise, parallels,
tooling plate, sacrificial material, stock; and much else besides
vises) -- later.  #22 a roughing bit removes material whenever one is
available; the final pass is with an end mill, for a smooth finish.
#23 the ball nose cuts rounded inside edges; not yet.  #24 remove
unneeded files; make the shop files work for everything before
materials, speeds and feeds.

Done: `machine.toml` deleted (`hg remove`; still in git until the
user commits); `scmachine.py` is now only `SCTool`, `SCMachine`,
`ToolKind`, `DrillCycle` (no loader); the unit tables live in
`shops.py`.  The router has `[preferences]` (guesses), so both
machines build.  `test_scmachine.py` uses the example shop; the
reader tests share `CopiedShop`.  77 tests; demo G-code unchanged.
Not done: #22 (proposed in the session's answer, waiting).

## 2026-10-27: Roughing

User: allowance 0.05 in; show the result in the GUI.

Done: preference `finish_allowance` (shop files, `SCMachine`, default
0.05); `scmachine` kind `roughing end mill` (from `roughing = true`),
`SCMachine.rougher_for()` (largest rougher no wider than the end
mill).  `SCCNC` `Stage` = full/rough/finish on `profile()`,
`pocket()`, `profile_entry()`, `pocket_entries()`: rough leaves the
allowance on walls/islands (`inset()` of the region) and floors, and
never cuts through; finish is one pass at full depth (pockets plunge
into the roughed area; profile leads of radius allowance/2 start on
the rougher's path).  Profile leads halve (up to 3 times) to fit
narrow holes (`_fitted_path()`).  Demo (`cut_demo()`): drill at the
rougher's entries, T8 roughs pocket, hole and outline, T1 finishes
pocket and hole, bevels, round-over, T1 finishes the outline (cuts
the part free).  19.6 minutes.  Finish entries checked 0.25+ in from
walls.  80 tests.  Shown in the GUI (port 8080, 37 s).
