# LLM Agent Context Log

catxtract's notes, copied 2026-11-07 from `../catxtract/TASKS/1_Initial_Explortation/Context.md` (`T.ie~1` there).  Their paths are relative to `../catxtract/`, and their `ezpkg`, PyMuPDF and `PYTHONPATH` instructions are out of date: since S2-S4 the code is `scraftcnc/catalog/catxtract.py` and `pdf.py` (`pdfplumber` + `pypdfium2`, fetched into `~/.scraftcnc/packages/`), run with `python3 -m scraftcnc.catalog.catxtract PDF OUTDIR`; see the dated entries at the end.

## State as of 2026-10-29 (end of second session)

`catxtract.py` (one file, tkinter + PyMuPDF) works well; the user calls
it "a winner".  `catalog.pdf` is the 2026 Shars catalog (456 pages,
Flipsnack, real text layer, no OCR needed).

* Run: `./catxtract.py catalog.pdf SharsMD` (no page range any more).
  It starts at the first page with no `page_NNN` directory.
* Packages come from `ezpkg` (the user is its developer), not a
  virtual environment: PEP 723 header plus the bootstrap, pasted
  verbatim (never edit it; it sits between `# fmt: off`/`on` and
  `# pylint: disable=all`/`enable=all`).  `catxtract.py.toml` marks
  the developer.  To import `catxtract` in tests:
  `PYTHONPATH=$HOME/.ezpkg/versions/pymupdf-2.0-cpython-312-linux-x86_64`
  (the bootstrap only fetches when run as a program).  Test against a
  copy of `SharsMD` in the scratchpad, never the real one.
* Checkers: `.flake8` and `ruff.toml` have per-file ignores for the
  bootstrap (the user agreed).  `import pymupdf` carries
  `# type: ignore[import-not-found]`.  All four checkers pass.
* Output: `SharsMD/page_NNN/page_NNN.md`, `page_NNN.json`
  (`{"regions": [...], "ignored": [...]}`), `page_NNN_K.png`.  A page
  with no directory is not done.  The `.md` is `# Page NNN`, then a
  links paragraph `Previous: [Page M](../page_MMM/page_MMM.md) | Next:
  ...` (or `none`) to the nearest saved pages; saving a page rewrites
  that line in it and its two saved neighbors (`write_links()`).
* UI is mouse only (keyboard commands removed, except typing in the
  Goto box).  Rows:
  1. Page: Next New, Next, Prev., Prev. New, Goto [5-digit box,
     Enter works; 0 means 1, past the end means last page], Quit.
     Buttons grey out when they have nowhere to go.  "New" = no
     directory yet.
  2. Region: Region Up, Region Down, Cycle Up (newer), Cycle Down
     (older, newest first, wraps), Delete, Undo, Clear.
  3. Mode: Title, Text, Image, Table; also sets the kind of the
     selected region.  A newly drawn region is selected.
  Status line: `Page N of 456  Edited E/T=P%  Next region: KIND  msg`
  (progress recounted on each page change).
