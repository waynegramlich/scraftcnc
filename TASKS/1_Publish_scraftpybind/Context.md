# LLM Agent Context Log

## 2026-10-26: Repository made from `../solidcraft/`

* Copied (the old project is untouched): `pysolidcraft.py`,
  `pysolidcraft_generate.py`, `pysolidcraft_commands.json` (from
  `solidcraft-cli` 0.20.0), `examples/plate_with_holes.py`.
* The EZPkg bootstrap and PEP 723 block are gone: the module needs
  only the standard library, and a PyPI package has no use for them.
  `json`, `subprocess` and `sys` (which the bootstrap imported) are
  imported directly.  `__version__ = "0.1.0"`.
* Packaging follows `aicontexts`: `pyproject.toml` (setuptools,
  version from `pysolidcraft.__version__`, MIT-0, console script
  `pysolidcraft` = the plate demo), `LICENSE`, `git_hooks/`
  (`core.hooksPath` set), `.gitignore`, `.hgignore`.  No "Typing ::
  Typed" classifier: a single module cannot carry `py.typed`.
* Checkers: `mypy --strict` (now on in `mypy.ini`), ruff (with E501
  selected so `# noqa: E501` is not unused), flake8 and pylint all
  clean.  The generated classes keep SolidCraft's names and one
  argument per parameter, so `pysolidcraft.py` disables the matching
  pylint messages module wide (with the reason).
  `./pysolidcraft_generate.py --cached` reproduces the file exactly.
* Verified: `uv build` wheel (84 KB) into a fresh venv; the
  `pysolidcraft headless` command and the example both wrote STEP
  files (with `solidcraft-cli` from the old project's
  `squashfs-root/usr/bin` on `PATH`).
* Rules copied from `solidcraftcnc`, sources repointed at
  `../aicontexts/RULES/`.
* git and hg initialized; nothing committed to git (the user commits).
  No GitHub repository yet; the URLs in `pyproject.toml` assume
  `waynegramlich/scraftpybind`.

Next: no test suite yet; GitHub repository and workflows
(`check.yml`, `release.yml`) once there is interest.

## 2026-10-26: Moved to `~/public_html/projects/scraftpybind/`

The user meant this directory, not `~/scraftpybind/`.  Rule sources
repointed to `../aicontexts/RULES/`.

## 2026-10-26: Everything working; test suite written

* There was no test suite (none in `../solidcraft` either), so
  `test_pysolidcraft.py` (stdlib `unittest`) was written: 25 tests.
  Offline: `Namespace.execute()`, every cached command reached by
  exactly one method, `connect()`, `control_dir()`, `ControlTransport`
  against a fake control port, `HeadlessTransport` against a fake
  `solidcraft-cli` script, and `pysolidcraft_generate.py --cached`
  reproducing `pysolidcraft.py` (in a scratch copy, with `ruff.toml`).
  Live (needs `solidcraft-cli` on `PATH`): an un-cached generator run
  (only for `solidcraft-cli 0.20.0`), both plates measured with
  `solidcraft-cli eval` (volumes within 1e-4; SolidCraft's are about
  5e-6 off), results and errors.  GUI: opt-in, `PYSOLIDCRAFT_TEST_PORT`.
* Fixed: the generator's default `--cli` was
  `./squashfs-root/usr/bin/solidcraft-cli` (only in `../solidcraft`);
  it is now `solidcraft-cli` on the `PATH`.
* Fixed: `HeadlessTransport.stopped()` used `poll()`, so a session
  whose output ended before it exited reported `status=None` and lost
  its error text; it now waits (up to 10 s).  The fake reproduces it.
* For the live tests:
  `PATH=../solidcraft/squashfs-root/usr/bin:$PATH python3 -m unittest`.
* The user does not expect to run live tests, so the offline tests
  are the ones that matter; the live ones stay as skips.
