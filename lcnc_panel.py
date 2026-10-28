#!/usr/bin/env python3
"""A minimal LinuxCNC control panel, in place of AXIS (`T.mlcp~3.4`).

A small `tkinter` window that drives the LinuxCNC back end through its
Python API: three G-code windows (executed, a few editable lines run
as MDI when paused, coming next), six jog buttons, Run, Pause, Stop,
Open, Set Origin, a speed slider (the feed override), and the work
position and tool in the spindle.  The LinuxCNC calls are kept in
`Machine`, which imports `linuxcnc` (through `sim_linuxcnc`) only when
it connects, so the window can be built and tested where LinuxCNC is
not installed (it exists only in the `lcnc` box).

`lcnc_sim/shop_mill.ini` names it as its `[DISPLAY] DISPLAY`, so
LinuxCNC starts it (with `-ini FILE`), and closing it closes LinuxCNC
quietly.  When it starts, the machine is taken out of E-stop, turned
on and homed, and the INI file's `MAX_FEED_OVERRIDE` limits the
slider:

```
distrobox enter lcnc -- linuxcnc lcnc_sim/shop_mill.ini
./lcnc_panel.py --dry-run demo.ngc      # The window alone.
```

A program is opened from the command line (`DISPLAY = ... PROGRAM` in
the INI file, or by hand), with Open, or through the command port
(`--port PORT`, on 127.0.0.1), which takes one line per connection and
answers one line: `ping`, `open FILE`, `run`, `pause`, `stop`,
`speed X`, `status` or `quit`:

```
echo "open demo.ngc" | nc -q 1 127.0.0.1 5007
```
"""

import argparse
import functools
import importlib
import signal
import socket
import sys
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

# How far one press of a jog button moves (inches), and how fast
# (inches per second).
JOG_STEP: float = 0.1
JOG_SPEED: float = 1.0

# How often the panel polls LinuxCNC and the command port
# (milliseconds).
POLL_MS: int = 100

# The highest speed slider setting when the INI file has none.
MAX_SPEED: float = 10.0

# How many lines the executed and coming windows show.
SHOWN: int = 6


# Class `Status`:
@dataclass(slots=True)
class Status:
    """What the panel shows of the machine, from one poll.

    Attributes:
    * `file` (`str`): The open program ("" for none).
    * `line` (`int`): The line being run (counted from 1; 0 for none).
    * `position` (`tuple[float, float, float]`): X, Y and Z, in work
      coordinates (inches).
    * `tool` (`int`): The T number in the spindle (0 for none).
    * `messages` (`list[str]`): LinuxCNC's new error messages.

    Constructor:
    * `Status(file, line, position, tool, messages)`
    """

    # Constructor arguments:
    file: str = field(init=True)
    line: int = field(init=True)
    position: tuple[float, float, float] = field(init=True)
    tool: int = field(init=True)
    messages: list[str] = field(init=True)


