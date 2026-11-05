"""Tests of `lcnc_hmi.py` that need no LinuxCNC or window."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from scraftcnc import shops
from scraftcnc.assembly import Assembly
from scraftcnc.demo import demo_assembly, with_setup
from scraftcnc.hmi import lcnc_hmi, lcnc_hmi_headless
from scraftcnc.lcnc.lcnc_client import BridgeError
from scraftcnc.setups import SHOP as EXAMPLE_SHOP
from scraftcnc.tooling.shop_registries import use_shop

# The constants that `FakeClient` answers with.
IDLE = 1
RUNNING = 2
MODE_MDI = 3
STATE_ON = 4


class TestToolSpeeds(unittest.TestCase):
    """The tools' speeds and feeds, as the Tools window lists them."""

    def setUp(self) -> None:
        self.shop = shops.read(lcnc_hmi.SHOP_FILE)

    def test_materials(self) -> None:
        """The chooser lists the shop's materials."""
        names = lcnc_hmi.material_names(self.shop)
        self.assertIn("6061 aluminum", names)
        self.assertIn("hdpe", names)

    def test_table(self) -> None:
        """One line per loaded tool."""
        text = lcnc_hmi.tool_speeds(self.shop, lcnc_hmi.SHOP_MACHINE, "steel")
        self.assertIn("cutting steel", text)
        self.assertIn("1630   6.5     6.5  15/64 in HSS jobber drill", text)

    def test_problem(self) -> None:
        """A problem is shown in place of the table."""
        text = lcnc_hmi.tool_speeds(
            self.shop, lcnc_hmi.SHOP_MACHINE, "unobtainium"
        )
        self.assertIn('"unobtainium" is not one of', text)


# pylint: disable-next=too-many-instance-attributes
class FakeClient:
    """Stands in for `lcnc_client.BridgeClient`, and records the calls."""

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


def client_machine() -> tuple[lcnc_hmi.HMIMachine, FakeClient]:
    """Return a machine connected to a `FakeClient`."""
    machine = lcnc_hmi.HMIMachine(True)
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
            lcnc_hmi.HMIMachine(False, port)

    def test_old_server(self) -> None:
        """A server of an older protocol says what to do."""
        client = mock.MagicMock()
        client.call.return_value = {"protocol": 1}
        with (
            mock.patch.object(lcnc_hmi, "BridgeClient", return_value=client),
            self.assertRaisesRegex(RuntimeError, "install_linuxcnc"),
        ):
            lcnc_hmi.HMIMachine(False)


class TestStart(unittest.TestCase):
    """Getting a LinuxCNC ready."""

    def test_new_linuxcnc(self) -> None:
        """A new one is turned on and homed, and gets the tools."""
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
        # No origin: each program gets its own (`mark_origin_set()`).
        self.assertEqual(lcnc.sent("command.mdi"), [])
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
        """The HMI shows what LinuxCNC has open."""
        machine, _ = client_machine()
        self.assertEqual(machine.program_lines("/x.ngc"), ["G0 X1", "M2"])

    def test_lines_of_an_unreadable_program(self) -> None:
        """A program the server will not give shows no lines."""
        machine, lcnc = client_machine()
        lcnc.call = mock.MagicMock(  # type: ignore[method-assign]
            side_effect=BridgeError("ValueError", "no")
        )
        self.assertEqual(machine.program_lines("/x.ngc"), [])


class TestMdi(unittest.TestCase):
    """MDI lines never hold the HMI up."""

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
        handle = lcnc_hmi.HMI.handle
        self.assertEqual(handle(panel, "messages"), "messages: first")
        machine.messages = []
        self.assertEqual(handle(panel, "messages"), "messages: ")


