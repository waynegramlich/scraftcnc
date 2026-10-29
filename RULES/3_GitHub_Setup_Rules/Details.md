# GitHub Setup Rules

<!-- --------------------------- 79 characters ---------------------------- -->

These rules set up a GitHub account protected by hardware two-factor
authentication (2FA), the `gh` command that Claude uses to drive it, and
a project's GitHub repository.  They come from the `ezpkg` project
(October 2026), where the same keys also protect test.pypi.org and
pypi.org.  `GitHub_Workflow_Rules.md` builds on them.

## Who Does What

* The human does only what needs a browser, a hand on a key or a
  password: creating accounts, registering keys, saving recovery codes
  and the one-time `gh` sign-in.
* Claude does everything else with `gh` (`gh api` for settings), and
  checks each result with `gh api` rather than trusting a web page.
* When a step must be done on the web, Claude names the exact page
  (its URL), the buttons in order, and how it will check the result.
  The human reports each step by number, so Claude gives the steps
  numbers (e.g. R1, R2, ...).
* `git` commits, pushes and tags follow `Version_Control_Rules.md`.

## Hardware 2FA Keys

* Buy two FIDO2/WebAuthn security keys (e.g. YubiKey 5): a primary and
  a backup.  Label them (e.g. `GitHubA`, `GitHubB`) and register each
  under its label, so a lost key can be removed by name.
* Register **both** keys on every site that the release depends on:
  github.com, and when publishing to PyPI, test.pypi.org and pypi.org.
  test.pypi.org and pypi.org are separate sites with separate accounts,
  passwords, keys and recovery codes; use the same user name on all
  three if it is free.
* Verify each key by signing in with it in a private window.  A site
  can appear to accept a key without registering it (test.pypi.org's
  first pass did); a sign-in that never asks for the key means it is
  not registered.
* GitHub's 2FA page is https://github.com/settings/security (Password
  and authentication).  Add both keys, then make security keys the
  preferred method.  Existing SMS or GitHub Mobile methods stay as
  fallbacks until the keys have proven themselves.
* An old account whose password is forgotten is recovered by password
  reset, not replaced (a registration form refusing the name is the
  sign that one exists).
* Save every site's recovery codes offline, print them, and keep the
  paper apart from the keys.  Store the backup key apart from the
  primary.  Using a recovery code uses it up; note which are left.
* On Linux, browsers see the keys through `libfido2` and udev's
  `60-fido-id.rules` (both standard on Ubuntu 24.04).  If a browser
  ignores the key's touch, suspect the udev rules first.
* No API tokens are ever made, on GitHub or PyPI: publishing uses
  Trusted Publishing (`GitHub_Workflow_Rules.md`), so the GitHub account is
  as much a gate on a release as the PyPI one.

## The `gh` Command

* The human signs in once: `gh auth login` (GitHub.com, HTTPS, sign in
  with a browser), which shows a one-time code to enter at
  https://github.com/login/device.  Suggest `! gh auth login` so it
  runs in the session.
* `gh auth setup-git` makes `gh` the credential helper, so `git push`
  over HTTPS needs no ssh key and no stored password.  Prefer HTTPS
  remotes: an ssh key with a forgotten passphrase blocks every push.
* `gh` keeps the protocol per host, which wins over the global one, so
  set both: `gh config set git_protocol https` and `gh config set -h
  github.com git_protocol https`.  `gh auth status` then says
  "Git operations protocol: https".  `gh repo create --remote` uses it;
  a remote made while it was still ssh is fixed with `git remote
  set-url github https://github.com/OWNER/REPO.git`.
* The token needs the `repo` and `workflow` scopes.  Without
  `workflow`, pushing a file under `.github/workflows/` is refused
  ("refusing to allow an OAuth App to create or update workflow ...
  without `workflow` scope").  Add it with `gh auth refresh -h
  github.com -s workflow` (another one-time code).
* Check with `gh auth status` (account, protocol, scopes).  Never print
  the token itself.
* Claude finds the user's numeric id, which some settings need, with
  `gh api user --jq .id`.

## Creating the Repository

Claude does this with the human's agreement on each choice:

1. Check whether the project is already on GitHub under any name:
   `gh repo list OWNER --limit 200` and the local `git remote -v`.
2. Decide public or private (the human's choice).  Public repositories
   get GitHub Actions runners free, including Windows and macOS.
3. Before the first push, look at what would become public:
   * Symbolic links into directories outside the project dangle on
     GitHub; untrack them (`git rm --cached`, add them to
     `.gitignore`), leaving them on disk.
   * Search the history for secrets (tokens, keys, passwords); nothing
     pushed can be taken back.
   * Item collections (`TASKS/`, `ISSUES/`, `RULES/`) become public
     along with the code.
   * Every commit's author name and email become public.
4. Create it, naming the remote `github` (the `remote.pushdefault` in
   the human's `~/.gitconfig`), with a one-line description:

   ```
   gh repo create OWNER/REPO --public --source=. --remote=github \
       --description "..."
   git remote -v                       # https://, not git@
   ```
5. Push the default branch, after asking (`Version_Control_Rules.md`):
   `git push -u github main`.  Until then `defaultBranchRef` is empty.
   When the human will push, Claude sets the upstream instead (`git
   branch --set-upstream-to` refuses until `github/main` exists): `git
   config branch.main.remote github`, `git config branch.main.merge
   refs/heads/main`, then checks with `git push --dry-run`.  A plain
   `git push` then works.
6. Verify: `gh repo view OWNER/REPO --json url,visibility,defaultBranchRef`
   and `git ls-remote github main` against `git rev-parse main`.

## Disclosing AI Help in Commits

The human is the author of every commit and answers for it, so the
trailer is `Assisted-by: AGENT_NAME:MODEL_VERSION` (the Linux kernel's
form, e.g. `Assisted-by: Claude Code:claude-opus-5-5`), not
`Co-authored-by:`.  The project's `git_hooks/` adds it:

* `prepare-commit-msg` runs `git interpret-trailers --in-place
  --if-exists doNothing --trailer "$TRAILER" "$1"`, skipping merges and
  squashes, so the trailer is in the editor and can be deleted from a
  commit the AI had no part in.
* `commit-msg` refuses a message that is only the trailer, since
  quitting the editor would otherwise still make a commit.
* Each clone turns them on with `git config core.hooksPath git_hooks`.
* Update the model in the trailer when the model changes.
