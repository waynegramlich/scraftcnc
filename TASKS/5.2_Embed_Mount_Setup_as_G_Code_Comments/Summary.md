# Summary of `T.emsagc` Embed Mount Setup as G-Code Comments

Done 2026-11-04.  A `.nc` program now carries its whole mount setup,
and the panel (`lcnc_hmi.py`, renamed from `lcnc_panel.py`) draws it
in SolidCraft from those lines alone.

* Format (`scraftcnc/setup_comments.py`): whole-line `(SCC: ...)`
  comments holding TOML (`(`/`)` escaped as backslash-u 0028/0029),
  `version` from `scraftcnc.__version__` (newer only warns), one
  ordered `[[item]]` list: `kind`, `name`, `call` (`module:Class.method`
  or `module:function`), `args` (names and unit strings; a plain number
  is a count, #48), `location` (from the origin handed up by the item
  below, #32), `orientation` (quarter turns counterclockwise, +X to +Y,
  #46/#50), optional `color`, `transparency`, `note`, and `keep_out`
  boxes, one string each (`"x0 y0 z0 x1 y1 z1 in"`).  Files with no
  setup lines run anyway (#17).
* Classes: `scraftcnc/assembly.py` (`SCStock`, `SCItem`, `SCAssembly`,
  `resolve()`); name dictionaries `tooling/registry.py` (keys like
  `kurt_d688`, shown with spaces), filled from one shop by
  `tooling/shop_registries.py` `use_shop()` (shops independent,
  #62-#64); `origin(turns)` on table, vise (model's fixed jaw top),
  parallel (passes through), grid plate, stock; cache key from `call` +
  `args` + source digest (#57); headless fallback warns (#60).
* Drawing: `scraftcnc/setup_view.py` `place()`, `named_origins()`,
  `SCSetupView` (shows only what changed between programs, by set
  difference, #68; stock as a wire outline, #45; keep-outs on a
  toggle).  Panel: `--solidcraft PORT`, `--shop FILE`, a drawing
  thread with Start greyed out and a progress bar, Set Origin picks
  from the setup's origins (`G10 L20 P1`), Next Step walks the items
  with their notes, front perspective view.  `./show_demo.py` only
  starts things; `--headless` (`T.hlp~3.3.1`) runs it all with no
  window and reports every body.
* Demo (`demo.py`): `demo_assembly()`; the G-code's zero is the
  plate's lower left top corner (#78); stock centered on the grid
  plate (#80); `SCGridPlate.named(chamfer=False)` (#83; 10 s instead
  of ~4-1/2 minutes).  Also: finishing passes get full-size leads
  (#86a); through cuts go at least 1 mm below, drills by their point's
  length too.
* Tests: 603, OK (13 skipped), 189 s.

Left open: #69 transparency 0 means "default"; #72 stock outline has
no color; #73 material names differ (`aluminum_6061` vs "6061
aluminum", `T.sm2~5.5`); #74 the Tools window ignores `--shop`; #81
keep-out cylinders not in the `.nc`; #61 parent/child in part
assemblies; #12 spindle tools (tool management); the hole's
full-size finishing lead sweeps its slug at full depth; through cuts
enter the grid plate (spacers needed, forced once keep-out checking
is on); #55 vise dimensions still unchecked against a real vise.

Related: `T.hlp~3.3.1`, `T.sm2~5.5`, `T.ipfds~5.6`, `T.ikz~4`.