class TestHeadless(unittest.TestCase):
    """The whole panel, with no display, pressed through its port's words."""

    def setUp(self) -> None:
        lcnc_hmi.use_headless()
        lcnc_hmi_headless.ANSWERS.clear()
        lcnc_hmi_headless.ASKED.clear()
        self.machine = lcnc_hmi.HMIMachine(True)
        self.root: Any = lcnc_hmi_headless.Tk()
        self.panel = lcnc_hmi.HMI(
            cast(Any, self.root), self.machine, 10.0, None
        )
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.file = Path(scratch.name, "part.ngc")
        lines = ["G20", "T1 M6", "G0 X1", "T8 M6", "G0 X2", "M2"]
        self.file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def tick(self) -> dict[str, Any]:
        """Run the HMI's next poll, and return what it shows."""
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

    def open_with_origin(self) -> None:
        """Open the program, and set its origin where the tool is."""
        self.assertEqual(self.ask(f"open {self.file}"), "ok")
        self.ask("answer yes")
        self.assertEqual(self.ask("press Set Origin"), "ok")

    def test_origin_gate(self) -> None:
        """Start waits for the origin; jogs and MDI do not."""
        self.ask(f"open {self.file}")
        shown = self.tick()
        self.assertFalse(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "disabled")
        self.assertEqual(shown["buttons"]["+X"], "normal")
        self.assertEqual(shown["message"], "Set the origin first")
        self.ask("answer yes")
        self.ask("press Set Origin")
        shown = self.tick()
        self.assertTrue(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "normal")
        self.assertEqual(shown["message"], "")

        # Opening it again clears the mark.
        self.ask(f"open {self.file}")
        self.assertFalse(self.tick()["origin_set"])

    def test_buttons_follow_the_run(self) -> None:
        """Start, Pause and Resume grey out as a person sees them."""
        self.open_with_origin()
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
            [
                entry
                for entry in self.machine.log
                if not entry.startswith(("open", "tool table", "mdi"))
            ],
            ["run 0", "pause", "resume", "stop"],
        )

    def test_tool_buttons(self) -> None:
        """+Tool and -Tool move the start line, and the coming window."""
        self.open_with_origin()
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
        self.assertEqual(self.panel.show()["mdi_color"], lcnc_hmi.BAD)
        self.assertIn("greyed out", self.ask("press Execute"))
        self.ask("type G0 X1")
        self.assertEqual(self.panel.show()["mdi_color"], lcnc_hmi.GOOD)
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
            return_value=lcnc_hmi.HMIStatus("", 0, (1.0, 0.0, 0.0), 0, [], "")
        )
        self.tick()
        self.assertEqual(self.ask("press Set Origin"), "ok")
        self.assertNotIn("mdi G10 L20 P1 X0 Y0 Z0", self.machine.log)
        self.assertIn("Set Origin", lcnc_hmi_headless.ASKED[0])
        self.ask("answer yes")
        self.ask("press Set Origin")
        self.assertIn("mdi G10 L20 P1 X0 Y0 Z0", self.machine.log)

    def test_open_button(self) -> None:
        """Open takes the file answered, or none."""
        self.assertEqual(self.ask("press Open"), "ok")
        self.assertEqual(self.machine.log, [])
        self.ask(f"answer {self.file}")
        self.ask("press Open")
        self.assertEqual(
            self.machine.log,
            [f"open {self.file}", f"tool table {lcnc_hmi.MATERIAL}"],
        )

    def test_tools_tab(self) -> None:
        """The Tools tab lists the tools for a material."""
        self.ask("tab Tools")
        texts = self.panel.show()["texts"]
        self.assertIn("cutting 6061 aluminum", texts[-1])

    def test_tabs(self) -> None:
        """Each tab can be shown, and `show` says which one is."""
        self.assertEqual(self.panel.show()["tab"], "Run")
        for name in lcnc_hmi.TABS:
            self.assertEqual(self.ask(f"tab {name}"), "ok")
            self.assertEqual(self.panel.show()["tab"], name)
        self.assertIn("error: no tab Nope", self.ask("tab Nope"))

        # A button on another tab is still pressed by its label.
        self.ask("tab View")
        self.assertEqual(self.ask("press Home"), "ok")

    def test_labels_unique(self) -> None:
        """No two buttons, on any tab, have the same label."""
        labels: list[str] = [
            str(widget.cget("text"))
            for widget in self.panel.widgets()
            if widget.winfo_class() in lcnc_hmi.BUTTONS
        ]
        self.assertEqual(len(labels), len(set(labels)))

    def test_speed(self) -> None:
        """The speed stays in the slider's range, and is shown."""
        self.ask("speed 500")
        self.assertEqual(self.panel.show()["speed"], "10x")
        self.assertEqual(self.machine.log[-1], "speed 10.00")

    def test_quit_button(self) -> None:
        """Quit closes the window, which ends the HMI."""
        self.assertTrue(self.root.alive)
        self.assertEqual(self.ask("press Quit"), "ok")
        self.assertFalse(self.root.alive)

    def test_unknown(self) -> None:
        """A word or button it does not know is an error."""
        self.assertIn("unknown", self.ask("dance"))
        self.assertIn("no button", self.ask("press Nope"))

    def test_lost_server(self) -> None:
        """A LinuxCNC that goes away is shown; the HMI keeps polling."""
        self.machine.status = mock.MagicMock(  # type: ignore[method-assign]
            side_effect=BrokenPipeError("gone")
        )
        self.assertIn("not answering", self.tick()["message"])
        self.assertTrue(self.root.due)


