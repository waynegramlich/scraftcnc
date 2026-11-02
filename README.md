# `scraftlinuxcnc`: LinuxCNC's Simulator, on a Port

`scraftlinuxcnc` installs LinuxCNC's simulator (`linuxcnc-uspace`, with
no realtime) on Linux or on Windows, and runs it so that any program
on the same computer can drive it by sending JSON to a port.  The
program does not need LinuxCNC's Python module, Debian, or to know
about `distrobox` or WSL.  This package holds all of that pain, and
depends on nothing else.

**LinuxCNC's own screens are not used or installed.**  It does not set
up LinuxCNC to drive a real mill: that needs a realtime kernel and
hardware drivers, which the installer deliberately leaves out.

## Status

The repository is private until it works everywhere.  See `Probe runs`
below for what has been shown.

## Use

```
pip install .
install_linuxcnc     # Once.  It tells you of anything you must run.
serve_linuxcnc       # Runs LinuxCNC until it is stopped.
```

LinuxCNC goes in a `distrobox` box named `lcnc` on Linux, and in WSL 2's
`Debian` on Windows.  `install_linuxcnc` shows and copies each command
that needs you (such as a `sudo`).  `demo_linuxcnc` runs a program from
start to finish as a test.

## The Protocol

`serve_linuxcnc` listens on port 5008 of `localhost`.  Anyone on the
same computer can connect, with no password.  A request and a reply
are each one line of JSON, and `id` is returned as it was sent:

```
{"id": 1, "call": "command.mdi", "args": ["G0 X1"]}
{"id": 1, "result": 1}
{"id": 2, "call": "stat", "args": [["actual_position"]]}
{"id": 2, "result": {"actual_position": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}}
{"id": 3, "call": "command.nope"}
{"id": 3, "error": {"type": "ValueError", "message": "command has no 'nope'"}}
```

| `call` | `args` | `result` |
|---|---|---|
| `ping` | | The protocol's number and LinuxCNC's version |
| `constants` | | The `linuxcnc` module's numbers and strings, by name |
| `stat` | A list of names, or nothing for all | `linuxcnc.stat`'s attributes, after a `poll()` |
| `command.NAME` | Its arguments | What the `linuxcnc.command` method returned |
| `error_channel.poll` | | The next error as `[kind, text]`, or `null` |
| `ini.find` | Section, option | The running INI file's value, or `null` |
| `program.write` | Name, text | The path to give `command.program_open` |
| `shutdown` | | `null`; LinuxCNC then shuts down |

In `command` arguments, `{"constant": "MODE_MDI"}` stands for that
constant.  One request runs at a time, so a `command.wait_complete`
holds up other connections until it finishes.  The meanings of the
`stat` attributes and `command` methods are LinuxCNC's, in its [Python
interface](https://linuxcnc.org/docs/2.9/html/config/python-interface.html).

`scraftlinuxcnc/lcnc_client.py` is a small Python client, and
`scraftlinuxcnc/demo_linuxcnc.py` shows a whole session: machine on,
homing, MDI, and running a program.

## Why the Installation Is Small

LinuxCNC's package depends on all of its screens, whether or not they
are used.  The installer replaces that list with only what the
simulator needs, so a new dependency of those screens is never
installed.  One measurement, in a `distrobox` box on Ubuntu 24.04, of
LinuxCNC 2.9.10, while the list also held `python3-tk`:

| | Trimmed | LinuxCNC's own list |
|---|---|---|
| Time to install LinuxCNC | 18 s | 145 s |
| Packages added | 25 | 454 |
| Downloaded | 11.3 MB | 338 MB |
| Installed size added | 130 MB | 1421 MB |

(Both leave out LinuxCNC's recommended packages.)

## Probe runs

`.github/workflows/probe_linuxcnc.yml`, run by hand, installs and runs
`demo_linuxcnc` on `ubuntu-latest` and `windows-latest`.

## License

MIT No Attribution (`LICENSE`).
