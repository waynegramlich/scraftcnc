# GitHub Workflow Rules

<!-- --------------------------- 79 characters ---------------------------- -->

These rules run a project's testing and releases on GitHub Actions, and
publish Python packages to test.pypi.org and pypi.org with Trusted
Publishing.  They assume `GitHub_Setup_Rules.md` (2FA, `gh` with the
`repo` and `workflow` scopes, a repository with a `github` remote).
They come from the `ezpkg` project (October 2026), whose
`.github/workflows/release.yml` and `check.yml` and `release_check.py`
are the worked examples; `OWNER`, `REPO` and `PACKAGE` stand for the
project's own names.

## The Web Site Is a Last Resort

* Claude does every GitHub step with `gh`: starting, watching,
  approving, re-running and cancelling runs, reading logs and
  artifacts, and all repository settings (`gh api`).
* After any setting is changed, Claude reads it back with `gh api`.
  A web form can look saved and not be (a required reviewer chosen but
  never saved, the first time for `ezpkg`).
* Only these need the human on a web page:
  * The one-time `gh` sign-in and scope refreshes (a device code).
  * PyPI's pending publisher, on each of test.pypi.org and pypi.org:
    PyPI has no API for it and no way to read it back.  Claude gives
    the field values; the human checks the listing by eye.
* Claude Code's own permission check may refuse to start a run that
  publishes to pypi.org until the human says go; that is expected.

## Testing Workflows

A testing workflow runs the project's checks on GitHub's machines,
where the project has none of its own (Windows, Apple Silicon and Intel
macOS):

* Trigger it with `workflow_dispatch` (by hand, with `inputs`) and
  `workflow_call` (from another workflow, with the same inputs as
  plain `string`s, since `choice` is not allowed there).  A
  `workflow_dispatch` workflow can be started only once its file is on
  the default branch.
* Use a matrix with `fail-fast: false`, so one failure does not hide
  the others.  The runners:
  * `ubuntu-latest`, `windows-latest`.
  * `macos-latest` (Apple Silicon).
  * `macos-15-intel`, the last Intel image (until fall 2027; the
    `macos-13` images were retired in December 2025).
  * Every supported Python through `actions/setup-python@v6` (`ezpkg`:
    3.11 to 3.15).  `ezpkg`'s 25 jobs take about 3 minutes.
* Give every job `timeout-minutes` (`ezpkg`: 15).  A program that
  waits for an answer waits for ever on a runner.
* Keep `permissions` minimal: `contents: read`, plus `actions: read`
  only for a job that reads other runs (`gh run download`).  Give that
  step `GH_TOKEN: ${{ github.token }}`.
* `actions/checkout@v5` with `persist-credentials: false`.
* Pass inputs to scripts through `env`, never by writing
  `${{ inputs.X }}` inside a `run:` script, which would let an input
  inject shell code.
* Test as a stranger would run it: a fresh `HOME` (and `USERPROFILE`,
  which Windows Python uses instead), no `PYTHONPATH` or `PIP_*`
  variables, standard input from the null device, a scratch directory
  under `runner.temp`.  Runners set `CI`, which a program can take to
  mean that nobody is there to answer.
* Add jobs for what the matrix cannot show.  `ezpkg`'s:
  * `python-org`: python.org's macOS Python, which has no certificates
    until its `Install Certificates.command` is run.
  * `console`: a real terminal (a pseudoterminal, or ConPTY through
    `pywinpty` on Windows), so a question is asked and answered.
* On failure, keep the evidence: `actions/upload-artifact@v4` of the
  scratch directory under `if: failure()`, with `include-hidden-files:
  true` for dot-directories.
* Pin lint tools to the versions used locally (`ruff==X`, `mypy==Y`),
  so a new upstream rule cannot fail a run.
* Give the testing workflow a `source` target (the default) that
  builds a wheel from the chosen commit and tests it as a stranger
  would, and runs the linters, so the workflow is useful before
  anything is published (`aicontexts`: `check.yml` with
  `release_check.py source`).
* Pass an optional input as an optional argument with
  `${VERSION:+"$VERSION"}`: nothing when it is empty, and quoted when
  it is not.
* Before committing a workflow, check it locally:
  * `uvx --from actionlint-py actionlint .github/workflows/*.yml`
    checks the syntax, the expressions and (with `shellcheck`) the
    scripts.
  * Rehearse a `run:` script by extracting it with `yaml.safe_load`
    (`uvx --with pyyaml python`) and running it with `bash -e`, as the
    runner does.  Runners have `python`; a machine with only `python3`
    needs a scratch `python` link on `PATH`.
  * Run the stranger check on every supported Python with
    `uv run --no-project --python 3.X python release_check.py source`.

