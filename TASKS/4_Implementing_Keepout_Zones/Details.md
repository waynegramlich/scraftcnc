# 4 Implementing Keepout Zones

Check every move of the G-code that `scraftcnc` generates against the
regions the tool must not enter, first to catch bugs in the code that
writes the G-code, and eventually to stop manual moves in the LinuxCNC
panel from crashing into anything.  (Vise crashes happen all the time
and things break.)

The first two parts are the user's direction.  The rest is Claude's
draft plan, for the user to read and revise.  No code has been written.

## The User's Direction

### 2.5D

We are doing the simplest form of CNC, called 2.5D.  Moves in Z are
always separate from moves in X/Y, so an RS-274 line never has a Z on
the same line as an X and/or Y.  This massively simplifies keep out
zones.

* `SCRoundedPolygon`s need to be expanded (exterior polygons) or
  contracted (interior polygons) by the radius of the current tool.
* Then each linear move and arc move is verified not to enter any of
  the active keep out zones.

### Decisions

* **Only generated code is checked.**  The checker is for the code that
  `scraftcnc` generates, not for G-code in general.
* **Commands are not combined.**  The generated code does not combine
  various commands.  A canned drilling cycle is a macro: an XY move
  first, on its own line, followed by the pecking.  So
  `G83 X.. Y.. Z.. R.. Q..` is replaced by `G0 X.. Y..`, then
  `G83 Z.. R.. Q..`.
* **Ramps** stay, but we have to be careful how we treat them.  Testing
  a ramp over its whole Z range is basically correct, but linear ramps
  are much easier than circular ramps.
* **Helical cycles** are dealt with later.
* **Cutters are vertical cylinders**, reaching up forever for now.
* **Tool holder**: there will eventually be a keep out zone for the
  tool holder.  It is ignored for quite a while.
* **The widest radius**: in general, a tool's widest radius is used,
  and for keep out zones it is used for now.
* **Rapids really only belong at Zsafe.**  Rapids from Zsafe to Ztop
  might be workable, but they are not generated for now; the distance
  from Zsafe to Ztop is usually not that long.  So rapids into material
  are not dealt with at all, since this rule disallows them.
* **Rising rapids are always OK**, but not the other way around.
* **Drills**: a drill may come down in rapid mode, as long as it is out
  of rapid mode by the time it hits Ztop.  This requirement can be
  relaxed as stacked keep out zones are dealt with.  `G83` is exempted,
  since it rapids back into its hole between pecks.
* **Circular ramps** have to be allowed.  How to treat them has no
  answer yet (question 9).
* **Result**: every violation is reported, with its G-code line and
  the zone's name, rather than stopping at the first one.
* **Names**: all classes start with `SC`, to be consistent.  All of the
  classes in this directory are done first; those in `scraftpybind` are
  a separate task.
* **MDI**: a line in the panel that moves Z with X or Y is rejected.

### Stacked Keep Out Zones

The user has more to say about stacked zones before this part is
designed.

* **Active** means for the current `SCSetup`.
* `SCRoundedPolygon` can have nested pockets and islands.  Later on,
  islands will have sub-pockets and sub-islands, recursively.  Each
  island and pocket has a depth.  The same is true for an `SCMount`.
* We create a stacked set of `SCRoundedPolygon`s, each active for a
  particular range of Z.
* The code to figure this out is going to be quite involved.  When it
  is done, the G-code that Claude generates can be checked against the
  keep out zones, to catch bugs.
* Done properly, this can be added to the LinuxCNC panel, to prevent
  manual tool movement from crashing into anything.

## Where the Code Is Today (2026-10-31)

Line numbers are as of this date.

* **Keep-outs**: `Prism` and `Cylinder` (`tools.py:362`, `tools.py:449`)
  in setup coordinates (mm, table top at Z = 0), already grown by a
  margin of 1/8 in or so.  `Setup.keep_out()` (`scsetup.py:707`) gathers
  the tooling's; material and parts have none.  Nothing in
  `solidcraftcnc.py` or `scmachine.py` uses them.
