# LLM Agent Context Log

## 2026-10-31: Created; the plan is in `Details.md`

* The user asked for a plan and no code yet, and will read `Details.md`.
  The user also has more to say about stacked zones before that design
  is settled.  Next: the user's reactions and its open questions.
* The demo's G-code has only 2 lines with Z beside X or Y, both `G83`,
  since its pockets are drilled, not ramped.

## 2026-10-31: The user's answers; `Details.md` updated

* Settled: no combined commands (so canned cycles get their own `G0 X Y`);
  only generated code is checked; all classes start with `SC`; cutters are
  vertical cylinders; rapids belong at Zsafe.
* Open in `Details.md`: the user's stacked zones talk, and questions 5 and
  7-12.  Still no code.

## 2026-10-31: Second round of answers

* Settled: rising rapids always fine, descending ones not; a drill out of rapid
  mode by Ztop; widest radius; rename this directory first (`scraftpybind` a
  separate task); combined MDI lines rejected.
* Open in `Details.md`: the user's stacked zones talk, and questions 5, 9, 13,
  14, 15.  Still no code.  The user is tired, so keep new issues to what matters.

## 2026-10-31: `Details.md` wrapped up for now

* The user: the questions were getting into implementation, so stop here and
  commit.  `G83` exempted; consistency checks only for bad data; Home belongs at
  Zsafe, so its `G0 Z0` is a bug to fix in step 10.
* Next session: the user's talk about stacked zones (step 1), and questions 5
  and 9, which are still open.  Then step 11, the `SC` rename.  No code yet.
