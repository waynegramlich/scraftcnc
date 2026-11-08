# LLM Agent Context Log

catxtract's notes, copied 2026-11-07 from `../catxtract/TASKS/1_Initial_Explortation/Context.md` (`T.ie~1` there), unchanged so far; its paths are still relative to `../catxtract/`, until the code moves here (`T.cm~5.1.9`).

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