* **Names**: 48 classes in this project do not start with `SC`, 13 of
  them in `tools.py` and 7 in `mount.py`.  `scraftpybind.py`, a link to
  its own project, has 44 more.
* **Depth**: `SCRoundedPolygon` has no depth.  `SCCNC.pocket()`
  (`solidcraftcnc.py:1339`) is given a `bottom` and a flat list of
  `islands`, and does not cut a polygon's own `holes` and `regions`.
* **Moving by a tool radius**:
  * `SCRoundedPolygon.offset()` (`scgeometry.py:541-594`) moves only the
    outline, drops holes and regions, and raises `ValueError` when the
    result collapses or crosses itself.
  * `inset()` on reversed loops, as `beyond()` does
    (`scgeometry.py:1479`), copes with outlines that merge or vanish,
    but has not been tried on an outline with holes.
* **Testing a move**: `meet()` (`scgeometry.py:767`) and
  `SCLoop.contains()` (`scgeometry.py:1306`).
* **A tool's radius**: `SCTool.diameter` is the tip's for a chamfer or
  corner rounding bit (`scmachine.py:49-51`, `shops.py:2759`).  The
  widest diameter is in the tool files, but `SCTool` does not keep it.
* **Lines that combine commands**:
  * `_ramp()` (`solidcraftcnc.py:1666-1676`), including helical arcs
    through `SCCNC.arc(z=...)`.
  * Canned cycles (`solidcraftcnc.py:966-978`).  Only the first hole's
    line names the cycle; later holes are bare `X Y` lines.  These go
    through `add()`, not `_move()`, so `position` is not updated.
* **Rapids that are not at Zsafe**:
  * Down to `z_top + clearance`, before cutting
    (`solidcraftcnc.py:1124`, `1301`, `1638`, and `993` for a hole).
  * Sideways at that height, inside a pocket (`solidcraftcnc.py:1629`).
  * Up from a lower level, inside a pocket (`solidcraftcnc.py:1627`).
  * Up and down during pecks (`solidcraftcnc.py:999`, `1002`).
  * Straight up to Zsafe after a cut (`solidcraftcnc.py:1127`, `1308`,
    `1419`, `1432`, `1636`), and to `tool_change_z` (`735`).
  * A canned cycle does its own, down to its `R` plane, and in and out
    of the hole between pecks.
* **Panel**: `Machine.jog()` (`lcnc_panel.py:385`), `Machine.mdi()`
  (`lcnc_panel.py:358`) and the moves that go to the work origin
  (`lcnc_panel.py:415-417`) are where manual moves leave it.

## Insights

1. **Do not merge zones in order to check them.**  A move is bad if it
   enters any zone, so overlapping polygons can simply be tested one at
   a time.  This matters because the vise's keep-outs overlap where they
   meet, and `SCRoundedPolygon` refuses outlines that cross.  Merging is
   only needed for a tidy picture.
2. **A hole too small for the tool is not an error.**  Contracting an
   interior polygon can make it vanish, which means the tool does not
   fit there.  Likewise, a notch in an exterior polygon can close up as
   it expands.  The code must treat both as normal results.
3. **The tool occupies a range of Z, not a point.**  As a vertical
   cylinder reaching up forever, with its tip at Z, it meets every slab
   at or above the tip, each grown by its radius.  When the holder
   arrives, the tool becomes a small stack of (height range, radius)
   pieces, with no other change to the design.
4. **A linear ramp is tested over its whole Z range.**  A ramp's segment
   runs from one Z to another, so it is tested as a flat move against
   every slab at or above its lowest Z.  This is conservative: it can
   report a move that really clears, but can never pass one that does
   not.
5. **Anything the checker does not understand is reported.**  It must
   never pass silently: a helical arc, an unknown G code, or a move
   with no known tool or position gets an "unchecked" entry.  A clean
   report then means that everything was really checked.  Since only
   generated code is checked, this is a guard against the checker and
   the generator drifting apart, not a G-code interpreter.
