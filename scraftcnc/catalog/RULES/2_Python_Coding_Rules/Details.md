# Python Coding Rules

<!-- --------------------------- 79 characters ---------------------------- -->

<!--
These rules are based on `Misc_Files/python_with_markdown.md`, which has
background and references.  Where the two differ, these rules take
precedence.
-->

## Checkers

* After every code change, rerun all of the checkers on the files that
  changed, and fix (or report to the user) everything they find before
  calling the change done:
  * `ruff check` (`ruff check --fix` fixes simple errors) and
    `ruff format --line-length 79`, which formats the code.
  * `flake8`, with `max-line-length = 79` in the project's `.flake8`.
    `ruff format` puts spaces around a `:` in a complex slice (which
    PEP 8 allows), so `.flake8` also has `extend-ignore = E203`.
  * `mypy --strict` (or at least `mypy --disallow-untyped-defs`), since
    plain `mypy` skips functions with no type hints.
  * `pylint`, which finds things that the others do not (e.g. unused
    arguments, and functions that have grown too big).
* Fix what the checkers find where that is reasonable (e.g. an unused
  argument gets a name starting with `_`; a function with many
  arguments takes some keyword-only).  A message that is deliberate is
  quieted by a comment that names it (never a bare one that quiets
  everything), next to a comment (or docstring sentence) saying why:
  * `ruff` and `flake8`: `# noqa: CODE` at the end of the line (e.g.
    `# noqa: E501`); both read the same comment.  A code that does not
    suit the project is ignored in its `ruff.toml` or `.flake8`, with a
    comment, and only with the user's agreement.
  * `mypy`: `# type: ignore[CODE]` at the end of the line (e.g.
    `# type: ignore[arg-type]`).
  * `pylint`, for one line: `# pylint: disable=NAME` at the end of the
    line (for a function's messages, its `def` line), or
    `# pylint: disable-next=NAME` on the line before, when the line
    would be too long.
  * `pylint`, for a whole module (e.g. its size limits, like
    `too-many-locals`, which type hints on every variable inflate): a
    `# pylint: disable=NAME,...` line after the module docstring,
    before the imports.
* Use current versions of the checkers; distribution packages can be
  far behind (Ubuntu 24.04 has `pylint` 3.0.3 and `mypy` 1.9).
  `uv tool install ruff flake8 mypy pylint` installs them for the user,
  in `~/.local/bin`, which must come before `/usr/bin` in `PATH`.
* No checker is run on the PEP 8 72 character limit for docstring and
  comment lines (`ruff` rule `W505` could, but it is not used).  Claude
  is responsible for keeping those lines to 72 characters or fewer.

## Type Hints

* **ALL** Python variables should have a valid type hint.
* Use `Any` only as a last resort.
* Quoted type hints (e.g. `"MyClass"`) are forward references for types
  not yet defined; `from __future__ import annotations` avoids the quotes.
* To discover an expression's type, temporarily insert
  `reveal_type(expr)`, run `mypy`, then remove it.
* To give a long type a short name, use a type alias
  (`type Matrix = list[list[float]]` in Python 3.12+, or
  `Matrix: TypeAlias = list[list[float]]` before that).
* Use `NewType` only to create a distinct type (e.g.
  `UserId = NewType("UserId", int)`) that `mypy` keeps separate from its
  base type.

## Comments and Formatting

* Docstrings and comments are written in Markdown.
* Write comments and docstrings as English sentences: first word
  capitalized, ending with a period (or question mark).  Partial
  sentences that end in a `:` are allowed as well.  No misspelled
  words.
* PEP 8 line lengths: code lines 79 characters or fewer; docstring and
  comment lines 72 characters or fewer.  Exceptions are allowed where
  a line cannot reasonably be wrapped (e.g. long hyperlinks, code
  blocks).
* Enclose variable, function, class, and method names in back quotes
  inside comments and docstrings (e.g. `my_func`, `my_class`,
  `my_variable`).
* Separate blocks of code with blank lines, and put a 1- or 2-line `#`
  comment at the front of each block.

## Test Suites

A test suite file is a Python file (its name ends with `.py`) that
meets at least one of the following:

* Its parent directory is named `tests` (e.g. `tests/foo.py`, but
  not `tests/unit/foo.py`).
* Its name starts with `test_`.
* Its name ends with `_test.py`.

Test suite files are exempt from the rules in the `Shebang Line`
section and every section after it.  This is a deliberate fence: test
suites are designed and written by AI, so only the sections above
`Shebang Line` apply to them.  A new section placed after
`Shebang Line` is intentionally exempt as well; a rule that test
suites must follow goes above it.

## Shebang Line

* A module meant to be directly executable starts with
  `#!/usr/bin/env python3` (PEP 394) and should have its execute bit set.
* Omit the shebang if the module is not meant to be directly executable.

## Docstrings

Docstring layout follows PEP 257:

* Use triple double quotes (`"""`).
* The one-line summary immediately follows the opening `"""` with no
  intervening space, and ends with a period.
* No blank line before a docstring.
* A one-line docstring keeps the opening and closing `"""` on the same
  line, with no blank line after it.
* A multi-line docstring follows the summary with a blank line, then
  one or more Markdown paragraphs separated by blank lines.  The
  closing `"""` goes on a line by itself.
* Put a blank line after a class docstring (one-line or multi-line).
  Function and method docstrings need no blank line after them.
* The module docstring comes first in the file (after any shebang) and
  describes the overall module or program.

```python
#!/usr/bin/env python3
"""A one-line summary of the module or program, terminated by a period.

One or more Markdown paragraphs describing the module or program.
"""
```

## Functions and Methods

Docstring sections, in order:

* **One-line summary** of what the function/method does, then a blank
  line.
* **`Arguments:`**: one bullet per argument as `` * `name` (`type`): ``
  followed by its description.
* **`Returns:`** / **`Yields:`**: the return or yield value(s), with the
  type in parentheses.
* **`Raises:`**: one bullet per possible exception.

```python
# Function `divide()`:
def divide(dividend: int, divisor: int) -> int:
    """Divide two integers.

    Arguments:
    * `dividend` (`int`):
      The number to divide.
    * `divisor` (`int`):
      The number to divide by.

    Returns:
    * (`int`): The quotient of the division.

    Raises:
    * `ZeroDivisionError`: If `divisor` is zero.
    """
    return dividend // divisor
```

## Classes

* Document class attributes under an `Attributes:` section, using the
  same `` * `name` (`type`): `` bullet format.  Every attribute is
  listed, including those not passed to the constructor.
* If the attributes have no natural order, consider alphabetizing them
  and titling the section `Attributes (alphabetized):`.

## Dataclasses

* Prefer `@dataclass(slots=True)` for classes that mostly hold data.
  Slots reduce memory usage, slightly speed up attribute access, and
  turn a misspelled attribute assignment into an `AttributeError`.
* Declare every attribute with an explicit `field(...)` so it is
  obvious which attributes are constructor arguments:
  * `field(init=True)`: a constructor argument.
  * `field(init=False, default=...)`: not a constructor argument; it
    is filled in by `__post_init__()` or later processing.
* Attribute order:
  * Put all of the `init=True` fields (and any `InitVar` fields) first,
    in their natural constructor argument order.
  * Put the remaining fields after them, in whatever groups make sense
    to the programmer (e.g. fields computed by `__post_init__()`, or
    fields used by the same feature).
  * Start each group with a one-line `#` comment explaining what the
    group is for (e.g. `# Constructor arguments:`).
  * Alphabetize the fields within every group after the constructor
    arguments, and end its comment with `(alphabetized):`.
  * Put any fields that don't fit a group last, under a
    `# Remaining attributes (alphabetized):` comment.
* Add a `Constructor:` section to the class docstring showing the
  initialization call, because the arguments are hard to see in a
  dataclass.  Keep it in sync with the `init=True` fields and any
  `InitVar` fields (in field order, including those inherited from a
  base class).
* Mutable defaults (`list`, `dict`, `set`, and other objects) **must**
  use `default_factory` (e.g. `field(init=False, default_factory=list)`)
  so instances do not share one object.  Immutable defaults (`int`,
  `str`, `tuple`, `None`) use `default=`.
* For `init=False` fields filled in later, prefer a type-correct
  sentinel (e.g. `-1`, `""`, `()`) over `None`, so the type hint need
  not be `X | None` and `mypy` does not force `None` checks everywhere.
  Use `X | None = None` only when "absent" is a real, meaningful state.
* Use `__post_init__()` to validate constructor arguments (with
  `assert` or by raising an exception) and to compute `init=False`
  fields.  Its docstring follows the Functions and Methods rules, with
  an `Arguments:` section for any `InitVar` arguments.
* A value needed only during initialization (e.g. a `tracing` string)
  should be an `InitVar[...]`; it is passed to `__post_init__()` as an
  argument instead of being stored as an attribute.
* Use quoted forward references (e.g. `"PyNode"`) for types defined
  later in the file, or use `from __future__ import annotations`.
* Inheritance:
  * Subclass fields are appended after the base class fields.  Since a
    field without a default cannot follow one with a default, subclass
    fields are usually `init=False` with a default (or use
    `kw_only=True`).
  * If the subclass uses `slots=True`, the base class must as well;
    otherwise instances still get a `__dict__` and the slot benefits
    are lost.
  * A subclass's `__post_init__()` replaces the base class's; call the
    base version explicitly if it exists.  With `slots=True`, the
    zero-argument `super()` fails before Python 3.14, so write
    `BaseClass.__post_init__(self)` instead.
  * A dataclass may have zero fields; no placeholder attribute is
    needed.
* Ordering and equality:
  * `@dataclass` generates `__eq__()` automatically.  For sorting,
    prefer `@dataclass(order=True)` (which compares fields in
    declaration order) or a `__lt__()` that compares tuples:
    `return (self.a, self.b) < (other.a, other.b)`.
  * Do not chain comparisons with `or` (e.g.
    `self.a < other.a or self.b < other.b`); that is not a valid
    ordering and gives inconsistent sort results.
* Use `@dataclass(frozen=True, slots=True)` for values that should
  never change after construction (they also become hashable).

```python
from dataclasses import InitVar, dataclass, field


# Class `SampleClass`:
@dataclass(slots=True)
class SampleClass:
    """One-line summary goes here.

    More multi-line documentation goes here.

    Attributes:
    * `likes_spam` (`bool`): True if we like SPAM.
    * `eggs` (`int`): The number of eggs laid.
    * `egg_sizes` (`list[float]`): The size of each egg laid.
    * `total_size` (`float`): The total size of all eggs laid.
    * `cook_style` (`str`): How the eggs get cooked.
    * `served` (`bool`): True once the eggs are served.

    Constructor:
    * `SampleClass(likes_spam, eggs, tracing)`
    """

    # Constructor arguments:
    likes_spam: bool = field(init=True)
    eggs: int = field(init=True)
    tracing: InitVar[str] = ""

    # Attributes set by `__post_init__()` (alphabetized):
    egg_sizes: list[float] = field(init=False, default_factory=list)
    total_size: float = field(init=False, default=-1.0)

    # Remaining attributes (alphabetized):
    cook_style: str = field(init=False, default="")
    served: bool = field(init=False, default=False)

    # Method `SampleClass.__post_init__()`:
    def __post_init__(self, tracing: str) -> None:
        """Validate arguments; compute `egg_sizes` and `total_size`.

        Arguments:
        * `tracing` (`str`):
          A tracing string used only during initialization.

        Raises:
        * `ValueError`: If `eggs` is negative.
        """
        # Validate the arguments.
        if self.eggs < 0:
            raise ValueError(f"{self.eggs=} must not be negative")

        # Compute the egg sizes and their total size.
        self.egg_sizes = [1.0] * self.eggs
        self.total_size = sum(self.egg_sizes)
```
