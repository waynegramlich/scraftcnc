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
3. Shop schema and files: S3.1-S3.3 done; S3.4, S3.5 next.
4. Tool documentation and SVG (#5, #80).
5. Machine control: the HMI as a panel (#6).

Each step: offscreen tests, checkers, the user's GUI run; done only
when the user likes it (#85, #112).

## Where Things Are

* `scraftcam/gui/`: `app.py` (model, no Qt), `window.py` (windows,
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

## Next: S3.4, the Fields Panel (#72, #132)

Clicking a shop item shows a row per field, in `KINDS` order: entry
light red while bad, the value in the shop's units in grey, help as
tooltip; written with `shop_writer.item_text()` when focus leaves a
field, never a bad value.  Scalars only (measurements, strings,
choices); lists and nested tables read only as TOML for now; sketches
in step 4.  Then S3.5: `gui/README.md`, tests.

Open from S3.2: materials now list alphabetically (by file name);
the example shop's `notes` still mention `materials.toml`.
