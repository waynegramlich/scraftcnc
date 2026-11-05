# LLM Agent Context Log

## 2026-11-05: First round (#1-#13), and the code homework

Decided (the user): two processes stay (the panel, and the bridge in
LinuxCNC's Python) (#1); the shop file owns the T numbers and we write
LinuxCNC's tool table (#2, already done: `SCPanelMachine.start()`
sends `shops.tool_table_text()`); one jog per click, of a step that
can be changed (#4, already so: `JOG_STEPS`); the operator sets each
axis of the origin by hand to a number (#5); the end user controls
the clutter (#6); the carousel plan is open (#7); time to the next
tool change goes on the panel (#8); the setup tools went to
`T.cmt~5.3` (opened, added to its `Details.md`) (#9); headless parity
always (#10); task tabs (#11).

Steps (#12): S1 architecture (#1), S2 tool table and tool changes
(#2, #3), S3 next tool and time left (#8), S4 toggles (#6), S5 safe
jogging (#4), S6 setup instructions and origin (#5), S7 carousel (#7).

Homework (#13): the processes are the panel (host Python, `tkinter`)
-> `lcnc_bridge.py` (LinuxCNC's `DISPLAY`, in the box, JSON on 5008);
`serve_linuxcnc.py` only starts LinuxCNC and waits.  The panel
hard-codes `SHOP_FILE`, `SHOP_MACHINE`, `MATERIAL` and `ORIGIN`
(`lcnc_hmi.py:105-152`).  The simulator's HAL (`core_sim.hal`, from
LinuxCNC) completes `M6` at once; there is no tool change prompt.  The
G-code rises to `tool_change_z` and writes `T.. M6 G43 H..`.

## 2026-11-05: Second round (#14-#18)

The user: fewer processes only where it makes sense; the three stay
(#14).  We simulate, so the tool change can be done any way we like
(#15).  The `tkinter` program is called the HMI from now on (#16).
Jogging as it stands is workable (#17).  The four tabs (Run, Setup,
Tools, View, with position and messages above them) are a good start
(#18).  `scraftpybind.py` has `visibility(visible=, items=)`
(`browser.visibility`), by body or sketch name; keep-outs are toggled
today by drawing the setup again.

## 2026-11-05: Third round (#16, #19-#22)

Decided: the HMI takes shop, machine, material and origin from the
program's setup comments, the constants only without them (#16).  The
user doubts the `SC` class prefix is needed (`import A as B` solves a
clash) (#19; scope open, #23).  Tool changes: the simple way, a
G-code pause (`M0` with a message), not a HAL handshake (#20).  S8
(tabs, the HMI rename, #16) comes first; S1 closed, three processes
stay (#21).  SolidCraft can make a body translucent:
`appearance.assign(bodies=[...], opacity=0..1)` (`scraftpybind.py:1081`),
used already in `setup_view.py:532-535`, `plot.py:678` (#22).

## 2026-11-05: Fourth round (#23-#27)

Decided: drop the `SC` prefix (one tree, our sandbox); only "when" is
open (#23).  Tool change pause as #24 proposed (`MSG` + `M0`); other
controllers just do `Tnnn`.  S8 splits into S8, S9, S10 (the user's
#26 answer, taken as #25).  Order of S2 vs S3: Claude's call (#27): S2
right after S10.  Dropping `SC`: 135 classes; `Arc` and `Tool` already
exist unprefixed; `PyBind`, `Sample`, `View` are each defined in two
modules; generic results: `Item`, `Client`, `Server`, `Handler`,
`Status`.

## 2026-11-05: Fifth round (#26-#31): the steps, renumbered

The user wants the steps numbered in the order they are done, and a
checkpoint after each.  Old S1 (architecture) is closed: three
processes stay.

* S1: Baseline: the LinuxCNC end-to-end suite, and a code trace
  (coverage) run (#26).
* S2: Drop the `SC` prefix everywhere, generator included; "panel"
  becomes "HMI" in the text (#19, #23, #28, #31).
* S3: The HMI's four tabs (Run, Setup, Tools, View), and a headless
  stand-in for them (#11, #18).
* S4: Shop, machine, material and origin from the setup comments
  (#16).
* S5: Tool change pause: `MSG` + `M0` in the controller's
  `tool_change` template, with `{description}` (#20, #24, #29).
* S6: Next tool and time left to it, on the Run tab (#8).
* S7: Set the origin axis by axis, to a number (#5).
* S8: Keep-out check before each jog (#4, #17).
* S9: Toggles, by `visibility` and `opacity` (#6, #22).
* S10: Tool changer carousel (#7).

## 2026-11-05: How the steps are run (#32, #33)

No sub-tasks: S1-S10 all stay in `T.hs~5.1.5`.  "Trace run" means
Python's own `python3 -m trace` (standard library), not `coverage`.
A trace run is the S1 baseline, and another one comes after S10, to
compare.  One background agent does the steps, one at a time (reused
with SendMessage), so the user can talk to Claude meanwhile; an
`hg` checkpoint after each step, then the user commits to `git`.

## 2026-11-05: S1 baseline

Not done; stopped at the 8 minute cap.  The whole suite under the
standard library's `trace` (`python3 -m trace --count --missing
--summary --coverdir=TASKS/5.1.5_HMI_Subpackage/trace_S1
--ignore-dir=<stdlib, dist-packages, ~/.local/lib, tests> --module
unittest discover -s tests -t .`) ran only 48 of about 596 tests
(no failures yet) in 5.5 minutes, so it was stopped; no `.cover`
files were written (`trace` writes them only at the end).  At that
rate the whole suite would take about an hour.  Proposed split: one
`trace` run per test module (or a few modules per run), each with its
own `--file` counts file, merged by passing the same `--file` to each
run, then one `--report` at the end.  The LinuxCNC end-to-end suite
was not run (no time left).

## 2026-11-05: S1 closed, skipped

The whole traced suite would take about an hour, so the user skipped
the baseline trace (and so the final trace after S10 has nothing to
compare with).  The LinuxCNC end-to-end suite was not run either.
Next: S2, drop the `SC` prefix.

## 2026-11-05: End-to-end baseline

The trace baseline was dropped (the user).  `SCRAFTCNC_LINUXCNC=1
python3 -m unittest -v tests.test_lcnc_end_to_end`: all 10 tests pass
(134 s wall time), the first run since the one-tree reorganization.

## 2026-11-05: S2

The `SC` class prefix is gone from `scraftcnc/`, `tests/`, `show_demo.py`
and the docs, renamed by a whole-word script from
`S2_rename_map.txt` (149 names; 33 non-mechanical, marked `(*)`, e.g.
`SCPanel` -> `HMI`, `SCArc` -> `ArcSegment`, `SCTool` -> `ToolEntry`,
`SCNamespace` -> `CommandNamespace`, `SCSegment` -> `XYSegment`).
`scraftpybind_generate.py` writes the new names; the regenerated
`scraftpybind.py` matches the scripted renaming exactly.  "panel" is
"HMI" in prose; the `--panel-port` flag and the `"panel"` process keys
in `show_demo.py` are unchanged.  ruff and mypy are clean; pylint shows
only findings that were there before (the same 20 file and message
counts as on the pre-S2 tree, hg rev 540).  Unit suite: 603 tests, 13
skipped, 193 s, with one failure, `TestFiles.test_document_is_current`:
the top level `Tool_Models.md` (written from the code) still had the
`SC` names, and was rewritten from `tool_models.document()`;
`test_tool_models` then passes.

## 2026-11-05: S3

The HMI has tabs (`ttk.Notebook`; `TABS` = Run, Setup, Tools, View).
The position, message and progress lines sit above them, and Open and
Quit below.  The Tools popup is now the Tools tab, filled each time
the tab is shown, and the Tools button is gone.  The headless HMI has
a `Notebook` stand-in.  On the command port, `tab NAME` shows a tab,
`show` has a new `tab` key, and `press` still finds a button on any
tab.  The HMI has no protocol number of its own, and the changes only
add to it.  New tests: `test_tabs` (walks all four tabs) and
`test_labels_unique`; `test_tools_window` became `test_tools_tab`.  A
real (withdrawn) Tk window switched through all four tabs fine.
Checkers are clean.  Unit suite: 605 tests OK, 13 skipped, 199 s.

## 2026-11-05: S4 (partly done; the format lacks shop, machine, origin)

The `(SCC: ...)` comments carry only one of the four: the material
(the part's `material`, "6061 aluminum", and the stock's short name
`aluminum_6061`).  They have no shop, no machine (only a table,
`mikini_1610l`), and no G54 origin in machine coordinates: the setup
frame is the work frame (`named_origins()`), so the table's place in
the machine is not known.  Done for the material:
`setup_material()` takes the part's material, then the stock's, when
the shop knows the name, else `MATERIAL`.  Each open sends the tool
table again (`HMIMachine.write_tool_table()`, only while LinuxCNC is
idle, otherwise a message).  The Tools tab's chooser starts on that
material, and the position line ends with "Shop mill, <material>".
Tests: `test_material_from_setup` and `test_material_fallback`.
Checkers clean; unit suite 607 OK, 13 skipped, 229 s.  The options for
the missing three go to the user (format not extended).
