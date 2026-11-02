"""Tests of `lcnc_panel.py` that need no LinuxCNC or window."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

import lcnc_headless
import lcnc_panel
import shops
from lcnc_client import SCBridgeError

# The constants that `FakeClient` answers with.
IDLE = 1
RUNNING = 2
MODE_MDI = 3
STATE_ON = 4


class TestToolSpeeds(unittest.TestCase):
    """The tools' speeds and feeds, as the Tools window lists them."""

    def setUp(self) -> None:
        self.shop = shops.read(lcnc_panel.SHOP_FILE)

    def test_materials(self) -> None:
        """The chooser lists the shop's materials."""
        names = lcnc_panel.material_names(self.shop)
        self.assertIn("6061 aluminum", names)
        self.assertIn("hdpe", names)

    def test_table(self) -> None:
        """One line per loaded tool."""
        text = lcnc_panel.tool_speeds(
            self.shop, lcnc_panel.SHOP_MACHINE, "steel"
        )
        self.assertIn("cutting steel", text)
        self.assertIn("1630   6.5     6.5  15/64 in HSS jobber drill", text)

    def test_problem(self) -> None:
        """A problem is shown in place of the table."""
        text = lcnc_panel.tool_speeds(
            self.shop, lcnc_panel.SHOP_MACHINE, "unobtainium"
        )
        self.assertIn('"unobtainium" is not one of', text)


