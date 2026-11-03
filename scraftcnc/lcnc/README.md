# `scraftcnc.lcnc`: SolidCraft LinuxCNC Simulator Access

When working on a system that generates G code for a CNC machine, it is
extremely desirable to be able to simulate what the G code actually does.
The open source [LinuxCNC](https://linuxcnc.org/) project is used to control
actual CNC machines in real-time.  For fairly obvious reasons, the LinuxCNC
development team has a version that runs on a regular version of Linux rather
than requiring the real-time version of Linux running on real hardware.  This
technology is used to test CNC code generation for use in conjunction with
[SolidCraft Open-source parametric CAD](https://solidcraft.io/).

This package encapsulates the installation of the Linux User Space
(`linuxcnc-uspace`) package for both regular Linux and Microsoft via their
WSL [Windows Subsystem for Linux](
https://learn.microsoft.com/en-us/windows/wsl/).  This Linux package provides a
complete Python interface to all of the LinuxCNC functionality.  There is
a light-weight program that provides a bi-directional JSON message protocol
controlling the LinuxCNC simulator via the Python interface.  At no point
does any of this software need access to a display screen, mouse or keyboard.

## Status

Part of `scraftcnc` (it was the `scraftlinuxcnc` repository).  See
`Probe runs` below for what has been shown.

## Use

From the top of `scraftcnc`:

```
python3 -m scraftcnc.lcnc.install_linuxcnc  # Once; lists what you run.
python3 -m scraftcnc.lcnc.serve_linuxcnc    # Runs LinuxCNC until stopped.
```

LinuxCNC goes in a `distrobox` box named `lcnc` on Linux, and in WSL 2's
`Debian` on Windows.  `install_linuxcnc` shows and copies each command
that needs you (such as a `sudo`).  `demo_linuxcnc` runs a program from
start to finish as a test.

## The JSON Protocol

`serve_linuxcnc` listens on port 5008 of `localhost`.  Anyone on the
same computer can connect, with no password.  A request and a reply
are each one line of JSON, and `id` is returned as it was sent:

```json
{"id": 1, "call": "command.mdi", "args": ["G0 X1"]}
{"id": 1, "result": null}
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
| `program.read` | A path from `program.write` or `stat`'s `file` | The file's text |
| `tool_table.write` | Text | Its path; `command.load_tool_table` then reads it |
| `shutdown` | | `null`; LinuxCNC then shuts down |

In `command` arguments, `{"constant": "MODE_MDI"}` stands for that
constant.  A connection's requests run in order, each answered before
the next, while requests from other connections go between them.  So
`command.wait_complete` holds up only its own connection, and a program
that must stay responsive either waits on a second connection or never
waits: `command.wait_complete` with a timeout of 0 returns at once, with
`-1` if the command is still running.  An error goes to whichever
connection reads `error_channel.poll` first.

The tool table and the programs are sent as text, since the files are
in the target.  The INI file is fixed (three axes, X 18, Y 9 and Z 16
inches of travel).  The meanings of the
`stat` attributes and `command` methods are LinuxCNC's, in its [Python
interface](https://linuxcnc.org/docs/2.9/html/config/python-interface.html).

`lcnc_client.py` is a small Python client, and
`demo_linuxcnc.py` shows a whole session: machine on,
homing, MDI, and running a program.

## Why the Installation Is Small

The main LinuxCNC package also provides a Graphical User Interface (GUI)
that is not need for simulation purposes.  Since only the simulator is
accessed there the huge set of packages needed to support a graphical
user interface are not fetched.  This results in a large time saving:
* Download Time: 18 seconds vs. 145 seconds.
* Download Storage: 130 MB vs. 1421 MB

## Probe runs

`.github/workflows/probe_linuxcnc.yml`, run by hand, installs and runs
`demo_linuxcnc` on `ubuntu-latest` and `windows-latest`.

## License

MIT No Attribution (`LICENSE`).
