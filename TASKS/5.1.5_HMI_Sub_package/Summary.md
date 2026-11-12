# Summary of `T.hs` HMI Sub-package

Done 2026-11-05 in fourteen steps, all in this task (no sub-tasks).
The three processes stay (the HMI, `lcnc_bridge.py`,
`serve_linuxcnc.py`).  S1 (trace baseline) was dropped.  S2 dropped
the `SC` class prefix, and "panel" became "HMI" (later
`show_demo.py`'s `--panel-port` became `--port`).  S3 gave the HMI
four tabs (Run, Setup, Tools, View).  S4 takes the shop, machine
and origin from the setup comments, refuses other machines, and
greys out Start until an origin is set.  S5 added the tool change
pause (`MSG` + `M0`).  S6 shows the next tool and the time left to
it.  S7 sets the origin axis by axis.  S8 and S12 check jogs and
typed MDI lines (axis-only lines included; G28, G30 and G53 refused)
against the keep-outs.  S9 added the View toggles (keep-outs, stock,
origin, holders).  S10 and S11 added the tool carousel (slot plan,
swap prompts, drawn in SolidCraft).  S13 put holders (at least two
bands) on the simulated tools.  S14 made the keep-outs red
translucent boxes.  The user checked it all in a GUI run of
`./show_demo.py`.  Not done: the toggles do not cover flute lines
(the user's choice).  Related: `T.cmt~5.3` (setup tools: edge finder,
center finder, tool setter), `T.npfetc~5.4`, `T.sm2~5.5`.

Reopened and done again 2026-11-12: the HMI was ported from `tkinter`
to Qt (`PySide6`), in five steps, as `T.osiade~5.1.9` chose (#21).
S1 renamed the package `scraftcnc` to `scraftcam` (and
`~/.scraftcnc/` to `~/.scraftcam/`).  S2 needed no venv: each fetched
package gets its own directory, `~/.scraftcam/packages/<tag>/<module>/`,
swapped in whole so versions never mix, from `scraftcam/pins.toml`
(PySide6 pinned by SHA-256), with a `current` link that `mypy.ini`
and `.pylintrc` use.  S3 wrote the Qt HMI (a `QWidget`, same tabs,
buttons and port; headless is offscreen Qt), S4 moved the HMI tests
onto it, and S5 switched `show_demo.py` and the end-to-end suite to
it (which also fixed the suite counting earlier tests' messages),
then deleted the `tkinter` HMI and `lcnc_hmi_headless.py`.  Now
`scraftcam/hmi/lcnc_hmi.py` is the Qt HMI and `hmi_machine.py` the
part with no toolkit.  The user checked a GUI run of `./show_demo.py`.
Not done: `catxtract.py` still has a `tkinter` window, left for
`T.osiade~5.1.9`, where the HMI becomes a tab of the larger GUI.
Related: `T.osiade~5.1.9`.
