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
