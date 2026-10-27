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
