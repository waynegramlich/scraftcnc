# LLM Agent Context Log

## 2026-11-04: Questions and the first answers

Claude asked 22 numbered questions (sticky numbers; new ones go on
from #23; the user answers about five at a time).  The user's answers:

* #1: Only RS-274 `( ... )` comments, no `;`.  A whole-line comment
  and a comment at the end of a command are to be told apart (the
  user's wording repeated itself; to confirm).
* #2: Open.  RS-274 is meant to be read by humans: pretty printed
  JSON is only semi-readable, TOML better, and a Python call has
  appeal because the Python code can be heavily documented.
* #3: Keep lines to PEP 8 lengths (79), for people reading them.
* #4: The user leans to Python (module, class, method).
* #5: Yes, versions are wanted.

Found by Claude: a `( ... )` comment can not hold `(` or `)`, so a
Python call can not be written as is (#23).

Still open: #6-#22 as first asked (self-contained vs by reference,
cache keys, the part, stock, coordinate frames, keep-outs, spindle
tools, display, operator steps, writer and reader, the rename,
foreign files, multi-setup).

## 2026-11-04: Second answers

* #1: Settled.  Setup data only in comment lines of their own.
* #23: Leaning to TOML (the only format without parentheses), though
  the user is not fond of it.  A `)` in a TOML string is still a
  problem.  (Claude: TOML's Unicode escapes, backslash-u 0028
  and 0029, get around it.)
* #4: Anything importable from `PYTHONPATH` can be used, and
  `PYTHONPATH` should be easy to set when running.  The user isn't sure
  this fully answers it.
* #5: Settled.  The version is the `scraftcnc` release number (the
  PyPI version, if it ever goes there).
* #6: Settled.  A `.nc` refers to the environment that built it and
  is not expected to work anywhere else.

## 2026-11-04: Third answers

* #4: A comment names `M.C.M` (module, class, method).  `importlib`
  imports M; the rest follows.
* #24: Read at most 5 files at a time, asked for as a top 5 item.
  `setups.py` and `tooling/mount.py` have been read.  `SCLayer`
  (`mount.py`) already has `name`, `seat()`, `model()`, `cacheable()`
  and `keep_out()`.  `SCPlacement` (`setups.py`) gives x, y, z and
  quarter turns.  `SCPlacedWork.work_origin()` is the middle of the
  part's top.
* #25: Settled.  `__version__` in `scraftcnc/__init__.py`.
* #10: Settled.  Everything is placed from the origin the operator
  sets.

Found: the layer constructors take objects and millimeter floats, not
TOML values (#26).  `examples/setup/*.json` overlaps the TOML (#27).

## 2026-11-04: Fourth answers, and five more files read

* #4: Settled, b.  `module:Class.method`, as in entry points.
* #26: The user suspects every class should take strings for lengths
  (`"3mm"`, `"1.2in"`, `".321m"`) and angles (`"12.3 deg"`), with
  spaces optional.  Not sure that fully answers it.
* #27: JSON and TOML are interchangeable the way they are used here,
  so maybe support both: TOML as a `str` or `Sequence[str]`, JSON as
  `dict[str, Any]`.
* #10: Origins are messy.  Two common ones: the fixed vise jaw, and a
  corner of the stock.

Read: `tooling/tools.py` (outline only, 3753 lines), `model_cache.py`,
`examples/setup/demo_stack.json`, `show_demo.py`, `hmi/lcnc_panel.py`
(docstring and outline).  Facts:
* `demo_stack.json` is already in the plate's (work) coordinates
  (`show_demo.py` `SCShow.model_stack()`).
* The panel has no SolidCraft link.  The watcher (`sim_linuxcnc
  --watch`, in the box) draws the tool and path, and `show_demo.py`
  draws the part (`demo.py`) and the stack (`SCSetup`).  Who draws
  the setup from the comments is #28.
* The cache hash is over a JSON shape tree, with `source_digest()` of
  `TOOLING_SOURCES`.  A miss just rebuilds.
* JSON has no parentheses either, and `)` works in it too.

## 2026-11-04: Fifth answers

* #26: Settled, b.  Fields take `str | float`, and each string is
  turned into the right float.
* #27: Settled.  One reader on `dict[str, Any]`, fed by TOML (`str`
  or `Sequence[str]`) or JSON.  The writer puts TOML in the `.nc`.
* #10: Settled.  `[work_zero]` names an item, one of its named points
  (`points()` on each layer class) and an offset.  The HMI moves the
  setup so that point is the operator's G54 zero.
* #28: Settled.  `lcnc_panel` (`lcnc_hmi.py`) gets a SolidCraft
  connection, perhaps headless too.
* #8: `demo.py` read (outline).  This code will change.  Some day
  `lcnc_hmi.py` reads a directory of numbered `.nc` files and works it
  all out; not to be pursued now.  Stay on what goes in the `.nc`.
  The part is `SCPart` plus the function `model()`
  (`demo.py:72`, `demo.py:216`).

## 2026-11-04: Sixth answers; where things stand

* #30: Settled.  The marker is `SCC:` (SolidCraft CNC), e.g.
  `(SCC: [[tooling]])`.
* "#12" (first of two; probably meant for #29 or #8, to confirm): the
  `.nc` must carry all the information it needs, so new code does not
  break existing files.  Incompatible changes to the Python APIs will
  still cause trouble.
* #12: Tools in the spindle belong to a bigger topic, tool
  management.  Deferred.
* #11: Settled, c.  Keep-outs are written outright; each is about 6
  numbers.

Settled so far: #1, #4 (`module:Class.method`), #5/#25
(`__version__` in `scraftcnc/__init__.py`), #6, #10 (`[work_zero]`
item + point + offset, from the operator's origin), #11c, #23 (TOML,
with backslash-u 0028/0029 escapes), #26b, #27, #28 (the panel connects
to SolidCraft, perhaps headless), #30.

Next round, still open: #8 (also allow `module:function`?), #29 (the
header skeleton: `version`, `[setup]`, `[[tooling]]`, `[[stock]]`,
`[[part]]`, `[work_zero]`, `[[tools]]`; each item has `call`,
`location`, `height`, `orientation` plus its own arguments), and the
first "#12" answer's meaning.  How does "all the information it needs"
square with `call` naming Python (#4): write every argument out, never
rely on shop lookups?  Then #7, #9, #13-#22 as first asked.  Nothing
has been coded.
