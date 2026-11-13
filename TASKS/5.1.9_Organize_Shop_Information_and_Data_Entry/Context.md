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

## 2026-11-12: Git settled

The user force pushed: `github/main` is `1fe9d36` with the reworded
"5.1.9" commits; the 2026-11-08 "do not pull with rebase" caution is
over.

## 2026-11-12: #55 replaced: no venv

No venv anywhere: packages go in with `pip --target` into
`~/.scraftcam/packages/<cache_tag>/` (`packages.require()`), and
`scraftcam` itself too, from the bootstrap installer; its launcher
puts the directory on `sys.path`.  See `T.hs~5.1.5`'s `Context.md`.

## 2026-11-12: The HMI is in Qt; resume here

`T.hs~5.1.5` is closed again: the HMI is Qt (`scraftcam/hmi/lcnc_hmi.py`,
an `HMI(QWidget)`, so it can become a tab of this GUI; the parts with
no toolkit in `hmi_machine.py`; headless is offscreen Qt), PySide6 is
fetched by `packages.require("PySide6")` into its own directory
(pins and SHA-256 digests in `scraftcam/pins.toml`; no venv, #55
replaced), and the package is `scraftcam`.  Offscreen widget tests
use `tests/qt_hmi.py`.  Still open here: #61 the new step order (#22),
#62 a pass over #1-#17 against Qt, and `catxtract.py`'s `tkinter`
window (to Qt, in this GUI).

## 2026-11-12: Round after the Qt HMI (#61, #62, #64)

* #61 (step order): many earlier decisions need revisiting first; the
  order waits on that.
* #62: broken out into #62.1-#62.N, one decision of #1-#17 each,
  worked through one by one.
* #1 confirmed: LinuxCNC is deferred until it is really needed (the
  HMI tab); settles `T.cm~5.1.10` #15.
* #64 (new): where everything lives must be rethought.  The user: all
  of the user's shop, tool, etc. data lives in a directory that they
  keep under their own favorite version control system.  Replaces
  `T.cm~5.1.10` #14 (`~/.scraftcam/catalogs/`).
* First: `catxtract` ported to Qt (`T.cm~5.1.10`), to remove the last
  `tkinter` code.

## 2026-11-12: Revisiting the decisions, by their own numbers

