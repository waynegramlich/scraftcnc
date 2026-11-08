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

* Git: commit `4185f6e` ("5.9.1 - ...") was reworded locally to
  `be77023` ("5.1.9 - ..."), with the user's `eef7b7c` replayed on
  top as `15dc20f` (same files).  `main` is ahead 2, behind 2 of
  `github/main`; the force push (`git push --force-with-lease=
  main:eef7b7c github main`) was blocked by Claude Code's auto mode,
  so the user runs it, or `git reset --hard github/main` keeps the
  typo.  Until then, do not pull with rebase.
* The item is Open (2026-11-08).
* Next: more design issues (numbered from #13), a top five per round.
  Held back so far: the tab layout (nested Shop sub-tabs or a tree),
  the unit entry widget (keep what was typed, show the shop's units),
  new shops from a template (`T.sm2~5.5`, `T.ipfds~5.6`), undo and
  unsaved changes on quit, a "show in SolidCraft" button, drawing
  shared between SVG and Canvas (#5), the order in which `lcnc_hmi.py`
  becomes the HMI tab (with the headless HMI and `show_demo.py` still
  working), and fitting shop floor screens.

## 2026-11-08: Issues #13-#17 raised

#13 order of steps (and `lcnc_hmi.py` becoming the HMI tab); #14 tab
layout (nested notebooks or a tree that mirrors the directories);
#15 entering values with units; #16 one drawing for both SVG and
Canvas; #17 unsaved changes and undo.  Still held back: new shops
from a template, a "show in SolidCraft" button, shop floor screens.

## 2026-11-08: Decisions #13-#17

13. Agreed order: S1 the TOML reader and writer (#8); S2 the field
    descriptions (#9) with the reader's checks moved onto them; S3 the
    GUI window with only the HMI tab (`lcnc_hmi.py` moves in, LinuxCNC
    starts it with #1's flag); then the Tools, Machines, Stock and
    Catalogs tabs.  `lcnc_hmi_headless.py` and `./show_demo.py` keep
    working at every step.  The user: "This feels like a Step 1."
14. Nested tabs (Shop: Machines, Tools, Stock, Catalogs; HMI).  One
    consistent way to close a tab together with its child tabs.  A
    tree of the hierarchy on the left side as well, with an easy way
    to show or hide it.
15. A field keeps what was typed, checked on leaving the field, with
    the value in the shop's preferred units shown in grey beside it.
    White space between tokens is silently compressed to one space.
16. One drawing per tool (lines, arcs, dimension letters from #9),
    drawn both as SVG (`Tool_Models.md`) and on the Canvas (#5).
17. History: the user can look back in time at edits.  In history
    mode nothing can be edited, but an old entry can be copied to the
    clipboard; out of history mode, a paste-from-clipboard button.
    Kept simple.  Open: where the history comes from (`git`, `hg`, or
    a log of our own), and per field or per file.

Next round: issues from #18 (new shops from a template, a "show in
SolidCraft" button, shop floor screens, the history question in #17).