6. **The checker reads the finished `SCCNC.commands`.**  It does not sit
   inside `_move()`, so that it is independent of how the path was
   generated.  Once commands are not combined, each canned cycle's XY
   move is an ordinary `G0`, so the checker needs no modal logic for
   holes, and a cycle's line is just a vertical move.
7. **Shared code can hide a shared bug.**  The tool paths and the
   checker both use `scgeometry.py`, so a bug in an offset could fool
   both.  So tests also walk points along each move and measure their
   distance to the zones directly with `distance_to()`, with no offsets.
8. **Depth decides which way a slab reads.**  A pocket with its floor
   at Z is open above Z and solid below it; an island with its top at Z
   is solid below Z and open above it.  So the recursive tree of
   depths turns into a sorted list of Z breaks, with one set of
   polygons between each pair.
9. **The panel's guard is only as good as its numbers.**  It relies on
   the work origin, the tool length and the real position of the vise.
   If the operator touches off wrongly, the check is wrong too.  It is
   not a hard stop, and only guards moves made through this panel.  Say
   so on the screen.  It also must let a tool that is already inside a
   zone move back out.
10. **The rapid rule is itself a check, and an easy one.**  Material is
    not tracked, but the checker can enforce the rule directly: a `G0`
    in X or Y below Zsafe is a violation, and so is a `G0` going down
    below Zsafe, except a drill's that stops above Ztop (and `G83`, which
    is exempted).  A `G0` going up
    is always fine.  That catches rapids into material with no knowledge
    of the material.

## Plan

The steps are in the order they are done; their numbers are kept, so
new steps come out of order.  Each is usable and tested before the next
starts.  Steps 2, 8 and 9 depend on the talk about stacked zones, so
those designs may change.

* **Step 1, agree the design.**  The user explains stacked zones; the
  open questions below are answered.
* **Step 11, rename the classes** in this directory to start with `SC`
  (private ones as `_SCReader`, and the throwaway scripts as well), in
  their own checkpoint, with no other changes.  Older log entries keep
  the old names.
* **Step 12, make the generator follow the rules**:
  * Canned cycles: `G0 X.. Y..` at Zsafe, then the cycle with no X or Y,
    then `G80`, for every hole.  `position` is then kept up to date.
    To confirm in the LinuxCNC simulator: it accepts a cycle with no X
    or Y, drilling where the tool is.  `test_solidcraftcnc.py:612`
    expects the present form and changes with it.
  * A drill's `R` plane stays at `z_top + clearance`, above Ztop.
  * Other descents from Zsafe at the plunge feed, not rapids.
  * No sideways rapids below Zsafe.  Rising rapids stay.
  * `SCTool` gets a field for the widest diameter.
  * Run time goes up; report the demo's before and after.
* **Step 2, the stack** (new module, perhaps `sckeepout.py`):
  * A zone: a polygon, with a name and a range of Z.
  * A stack: the zones sorted into slabs between Z breaks, with a
    lookup for a range of Z.
  * `SCPrism` to a sharp cornered polygon, and `SCCylinder` to a polygon
    (a square whose corner radii are half its side should make a full
    circle; to be tested) or a `SCHole`.
  * `SCSetup.keep_out()` to a stack.
* **Step 3, growing by the tool**: a zone's polygon, with its holes and
  regions, turned into grown loops, which may vanish or merge (insight
  2).  It starts from `inset()`; `offset()` stays as it is for tool
  paths.  The radius is the tool's widest.
* **Step 4, checking one move**: a line or arc, at a Z or a range of Z,
  against the stack.  Bad if it crosses a grown boundary or starts
  inside one.  Vertical moves are tested as points.  A move that only
  touches a boundary counts as clear, within `TOUCH`, since the margins
  are already there.
* **Step 5, checking a program**: walking `SCCNC.commands` (tool
  changes, canned cycles as vertical moves, linear ramps as ranges of
  Z, the rapid rule of insight 10, and helical arcs as question 9
  says), reporting every violation.