The user: the decisions are revisited under their own numbers (#1,
#2, ...; not #62.N), five at a time, starting with #1-#5.

## 2026-11-12: Decisions #1-#5 revisited

1. The GUI starts LinuxCNC only when needed.  `show_demo.py` is a
   test program; eventually it is replaced by `scraftcam DESIGN
   SHOP`: DESIGN a directory tree of the user's Python files (likely
   written with an AI's help) that use our classes to make a
   parametric assembly; SHOP the shop with the machines that make it.
2. Stop is visible whenever a machine is running.
3. Replaced (the user's preferences are not everyone's): everything
   can be done from one window, but pop-up windows are allowed; two
   or more windows showing the same content are always kept in sync.
4. Agreed: our writer writes a key order we choose, so diffs in the
   user's version control stay small.
5. Agreed: tool sketches are the SVG `Tool_Models.md` uses, shown in
   a `QSvgWidget` (settles #16).
Rule for this round: a settled decision leaves the top five, and the
next open one is added at the bottom.

## 2026-11-12: Decisions #2-#10, #65, #66

2. More than one machine may run at once.  Whenever more than one
   is running, a [Stop All] button shows in the upper left corner of
   every open window.  No machine may run with its control window
   closed.
3, 4, 5, 8: agreed as proposed (windows in sync through one model per
   item; key order from the field descriptions; SVG in `QSvgWidget`;
   #8 replaced by #18).
6. Agreed (the HMI is a tab), likely to change in implementation.
7. Probably no [Catalogs] tab: a hierarchical tree widget instead
   (big change).  Each window has one or more sub-panels; a button
   always brings up the tree; clicking an item makes the window's
   other views show content for it.  (Affects #14.)
9. A metadata file will describe the fields and values of everything
   in a TOML file.  Open: has the TOML world solved this already?
10. Agreed; keep-outs guard against the most common crash (a bit into
    tooling).
65. Leaning: the user names a Python file with a `main()` function;
    its directory is the design tree's root, everything else in it or
    below.  Shops alike, as TOML: a top file, its directory the root.
66. Agreed: the design runs in its own process, again when its files
    change.

## 2026-11-12: Decisions #9, #11, #12, #65, #67

9. Field metadata: try JSON Schema, "enhanced" as needed (our own
   keywords).  JSON and TOML are largely interchangeable, and TOML
   embeds better in `.nc` files, so the schemas are written in TOML
   and converted to JSON for the tools; if that fails, JSON vs TOML
   for schemas is revisited.
11. The user's files are kept under revision control (git, hg); the
    GUI may need a pop-up when a file is revised outside it.
12. Some directories are ours, the rest the user's.  The user never
    changes our schema, and we never change theirs.
65. `main()` returns 0 for success, non-zero otherwise; the user puts
    whatever code they like in it.
67. Agreed: closing a running machine's control window is refused
    ("Stop the shop mill first").

## 2026-11-12: Decisions #14, #15, #17, #68, #69

68. More than one command line argument, e.g. `scraft_cam.py
    --shop=SHOP1.py --design=DESIGN1.py`; maybe it can work out what
    everything is just by importing the `.py` files.
69. Agreed as a starting assumption (ours = the directories our
    schema names; the rest the user's), may change.
14. Nested tabs dropped: with the tree widget they are a bad idea.
15. Character by character checking, preferably by a regular
    expression, with a light red background while bad.  Bad values
    are NEVER written to the TOML files.
15.1. No [Save] button: revision control is the better way.  A value
    is written to the file system as soon as focus moves elsewhere.
17. No history of our own: users use whatever version control they
    want.

## 2026-11-12: Decisions #13, #19, #64, #68.1

68.1. The shop is TOML, the design Python: that makes them easy to
      tell apart.  Follow-up: when an argument is a directory, a
      directory of Python files with `__init__.py` is clear; for one
      of TOML files, maybe a rule like `ROOT.toml` (a thought, may
      not last).
19. Run with it (directory = branch, `.toml` = one item) until
    something makes us reconsider.
57. The user asked what PySide6 is (explained: Qt's own Python
    binding, the GUI toolkit itself).
64. Agreed: `~/.scraftcam/` holds only what can be rebuilt, and is
    always safe to delete.
13. The first step is a GUI design session: what a panel looks like
    (remember panels can be replicated).  The non-GUI matters settle
    some more first.

## 2026-11-12: GUI design: #71-#73

71. Agreed (panel menu: "New panel like this", "Move to new window",
    pinning).  When a panel is replicated, the tree view opens by
    itself to show where it is.  The tree also lists the user's
    Python design files.
72. Agreed (fields panel: a row per field in schema order, entry
    light red while bad, preferred units in grey, help as tooltip,
    the sketch beside it, a letter puts the cursor in its field).
73. No right click: a selected item gets one or more rows (as
    appropriate) in the top panel, for its actions.  No icons: a
    parenthetical word to the right of the name (e.g. "T01 (tool)").
(#68.2 and #70 not answered yet.)

## 2026-11-12: GUI design: #70, #74-#76

70. The tree, when shown, sticks to the left edge.  SVG (when
    present) on the right; for documentation, the text left of the
    SVG panel.  The catalog part will show a table.  The look gets
    tried out until it "looks right" to the user.
74. A Python file shows only its top level docstring; another button
    sends the file to the user's favorite Python viewer/editor.
75. Agreed (action rows, only those that apply); some items may need
    more than one row.
76. Agreed: [Delete] asks once, says it can be restored from version
    control, removes the file; no `git rm`.
68.2: the user asked for a suggestion.

## 2026-11-12: #13 (order), #77-#81

77. Agreed: `$VISUAL`, then `$EDITOR`, then the system's default
    (`QDesktopServices`).
78. The user: why not keep the GUI's settings in the shop's TOML
    data?  Configuring the GUI is like configuring the machine tools,
    and it puts them under version control.
79. Same solution as #78.
80. Agreed in outline (a kind's directory shows its documentation,
    text left, SVG right, from the source of `Tool_Models.md`);
    details to come.
81. No prototype: Qt is just function calls, and layout is largely
    independent of function.
13. Order of implementation (expected to change as we go): 1. the
    top line; 2. the hierarchical tree view; 3. the shop TOML schema
    and `.toml` file creation; 4. tool documentation and SVG images;
    last, actual machine control.

## 2026-11-12: #78.1, #82, #84, #85

78.1. Agreed: shared GUI settings in `shop.toml`; each person's
      layout in `gui/USER@HOST.toml` in the shop (commit or ignore).
82. A reasonable start (top line: [Tree], [Stop All] while more than
    one machine runs, shop and design names, a message area,
    [+ Panel], [x]; action rows under it).
84. Agreed: in step 3 `examples/shop/` becomes the first shop in the
    new layout, and the demo, `show_demo.py` and the tests move with
    it.
85. Total agreement: offscreen tests per step (`tests/qt_hmi.py` to
    become `tests/qt_app.py`), the user's GUI run for the look, a step
    done only when the user likes it, checkers on everything.  The
    user asked whether testing uses MCP (it does not; see #86).
(#83 not answered yet.  The `.nc` setup comments are already TOML.)

## 2026-11-12: #83, #86-#89

83. Agreed: with no `--shop`, look for `shop.toml` in the current
    directory, then its parents (as `git` does).
86. An MCP port will probably come some day; deferred until needed.
    Meanwhile the command port (one line in, one out) drives the GUI.
87. No huge `.pdf` files in git/hg.  Extracted tables and text go
    under revision control; images are extracted on demand.  Once a
    tool is "purchased", its captured material should be kept under
    revision control (small `.png`/`.jpg` files are fine).
88. Something like a tool's optional `catalog` field could work.
89. Agreed: installer (#54), launchers (#56) and PySide6 in
    `pyproject.toml` (#57) deferred until PyPI; #1's second half
    settled (the GUI starts LinuxCNC).

## 2026-11-12: #87 settled, #90-#92 deferred; where things stand

87. The user's intent all along: images only on demand until a tool
    is purchased, then written once (fixed resolution, never
    rewritten; today's re-save of page 210 rewrote every PNG with
    new bytes, which would be revision control noise).  The user is
    flexible; the catalog side could even be simplified to extracting
    the tables, plus a one page `.pdf` saved for each purchased tool.
    The frustration to fix: a tool is bought, and all its
    documentation is gone.
90-92. Deferred until they come up: new shops from a template, a
    "Show in SolidCraft" button, shop floor screens.

Where things stand: the decisions are done for now (#1-#19 revisited,
#64-#89).  Next: step 1 of #13, the top line (#82).  Before coding,
Claude writes down what step 1 covers for the user to check.  The
order (#13): 1 top line, 2 tree view (shop and design trees: `shop.toml`
root, design `.py` with `main()` or a package with `__main__.py`,
#68.2; names with a parenthetical kind, #73), 3 shop TOML schema
(TOML, converted to JSON Schema, `#:schema` line, #9) and `.toml`
creation (written on focus-out, never a bad value, #15), with
`examples/shop/` moved to the new layout (#84), 4 tool documentation
and SVG (#5, #80), last machine control (the HMI as a panel, #6).
Tests: offscreen plus a command port (#85, #86).

## 2026-11-12: S1 (the top line) expanded; #93-#97

S1 draft: `python3 -m ... [--shop=SHOP] [--design=DESIGN]`; window =
top line, action rows, panel area; top line [Stop All] (more than one
machine running), [Tree], shop and design names, message area,
[+ Panel], [x]; a model with no Qt shared by all windows; closing
refused while a machine runs (#67); `tests/qt_hmi.py` becomes
`tests/qt_app.py`.  Not in S1: tree contents, schema, panel menu
(#71), layout files (#78.1), machine control.

93. `scraftcam/gui/` with `app.py` (model, no Qt) and `window.py`.
    No `__main__.py` (ugly); the user suggested `scraftcam/gui.py` or
    `scraftcam/run.py`.  Open: `gui.py` clashes with `gui/`.
94. Try it ([+ Panel] adds a panel beside the others, [x] closes the
    window) and see how it looks.
95. Agreed: one line, latest message, problems in red; history later.
96. Agreed: a small command port in S1 (`status`, `press BUTTON`,
    `quit`).
97. Mostly agreed: with no shop found the GUI still starts, and also
    offers to create a `shop/` directory and initialize it.

## 2026-11-12: #93, #98-#102

(The user answered #98-#101 as "#94-#97", and the README as "#0".)

93. `scraftcam/run.py`, run as `python3 -m scraftcam.run`; with
    `#!/usr/bin/env python3` and the execute bit (not on Windows).
98. A new shop starts with a quick questionnaire: which machines the
    shop has (CNC mill, CNC lathe, laser cutter, 3D printer, ...).
99. The GUI does not run `git init`/`hg init`, but recommends that a
    version control system be installed, suggesting `git` or `hg`.
100. Agreed: shop name from `shop.toml`'s `name` (else the directory
     name), design name from the file or package, "(none)" if absent.
101. Agreed: `--port=N`, off by default.
102. (New, the user's "#0") Start a `README.md` for the GUI's
     documentation.

## 2026-11-12: #103-#107 agreed

103. `run.py` run as a script puts the directory above `scraftcam/`
     on `sys.path`; absolute imports only.
104. Questionnaire: shop name, units (in/mm), a checkbox per machine
     kind (CNC mill, CNC router, CNC lathe, laser cutter, 3D printer,
     manual mill, manual lathe); written as a `machines` list in
     `shop.toml`; all but the mill "(not supported yet)".
105. (a): the dialog in S1 with a tiny writer for its keys; S3
     replaces the writer.
106. `scraftcam/gui/README.md`, linked from the top `README.md`,
     growing per step.
107. Each start: `shutil.which` for `git`/`hg`, and whether the shop
     is in a repository; if not, one line in the message area.

## 2026-11-12: #108-#112; S1 ready to start

108. Agreed: S1.1 `gui/app.py` (model) and tests; S1.2 `gui/window.py`
     (top line, bands, [+ Panel]), first GUI look by the user; S1.3
     `run.py`, `shop.toml` lookup, `--port`, command port; S1.4
     questionnaire and version control hint; S1.5 `gui/README.md`,
     `tests/qt_hmi.py` -> `tests/qt_app.py`.  Inline, hg after each.
109. Smaller, so SolidCraft's window fits beside it: 720 x 480 to
     start; the user resizes.  (Wayland: the compositor places it.)
110. Claude's call: one JSON line in, one JSON line out, shaped like
     JSON-RPC 2.0 (`id`, `method`, `params` / `result` or `error`),
     so a later MCP server (#86) can wrap it.  A new
     `scraftcam/gui/port.py`; the HMI may move to it later.
111. Claude's call: no env var; the default `./shop/` keys off the
     current directory, and tests and trial runs start in a scratch
     directory.
112. Agreed: done when offscreen tests and checkers pass and the user
     likes two GUI runs (empty directory -> questionnaire; then
     `--shop` on the shop it made).

## 2026-11-12: S1.1, S1.2 done; waiting on the user's first look

* S1.1: `scraftcam/gui/app.py` (`App`, `Message`, `find_shop()`,
  `shop_name()`, `design_name()`, `in_repository()`,
  `version_control_hint()`); `tests/test_gui_app.py`.
* S1.2: `scraftcam/gui/window.py` (`Window`, `run()`,
  `make_application()`, `use_headless()`); a bare `scraftcam/run.py`
  (`--shop`, `--design`, `--headless`; no port yet), executable, works
  as `./scraftcam/run.py` (#103); `tests/qt_app.py` (the GUI's;
  `qt_hmi.py` merges in at S1.5), `tests/test_gui_window.py`.  11
  tests pass; checkers clean.
* Next: S1.3 (command port, JSON-RPC shaped lines, `--port`).

## 2026-11-12: S1.3 done

The user's first look: fine ("didn't see a tree" was the empty
placeholder; it now says "Tree: empty until step 2", and [Tree] gives
it 30% of the width).  `scraftcam/gui/port.py` (no Qt: `reply()`,
`parse()`, `PortError`, JSON-RPC codes); `window.CommandServer`
(`QTcpServer`, 127.0.0.1 only; `status`, `press`, `quit`, which waits
`QUIT_DELAY_MS` so its answer gets out); `window.WINDOWS`;
`run.py --port`.  Checked end to end with `nc`.  13 tests pass.
Next: S1.4 (questionnaire, version control hint).

## 2026-11-12: S1.4 done

`app.py`: `UNITS`, `MACHINE_KINDS` (key, label, supported; only
`cnc_mill` supported), `new_shop_text()` (the tiny writer, #105:
`name`, `units`, `machines`; JSON strings as TOML basic strings),
`create_shop()` (never over an existing `shop.toml`), `App.use_shop()`,
`App.new_shop()` ("Created ..." plus the version control hint).
`window.py`: an action row "No shop yet: [New Shop]" while there is
no shop; `NewShopDialog` (directory, default `./shop`, [Browse...],
name, units, a check box per kind, [Create] grey until named); it
opens by itself at start with no shop (not headless); the port's
`new_shop`.  `tests/qt_app.py` imports `QApplication` only for type
checking (it failed when imported first).  17 tests pass.
Next: S1.5 (`gui/README.md`, `qt_hmi.py` into `qt_app.py`).

## 2026-11-12: S1.5 done; S1 waiting on the user's GUI runs

`scraftcam/gui/README.md` (starting, the window, a new shop, the
command port, the code), linked from the top `README.md`.
`tests/qt_hmi.py` merged into `tests/qt_app.py` (`make_hmi()`); seven
HMI/catalog tests import it.  122 tests (GUI, HMI, catalog) pass.
Found, not caused by S1 (same at HEAD `02cfb98`, in a scratch
worktree): running the HMI and catalog tests together, Python aborts
or segfaults at exit, after "OK" (likely Qt's teardown order).
Raised as #113.

## 2026-11-12: #113 fixed

Cause: the HMIs the tests make are kept alive by their own signal
connections (bound methods, `functools.partial`), so they lived until
exit, and PySide's `destroyQCoreApplication()` then deleted the many
left in no safe order (gdb: `QObject::~QObject()`; glibc
`malloc_consolidate(): unaligned fastbin chunk`).  `tests.test_lcnc_hmi`
alone crashed 2/6 (`TestMainSolidCraft` 8/8).  Fix:
`window.delete_windows()` (close, `deleteLater()`, send the deferred
deletes), registered with `atexit` in `tests/qt_app.py`, which runs
before PySide's clean up.  The GUI/HMI/catalog set: 0/10 crashed
(was 3/3).  The real HMI and GUI exit 0 on quit (one window each).

## 2026-11-12: The user's S1 runs; small fixes

The user ran both (#112).  Fixed: units shown as "Imperial (in)" and
"Metric (mm)" (`UNIT_LABELS`; `shop.toml` keeps `in`/`mm`); kinds
added: manual drill press, manual bandsaw (the CNC router was there);
[Browse...] did nothing (KDE's native dialog from a modal dialog), now
Qt's own (`DontUseNativeDialog`), starting at the nearest existing
directory, checked on the real display; [Create]'s tooltip says why it
is grey.  Raised: #115 several machines of a kind; #116 [Create] grey
(by design until named); #117 Browse (fixed); #118 more kinds.

## 2026-11-12: #114-#118 settled

114. [x] narrow (square), for room later.
115. Agreed: checkboxes now; S3 lets a shop have any number of
     machines of a kind, each named.
116. [Create] beside the Name field (default button, Enter presses
     it), grey with a tooltip until named; [Cancel] alone at the
     bottom.
117. Fixed (Qt's own directory dialog).
118. Focus on computer controlled machines; manual ones only for prep
     work for CNC (mill, lathe, drill press, bandsaw), listed under
     "Manual, for prep work:" (`MANUAL_PREFIX`).

## 2026-11-12: S2 (tree view) planned; #119-#123

S2 parts: S2.1 `gui/tree.py` (model, no Qt; `main()` found by `ast`,
never importing); S2.2 the tree widget; S2.3 selecting shows the item
in the current panel (outlined); S2.4 [Edit] (#77); S2.5 file
watching, port `tree`/`select`, README, tests.  GUI looks after S2.3
and at the end.

119. Agreed: shop items as they are, "NAME (file)"/"(directory)";
     S3 brings the kinds.
120. Agreed, to be tried in practice: design root `--design`; `.py`
     files and packages below, no `__pycache__`/hidden; "(design)" if
     `main()`, else "(python)".
121. One tree, two roots (Shop, Design).
122. Agreed (current panel outlined; TOML text read only; `.py` top
     docstring; [Edit]).  Also: tell the user that `$VISUAL` and
     `$EDITOR` exist when neither is set.
123. Agreed: `QFileSystemWatcher`, no [Refresh].

## 2026-11-12: #124-#128; S2 started

124. Agreed (`$VISUAL` as is; `$EDITOR` in a terminal window; else
     the desktop's default, with a hint once per session).  The hint
     says "environment variables" so users can look them up.
125. Agreed: a bad file stays in the tree, red, "(error)"; the panel
     says "syntax error" at least, with the line when `tomllib` (or
     `ast`) gives it.
126. The design tree stops at 100 items, with a message.
127. Directories first, then files, alphabetical ignoring case.
128. Roots open one level; the rest collapsed; no memory until #78.1.

## 2026-11-12: S2.1-S2.3 done; waiting on the user's look

* S2.1 `gui/tree.py`: `Node`, `shop_tree()`, `design_tree()` (with
  `DesignReader`, `DESIGN_LIMIT` 100), `docstring()`, `toml_problem()`,
  `python_module()` (`ast`, never imports).  `tests/test_gui_tree.py`.
* S2.2 `App` holds `shop_root`, `design_root`, `tree_version`;
  `reload_tree()` ("No design at ..." when missing; a message when
  clipped).
* S2.3 `gui/views.py`: `TreeView` (keeps open items open when filled
  again; `labels()`), `Panel` (outlined when current; TOML unwrapped,
  docstrings and problems wrapped).  The tree now shows from the
  start (30% of the width).  21 GUI tests pass.
* A sample shop and design for looking:
  `/tmp/claude-1000/-home-wayne-public-html-projects-scraftcam/036c09a7-0d48-4676-8dfd-0ffea8825152/scratchpad/demo/`.
* Next: S2.4 [Edit] (#77, #124), S2.5 watching, port `tree`/`select`.

## 2026-11-12: S2.4, S2.5 done; S2 waiting on the user's look

* S2.4: `gui/editor.py` (`editor_command()`: `VISUAL`; `EDITOR` in
  `TERMINALS`; else the desktop's default, `HINT` once a session via
  `App.editor_hinted`); `tree.edit_path()` (Python, a package's
  `__init__.py`, any file with a problem); the [Edit] action row
  (`Window.action_row()`, `show_actions()`, `edit()`).
* S2.5: `views.TreeWatcher` (`QFileSystemWatcher`, 300 ms settle,
  re-watches whenever `tree_version` changes), made in `run()`; port
  `tree` and `select`; `App` resolves the shop's and design's paths
  (a relative `--design` broke `select`).  README sections: the tree
  and panels, [Edit], the port.  25 GUI tests pass; checked end to
  end with `nc` (an outside `router.toml` appeared).
