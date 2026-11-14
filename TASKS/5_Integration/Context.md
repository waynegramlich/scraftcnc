# LLM Agent Context Log

The user expects things to change all over, and missing features to be found as they come.  Work so far is in `T.ctfs~2.5.1`'s log.

## 2026-11-02: Where things stand

The user is writing this task's `Details.md`, and sub-tasks will follow.  Ready to integrate: `SCMachineVise` with `SCJawPlate`, `SCParallel` with optional holes (a set of 1/2 to 1-5/8 in), `SCGridPlate` (chamfers, tooling holes, and kind `grid_plate` in the shop's tooling files), and every cutter kind built from `examples/shop/tools.toml` with holders; all documented in `Tool_Models.md`.  Stock stays blocks of material for a while (`T.sm~2.4` pending).  `T.tm~2.5`, `T.ctfs~2.5.1` and `T.dtm~2.5.2` are suspended, as more tools are coming; vises, jaw plates, parallels and mill tables still have no kinds in the shop files.  `I.phpsa~1` is closed, never reproduced.  The chamfered grid plate takes about 5 minutes to build after any change to `tools.py`, `mount.py` or `scgeometry.py` (cache key), then 1 s from the cache.

## 2026-11-03: One tree (`T.rd~5.1`, closed)

Everything is now one repository, run from its top with `python3 -m`,
nothing installed: the package `scraftcnc/` (`pybind/`, `lcnc/`,
`hmi/`, `tooling/`; no `sc` module prefixes, classes keep `SC`),
`tests/` (`python3 -m unittest discover -s tests -t .`, 519 tests,
coverage 90.5%), `./show_demo.py` at the top.  `mypy.ini` and
`ruff.toml` hold the coding rules' settings.  The old `scraftpybind`
and `scraftlinuxcnc` repositories are archived (`I.amgr~2`).  The CI
workflow `probe_linuxcnc.yml` passes.  Next: `T.npfetc~5.3` (a path per
tool change); SolidCraft's hover translucency is a quirk, documented in
`README.md` (`I.mpgtis~3`).  The LinuxCNC end-to-end suite
(`SCRAFTCNC_LINUXCNC=1`) has not been run since the reorganization.

## 2026-11-04: `T.emsagc~5.2` design questions

Designing the `.nc` comment format, by question rounds with the user;
see `T.emsagc~5.2`'s `Context.md`.  Nothing coded yet.

## 2026-11-04: `T.emsagc~5.2` design done

The `.nc` setup comment design is settled (summary at the end of
`T.emsagc~5.2`'s `Context.md`); coding starts next, in its #39 order.
`T.sm2~5.5` Standard Materials created, Pending.

## 2026-11-04: `T.emsagc~5.2` closed

The `.nc` setup comments work end to end: the panel draws the mount
from them, picks the origin from a list, steps through the items, and
toggles keep-outs; `./show_demo.py --headless` (`T.hlp~3.3.1`, closed)
lets Claude run everything with no window.  Its summary lists what is
left open.  Next candidates: `T.npfetc~5.4` (a path per tool change),
spacers under the part (through cuts), `T.sm2~5.5`.

## 2026-11-05: `T.hs~5.1.5` closed

The HMI work (S1-S14) is done and checked by the user in a GUI run;
see its `Summary.md`.  Next candidates: `T.npfetc~5.4` (a path per
tool change), `T.cmt~5.3` (more tools), `T.sm2~5.5`.

## 2026-11-12: Qt, PyPI, no macOS (`T.osiade~5.1.9`)

The GUI toolkit is now Qt (PySide6), not `tkinter`; `scraftcnc` will
be published on PyPI with a standard-library bootstrap installer into
`~/.scraftcnc/venv/`; macOS is dropped; Linux is Wayland only.  Next:
port the HMI to Qt (`T.hs~5.1.5`, to be reopened).  See `T.osiade~5.1.9`'s
`Context.md`, #18-#63.

## 2026-11-12: `T.hs~5.1.5` closed again: the HMI is Qt

The package is `scraftcam`; the HMI is Qt (`scraftcam/hmi/lcnc_hmi.py`,
with `hmi_machine.py`), headless as offscreen Qt; PySide6 comes from
`packages.require()` (`scraftcam/pins.toml`); no venv (the
`~/.scraftcnc/venv/` plan above is replaced).  Next: `T.osiade~5.1.9`.

## 2026-11-12: `catxtract` in Qt; the GUI's design decided

No `tkinter` code is left (`T.cm~5.1.10`, suspended again).  The
decisions for the one GUI are done for now (`T.osiade~5.1.9`, #1-#89):
the user's shop and designs live in their own version controlled
directories, `~/.scraftcam/` is always deletable, a tree view drives
the panels, no tabs, no [Save].  Next: step 1, the top line.

## 2026-11-12: `T.osiade~5.1.9` S3.4 done

A shop item's panel shows its fields, edited in place
(`scraftcam/gui/fields.py`, `views.Panel`); the user liked it in a
GUI run.  Next: S3.5 (`gui/README.md`).

## 2026-11-13: `T.osiade~5.1.9` steps 3-4 done, step 5 under way

The shop GUI is done (fields, sketches, tooltips, light/dark,
`stock_materials/`/`tool_materials/`, the grid plate's new API and
sketches).  Step 5: the HMI is a panel of the GUI (`./show_demo.py`
starts `scraftcam.run --program`), with machine tabs, a bar to the
next manual tool task, [Stop All] always shown, a minimal form.  New
Pending tasks: `T.cpfj~5.7` (carousel planning for a job),
`T.rslsao~5.8` (several LinuxCNC simulators at once).  Next: the
inside of a machine tab (see `T.osiade~5.1.9`'s `Context.md`).
