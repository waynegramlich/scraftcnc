# LLM Agent Context Log

## 2026-11-03: First look (code only, nothing run)

* `show_demo.py` models the plate with `python3 -m scraftcnc.demo
  --no-path --opaque PORT` (`model_part()`), so it starts solid
  (`demo.py`: `opacity=1.0 if opaque else 0.35`).
* No transparency code changed in the reorganization: `git diff -M
  4c6e358 HEAD` of `setups`, `demo` and `show_demo` has no opacity,
  color or material lines.  The demo's G-code is byte-identical.
* Suspect: `model_stack()` comes after `model_part()`, and the stack
  (`examples/setup/demo_stack.json`) includes the raw material, drawn
  as a translucent white box (`setups.py`: `RAW_COLOR`, `RAW_OPACITY =
  0.35`) around the plate, which can make the plate look translucent.
  Check: when it happens (before or after "Modeling the stack"), and
  whether hiding the raw material's body brings the plate back.
  `T.i~5`'s `Details.md` wants the
  initial stock translucent and the final part solid.
* Other thing that changed this session: the model cache was emptied
  (`~/.scraftcnc/tool_cache/`), so the stack's models were rebuilt
  and imported fresh, which may differ from older cached STEP files.

## 2026-11-03: Found: a SolidCraft quirk, not a regression

* Not the stock: `demo_stack.json` has `"materials": []`, and the plate
  is modeled solid (`--opaque`, opacity 1.0).
* The user found it: SolidCraft makes what is under the mouse pointer
  translucent; with the pointer out of the window, the plate stays
  solid.  No SolidCraft command turns it off (none of the 407 is about
  hover or highlighting; `render.settings.*` looks like the final
  render's).  The user did not want to spend more on it.
* Told users in `README.md` (step 5 of "Trying It"): keep the pointer
  out of SolidCraft's window, and leave its building panels be.
