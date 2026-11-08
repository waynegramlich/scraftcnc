# LLM Agent Context Log

## 2026-11-08: One GUI, first decisions

Issue numbers are sticky and never reused; new ones continue after the
highest.  Decided (the user):

1. The GUI starts without LinuxCNC; `linuxcnc` is imported only when
   the HMI tab connects.  LinuxCNC may still start it (as `[DISPLAY]
   DISPLAY`) with a flag that opens the HMI tab.
2. Stop and the "program running" state are visible whatever tab is
   showing; while a program runs, the shop tabs are read only.
3. One GUI, not one file: a thin window, each tab its own module, the
   logic apart from the widgets (as `lcnc_hmi_headless.py` is), so the
   tests need no display.
4. Our own TOML reader and writer (the format is simple); tests compare
   our reader against `tomllib`.
5. Tool sketches are drawn on a tkinter `Canvas` (no SVG in tkinter).
6. The HMI is a tab of the GUI.
7. The Catalogs tab fetches `pdfplumber` only when first opened, so
   the GUI starts with no network.

## 2026-11-08: Decisions #8-#12

8. Lossless round trip: our reader keeps comments, order and spacing;
   a save rewrites only the edited lines.  Only the TOML subset the
   shop files use; anything else is reported at its file and line.
   Tests: our reader agrees with `tomllib` on every example file, and
   read then write gives the same bytes.  One of the very first steps.
9. One description of each kind's fields (name, unit kind, required,
   default, help, sketch letter) drives the forms, the reader's
   checks, `Tool_Models.md`'s tables and the Canvas letters.  Fields
   will be added later, and a new field ALWAYS goes at the end.
10. Shops with errors: the GUI must never crash; it reports the
    problems (file and line).  No great effort to recover from the
    user's own errors.
11. Hand edits stay allowed.  When a file changes outside the GUI,
    the GUI detects it and asks whether to keep the hand edit or the
    GUI's.
12. Hierarchical TOML is already supported.  `scraftcnc` controls all
    sub-directory names.  The arrangement may change during
    development; afterwards only new sub-directories appear, never a
    rename or a deletion.

## 2026-11-08: Where things stand (the user is away)

* Git: the last commit's message was fixed by `git commit --amend`
  ("5.9.1" -> "5.1.9", now `57d0fac`).  The old commit is on
  `github/main`, so `main` is ahead 1, behind 1.  Waiting for the
  user's OK to `git push --force-with-lease github main`.
* The item is still Pending; ask whether to open it.
* Next: more design issues (numbered from #13), a top five per round.
  Held back so far: the tab layout (nested Shop sub-tabs or a tree),
  the unit entry widget (keep what was typed, show the shop's units),
  new shops from a template (`T.sm2~5.5`, `T.ipfds~5.6`), undo and
  unsaved changes on quit, a "show in SolidCraft" button, drawing
  shared between SVG and Canvas (#5), the order in which `lcnc_hmi.py`
  becomes the HMI tab (with the headless HMI and `show_demo.py` still
  working), and fitting shop floor screens.
