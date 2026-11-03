# General AI Rules

These rules are about how Claude works with the user, whatever the
project.

## Lists

* Number every list that the user may answer item by item: issues,
  open questions, choices and next steps (1, 2, 3, ...).  The user
  answers by number (e.g. "#2: Fix.  #3: Later.").
* When a list is given again, keep each item's number, so that the
  user's answers still match; a new item gets the next number, and a
  finished one is marked done rather than dropped and renumbered.
  When the user asks for the list to be renumbered (e.g. to put the
  items on hold last), say which old number each item had.

## Referring to Code

* When referring to code in a file, give the file name and the line
  range, as `FILE:FIRST-LAST` (e.g. `ai_contexts.py:1727-1760`), or
  `FILE:LINE` for a single line, so that the user can go straight to
  it.  Name the function, class or method as well when there is one
  (e.g. ``ai_contexts.py:1727-1760 (`Items.resolve()`)``).
* Line numbers change as a file is edited, so give them as the file is
  at the time, and look them up again rather than reusing old ones.

## Out of Date Tools

* At the start of each session, before other work, check whether the
  tools that the active rules use are out of date, and tell the user
  which ones are (with the installed and current versions); update one
  only when the user says so.  For tools installed with `uv tool`
  (e.g. the Python checkers): `uv tool list --outdated`, which prints
  nothing when every tool is current.  `uv self update --dry-run`
  checks `uv` itself.  For a tool installed with `apt` (e.g. `gh`, from
  GitHub's own repository), `apt list --upgradable 2>/dev/null` lists
  the ones with a newer package; a tool is only out of date when one
  is listed (GitHub's repository can lag its releases, which `gh
  release view --repo cli/cli --json tagName --jq .tagName` shows).
* Tools from a distribution (e.g. `/usr/bin/pylint` from Ubuntu) are
  often far behind; suggest replacing them with a `uv tool install`
  (see the Python Coding Rules).
