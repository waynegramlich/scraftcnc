# LLM Agent Context Log

## 2026-11-03: Chunk 2 stopped before `git subtree add`

* `git subtree add` always makes a git merge commit, and the rules
  say Claude never runs `git commit`; so it was not run, and the
  user is asked.  Nothing in git changed.
* `../scraftpybind` has `.ai_contexts.json` in `RULES/` and
  `TASKS/`; one Open item, `1_Publish_scraftpybind` (its
  `Details.md` is only the title), to copy here or drop; `2_Rename_
  Classes_to_SC` is Closed.
