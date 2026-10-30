# Version Control Rules

<!-- --------------------------- 79 characters ---------------------------- -->

Claude follows this logic at the start of each session.  It describes
what Claude does; it is not a program to run.

```python
if exists(".no_version_control_rules"):
    return  # The User declined: do not follow these rules or ask again.

missing = [
    name
    for name in (".git/", ".gitignore", ".hg/", ".hgignore")
    if not exists(name)
]
if missing:
    answer = ask_user(
        "The Version Control Rules have been enabled.  They require "
        f"creating {missing}.  Is it OK to create these?"
    )
    if answer == "yes":
        # `.gitignore` ignores `.hg/`; `.hgignore` ignores `.git/`.
        create(missing)
    else:
        create(".no_version_control_rules")
        if on_windows:
            run("attrib +h .no_version_control_rules")
        tell_user(
            "`ai_contexts r deactivate R.vcr` stops loading these rules.  "
            "Deleting `.no_version_control_rules` asks the question again.  "
            "On Windows: `del /a:h .no_version_control_rules` in `cmd`, or "
            "`Remove-Item -Force .no_version_control_rules` in PowerShell."
        )
        return  # Do not follow these rules.

# Follow the rules below.
```

The version control rules are:
* If `.hgignore` does not ignore `.git/`, or `.gitignore` does not ignore
  `.hg/`, Claude tells the User and asks whether to add the entry.
* Claude has exclusive use of `hg`.
* Claude does its regular checkpoints into `hg`.
* When Claude does an `hg` checkpoint, it does not tell the user.
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
* When the User says they are getting ready to do a commit (e.g. by
  mentioning `git commit`), Claude does these in order:
  1. If the project has any Open `ai_contexts` items, Claude brings the
     `Context.md` of each one up to date, so that the next session can
     pick up the work.
  2. Does an `hg` checkpoint.
  3. Runs `git add -A` in the directory that contains `.git/`.
  4. Suggests a commit message.
