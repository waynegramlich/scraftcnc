# LLM Agent Context Log

Trimmed 2026-11-12: only decisions still in force and where things
stand.  The full history is in `hg` and `git`.  Issue numbers are
sticky (code comments cite them); new ones continue after #133.

## Decisions in Force

* Toolkit and platforms: Qt (PySide6, fetched by `packages.require`,
  no venv); Linux (Wayland) and Windows; no macOS (#21, #52, #55).
* One GUI, started by `python3 -m scraftcam.run` (or
  `scraftcam/run.py`, shebang, #93, #103): `--shop`, `--design`,
  `--port`, `--headless`.  With no `--shop`, `shop.toml` is looked
  for here and in the parents (#83).  LinuxCNC only when needed (#1).
* Windows: one model shared by all windows, kept in sync (#3);
  pop-ups allowed.  [Stop All] whenever more than one machine runs
  (#2); a window controlling a running machine refuses to close
  (#67).  Starts at 720 x 480 (#109).
* Top line (#82): [Stop All], [Tree], shop and design names, latest
  message (red for problems, #95), [+ Panel], narrow [x] (#114).
  Action rows under it (#73, #75); no right click; no icons, a kind
  in parentheses ("T01 (tool)").
* No shop: "No shop yet: [New Shop]"; the dialog opens at start
  (#97): directory (`./shop`, [Browse...] is Qt's own dialog, #117),
  name with [Create] beside it (#116), units "Imperial (in)" /
  "Metric (mm)", machine kinds: computer controlled, then manual for
  prep work (#104, #118).  More than one machine of a kind: S3 (#115).
  Never `git init`; suggest `git` or `hg` when not in a repo (#99,
  #107).
* Tree (#119-#128): one tree, two roots (shop, design); directories
  first, alphabetical; roots open one level; bad files red
  "(error)" with "syntax error ... line N"; design tree parsed with
  `ast`, never imported, max 100 items; watched with
  `QFileSystemWatcher` (no [Refresh]).
* Panels (#122): clicking shows the item in the current (outlined)
  panel; TOML text, a Python docstring, or the problem.  [Edit]:
  `$VISUAL`, else `$EDITOR` in a terminal, else the desktop default,
  with a once-a-session hint naming the environment variables
  (#77, #124).
* Command port (#96, #110): JSON-RPC 2.0 shaped lines on 127.0.0.1:
  `status`, `press`, `new_shop`, `tree`, `select`, `quit`.  MCP later
  (#86).
* Shop data (#4, #9, #11, #12, #18, #19, #64, #129-#133): the user's
  shop is a directory under their own version control; `scraftcam`
  names the directories, one item per `.toml` file; `shops.KINDS` is
  the one schema; JSON Schemas generated from it with a `#:schema`
  first line; our writer orders keys by `KINDS`; comments are not
  kept, `notes` holds them; hand edits allowed, bad files reported.
  `~/.scraftcam/` only holds what can be rebuilt.
* Values (#15): checked as typed, light red while bad, never written
  bad; written when focus leaves the field; no [Save], no history of
  our own (#17).  Shared GUI settings in `shop.toml`; per-user layout
  in `gui/USER@HOST.toml` (#78.1, not done).
* Catalogs (#87, #88): tables and text under version control; images
  on demand; a purchased tool keeps its material.
* Deferred: #90-#92 (shop templates, "Show in SolidCraft", shop
  floor screens); installer, launchers, PyPI (#54, #56, #57, #89);
  panel menu (#71).

## Step Order (#13)

1. Top line: done.
2. Tree view: done.
3. Shop schema and files: S3.1-S3.4 done; S3.5 next.
4. Tool documentation and SVG (#5, #80).
5. Machine control: the HMI as a panel (#6).

Each step: offscreen tests, checkers, the user's GUI run; done only
when the user likes it (#85, #112).

## Where Things Are

* `scraftcam/gui/`: `app.py` (model, no Qt), `fields.py` (a shop
  item's field rows, no Qt, S3.4), `window.py` (windows,
  `NewShopDialog`, `CommandServer`, `delete_windows()`), `views.py`
  (`TreeView`, `Panel`, `TreeWatcher`), `tree.py`, `editor.py`,
  `port.py`, `README.md`.
* `scraftcam/shops.py`: `read()` takes `shop.toml` or its directory
  and fills in `machines`, `tools`, `tooling`, `materials` from
  `SHOP_DIRECTORIES` (the CNC side is unchanged: the demo's G-code is
  identical); tables by name (`controller = "LinuxCNC"`); no `@`.
* `scraftcam/shop_writer.py` (`item_text()`), `scraftcam/shop_schema.py`
  and `scraftcam/schemas/`, `scripts/convert_shop.py` (one time,
  kept as a record).
* `examples/shop/`: the new layout (`shop.toml`, `controllers/`,
  `machines/`, `tools/`, `tooling/`, `materials/`).
* Tests: `tests/test_gui_*.py`, `tests/test_shop_schema.py`,
  `tests/test_shops.py`; `tests/qt_app.py` (offscreen app; deletes
  windows at exit, which fixed #113's crash).
* A sample shop and design for GUI looks:
  `/tmp/claude-1000/-home-wayne-public-html-projects-scraftcam/036c09a7-0d48-4676-8dfd-0ffea8825152/scratchpad/demo/`
  (scratch, may be gone).

## Done: S3.4, the Fields Panel (#72, #132)

Clicking a shop item shows a row per field, in `KINDS` order: entry
light red while bad, the value in the shop's units in grey, help as
tooltip; written with `shop_writer.item_text()` when focus leaves a
field, never a bad value.  Scalars only (measurements, strings,
choices); lists and nested tables read only as TOML for now; sketches
in step 4.  Then S3.5: `gui/README.md`, tests.

Open from S3.2: materials now list alphabetically (by file name);
the example shop's `notes` still mention `materials.toml`.

## 2026-11-12: S3.4 under way

* `shops._scalar_problem` is now public `scalar_problem`.
* New `scraftcam/gui/fields.py` (no Qt): `Row`, `rows()`,
  `check()`, `value_of()`, `with_value()`, `rest_text()`,
  `read_item()`, `write_item()`, `shop_units()`, `SHOP_UNITS`.
  `kind` and `version` shown, not edited (`FIXED`).  Not yet run
  or checked.
* Next: the field rows in `views.Panel` (`QLineEdit`, `notes` as a
  multi-line entry, write on `editingFinished`, skip rebuilding
  when the file holds what the panel just wrote), the window passing
  the shop's units, tests in `tests/test_gui_fields.py`.
* `views.Panel` has the field rows (`fill_rows()`, `typed()`,
  `write()`, `written`); `window.py` passes `fields.shop_units()`;
  `tests/test_gui_fields.py` (4 tests) pass, checkers clean.  #7
  (choices typed, no drop-down) and #8 (rewrite only on a change)
  agreed.
* The user's GUI run: "looks great"; S3.4 done (2026-11-12).
* Open, for the user: #9 the `notes` entry is 4 lines high and the
  fields take about 2/3 of the panel (TOML below); change after
  seeing them?  #10 S3.5 next: `scraftcam/gui/README.md` (the
  field rows, `fields.py`), and the two S3.2 leftovers below.

## 2026-11-13: S3.2 leftovers and #9-#12

* #9: the field rows stay as they are for now (the user).
* #11 done: the example shop's `notes` (`shop.toml`, the cobalt
  jobber drill) point at `materials/`, not `materials.toml`.
* #12: materials stay alphabetical by file name (the user).
* #10 (S3.5, `scraftcam/gui/README.md`) last, as the user may want
  to edit it; then steps 4 and 5.

## 2026-11-13: Step 4's decisions, recovered (#13)

From the log before the trim (`hg` rev 695):

* #5: tool sketches are the SVG that `Tool_Models.md` uses, shown in
  a `QSvgWidget` (replaces the old `tkinter` Canvas plan, #16).
* #9 (fields): one description of each kind's fields (name, unit
  kind, required, default, help, sketch letter) drives the forms,
  the reader's checks, `Tool_Models.md`'s tables and the sketch
  letters.
* #16: one drawing per tool (lines, arcs, dimension letters), the
  same SVG for `Tool_Models.md` and the GUI.
* #70: SVG (when present) on the right; for documentation, the text
  left of the SVG; tried out until it "looks right" to the user.
* #80: agreed in outline: a kind's directory shows its
  documentation, text left, SVG right, from the source of
  `Tool_Models.md`; details to come.
* Next (#14): a tool item shows its existing SVG beside its field
  rows, with no new drawing code.

## 2026-11-13: #14 done, waiting on the user's GUI run

* `fields.sketch(item)` returns `docs/tool_models/KIND.svg`, or the
  first `KIND_*.svg` (grid plate: its section), or `None`;
  `fields.SKETCHES` is that directory, outside the package (to move
  inside before PyPI, #54).
* `views.Panel.sketch` (`QSvgWidget`, aspect kept) sits right of the
  field rows (2:1), hidden for kinds with no sketch.
* `tests/test_gui_fields.py`: 6 tests pass; checkers clean.

## 2026-11-13: The user's look at #14; #18-#25 decided

* #18: grid plate (and every sketch) labels are letters, not numbers.
* #19: a field row reads `length (L)`, from `TableField.letter`.
* #20: letters follow the names' first letters; when two fields
  share one, the next is the next letter, lower case (e.g. `Ch`?).
* #21: a tool's tree label is its function and key sizes, e.g.
  `End mill (1/2in 2-flute HSS)` (no space in `1/2in`), from its
  fields; the tree sorts by label.
* #22: fixed by #25.
* #23: `stock_materials/` (what is machined) and `tool_materials/`
  (carbide, cobalt, HSS: speed factors); tools name theirs.
* #24: follow the desktop's light/dark (`QStyleHints.colorScheme()`),
  no hard-coded colors, sketches recolored; the user reports what
  does not work.
* #25: `QSplitter` between the tree and the panels and between
  panels.
* Order: #25, #19, #18+#20, #21, #24, #23.

## 2026-11-13: #25 and #22 done (offscreen look)

* `views.splitter()`: 5 px handles in `palette(mid)`, not
  collapsible; used by the window (tree | panels) and inside each
  `Panel` (`top`: fields | sketch; `split`: those above the text),
  starting 2:1 (`SHARES`).
* `Window.fit_tree()` (first fill and [Tree]): the tree as wide as
  its open labels (`TreeView.wanted_width()`), at most `TREE_MOST`
  (half) of the width; `TREE_SHARE` is gone.
* Next: #19 (`length (L)`).

## 2026-11-13: #19 done; #20's rule coded, not yet used

* #19: `views.Panel.fill_rows()` labels a lettered row `key (L)`.
* #20: `shops.dimension_letters(keys)`: first letter, capital; taken
  -> plus a lower case letter: the other words' initials, then the
  other letters; three if needed; fewer-word names choose first.
  Cutters and grid plate come out well (`shank` S, `shank_length`
  Sl, `drill_diameter` Dd); the vise's 35 sizes are a jumble of B's
  (asked the user).  Not yet wired into `KINDS` letters or
  `tool_models.vise_numbers()`; the SVGs not regenerated.

## 2026-11-13: #18, #20, #26 done (option 2 for the vise)

* `shops.dimension_letters(keys)`: plain names by `free_letters()`
  (first letter; taken -> plus the other words' initials, then the
  other letters, lower case; fewer words choose first, then the
  earlier); `part.size` -> the part's letters plus the size's, lower
  case; a part named after a part takes its letters plus the other
  words' initials (`body_notches` `Bon`).
* `KINDS` letters follow it (`overall_length` O, `length_of_cut` L,
  `corner_radius` C, `shank_length` Sl, `drill_diameter` Dd,
  `drill_length` Dl, `neck_length` Nl); `grid_plate` fields now
  lettered (chamfer_depth Cd, close_diameter Cl, ...);
  `TableField.letter` allows a capital and up to 3 lower case.
* `tool_models.size_letters(views, kind)` replaces `vise_numbers()`;
  a kind in `KINDS` uses its fields' letters.  SVGs and
  `Tool_Models.md` regenerated.
* `tests/test_tool_models.py`: letters test rewritten (a key has one
  letter in every kind; a kind's follow the rule), rule test added;
  passes with `test_gui_fields`.
* #27: the mill's name "Mikini mill" was the user's test; reverted to
  "Shop mill"; `tests.test_shops` passes.
