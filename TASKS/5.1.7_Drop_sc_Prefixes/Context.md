# LLM Agent Context Log

## 2026-11-03: Chunk 5, renames done

* `git mv`: `scgeometry` -> `geometry`, `scmachine` -> `machine`,
  `scplot` -> `plot` (`scplot_template.html` -> `plot_template.html`),
  `scmodelcache` -> `model_cache`, `sckeepout` -> `keepout`, `scsetup`
  -> `setups`, `solidcraftcnc` -> `gcode`, `solidcraftcnc_demo` ->
  `demo`, `tooling/sctoolmodel` -> `tooling/cutter_models`; the root
  tests to match (`test_geometry`, `test_machine`, `test_plot`,
  `test_model_cache`, `test_keepout`, `test_setups`, `test_gcode`,
  `test_cutter_models`).
* References changed with a word-bounded `sed` over every tracked
  `.py`, `.yml`, `.ini`, `.html`, `.toml` outside `TASKS/` and
  `ISSUES/`; no old name is left in them.  No variable collides with a
  new module name (the module objects imported whole are `setups`,
  `keepout`, `model_cache`, `cutter_models`, `demo`).
* Checks: `ruff` clean; every renamed module and every root test,
  `show_demo` and `probe_*` import; `python3 -m scraftcnc.demo` writes
  the G-code; `python3 -m scraftcnc.shops check examples/shop/*.toml`
  OK.  No tests, no mypy.
* Old names left in prose: `README.md` (13 lines), `Tool_Models.md`
  (25, written by `tool_models.py`: regenerate), and open tasks'
  notes; closed tasks keep theirs.
