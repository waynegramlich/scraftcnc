# 5.3 New Path for Each Tool Change

(Draft by Claude, 2026-11-03, from the user's request; the user's to
revise.)

A new tool path should be created each time the tool is changed, not
one per T number.  In the demo, T1 (the 1/4 in end mill) cuts twice:
the profiles and pocket (program lines 330-483), and, after the
corner rounding pass (T6), the plate's finishing outside profile
(line 591 on).  Since `SCPathRack` keeps one sketch per T number, T1's
last cut shows its whole earlier path too, which looks like the first
path coming back.
