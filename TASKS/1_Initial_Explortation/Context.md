# LLM Agent Context Log

## State as of 2026-10-29

`catxtract.py` (one file, tkinter + PyMuPDF) works and the user has
marked pages 100 and 102-110 of `catalog.pdf` (the 2026 Shars catalog,
456 pages, Flipsnack, has a real text layer; no OCR needed).

* Run: `./catxtract.py catalog.pdf SharsMD 100-110` (range `SSS-EEE`
  or one page; none means the whole PDF).
* Packages come from `ezpkg` (the user is its developer), not a
  virtual environment: PEP 723 header plus the bootstrap, pasted
  verbatim (never edit it; it sits between `# fmt: off`/`on` and
  `# pylint: disable=all`/`enable=all`).  `catxtract.py.toml` marks
  the developer.  PyMuPDF lives in `~/.ezpkg/versions/pymupdf-2.0-*`;
  to import `catxtract` as a module in tests, put that on
  `PYTHONPATH` (the bootstrap only fetches when run as a program).
* Checkers: `.flake8` and `ruff.toml` have per-file ignores for the
  bootstrap (the user agreed).  `import pymupdf` carries
  `# type: ignore[import-not-found]`, so mypy does not check PyMuPDF
  calls.  All four checkers pass.
* Output: `SharsMD/page_NNN/page_NNN.md`, `page_NNN.json`
  (`{"regions": [...], "ignored": [...]}`; old plain-list files and
  kind `description` still load), `page_NNN_K.png`.  A page with no
  directory is not done.
* UI: row 1 "Actions:" Previous (p), Next (n), Undo (u), Region Up
  ([), Region Down (]), Ignore (x), Quit (q); row 2 "Mode:" Title (1),
  Text (2), Image (3), Table (4).  Drag adds, click selects, right
  click ignores.  Saving happens on page change, Quit and window close.
* Tables (generic): rows by vertical centers; column dividers from
  data rows only (gaps few rows cover); leading rows with under half
  digit-bearing words are headers, kept as separate rows with phrases
  whole; Markdown `|`s aligned.
* Suggestions (generic) for unsaved pages: PyMuPDF tables with at
  least 3 data rows; embedded images merged when within 10 points,
  kept if the long side is over 40 and the short side over 10 points
  and under 80% of the page; nearest earlier saved page's regions
  carried over (tables/images by matching detections, titles/text
  snapped to words) and its ignored regions not resuggested.  Score
  script idea: compare suggestions to the user's saved pages
  (IoU > 0.5, same kind); on 103-110, 31 of 60 matched.

## Open items (user's numbering)

2. Multi-page tables not detected.
3. Wrapped rows become two rows.
4. Page 100 first table: "2 Flute Square End" lands two columns left.
5. Title detection from font size / bold.
6. Page 105 full-page picture is vector drawings, not detected.

## Preferences

* Always point out generic vs Shars-specific solutions.
* User is token limited: quick over perfect, short reports.
* hg repository was created for Claude's checkpoints (`.hgignore`).
