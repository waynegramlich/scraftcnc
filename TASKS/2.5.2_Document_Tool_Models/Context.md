# LLM Agent Context Log

## 2026-11-02: The plan, as the user answered it

* Aim: an AI can easily generate these models; `Tool_Models.md` is how it learns to.  The user is shooting for 100 % generated from the code.
* The list will grow; the Shars catalog is huge and will not all be covered.
* SVG wherever possible, no raster images.  3D images are skipped until SolidCraft can capture them.
* `Tool_Models.md` at the top level, with a local table of contents.  The end mill goes first, end to end, for the user to judge.

## 2026-11-02: The user's second round of answers

* One command takes one JSON description (`./sctoolmodel.py 8080 '{"kind": "end_mill", ...}'`).  `Tool_Models.md` is generated, with a test keeping it in step; every example is tested.
* We generate the models ourselves for now; eventually the documentation must be enough for a user to write their own.
* Our own letters, the same meaning on every model; not Shars's.  Tooling gets generated as well.
* The table is only Letter (A-Z), Units and Description, with no values: the user reads the catalog for the numbers or makes them up.
* No SVG library: our own small writer, standard library only.

## 2026-11-02: The end mill's page is done, for the user to judge

`./tool_models.py` writes `Tool_Models.md` and `docs/tool_models/end_mill.svg` from `SCModelPage`s (`PAGES`); letters are `SCField.letter`, outlines `profile()`.  `./sctoolmodel.py PORT 'JSON'` and `model_description()` use `shops.check_tool()`, which gives stand-ins for `name`, `unique_id` and `material`.  Letters so far: C, D, L, S.

* Firefox here is a snap: to render an SVG, use `--headless --no-remote --profile` in a temporary directory under the home directory.
* A bull nose is modeled square; `corner_radius` is ignored, so it is left off the page.
* Next, after the user's verdict: the other four tool kinds, then tooling, which the user wants generated as well.

## 2026-11-02: Second iteration

The user: the SVG looks great (Emacs shows it too); shown at half size (`SHOWN`).  The Python Interface section is generated (`INTERFACE`): signatures by `ast` from the source, the rest from docstrings, with exceptions.  The Units column says `Length`; units are explained once, up front.  The user prefers to be shown things and suggest improvements, not asked about them.

## 2026-11-02: Drills

The user approved the end mill's page ("fantastic").  Drills have a page; `shank_length` is new (`K`, from the top; without it a `shank` starts where the flutes stop); `point_angle` is `P`, marked by `SCAngle`.  Left: chamfer mill, corner rounding mill, double angle cutter, then tooling.  Bull nose still models square.

## 2026-11-02: All five kinds of cutter have pages

The user: there are many more tools, but cover only the ones currently modeled.  Letters: A angle, C cut, D diameter, K shank length, L length, M neck length, N neck diameter, P point angle, R radius, S shank, T tip, W width.  Marks: `SCDimension`, `SCAngle`, `SCRadius`.  Left: tooling (table, vise, parallel, plate, countersink, holder), whose fields have no `SCField`.

Found, not fixed: bull nose models square; double angle `profile()` uses `tan(angle/2)` where a rim angle would be `1/tan`, right only at 90 degrees; `neck_length` is measured from the cutter's top in `profile()`, but the schema says to the cutter (L3).

## 2026-11-02: Every cutter and countersink has a page; the user is wrapping up

The user: stop when the existing tools are done; many more tools later, not now.  Never read catalog pages (tokens).

* Done: `coating` renamed `finish`; `material` required even for a model; bull nose (`B`) and the double angle's rim angle fixed; `neck_length` is L3, the neck alone, per the drawing on Shars page 112 (its schema text was wrong, the model right).
* New kinds `single_countersink` and `double_countersink` (letters `E`, `G`; titles say "End"): not in `CNC_KINDS`, so not in a `tool_table` yet; `loaded_tools()` says so.  `SCDoubleEndCountersink` and its 44 order numbers stay in `tools.py`.
* Not documented: tooling (table, vise, parallel, plate), holders.  `T.ctfs~5.1` gives them kinds; add their pages then.

## 2026-11-02: The machine vise's page

