# 3 Simulation

Run the G-code in a LinuxCNC simulator and show the tool moving
through the part in SolidCraft.  The proposed steps:

1. Verify that an object (e.g. a tool model) can be moved
   programmatically in SolidCraft.
2. Install `linuxcnc-uspace`, the non-realtime simulator for
   LinuxCNC.  It is only easily installed on Ubuntu Linux.  Thus,
   the simulator will be runnable on a Ubuntu Linux machine.
3. See what it takes to control LinuxCNC from Python and to poll it
   for the current position.
4. Bolt it all together to run the simulation.