* `aic` (a link to `../aicontexts/ai_contexts.py`) was removed from
  git and disk; the installed `ai_contexts` is used instead.
* `ruff` 0.17.3 and `uv` 0.13.6 (updated 2026-10-26).

## 2026-10-26: Renamed `pysolidcraft` to `scraftpybind`

* At the user's request, to match the directory: `scraftpybind.py`,
  `scraftpybind_generate.py`, `scraftpybind_commands.json`,
  `test_scraftpybind.py` (all but the test with `git mv`), the PyPI
  package and console script, `SCRAFTPYBIND_TEST_PORT`,
  `scraftpybind_plate.step`.  The class `PySolidCraft` and this task's
  title are unchanged so far (asked).  The entries above use the old
  names.
* Offline `trace` coverage (`python3 -m trace --count --missing
  --module unittest test_scraftpybind`): 32 lines of 19,715 uncovered,
  in `Transport.request()`, `HeadlessTransport.stopped()`/`close()`
  timeouts, the non-`Mapping` result check, `PySolidCraft.execute()`
  and `main()`.

## 2026-10-26: `SolidCraftPyBind`; `T.pp` became `T.ps`; coverage

* The class `PySolidCraft` is now `SolidCraftPyBind` (the generator
  writes it).  This task was renamed "Publish scraftpybind", so its tag
  went from `T.pp` to `T.ps`; nothing referred to the old tag.
* `EXIT_TIMEOUT` (10 s) is how long `HeadlessTransport.stopped()` and
  `close()` wait for a session to exit; tests patch it to 0.2 s.
* New tests (29 now): `Transport.request()`, a result that is not an
  object, a session that never exits (`status=None`), and one killed
  by `close()`.  Offline `trace` coverage: 23 lines uncovered, all in
  `SolidCraftPyBind.execute()` (it sends `None` as `null`, unlike
  `Namespace.execute()`) and `main()`; the user will come back to
  both.
