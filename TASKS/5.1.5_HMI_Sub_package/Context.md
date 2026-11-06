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

## 2026-11-05: S4

The user chose option 2, and put the two material names (part
"6061 aluminum", stock `aluminum_6061`) off until `T.sm2~5.5`.
* Setup comments have a header after `version`: `shop` and `machine`
  (names), written from `Assembly.shop`/`.machine` (new fields;
  `demo_assembly()` fills them from its shop).  Older files without
  the header still read (both `""`).
* A shop's `machine_table` may give `x`, `y`, `z`: where the table's
  reference point sits in machine coordinates.  The example mill has
  6, 4.5, -13.64 in, which gives today's `ORIGIN` for the demo.
  `Shops.md` was regenerated.
* HMI: `setup_origin()` = table place in the machine (shop) minus the
  setup's bottom item (a `table`) location.  Each open of such a
  program sets G54 (`HMIMachine.set_work_origin()`, only while idle).
  Without one, G54 is left as it is (`ORIGIN` from start-up).
  `setup_material()` picks the material.  The tool table is sent again
  on each open.  The position line ends with "<machine>, <material>".
* A program for another machine (or shop): warn, not refuse.  The
  message line says "Warning: the program is for X, not Shop mill;
  origin not set".  The program still opens, LinuxCNC's own machine's
  tool table is used, and G54 is not touched.
* Tests: header round trip, no header, demo origin equals `ORIGIN`
  (and in the HMI log), no origin without a table place, machine
  mismatch warning.  Checkers clean; unit suite 612 OK, 13 skipped,
  200 s.

## 2026-11-05: S4 follow-up decisions (#38, #39)

#38: a program for another shop or machine is refused (not opened;
the program open before stays).  #39: no run without an origin set
for this program: each open clears an "origin set" mark; it is set on
open from the setup's worked-out origin, or by the operator (Set
Origin; by hand per axis in S7).  Start is greyed out until then
("Set the origin first").  `ORIGIN` is no longer set at start-up.
Jog and MDI still work without an origin.

