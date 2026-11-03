# Summary of `T.msaf` Materials Speeds and Feeds

`examples/shop/materials.toml` and `shops.tool_cutting()` work out each tool's RPM and feeds from the material; a tool's own
`[TOOLS.cutting."MATERIAL"]` wins; drills over 1 in are refused.  End mill chip loads and cobalt's 110 % are guesses.  Left out: chip
thinning, machine power.
