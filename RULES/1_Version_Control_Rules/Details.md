# Version Control Rules

<!-- --------------------------- 79 characters ---------------------------- -->

The version control rules are:
* Claude has exclusive use of `hg`.
* Claude does its regular checkpoints into `hg`.
* When Claude does an `hg` checkpoint, it does not tell the user.
* The User is entirely disallowed from using `hg`.
* The User is allowed to use features of `git`.
* The User writes all `git` commit messages, so Claude never runs
  `git commit`.
* Claude may run every other `git` command without asking, including
  those that modify the commit log or a remote (e.g. `merge`,
  `rebase`, `reset`, `revert`, `cherry-pick`, `pull`, `push`, `tag`).
* Claude does an `hg` checkpoint before any `git` command that changes
  state (e.g. `add`, `mv`, `rm`, `restore`, `stash`).  This includes
  a `stash` that is popped straight back, such as one used to see how
  the committed files behave; for that, prefer the read-only `git show
  HEAD:FILE`, or `git worktree` in a scratch directory.
* Read-only `git` commands (e.g. `status`, `diff`, `log`) are free.
