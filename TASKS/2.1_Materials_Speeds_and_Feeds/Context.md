# LLM Agent Context Log

## 2026-10-28: First research (3 minutes, two web searches)

* Formulas (inch): RPM = SFM x 3.82 / D (= 12 SFM / (pi D));
  feed IPM = RPM x flutes x IPT (chip load per tooth).  Metric:
  RPM = 1000 Vc / (pi D), Vc in m/min, D in mm.
* Radial chip thinning: below 50% width of cut the real chip is
  thinner than the programmed IPT; multiply IPT by
  1 / sqrt(1 - (1 - 2 WOC / D)^2) (about 1.67 at 10% WOC).
* Chip load scales roughly with diameter (a 1/4 in tool takes about
  half the IPT of a 1/2 in one), so tables are by material group x
  tool diameter (Harvey Tool: .0005 to .008 in/tooth).
* Carbide end mill ranges (Amana): aluminum 600-1200 SFM, medium
  carbon steel 175-350 SFM, both about .001-.002 in/tooth at
  1/4-1/2 in.  Others: aluminum 500-1500, mild steel 200-600,
  stainless 100-350 SFM.  HSS is far slower (e.g. about 35 SFM for
  carbon steel drilling, U. of Toronto drill press notes).
* Drills feed per revolution, not per tooth: HSS 1/4-1/2 in about
  .004-.010 in/rev, 1/2-1 in .007-.015 (Toronto); carbide 3/8 in in
  non-alloy steel .0075-.0106 in/rev (Haas/YG-1, which also advise
  20% less speed and 10% less feed as a start).
* Every source: these are starting points; the tool maker's chart
  for that tool and coating wins, which fits keeping per tool
  overrides.  A hobby mill's rigidity and spindle top RPM will cap
  most of these (the spindle and axis limits in the shop files).
* Sources: harveytool.com/resources/general-machining-guidelines,
  Amana's spiral end mill and SCFD drill charts, Haas carbide drill
  PDFs, mie.utoronto.ca MODULE-1-The-Drill-Press.pdf.

## 2026-10-28: The user's view

* Catalog tools (Shars: "Made in USA", "Made in China") come with no
  chart; the machine's power sets the chip load it can take, and its
  power curve is seldom known (the home mill's falls off under
  load).  Arcs need a feed change (the center feed lower on an
  inside arc, higher on an outside one) to keep the chip load.  The
  chip load guide (cnc-optimizations) is a good place to start.
* Decision: calculated speeds and feeds are only defaults; every
  machine and tool pair must be able to override them.

## 2026-10-28: Arc feeds for the cutting edge (done)

* `SCCNC.arc(..., edge=True)` (`solidcraftcnc.py`) scales the feed by
  R_center / R_edge so the cutting edge, not the center, moves at the
  tool's feed (climb milling, clockwise spindle, material on the
  right): `G2` (right turn) R_edge = R - r, feed up; `G3` (left)
  R_edge = R + r, feed down.  RPM unchanged.  Clamped to
  `ARC_FEED_MIN` 0.25 and `ARC_FEED_MAX` 2.0.
* Used by every arc in `_follow()`: walls, pocket rings and the
  profile lead-in/lead-out half circles (which turn left, so they now
  run at half feed; the user may want them at full feed).  Not the
  helical ramp arcs.  Chamfer and corner rounding bits use their tip
  diameter, an approximation.
* `test_arc_edge_feed` added; `test_profile_outside` and
  `test_through` updated for the new feeds.  116 tests pass,
  checkers clean, demo about 19.4 minutes.  Not yet looked at in the
  viewer or the simulator.

## 2026-10-28: Drill (tool) materials

* The user's search, "drills - what are the more common material to
  make drill bits for drilling metal out of": tool material and
  finish both matter for speeds and feeds; keep to the 4 materials
  that search listed, for now.
* Claude's same search found HSS (the default: mild steel, cast iron,
  non-ferrous), cobalt (HSS-Co, M35/M42: stainless, titanium) and
  carbide (hardest, brittle), plus coatings: TiN (often sold as
  "titanium" bits; a coating on HSS or cobalt, not a material) and
  black oxide.  The sources were weak (mostly scraped pages).