S4 follow-up (#38, #39).  A program whose setup names another shop or
machine is refused: `HMI.open()` raises `ValueError` before anything
is sent (the port answers `error: Not opened: ...`, the message line
says the same, and the program open before stays).  The origin gate:
each open clears `origin_set`, and `HMI.mark_origin_set()` is the one
place it is set (on open from `setup_origin()`, or by Set Origin,
named or plain; S7 can call it too).  Until then Start is greyed out
and the message line says "Set the origin first"; Set Origin stays
pressable even at the origin; jogs, Home and MDI still work.  `show`
has `origin_set`.  `ORIGIN` is gone from the HMI (start-up sets no
G54).  The end-to-end suite (not run) sets G54 to (4, 3, -6) in its
`setUpClass()` through the HMI, and `open_program()` presses Set
Origin for programs without a setup origin.  Tests: `test_origin_gate`,
`test_other_machine` (refused, previous program kept), demo Start
enabled right after open.  Checkers clean; unit suite 613 OK, 13
skipped, 209 s.
End-to-end (`SCRAFTCNC_LINUXCNC=1`): all 10 tests pass with the origin gate, 138 s.

## 2026-11-05: S5

The controller's `tool_change` may hold several lines, each words or
a whole-line comment, filled in with `number` and `description` (the
tool's name): `Machine.change_lines()` (was `change_words()`),
checked in `Machine.__post_init__()`.  The example LinuxCNC template
is `(MSG, Insert T{number:02d}: {description})`, `M0`, then
`T{number:02d} M6 G43 H{number:02d}`; `CNC.change_tool()` already
rises to `tool_change_z` and stops the spindle (`M5`) first.
`Shops.md` regenerated.  The HMI's `tool_changes()` starts each change
at its `MSG` line, so -Tool/+Tool and a run from there prompt first.
A pause the operator did not ask for (`operator_paused`) is the
program's: the `MSG` text is on the message line, and a person
presses Start (Resume); headless, the HMI resumes by itself.
`sim_linuxcnc.Simulator.follow()` resumes too (no one to press).
`demo_linuxcnc.py` runs its own program, unchanged.  `keepout.py`,
`plot.py` and the time estimate read the new lines as they are.  The
end-to-end demo test now allows the `Insert T..` messages.  Tests:
`TestToolChangePause` (demo pauses at each change, change starts,
headless goes on, Pause's pause waits), `test_machine`, `test_shops`.
Checkers clean; unit suite 616 OK, 13 skipped, 200 s.  End-to-end
not run yet (time cap).
End-to-end: the first run failed two tests on messages only (a `MSG`
text comes with a leading space, and the HMI keeps every message, so
later tests saw the demo's prompts); the HMI now strips messages, and
the suite's `messages()` leaves the `Insert T..` prompts out.  Re-run:
all 10 pass, 139 s, the real `M0` pauses gone on from by the headless
HMI.

## 2026-11-05: S6

The Run tab's `next_tool` label shows "Next: T05 <description> in
M:SS", "Now: T05 <description>, cut M:SS" (from a change's `MSG` line
to its `M6`, as when paused at its prompt), or "Last tool: M:SS to the
end".  `line_minutes()` times each line once per program
(`HMI.time_program()`, kept as running sums, so a poll only
subtracts): it reuses `plot.read_gcode()` (line by line, an odd line
costs nothing) and `plot.command_moves()`; rapids at the INI's
`[TRAJ] MAX_LINEAR_VELOCITY` (or `MAX_VELOCITY`) x 60
(`HMIMachine.rapid_speed()`, `RAPID_SPEED` = 60 in/min without
LinuxCNC), feeds at `F`, arcs by length, drill cycles without pecks;
acceleration ignored.  Time left is divided by the feed override.
`change_spans()` gives each change's first and `M6` lines
(`tool_changes()` uses it).  `show` has `next_tool`.  Demo: lines add
up to 11.49 min, the demo's own estimate 11.83 min (pecks).  Tests in
the new `tests/test_hmi_tool_changes.py` (S5's moved there too, as
`test_lcnc_hmi.py` passed 1000 lines).  Checkers clean; unit suite 621
OK, 13 skipped, 196 s.  End-to-end not run (time cap).
End-to-end (`SCRAFTCNC_LINUXCNC=1`): all 10 pass with S6, 141 s.

## 2026-11-05: S7

The Setup tab has, for X, Y and Z, a number entry and a Set X / Set
Y / Set Z button (`AXES`, `on_set_axis()`): the current position on
that axis is made to read the number (`G20`/`G21`, then
`G10 L20 P1 X<n>`), after a question with No as the default.  An
entry is colored like the MDI line, and its button is greyed out
unless it holds a number and nothing runs (`check_axes()`, also from
`set_running()`).  `axes_set` counts the axes set since the program
was opened; all three call `mark_origin_set()`, which is still the
one place the mark is set (it also fills or clears `axes_set`, so
Set Origin counts as all three and a new open clears them).  Until
then the message line says "Origin still to set: Y Z".  Command
port: `origin AXIS NUMBER` types into an entry; `show` has `axes_set`
and `axis_entries`.  Tests: new `tests/test_hmi_origin_axes.py` (one
axis, bad number, No sends nothing, all three enable Start, a new
open clears, greyed out while running); `test_labels_unique` still
passes.  Checkers clean; unit suite 626 OK, 13 skipped, 200 s;
end-to-end all 10 pass, 139 s.

## 2026-11-05: S8

Each jog is checked before it is sent (`HMI.on_jog()`, `jog_hit()`):
the straight move from the work position to position + step, against
the setup's keep-outs (`keepout.assembly_zones()`, built once per open
in `use_setup()`, work inches), with the tool as `keepout.py` checks
program moves: a vertical cylinder of the spindle tool's widest radius
(`tool_radii`, from the shop's machine, once per open; 0 for no tool)
reaching up forever, at the move's lowest tip height.  A hit is
refused, not shortened: nothing is sent, the message line (and the
port's `press` answer, `error: ...`) says "Jog refused: it would
enter <name>; choose a smaller step and try again".  Choice for a tool
already inside a keep-out: a straight +Z jog is always allowed (the
cylinder only rises); any other jog is refused (raise Z first).
Without a setup, or before the origin mark (#39), jogs are sent
unchecked, and the message line says so once ("Jogs not checked: no
setup" / "... origin not set").  Tests: new
`tests/test_hmi_jog_keepouts.py`.  Checkers clean; unit suite 630 OK,
13 skipped, 207 s; end-to-end all 10 pass, 137 s.

## 2026-11-05: After S8 (#41, #42)

#41: agreed, inside a keep-out only +Z jogs.  #42: checking typed MDI
moves against the keep-outs becomes a new step, S11, after S10.

## 2026-11-05: S9

The View tab has check buttons (`TOGGLES`): Keep-outs (off at first)
and Stock outline (on).  They change only visibility:
`SetupView.hidden` (kinds of `HIDEABLE`, the first word of a display
key) is applied after every `show()` by `apply_hidden()`, one
`browser.visibility(visible=, items=[...])` per kind, by sketch name
(`keep_out_N`, `stock_N`).  The keep-outs are now always drawn
(`SetupDrawer` sets `view.keep_outs = True`), hidden unless toggled
on, so the old Keep-outs redraw is gone; a toggle hands the same
setup to the drawer, which changes nothing but the visibility, and a
later drawing (Next Step, a new open) keeps the choices.  `press
LABEL` presses a check button (headless `Checkbutton`, `BooleanVar`);
`show` has `toggles`.  Left out: flute lines (a sketch per tool, `ModeledTool.sketch`, drawn
by `sim_solidcraft.py`; the user's decision).  (Corrected: an earlier
note here said the holder was part of the tool's body; it is not, see
below.)  Tests: `test_hidden` (`test_setup_view.py`, with a `browser` namespace
in its fake session), `test_keep_outs` (HMI).  Checkers clean; unit
suite 631 OK, 13 skipped, 203 s.  `./show_demo.py --headless` not run
(time cap).
Checked in a real headless SolidCraft (`./show_demo.py --headless`,
109 s, closed cleanly), probing the HMI port and SolidCraft's
`document.inspect` (sketches have `visible`): the five `keep_out_N`
sketches start hidden and `stock_3` shown; `press Keep-outs` shows
them, a second press hides them; `press Stock outline` hides the
stock; no SolidCraft errors.  Nothing needed fixing.

Two more View toggles (both shown at first): Origin, SolidCraft's own
origin by `browser.visibility(visible=, folder="origin")` (the setup is
drawn in the work frame, so it sits at the program's zero), sent only
on a change; Holders, the holder bands' bodies (`model_holder()` makes
each band a body `Holder <unique_id> band <n>`), found by name in
`document.inspect()` (`setup_view.HOLDER_BAND`) and hidden again on
every `show()` while hidden, since `sim_solidcraft.py` draws a tool
when it is changed to; the HMI's `follow_tool()` hands the setup to
the drawer again on each tool change while holders are hidden.  Tests
(run by name only, by the user's wish): `test_origin_and_holders`,
`test_hidden`, `test_keep_outs`, `test_labels_unique`, `test_tabs`, all
pass; checkers clean.  Not run in SolidCraft.

## 2026-11-05: Carousel decisions (#45-#48)

The machine definition says whether there is a carousel: number of
slots (none or 0 = manual), the hub's location and the spoke length.
Shown in SolidCraft as N spoke lines with each slot's tool at its
spoke's end; a change rotates the spokes and moves the tools, no
animation.  A tool is loaded/unloaded at the +X spoke.  More tools
than slots: the message names both tools by unique id and holder
colors, e.g. "Swap tool 23 (red/orange) with tool 43 (yellow/orange)".
Slots (Claude's choice, #47): prescan the program, fill the slots in
first-use order; when a tool must come in, swap out the one whose next
use is furthest away (or never).  Split: S10 = machine definition,
the plan and the messages; S11 = the carousel drawn in SolidCraft;
S12 = MDI move check (was S11, #42).

## 2026-11-05: S10

A machine may have a `carousel` (`shops.py` kind `carousel`: `slots`,
hub `x`/`y`/`z`, `spoke_length`; `Shops.md` regenerated), kept in
`Machine.carousel_slots`, `carousel_hub`, `spoke_length`, with
`id_digits` (the shop's longest `unique_id`) and `ToolEntry.unique_id`.
The example mill has 4 slots.  New `scraftcnc/carousel.py`: `plan()`
fills the slots in first-use order, then swaps out the tool next used
furthest away (never first; ties to the lowest slot);
`gcode_sequence()` prescans G-code text; `colors()`, `tool_text()`,
`swap_message()` ("Swap tool 5 (black/green) with tool 8
(black/gray)"); `plan_text()` for the HMI.  `CNC` keeps `changes`; on
a carousel machine `change_tool()` leaves out the template's prompt
lines, and `finish()` puts `(MSG, Swap ...)` + `M0` before each change
that needs a swap (colors in brackets, as a comment can not hold
parentheses; checked by `comment()`).  Manual machines keep S5's
prompt at every change.  The demo (tools 4, 8, 1, 5, 6, 1) now has one
swap, before T06.  The HMI's Tools tab lists the load and the swaps.
The end-to-end suite's `messages()` also leaves out `Swap tool`
prompts.  Tests: new `tests/test_carousel.py`, `test_demo_pauses`
changed.  Checkers clean; unit suite 640 OK, 13 skipped, 194 s;
end-to-end all 10 pass, 137 s.

## 2026-11-05: S11 (done by Claude directly; no sub-agents)

The carousel is drawn in SolidCraft by `sim_solidcraft.CarouselView`:
the spokes are a 3D sketch of lines from the hub, one sketch per slot
at +X (drawn when first needed, only one shown), and each slot's tool
stands on its tip at its spoke's end.  A change turns the new tool's
slot to +X; a swap hides the tool taken out.  The hub is in machine
coordinates; samples now carry the work origin (`Sample.origin`,
G5x + G92, from `Simulator.work_origin()`), and a new origin places
everything again.  `carousel.spoke_ends()` does the geometry.
`display()` builds the machine with `shops.cnc_machine()` (new
`--material`, default 6061 aluminum) and plans from the program's
text.  Tests: `tests/test_sim_carousel.py` (7).  Unit suite 647 OK,
13 skipped, 238 s.  `./show_demo.py --headless`: four spoke sketches
(`Carousel 1`-`4`, 4 wires each) at work (-7, 1.5, 4) in = hub
(-3, 4.5, -2) less G54 (4, 3, -6); no errors, 114 s.  Known: a tool
shown in the carousel shows its holder bands even while the Holders
toggle hides holders, until the HMI applies the toggle again.

## 2026-11-05: S12 (done by Claude directly)

Typed MDI lines are checked against the keep-outs before they run
(`HMI.mdi_refusal()`, called by `on_execute()`): `mdi_segments()`
reads the line with the viewer's reader (`plot.read_gcode()`) after a
move to the tip's place, in `G90`, and each piece (arcs in short
pieces) goes through `jog_hit()`.  A hit is refused ("MDI refused: it
would enter ..."), as is any `G91` move while keep-outs are checked.
Units follow LinuxCNC's mode (`HMIMachine.modes()`, from `gcodes`)
unless the line has `G20`/`G21`.  Without a setup or origin, lines run
unchecked, said once.  Refusals reach the port through `jog_refusal`.
Tests: `tests/test_hmi_mdi_keepouts.py` (6).  Unit suite 653 OK, 13
skipped, 228 s; end-to-end 10 OK, 138 s.  Open: #49 (holders of tools
in the carousel ignore the Holders toggle; the follower process does
not know the HMI's toggles).  All steps S1-S12 are done.

## 2026-11-05: S13 (#49; done by Claude directly)

#49 was moot: the simulated tools had no holders at all (only the
cutter gallery, `model_shop_tools()`, drew them), so the S9 Holders
toggle found nothing in `show_demo`.  Now `cutter_models.add_holder()`
builds a tool's bands and moves them into the tool's component
(`component.move_bodies`, component id from `occurrence_ids()`), and
`sim_solidcraft.ToolModel` uses it; a tool is shown or hidden whole
(`browser.visibility(paths=[[occurrence id]])`, plus body and flutes),
so only the HMI touches the bands.  A probe showed a band hidden by
the toggle stays hidden through tool changes, and unused tools hide
whole.  Unit suite 655 OK, 13 skipped, 203 s; `./show_demo.py
--headless` fine (105 s): the carousel tools' bands sit at the spoke
ends (63.5 mm from the hub).  To check in a GUI run (#50): a body
named `Holder band` at the work origin, and empty `Holder band
profile` sketches, appear (from building the bands' cache entries?).

## 2026-11-05: S14, and two holder bands (the user, #0, #51, #52)

The user saw `show_demo.py` and liked it.  Holder bands: at least two
(`cutter_models.MIN_BANDS`), set by the whole shop's highest
`unique_id` (`Machine.id_digits`, passed to the simulator's
`ToolRack`; it used to count only the loaded tools, giving one band).
S14: keep-outs are solid boxes (`solid.box`), red `#ff0000` at
opacity 0.15 (`setup_view.KEEP_OUT_COLOR`/`_OPACITY`), named
`keep_out_<item>_<n>`, in place of wire sketches (SolidCraft has no
line colors); the toggle works as before.  Unit suite 655 OK, 13
skipped, 198 s; `./show_demo.py --headless --keep-outs`: every holder
has two bands, the 7 keep-out boxes match the old sketches' extents,
no errors, 104 s.  `T.hs~5.1.5` stays open until the user has seen it.

## 2026-11-05: After the user's GUI look (two items)

1) Carousel spokes end at the holder's narrow (tool) end (the user
corrected "base"): tools hang there
(`cutter_models.holder_tool_end_height()` = overall length x (1 -
HOLDER_GRIP); `ToolModel.base`).  2) The user drove a
bit through the tooling (grid) plate.  Not reproduced: in a dry-run
HMI with the demo open, zones (7) and the origin mark are set, and a
1 in -Z jog is refused ("would enter grid plate"); `jog_hit()` refuses
moves into it; the grid plate's red box covers its body (top -0.375 in
vs body top -0.5 in).  Asked the user how (jog step, MDI, or a run)
and what the message line said.

The drive-through: the user typed `Z-4` (no move word).  The viewer's
reader gives no move for a line with axis words but no motion word
(modal motion), so `mdi_segments()` found nothing to check.  Fixed: such
a line is read as a straight `G1`; a line with axis words that still
reads as no move is refused (unless it is `G10`, `G92`, `G43`, `G5x`);
`G28`, `G30` and `G53` (machine-coordinate moves) are refused while
keep-outs are checked.  Tests added (8 in `test_hmi_mdi_keepouts.py`).

## 2026-11-05: Where things stand (before the user's reboot)

All committed to git by the user.  Steps S1-S14 are done: S1 dropped
(no trace baseline), S2 no `SC` prefix, S3 HMI tabs, S4 shop/machine/
origin from setup comments (refuse other machines; no Start without an
origin), S5 tool change pause, S6 next tool and time left, S7 per-axis
origin, S8 jog keep-out check, S9 View toggles (keep-outs, stock,
origin, holders), S10 carousel plan, S11 carousel drawn, S12 MDI
keep-out check (now also axis-only lines; G28/G30/G53 refused), S13
holders on simulated tools, S14 red translucent keep-out boxes; holders
have at least two bands; carousel tools hang by the holder's narrow
end.  Last unit suite: 657 OK; end-to-end last run at S12 (10 OK).

Open:
1. Keep `T.hs~5.1.5` open until the user has seen it in a GUI run of
   `./show_demo.py`; then write `Summary.md` and close it with `aic`.
2. #50: a body named `Holder band` at the work origin, and empty
   `Holder band profile` sketches, seen once in a headless run
   (from building the bands' cache entries?); check in a GUI run.
3. S2 leftovers, unanswered: rename `--panel-port` (and the `panel`
   names in `show_demo.py`) to HMI; the old `SC` names in
   `index_conversion_issues.md` and `shars_catalog.md`.
4. The carousel tools now hang lower (by the holder's narrow end); if
   their tips sit too low, raise the carousel's `z` in
   `examples/shop/shop_mill.toml`.
5. The aic directory name `5.1.5_HMI_Subpackage` does not match its
   title; `aic T.hs rename to HMI Sub-package` wants a git commit first.

Working method: the user asked for no sub-agents for now; Claude does
the steps directly.  `.claude/agents/step-worker.md` (Sonnet) exists
for when agents are used again.

## 2026-11-05: Closed

The user checked the GUI run (fine), the stray holder band bodies
(#50, fine) and the carousel heights (fine).  `--panel-port` became
`--port` in `show_demo.py`, and its `panel` names (and the
end-to-end suite's) became `hmi`.  No `SC` names were left in
`index_conversion_issues.md` (the matches were words like
"Scraper"); `shars_catalog.md` is left alone (written by another
tool).  The directory was renamed with `aic`.
