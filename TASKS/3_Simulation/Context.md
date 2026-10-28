# LLM Agent Context Log

## 2026-10-28: Split into sub-tasks

* The user: we got side-tracked into replacing LinuxCNC's GUI, which
  is not this project's goal; LinuxCNC was brought up to give us a
  CNC controller to talk to.  The work was split, and this log with
  it:
  * `T.il~3.1` Installing LinuxCNC (the `lcnc` distrobox).
  * `T.tl~3.2` Tracking LinuxCNC (`sim_linuxcnc.py`, the shop mill
    configuration, running the demo's G-code).
  * `T.rlg~3.3` Replace LinuxCNC GUI (the tool and the trace in
    SolidCraft: `ToolRack`, `RevealTrace`, `probe_reveal.py`, the
    SolidCraft timings and the `engine.batch` findings).
