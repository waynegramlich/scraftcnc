# LLM Agent Context Log

## 2026-11-03: Decisions (the user's, before `GO`)

* One tree, everything MIT.  `scraftpybind` and `scraftlinuxcnc`
  (private until now) come in with `git subtree add`, keeping their
  git history; their `.hg/`, `ruff.toml`, `mypy.ini` and `.flake8`
  are dropped for this project's.  Their open `TASKS/` items are
  copied here; the rest dropped.  Their `.github/` workflow moves to
  `scraftcnc/.github/`, paths fixed.  An issue reminds the user to
  archive the two GitHub repositories after the reorganization.
* Plain layout, no `src/`: the repository holds `pyproject.toml`
  (if needed), `README.md`, `examples/`, `tests/`, `scripts/`,
  `TASKS/`, `RULES/`, and the package `scraftcnc/` with
  `__init__.py` and the subpackages `pybind/`, `lcnc/` (not
  `linuxcnc`: LinuxCNC's own module has that name), `hmi/` and
  `tooling/`.  Bring pybind's generator and its JSON along.
* No install step: run from the root with `python3 -m ...`; nothing
  outside the standard library (installing LinuxCNC itself is the
  exception).  LinuxCNC starts the panel through a small wrapper
  that sets `PYTHONPATH`.
* Module renames (classes keep their `SC` prefix):
  `scgeometry` -> `geometry`, `scmachine` -> `machine`, `scplot` ->
  `plot`, `scmodelcache` -> `model_cache`, `sckeepout` ->
  `keepout`, `scsetup` -> `setups`, `solidcraftcnc` -> `gcode`,
  `solidcraftcnc_demo` -> `demo` (top level); `sctoolmodel` ->
  `cutter_models`, `tool_models`, `tools`, `mount` (`tooling/`);
  `lcnc_panel`, `lcnc_headless` (`hmi/`); `sim_*`, `lcnc_client`,
  `serve_linuxcnc` (`lcnc/`).
* Scripts: `show_demo.py` (the only one the user runs) and
  `probe_batch.py` (has tests) go to `scripts/`; `probe_flutes.py`
  and `probe_reveal.py` are deleted unless something uses them.
* Links: drop `rs274`, `aic` (now `~/.local/bin/aic`) and the two
  repository links; keep `SharsMD` (dated catalog, not for git) and
  `solidcraft` (found on the `PATH` later).
* Tests: all in `tests/`; the goal is coverage.  One baseline with
  `python3 -m trace --count --summary` before the first move (ask
  first), then no tracing until the user says so.  Ask before every
  test run.
* Old closed task notes keep the old names; open tasks, `README.md`
  and the other documents are updated.
* Work is done by a background agent in chunks of about 3 minutes,
  each ending with a report, so the user can talk in between.

## 2026-11-03: Coverage baseline (before any move)

`python3 -m trace --count --summary --module unittest` (`--ignore-dir` the standard library): 445 tests, OK (10 skipped), 20.5 minutes.  `trace`'s own summary says 100% without `--missing`, so coverage was computed from the `.cover` counts against `trace._find_executable_linenos()` (executable lines, percent hit):

```
    51  51.0%  lcnc_client
   124  92.7%  lcnc_headless
   708  83.2%  lcnc_panel
   306  95.1%  mount
   232  46.6%  probe_batch
   998  99.2%  scgeometry
   250  90.0%  sckeepout
   108  94.4%  scmachine
   157  96.2%  scmodelcache
   320  86.9%  scplot
  6278  53.2%  scraftpybind
   447  94.2%  scsetup
   503  88.7%  sctoolmodel
  1635  96.9%  shops
   376  27.7%  show_demo
   146  63.0%  sim_solidcraft
   699  98.7%  solidcraftcnc
   280  56.4%  solidcraftcnc_demo
  1536  98.6%  tool_models
  1642  97.2%  tools
 16796  76.3%  TOTAL
```

## 2026-11-03: git commits

The user: "During this reorg, I give you permission to do git commits."  Only for `T.rd~5.1` and its subtasks.

## 2026-11-03: mypy (chunk 8)

`mypy.ini` has only `python_version` and the `follow_imports = silent`
override for the generated `scraftcnc.pybind.scraftpybind`; the strict
options of the Python Coding Rules are given on the command line:
`mypy --strict --warn-unreachable --enable-error-code
ignore-without-code --enable-error-code redundant-expr
--enable-error-code truthy-bool scraftcnc tests` (about 4 s).  The
package itself is clean; every error is in a test.

* Before: 255 errors in 8 test files.
* Fixed (test side only): `test_shops`, `test_tools`,
  `test_cutter_models`, `test_mount`, `test_geometry`,
  `test_model_cache`.  Kinds: missing annotations, `shops.read()` and
  SolidCraft replies indexed as JSON (now `Any`, by a `cast` or a
  `reply()` helper), `dataclasses.replace(**dict[str, float])`,
  `SCInserted | None` narrowed with `assert`, `SCHole` narrowed with
  `isinstance`, `setups.KURT_D688` -> `tools.KURT_D688` and
  `setups.SCMachineViseLayer` -> `mount.SCMachineViseLayer` (the same
  objects, re-exported only implicitly), a `SimpleNamespace` stand-in
  cast to `SCPyBind`, one deliberate `# type: ignore[arg-type]`
  (`hole.model(None)`, refused before SolidCraft is used).
* After: 174 errors, in `tests/test_keepout.py` and
  `tests/test_setups.py` only.  Next chunk: those two.

## 2026-11-03: mypy, chunk 9

174 -> 0.  `tests/test_keepout.py` (87) and `tests/test_setups.py` (87, after chunk 8) are clean: annotations; `SCLine | SCArc` narrowed with `isinstance`; `known()` asserts an axis value is set where the old code would have failed on `None` anyway; layers narrowed to `SCParallelLayer` / `SCMachineViseLayer` with `assert isinstance`; `grid_plates` and `read` imported from `shops`, not through `setups`; SolidCraft replies and the example JSON typed `Any`; `SCSetup([])` quieted with `type: ignore[arg-type]` (deliberately wrong).  `mypy --strict --warn-unreachable` with the rules' error codes: no issues in `scraftcnc/` and `tests/` (55 files).  No package code changed.  `mypy.ini` untouched (#14 waits for the user).

## 2026-11-03: Coverage after the reorganization

`python3 -m trace ... --module unittest discover -s tests -t .`: 519 tests in 23 minutes; 1 failure and 2 errors, all old paths (`import lcnc_panel` in two subprocesses of `test_lcnc_panel`, and pybind's deleted `ruff.toml` in `test_scraftpybind`), fixed afterwards.  Every module covers at least what it did in the baseline; `scraftpybind` and `lcnc_client` gained from the tests that came with them:

```
   280  56.4%  scraftcnc.demo
   699  98.7%  scraftcnc.gcode
   998  99.2%  scraftcnc.geometry
   124  92.7%  scraftcnc.hmi.lcnc_headless
   708  83.2%  scraftcnc.hmi.lcnc_panel
   250  90.0%  scraftcnc.keepout
   522  54.6%  scraftcnc.lcnc.install_linuxcnc
   197  87.3%  scraftcnc.lcnc.lcnc_bridge
    51  96.1%  scraftcnc.lcnc.lcnc_client
   231  46.8%  scraftcnc.lcnc.probe_batch
    60  46.7%  scraftcnc.lcnc.serve_linuxcnc
   146  63.0%  scraftcnc.lcnc.sim_solidcraft
   108  94.4%  scraftcnc.machine
   157  96.2%  scraftcnc.model_cache
   320  86.9%  scraftcnc.plot
  6278 100.0%  scraftcnc.pybind.scraftpybind
   495  17.6%  scraftcnc.pybind.scraftpybind_generate
   448  94.2%  scraftcnc.setups
  1635  96.9%  scraftcnc.shops
   503  88.7%  scraftcnc.tooling.cutter_models
   306  95.1%  scraftcnc.tooling.mount
  1535  98.6%  scraftcnc.tooling.tool_models
  1643  97.2%  scraftcnc.tooling.tools
   377  27.9%  scripts.show_demo
 18071  90.5%  TOTAL
```

## 2026-11-03: Where things stand (before the user's git commit)

* Done since the last commit: `ruff.toml` has the rules' `extend-select
  = ["B", "E", "W"]` and its 66 findings are fixed (39 `zip()` calls
  `strict=True`, `zip(pts, pts[1:])` in `test_lcnc_end_to_end`
  `strict=False`; the `strict=True` in its `segment_distance()` is
  unrun, since that suite needs `SCRAFTCNC_LINUXCNC=1`); the coverage
  script is `scripts/coverage_from_trace.py`; the three tests on old
  paths are fixed and pass.
* `show_demo.py` is back at the root (the user: "`./show_demo.py` must
  just work"); `./tests/test_show_demo.py` runs directly too.  Its
  watcher is now stopped by `pkill -f "scraftcnc.lcnc.sim_linuxcnc
  --watch ..."` (the old `sim_linuxcnc.py` pattern no longer matched).
* The user's first `./show_demo.py` run after the move stopped in
  state `T` (stopped by the terminal: Control-Z or `&`) while modeling
  the stack; LinuxCNC, SolidCraft and the part were up.  Not a
  reorganization bug as far as seen.
* The one regression the user saw (the first path shown again after
  the rounding pass) is how `SCPathRack` always worked: `T.npfetc~5.3`.
* **Nothing closes until the user has run `./show_demo.py` through
  (the user's rule).**  Then: check the `Summary.md` files (written
  already) and close `T.rd~5.1` and its eight subtasks.  Not yet run:
  the LinuxCNC end-to-end suite (`SCRAFTCNC_LINUXCNC=1`), the CI
  workflow.  `I.amgr~2` (archive the old GitHub repositories) waits
  for all of it.
