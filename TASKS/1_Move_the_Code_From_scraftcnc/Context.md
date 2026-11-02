# LLM Agent Context Log

## 2026-11-01: The plan, as agreed in `scraftcnc`

Background is in `../scraftcnc/TASKS/3.1_Installing_LinuxCNC/Context.md`.

* Moving: `install_linuxcnc.py`, `demo_linuxcnc.py`, `stop_linuxcnc.py`,
  `sim_linuxcnc.py`, `sim_solidcraft.py`, `lcnc_panel.py`, `probe_batch.py`,
  `lcnc_sim/`, their tests, `probe_linuxcnc.yml`.  `sctoolmodel.py` stays there
  (`tools.py` and others import it).
* Order: the probe run of the trimmed install in `scraftcnc`; a `pyproject.toml` for
  `scraftcnc`; copy here and debug, with a probe run; only then delete there.
* Here: real package names (`scraftlinuxcnc.sim_linuxcnc`), so the old copies can not
  be imported by mistake.  From the copy on, fixes are made only here.
* To solve: the code runs on the host and inside the box or WSL, which needs `shops`;
  LinuxCNC writes `.tbl` and `.var` next to the INI file, and `DISPLAY =
  ../lcnc_panel.py` is relative, so the configuration goes in a user directory;
  `probe_batch.py` imports `solidcraftcnc_demo`.
* Later: `lcnc_panel.py --headless`, for tests, with no `Xvfb`.  The repository stays
  private until it works, then goes public.  `scraftcnc`'s line says the same.

## 2026-11-01: Paused

* Done: the trimmed install in `scraftcnc` passes on Ubuntu and WSL.  `github` is the
  remote here; the repository is private, with the user's first commit.
* Not started: no code is copied.  It waits on how `scraftcnc` is packaged, the first of
  the five open issues at the end of
  `../scraftcnc/TASKS/3.1_Installing_LinuxCNC/Context.md`.

## 2026-11-01: The scope narrows (the user's; details not settled)

* The user's goal now: this package wraps installing LinuxCNC userspace on Linux and on
  Windows through WSL, giving a non-realtime LinuxCNC that is driven through its `linuxcnc`
  Python module.  This replaces the list of files in the plan above, if the user agrees
  to Claude's suggestions below.
* Checked: `install_linuxcnc.py` and `stop_linuxcnc.py` import only the standard library, so
  this no longer waits on `scraftcnc`'s packaging.  `lcnc_panel.py`, `sim_linuxcnc.py`,
  `sim_solidcraft.py` and `probe_batch.py` all import `scraftcnc` modules.  The end to end
  test, `demo_linuxcnc.py`, needs those too, so a new standalone test is needed.
* Suggested, waiting for an answer: those four stay in `scraftcnc`.  Not tried: a small
  `DISPLAY` program in place of the panel.  The `linuxcnc` module exists only in the
  box or WSL, so programs that import it must run there.

## 2026-11-01: The user's answers on the new scope

* This package has no dependency on `scraftcnc`.  `lcnc_panel.py` stays there; so must
  the others that import `scraftcnc` modules.  Its packaging is not a question here.
* Rebuilding the `lcnc` box with the trimmed install: yes, on the condition that it holds
  LinuxCNC's compiled userspace programs, which it does.  Not done yet.
* The retry in `newest_package()`: yes.  Not done yet.

## 2026-11-01: More answers, and the numbering slip

* The list given to the user was numbered 4, 5, 7, 8, 9, 10, and the answers came back as
  4 to 9, so the terminal probably renumbered it.  Do not give a list with gaps in its
  numbers.  Claude's reading of the answers, which the user is asked to confirm:
  * `--headless` belongs in `scraftcnc`: `T.hlp~3.3.1` there.  `T.il~3.1` stays open.
  * The user's code is installed into WSL (or the box) and runs there.
  * This directory takes all the pain of getting userspace LinuxCNC.
  * `python3-tk` goes (`install_linuxcnc.py:133`), and `tkinter` from `PANEL_MODULES`
    (`install_linuxcnc.py:148`); `scraftcnc` installs it for the panel.  `tk8.6` stays.
  * `scraftcnc` depends on this package, for its LinuxCNC tests only, so this one gets a
    small `pyproject.toml`.
* Claude's decision: `lcnc_sim/shop_mill.ini` stays in `scraftcnc`, as it starts the
  panel; this package gets its own simulator INI and small `DISPLAY` program.
* Open with the user, numbered from 10: 10 (the reading above), 11 (where `T.hlp` goes),
  12 (moving the run-inside-the-target code out of `demo_linuxcnc.py`).

