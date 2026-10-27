# `scraftcnc`: 3-Axis CNC Milling for SolidCraft

`scraftcnc` writes RS-274 G-code for a 3-axis CNC mill from shapes
described in Python, and can show the part and its tool path in
[SolidCraft](https://github.com/tangency-labs/solidcraft), an open
source CAD program.  It drives SolidCraft through
[`scraftpybind`](https://github.com/waynegramlich/scraftpybind), its
Python bindings.

What it does today:

* Outlines in the XY plane made of straight edges whose corners each
  have their own radius (`SCRoundPoly`).
* Outside and inside profiles, climb milled, with half circle lead-ins
  and lead-outs, in passes down to depth, and through cuts that go a
  little below the part.
* Pockets, with islands left standing, cleared by rings that step in
  from the walls.
* Entry holes drilled first (canned cycles or pecks), so the end mill
  drops into a hole instead of plunging; or a ramped entry.
* Top edges beveled with a V-bit or rounded over with a corner
  rounding bit.
* A machine and tool table in `machine.toml`, where every number
  carries its unit (`"0.25 in"`, `"12 in/min"`), so inches and
  millimeters can not be mixed up.
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
`../scraftpybind/scraftpybind.py`:

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

## The Files

* `solidcraftcnc.py`: `SCCNC`, which writes the G-code (profiles,
  pockets, drilling, edge finishing).
* `scgeometry.py`: outlines (`SCRoundPoly`, `SCLoop`) and the offsets
  that tool paths are made from.
* `scmachine.py` and `machine.toml`: the machine, its preferences and
  its tools.
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

The tests need no SolidCraft.

## License

MIT No Attribution (`LICENSE`).  SolidCraft itself is MIT licensed.