* Drag adds, click selects, right click ignores (Ignore = remove and
  remember in `.json` so it is not suggested on later pages; no
  button, by the user's choice).  Delete just removes.
* Leaving a page (or Quit/close) saves it if it has, or had, regions,
  including untouched suggestions; the user confirmed that is right.
* Internally, `App.command(key)` still dispatches on the old one-letter
  keys (e.g. `N`, `n`, `y`, `Y`, `d`) as command names.
* Tables and suggestions: unchanged from the first session (rows by
  vertical centers, dividers from data rows, header rows; PyMuPDF
  tables with 3+ data rows, merged embedded images, carry-over from
  the nearest earlier saved page).

## Index mode (2026-10-30, third session)

The user likes this.

* Page buttons are now Prev. New, Prev., Next, Next New; `Index Update`
  sits before `Quit`.
* Mode `Index` (`lines_inside()`, `index_rows()`, `page_link()`,
  `INDEX_LINE`) writes a two column table, `Item` and `Pages`, one row
  per line, for each index region, left to right.  The index is PDF
  pages 451-455 (printed page numbers equal PDF page numbers).
* A heading line gets a row with no pages.  An indented line starts
  with `* `.  `~` is written as `-`.
* An item links to the first page listed, only if that page's `.md`
  exists at save time.
* Each page or range after a comma also gets a `+ NNN` row, whose
  `Pages` is that piece; the main row keeps the whole list.  The user
  approved this.
* `App.update_indexes()` rewrites every saved page with an index
  region.  The current page stays on screen; a fresh one stays unsaved.
  Tested only on a scratch copy, by invoking the button from a script.
* In the real `SharsMD`, only `page_452.md` was regenerated with the
  final format by Claude; the user will press `Index Update` for the
  rest, and again as more pages get extracted.
* To drive `App` from a script: `PYTHONPATH` as above plus `.`, then
  `a = App(...)`, `a.root.withdraw()`, set `a.page_no`, `a.show_page()`,
  `a.save()`, `a.root.destroy()`.

## Open items

Dropped (the user, 2026-11-07): `catxtract` works well enough.

## Preferences

* Always point out generic vs Shars-specific solutions.
* User is token limited: quick over perfect, short reports.
* Number list items and keep numbers when re-listing.
* `hg` is for Claude's checkpoints; `.hgignore` ignores `.git/`.

## 2026-11-07: Moving into `scraftcnc` (`T.cm~5.1.9`)

* `SharsMD/` now lives in `scraftcnc/SharsMD/` (ignored by git and
  hg; the user backs it up); `../catxtract/SharsMD` links back to it,
  so the old program still runs.
* Decided: `catxtract.py` goes to `scraftcnc/catalog/` for now (one UI
  program eventually); `ezpkg` will be dropped; PyMuPDF fetched on
  first use (probably on entering Catalog mode); the paths in these
  notes get fixed when the code moves.
* `../catxtract/` is deleted only after all of it is integrated here
  and committed to GitHub.
* Decided (2026-11-07): try `pdfplumber` (MIT) in place of PyMuPDF
  (AGPL); bring `catxtract`'s 8 commits in with `git subtree add`,
  as `T.mp~5.1.1` did for `pybind/`.  Steps: S1 move (subtree) and
  run unchanged; S2 drop `ezpkg`, fetch the PDF package on first use;
  S3 checkers; S4 tests, skipped without the package; S5 notes and
  README; S6 Catalog mode in the HMI (one UI program; no separate
  task).
* Decided (2026-11-07): Claude runs `git subtree add` (its merge
  commit is allowed, as in `T.mp~5.1.1`); keep only `catxtract.py`
  and `catxtract.py.toml`, drop the rest (README folded into these
  notes).  S2 judges `pdfplumber` against PyMuPDF by a script that
  reports table, row and cell counts on pages 100, 105 and 452; the
  user checks differing pages in the GUI.  Claude may browse a few
  `SharsMD/` `.md`/`.json` files, never all of them.

## catxtract's README (folded in, S1)

# **catextract** -- Catalog Information Extraction

Many catalogs are distributed in PDF (Portable Document Format).  These
typically contain a product image, descriptive text, part number, price, etc.
Frequently there is a table of related parts, each with a part number, some
part characteristics, price, minimum quantity, etc.

The `catextract` program is a graphical user interface that allows the user
to identify the name, description, and tables on a catalog page.  This
information is extracted and entered into a Markdown (`.md`) file on a
page by page basis.


## 2026-11-07: S1

* `git subtree add --prefix=scraftcnc/catalog ../catxtract main`: merge
  commit `82af26d` (8 commits of history).
* Staged (uncommitted) removals: `aic` link, `CLAUDE.md`, `.flake8`,
  `.gitignore`, `.hgignore`, `ISSUES/`, `README.md` (folded in above),
  `ruff.toml`, `RULES/`, `TASKS/`.  Kept `catxtract.py`,
  `catxtract.py.toml`; added `scraftcnc/catalog/__init__.py`.
* `python3 -m scraftcnc.catalog.catxtract --help` prints the usage
  (docstring) and exits; the `ezpkg` header was not edited.  No GUI run.

## 2026-11-07: Where things stand (end of session 1)

* S1 done: merge `82af26d`; only `catxtract.py`, `catxtract.py.toml`
  and `__init__.py` in `scraftcnc/catalog/`; `python3 -m
  scraftcnc.catalog.catxtract --help` works.  PyMuPDF is not in the
  system `python3`; the GUI still runs only through the `ezpkg`
  bootstrap (`python3 scraftcnc/catalog/catxtract.py
  2026_Shars_Catalog.pdf SharsMD`) until S2.
* Next: S2, done inline by Claude (no step-worker unless it grows):
  drop `ezpkg`; fetch the PDF package on first use; try
  `pdfplumber`, judged by the count script on pages 100, 105, 452
  against PyMuPDF (kept available until judged); fall back to
  PyMuPDF plus a README license note if `pdfplumber` falls short.
* Then S3 checkers (the `ezpkg` ignores go away), S4 tests (skipped
  without the package), S5 notes and README (fix this file's
  catxtract paths), S6 Catalog mode in the HMI.
* `../catxtract/` is deleted only after all this is committed and
  pushed; its `SharsMD` is now a link to `scraftcnc/SharsMD/`.

## 2026-11-07: S2 started (session 2)

* `pip` cannot be assumed (Ubuntu's Python has none).  Shown to
  work, with the system `pip` hidden (`python3 -I -S`): fetch pip's
  wheel from `https://pypi.org/pypi/pip/json` (urllib, curl
  fallback, SHA-256 checked), run `python3 WHEEL/pip install
  --target DIR pdfplumber`.  Gets `pdfplumber` 0.11.10, `pdfminer.six`,
  `pypdfium2` (renders pages), Pillow; all permissive licenses.
* The `ezpkg` bootstrap, PEP 723 header and `catxtract.py.toml` are
  deleted (the user agreed); `catxtract.py` imports `json` and `sys`
  itself.  It does not run until the rewrite (no PyMuPDF).
* Checkers before the rewrite: `pylint` and `ruff format` clean;
  `ruff check` and `mypy` left with the 3.12 `type` alias
  (`catxtract.py:77`) and `zip()` without `strict=`
  (`catxtract.py:312`).
* Next: rewrite onto `pdfplumber` + `pypdfium2` with our own `Rect`;
  packages fetched on first use into `~/.scraftcnc/packages/`
  (proposed, not yet confirmed); then the count script on pages 100,
  105, 452 against PyMuPDF.

## 2026-11-07: Package fetching done (S2, part 1)

* The installed package is read only (the user); all writes go under
  `~/.scraftcnc/`.  `scraftcnc/home.py` (`make_directory()`) creates
  it with `Created ~/.scraftcnc/ directory to cache information.` on
  stderr; `model_cache.py` uses it too.
* `scraftcnc/packages.py` (`require(module, requirement)`): fetches
  pip's wheel into `~/.scraftcnc/pip/`, installs into
  `~/.scraftcnc/packages/cpython-312/` (`--no-warn-conflicts` hides
  pip's report on unrelated system packages).  Tested with a fake
  `HOME` and `python3 -S` (no system pip): installs, second run quiet.
* `catxtract.py`: 3.11 `TypeAlias`, `zip(strict=False)`, pylint
  limits quieted by name.  All four checkers clean on the four files.
* Next: the rewrite onto `pdfplumber` + `pypdfium2`.
* Later the same day: `~/.scraftcnc/` hidden on Windows (`attrib +h`),
  checked by `tests/test_home.py`, added to the Windows/Linux CI
  workflow's offline tests (`probe_linuxcnc.yml`).  `pip`'s stdout is
  dropped; anything on its stderr is an error exit.  `.pylintrc`:
  `max-module-lines = 10000` (the user).  `App.command()` dispatches by
  a dictionary to private `App._...()` methods (public method limit);
  `best_match()` replaces the loop `lambda`.  The user dislikes
  `lambda`s: prefer local functions.

## 2026-11-07: S2 rewrite done, awaiting the user's GUI check

* `scraftcnc/catalog/pdf.py`: the only module touching the libraries
  (`Rect`, `Page`, `Document`; `pdfplumber` text/images/tables,
  `pypdfium2` drawing).  `catxtract.py` no longer mentions PyMuPDF.
  Run with `python3 -m scraftcnc.catalog.catxtract PDF OUTDIR`.
* `lines_inside()` uses pdfminer's layout lines (a second
  `pdfplumber` handle with `laparams={}`, opened only when needed,
  ~1 s a page), sorted top to bottom: keeps index indents, keeps the
  full width footer whole (so it stays out), and puts the big section
  letters (D, E, F, G on page 452) before their sections (PyMuPDF put
  them at the column's end).
* Compared with PyMuPDF (scratch copy of the old file): pages 100 and
  105 identical; page 452 index identical except those letters.  On
  10 saved pages with images, image suggestions identical; table
  suggestions differ on 8 (pages 1, 15, 27, 44, 72, 107, 127, 146):
  splits, extra small tables, tighter boxes than PyMuPDF's page sized
  ones.  The user is to judge in the GUI.  Suggest 2.5x faster.

## 2026-11-07: S4 tests

* Decided: keep `pdfplumber` (on pages 15, 27, 44, 107 its table
  suggestions beat PyMuPDF's: two side by side tables instead of one,
  small tables PyMuPDF missed, photos no longer swallowed).
* `pdf.py` fetches the packages in `Document()`, not on import.
  `Document.close()` added (the tests and Quit call it).
* `tests/test_catalog_pdf.py`: 7 tests on a one page PDF written by
  hand into a temporary directory (no binaries in git, the user's
  wish): `Rect`, words, text, `lines_inside()` indents, `detect()`
  (ruled table + inline image), `table_rows()`, `png()`.  Skipped
  when the packages are not in `~/.scraftcnc/packages/`.
* Relevant tests pass (`test_catalog_pdf`, `test_home`,
  `test_model_cache`: 30).  The user: never the full suite, and no
  agents without asking.  Next: S5 notes and README, S6 Catalog mode
  in the HMI.

## 2026-11-07: S5 done; S6 design questions open (end of session 2)

* S5: `README.md` lists `catalog/`, `home.py`, `packages.py`, and the
  PyPI fetch in Requirements; the copied notes above are marked out of
  date.
* S6, the user's design (2026-11-07): a separate [Catalogs] tab in the
  HMI, listing each catalog downloaded as a PDF.  Top rows:
  `Catalog Name: [...] [Create] [Delete]` ([Delete] pops up `Really
  delete: [Yes] [No]`), then `PDF File Name: [...]`; [Create] greyed
  out while that file does not exist.  Below: an alphabetical,
  scrolling list of catalog names (a sub-directory each).  Selecting
  one ungreys [Enter], which leads into the catxtract GUI.  The user
  expects room for improvement.
* Open questions, Claude's recommendation after each; the user was too
  tired to decide, and will answer next session (numbers sticky):
  14. Where catalogs live.  Rec: `~/.scraftcnc/catalogs/NAME/`, never
      swept; change the "to cache information" message and README,
      since `~/.scraftcnc/` would then hold the user's work, not just
      caches; move `scraftcnc/SharsMD/` to
      `~/.scraftcnc/catalogs/Shars/`.  Alternative: a separate
      directory (e.g. `~/scraftcnc_catalogs/`).
  15. HMI without LinuxCNC.  Today LinuxCNC starts the HMI as its
      display.  Rec: the HMI can also start alone, opening on
      [Catalogs], the machine tab greyed out with no LinuxCNC.
  16. What [Create] does with the PDF.  Rec: copy it to
      `NAME/catalog.pdf` (Shars is 60 MB).  Alternative: record the
      original's path.
  17. Safe [Delete].  Rec: pop-up names the loss (`Really delete Shars
      (254 pages extracted): [Yes] [No]`); Yes renames to
      `NAME.deleted` rather than erasing.
  18. Where catxtract's view goes after [Enter].  Rec: it replaces the
      [Catalogs] tab's contents, with a [Back] button that saves and
      returns to the list (page fit to screen height loses a little to
      the tab bar).  Alternatives: a separate window, or a tab per
      open catalog.
  Queued, not yet raised: 19 a [Browse...] button for the PDF; 20 each
  catalog's progress (pages done) in the list; 21 rules for catalog
  names.
* The HMI (`scraftcnc/hmi/lcnc_hmi.py`, 2899 lines) has no tabs today
  (no `ttk.Notebook`).
* Next session: answer 14-18, then code S6 (ask before any agent; only
  the relevant tests, never the full suite), then delete
  `../catxtract/` after S6 is committed and pushed.

## 2026-11-08: Suspended

Suspended by the user in favor of `T.osiade~5.1.9` (Organize Shop
Information and Data Entry): shop information has no organizing
strategy yet.  Open questions 14-21 (above) and deleting
`../catxtract/` (22) wait on it.

## 2026-11-12: Reopened: port `catxtract` to Qt first

Reopened by the user, as `catxtract.py` is the last `tkinter` code
(the HMI is Qt now, `T.hs~5.1.5`).  Decided: a straight port to Qt
first (same look and behaviour, `python3 -m scraftcam.catalog.catxtract
PDF OUTDIR`), before any Catalogs tab.  #14 replaced by
`T.osiade~5.1.9` #64 (the user's data in a directory under their own
version control).  #15 settled by `T.osiade~5.1.9` #1 (LinuxCNC only
when needed).  #16-#22 will probably be re-architected completely.
(Paths above say `scraftcnc`; the package is now `scraftcam`, and
`SharsMD/` is at the top of the tree, ignored by git and hg; the
link `../catxtract/SharsMD` -> `../scraftcnc/SharsMD` broke when the
directory was renamed.)

## 2026-11-12: `catxtract` in Qt

Straight port: `App(QWidget)` (`App(pdf, out_dir, parent=None)`, so
it can be the Catalogs tab later), same three button rows, status
line and mouse use; a `PageView(QWidget)` paints the page (a
`QPixmap` from `Page.png()`) and the regions (`QPainter`; selected
thick and dashed) and the rectangle being dragged (`dragging`), and
passes presses (left: drag/select, right: ignore) to `App.on_press()`,
`on_release()`, `on_delete()` (screen x, y now, not Tk events).
Mode buttons: checkable, in an exclusive `QButtonGroup`
(`kind_buttons`, was `kind_var`), text in the kind's color
(`dark orange` is now `darkorange`).  Goto box: a
`QRegularExpressionValidator` (`\d{0,5}`).  Quit and the window's
close both reach `closeEvent()`, which saves and closes the PDF once
(`closed`).  `require("PySide6")` at import.  `App.save()`'s lambdas
became local functions.  `tests/test_catalog_pdf.py` no longer needs
`tkinter`, and has `AppTest` (3, offscreen through `tests/qt_hmi.py`:
drag a title with `QTest` mouse events and save on Quit, click
select and right-button ignore, page buttons and the Goto box).  All
10 pass; checkers clean.  No `tkinter` code is left in the tree.  Not
yet: the user's GUI check on the real catalog
(`2026_Shars_Catalog.pdf` at the top, `SharsMD/`, 253 pages).

## 2026-11-12: First GUI run of the Qt `catxtract`

The user ran it on a scratch copy of `SharsMD/` (in Claude's
scratchpad): it closed cleanly (exit 0, nothing on standard error),
with 10 new pages saved (207, 409-417); the only changes to old pages
are the neighbor links (206, 210, 345), as expected.  The real
`SharsMD/` is untouched.  Waiting on the user's verdict.

## 2026-11-12: The Qt port is a success (the user)

Second GUI run, on a fresh scratch copy, pages 207-209 (the first
three unmarked pages in a row): the user checked that their edits
were kept, and is happy with what was saved.  The "kind of broken"
of the first run was not the port: a page with no saved regions
starts with suggestions carried over from the nearest earlier saved
page (`suggest()`, unchanged from `tkinter`), which look like another
page's content when the layout differs; the user usually presses
Clear first.  Worth a rethink with #16-#22 (e.g. carry-over only on
request).  The `tkinter` replacement is done.  The scratch copies'
pages were not copied into the real `SharsMD/`.
