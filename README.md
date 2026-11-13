# `scraftcam`: 3-Axis CNC Milling for SolidCraft

`scraftcam` writes RS-274 G-code for a 3-axis CNC mill from shapes
described in Python, and can show the part and its tool path in
[SolidCraft](https://github.com/tangency-labs/solidcraft), an open
source CAD program.  It drives SolidCraft through its
Python bindings, `scraftcam/pybind/`.

What it does today:

* Outlines in the XY plane made of straight edges whose corners each
  have their own radius (`RoundedPolygon`), each with a range of
  heights, going up (material) or down (a hole), and children that
  start on its surface, such as islands with holes of their own.
* Outside and inside profiles, climb milled, with half circle lead-ins
  and lead-outs, in passes down to depth, and through cuts that go a
  little below the part.
* Pockets, with islands left standing, cleared by rings that step in
  from the walls.
* Entry holes drilled first (canned cycles or pecks), so the end mill
  drops into a hole instead of plunging; or a ramped entry.
* Top edges beveled with a V-bit or rounded over with a corner
  rounding bit.
* A shop described in TOML files (its machines, their tool tables
  and the tools on hand, taken from a real catalog), where every
  number carries its unit (`"1/4 in"`, `"12 in/min"`), so inches and
  millimeters can not be mixed up.  `Shops.md` describes the files.
* A tool path viewer: a self-contained HTML page that plays the path
  back in 3D.

## Status

An early, unofficial project, not affiliated with the SolidCraft
developers.  It is published to see whether other SolidCraft users
want CNC support; comments are welcome in the issues.

**Never run its G-code on a real machine without checking it first**
(in a simulator, and by cutting air).  It has only been checked on
screen.

## Requirements

* Python 3.11 or newer; nothing outside the standard library, except
  for the HMI (`scraftcam/hmi/`), which fetches Qt (`PySide6`, about
  250 MB) from PyPI the first time it starts, and the catalog
  extractor (`scraftcam/catalog/`), which fetches `pdfplumber` and
  `pypdfium2` the first time it opens a PDF (a network connection is
  needed then).  They go into `~/.scraftcam/packages/`, never into
  Python itself, each in a directory of its own (`PySide6` checked
  against the SHA-256 digests in `scraftcam/pins.toml`); `pip` is
  fetched too, since some Pythons (e.g. Ubuntu's) have none.
* `git`, to get the code.
* SolidCraft, only to see the part: its GUI, or `solidcraft-cli` on
  the `PATH` for sessions with no window.  Downloads are on the
  [SolidCraft releases](https://github.com/tangency-labs/solidcraft/releases)
  page.

## Getting It

One repository holds everything: the Python bindings for SolidCraft
(`scraftcam/pybind/`) and the LinuxCNC side (`scraftcam/lcnc/`)
included.  Everything is run from its top directory, with `python3 -m`;
nothing is installed:

```
git clone https://github.com/waynegramlich/scraftcam.git
cd scraftcam
```

## Trying It

`scraftcam/demo.py` makes a notched 4 x 3 inch plate, 1/2 inch
thick, with a hole through it and a pocket around three islands.
Each step below needs a little more than the one before it.

1. The G-code alone (no SolidCraft needed):

   ```
   python3 -m scraftcam.demo > demo.ngc
   ```

   It prints an estimate of the run time (about 12 minutes).

2. The tool path viewer (no SolidCraft needed):

   ```
   python3 -m scraftcam.demo --plot demo.html > demo.ngc
   ```

   Open `demo.html` in a web browser.  Drag to turn the view, play
   the path back, and watch the G-code line by line.

3. The part, modeled in SolidCraft with no window (needs
   `solidcraft-cli` on the `PATH`):

   ```
   python3 -m scraftcam.demo headless > demo.ngc
   ```

   It prints the number of closed profiles it sketched (6).

4. The part and its tool path in the SolidCraft GUI, started first
   with a control port (on Linux, as below; elsewhere, start the
   installed program with `--control 8080`):

   ```
   solidcraft --control 8080 &
   python3 -m scraftcam.demo 8080 > demo.ngc
   ```

   The plate is see-through, so the tool path shows inside it (it
   takes 15 to 35 seconds to build).  The cuts and the rapids are
   separate sketches, which can be hidden one at a time.

5. All of it connected, in one command, on Linux, with LinuxCNC's
   simulator (installed by `python3 -m
   scraftcam.lcnc.install_linuxcnc`) and no other SolidCraft on its
   port:

   ```
   ./show_demo.py
   ```

   It starts LinuxCNC, SolidCraft with the plate in it (on the table,
   vise, parallels and grid plate drawn by the HMI from the program's
   `(SCC: ...)` setup comments), and the HMI, stopped.  Press Start in the HMI, and the tool cuts
   the plate in SolidCraft.  The HMI's Quit button closes everything.

   Keep the mouse pointer out of SolidCraft's window while it runs:
   SolidCraft makes what is under the pointer see-through, so a pointer
   resting over the plate or the vise makes them flicker translucent.
   SolidCraft also opens a series of panels while it builds everything;
   leave them be.

   `./show_demo.py --headless` runs the same thing with no windows
   (a headless SolidCraft session, the HMI drawn offscreen),
   presses Start itself, and prints what was built, with bounding
   boxes.

## The Files

The code is the package `scraftcam/`:

* `gcode.py`: `CNC`, which writes the G-code (profiles, pockets,
  drilling, edge finishing).
* `geometry.py`: outlines (`RoundedPolygon`, `Loop`) and the
  offsets that tool paths are made from.
* `shops.py` (with `Shops.md` and `examples/shop/`): the shop
  description files, their reader (every problem reported at its file
  and line), and the example shop that the demonstration uses.
* `home.py`: `~/.scraftcam/`, where `scraftcam` keeps everything it
  writes for itself (the package is treated as read only); created on
  first use, with a message, and hidden on Windows.
* `packages.py`: fetches optional packages from PyPI into
  `~/.scraftcam/packages/` the first time they are needed.
* `model_cache.py`: keeps models of tools and tooling as STEP files in
  `~/.scraftcam/tool_cache/`, so the second start is much faster.  One
  not used for a week is deleted, and deleting them all is always safe.
* `setups.py` (with `examples/setup/`): a whole setup, read from JSON:
  where each piece of tooling, material and finished part goes.
* `keepout.py`: checks every move of a program against a setup's
  keep-outs, and that rapids stay at `z_safe`.  Run it to check two
  programs in `examples/setup/`: the demonstration plate is clear of
  everything, and the grid plate's long edges deliberately are not.
* `machine.py`: the machine and its tools as the G-code side sees
  them.
* `plot.py` and `plot_template.html`: the tool path viewer, and the
  tool path drawn as SolidCraft sketches.
* `demo.py`: the demonstration above.
* `tooling/`: 3D models of tools and tooling.
  * `tools.py`: tooling (mill tables, drills, a vise, a grid plate)
    and the keep-out regions around them.  Run it to see them in
    SolidCraft.
  * `cutter_models.py`: each cutter in the shop's tools files, with
    its holder.
  * `mount.py`: stacks of tooling and material that hold work on a
    machine, with their keep-out regions.  Run it to see the first
    one.
  * `tool_models.py` (with `Tool_Models.md` and `docs/tool_models/`):
    how to make each model, with its sketch, all written from the
    code.
* `pybind/`: `scraftpybind.py`, the Python bindings for SolidCraft,
  written by `scraftpybind_generate.py`.
* `lcnc/`: LinuxCNC's simulator (`install_linuxcnc.py`), the bridge
  and server that drive it, and the simulations that show it in
  SolidCraft.
* `run.py` and `gui/`: the one GUI for the shop, the designs and the
  machines, being built (`python3 -m scraftcam.run`); see
  `scraftcam/gui/README.md`.
* `hmi/`: the operator's HMI (`lcnc_hmi.py`, in Qt), and its link
  to LinuxCNC with everything else it does but draw
  (`hmi_machine.py`).
* `catalog/`: `catxtract.py`, which pulls titles, text, images and
  tables out of a vendor's PDF catalog into a Markdown file per page
  (`python3 -m scraftcam.catalog.catxtract PDF OUTDIR`), and `pdf.py`,
  the only module that touches the PDF packages.

Beside it, `tests/` holds the tests and `show_demo.py` the
demonstration that connects everything.

* `TASKS/` and `RULES/`: the plans and work log kept with
  [`ai_contexts`](https://github.com/waynegramlich/aicontexts) while
  the code was written with Claude Code.

## Testing

```
python3 -m unittest discover -s tests -t .
```

The tests need no SolidCraft, and no display.  One more suite follows
the whole path, from the demonstration's G-code, through the
headless HMI (`scraftcam/hmi/`) and `serve_linuxcnc`, to a real
LinuxCNC simulator, in about two minutes, when asked (it needs LinuxCNC, from
`python3 -m scraftcam.lcnc.install_linuxcnc`):

```
SCRAFTCAM_LINUXCNC=1 python3 -m unittest -v tests.test_lcnc_end_to_end
```

## License

MIT No Attribution (`LICENSE`).  SolidCraft itself is MIT licensed.
