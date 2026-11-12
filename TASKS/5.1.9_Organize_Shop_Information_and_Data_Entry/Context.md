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

## 2026-11-12: Decisions revisited (#1-#17 reopened)

The user: the GUI, not hand typing, is how shop data gets entered.
The data is a tree, mirrored as directories, sub-directories and
TOML files.  Decided:

18. Hand edits stay allowed, but a file that does not read cleanly is
    reported, and the user must fix it by hand.  TOML `#` comments are
    ignored and not kept; comments are a field of our own data
    structures, shown by the GUI.  (Replaces the lossless round trip
    of #4 and #8: `tomllib` reads, a small writer of ours writes.)
19. A directory is a branch; a `.toml` file is one item (a tool, a
    machine, a material); a directory may have a file of its own
    settings.  May change later.
21. (c) a browser GUI: rejected ("a Javascript nightmare").  (a)
    `tkinter` or (b) Qt: being decided; the user leans to Qt for SVG.
22. The step order (#13) waits on #21.

## 2026-11-12: #23-#43

* #23: download size does not matter.  #24/#28: no superuser on
  student workstations; LinuxCNC itself needs it once (`sudo apt-get
  install podman distrobox`, or WSL's administrator), so only the shop
  GUI must run without it.
* #25/#38-#41 (the user's summary): there is a way to install `uv`
  without admin privileges, and `uv`'s Pythons bundle Tk (3.14: Tk
  9.0).  `uv` is a wheel on PyPI, so `packages.py` can fetch it.
* #30-#32: Tk has no native Wayland; it runs under XWayland.  The user
  will drop X11 if Wayland is fully supported.
* #42: Qt (PySide6 from PyPI) runs natively on Wayland, which removes
  the `libxcb-cursor0` (X11 only) root problem.  #43: testing it now.

## 2026-11-12: #43 test result: Qt on Wayland works with no root

`uv pip install PySide6-Essentials` (6.12.0) into a scratch venv: 9 s,
244 MB, no root.  Its wheel carries `libqwayland.so`, which needs only
`libwayland-client`, `libwayland-cursor` and `libxkbcommon` (no
`libxcb-cursor`).  In a nested `kwin_wayland` (on this X11 desktop),
with `DISPLAY` unset and `QT_QPA_PLATFORM=wayland`, a `QSvgWidget`
window drew an end mill sketch with dimension letters;
`platformName()` was `wayland`.

## 2026-11-12: #52, #53 decided

52. macOS support is officially dropped (LinuxCNC needs a VM there).
    Supported: Linux (Wayland only) and Windows (WSL for LinuxCNC).
53. `scraftcnc` is published on PyPI.  The user: `pip` need not be
    preinstalled; we fetch its wheel ourselves (`urllib` or `curl`)
    and run it.

## 2026-11-12: #21 Qt; #54-#60 decided

21/60. Qt (PySide6) is selected over `tkinter`.
54. A standard-library-only bootstrap script on GitHub
    (`install_scraftcnc.py`): fetches `pip`'s wheel, runs it to install
    `scraftcnc` from PyPI; running it again upgrades.
55. Installed into `~/.scraftcnc/venv/`, made with `python3 -m venv
    --without-pip` (so Ubuntu's missing `ensurepip`/`python3-venv` does
    not matter); no `pip install --user` (PEP 668).
56. Launchers: `~/.local/bin/scraftcnc`; Windows `.cmd` and Start Menu
    shortcut; a Linux desktop menu entry (`.desktop` file).
57. PySide6 is a normal dependency in `pyproject.toml`; `pdfplumber`
    stays on demand or an optional extra.
58. Every download is checked against PyPI's published SHA-256.
59. No `uv` dependency.

## 2026-11-12: Where things stand

* The user leans to renaming the package `scraftcam` (SolidCraft
  Computer Aided Manufacturing); not reserving it on PyPI yet (#63).
* Next: reopen `T.hs~5.1.5` and port the HMI (`scraftcnc/hmi/`) to
  Qt.  Still open here: #61 the new step order (#22), #62 a quick pass
  over #1-#17 against Qt (#4/#8 replaced by #18; #5/#16 Canvas become
  Qt drawings; #6 means the Qt port; #15 can use Qt validators).
* `show_demo.py` starts the HMI with the host's `sys.executable` (the
  system Python 3.12, PEP 668), so PySide6 needs a development venv
  on the host before the port.
* (Earlier hg messages today say `T.oside`; the tag is `T.osiade`.)