* `shops.MATERIALS` already has HSS, cobalt, carbide (and cermet,
  ceramic, CBN, PCD; open list); `coating` is a free string (the
  example tools use uncoated, black oxide, straw).
* Asked the user which is the fourth (TiN coated as a material, or
  something else), and whether `coating` becomes a choice.
* The user: the search links were mostly advertisements and are not
  to be kept; the user's temporary `drill_rules.txt` (project
  directory) is the source for now.  It gives HSS SFM by workpiece
  group (aluminum/brass/acetal 250, mild steel/soft cast iron 100,
  medium/hard cast iron 80, tool/alloy steel 40, stainless/titanium/
  hardened 20), carbide about 2.5x HSS, cobalt for work hardening
  materials, and RPM = 12 SFM / (pi D), IPM = RPM x IPR.

## 2026-10-28: The user's answers on drills

* Cobalt: no data, so it is left out for now.  Carbide: 2.5x HSS for
  every group, the best there is (titanium is trouble anyway).
  Coatings: skipped for now.
* The five rows of `drill_rules.txt` become the groups of materials
  being cut, and each workpiece material (6061 aluminum, brass, ...)
  names its group.
* `drill_rules.txt` now gives IPR: a rule of thumb, .001 in/rev per
  1/16 in of diameter (IPR = .016 D x a material factor, adjusted for
  hardness and depth), and catalog ranges (under 1/8 in .001-.003,
  1/8-1/4 .002-.006, 1/4-1/2 .004-.010, 1/2-1 .007-.015 in/rev).
  The material factors are not given.
* The user: precise speeds and feeds are very hard to come by; these
  are starting points.

## 2026-10-28: Drill design, the user's answers