# A stand-in, which needs only `show()`.
class FakeView:  # pylint: disable=too-few-public-methods
    """Stands in for `SetupView`: records each assembly shown."""

    def __init__(self, fail: bool = False) -> None:
        self.fail: bool = fail
        self.keep_outs: bool = False
        self.hidden: set[str] = set()
        self.progress: tuple[int, int] = (0, 0)
        self.keep_out_shows: list[bool] = []
        self.shown: list[Assembly] = []

    def show(self, assembly: Assembly) -> None:
        """Record an assembly, or fail."""
        if self.fail:
            raise ValueError("no such vise")
        self.shown.append(assembly)
        self.keep_out_shows.append("keep_out" not in self.hidden)


class TestSetupDrawing(unittest.TestCase):
    """Opening a program hands its `SCC:` setup to the drawer."""

    def setUp(self) -> None:
        use_shop(shops.read(EXAMPLE_SHOP))
        lcnc_hmi.use_headless()
        self.machine = lcnc_hmi.HMIMachine(True)
        self.root: Any = lcnc_hmi_headless.Tk()
        self.panel = lcnc_hmi.HMI(
            cast(Any, self.root), self.machine, 10.0, None
        )
        self.view = FakeView()
        self.panel.drawer = lcnc_hmi.SetupDrawer(self.view)
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.gcode = "G20\nG0 X1\nM2\n"

    def program(self, text: str) -> str:
        """Write a program, and return its path."""
        path = self.directory / "part.nc"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_setup_drawn(self) -> None:
        """A program with setup lines has its assembly drawn."""
        assembly = demo_assembly()
        self.panel.open(self.program(with_setup(self.gcode, assembly)))
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        self.assertEqual(len(self.view.shown), 1)
        names = [item.name for item in self.view.shown[0].items]
        self.assertEqual(names, [item.name for item in assembly.items])
        self.assertEqual(self.machine.file, self.program_path())

    def program_path(self) -> str:
        """Return the program's path, as opened."""
        return str(self.directory / "part.nc")

    def test_no_setup(self) -> None:
        """A program with no setup lines opens, and nothing is drawn."""
        self.panel.open(self.program(self.gcode))
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        self.assertEqual(self.view.shown, [])
        self.assertEqual(self.panel.show()["message"], "Set the origin first")

    def test_material_from_setup(self) -> None:
        """The setup's material picks the tool table and the Tools tab."""
        assembly = demo_assembly()
        assembly.items[-1].args["material"] = "brass"
        self.panel.open(self.program(with_setup(self.gcode, assembly)))
        self.assertIn("tool table brass", self.machine.log)
        self.assertEqual(self.panel.material.get(), "brass")
        self.root.run_one()
        self.assertIn("brass", self.panel.show()["position"])

    def test_material_fallback(self) -> None:
        """No setup, or a material the shop lacks: `MATERIAL` is used."""
        self.panel.open(self.program(self.gcode))
        self.assertEqual(
            self.machine.log[-1], f"tool table {lcnc_hmi.MATERIAL}"
        )
        assembly = demo_assembly()
        for item in assembly.items:
            if "material" in item.args:
                item.args["material"] = "unobtainium"
        self.panel.open(self.program(with_setup(self.gcode, assembly)))
        self.assertEqual(
            self.machine.log[-1], f"tool table {lcnc_hmi.MATERIAL}"
        )
        self.assertEqual(self.panel.material.get(), lcnc_hmi.MATERIAL)

    def test_origin_from_setup(self) -> None:
        """The demo's table and the shop's table place: (4, 3, -6) in."""
        assembly = demo_assembly()
        origin = lcnc_hmi.setup_origin(
            assembly, shops.read(EXAMPLE_SHOP), lcnc_hmi.SHOP_MACHINE
        )
        assert origin is not None
        for got, want in zip(origin, (4.0, 3.0, -6.0), strict=True):
            self.assertAlmostEqual(got, want, places=9)
        self.panel.open(self.program(with_setup(self.gcode, assembly)))
        self.assertIn("origin 4.0 3.0 -6.0", self.machine.log)
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        self.root.run_one()
        shown = self.panel.show()
        self.assertTrue(shown["origin_set"])
        self.assertEqual(shown["buttons"]["Start"], "normal")
        self.assertIn("Shop mill, 6061 aluminum", self.tick_position())

    def tick_position(self) -> str:
        """Run one poll, and return the position line."""
        self.root.run_one()
        return str(self.panel.show()["position"])

    def test_no_origin(self) -> None:
        """Without the table's place, no origin is worked out."""
        shop = shops.read(EXAMPLE_SHOP)
        self.assertIsNone(
            lcnc_hmi.setup_origin(demo_assembly(), shop, "Shop router")
        )
        self.assertIsNone(
            lcnc_hmi.setup_origin(Assembly([]), shop, lcnc_hmi.SHOP_MACHINE)
        )

    def test_other_machine(self) -> None:
        """A program for another machine is refused; the last stays."""
        self.panel.open(self.program(self.gcode))
        log = list(self.machine.log)
        assembly = demo_assembly()
        assembly.machine = "Shop router"
        other = self.directory / "other.nc"
        other.write_text(with_setup(self.gcode, assembly), encoding="utf-8")
        answer = self.panel.handle(f"open {other}")
        self.assertIn("Not opened: the program is for Shop router", answer)
        self.assertIn("Not opened", self.panel.show()["message"])
        self.assertEqual(self.machine.log, log)
        self.assertEqual(self.machine.file, self.program_path())
        self.assertIsNone(self.panel.assembly)

    def test_bad_setup(self) -> None:
        """A wrong setup line is reported; the program still opens."""
        self.panel.open(self.program("(SCC: [[item]\n" + self.gcode))
        self.assertIn("Setup not read", self.panel.show()["message"])
        self.assertEqual(self.view.shown, [])
        self.assertEqual(self.machine.file, self.program_path())

    def test_next_step(self) -> None:
        """Next Step shows one more item, with its note, then all."""
        assembly = demo_assembly()
        count = len(assembly.items)
        self.panel.open(self.program(with_setup(self.gcode, assembly)))
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        messages: list[str] = []
        step: int
        for step in range(1, count + 2):
            self.assertEqual(self.ask("press Next Step"), "ok")
            self.panel.drawer.wait()
            messages.append(self.panel.show()["message"])
            self.assertEqual(len(self.view.shown[-1].items), min(step, count))
        self.assertEqual(messages[0], "Step 1/7, mill table: Clean the table.")
        self.assertTrue(messages[count - 1].startswith("Step 7/7, demo"))
        self.assertEqual(messages[-1], "Setup: all 7 items.")
        self.assertTrue(all(item.note for item in assembly.items))

    def test_step_error(self) -> None:
        """A step's drawing error comes after its note."""
        self.panel.open(self.program(with_setup(self.gcode, demo_assembly())))
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        self.panel.drawer.view = FakeView(fail=True)
        self.ask("press Next Step")
        self.panel.drawer.wait()
        self.panel.poll()
        self.assertEqual(
            self.panel.show()["message"],
            "Step 1/7, mill table: Clean the table. "
            "(Setup not drawn: no such vise)",
        )

    def test_keep_outs(self) -> None:
        """The View toggles show or hide; a later drawing keeps them."""
        self.panel.open(self.program(with_setup(self.gcode, demo_assembly())))
        assert self.panel.drawer is not None
        for _ in range(2):
            self.panel.drawer.wait()
            self.assertEqual(self.ask("press Keep-outs"), "ok")
        self.panel.drawer.wait()
        self.assertEqual(self.view.keep_out_shows, [False, True, False])
        self.assertEqual(
            self.panel.show()["toggles"],
            {
                "Keep-outs": False,
                "Stock outline": True,
                "Origin": True,
                "Holders": True,
            },
        )

        # The stock outline hidden stays hidden through Next Step.
        self.assertEqual(self.ask("press Stock outline"), "ok")
        self.panel.drawer.wait()
        self.ask("press Next Step")
        self.panel.drawer.wait()
        self.assertEqual(self.view.hidden, {"keep_out", "stock"})

        # Hidden holders: a tool change draws again, to hide the new one.
        self.ask("press Origin")
        self.ask("press Holders")
        self.panel.drawer.wait()
        drawings = len(self.view.shown)
        self.panel.follow_tool(4)
        self.panel.drawer.wait()
        self.assertEqual(len(self.view.shown), drawings + 1)
        self.assertEqual(
            self.view.hidden, {"keep_out", "stock", "origin", "holder"}
        )
        self.panel.follow_tool(4)
        self.panel.drawer.wait()
        self.assertEqual(len(self.view.shown), drawings + 1)

    def test_start_waits(self) -> None:
        """Start is greyed out while the setup draws; the bar shows it."""
        gate = threading.Event()
        started = threading.Event()
        shown = self.view.show

        def slow(assembly: Assembly) -> None:
            self.view.progress = (1, 7)
            started.set()
            gate.wait(5.0)
            shown(assembly)
            self.view.progress = (7, 7)

        self.view.show = slow  # type: ignore[method-assign]
        self.panel.open(self.program(with_setup(self.gcode, demo_assembly())))
        self.assertTrue(started.wait(5.0))
        self.panel.poll()
        self.assertEqual(self.panel.show()["buttons"]["Start"], "disabled")
        self.assertEqual(self.panel.show()["setup_progress"], [1, 7])
        gate.set()
        assert self.panel.drawer is not None
        self.panel.drawer.wait()
        self.panel.poll()
        self.assertEqual(self.panel.show()["buttons"]["Start"], "normal")
        self.assertEqual(self.panel.show()["setup_progress"], [7, 7])

    def test_no_steps(self) -> None:
        """Next Step without a setup says so."""
        self.panel.open(self.program(self.gcode))
        self.ask("press Next Step")
        self.assertEqual(
            self.panel.show()["message"], "This program has no setup."
        )

    def ask(self, line: str) -> str:
        """Send one line, as the command port would."""
        return self.panel.handle(line)

    def test_draw_error(self) -> None:
        """An error while drawing comes to the message line on a poll."""
        assert self.panel.drawer is not None
        self.panel.drawer.view = FakeView(fail=True)
        self.panel.open(self.program(with_setup(self.gcode, demo_assembly())))
        self.panel.drawer.wait()
        self.panel.poll()
        self.assertIn("no such vise", self.panel.show()["message"])

    def test_newest_drawn(self) -> None:
        """Setups handed in while drawing: only the newest is drawn."""
        gate = threading.Event()
        started = threading.Event()
        view = FakeView()
        shown = view.show

        def slow(assembly: Assembly) -> None:
            started.set()
            gate.wait(5.0)
            shown(assembly)

        drawer = lcnc_hmi.SetupDrawer(cast(Any, mock.Mock(show=slow)))
        first, second, third = Assembly(), Assembly(), Assembly()
        drawer.draw(first)
        self.assertTrue(started.wait(5.0))
        drawer.draw(second)
        drawer.draw(third)
        gate.set()
        drawer.wait()
        self.assertEqual(len(view.shown), 2)
        self.assertIs(view.shown[0], first)
        self.assertIs(view.shown[1], third)


