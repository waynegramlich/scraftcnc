# Summary of `T.il` Installing LinuxCNC

The simulator runs on Linux (`distrobox` box `lcnc`, Debian Trixie, `podman`) and Windows (WSL 2 Debian); macOS dropped.  The installer now
lives in `../scraftlinuxcnc`; `lcnc_panel.py` is its client on the host, through `lcnc_client.py`.  `rtapi_app` must not be setuid in a
rootless box.  After a reboot, enter the box once and wait: two `distrobox enter`s at once hang.

Not done: the box still has the full install (`T.hlp~3.3.1`); no retry in `newest_package()`; WSL unrun since protocol 2; no `pyproject.toml`
(data files are lost on install, and `tools`, `mount`, `shops` are taken on PyPI).  A real mill needs realtime, which this install undoes.
