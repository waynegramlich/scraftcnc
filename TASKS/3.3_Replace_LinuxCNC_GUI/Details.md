# 3.3 Replace LinuxCNC GUI

Show the program running in SolidCraft instead of LinuxCNC's AXIS
screen: the tool (its real shape) moving through the part, and the
path traced as it goes.  A side line, not the project's direct goal
(see `T.s2~3`).

## Where It Stands

* The tool models follow LinuxCNC at 20 Hz (`ToolRack`), and the path
  is revealed line by line (`RevealTrace`), built before the run.
* Open questions: building the trace with `engine.batch`; a live
  trace; a pull request to SolidCraft (`defer_refresh` for
  `engine.batch`); see `Context.md`.
