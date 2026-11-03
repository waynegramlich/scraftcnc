# LLM Agent Context Log

## 2026-11-03: Chunk 6

* All 17 root tests, `test_scraftpybind` and lcnc's two tests are in
  `tests/` (with `__init__.py`); `scraftcnc/lcnc/tests/` is gone.
  Run with `python3 -m unittest discover -s tests -t .` (479 tests
  discovered; not run).  Root lookups use `Path(__file__)...parent.parent`;
  cross-test imports are `from tests.test_x import`.  The workflow runs
  `tests.test_install_linuxcnc` and `tests.test_lcnc_bridge`.
* Docs: `README.md` rewritten for one clone and `python3 -m`; usage
  text in package modules uses `python3 -m scraftcnc....`; generated
  snippets in `tool_models.py` import `scraftcnc.tooling.tools` etc.;
  `Shops.md` and `Tool_Models.md` regenerated (the document check
  `tool_models.DOCUMENT == document()` holds).  lcnc and pybind
  READMEs updated.
* Left for `T.salc~5.1.8`: `show_demo.py` and `probe_*.py` at the root
  (their usage text still says `./x.py`).
