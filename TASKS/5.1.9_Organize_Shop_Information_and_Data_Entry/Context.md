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

## 2026-11-13: #28 the grid plate's top view, broken

* The user: draw the tooling (grid) plate as four corners, each with
  its rounded corner and a 2 x 3 hole pattern, long break lines on
  the two inner sides.
* Done with 3 x 3 (`BREAK_COLUMNS`, `BREAK_ROWS` in
  `tool_models.py`): a 2 wide corner would cut through the tooling
  hole (at 1.5 pitches), and T, Td, Cl need one.  `_Broken` maps the
  plate to the drawing; `_zigzag()` draws a long break line.  The
  SVG is 127 lines, was 583.  `tests.test_tool_models` passes.
* Round 2 (the user): 4 x 4 corners (the tooling holes' checkerboard
  shows across the corners); facing break lines mesh (`_zigzag()`
  offsets fixed in the drawing, built after mirroring); `Cl`, `Td`
  letters moved out (`TOOLING_SHIFT`); `E`, `P` up the left side, `W`
  beyond them.
* Round 3 (the user): `Cl`, `Td` along the bottom with `E`, `P`
  (letters shifted right); `W`, `L` extension lines stop at the
  plate's corner; `C` at the upper right.  The user asked for 4 x 3
  corners with two tooling holes each: impossible on the sample (3
  in tooling pitch, 0.5 in grid), so 8 rows x 3 columns; `T` up the
  right side, between the lower right corner's two tooling holes.

## 2026-11-13: #29-#35, the grid plate's API; step A done

* Decided (the user): R x C grid, H, Cw (45 degrees), Cr, T
  (thickness), Tp with tooling holes as many as fit (#30), Tt
  (`tooling_tap_diameter`), Tc (`tooling_close_diameter`); length
  and width from the grid (#29).  #32: a cross section line showing
  the plate's edge chamfers and the holes' chamfers (step C; the
  plate has no edge chamfers yet).  #33: the sketch from a made-up
  plate (step B).  #35: a small 5 x 7 plate first.
* Step A done: `tools.GridPlate(name, rows, columns, pitch, edge,
  thickness, hole_diameter, corner_radius, chamfer_width,
  tooling_pitch, tooling_tap_diameter, tooling_close_diameter)`,
  `length`/`width` computed; `_tooling_places()` finds the most that
  fit.  `GRID_PLATE` is the same plate (same holes).  `KINDS`,
  samples, `examples/shop/tooling/grid_plate.toml`, `keepout.py`,
  `Shops.md`, schemas, tests updated; `tests.test_mount`'s
  `SMALL_PLATE` is 7 x 5 and builds in headless SolidCraft.
  `tool_models.size_letters()`: a drawn size that is not a field
  takes a free letter (the sketch still draws L, W until step B).
  `corner_radius` is C on cutters, Cr on the grid plate (test of one
  letter per key dropped).
* 171 tests (mount, setups, assembly, tool_models, shops,
  shop_schema, gui_fields, keepout) pass, about 1 minute.

## 2026-11-13: step B done, the top view from a made-up plate

* `tool_models.SKETCH_GRID`: `GRID_PLATE` at 16 rows x 12 columns,
  `tooling_pitch` 2P (1 in); corners 4 x 4 (`BREAK_COLUMNS`,
  `BREAK_ROWS`), each with 2 x 2 tooling holes in a checkerboard.
* Marks: E, P along the bottom and up the left; C and R as brackets
  (#36, `Dimension.bracket`, `TICK`), outside them; H on the lower
  right corner's last hole; Cr at the upper right; Tp over the upper
  left corner's top two tooling holes; Tc, Tt over the upper right
  corner's.  L and W no longer drawn.  `_size_rows()` gives R, C the
  units "Count" (`COUNTS`).  `TOOLING_SHIFT`, `_hole_y()` gone.
* Section view (T, Cw, H) unchanged, still from `GRID`; step C next
  (#32: a cross section line with edge and hole chamfers).

## 2026-11-13: #37 edge chamfer; step C done

* `GridPlate.edge_chamfer` (45 degrees, top outer edge; letter Ec;
  corners square or rounded at least that much): `_edge_bevel()`
  (volume, Pappus at rounded corners), `_outer_edges()` (a point on
  each side and corner arc for SolidCraft's chamfer).  `GRID_PLATE`
  and the example shop: 1/32 in.  `named(chamfer=False)` drops both
  chamfers.  `tests.test_mount` (37 tests, 41 s) builds the 7 x 5
  plate with it in headless SolidCraft; volume within 1 %.
* Step C: `tool_models._grid_section()` replaces
  `_grid_hole_section()`: a section along a row of holes, from the
  side across two holes to a break line, 6 times size (`DETAIL`):
  T, Ec, Cw, H.  No cutting plane line on the top view yet.
* The full `GRID_PLATE` model is not rebuilt yet (about 5 minutes,
  the next `show_demo.py` or setup that uses the chamfered plate).
* #38 done: `tool_models.Cut` and `_cut()` (thick dash-dot line,
  legs with arrows, the name outside), `View.cuts`; the grid plate's
  top view cuts A-A along the top row of holes (the bottom row's
  line would sit on the E/P extension line); the section is titled
  "Section A-A".

## 2026-11-13: #21 done, tool labels in the tree

* `shops.tool_label(item)`: function (kind, with `end` other than
  square and `roughing` in front) and sizes: diameter, radius ("R"),
  angle, drill diameter ("drill"), "N-flute", material; values with
  no space ("1/2in").  `shops.tool_order(item)`: function, then
  diameter (or radius) in inches.
* `tree.Node.shown` (replaces "NAME (KIND)") and `Node.order`;
  `shop_children()` puts directories first, then files by `order`
  (by name for non-tools).  `tests/test_gui_tree.py` `test_tools`.

## 2026-11-13: #40-#42

* #40: the corner rounding mill's `radius = "1/16 in"` (was
  "0.0625 in").  #41: countersink labels stay.
* #42: the user's GUI run showed only the grid plate's section (the
  panel showed one sketch, the first alphabetically).  Now
  `fields.sketches(item)` gives all of a kind's views, `_top` first;
  `views.Panel.sketch` is a column of `QSvgWidget`s (`Panel.views`,
  `show_sketches()`), each stretched by its drawn height.
* The user could not see A-A in the panel (drawn at about 1/4 size)
  nor tell what the section was.  Now: `View.caption` ("TOP",
  "SECTION A-A", drawn under the view in the SVG), `_hatch()` (45
  degree hatching on the section's cut faces), the cut line 5 px
  (`CUT_WIDTH`, `CUT_LINE`), `ViewShape.width`.  The user prefers to
  look in a GUI run over Claude's PNGs.
* The user: the section must match the top view.  Now A-A runs
  across the upper left corner only (from past the side to the
  middle of the gap), and `_grid_section()` draws that corner: the
  side, `BREAK_COLUMNS` (4) holes, the break line; `DETAIL` 4.

## 2026-11-13: Where things stand (end of session)

* The grid plate's sketches are done; the user: "Perfect".
* Done this session: #11, #14, #18-#22, #25-#30, #31-#42 (see
  above).  Decided, not done: #23 (`stock_materials/` and
  `tool_materials/`), #24 (light/dark from the desktop, no hard-coded
  colors, sketches recolored).
