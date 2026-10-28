# LLM Agent Context Log

## 2026-10-26: Created; what `../Fab/` (2022, FreeCAD) offers

Fab's shop model (`../Fab/FabShops.py`, `docs/FabShops.md`):
* `FabShops` > `FabShop` (name, `FabLocation`, machines) >
  `FabMachine` (name, placement in the shop, tool library).
* `FabCNC` (`FabCNCMill`, `FabCNCRouter`; lathe, laser/water jet/
  plasma and 3D printer planned): `FabAxis` per axis (letter, linear
  or rotary, range, max feed, max acceleration, end sensors, brake),
  `FabTable`, `FabSpindle` (taper type such as R8 or CAT40, max RPM,
  reversible, flood and mist cooling), `FabController` (name, post
  processor).  Rapid feeds come from the axes.
* `Fab_ShopBit`: a bit as usable on one machine in one shop, with a
  tool number and a selection priority.  Fab tried to find the fewest
  machines (and shops) that can do every mount of a part, and wrote
  G-code per machine per mount.
* `FabStock` (`FabSolids.py`): stock comes in X/Y increments and a
  list of standard thicknesses, plus a minimum cut on the outside;
  `enclose()` picks the stock for a part's bounding box.
* `FabMount`: a work plane per setup, with an orientation vector and
  CNC origin, so the part can be re-fixtured (`2do.md`: mount
  reorienting, multi mounts, vise and parallels, tooling plate).
* Tools (`FabToolBits.py`, `FabTools.py`): FreeCAD's Path layout,
  `Tools/Shape` (`.fcstd` shapes), `Tools/Bit` (`.fctb` JSON, one
  bit with dimensions), `Tools/Library` (`.fctl`, tool number to bit,
  one library per machine).  Bit families: ball end, bull nose,
  chamfer, dovetail, drill, end mill, probe, slitting saw, thread
  mill, V-bit.  `tool_notes.md`: drills lacked shank diameter/length,
  cutting edge length, flutes, center cutting.
* `FabShops.py` cites MachiningDoctor's chip load calculator for
  feeds and speeds.
* `2do.md` points at EZCAD3's vise, parallels, tooling plate, tool
  matching and operation ordering code (line numbers there).

Lessons: the bit/library split matches #26 in `T.cuwp`; FreeCAD's
Path files were the pain point (poorly documented), so our own TOML
with units is the better base.

## 2026-10-27: Sub-tasks

* `T.si~1.1` (Shop Information) closed: the files, reader, tools,
  tool tables, preferences and the demo running from the shop.
* `T.cuwp~2` and `T.or~3` closed; `T.ds` moved to 1 (the user's
  choice: open work first).
* New sub-tasks, with draft `Details.md`: `T.m~1.2` Mounting (with
  bottom chamfers, tooling holes, tabs), `T.sm~1.3` Stock,
  `T.msaf~1.4` Materials Speeds and Feeds (and where preferences
  belong), `T.tm~1.5` Tool Models.

## 2026-10-27: Renumbered; where things stand

* At the user's choice, history first: `T.or~1` (Original Roadmap)
  with `T.cuwp~1.1` under it, then `T.ds~2` with `T.si~2.1` (closed)
  and the Pending `T.m~2.2` Mounting, `T.sm~2.3` Stock,
  `T.msaf~2.4` Materials Speeds and Feeds, `T.tm~2.5` Tool Models.
* Next session: the user picks which sub-task to open first, and may
  rewrite the draft `Details.md` files.  The user commits and pushes
  in git (including the removal of `machine.toml`).
