# 5.8 Run Several LinuxCNC Simulators at Once

(Draft by Claude, 2026-11-13, from the user's request; the user's to
revise.)

The GUI shows one tab per machine, each with its own controls and a
bar showing the time to its next operator intervention (`T.osiade~5.1.9`
#101, #102).  Testing that needs more than one machine running at
once, so more than one LinuxCNC simulator.

* LinuxCNC uses fixed shared memory and real time keys, so two copies
  on one computer collide; each probably needs a container of its own
  (a second `lcnc` box), with its own `serve_linuxcnc` port.
* `show_demo.py` (or a test) starts N of them, one per machine of the
  example shop, and the GUI connects to each.
* [Stop All] must stop every one of them.
