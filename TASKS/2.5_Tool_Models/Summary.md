# Summary of `T.tm` Tool Models

3D models of tooling in SolidCraft (2026-10-30 to 2026-11-02).  Closed
at the user's word on 2026-11-02, with the items below still undone.
Decided and done:

* `tools.py`: `MillTable` (Tormach's three, from Tormach's drawing,
  which won conflicts with the spec sheets), `KeepOut` with `Prism` and
  `Cylinder` (shown at opacity 0.25), `Vise` with `KURT_D688` (mostly
  estimates; "That looks like a Kurt vise"), `Parallel` (1/2 to 2 in by
  1/8 in), and `SCDoubleEndCountersink` (44 from Shars page 24; the user:
  "They look great").  The radius type is a plain 60 degree cone, and each
  tip has a small flat, since revolves to a point showed errors.
* `sctoolmodel.model_tool()` is the one path for a shop's tool: a plain
  body, its color, flute lines in a 3D sketch, all in one component that
  moves as one.  `SCToolModel`, `model_shop_tools()` and `probe_flutes.py`
  all call it.  No lines on the tips (the user's word).  `show_demo.py`
  ran with them: "It was very good."

Traps found:

* A covered SolidCraft window is slow (about 109 ms a move against 13
  ms).  With no `wmctrl` or `xdotool` here, send `_NET_ACTIVE_WINDOW`
  with `ctypes` and `libX11`; `xwd -root` through Pillow then captures it.
* SolidCraft 0.25.1 has no command to color a sketch line or hide edges.
* Round bodies measure about 1.1 % low in `inspect.center_of_mass`, and
  small revolves lower still, so compare volumes with that in mind.
* Booleans on coned tips fail; extrude the grooved outline, then cut with
  an inverse cone (`SCDrill.model()`).

Not done: `SCDrill.model()` still cuts real grooves and
`SCDoubleEndCountersink` builds its own body; both wait on `T.ctfs~5.1`.
The helix angle (30 degrees) and 2 flutes for drills and countersink ends
are from memory, since the tools files have no helix key.  Why sketch
lines look white here, against the black noted for tool paths, is not
known.  SolidCraft 0.30.1 is out; 0.25.1 is what runs here.
