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

## Next

1. The design from the user's points: calculated speeds and feeds
   are defaults; per machine and tool overrides (perhaps in each
   machine's tool table file).
2. A machine power limit (one usable power number per machine,
   set by the owner; power = removal rate x a material's unit
   power, about 0.3 hp per in^3/min aluminum, 1 steel) to slow
   feeds; not yet discussed with the user.
3. Material tables to start from the chip load guide
   (cnc-optimizations.pages.dev), which the user liked.