The user renamed the vise's parts: `SCMachineVise` with base, body, bed (rails and end blocks), fixed and movable jaws, jaw plates, lead screw, hex; the slider is left alone.  Setup JSON kind `machine_vise`.  `SCViseBlock`, `SCViseNotches`, `vise_mount()` and the `VISE_*` constants keep their names (a drill press vise is to come).

* The user's views: top, back (the hex end) and side.  `tool_models.py`'s `SCView`/`SCShape` draw them from `KURT_D688` at `max_opening`, hidden edges dashed; files `docs/tool_models/machine_vise_{top,back,side}.svg`.
* Sizes are numbered 1-41 (not letters: too many, and letters keep one meaning across cutters); descriptions joined from the docstrings (`vise_sizes()`).  The vise has no tools file kind yet, so the page shows Python and the setup JSON entry.
* The user: do not run the test suite after a rename.  Two tests added in `test_tool_models.py`, not run.
* `SCJawPlate` (the user asked for a "ViceJaw"; named for the parts already called jaw plates): thickness, width, height, two counterbored holes, `screw` label; `KURT_JAW_PLATE` (20 mm counterbores from the user's notes, 17/32 in deep an estimate).  Its own section, `Jaw Plate`, with top and face views; the vise page no longer dimensions the plate.
* The user: the Kurt style vise is "good enough" (2026-11-02).  A drill press vise is to come.
* Whole suite, 2026-11-02, after the vise and jaw plate work: 438 tests, 2 failures from the renames (cache file `Kurt_D688_movable`; plate center of mass moved about 0.1 mm by the counterbores), both fixed and rerun; `test_plate_places` checks X to 0.01 mm, as SolidCraft's round faces put it 0.0008 mm off.
* Next, when the user picks it up: parallels, tooling plate, a drill press vise; then tables and holders.

## 2026-11-02: Parallels

The user: parallels mostly have two holes, to lighten them and make them easier to handle; spacing and diameter optional.  `SCParallel` has `hole_spacing` and `hole_diameter` (0 for none, both or neither), `volume()`, holes cut along X halfway up.  The set is the standard imperial heights, 1/2 to 1-5/8 in (was to 2 in); each with holes 3 in apart, half its height across (Claude's estimate).  `test_mount`'s no-grip test now builds its own 1-7/8 in pair.  Page `Parallel` (side and end views) in `Tool_Models.md`.  Shown on screen: the vise with a 3/4 in pair against its jaw plates.  Tests not run.

## 2026-11-02: Grid plate

The user renamed the tooling plate a grid plate: `SCGridPlate`, `GRID_PLATE`, setup kind `grid_plate`, `examples/setup/grid_plate.json` (git mv).  Fields `height` (was `thickness`), `pitch` (X and Y, was `hole_spacing`), `edge`, `hole_diameter`, optional `corner_radius`, `chamfer_depth` (45 degrees, grid holes only), `tooling_columns`/`tooling_rows` (even, 0 for none), `tooling_pitch`, `tap_diameter`, `close_diameter`; tooling holes at cell centers, a checkerboard with a tap hole at the lowest corner, so plates are easy to make in pairs (the user).  `GRID_PLATE`: 1/32 in chamfer; 2 x 4 tooling holes on 3 in centers for #10-32 (Claude's choice).
* Chamfers: `solid.chamfer` with every edge named by a point on it, one command: 30 s for 81 holes headless.  `solid.hole` countersinks hung (over 2 min); a 45 degree tapered extrude cut took 74 s and cut the wrong way.
* Page `Grid Plate`: top view and an 8 times size section through a grid hole.
* `solid.chamfer` names each hole's edge by the middle of its +Y half circle (the two halves meet along X).  In the GUI the 200 chamfers took about 5-1/2 minutes (client times out at 60 s; the command finishes); volume within 0.2 %.  The STEP cache should make it a one-time cost; not yet tried with `show_demo.py`.
* Cached: `Grid_plate__0a8d619ce91c7e38.step` (1.4 MB) took 271 s to build headless the first time (load average to about 4 on 4 processors); inserting it took 1.0 s.  Calling `GRID_PLATE.model()` directly skips the cache; `cache.insert(solidcraft, GRID_PLATE.cacheable()[0])` uses it.
* Without chamfers: built in the window 4.2 s, built for the cache 2.2 s, loaded from it 0.05 s (`Grid_plate__8b6da6fe732dc93e.step`).  Chart: `~/scraftcnc_charts/grid_plate_times.html` (outside version control).
