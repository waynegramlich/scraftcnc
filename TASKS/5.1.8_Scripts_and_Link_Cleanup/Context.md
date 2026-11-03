# LLM Agent Context Log

## 2026-11-03: Done (chunk 7)

* `show_demo.py` -> `scripts/show_demo.py`, run as
  `./scripts/show_demo.py` (from anywhere): it puts the repository
  root on `sys.path`; `PROJECT` is now the root (`parent.parent`).
  `tests/test_show_demo.py` imports `from scripts import show_demo`
  (a namespace package; no `scripts/__init__.py`).
* `probe_batch.py` -> `scraftcnc/lcnc/probe_batch.py`, not `scripts/`:
  `scraftcnc/lcnc/sim_solidcraft.py` imports `path_steps`,
  `send_batch` and `sketch_steps` from it, and the package must not
  import a script.  Run as `python3 -m scraftcnc.lcnc.probe_batch`.
* `probe_flutes.py`, `probe_reveal.py`: deleted (only old task notes
  name them).
* Links `rs274` and `aic` removed, and dropped from `.gitignore`;
  `solidcraft` and `SharsMD` stay.  No `.py` is left at the root.
* `aic` now runs `~/.local/bin/aic` -> `~/.local/bin/ai_contexts`
  (the installed one); the old `./aic` ran `../aicontexts/ai_contexts.py`
  (the working copy), which may be newer.
* Checks: ruff clean; imports of the moved modules and their tests;
  `./scripts/show_demo.py --help`.  No tests, no mypy.
