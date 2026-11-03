# LLM Agent Context Log

## 2026-11-02: Squeezed; where things stand

Done: tools have `unique_id` and `holder`; `./sctoolmodel.py 8080` shows the shop's 12 tools in holders (the user: "That is great");
models are cached (below).  Next: tables, vises, parallels, tooling plates and countersinks need kinds in the shop files; then
countersinks and `SCDrill` come under `model_tool()`, and the grooved drill can go.  Tool changers, with a mapping of their own, come
later; the user will revisit holders.  `examples/shop/` keeps its names (no `example_shop.toml`).

### `unique_id` and `holder`

* `unique_id`: required, a positive integer, unique among all tools, not a T number; gaps allowed.  `tools.toml` has 12, not in order.
* `holder`: an optional list, a chain such as `["tormach", "er16", "7/16 in"]`; each entry but the last known or ending in `!`, the last a
  length.  No cross checks (the user: "If the user screws up, well too bad").  It stays on the tool, as a tool is in one machine at a time,
  and moves to the tool table when gauge lengths arrive (Claude's decision).
* Research, unverified: ER largest bores 5, 7, 10, 13, 16, 20, 26, 34 mm, so the example's 7/16 in in ER16 would not really fit.
* A bare `"1/2"` is reported as `'/2' is the wrong unit`, a confusing message from `measurement_problem()`; left alone.

### Holder models

The user: a very rough truncated cone, N bands for the most digits in the shop's `unique_id`s, each one digit in the resistor color code,
first digit at the base; kind ignored.  Claude's sizes: 2-1/2 in long, base 1-3/4 in, tool end the bore plus 1/2 in, a third of the bit
inside, `HOLDER_OPACITY` 0.4.  `view.navigate` needs a `camera` Claude could not name, so the view is not fitted.

### `scmodelcache.py`, a STEP cache

The user: `~/.scraftcnc/tool_cache/MODEL_NAME__HASH.step` (16 hex digits); the vise is two files, the vise and what moves; a reused file is
touched, one over a week old is deleted; the hash has only what affects the shape, not color; lines are redrawn; user objects are to come,
given a unique JSON tree of their arguments, which `SCCacheable.shape` already takes.

* A missing file is built in its own `solidcraft-cli` session (allowing the cache directory) if on the `PATH`, else in the design's session
  and removed, changing units then.  Any cache failure prints a message, stops it for the run, and the caller builds.
* Claude's choices: tools and holder bands hash their `profile()` points; tooling hashes its dataclass plus a digest of `tools.py`, `mount.py`
  and `scgeometry.py`, as touching means nothing else notices stale code.  Tests use `tempfile` or no cache.  Raw material and headless
  designs are not cached.
* `show_demo.py` to Ready: 33.9 s before headless building, 17.2 s with it and an empty cache, 13.1 s with a full one (the user saw about 13):
  plate 6.0 s (the slowest now, not cached), stack 0.9 s, tools and paths 1.8 s.  Tools gain little (12 in the GUI, 1.99 to 1.70 s).  The
  watcher is in the `lcnc` box, with no usable `solidcraft-cli`, so tools build in the GUI.
* The user ran it with Start: "That ran smoothly."  Whole suite: 415 tests, 10 skipped (`test_lcnc_end_to_end` not run).  It prints 644
  bytes, so it is not what uses tokens.

### SolidCraft 0.25.1 findings

* `document.units` takes 4.5 s with the demonstration plate in the design, most of the stack's time, so it is changed only to build.
* `file.insert_step`'s `matrix` is in millimeters whatever the design's units.  Inserts take 30 to 60 ms (500 ms for the tooling plate).
* An inserted STEP has no color in a new session, though the file has `COLOUR_RGB`; in the session that made it a color comes back by body
  name, which misleads.  Colors are given after every insert.
* Headless reads and writes only in `allow_paths` (default the working directory); the GUI has no such limit.
* Center of mass differs by up to 0.006 mm between a built body with round faces and its STEP.
* `body.rename` works on inserted bodies; a taken name gets ` (2)`.  `solid.remove` keeps the features.
* Killing a GUI leaves recovery files that bring up a "Recover unsaved design?" dialog in the next: remove them by PID.

## 2026-11-02

The vise is now `SCMachineVise` with an `SCJawPlate`; setup files name it with kind `machine_vise`.  Neither has a kind in the shop files yet.
