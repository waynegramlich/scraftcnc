# AI Contexts Rules

<!-- Written by ai_contexts; do not edit. -->

* `aic` (or `ai_contexts`) manages the collections (`TASKS/`, `ISSUES/`,
  `RULES/`); `aic -h` lists the commands.  Follow what its prompts and
  messages recommend.  Never edit a file it marks `Written by
  ai_contexts`, an item's `.item.json`, or a rule's `Details.md` (a
  copy of its source, which is changed only when asked).
* Each item has `Details.md` (the user's; edit only when asked),
  `Context.md` (Claude's working notes) and `Summary.md` (written by
  Claude before closing: what was decided and done, with related
  tags).
* States: Pending, Open, Reference (not worked on), Suspended, Closed,
  Rejected (decided against; the summary says why).  Startup loads
  `Details.md` until closed, `Context.md` while Open or Reference, and
  the `Summary.md` of the 50 most recently closed, but a closed child's
  only while its parent is Reference.
* A tag (e.g. `T.fbm`) names an item; numbers are positions that
  change.  In text and commit messages write `` `TAG~NUMBER` `` (e.g.
  `` `T.fbm~3` ``), never a number alone.  Commands take a tag wherever
  they take a number, and `aic T.fbm show` shows everything.
* Experiment with changing commands in a scratch directory, never on
  real items.
