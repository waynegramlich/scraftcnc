# Summary of `T.rcts` Rename Classes to SC

All 44 classes start with `SC`, for `scraftcnc`'s `T.ikz~4` (2026-11-01), renamed together with
`scraftcnc`, which links to this file.  `SolidCraftPyBind` is `SCPyBind`, `SolidCraftError` is
`SCSolidCraftError`; the transports, `SCNamespace` and `SC...Commands` (from the generator) just
gained the prefix, as did the test helpers (test classes keep `unittest`'s `Test` prefix).  The 118
type aliases are not classes and stayed.  No old names are kept as aliases; `__version__` went to
0.2.0.  The cached command list was used, so no new commands came in.
