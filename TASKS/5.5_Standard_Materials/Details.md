# 5.5 Standard Materials

(Draft by Claude, 2026-11-04, from `T.emsagc~5.2` #35; the user's to
revise.)

* A standard list of materials ships with `scraftcnc`.  A shop may
  define its own; when it does not, the standard list is used.
* Each material has a short name (e.g. `aluminum_6061`), a display
  name, a default color, and later its cutting data (`T.ds~2` section
  7), for speeds and feeds.
* A starting list: 6061 and 7075 aluminum, 1018 mild steel, 303/304
  stainless, 360 brass, acetal (Delrin), HDPE, acrylic, MDF, hardwood.
* `.nc` setup comments and model cache keys hold the short name only.
