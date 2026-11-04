# LLM Agent Context Log

## 2026-11-03: Where to start

* `scraftcnc/lcnc/sim_solidcraft.py` (`SCPathRack`): `moves` is a
  `dict[int, list[SCMove]]` by T number (filled in `__init__()`), the
  sketches are named `T{number:02d} path`, `show()` switches on the T
  number of the tool in the spindle (`SCSample.tool`, from
  `stat.tool_in_spindle`) and draws the next tool ahead.  Keying by
  turn (the index of each tool change in program order) instead of T
  number needs the sample to know which turn it is in: e.g. count tool
  changes as samples arrive, or carry the program line
  (`stat.motion_line`) and map line ranges to turns.
* Not a reorganization regression: the demo's G-code is byte-identical
  to before `T.rd~5.1`, and `SCPathRack` only had import and path
  changes.  It may also explain `I.phpsa~1` (an earlier tool's path
  shown near the end of a run).
* `tests/test_sim_path_rack.py` tests `SCPathRack`.
