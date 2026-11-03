# LLM Agent Context Log

## 2026-11-03: chunk 3

Flattened `scraftcnc/lcnc/`; dropped both merged repositories' settings, `RULES/`, `TASKS/` (their open items were empty), `LICENSE` (same MIT-0) and pybind's `git_hooks/` (the root has its own); moved the workflow to `.github/workflows/` (runs `python -m scraftcnc.lcnc...`, no install); repointed imports to `scraftcnc.pybind.scraftpybind` / `scraftcnc.lcnc` (relative inside `lcnc`); removed the `scraftpybind.py`, `lcnc_client.py` and `scraftlinuxcnc` links.  Kept `~/.cache/scraftlinuxcnc` and `.local/share/scraftlinuxcnc` (installed targets use them).  Open: `mypy --strict` on the changed test files now finds 135 errors in 5 test files (`test_scsetup`, `test_scmodelcache`, `test_mount`, `test_sctoolmodel`, `test_tools`); before the change `test_scsetup`+`test_mount` gave 46 in 9 files (in followed modules); `mypy.ini`'s override now names `scraftcnc.pybind.scraftpybind`.  Not yet looked into.
