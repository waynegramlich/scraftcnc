# 2.3 Mounting

Mounting is the process of attaching one or more parts and associated
to a machine via mounting hardware (e.g. a vice, toe clamps, etc.)
It can be an iterative process in that sometimes the parts need to be
reoriented several times before the part is finished.

In addition, the parts do not all need to be the same, since a CNC machine
is perfectly capable of working on several different parts at the same time.
Thus, having the ability to merge several G-code files into one G-code file
that use the same tool and a single shared machine origin is desirable.

Most CNC machines have a milling table that consists of T-slots that
can be used to bolt down a vice or some another specialized fixture.
Sometimes a part is bolted directly to the table with some sacrificial
material and the part is held down with a variety clamps (e.g. hold-down,
step clamps, toe clamps, etc.)

The key thing about mounts is that there are 3d regions that the tool bit
must not be allowed to enter.  These safety checks are part of the mounting
process.  The unsafe regions are represented by cuboids (i.e. a rectangular
prism) and should be checked prior to executing the CNC program.

Another aspect of mounting is that sometimes the original material is not
flat (i.e a rod, tube, or some previously manufactured part that needs
further machining.)

It is extremely useful if the mounting steps can be documented visually
to make it easier for the machine operators to properly mount the object
to be machined to the actual CNC machine.