# pylint: disable-next=too-many-instance-attributes
class FakeClient:
    """Stands in for `lcnc_client.SCClient`, and records the calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.errors: list[Any] = []
        self.finished = True
        self.interp_state = IDLE
        self.values: dict[str, Any] = {
            "actual_position": [5.0, 6.0, -1.0],
            "axis": [{}, {}, {"max_position_limit": 0.0}],
            "file": "",
            "g5x_offset": [4.0, 3.0, -6.0],
            "g92_offset": [0.0, 0.0, 0.0],
            "homed": [1, 1, 1],
            "joints": 3,
            "motion_line": 7,
            "paused": False,
            "task_mode": MODE_MDI,
            "task_state": STATE_ON,
            "tool_in_spindle": 8,
            "tool_offset": [0.0, 0.0, 2.0],
        }

    def call(self, name: str, *args: Any) -> Any:
        """Record a call, and answer it."""
        if name == "error_channel.poll":
            return self.errors.pop(0) if self.errors else None
        self.calls.append((name, *args))
        if name == "program.write":
            return f"/server/programs/{args[0]}"
        if name == "program.read":
            return "G0 X1\nM2\n"
        if name == "command.wait_complete":
            return 1 if self.finished else -1
        return None

    def stat(self, *names: str) -> dict[str, Any]:
        """Return the values asked for."""
        self.values["interp_state"] = self.interp_state
        return {name: self.values[name] for name in names}

    def sent(self, name: str) -> list[tuple[Any, ...]]:
        """Return the arguments of each call with this name."""
        return [call[1:] for call in self.calls if call[0] == name]


def client_machine() -> tuple[lcnc_panel.SCPanelMachine, FakeClient]:
    """Return a machine connected to a `FakeClient`."""
    machine = lcnc_panel.SCPanelMachine(True)
    lcnc = FakeClient()
    machine.lcnc = cast(Any, lcnc)
    machine.constants = {
        "INTERP_IDLE": IDLE,
        "MODE_MDI": MODE_MDI,
        "STATE_ON": STATE_ON,
    }
    return machine, lcnc


class TestConnecting(unittest.TestCase):
    """Reaching `serve_linuxcnc`."""

    def test_nobody_there(self) -> None:
        """No server says how to start one."""
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        with self.assertRaisesRegex(RuntimeError, "serve_linuxcnc"):
            lcnc_panel.SCPanelMachine(False, port)

    def test_old_server(self) -> None:
        """A server of an older protocol says what to do."""
        client = mock.MagicMock()
        client.call.return_value = {"protocol": 1}
        with (
            mock.patch.object(lcnc_panel, "SCClient", return_value=client),
            self.assertRaisesRegex(RuntimeError, "install_linuxcnc"),
        ):
            lcnc_panel.SCPanelMachine(False)


class TestStart(unittest.TestCase):
    """Getting a LinuxCNC ready."""

    def test_new_linuxcnc(self) -> None:
        """A new one is turned on and homed, with the origin and tools."""
        machine, lcnc = client_machine()
        lcnc.values["homed"] = [0, 0, 0]
        lcnc.values["task_state"] = 1
        real = lcnc.call

        def call(name: str, *args: Any) -> Any:
            if name == "command.state":
                lcnc.values["task_state"] = STATE_ON
            if name == "command.home":
                lcnc.values["homed"] = [1, 1, 1]
            return real(name, *args)

        lcnc.call = call  # type: ignore[method-assign]
        machine.start()
        self.assertEqual(lcnc.sent("command.home"), [(-1,)])
        self.assertEqual(len(lcnc.sent("command.state")), 2)
        self.assertEqual(
            lcnc.sent("command.mdi"), [("G20 G10 L2 P1 X4.0 Y3.0 Z-6.0",)]
        )
        table = lcnc.sent("tool_table.write")[0][0]
        self.assertTrue(table.startswith("T"), table)
        self.assertEqual(len(lcnc.sent("command.load_tool_table")), 1)

    def test_running_linuxcnc(self) -> None:
        """One already homed keeps its origin, and gets the tools."""
        machine, lcnc = client_machine()
        machine.start()
        self.assertEqual(lcnc.sent("command.home"), [])
        self.assertEqual(lcnc.sent("command.state"), [])
        self.assertEqual(lcnc.sent("command.mdi"), [])
        self.assertEqual(len(lcnc.sent("tool_table.write")), 1)

    def test_program_running(self) -> None:
        """One running a program is left alone."""
        machine, lcnc = client_machine()
        lcnc.interp_state = RUNNING
        machine.start()
        self.assertEqual(lcnc.calls, [])


class TestPrograms(unittest.TestCase):
    """Programs go over the wire, whole."""

    def test_open_sends_the_text(self) -> None:
        """The file's text is sent, and the server's path opened."""
        machine, lcnc = client_machine()
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory, "part.ngc")
            file.write_text("G0 X1\nM2\n", encoding="utf-8")
            machine.open(str(file))
        self.assertEqual(
            lcnc.sent("program.write"), [("part.ngc", "G0 X1\nM2\n")]
        )
        self.assertEqual(
            lcnc.sent("command.program_open"),
            [("/server/programs/part.ngc",)],
        )

    def test_open_missing_file(self) -> None:
        """A file that is not there is refused here."""
        machine, lcnc = client_machine()
        with self.assertRaises(FileNotFoundError):
            machine.open("/no/such/file.ngc")
        self.assertEqual(lcnc.calls, [])

    def test_lines_come_from_the_server(self) -> None:
        """The panel shows what LinuxCNC has open."""
        machine, _ = client_machine()
        self.assertEqual(machine.program_lines("/x.ngc"), ["G0 X1", "M2"])

    def test_lines_of_an_unreadable_program(self) -> None:
        """A program the server will not give shows no lines."""
        machine, lcnc = client_machine()
        lcnc.call = mock.MagicMock(  # type: ignore[method-assign]
            side_effect=SCBridgeError("ValueError", "no")
        )
        self.assertEqual(machine.program_lines("/x.ngc"), [])


class TestMdi(unittest.TestCase):
    """MDI lines never hold the panel up."""

    def test_home_goes_a_line_at_a_time(self) -> None:
        """Each line waits for the one before it to finish."""
        machine, lcnc = client_machine()
        machine.go_origin(-1.0)
        first = "G20 G90 G0 Z0.0000"
        self.assertEqual(lcnc.sent("command.mdi"), [(first,)])

        # The first is still moving.
        lcnc.interp_state = RUNNING
        self.assertEqual(machine.status().state, "running")
        self.assertEqual(len(lcnc.sent("command.mdi")), 1)

        # The interpreter is idle, but LinuxCNC has not finished.
        lcnc.interp_state = IDLE
        lcnc.finished = False
        self.assertEqual(machine.status().state, "running")
        self.assertEqual(len(lcnc.sent("command.mdi")), 1)

        # Finished: the next ones, and then it reads as idle.
        lcnc.finished = True
        self.assertEqual(machine.status().state, "running")
        self.assertEqual(machine.status().state, "running")
        self.assertEqual(
            lcnc.sent("command.mdi"),
            [(first,), ("G0 X0 Y0",), ("G0 Z0",)],
        )
        self.assertEqual(machine.status().state, "idle")

    def test_a_message_drops_the_rest(self) -> None:
        """Lines after one that failed are not run."""
        machine, lcnc = client_machine()
        machine.go_origin(0.0)
        lcnc.errors = [[1, "Can't do that"]]
        self.assertEqual(machine.status().state, "idle")
        self.assertEqual(len(lcnc.sent("command.mdi")), 1)

    def test_reset_drops_the_rest(self) -> None:
        """Reset stops the lines still waiting."""
        machine, lcnc = client_machine()
        machine.go_origin(0.0)
        machine.stop()
        self.assertEqual(lcnc.sent("command.abort"), [()])
        machine.status()
        self.assertEqual(len(lcnc.sent("command.mdi")), 1)

    def test_refused_while_running(self) -> None:
        """LinuxCNC staying out of MDI mode says what to do."""
        machine, lcnc = client_machine()
        lcnc.values["task_mode"] = MODE_MDI + 1
        with self.assertRaisesRegex(RuntimeError, "Reset"):
            machine.mdi("G0 X1")
        self.assertEqual(lcnc.sent("command.mdi"), [])


class TestResume(unittest.TestCase):
    """Resuming a paused program."""

    def test_mode_is_left_alone(self) -> None:
        """Setting the mode while paused would end the program."""
        machine, lcnc = client_machine()
        machine.resume()
        self.assertEqual(lcnc.sent("command.mode"), [])
        self.assertEqual(len(lcnc.sent("command.auto")), 1)


class TestStatus(unittest.TestCase):
    """What a poll shows."""

    def test_work_position(self) -> None:
        """The position has the offsets taken off."""
        machine, _ = client_machine()
        status = machine.status()
        self.assertEqual(status.position, (1.0, 3.0, 3.0))
        self.assertEqual((status.line, status.tool), (7, 8))

    def test_paused(self) -> None:
        """A paused program reads as paused."""
        machine, lcnc = client_machine()
        lcnc.interp_state = RUNNING
        lcnc.values["paused"] = True
        self.assertEqual(machine.status().state, "paused")

    def test_travel_message(self) -> None:
        """LinuxCNC's travel error says how high work Z can go."""
        machine, lcnc = client_machine()
        lcnc.errors = [[1, "invalid params in linear command"]]
        self.assertIn("reach only 4.0000", machine.status().messages[0])


