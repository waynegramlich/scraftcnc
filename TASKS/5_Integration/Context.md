# LLM Agent Context Log

The user expects things to change all over, and missing features to be found as they come.  Work so far is in `T.ctfs~2.5.1`'s log.

## 2026-11-02: Where things stand

The user is writing this task's `Details.md`, and sub-tasks will follow.  Ready to integrate: `SCMachineVise` with `SCJawPlate`, `SCParallel` with optional holes (a set of 1/2 to 1-5/8 in), `SCGridPlate` (chamfers, tooling holes, and kind `grid_plate` in the shop's tooling files), and every cutter kind built from `examples/shop/tools.toml` with holders; all documented in `Tool_Models.md`.  Stock stays blocks of material for a while (`T.sm~2.4` pending).  `T.tm~2.5`, `T.ctfs~2.5.1` and `T.dtm~2.5.2` are suspended, as more tools are coming; vises, jaw plates, parallels and mill tables still have no kinds in the shop files.  `I.phpsa~1` is closed, never reproduced.  The chamfered grid plate takes about 5 minutes to build after any change to `tools.py`, `mount.py` or `scgeometry.py` (cache key), then 1 s from the cache.
