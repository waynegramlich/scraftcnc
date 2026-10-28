# 3 Simulation

Run our G-code on a real CNC controller, LinuxCNC's simulator, so
that `scraftcnc` has a controller to talk to.  Replacing LinuxCNC's
own GUI is not the goal; it got its own sub-task after the work
drifted that way.

## Sub-Tasks

1. `T.il~3.1` Installing LinuxCNC: `linuxcnc-uspace` in a Debian
   Trixie `distrobox` on Ubuntu.
2. `T.tl~3.2` Tracking LinuxCNC: driving it from Python (load a
   program, set the work origin, the tool table, run it) and polling
   where the tool is and which G-code line it is on.
3. `T.rlg~3.3` Replace LinuxCNC GUI: the tool and its path shown in
   SolidCraft as the program runs.

## Done When

* The sub-tasks are closed or deliberately deferred.
