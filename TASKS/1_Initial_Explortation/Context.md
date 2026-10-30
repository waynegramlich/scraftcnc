# LLM Agent Context Log

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

## Open items (user's numbering, from the first session)

2. Multi-page tables not detected.
3. Wrapped rows become two rows.
4. Page 100 first table: "2 Flute Square End" lands two columns left.
5. Title detection from font size / bold.
6. Page 105 full-page picture is vector drawings, not detected.

## Preferences

* Always point out generic vs Shars-specific solutions.
* User is token limited: quick over perfect, short reports.
* Number list items and keep numbers when re-listing.
* `hg` is for Claude's checkpoints; `.hgignore` ignores `.git/`.
