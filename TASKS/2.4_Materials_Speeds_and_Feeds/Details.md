# 2.4 Materials Speeds and Feeds

Cutting data (draft by Claude, 2026-10-27; the user's to revise).

* Per material (6061 aluminum, mild steel, brass, acrylic, wood, ...):
  surface speed and chip load by tool material and diameter; RPM =
  surface speed / (pi x diameter), feed = RPM x flutes x chip load,
  limited by the spindle and the axes.
* Replaces the per tool `rpm`, `feed` and `plunge` in the tools files
  (kept as per tool overrides).
* Also decides where the machine `preferences` belong (shop, machine
  or job).
