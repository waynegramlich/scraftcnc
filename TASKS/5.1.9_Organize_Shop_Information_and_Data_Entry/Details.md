# 5.1.9 Organize Shop Information and Data Entry

Currently, shop information is organized into hierarchical TOML files.  This
is actually a pretty good design.  There are some follow on issues:
* What happens when the end user makes a data entry error into a TOML file
* What happens as additional Tools and Stock templates show up.
* Should the end user be creating these files in the first place?

Since it is relatively easy to create a graphical user interface (GUI) tools
in Python, it seems reasonable to create and manage the TOML files and to
organize them into appropriate sub-directories.  After some thought, it
seems reasonable to have a single GUI that manages the information ***AND***
can drive the LinuxCNC simulation.

A proposed architecture is to have a top level tab selection bar.  The
possible to top level tabs could be:
* [Shop]
  * [Machines]
  * [Tools]
  * [Stock]
  * [Catalogs]
* [Simulator]

We already are generating the documentation file containing vector graphics.
It would be nice to have this image available on the screen when doing data
entry.


