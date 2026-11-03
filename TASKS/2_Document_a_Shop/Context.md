# LLM Agent Context Log

## 2026-11-02: Squeezed; where things stand

`T.msaf~2.1`, `T.si~2.2` and `T.m~2.3` are closed, `T.tm~2.5` is Open, and `T.sm~2.4` is Pending, though `scsetup.py` places raw
material as a plain box.  `examples/shop/` replaced `machine.toml`.

### What `../Fab/` (2022, FreeCAD) offers, for what is left

* `FabStock` (`FabSolids.py`): stock comes in X/Y increments and a list of standard thicknesses, plus a minimum cut on the outside;
  `enclose()` picks the stock for a part's bounding box.
* `FabMount`: a work plane per setup, with an orientation vector and CNC origin, so a part can be re-fixtured.
* `FabCNC` kinds planned: router, lathe, laser/water jet/plasma, 3D printer.  Fab sought the fewest machines and shops that can do
  every mount of a part, and wrote G-code per machine per mount.
* `2do.md` points at EZCAD3's vise, parallels, tooling plate, tool matching and operation ordering code.
* The lesson: FreeCAD's Path files were the pain point, so our own TOML with units is the better base.