* Open: #10 (S3.5, `scraftcam/gui/README.md`, last; the user may edit
  it), #43 (sketch column 1:1 instead of 1:2?), #9 (left as is).
  Then step 4's rest (#80: a kind's directory shows its
  documentation) and step 5 (the HMI as a panel).
* Not yet run: the full chamfered `GRID_PLATE` rebuild (about 5
  minutes, the next `show_demo.py` with the chamfered plate); the
  full test suite (only the modules touched were run).

## 2026-11-13: Order corrected (the user)

* #10 (`scraftcam/gui/README.md`) comes at the very end of this
  task, after the LinuxCNC GUI (step 5) and the catalog work
  (`T.cm~5.1.10`) are merged in; it is not S3.5.
* Next: #24 (light/dark), then #23 (materials).  #43 (sketch column
  1:1?) explained to the user, waiting on an answer.

## 2026-11-13: #24 done (light/dark), waiting on the user's GUI run

* New `scraftcam/gui/theme.py`: `dark()` (`QStyleHints.colorScheme()`),
  `Colors`, `LIGHT`, `DARK`, `colors()`, `palette()` (Fusion's own
  for light; ours for dark), `apply()`, `follow()` (applies now and
  on `colorSchemeChanged`, then the windows' redraw),
  `sketch_text()` (recolors an SVG from `LIGHT`'s sketch colors).
* `views.py`: `ERROR_COLOR`, `BAD_STYLE`, `SHOWN_STYLE` gone; now
  `colors()` and `bad_style()`; sketches loaded through
  `sketch_text()`; `Panel.restyle()`.  `window.py`: `PROBLEM_COLOR`
  gone; `run()` calls `theme.follow(application, redraw_windows)`.
* Port `select` also answers `fields` (each field row's entry); its
  test had failed since S3.4 (the name is a field row now).
* `tests/test_gui_theme.py` (3 tests); the GUI tests (34) pass.
* The chamfered `GRID_PLATE` is in the cache
  (`Grid_plate__8465bd3902f772b5.step`, 5 min 17 s headless).

## 2026-11-13: #23 done, stock and tool materials

* `examples/shop/materials/` is now `stock_materials/` (`git mv`);
  new `tool_materials/` (`hss.toml`, `cobalt.toml`, `carbide.toml`),
  kind `tool_material` (`speed_factor`, `description`).
  `cutting_data.toml` lost `carbide_speed_factor` and
  `cobalt_speed_factor`.  `SHOP_DIRECTORIES` reads `tool_materials`
  before `tools`; `shop["tool_materials"]` is their list;
  `_tool_material()` finds a tool's by name, any capitals;
  `SPEED_FACTORS` is gone.  Internally the stock side is still
  `shop["materials"]`.
* The demo's G-code is byte for byte the same (697 lines, against
  HEAD in a worktree).  `Shops.md`, schemas (30) regenerated;
  shops, schema, tree, fields, machine tests pass.
* #43 explained to the user; 2:1 stays unless they say otherwise.

## 2026-11-13: #43 answered: lines fitted automatically

* The user drags the panel's lines all the time; asked that the line
  move left until it "bumps into something".  `Panel.fit()` (after
  each item is shown, by a zero timer): the rows | sketches line to
  the rows' own width (`MIN_SKETCH` 120 px kept for the sketches);
  the line above the text up to the text's lines, at most a third
  of the panel.  Dragging stays until the next item.  Test
  `test_fit`.  Waiting on the user's GUI run.
* The tree was not fitted at start: `TreeView.wanted_width()` used
  the column's width, which stretches to the view; now
  `sizeHintForColumn(0)`.  The tree refits when a branch opens or
  closes (`Window.tree_opened()`): 211 px closed, up to half the
  window with `tools` open.
* #44 (the user: no hint that the lines can be moved): every
  splitter is a `views.GripSplitter`, whose `GripHandle` draws three
  dots at its middle; handles 7 px, `palette(highlight)` on hover.
* The section A-A is drawn at 2 times size (`DETAIL`), about as wide
  as the top view (the user).

## 2026-11-13: Where things stand (end of session 2)

* Done since the last commit: #24 (light/dark, `gui/theme.py`), #23
  (`stock_materials/`, `tool_materials/`), #43 (lines fitted to the
  rows; the tree fits its labels and refits), #44 (grip dots, hover
  highlight), port `select` answers `fields`, the chamfered
  `GRID_PLATE` cached.  The user finds the GUI "very pleasant and
  natural".
