# Summary of `T.ct` Consolidate Tests

All tests (the root ones, pybind's and lcnc's, 22 files) are in `tests/`, run with `python3 -m unittest discover -s tests -t .` (519 tests).  The suite was not run during the moves (the user's rule: ask first); the one run at the end, under `trace`, found 3 tests on old paths, fixed.  Coverage went from 76.3% to 90.5% (pybind's and lcnc's tests came along); no module dropped; numbers in `T.rd~5.1`'s `Context.md`.  Part of `T.rd~5.1`.