# Class `Machine`:
class Machine:
    """The LinuxCNC back end, as the panel sees it.

    With `dry_run`, nothing is sent anywhere and every call only
    records what it would have done, so the window can be built and
    tested without LinuxCNC.

    Attributes:
    * `dry_run` (`bool`): True when no LinuxCNC is used.
    * `file` (`str`): The program opened (kept for a dry run).
    * `linuxcnc` (`Any`): The `linuxcnc` module, or `None`.
    * `log` (`list[str]`): What was asked of the machine, in order.
    * `sim` (`Any`): A `sim_linuxcnc.Simulator`, or `None`.
    """

    # Method `Machine.__init__()`:
    def __init__(self, dry_run: bool) -> None:
        """Connect to LinuxCNC, unless `dry_run`.

        Arguments:
        * `dry_run` (`bool`):
          True to use no LinuxCNC at all.
        """
        self.dry_run: bool = dry_run
        self.file: str = ""
        self.log: list[str] = []
        self.linuxcnc: Any = None
        self.sim: Any = None

        # Import `linuxcnc` only here, since only the `lcnc` box has it.
        if not dry_run:
            self.linuxcnc = importlib.import_module("linuxcnc")
            self.sim = importlib.import_module("sim_linuxcnc").Simulator()

    # Method `Machine._mode()`:
    def _mode(self, name: str) -> None:
        """Switch LinuxCNC to a mode (`MODE_AUTO`, `MODE_MDI`, ...).

        Arguments:
        * `name` (`str`):
          The name of the mode constant in `linuxcnc`.
        """
        if self.sim is not None:
            self.sim.command.mode(getattr(self.linuxcnc, name))
            self.sim.command.wait_complete()

    # Method `Machine.start()`:
    def start(self) -> None:
        """Take it out of E-stop, turn it on and home it."""
        self.log.append("start")
        if self.sim is not None:
            self.sim.home()

    # Method `Machine.max_speed()`:
    def max_speed(self, ini_file: str) -> float:
        """Return the highest feed override the INI file allows.

        Arguments:
        * `ini_file` (`str`): The INI file ("" for LinuxCNC's own).

        Returns:
        * (`float`): Its `[DISPLAY] MAX_FEED_OVERRIDE`, or
          `MAX_SPEED` when there is none.
        """
        if self.sim is None:
            return MAX_SPEED
        if not ini_file:
            self.sim.stat.poll()
            ini_file = self.sim.stat.ini_filename
        found: str | None = self.linuxcnc.ini(ini_file).find(
            "DISPLAY", "MAX_FEED_OVERRIDE"
        )
        return float(found) if found else MAX_SPEED

    # Method `Machine.open()`:
    def open(self, path: str) -> None:
        """Open a program, ready to run from its start.

        Arguments:
        * `path` (`str`): The G-code file (a relative path is from
          the panel's directory: `lcnc_sim/` when LinuxCNC starts it).

        Raises:
        * `FileNotFoundError`: If there is no such file.
        """
        if not Path(path).is_file():
            raise FileNotFoundError(f"no file {path}")
        self.file = str(Path(path).resolve())
        self.log.append(f"open {self.file}")
        if self.sim is not None:
            self._mode("MODE_AUTO")
            self.sim.command.program_open(self.file)
            self.sim.command.wait_complete()

    # Method `Machine.run()`:
    def run(self) -> None:
        """Run the open program from its start."""
        self.log.append("run")
        if self.sim is not None:
            self._mode("MODE_AUTO")
            self.sim.command.auto(self.linuxcnc.AUTO_RUN, 0)

    # Method `Machine.pause()`:
    def pause(self) -> None:
        """Pause the running program."""
        self.log.append("pause")
        if self.sim is not None:
            self.sim.command.auto(self.linuxcnc.AUTO_PAUSE)

    # Method `Machine.resume()`:
    def resume(self) -> None:
        """Resume a paused program."""
        self.log.append("resume")
        if self.sim is not None:
            self._mode("MODE_AUTO")
            self.sim.command.auto(self.linuxcnc.AUTO_RESUME)

    # Method `Machine.stop()`:
    def stop(self) -> None:
        """Stop at once (`command.abort()`)."""
        self.log.append("stop")
        if self.sim is not None:
            self.sim.stop()

    # Method `Machine.mdi()`:
    def mdi(self, line: str) -> None:
        """Run one line of G-code as a manual (MDI) command.

        Arguments:
        * `line` (`str`):
          The G-code line.
        """
        self.log.append(f"mdi {line}")
        if self.sim is not None:
            self._mode("MODE_MDI")
            self.sim.command.mdi(line)
            self.sim.command.wait_complete()

    # Method `Machine.set_origin()`:
    def set_origin(self) -> None:
        """Make the current position the program's zero (G54)."""
        self.mdi("G10 L20 P1 X0 Y0 Z0")

    # Method `Machine.jog()`:
    def jog(self, axis: int, direction: int) -> None:
        """Jog one axis by one `JOG_STEP`.

        Arguments:
        * `axis` (`int`):
          The axis: 0 for X, 1 for Y, 2 for Z.
        * `direction` (`int`):
          +1 or -1.
        """
        self.log.append(f"jog {'XYZ'[axis]} {direction:+d}")
        if self.sim is not None:
            self._mode("MODE_MANUAL")
            self.sim.command.teleop_enable(True)
            self.sim.command.jog(
                self.linuxcnc.JOG_INCREMENT,
                False,
                axis,
                JOG_SPEED,
                direction * JOG_STEP,
            )

    # Method `Machine.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override.

        Arguments:
        * `speed` (`float`):
          The feed override (1.0 is the programmed feed).
        """
        self.log.append(f"speed {speed:.2f}")
        if self.sim is not None:
            self.sim.command.feedrate(speed)

    # Method `Machine.status()`:
    def status(self) -> Status:
        """Poll LinuxCNC.

        Returns:
        * (`Status`): The program, line, position, tool and messages.
        """
        if self.sim is None:
            return Status(self.file, 0, (0.0, 0.0, 0.0), 0, [])
        stat: Any = self.sim.stat
        stat.poll()
        messages: list[str] = []
        error: Any = self.sim.errors.poll()
        while error:
            messages.append(str(error[1]))
            error = self.sim.errors.poll()
        return Status(
            str(stat.file),
            int(stat.motion_line),
            self.sim.work_position(),
            int(stat.tool_in_spindle),
            messages,
        )


# Class `CommandPort`:
class CommandPort:  # pylint: disable=too-few-public-methods
    """A command port on 127.0.0.1: one line in, one line back.

    Attributes:
    * `server` (`socket.socket`): The listening socket (not blocking).
    """

    # Method `CommandPort.__init__()`:
    def __init__(self, port: int) -> None:
        """Listen on a port.

        Arguments:
        * `port` (`int`): The port.
        """
        self.server: socket.socket = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", port))
        self.server.listen()
        self.server.setblocking(False)

    # Method `CommandPort.poll()`:
    def poll(self, handle: Any) -> None:
        """Answer each waiting connection.

        Arguments:
        * `handle` (`Callable[[str], str]`): Answers a command line.
        """
        while True:
            try:
                connection: socket.socket = self.server.accept()[0]
            except BlockingIOError:
                return
            with connection:
                connection.settimeout(1.0)
                try:
                    data: bytes = b""
                    while b"\n" not in data:
                        chunk: bytes = connection.recv(1024)
                        if not chunk:
                            break
                        data += chunk
                    line: str = data.decode(errors="replace").strip()
                    connection.sendall((handle(line) + "\n").encode())
                except OSError:
                    pass


# Class `Panel`:
class Panel:  # pylint: disable=too-many-instance-attributes
    """The control panel window, laid out as in `T.mlcp~3.4`.

    Attributes:
    * `coming` (`tk.Text`): The G-code coming next (read only).
    * `edit` (`tk.Text`): A few lines of G-code, run when paused.
    * `executed` (`tk.Text`): The G-code already run (read only).
    * `lines` (`list[str]`): The open program's lines.
    * `lines_button` (`ttk.Button`): Runs the editable lines.
    * `lines_file` (`str`): The file `lines` was read from.
    * `machine` (`Machine`): The LinuxCNC back end.
    * `message` (`ttk.Label`): LinuxCNC's last error message.
    * `paused` (`bool`): True while the program is paused.
    * `pause_button` (`ttk.Button`): The Pause button.
    * `port` (`CommandPort | None`): The command port, if any.
    * `position` (`ttk.Label`): The work position and the tool.
    * `root` (`tk.Tk`): The window.
    * `run_button` (`ttk.Button`): The Run button.
    * `speed` (`tk.DoubleVar`): The speed slider's value.
    """

    # Method `Panel.__init__()`:
    def __init__(
        self,
        root: tk.Tk,
        machine: Machine,
        max_speed: float,
        port: CommandPort | None,
    ) -> None:
        """Build the window.

        Arguments:
        * `root` (`tk.Tk`):
          The window to build in.
        * `machine` (`Machine`):
          The LinuxCNC back end.
        * `max_speed` (`float`):
          The speed slider's highest setting.
        * `port` (`CommandPort | None`):
          The command port, if any.
        """
        self.root: tk.Tk = root
        self.machine: Machine = machine
        self.port: CommandPort | None = port
        self.paused: bool = False
        self.lines: list[str] = []
        self.lines_file: str = ""
        root.title("LinuxCNC Panel")

        # The three G-code windows, one above another.
        self.executed: tk.Text = tk.Text(root, height=SHOWN, width=50)
        self.edit: tk.Text = tk.Text(root, height=3, width=50)
        self.coming: tk.Text = tk.Text(root, height=SHOWN, width=50)
        for row, text in enumerate((self.executed, self.edit, self.coming)):
            text.grid(row=row, column=0, padx=4, pady=2, sticky="ew")
        self.executed.configure(state="disabled")
        self.coming.configure(state="disabled")

        # The work position and the tool, and LinuxCNC's messages.
        self.position: ttk.Label = ttk.Label(root, font="TkFixedFont")
        self.position.grid(row=3, column=0, padx=4, sticky="w")
        self.message: ttk.Label = ttk.Label(root, foreground="red")
        self.message.grid(row=4, column=0, padx=4, sticky="w")

        # The jog buttons: X side by side, Y diagonal to their right,
        # Z one above the other at the far right.
        jog: ttk.Frame = ttk.Frame(root)
        jog.grid(row=5, column=0, pady=6)
        places: tuple[tuple[str, int, int, int, int], ...] = (
            ("-X", 0, 1, 0, -1),
            ("+X", 1, 1, 0, +1),
            ("+Y", 3, 0, 1, +1),
            ("-Y", 2, 2, 1, -1),
            ("+Z", 5, 0, 2, +1),
            ("-Z", 5, 2, 2, -1),
        )
        for label, column, row, axis, direction in places:
            ttk.Button(
                jog,
                text=label,
                width=4,
                command=functools.partial(self.machine.jog, axis, direction),
            ).grid(row=row, column=column, padx=2, pady=2)
        jog.columnconfigure(4, minsize=60)

        # Open, Run, Pause, Run Lines, Stop and Set Origin.
        buttons: ttk.Frame = ttk.Frame(root)
        buttons.grid(row=6, column=0, pady=4, sticky="ew")
        self.run_button: ttk.Button = ttk.Button(
            buttons, text="Run", command=self.on_run
        )
        self.pause_button: ttk.Button = ttk.Button(
            buttons, text="Pause", command=self.on_pause, state="disabled"
        )
        self.lines_button: ttk.Button = ttk.Button(
            buttons, text="Run Lines", command=self.on_lines, state="disabled"
        )
        ttk.Button(buttons, text="Open", command=self.on_open).grid(
            row=0, column=0, padx=2
        )
        self.run_button.grid(row=0, column=1, padx=2)
        self.pause_button.grid(row=0, column=2, padx=2)
        self.lines_button.grid(row=0, column=3, padx=2)
        ttk.Button(buttons, text="Stop", command=self.on_stop).grid(
            row=0, column=4, padx=2
        )
        buttons.columnconfigure(5, weight=1)
        ttk.Button(
            buttons, text="Set Origin", command=self.on_set_origin
        ).grid(row=0, column=6, padx=2)

        # The speed slider, under all of the buttons.
        self.speed: tk.DoubleVar = tk.DoubleVar(value=1.0)
        slider: ttk.Frame = ttk.Frame(root)
        slider.grid(row=7, column=0, pady=4, sticky="ew")
        ttk.Label(slider, text="speed").pack(side="left", padx=4)
        ttk.Scale(
            slider,
            from_=0.0,
            to=max_speed,
            orient="horizontal",
            variable=self.speed,
            command=lambda _value: self.machine.set_speed(self.speed.get()),
        ).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(slider, textvariable=self.speed, width=5).pack(side="left")
        root.after(POLL_MS, self.poll)

    # Method `Panel.set_text()`:
    @staticmethod
    def set_text(text: tk.Text, lines: list[str]) -> None:
        """Replace the contents of a read only text window.

        Arguments:
        * `text` (`tk.Text`):
          The text window.
        * `lines` (`list[str]`):
          Its new lines.
        """
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    # Method `Panel.set_running()`:
    def set_running(self, running: bool, paused: bool) -> None:
        """Grey out the buttons that can not be pressed now.

        Arguments:
        * `running` (`bool`): True while a program runs (or is paused).
        * `paused` (`bool`): True while it is paused.
        """
        self.paused = paused
        self.run_button.configure(
            state="disabled" if running and not paused else "normal"
        )
        self.pause_button.configure(
            state="normal" if running and not paused else "disabled"
        )
        self.lines_button.configure(state="normal" if paused else "disabled")

    # Method `Panel.open()`:
    def open(self, path: str) -> None:
        """Open a program.

        Arguments:
        * `path` (`str`): The G-code file.
        """
        self.machine.open(path)
        self.set_running(False, False)

    # Method `Panel.on_open()`:
    def on_open(self) -> None:
        """Choose a program with a file window, and open it."""
        path: str = filedialog.askopenfilename(
            title="Open G-code",
            filetypes=[("G-code", "*.ngc *.nc *.gcode"), ("All", "*")],
        )
        if path:
            self.open(path)

    # Method `Panel.on_run()`:
    def on_run(self) -> None:
        """Run the program, or resume it after a pause."""
        if self.paused:
            self.machine.resume()
        else:
            self.machine.run()
        self.set_running(True, False)

    # Method `Panel.on_pause()`:
    def on_pause(self) -> None:
        """Pause the program; the editable lines may then be run."""
        self.machine.pause()
        self.set_running(True, True)

    # Method `Panel.on_lines()`:
    def on_lines(self) -> None:
        """Run the editable lines as MDI, while paused."""
        line: str
        for line in self.edit.get("1.0", "end").splitlines():
            if line.strip():
                self.machine.mdi(line.strip())

    # Method `Panel.on_stop()`:
    def on_stop(self) -> None:
        """Stop at once, ready to run again."""
        self.machine.stop()
        self.set_running(False, False)

    # Method `Panel.on_set_origin()`:
    def on_set_origin(self) -> None:
        """Make the current position zero, after asking (No first)."""
        if messagebox.askyesno(
            "Set Origin",
            "Make the current position the program's zero?",
            default="no",
        ):
            self.machine.set_origin()

    # Method `Panel.handle()`:
    def handle(self, line: str) -> str:
        """Answer one command from the command port.

        Arguments:
        * `line` (`str`): The command.

        Returns:
        * (`str`): The answer: `ok`, the status, or `error: ...`.
        """
        word, _, rest = line.partition(" ")
        actions: dict[str, Any] = {
            "ping": lambda: None,
            "run": self.on_run,
            "pause": self.on_pause,
            "stop": self.on_stop,
            "quit": self.root.destroy,
        }
        try:
            if word in actions:
                actions[word]()
            elif word == "open" and rest:
                self.open(rest.strip())
            elif word == "speed" and rest:
                self.speed.set(float(rest))
                self.machine.set_speed(float(rest))
            elif word == "status":
                status: Status = self.machine.status()
                x, y, z = status.position
                return (
                    f"file={status.file} line={status.line} "
                    f"x={x:.4f} y={y:.4f} z={z:.4f} tool={status.tool}"
                )
            else:
                return f"error: unknown command {line!r}"
        except (ValueError, OSError) as error:
            return f"error: {error}"
        return "ok"

    # Method `Panel.poll()`:
    def poll(self) -> None:
        """Show the machine's state, answer the port, then poll again."""
        # The program around the line being run, read once per file.
        status: Status = self.machine.status()
        if status.file != self.lines_file:
            self.lines_file = status.file
            try:
                self.lines = (
                    Path(status.file).read_text(encoding="utf-8").splitlines()
                )
            except OSError:
                self.lines = []
        current: int = status.line
        self.set_text(
            self.executed, self.lines[max(0, current - SHOWN) : current]
        )
        self.set_text(self.coming, self.lines[current : current + SHOWN])

        # The position, the tool and any message.
        x, y, z = status.position
        self.position.configure(
            text=f"X {x:9.4f}  Y {y:9.4f}  Z {z:9.4f}  T{status.tool:02d}"
        )
        if status.messages:
            self.message.configure(text=status.messages[-1])

        # Commands from the port.
        if self.port is not None:
            self.port.poll(self.handle)
        self.root.after(POLL_MS, self.poll)


