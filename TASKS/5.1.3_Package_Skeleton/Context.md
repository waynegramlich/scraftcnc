# LLM Agent Context Log

## 2026-11-03: Chunk 4 (modules moved, old names kept)

* `git mv` into `scraftcnc/` (scgeometry, scmachine, scplot +
  template, scmodelcache, sckeepout, scsetup, solidcraftcnc,
  solidcraftcnc_demo, shops), `scraftcnc/tooling/` (tools, mount,
  sctoolmodel, tool_models), `scraftcnc/hmi/` (lcnc_panel,
  lcnc_headless), `scraftcnc/lcnc/` (sim_linuxcnc, sim_move,
  sim_solidcraft).  Tests, `show_demo.py`, `probe_*.py` stay at the
  root for now.
* Imports: relative inside the package, absolute `scraftcnc.x` in
  root files and in the tests that live in the package
  (`scraftcnc/lcnc/tests/`, `scraftcnc/pybind/test_scraftpybind.py`).
* Paths: `Path(__file__).resolve().parents[N]` for the repository
  root (`examples/`, `solidcraft/`, `Tool_Models.md`, `docs/`);
  `tools.TOOLING_SOURCES` names `mount.py`, `../scgeometry.py` and
  `tools.py` (the cache key's sources; models are rebuilt once).
* `show_demo.py` and `test_lcnc_end_to_end.py` start the demo, the
  panel and the watcher with `python3 -m ...`.
* No wrapper for LinuxCNC was needed: `lcnc_sim.ini`'s `DISPLAY` is
  `lcnc_bridge.py` (copied into the target), not the panel.
* Checked: every moved module imports (`sim_linuxcnc` needs LinuxCNC's
  `linuxcnc`, as before); `python3 -m scraftcnc.solidcraftcnc_demo`
  writes the G-code; `python3 -m scraftcnc.shops check` is OK.  No
  tests run.
* Left: `tool_models.py` writes `./tool_models.py` and `./sctoolmodel.py`
  into `Tool_Models.md` (regenerate later); `test_shops.py` and
  `test_tool_models.py` messages name `./shops.py` and
  `./tool_models.py`.
