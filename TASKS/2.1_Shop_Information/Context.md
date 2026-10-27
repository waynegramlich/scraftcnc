# LLM Agent Context Log

## 2026-10-27: Created; `Details.md` drafted with the user

* Created as sub-task 2.1 of `T.ds~2` (both Open) instead of a new
  top-level task, since `T.ds~2` already planned this (its
  `Context.md` summarizes `../Fab/`).  `Details.md` was drafted by
  Claude at the user's request and revised from the user's answers;
  it holds every decision so far and the open questions (the user's
  numbering 0-5).
* Read in full: `../Fab/FabShops.py` (1032 lines; summarized in
  `Details.md`).  Not yet reread: `../Fab/FabTools.py`,
  `FabToolBits.py`, `FabSolids.py` (`FabStock`), `docs/FabShops.md`.
* User decisions: many TOML files, each starting with `name`, `kind`,
  `language`, `version` (semantic); `"@FILE_NAME"` stands for another
  file's contents, which must be in the same directory; tools are
  shared between machines, T numbers allocated per machine (a tool
  table); the controller lists all the codes it accepts, LinuxCNC the
  baseline; Python classes `SC` + `CamelCase`, no collision with
  `scraftpybind` (none of its classes start with `SC`; this project
  has `SCMachine` and `SCTool` already); only example files in this
  repository; shop location is latitude, longitude and address.
* Waiting on the user: #0 TOML key style (research in `Details.md`,
  `snake_case` recommended); #1 the machine class name; #3 address as
  one string or separate fields; #5 how the files are split (left to
  the user).
* Next: once #0 is settled, write example files (e.g.
  `examples/shop/`) and the loader (`scshop.py`?), with tests.