# Function `split_ini()`:
def split_ini(arguments: list[str]) -> tuple[str, list[str]]:
    """Take LinuxCNC's `-- -ini FILE` off the arguments.

    LinuxCNC starts its display as `DISPLAY ARGS... -- -ini FILE`
    (from the INI file's `[DISPLAY] DISPLAY` line).

    Arguments:
    * `arguments` (`list[str]`): The command line arguments.

    Returns:
    * (`tuple[str, list[str]]`): The INI file ("" for none) and the
      other arguments.
    """
    rest: list[str] = [word for word in arguments if word != "--"]
    if "-ini" in rest:
        index: int = rest.index("-ini")
        ini_file: str = rest[index + 1] if index + 1 < len(rest) else ""
        return ini_file, rest[:index] + rest[index + 2 :]
    return "", rest


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Show the panel until its window is closed.

    Arguments:
    * `arguments` (`list[str]`):
      The command line arguments, less the program name.

    Returns:
    * (`int`): The exit status.
    """
    # The command line, less LinuxCNC's `-ini FILE`.
    ini_file, arguments = split_ini(arguments)
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("program", nargs="?", help="G-code to open")
    parser.add_argument("--port", type=int, help="a command port on 127.0.0.1")
    parser.add_argument(
        "--dry-run", action="store_true", help="use no LinuxCNC"
    )
    options: argparse.Namespace = parser.parse_args(arguments)

    # The machine, on and homed, and the command port.
    machine: Machine = Machine(options.dry_run)
    machine.start()
    port: CommandPort | None = (
        CommandPort(options.port) if options.port else None
    )

    # The window.  A `SIGTERM` (`stop_linuxcnc.py`) closes it as the
    # window's close button does, so LinuxCNC shuts down quietly.
    root: tk.Tk = tk.Tk()
    panel: Panel = Panel(root, machine, machine.max_speed(ini_file), port)
    signal.signal(signal.SIGTERM, lambda *_: root.destroy())
    if options.program:
        panel.open(options.program)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
