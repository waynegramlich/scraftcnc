# Summary of `T.rlg` Replace LinuxCNC GUI

`sim_solidcraft.py`, a listener of `sim_linuxcnc.py --watch`, shows the tool and its path in SolidCraft: hidden components moved at 20 Hz, and
each tool's path one hidden 3D sketch built by one `engine.batch`, only the current tool's shown.  The user dropped a live trace; color left
out.  SolidCraft refreshes per command and takes one command a frame in the GUI, hence the batch.  A design's first component is grounded;
start with `file.new`, as names repeat in a reused design.  No unit tests for the live display.