class TestSetOrigin(unittest.TestCase):
    """Set Origin with a setup: pick an origin, confirm, set G54."""

    def setUp(self) -> None:
        use_shop(shops.read(EXAMPLE_SHOP))
        lcnc_hmi.use_headless()
        lcnc_hmi_headless.ANSWERS.clear()
        self.machine = lcnc_hmi.HMIMachine(True)
        self.panel = lcnc_hmi.HMI(
            cast(Any, lcnc_hmi_headless.Tk()), self.machine, 10.0, None
        )
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.path = Path(scratch.name, "part.nc")

    def open(self, setup: bool) -> None:
        """Open a program in inches, with or without the demo setup."""
        gcode = "G20\nG0 X1\nM2\n"
        if setup:
            gcode = with_setup(gcode, demo_assembly())
        self.path.write_text(gcode, encoding="utf-8")
        self.panel.open(str(self.path))

    def test_pick(self) -> None:
        """Picking the stock's corner sets G54 to read it, in inches."""
        self.open(True)
        self.assertTrue(self.panel.inches)
        lcnc_hmi_headless.ANSWERS.extend(["stock: top left outer", "yes"])
        self.panel.on_set_origin()
        self.assertEqual(
            self.machine.log[-2:],
            ["mdi G20", "mdi G10 L20 P1 X-0.2500 Y-0.2500 Z0.0000"],
        )

    def test_cancel(self) -> None:
        """No pick, or No at the question, sets nothing."""
        self.open(True)
        lcnc_hmi_headless.ANSWERS.extend(["", "stock: top left outer", "no"])
        before = list(self.machine.log)
        self.panel.on_set_origin()
        self.panel.on_set_origin()
        self.assertEqual(self.machine.log, before)

    def test_no_setup(self) -> None:
        """Without a setup, Set Origin zeroes the position, as before."""
        self.open(False)
        self.assertEqual(self.panel.origins, [])
        lcnc_hmi_headless.ANSWERS.append("yes")
        self.panel.on_set_origin()
        self.assertEqual(self.machine.log[-1], "mdi G10 L20 P1 X0 Y0 Z0")

    def test_lines(self) -> None:
        """The units word and `G10 L20 P1`, in the program's units."""
        self.assertEqual(
            lcnc_hmi.origin_lines((25.4, -12.7, 0.0), True),
            ["G20", "G10 L20 P1 X1.0000 Y-0.5000 Z0.0000"],
        )
        self.assertEqual(
            lcnc_hmi.origin_lines((1.0, 2.0, -3.0), False),
            ["G21", "G10 L20 P1 X1.000 Y2.000 Z-3.000"],
        )
        self.assertTrue(lcnc_hmi.program_inches(["(G21)", "G20 G90"]))
        self.assertFalse(lcnc_hmi.program_inches(["G0 X1"]))


