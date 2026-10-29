# Summary of `T.msaf` Materials Speeds and Feeds

Every tool's speeds and feeds are worked out from the material being
cut (2026-10-28).  Decided and done:

* `examples/shop/materials.toml` (kind `materials`, spliced into the
  shop as `materials`): five groups from the user's
  `drill_rules.txt` (HSS surface speed, `feed_factor`), generic and
  particular materials naming their groups, carbide 250 % and cobalt
  110 % (a guess) of HSS's speed, drill feeds per revolution (the
  middle of the catalog ranges, "split the difference"), end mill
  chip loads by diameter (guesses) and a 50 % plunge.  New unit
  kinds `surface_speed`, `feed_per_rev`, `chip_load`; new form
  `by_material`.
* `shops.tool_cutting()`: RPM = 12 SFM / (pi D) at the widest
  diameter, held to the spindle; feed = RPM x (feed per revolution,
  or chip load x flutes) x `feed_factor`; a feed or plunge past the
  axes' `max_feed` scales RPM, feed and plunge down together.  A
  tool's own `[TOOLS.cutting."MATERIAL"]` (`rpm`, `feed`, `plunge`)
  wins; a tool material with no data needs one.  Drills over 1 in
  are refused (not worth handling).  No tool keeps `rpm`/`feed`/
  `plunge`; `peck` is `peck_depth`.
* `cnc_machine(shop, name, material)`; demo `--material` (default
  6061 aluminum), about 9.9 minutes (was 19); `SCCNC` takes the job's
  `job_z_safe` and `job_clearance` (the other preferences stay with
  the machine).  `lcnc_panel.py`'s Tools window lists the speeds and
  feeds for a chosen material.  Arc feeds for the cutting edge
  (`SCCNC.arc(edge=True)`) came first.

Left out: chip thinning, the machine's power limit (seldom known).
A display bug seen in the run is noted in `T.s~3`.