* **Step 6, work origin**: the setup JSON says where each part's G54
  origin is, and how the part is turned, so inches from the work origin
  become setup coordinates.  `SCSetup` has nothing for this now.
  * First real test: the tooling plate should fail, since its long
    edges are 1/8 in from the jaws' keep-outs.
  * Also a deliberate crash for each kind of move, a demo run that is
    clean on its own mount, and the brute force tests of insight 7.
* **Step 7, seeing it**: the slabs modeled in SolidCraft (as
  `KeepOut.model()` does for prisms), violations marked in the tool path
  viewer, and a command line report.
* **Step 8, nested depths**: `SCRoundedPolygon` pockets and islands with
  depths, recursively, turned into slabs (insight 8).  This is the
  involved part.  It may also bring depths to `SCCNC.pocket()`, and a
  finer model of a vise than three cuboids.
* **Step 9, `SCMount`**: the same treatment for mounts.
* **Step 10, panel**: `lcnc_panel.py` loads a setup.
  * Opening a generated program runs the check, and reports it before
    Start.
  * Each jog and MDI line, and the moves to the origin, are checked
    before being sent.  A move that would enter a zone is refused, with
    the zone's name; a move leading out of one is allowed.
  * An MDI line that moves Z with X or Y is rejected, and the operator
    is told to split it.  A program not generated by `scraftcnc` reports
    that it is unchecked.
  * The panel runs in the `lcnc` box; the code needs only the standard
    library, so this should be fine, and each check must be quick.

## Later, Not in This Task's First Pass

* The tool holder's keep out zone (insight 3).
* Helical moves, beyond what question 9 settles.
* Rapids from Zsafe to Ztop, if the longer run times come to matter.
* A separate task to rename the classes in `scraftpybind`.

## Questions

Numbers are kept; settled ones stay, marked done.

1. **Done.**  Commands are not combined; only generated code is checked.
2. **Done.**  All classes start with `SC` (scope in question 11).
3. **Done.**  Testing over the Z range is basically correct; linear
   ramps are much easier than circular ones (question 9).
4. **Done.**  Cutters are vertical cylinders.
5. **Open, restated.**  A part in its second setup, turned over, already
   has finished features.  Tooling has keep-outs, but material and parts
   have none, so a tool path bug that cuts into a finished wall or a
   thin island would pass.  Should finished features become keep out
   zones on later setups?  Claude's recommendation: not now; leave it
   until a part with two setups exists.
6. **Done.**  Rapids into material are not dealt with, since rapids only
   belong at Zsafe.
7. **Done.**  Rising rapids are always OK, but not the other way around.
8. **Done.**  A drill must be out of rapid mode by the time it hits
   Ztop (question 13 is what this leaves open).
9. **Open: circular ramps.**  They have to be allowed; the user has no
   answer yet for how to treat them.  `_ramp()` goes around a whole ring,
   and rings with rounded corners have arcs, so most ramped pockets
   contain them.  Until this is settled, the checker reports them as
   "unchecked".  Claude's suggestion, for when it comes up: an arc's
   outline in XY is the same whatever its slope, so test it over its Z
   range just like a linear ramp.
10. **Done.**  The widest radius is used.
11. **Done.**  All classes in this directory first; `scraftpybind` is a
    separate task.
12. **Done.**  Such an MDI line is rejected.
13. **Done.**  `G83` is exempted from the rule that a drill is out of
    rapid mode by Ztop: its rapids back into its hole between pecks are
    allowed.
14. **Done.**  If the user enters bad data, some consistency checks can
    be done, but ultimately there is only so much that can be done.
    `SCSetup` gets consistency checks, such as each item resting on the
    one below.
15. **Done.**  Home is supposed to be up at Zsafe; if it is not, that is
    a bug.  Today it ends with `G0 Z0` (`lcnc_panel.py:415-417`), so it
    is to be fixed in step 10.
