# Summary of `T.hlp` Headless LinuxCNC Panel

The panel runs with no display (`lcnc_hmi.py --headless`: the same
`SCPanel`, with `lcnc_hmi_headless.py` standing in for `tkinter`),
driven through its command port (`press LABEL`, `type LINE`, `show`,
`answer VALUE`); `tests/test_lcnc_end_to_end.py`
(`SCRAFTCNC_LINUXCNC=1`) runs it against a real LinuxCNC simulator.

Reopened 2026-11-04 from `T.emsagc~5.2` (#79), so Claude can run the
whole demonstration and see what it makes: `./show_demo.py
--headless` starts `scraftcnc/pybind/headless_server.py` (one
headless SolidCraft session behind the GUI's control protocol, token
file, one request at a time, `engine.batch` passed to the headless
`batch` tool; `solidcraft-cli` alone has no control port), the
LinuxCNC simulator, the watcher and the headless panel with
`--solidcraft`.  It waits for the setup drawing (`drawing` in the
panel's `show`), presses Start, waits for the end, prints every body
and sketch with its bounding box (from `model.edges`: `document.
inspect`'s `bbox` is in a body's own frame), then Quit.  About 100 s
with the cache warm (the chamfered grid plate takes ~4 minutes after a
key change).  Tests: `tests/test_show_demo.py`.

Found with it: the demo part and the tool path were 2 x 1.5 in apart
(`T.emsagc~5.2` #78); the setup now moves so the G-code's zero is the
plate's lower left top corner.  The headless server serializes
requests, so a clean run does not prove the GUI free of the
panel/watcher interleaving (#77).  Still noticed: the plate is not
centered on the grid plate (overhangs 6.35 mm at -Y), as in
`demo_stack.json`.  Earlier issues kept on hold (`Context.md`): moving
`sim_linuxcnc.py`, tool change height, rebuilding the `lcnc` box.

Related: `T.emsagc~5.2`, `T.mlcp~3.4`, `T.rlg~3.3`.
