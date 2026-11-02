# 4 Implementing Keepout Zones

Check every move of the G-code that `scraftcnc` generates against the
regions the tool must not enter, first to catch bugs in the code that
writes the G-code, and eventually to stop manual moves in the LinuxCNC
panel from crashing into anything.  (Vise crashes happen all the time
and things break.)