class TestMessages(unittest.TestCase):
    """LinuxCNC's messages, kept for the command port."""

    def test_messages(self) -> None:
        """Each message is kept, past the `status()` that read it."""
        machine, lcnc = client_machine()
        lcnc.errors = [[1, "first"]]
        machine.status()
        machine.status()
        self.assertEqual(machine.messages, ["first"])

        # The port shows them, and something when there are none.
        panel = mock.MagicMock(machine=machine)
        handle = lcnc_panel.SCPanel.handle
        self.assertEqual(handle(panel, "messages"), "messages: first")
        machine.messages = []
        self.assertEqual(handle(panel, "messages"), "messages: ")


class TestHeadless(unittest.TestCase):
    """The whole panel, with no display, pressed through its port's words."""

    def setUp(self) -> None:
        lcnc_panel.use_headless()
        lcnc_headless.ANSWERS.clear()
        lcnc_headless.ASKED.clear()
        self.machine = lcnc_panel.SCPanelMachine(True)
        self.root: Any = lcnc_headless.Tk()
        self.panel = lcnc_panel.SCPanel(
            cast(Any, self.root), self.machine, 10.0, None
        )
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.file = Path(scratch.name, "part.ngc")
        lines = ["G20", "T1 M6", "G0 X1", "T8 M6", "G0 X2", "M2"]
        self.file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def tick(self) -> dict[str, Any]:
        """Run the panel's next poll, and return what it shows."""
        self.root.run_one()
        return self.panel.show()

    def ask(self, line: str) -> str:
        """Send one line, as the command port would."""
        return self.panel.handle(line)

    def test_program_shows(self) -> None:
        """An opened program's lines come up in the coming window."""
        self.assertEqual(self.ask(f"open {self.file}"), "ok")
        self.assertEqual(self.tick()["coming"].split("\n")[0], "G20")
        self.assertEqual(self.machine.log[0], f"open {self.file}")

    def test_buttons_follow_the_run(self) -> None:
        """Start, Pause and Resume grey out as a person sees them."""
        self.ask(f"open {self.file}")
        buttons = self.tick()["buttons"]
        self.assertEqual(buttons["Pause"], "disabled")
        self.assertEqual(self.ask("press Pause"), "error: Pause is greyed out")

        self.assertEqual(self.ask("press Start"), "ok")
        buttons = self.tick()["buttons"]
        self.assertEqual(buttons["Start"], "disabled")
        self.assertEqual(buttons["+X"], "disabled")
        self.assertEqual(self.ask("press Start"), "error: Start is greyed out")

        self.assertEqual(self.ask("press Pause"), "ok")
        self.assertEqual(self.tick()["buttons"]["Resume"], "normal")
        self.assertEqual(self.ask("press Resume"), "ok")
        self.assertEqual(self.ask("press Reset"), "ok")
        self.assertEqual(self.tick()["buttons"]["Start"], "normal")
        self.assertEqual(
            [entry for entry in self.machine.log if "open" not in entry],
            ["run 0", "pause", "resume", "stop"],
        )

    def test_tool_buttons(self) -> None:
        """+Tool and -Tool move the start line, and the coming window."""
        self.ask(f"open {self.file}")
        self.tick()
        self.ask("press +Tool")
        self.ask("press +Tool")
        self.assertEqual(self.tick()["coming"].split("\n")[0], "T8 M6")
        self.ask("press -Tool")
        self.assertEqual(self.tick()["coming"].split("\n")[0], "T1 M6")
        self.ask("press Start")
        self.assertEqual(self.machine.log[-1], "run 2")

    def test_mdi_line(self) -> None:
        """The MDI line is colored, and only good lines can run."""
        self.ask("type not a line")
        self.assertEqual(self.panel.show()["mdi_color"], lcnc_panel.BAD)
        self.assertIn("greyed out", self.ask("press Execute"))
        self.ask("type G0 X1")
        self.assertEqual(self.panel.show()["mdi_color"], lcnc_panel.GOOD)
        self.assertEqual(self.ask("press Execute"), "ok")
        self.assertEqual(self.machine.log[-1], "mdi G0 X1")

    def test_jog_step(self) -> None:
        """A step button chooses the step, and a jog button moves."""
        self.assertEqual(self.ask("press .01"), "ok")
        self.assertEqual(self.panel.show()["step"], ".01")
        self.assertEqual(self.ask("press -Z"), "ok")
        self.assertEqual(self.machine.log[-1], "jog Z -1")

    def test_set_origin_asks(self) -> None:
        """Set Origin does nothing unless the answer is yes."""
        self.machine.status = mock.MagicMock(  # type: ignore[method-assign]
            return_value=lcnc_panel.SCStatus("", 0, (1.0, 0.0, 0.0), 0, [], "")
        )
        self.tick()
        self.assertEqual(self.ask("press Set Origin"), "ok")
        self.assertNotIn("mdi G10 L20 P1 X0 Y0 Z0", self.machine.log)
        self.assertIn("Set Origin", lcnc_headless.ASKED[0])
        self.ask("answer yes")
        self.ask("press Set Origin")
        self.assertIn("mdi G10 L20 P1 X0 Y0 Z0", self.machine.log)

    def test_open_button(self) -> None:
        """Open takes the file answered, or none."""
        self.assertEqual(self.ask("press Open"), "ok")
        self.assertEqual(self.machine.log, [])
        self.ask(f"answer {self.file}")
        self.ask("press Open")
        self.assertEqual(self.machine.log, [f"open {self.file}"])

    def test_tools_window(self) -> None:
        """Tools opens a window that lists the tools for a material."""
        self.ask("press Tools")
        texts = self.panel.show()["texts"]
        self.assertIn("cutting 6061 aluminum", texts[-1])

    def test_speed(self) -> None:
        """The speed stays in the slider's range, and is shown."""
        self.ask("speed 500")
        self.assertEqual(self.panel.show()["speed"], "10x")
        self.assertEqual(self.machine.log[-1], "speed 10.00")

    def test_quit_button(self) -> None:
        """Quit closes the window, which ends the panel."""
        self.assertTrue(self.root.alive)
        self.assertEqual(self.ask("press Quit"), "ok")
        self.assertFalse(self.root.alive)

    def test_unknown(self) -> None:
        """A word or button it does not know is an error."""
        self.assertIn("unknown", self.ask("dance"))
        self.assertIn("no button", self.ask("press Nope"))

    def test_lost_server(self) -> None:
        """A LinuxCNC that goes away is shown; the panel keeps polling."""
        self.machine.status = mock.MagicMock(  # type: ignore[method-assign]
            side_effect=BrokenPipeError("gone")
        )
        self.assertIn("not answering", self.tick()["message"])
        self.assertTrue(self.root.due)


