# Summary of `T.cuwp` Come up with a plan

The CNC side of `scraftcnc`, built 2026-10-25 to 2026-10-26, and its
publication on GitHub:

* `scgeometry.py`: `SCRoundPoly` (corners with their own radii,
  self-crossings refused, offsets), `SCLoop`, `inset()`, `beyond()`.
* `solidcraftcnc.py`: `SCCNC` writes RS-274 (inches, G90, G17, G94)
  as dictionaries: climb milled profiles with half circle leads,
  pockets cleared by rings (with islands, spurs into corners, ramped
  or drilled entries), drilling (canned cycles or pecks), through
  cuts with an overcut, top edge bevels (V-bit) and round-overs, run
  time estimates.  Roughing stages were added later, in `T.si~2.1`.
* `scplot.py`: a self-contained HTML tool path viewer, and the path as
  SolidCraft 3D sketches.  `solidcraftcnc_demo.py`: the notched plate
  with a hole and a pocket around three islands.
* Moved from `pysolidcraft`/EZPkg to `../scraftpybind` (a symlink);
  published as https://github.com/waynegramlich/scraftcnc (MIT-0),
  commits under GitHub's private address.

Left over, moved to `T.ds~2`: bottom chamfers (#22, now a question of
mounting), holding the part with tooling holes and two phase tabs
(#23), and 3D models of the tools (#25).  #24 (roughing) was done in
`T.si~2.1`; the tool library questions #26-#29 were settled there.
The `T.or~3` plan is closed with it.