class TestMainSolidCraft(unittest.TestCase):
    """`--solidcraft` makes the drawer; without it there is none."""

    def run_main(self, *extra: str) -> mock.MagicMock:
        """Run `main()` headless, with SolidCraft faked."""
        handler = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, handler)
        with (
            mock.patch.object(lcnc_hmi_headless.Tk, "mainloop"),
            mock.patch.object(lcnc_hmi, "connect"),
            mock.patch.object(lcnc_hmi, "PyBind"),
            mock.patch.object(lcnc_hmi, "ModelCache"),
            mock.patch.object(lcnc_hmi, "SetupView") as view,
        ):
            code = lcnc_hmi.main(["--headless", "--dry-run", *extra])
        self.assertEqual(code, 0)
        return view

    def test_no_solidcraft(self) -> None:
        """No `--solidcraft`: no view is made."""
        self.assertFalse(self.run_main().called)

    def test_solidcraft(self) -> None:
        """`--solidcraft PORT`: one view, made at the start."""
        self.assertEqual(self.run_main("--solidcraft", "8080").call_count, 1)


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
            "from scraftcnc.hmi import lcnc_hmi; "
            "sys.exit(lcnc_hmi.main(sys.argv[1:]))"
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
            "from scraftcnc.hmi import lcnc_hmi; "
            "sys.exit(lcnc_hmi.main(['--dry-run']))"
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
    """Send a line to an HMI's port, waiting for it to start."""
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
