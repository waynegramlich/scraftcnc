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

## 2026-10-27: Nested TOML and `Shops.md`

* User decisions: "Nested TOML" is a description in more than one
  `.toml` file, joined by `"@FILE_NAME"`; the reader splices them into
  one JSON style data structure for the CNC side.  One top-level
  `Shops.md` describes it: a general Nested TOML section first, then a
  section per `kind`, and the format version it describes.
* Done: `Details.md` updated; `Shops.md` created as a skeleton (keys
  `snake_case` pending #0, TODOs for the kinds not yet worked out).
  The user is now editing `Shops.md`.
* Not answered yet: a test that keeps `Shops.md` and the loader's keys
  in step.

## 2026-10-27: Where things stand (end of session)

* The user is editing `Shops.md` for a while, then commits and pushes
  in git.  Next session: read `Shops.md` as the user left it (it is
  now the user's document; Claude edits it only when asked), and pick
  up the open questions: #0 key style, #1 machine class name, #3
  address, #5 file split, #6 `Shops.md` at the top level (done that
  way, not yet confirmed), #7 a test keeping `Shops.md` and the
  loader's keys in step.
* To do once `Shops.md` settles: a pointer to it in `README.md`
  ("The Files"); then example files (`examples/shop/`) and the loader.
* `#README.md#` (an Emacs autosave) is lying in the project directory;
  it is not Claude's.