* Next: the rest of step 4 (#80: a kind's directory shows its
  documentation, text left, SVG right), then step 5 (the HMI as a
  panel), the catalog work (`T.cm~5.1.10`), and last #10
  (`scraftcam/gui/README.md`).
* Not run: the full test suite (only the modules touched).
* #45 (the user): the top view shows where the edge chamfer meets
  the top: `_Broken.bevel()`, a thin line `edge_chamfer` in from the
  two outer sides and around the corner, break line to break line.

## 2026-11-13: #80 tried (step 4's rest), waiting on the user's look

* The user did not remember asking for #80; "Let's do it and see".
  #46-#49 taken as Claude recommended: a directory lists its kinds;
  a page is the description and letter table (no JSON/Python/TOML
  examples); Markdown in a `QTextBrowser`; no [Docs] on items yet.
* New `scraftcam/gui/docs.py` (no Qt): `pages()` cuts
  `Tool_Models.md` into `KindPage`s by the kind their sketches name,
  up to the first example, less sketch links and a lead-in
  paragraph; `directory_pages(name)` by `SHOP_DIRECTORIES`.
* `views.Panel`: `guide` (`kinds` list over `page`) between the rows
  and the sketches in `top`; `show_page()`.  `fit()` sets three
  sizes now.  Test `test_directory_pages`.
* The user: #80's guide was sticky (no way back to the rows) and not
  that useful; taken out (`views.py`, `tests/test_gui_fields.py`
  back to rev 732; `gui/docs.py` deleted).  Instead, tooltips on
  the tree (#80, the user's idea): `tree.Node.about`,
  `about_item()` (the kind's first sentence, then the item's
  `description`), `about_directory()` (the shop key whose meaning
  names "files in `DIR/`", else the first kind's summary), wrapped
  at `ABOUT_WIDTH` (60), no back quotes.  Test `test_about`.
