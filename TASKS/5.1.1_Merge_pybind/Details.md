# 5.1.1 Merge pybind

(Draft by Claude, 2026-11-03; the user's to revise.)

`git subtree add --prefix=scraftcnc/pybind` of `../scraftpybind`, keeping its history; add `__init__.py`, bring the generator and `scraftpybind_commands.json`, drop its `.hg/` and checker configs, and point the imports at `scraftcnc.pybind`.
