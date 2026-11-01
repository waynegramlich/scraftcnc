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