* Two generated docstring lines are over 72 (a long word from
  SolidCraft's text, and a long type name); left as they are.

## 2026-10-26: `# pragma: no cover` marks

* The user's convention: every line the offline tests do not reach
  ends with `# pragma: no cover`, so that `grep` finds them.  As in
  `coverage.py`, a mark on a `def`, `class`, `if` or `else:` line
  covers its block (README, Testing).
* `TestGenerator.run_generator()` now runs the generator in this
  process (patching `TARGET`, `CACHE` and `sys.argv`), so `trace` sees
  it.
* Offline `trace` coverage: `scraftpybind.py` 99.63% (23 of 6300
  uncovered), `scraftpybind_generate.py` 91.52% (42 of 495),
  `test_scraftpybind.py` 82.66% (82 of 473); the example runs only in
  the live tests.  A scratch checker (ast spans of marked lines against
  the `.cover` files) found every uncovered line marked and no stale
  mark.

## 2026-10-26: Open items 9 and 10 fixed

* 9: the generated `SolidCraftPyBind.execute()` now returns
  `Namespace(self.transport).execute(command, params)`, so it leaves
  out `None` parameters like every other method
  (`test_top_level_execute`).
* 10: `test_main` runs `main()` in this process, headless on the fake
  `solidcraft-cli` (which now answers any other command with four
  curve ids), through `LoggingHeadlessTransport`; it checks the 8
  commands, their parameters and the `Wrote ...` line.
* 31 tests.  Offline `trace`: `scraftpybind.py` 99.98% (1 of 6299
  uncovered: the `__main__` line), `scraftpybind_generate.py` 91.52%,
  `test_scraftpybind.py` 84.53%.  24 marks.

## 2026-10-26: On GitHub

* https://github.com/waynegramlich/scraftpybind, public, remote
  `github` (HTTPS), default branch `main`; `main` tracks
  `github/main`.  First push: `64fe80c` (3 commits), checked with
  `gh repo view` and `git ls-remote`; `aic` is not in the tree.
* Next: the testing and release workflows (`check.yml`,
  `release.yml`) and PyPI Trusted Publishing, per the GitHub Workflow
  Rules.

## Where things stand (2026-10-26, end of session)

* Done: the copy from `../solidcraft` works; renamed to
  `scraftpybind` (module, generator, cache, tests, package, console
  script; class `SolidCraftPyBind`; this task `T.ps`); a 31 test
  offline suite (`python3 -m unittest`, 6 live tests skipped without
  `solidcraft-cli`); all checkers clean; on GitHub (public).
* Conventions settled with the user:
  * Live tests are not run; the offline tests are what matter.
  * Every line the offline tests do not reach ends with
    `# pragma: no cover` (one mark per block, as in `coverage.py`).
    After a code change, rerun `trace` and keep the marks exact:
    `python3 -m trace --count --missing --coverdir=DIR
    --ignore-dir=$(python3 -c 'import sys;print(sys.base_prefix)')
    --module unittest test_scraftpybind`, then check every `>>>>>>`
    line in `DIR/*.cover` is inside a marked block and no mark is
    stale.  Coverage: `scraftpybind.py` 99.98% (only the `__main__`
    line), `scraftpybind_generate.py` 91.52%, `test_scraftpybind.py`
    84.53%.
  * `trace`'s `--no-report` (`-R`) drops the counts file (Python
    3.12's `trace.py:736`); subprocess tracing was tried and rejected
    as not worth it, so tests call `main()`s in-process instead.
* Not doing yet: nothing goes to pypi.org (or test.pypi.org) until
  somebody asks for the package there, so no `release.yml` and no
  Trusted Publishing for now.  A `check.yml` testing workflow
  (Linux, Windows, macOS; Python 3.11 and up) is possible meanwhile,
  if the user wants it.
* A private claude.ai page of `README.md`, published by mistake, was
  deleted at the user's request (2026-10-26).

## 2026-10-26: Clear messages when SolidCraft is not there

Asked for by the user while getting `scraftcnc` ready for GitHub (a
newcomer who runs it without a GUI got a `FileNotFoundError`
traceback naming a token file).  The GUI deletes its token file when
it quits, so a missing token file usually means no GUI.

* `ControlTransport.connect()`: a missing `current.port` or token file
  raises `FileNotFoundError` asking whether a GUI is running (with
  `--control PORT`, as this user); a refused connection raises
  `ConnectionRefusedError` saying nothing is listening.
* `HeadlessTransport.start()`: a missing `solidcraft-cli` names the
  releases page (`RELEASES`) and the `PATH`.
* `main()` reports an `OSError` in one line (`scraftpybind: ...`,
  exit 1); the plate is built by `_plate()`.
* Tests: `test_no_gui` (all three, plus `main()`), and
  `test_not_found` checks the message.  `test_scraftpybind.py` now
  passes 1000 lines, so it quiets `too-many-lines`.  32 tests pass (2
  skipped with SolidCraft 0.24.0 on the `PATH`); checkers clean;
  `trace` still finds only the `__main__` line.

## 2026-10-26: Commit email made private

User decision: commits use GitHub's private address
`2482253+waynegramlich@users.noreply.github.com` (`git config
user.email` in this repository; the global one is still the real
address).  Every existing commit was rewritten to it (`git
fast-export | sed | git fast-import` in scratch, then `git reset
--soft`); trees, names, dates and messages checked identical.
`scraftpybind`'s `github/main` still has the old 4 commits, so its
next push is `git push --force-with-lease github main` (the user
agreed: nobody has cloned it).

## 2026-10-30: How automated the generator is; PyPI question

The user asked how automated `scraftpybind_generate.py` is, whether
perfect documentation would make it fully automatic, and whether PyPI
is pointless since the package would get out of date.

Measured (a scratch copy, so the repository did not change):

* A fresh run against `solidcraft-cli` 0.25.1 took 37 s with no manual
  steps; the output parses, but the checkers and tests were not run on
  it.  Compared with the 0.20.0 cache: 407 to 493 commands (86 added,
  none removed), 3 to 12 schemas, 38 to 39 namespaces, and 97 changed
  `params` descriptions.
* In the 0.20.0 cache, 404 of 407 commands are parsed from free text;
  1006 of their 1390 parameters are only `JSON`, 33 commands have no
  parameters and 137 have text left over as notes.
* Still manual: starting a run, reviewing changed methods (nothing
  reports them), `CACHED_VERSION` (`test_scraftpybind.py:62`) and the
  README's version, assertion failures on name collisions, and the
  hand-written `TEXT_TYPES` and `SCHEMA_REFS`.
* SolidCraft released 9 stable versions from 0.23.1 (2026-10-26) to
  0.27.1 (2026-10-30), about two a day.

Conclusions:

* Accurate prose would not be enough, because the free text is hard
  to parse even when correct (`sketch.rectangle.center` puts `connect`
  after a `Returns` sentence).  Input and output schemas for every
  command would make the signatures fully automatic, and the source
  code is not needed: the generator only reads `engine.describe`.
* `engine.describe` also gives an `output` schema, which `fetch()`
  drops today; it could give methods real return types.
* A schema still leaves ordering rules, some rules across parameters,
  what an id refers to, runtime refusals (`edit.repeat` is always
  refused outside the GUI) and failures to prose.  The transports stay
  hand-written, and renames or removals need a person's decision.

PyPI (not decided; this is Claude's recommendation):

* `scraftcnc` is the first consumer, through a symbolic link, and its
  plan is to package both for test.pypi.org.  PyPI refuses packages
  with direct URL dependencies, so a `scraftcnc` on PyPI needs
  `scraftpybind` on PyPI too (or a vendored copy).  This replaces
  "until somebody asks" in the end-of-session notes above.
* Being behind is not the same as being broken: no command was removed
  from 0.20.0 to 0.25.1, and `execute()` and `**extra` reach anything
  newer.  A text search of `scraftcnc` found 25 commands: 14 with the
  same description, 10 changed (not reviewed for whether they break
  anything) and `sketch.arc3d`, which is new and which `probe_batch.py`
  already writes as a raw step.
* Recommended: publish when `scraftcnc` is ready to, regenerating
  first, then release when a consumer needs a command or a change and
  not for every SolidCraft release.  Say which SolidCraft version each
  release was generated from.  The name was free on 2026-10-30.

## 2026-10-30: Could schemas be derived from the Rust source?

Read SolidCraft v0.25.1 in a scratch clone (one handler in depth;
nothing generated or built).  Answer: largely yes, as an AI reading of
each handler, but not as a mechanical parse.

* Upstream's direction (`crates/engine/src/schema/mod.rs`,
  `docs/book/src/dev/schemas.md`): `schemars` generates each schema
  from a Rust "contract" type checked in front of a handler, which
  still reads raw JSON.  `schema/unconverted.txt` lists 455 commands;
  it only shrinks, and new commands are meant to have both schemas
  (a warning for now, required later).
* Handlers show what the prose hides: `rect_center`
  (`crates/engine/src/cmd/sketch.rs:1196`) uses `req_vec2` for `center`
  and `corner`.  But `construction` and `connect` are read in helpers
  (`sketch.rs:410`, `:557`), so reading must follow the calls.  Scale:
  about 98,000 lines in `cmd/`.
* The contract check is off by default, and handlers read a wrong-typed
  key as absent, so a renamed key can be ignored silently.  That is the
  real interface-change risk: no error, possibly wrong geometry.
* Recommended, not decided: derive schemas first for the 25 or so
  commands `scraftcnc` uses, offer them upstream as contracts, and diff
  schemas between releases to flag removed or narrowed parameters.
