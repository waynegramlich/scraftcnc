# Python Coding Rules

<!-- --------------------------- 79 characters ---------------------------- -->

<!--
Terse, for Claude; background in `Misc_Files/python_with_markdown.md`.
HTML comments stay: imports strip them, so they cost no tokens.
-->

## Checkers

* After every change, run on the changed files and fix (or report) all
  findings before calling it done: `ruff check` (`--fix` ok), `ruff
  format --line-length 79`, `mypy --strict`, `pylint`, with the
  project's configs: `ruff.toml` has `extend-select = ["B", "E", "W"]`;
  `[tool.mypy]` has `strict`, `warn_unreachable` and `enable_error_code
  = ["ignore-without-code", "redundant-expr", "truthy-bool"]`.
* Fix findings where reasonable (unused arg -> `_name`; many args ->
  some keyword-only).  Quiet a deliberate one only by its code or name,
  with a comment saying why.  Project-wide ignores need the user's
  agreement.

## Type Hints

* Annotate every variable, not just the signatures `--strict` requires:
  the hints catch bugs.  `Any` only as a last resort.

## Test Suites

A `.py` whose parent directory is `tests`, or named `test_*` or
`*_test.py`.  Only the sections above apply to it.

## Comments and Docstrings

* Markdown, full English sentences, names in back quotes, lines <= 72
  columns (code: 79).
* Blank lines between code blocks; each block starts with a 1-2 line
  `#` comment.
* PEP 257, with Markdown paragraphs.  Shebang `#!/usr/bin/env python3`
  (and the execute bit) only on executable modules.
* Function docstring sections, in order, as needed: `Arguments:`
  (`` * `name` (`type`): ``, the description indented on the next
  line), `Returns:` / `Yields:` (`` * (`type`): description ``),
  `Raises:` (`` * `Error`: when ``).

## Classes and Dataclasses

* Class docstring lists every attribute under `Attributes:` (same
  bullet form; `Attributes (alphabetized):` if they have no order).  A
  dataclass's also has `Constructor:` (`` * `Name(arg1, arg2)` ``),
  matching its `init=True` and `InitVar` fields, inherited ones
  included.
* Data-holding classes: `@dataclass(slots=True)` (plus `frozen=True`
  for immutable values).  Every attribute uses `field(...)`:
  `init=True` for constructor arguments, `init=False, default=...`
  otherwise.
* Field order: constructor arguments and `InitVar`s first, in natural
  order, under `# Constructor arguments:`; then groups, each under a
  one-line comment ending `(alphabetized):` and alphabetized; leftovers
  last under `# Remaining attributes (alphabetized):`.
* Fields filled in later: a type-correct sentinel (`-1`, `""`, `()`),
  not `None`, unless absent is a real state.
* `__post_init__()` validates arguments and computes `init=False`
  fields; init-only values are `InitVar[...]`, documented under its
  `Arguments:`.