class TestHeadlessProgram(unittest.TestCase):
    """The program itself, with no display and no `tkinter`."""

    def test_runs_without_tkinter(self) -> None:
        """`--headless` starts, answers its port, and quits cleanly."""
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        environment = {
            key: value for key, value in os.environ.items() if key != "DISPLAY"
        }
        code = (
            "import sys; sys.modules['tkinter'] = None; "
            "import lcnc_panel; "
            "sys.exit(lcnc_panel.main(sys.argv[1:]))"
        )
        with subprocess.Popen(
            [sys.executable, "-c", code, "--headless", "--dry-run",
             "--port", str(port)],
            stderr=subprocess.PIPE,
            env=environment,
        ) as panel:  # fmt: skip
            try:
                self.assertIn("buttons", json.loads(ask_port(port, "show")))
                self.assertEqual(ask_port(port, "quit"), "ok")
                self.assertEqual(panel.wait(timeout=10.0), 0)
            finally:
                panel.kill()
            assert panel.stderr is not None
            self.assertEqual(panel.stderr.read(), b"")

    def test_refuses_without_tkinter(self) -> None:
        """With no `tkinter`, a window can not open, and it says so."""
        code = (
            "import sys; sys.modules['tkinter'] = None; "
            "import lcnc_panel; "
            "sys.exit(lcnc_panel.main(['--dry-run']))"
        )
        done = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        self.assertEqual(done.returncode, 1)
        self.assertIn("tkinter is not installed", done.stderr)


def ask_port(port: int, line: str) -> str:
    """Send a line to a panel's port, waiting for it to start."""
    end = time.monotonic() + 20.0
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), 5.0) as port_:
                port_.sendall(f"{line}\n".encode())
                return port_.makefile().readline().strip()
        except ConnectionRefusedError:
            if time.monotonic() > end:
                raise
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
