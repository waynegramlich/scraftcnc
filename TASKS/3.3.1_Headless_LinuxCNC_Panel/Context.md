# LLM Agent Context Log

## 2026-11-01: Created

* The user moved `lcnc_panel.py --headless` here from `scraftlinuxcnc`, since the panel
  stays in `scraftcnc`.  Nothing is done yet.
* The aim: tests run the panel with no display, so with no `Xvfb` (225 MB on WSL).  Not
  confirmed: the `linuxcnc` script accepting a `DISPLAY` program with no window.
* The installer in `scraftlinuxcnc` will drop `python3-tk`, the user's decision, so
  `scraftcnc` must install it for the panel, as `demo_linuxcnc.py` does `xvfb`.
* Asked of the user: whether this belongs at 3.3.1 or under `T.il~3.1`.