## What the Other Systems Find

The first runs of `aicontexts` on Windows and macOS (October 2026)
found these, none of which show up on Linux:

* Windows can not replace or delete a read-only file: make it writable
  first (`path.chmod(path.stat().st_mode | stat.S_IWUSR)`), also before
  `shutil.rmtree()`.
* Windows has no `os.geteuid()`, and permission tests mean little
  there; skip them with `os.name == "nt"` as well as for root.
* `str(path)` and `sorted()` of paths differ on Windows (`\`, and case
  is ignored): print paths the user typed with `as_posix()`, and sort
  with `key=Path.as_posix` wherever the order is shown or tested.
* `write_text()` writes `\r\n` on Windows; pass `newline="\n"` so files
  (and their hashes) are the same everywhere.
* On macOS, `/` has entries (`/.resolve`) that Python 3.11's
  `Path.glob()` can not `stat`; a search that can reach `/` should list
  directories with `iterdir()` and skip entries that raise `OSError`.
* A test suite that only prints the names of failed checks gives little
  to go on from a runner's log; print the output that failed too.

## Running and Watching

Claude runs these itself, in the background for anything over a minute,
telling the human how long it should take:

```
gh workflow run check.yml -f target=testpypi -f version=VERSION
RUN=$(gh run list --workflow=check.yml --limit 1 \
      --json databaseId --jq '.[0].databaseId')   # after a few seconds
gh run watch "$RUN" --exit-status                 # 0 when all passed
gh run view "$RUN" --json status,conclusion,jobs \
    --jq '.jobs[] | .name + " " + .conclusion'
gh run view "$RUN" --log-failed                   # only failed steps
gh run download "$RUN" --name ARTIFACT --dir DIR
gh run rerun "$RUN" --failed                      # a transient failure
gh run cancel "$RUN"
```

* `gh run list` may not show a run for a few seconds after `gh
  workflow run`; check that the run it finds is the new one (its
  `createdAt`, or a `run-name` that names the inputs).
* "Waiting" means waiting for an approval, not stuck.
* Record each run's id and result (e.g. "check.yml 40143578538 25/25")
  in the item's `Context.md`; summaries cite them.
* Re-run failed jobs only when the cause is understood to be outside
  the project (e.g. an index that had not caught up yet), and say so.

## Trusted Publishing

PyPI is told to trust one GitHub owner, repository, workflow file and
environment.  When that workflow runs, GitHub gives it a signed
identity token (OIDC) that PyPI exchanges for a short-lived upload
token, so no secret is ever stored.

* One workflow, `release.yml`, started by hand with an input `target`
  of `testpypi` or `pypi`; going live is changing that one word, and
  `run-name: release ${{ inputs.target }}` shows which in the list.
* The jobs:
  1. `build`: no special permissions; lint, build the wheel into
     `dist/`, `twine check --strict`, then `actions/upload-artifact`.
     The publish action uploads **everything** in `dist/`, so the build
     must leave nothing else there.  Expose the version built as a job
     output (from the wheel's file name).
  2. `publish`: `environment: ${{ inputs.target }}`, `permissions:
     id-token: write` on this job only, never the workflow;
     `actions/download-artifact`, then
     `pypa/gh-action-pypi-publish@release/v1`, with `repository-url:
     https://test.pypi.org/legacy/` for `testpypi` and
     `https://upload.pypi.org/legacy/` for `pypi`.
  3. `listed` (`pypi` only): wait until
     `https://pypi.org/pypi/PACKAGE/json` names the new version (up to
     a few minutes), since it can name the previous release for a
     minute or more after an upload.
  4. `check`: `uses: ./.github/workflows/check.yml` with the version
     built, so every upload is tested as a stranger gets it.
* Versions: `testpypi` uploads a disposable `X.Y.Z.devYYYYMMDDHHMM`
  (UTC), new on every run; `pypi` uploads `X.Y.Z` and the build refuses
  unless `git tag --points-at HEAD` includes `vX.Y.Z` (or, simpler, if
  `GITHUB_REF` is not `refs/tags/vX.Y.Z`).
* For a package built by `setuptools` with `dynamic = ["version"]` from
  a module's `__version__` (`aicontexts`), the build job rewrites that
  one line to the `dev` version before `python -m build`; the change
  lives only on the runner.

### One-Time Setup, by `gh api`

Claude does all of this except the pending publishers.  `ID` is
`gh api user --jq .id`.

1. An environment per target, with the human as required reviewer
   (`prevent_self_review` false, or nobody can approve their own run)
   and custom deployment rules:

   ```
   for ENV in testpypi pypi; do
     gh api -X PUT repos/OWNER/REPO/environments/$ENV --input - <<EOF
   {"reviewers": [{"type": "User", "id": $ID}],
    "prevent_self_review": false,
    "deployment_branch_policy":
      {"protected_branches": false, "custom_branch_policies": true}}
   EOF
   done
   ```
2. `testpypi` deploys from branch `main` (rehearsals are untagged);
   `pypi` deploys only from `v*` **tags** (`type=tag`; a branch rule
   named `v*` is a different thing and was the first mistake):

   ```
   gh api -X POST \
       repos/OWNER/REPO/environments/testpypi/deployment-branch-policies \
       -f name=main -f type=branch
   gh api -X POST \
       repos/OWNER/REPO/environments/pypi/deployment-branch-policies \
       -f name='v*' -f type=tag
   ```
3. A tag ruleset so that only a repository admin creates, moves or
   deletes `v*` tags (`actor_id` 5 is the admin role):

   ```
   gh api -X POST repos/OWNER/REPO/rulesets --input - <<'EOF'
   {"name": "release tags", "target": "tag", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"],
                                "exclude": []}},
    "rules": [{"type": "creation"}, {"type": "update"},
              {"type": "deletion"}],
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole",
                       "bypass_mode": "always"}]}
   EOF
   ```
4. Read it all back:

   ```
   gh api repos/OWNER/REPO/environments/pypi \
       --jq '.protection_rules[].type'  # branch_policy, required_reviewers
   gh api repos/OWNER/REPO/environments/pypi/deployment-branch-policies \
       --jq '.branch_policies[] | .type + " " + .name'      # tag v*
   gh api repos/OWNER/REPO/rulesets --jq '.[] | .id'
   gh api repos/OWNER/REPO/rulesets/RULESET_ID
   ```
5. The human, on each index: account → Publishing
   (`/manage/account/publishing/`) → Add a new pending publisher →
   GitHub: project name `PACKAGE`, owner `OWNER`, repository `REPO`,
   workflow `release.yml` (the file name only), environment `testpypi`
   on test.pypi.org or `pypi` on pypi.org.  A pending publisher does
   not reserve the name (someone else registering it first invalidates
   it), so the first upload should follow soon.

### Approving a Deployment

```
ENV_ID=$(gh api repos/OWNER/REPO/actions/runs/$RUN/pending_deployments \
         --jq '.[0].environment.id')
gh api -X POST repos/OWNER/REPO/actions/runs/$RUN/pending_deployments \
    -F "environment_ids[]=$ENV_ID" -f state=approved \
    -f comment="Approved by Claude at OWNER's word"
```

GitHub refuses an approval without a `comment`.  Claude approves
`testpypi` runs itself; a `pypi` run only after the human's go for that
release.

## The Release Procedure

1. Bump the version in the source; the human commits; Claude pushes
   (`Version_Control_Rules.md`).  No tag yet.
2. Rehearse: `gh workflow run release.yml -f target=testpypi`, approve,
   watch.  Its `check` job tests the `dev` upload everywhere.  Repeat
   from step 1 until it passes.
3. Tag that same commit and push the tag: `git tag -a vX.Y.Z -m
   "PACKAGE X.Y.Z" COMMIT`, `git push github vX.Y.Z`.  The tag comes
   last because a pushed tag should never move.
4. `gh workflow run release.yml --ref vX.Y.Z -f target=pypi`, approve
   at the human's word, watch.
5. Check it as a stranger from this machine too (`ezpkg`:
   `./release_check.py pypi X.Y.Z`).
6. A bad release is never repaired: leave its tag and release the next
   number.

## Index Facts and Traps

* **Never search test.pypi.org and pypi.org together.**  Anybody can
  upload to test.pypi.org, and names there are not the real owners'
  (its `cowsay` 6.1.2 is a stranger's, newer than the real 6.1), so
  `PIP_EXTRA_INDEX_URL` would pick the stranger's.  Download only your
  own wheel from test.pypi.org's JSON API, check its SHA-256, and give
  it to `pip` with `PIP_FIND_LINKS`; everything else comes from
  pypi.org.  Pin it with `PIP_CONSTRAINT` (`PACKAGE==VERSION`), or
  `pip` prefers a real release to a `.dev` one.
* `/pypi/PACKAGE/json` (the newest version) is cached for up to 15
  minutes and names the previous version right after an upload; ask
  for `/pypi/PACKAGE/VERSION/json` instead, or ask GitHub which version
  the newest successful release run built.  test.pypi.org's JSON API
  can answer 404 for a version uploaded minutes before; retry.
* Deletion on either index is permanent, and a deleted file name can
  never be uploaded again, so deleting never lets a version be retried.
  Never delete a project: its name goes to anybody, and may not come
  back.
* Artifacts expire after 90 days.