* Material factors (Claude's guesses, no source): aluminum/brass/
  acetal 1.5, mild steel/soft cast iron 1.0, medium/hard cast iron
  0.8, tool/alloy steel 0.7, stainless/titanium/hardened 0.5.
* Depth adjustment skipped for now.  Drills only; end mills get the
  same treatment later.
* Per tool overrides in the tools file, under each drill, as
  `[drills.cutting."MATERIAL"]` with `rpm` and `feed`, imperial or
  metric units.
* `plunge` should be `peck_depth` for drills.
* RPM is clamped to the spindle's range, and the feed comes from the
  RPM actually used (feed = IPR x actual RPM).
* The user names the material; the shop declares the materials it
  supports, with suggestions to start from (the list: 6061 aluminum,
  brass, acetal, 1018 mild steel, soft cast iron, medium cast iron,
  4140 alloy steel, O1 tool steel, 304 stainless, titanium).
* Surface speed units: `sfm`, `ft/min` and `m/min`, interchangeable.
* The user: it keeps getting messier, and a wrong guess breaks a bit.

## 2026-10-28: Last answers (numbered 11-16 by the user, read in
## order as Claude's 11, 16, 17, 22, 23, 24)

* 11: an IPR outside the catalog range is no guess: refuse, asking
  for a (speed, feed) for that (tool, material) pair.
* 16, 17 ("see #11"): no plain `rpm`/`feed` fallback; a cobalt drill
  (no data) needs its pairs given.
* 22: `materials.toml` with the groups and the shop's materials.
* 23: an unknown material is an error listing the shop's materials.
* 24: no safety margin ("breaking bits is part of the joy of CNC").
* The user: the questions are getting hard to answer; ask fewer.

## Next (drill plan, agreed 2026-10-28; nothing built yet)

1. A `surface_speed` unit kind in `shops.py`: `sfm`, `ft/min`,
   `m/min`, interchangeable.
2. `materials.toml` (kind `materials`): the five groups (HSS SFM,
   feed factor), carbide factor 2.5, catalog IPR ranges, the ten
   starting materials naming their groups; `shop.toml` has
   `materials = "@materials.toml"`.
3. Drills: `[drills.cutting."MATERIAL"]` with `rpm` and `feed`;
   `peck` becomes `peck_depth`; drop `rpm`, `feed`, `plunge`.
4. Calculation: RPM = 12 SFM / (pi D), clamped to the spindle; IPR =
   .016 D x factor, refused outside the catalog range; feed = IPR x
   actual RPM.  No guess (cobalt, out of range): error asking for the
   (tool, material) pair.
5. Job material: an `SCCNC` argument and demo `--material` (default
   6061 aluminum); the demo's cobalt drill gets a `cutting` entry.
6. `Shops.md` regenerated, tests, checkers.
7. Later: end mills; the machine power limit; the chip load guide
   (cnc-optimizations.pages.dev).

## 2026-10-28: Design drafted (5 minute cap, nothing wired in)

* `examples/shop/materials.toml`: draft data (kind `materials`):
  `[drilling]` (`ipr_per_diameter` .016, `carbide_speed_factor` 2.5,
  `ipr_ranges` with `below` and a [min, max] `ipr`), five `groups`
  (`hss_surface_speed`, `feed_factor`), ten `materials` naming a
  group.  Not yet in `KINDS` nor spliced into `home_shop.toml`.
* Open unit questions: `in/rev` and `in/rev/in` are new unit kinds
  besides `surface_speed`; `[min, max]` lists may need a schema type.
* Drill entry in `tools.toml` (to do): drop `rpm`/`feed`/`plunge`,
  add `peck_depth`, optional `[drills.cutting."MATERIAL"]` with
  `rpm`, `feed`.
* Lookup (to do, in `shops.py`): `drill_cutting(tool, material,
  spindle) -> (rpm, feed)`: override first; else HSS/carbide group
  SFM -> RPM = 12 SFM / (pi D) clamped to spindle; IPR = .016 D x
  factor, error if outside the range for D; feed = IPR x RPM.
  Cobalt (or anything else) with no override: error naming the pair.
* Units settled: `ipr_per_diameter` is a plain number (.001 in/rev
  per 1/16 in: the inches cancel).  `shops.py` gained unit kinds
  `surface_speed` (`sfm`, `ft/min`, `m/min`; inside ft/min) and
  `feed_per_rev` (`in/rev`, `ipr`, `mm/rev`); `Shops.md` regenerated;
  116 tests pass, checkers clean.  Next: the `materials` kind in
  `KINDS` (a [min, max] range form still undecided).
* The user: "split the difference" (bits breaking is part of the
  joy).  Read as: no .016 D rule and no refusal; drill feed = middle
  of the catalog range for its diameter x the group's `feed_factor`.
  `shops.py` now has kinds `materials`, `drilling`, `feed_range`
  (`below`, `feed`), `material_group`, `material`; factors are
  `fraction`s (`"150 %"`).  `materials.toml` reads cleanly; not yet
  spliced into `home_shop.toml`.  Next: plan steps 3-6 (drill
  `cutting` overrides, `peck_depth`, the lookup, `--material`).

## 2026-10-28: Drill speeds and feeds wired in

* `materials.toml` spliced into `home_shop.toml` and `shops.toml`
  (shop key `materials`); generic materials added (aluminum, copper,
  plastic, hdpe, acrylic, wood: soft; steel: mild; cast iron: cast;
  stainless steel: hard) before the particular alloys.
* `shops.drill_cutting(shop, machine, drill, material)`: RPM = 12
  SFM / (pi D) (carbide x 2.5), clamped to the spindle; feed = range
  midpoint x `feed_factor` x RPM; `plunge` = feed.  An unknown
  material lists the shop's.  `cnc_machine(shop, name, material)`
  uses it for HSS and carbide drills only (`DRILLED`); the cobalt
  drill keeps its own `rpm`/`feed` until `cutting` overrides (#3a).
* Demo `--material NAME` (default 6061 aluminum): T4 15/64 HSS gets
  4074 rpm, 24.4 in/min; steel 1630 rpm, 6.5 in/min.  116 tests pass
  (a line number in `test_shops.py` updated), checkers clean.  No
  test of `drill_cutting()` yet.
