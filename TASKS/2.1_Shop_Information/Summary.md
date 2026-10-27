# Summary of `T.si` Shop Information

Shops are described in Nested TOML files, read and checked by
`shops.py`, which also writes `Shops.md` from its schema (a test keeps
the two in step).  Decided and done (2026-10-27):

* Files start with `name`, `kind`, `language`, `version`; keys are
  `snake_case`; `"@FILE_NAME"` (same directory) splices another file
  in, read once; unknown keys, loops and wrong kinds are refused.
* Every problem is reported at once as `FILE:LINE: KEY: message`
  (`tomllib` for syntax errors; `_Scanner` finds the line of every
  key, since no TOML library keeps them).
* Measurements carry units, fractions allowed (`"1-1/2 in"`); money in
  any ISO 4217 code; dates are TOML dates.  Choices take any capitals;
  open lists (interfaces, collets, tool materials) take a value ending
  in `!` unchecked.
* Kinds: `shops`, `shop`, `location`, `machine` (with `axis`,
  `machine_table`, `spindle` with `interface`, `controller`,
  `preferences` with `finish_allowance`), `tool_table` (its own file:
  T number 1-99 to tool name, both unique; a tool is in one machine at
  a time), `tools` with `end_mill` (ball, bull nose, roughing),
  `drill`, `chamfer_mill`, `corner_rounding_mill`,
  `double_angle_cutter`.  Tools are bits only (no holders), shared by
  machines, with purchase facts and, for now, `rpm`/`feed`/`plunge`.
* `examples/shop/`: a mill and a 5 x 10 ft router, nine tools from the
  Shars 2026 catalog (`shars_catalog.md`, not in version control,
  maps it).
* `shops.cnc_machine()` builds `SCMachine`; the demo runs from the
  example shop and roughs with T8 before T1 finishes (0.05 in
  allowance); `machine.toml` and `load_machine()` were removed.

Not done here, left to sub-tasks of `T.ds~2`: mounting (work holding),
stock, materials with speeds and feeds, and 3D tool models.
