# Summary of `T.rlg` Replace LinuxCNC GUI

The program shown running in SolidCraft instead of LinuxCNC's AXIS
screen (2026-10-27 to 2026-10-28), in `sim_solidcraft.py`, a listener
of `sim_linuxcnc.py` (`T.tl~3.2`).  Decided and done:

* The tools: every tool of the machine modeled from the shop files
  (`sctoolmodel.py`: end mills, drills with their point, chamfer,
  corner rounding and double angle cutters), each a hidden,
  ungrounded component (`ToolRack`); the one in the spindle is
  shown and moved by `occurrence.move` (relative, so the difference
  is sent) at 20 Hz.
* The path: each tool's whole planned path is one hidden 3D sketch,
  built with one `engine.batch` (`probe_batch.py`; about 0.1 s for
  the demo, no sketch mode flash), drawn one tool ahead, and only
  the path of the tool in the spindle is shown (`PathRack`).  The
  user dropped an incremental reveal (`RevealTrace`, 48 s to build)
  and a live trace; color left out (black is fine), so no SolidCraft
  pull request (STEP wire import is blocked by its kernel pause).
* `sim_linuxcnc.py --watch`: sends LinuxCNC nothing and follows what
  `lcnc_panel.py` (`T.mlcp~3.4`) runs, until Ctrl-C; a failed
  listener stops the program.  `solidcraftcnc_demo.py --no-path
  --opaque PORT` models the plate for it.  Two whole demo runs from
  the panel; the user: "It was perfect."
* Findings kept in `Context.md`: SolidCraft's per command refresh
  and one command a frame in the GUI (why 0.20.0's live trace
  collapsed), `engine.batch`, recovery and pid files to clear after
  a kill, a design's first component grounded, duplicate names in a
  reused design (start with `file.new`).

No unit tests for the live display (it needs SolidCraft and
LinuxCNC); `test_sctoolmodel.py` and `test_probe_batch.py` cover the
models and batches.
