# `scraftcnc`: 3-Axis CNC Milling for SolidCraft

`scraftcnc` writes RS-274 G-code for a 3-axis CNC mill from shapes
described in Python, and can show the part and its tool path in
[SolidCraft](https://github.com/tangency-labs/solidcraft), an open
source CAD program.  It drives SolidCraft through
[`scraftpybind`](https://github.com/waynegramlich/scraftpybind), its
Python bindings.

What it does today:

* Outlines in the XY plane made of straight edges whose corners each
  have their own radius (`SCRoundedPolygon`), each with a range of
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

* Python 3.11 or newer; nothing outside the standard library.
* `git`, to get the code.
* SolidCraft, only to see the part: its GUI, or `solidcraft-cli` on
  the `PATH` for sessions with no window.  Downloads are on the
  [SolidCraft releases](https://github.com/tangency-labs/solidcraft/releases)
  page.

## Getting It

`scraftcnc` and `scraftpybind` are cloned side by side, into the same
directory, since `scraftcnc/scraftpybind.py` is a symbolic link to
`../scraftpybind/scraftpybind.py`.  `lcnc_panel.py` and its tests also
need `scraftlinuxcnc` beside them (`lcnc_client.py` is a link into it),
a repository that is still private:

```
git clone https://github.com/waynegramlich/scraftpybind.git
git clone https://github.com/waynegramlich/scraftcnc.git
cd scraftcnc
```

On Windows, `git` checks a symbolic link out as a small text file
unless symbolic links are turned on, so install `scraftpybind`
instead (after deleting that text file):

```
del scraftpybind.py
pip install git+https://github.com/waynegramlich/scraftpybind.git
```

## Trying It

`solidcraftcnc_demo.py` makes a notched 4 x 3 inch plate, 1/2 inch
thick, with a hole through it and a pocket around three islands.
Each step below needs a little more than the one before it.

1. The G-code alone (no SolidCraft needed):

   ```
   python3 solidcraftcnc_demo.py > demo.ngc
   ```

   It prints an estimate of the run time (about 19 minutes).

2. The tool path viewer (no SolidCraft needed):

   ```
   python3 solidcraftcnc_demo.py --plot demo.html > demo.ngc
   ```

   Open `demo.html` in a web browser.  Drag to turn the view, play
   the path back, and watch the G-code line by line.

3. The part, modeled in SolidCraft with no window (needs
   `solidcraft-cli` on the `PATH`):

   ```
   python3 solidcraftcnc_demo.py headless > demo.ngc
   ```

   It prints the number of closed profiles it sketched (6).

4. The part and its tool path in the SolidCraft GUI, started first
   with a control port (on Linux, as below; elsewhere, start the
   installed program with `--control 8080`):

   ```
   solidcraft --control 8080 &
   python3 solidcraftcnc_demo.py 8080 > demo.ngc
   ```

   The plate is see-through, so the tool path shows inside it (it
   takes 15 to 35 seconds to build).  The cuts and the rapids are
   separate sketches, which can be hidden one at a time.

5. All of it connected, in one command, on Linux, with LinuxCNC's
   simulator (`../scraftlinuxcnc`) and no other SolidCraft on its port:

   ```
   ./show_demo.py
   ```

   It starts LinuxCNC, SolidCraft with the plate in it (on the table,
   vise, parallels and tooling plate of
   `examples/setup/demo_stack.json`), and the panel, stopped.  Press Start in the panel, and the tool cuts the plate in
   SolidCraft.  The panel's Quit button closes everything.

## The Files

* `solidcraftcnc.py`: `SCCNC`, which writes the G-code (profiles,
  pockets, drilling, edge finishing).
* `scgeometry.py`: outlines (`SCRoundedPolygon`, `SCLoop`) and the offsets
  that tool paths are made from.
* `shops.py`, `Shops.md` and `examples/shop/`: the shop description
  files, their reader (every problem reported at its file and line),
  and the example shop that the demonstration uses.
* `tools.py`: 3D models of tooling (mill tables, drills, a vise, a
  tooling plate) and the keep-out regions around them.  Run it to see
  them in SolidCraft.
* `Tool_Models.md`, `tool_models.py` and `docs/tool_models/`: how to
  make each model, with its sketch, all written from the code.
* `mount.py`: stacks of tooling and material that hold work on a
  machine, with their keep-out regions.  Run it to see the first one.
* `scmodelcache.py`: keeps models of tools and tooling as STEP files in
  `~/.scraftcnc/tool_cache/`, so the second start is much faster.  One
  not used for a week is deleted, and deleting them all is always safe.
* `scsetup.py` and `examples/setup/`: a whole setup, read from JSON:
  where each piece of tooling, material and finished part goes.
* `sckeepout.py`: checks every move of a program against a setup's
  keep-outs, and that rapids stay at `z_safe`.  Run it to check two
  programs in `examples/setup/`: the demonstration plate is clear of
  everything, and the tooling plate's long edges deliberately are not.
* `scmachine.py`: the machine and its tools as the G-code side sees
  them.
* `scplot.py` and `scplot_template.html`: the tool path viewer, and the
  tool path drawn as SolidCraft sketches.
* `solidcraftcnc_demo.py`: the demonstration above.
* `TASKS/` and `RULES/`: the plans and work log kept with
  [`ai_contexts`](https://github.com/waynegramlich/aicontexts) while
  the code was written with Claude Code.

## Testing

```
python3 -m unittest -v
```

The tests need no SolidCraft, and no display.  One more suite follows
the whole path, from the demonstration's G-code, through
`lcnc_panel.py --headless` and `serve_linuxcnc`, to a real LinuxCNC
simulator, in about two minutes, when asked (it needs LinuxCNC, from
`install_linuxcnc` in `scraftlinuxcnc`):

```
SCRAFTCNC_LINUXCNC=1 python3 -m unittest -v test_lcnc_end_to_end
```

## License

MIT No Attribution (`LICENSE`).  SolidCraft itself is MIT licensed.
