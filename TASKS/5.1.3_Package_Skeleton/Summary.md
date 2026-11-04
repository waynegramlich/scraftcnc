# Summary of `T.ps` Package Skeleton

Plain layout, no `src/` and no install step: the package `scraftcnc/` (with `pybind/`, `lcnc/`, `hmi/`, `tooling/`), run from the repository root with `python3 -m`.  Modules moved with `git mv` straight to their final directories; relative imports inside the package; files at the repository root (`examples/`, `docs/`, `solidcraft`) found from the module's own location.  No LinuxCNC wrapper was needed (its INI starts `lcnc_bridge.py`, not the panel).  The demo's G-code was byte-identical before and after.  Part of `T.rd~5.1`.