## 2026-11-01: The user wants a JSON bridge on a port

* The user, on 11: will fix the tasks in `scraftcnc` themself.  On 12: wants code that
  accepts a connection on a local network port and exchanges JSON messages that reach
  LinuxCNC's Python API.  So programs need not run inside the box or WSL.
* Looked at, nothing built or run: in the `lcnc` box `linuxcnc.stat` has 87 public names,
  `linuxcnc.command` 40 and `linuxcnc.error_channel` 1 (`poll`), so a generic dispatch is
  small.  `lcnc_panel.py` already serves a port on 127.0.0.1, one line per connection.
* Claude's design, untried:
  * The bridge runs inside the target as the INI file's `DISPLAY` program, so LinuxCNC
    starts it and it stops LinuxCNC by exiting.  This is also the stand-in `DISPLAY`
    program, with no window, so no `Xvfb`.
  * One JSON message per line.  Only public names of those three objects, never `eval`.
    Constants are sent by name.  A message sends a G-code file's text, as
    `program_open` takes a path inside the target.
  * Bound to 127.0.0.1 unless the user says otherwise (13 on the list); no password.
* Not known: Windows reaching a port in WSL 2 (from memory, forwarded by default); stat
  values all converting to JSON; the `linuxcnc` script accepting such a `DISPLAY`.  The
  probe test connects from outside the target, on both runners.
* `pack()` and `place_project()` stay in `scraftcnc`, not moved.  Open: 10, 13.

## 2026-11-01: The bridge works locally; waiting for the commit and a probe run

* The user: the port is for anyone on the same machine; `scraftcnc` is the user's to
  handle, including its copies, its use of the installer and `python3-tk`.  This package
  gives only a port with a protocol we define.  LinuxCNC's GUIs are never used.
* Built: `scraftlinuxcnc/` (`install_linuxcnc`, `stop_linuxcnc`, `lcnc_bridge`,
  `lcnc_client`, `serve_linuxcnc`, `demo_linuxcnc`, `sim/`), `tests/`, `pyproject.toml`,
  `probe_linuxcnc.yml`, a new `README.md`.  Changed in the installer: no `python3-tk`, no
  panel check, no sample configurations, `retry()` on downloads, a step for the bridge.
* Throwaway box `lcnc-bridge` (removed).  From the checkout: install 2 min 39 s, 21
  packages.  Again from a wheel in a scratch virtual environment.  `demo_linuxcnc` passes in about 4 s, from outside the
  box with `DISPLAY` unset: ping, 83 constants, all 86 `stat` attributes through JSON,
  on, homed, MDI, a program, no errors, shutdown.  A rerun of the installer: all done.
  `serve_linuxcnc` stopped by `SIGINT` (to its group) and `SIGTERM`: exit 0, nothing left.
* Not shown: WSL 2 at all, so Windows reaching the port is still unknown.  Next: the
  user's commit, a push to `github`, `gh workflow run probe_linuxcnc.yml`.
* Not done: rebuilding `lcnc`, held because its panel needs `python3-tk` from `scraftcnc`.
* Limit to raise with the user: the INI file is fixed, with travel X 18, Y 9, Z 16.

## 2026-11-01: Saved for a `/clear`; start here

The user commits and pushes `github` themself, then comes back to run the Windows side.

1. Check that the commit is pushed (`git status -sb`, `git log -1`).
2. `gh workflow run probe_linuxcnc.yml --repo waynegramlich/scraftlinuxcnc`, on `main`,
   then watch it.  It runs on `ubuntu-latest` and `windows-latest`: `pip install .`, the
   offline tests, `install_linuxcnc --yes`, `demo_linuxcnc`.
3. The question it answers: can Windows' own Python reach port 5008 in WSL 2?  WSL has also
   never run this install without `python3-tk`, or the bridge at all.  If the port can not
   be reached, the bridge binds 127.0.0.1 (`lcnc_bridge.py`, `main()`), the first thing
   to look at.  A failed `serve_linuxcnc` prints `~/linuxcnc_print.txt` and
   `~/linuxcnc_debug.txt` from the target.

Open issues, left open by the user, keeping their numbers (no gaps in a list, as the
terminal renumbers them):

14. When to rebuild the `lcnc` box: held until `scraftcnc` installs `python3-tk`, which the
    user will say.  It was #2, answered yes.
15. `serve_linuxcnc --ini FILE`: Claude recommends adding it when `scraftcnc` needs it.

Not this package's: `scraftcnc` is the user's, including `T.hlp~3.3.1`, `T.il~3.1`, its
copies of these files and its unpushed `c841ddc`.
