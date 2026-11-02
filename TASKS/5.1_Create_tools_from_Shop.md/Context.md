# LLM Agent Context Log

## 2026-11-02: `id_number` and `holder`

* The user: `examples/shop/` stays as it is (`home_shop.toml` keeps its name, no
  `example_shop.toml`).  Every tool has an `id_number`, a positive integer, from 1.  A
  `holder` key takes `tormach`, `cat40`, `cat50`, `bt30`, `bt40`, `bt50`, `sk40`, `sk50`,
  `hsk-a63`, `hsk-a100`, or another ending in `!`.
* `shops.py`: the form `positive_integer`, `HOLDERS`, `_SCReader.number_tool()`.  Claude's
  choices: `id_number` is required and unique among all tools, is not a T number, and gaps
  are allowed (only the example is checked to have none); `holder` is optional and no
  example tool has one yet, since the mill's `interface` is `R8`, which is not on the list.
* `tools.toml` numbered 1 to 9, in file order.

## 2026-11-02: `holder` is a list; `collet` is gone

* The user: a holder is a chain, such as `["tormach", "er16", "7/16"]`; a Tormach TTS holder goes in
  an R8 3/4 in collet, with fixed bores or ER16, ER20, ER32 holders.  No cross checks for now (a bore
  against a tool's shank or a collet's range, a holder against a spindle): "If the user screws up, well
  too bad".  The user left to Claude where `holder` belongs.
* Claude's decision: it stays on the tool, as a tool is in one machine at a time.  It moves to the tool
  table when gauge lengths arrive, as tool table entries are only names today.
* `shops.py`: form `holder_list`, `HOLDER_PART`, `_holder_problem()`, `HOLDERS` (the user's, `r8`, `5c`,
  the ER collets, `drill-chuck`, `shell-mill`); `COLLETS` and `collet` removed.  Each entry but the last
  must be known or end in `!`, in any order; the last must be a length; at least two entries.  `holder`
  is optional, so a drill no longer must say what holds it.  `Shops.md` has a Tool Holders section.
* The example tools' holders are Claude's reading of the old comments; 15/64 in drill in a 1/4 in ER32.
* Research (3 minutes, vendors and forums, no standards read): ER largest bores 5, 7, 10, 13, 16, 20, 26,
  34 mm (ER16's 3/8 in is also Tormach's own figure, so `["tormach", "er16", "7/16 in"]` will not really
  fit, and the reader takes it).  No usable R8 or 5C ranges found.  TTS 3/4 in and ER32 details are from
  user reports, not a Tormach specification.
* A bare `"1/2"` is reported as `'/2' is the wrong unit`, a confusing message from `measurement_problem()`
  that predates this; left alone.

## 2026-11-02: Holders as truncated cones, in the resistor color code

* The user: a very rough holder, a truncated cone from base to tool end, sliced into N bands, N being the
  most digits in the shop's tool numbers, each band one digit in the resistor color code.  Not realism.
* `sctoolmodel.py` (now directly executable): `RESISTOR_COLORS`, `shop_tools()`, `id_digits()`,
  `holder_bands()`, `model_holder()`, `model_shop_tools()`, `main()`; `model()` takes `at`.
  `./sctoolmodel.py 8080` shows all tools in a row along X.
* Claude's choices: the id is the tool's `id_number`; leading zeros (1 of 12 is black, brown); first digit
  at the base; every holder 2-1/2 in long, base 1-3/4 in across, tool end the bore plus 1/2 in; a third of
  the bit's length inside the holder; bits drawn too; holder size ignores the holder's kind.
* `tools.toml`: three more from Shars page 54, ids 10 to 12, in no tool table, so that the shop needs two
  digits; the tools now run 1 to 12 and are not in `id_number` order in the file.
* Checked: 36 bodies; `appearance.list` reads the colors back right; `TestModel` (headless) passes with
  `model()`'s new plane.  Screen capture shows the shapes, but `xwd`'s stripes hide most colors.  The user's
  eye decides.  Left running on port 8080 for the user.

## 2026-11-02: `unique_id`; translucent holders

* The user: "unique id" is the term for all tools in the shop, and the color code uses it, so `id_number` is
  now `unique_id` everywhere in code (older entries here keep the old name).  First digit at the base (top
  down, hundreds to ones) stands.  Holder kind is ignored in the model.  Tool changers come later, with a
  mapping of their own; tool tables stay as they are until then.
* `HOLDER_OPACITY` 0.4.  Seen in a capture: the tool shows through its holder; `appearance.list` reads 0.4.
* `view.navigate` needs a `camera` that Claude could not name, so the view is not fitted by the program.

## 2026-11-02: Where things stand; saved for the user's commit and a `/clear`

The user: "That is great."  Done: every tool has a `unique_id`; `holder` is a list, with no cross checks (the
user's word); `collet` is gone; `./sctoolmodel.py 8080` shows the shop's 12 tools in translucent holders, in the
resistor color code, in SolidCraft (`solidcraft/solidcraft-linux-x86_64.AppImage --control 8080` first).

Next, as this task's title has it: the other things in the shop that are used for setup (tables, vises,
parallels, tooling plates, countersinks) are still only in Python (`tools.py`), and need kinds in the shop files.
Not started.  The user expects missing features to turn up all over.  Tool changers, with a mapping of their own,
come later; the holder topic will be revisited eventually.

## 2026-11-02: Flutes as lines

`T.tm~2.5` made flutes lines on a plain body, in one component, by `sctoolmodel.model_tool()`.  Next here is unchanged: tables, vises, parallels, tooling
plates and countersinks need kinds in the shop files.  Countersinks and `SCDrill` then come under `model_tool()`, and the grooved drill can go.
