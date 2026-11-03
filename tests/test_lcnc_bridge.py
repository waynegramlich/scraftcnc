"""Tests for `lcnc_bridge.py` and `lcnc_client.py`, with no LinuxCNC."""

import json
import os
import tempfile
import threading
import time
import types
import unittest
from collections import namedtuple
from pathlib import Path
from typing import Any
from unittest import mock

from scraftcnc.lcnc import lcnc_bridge, lcnc_client, serve_linuxcnc
from scraftcnc.lcnc.install_linuxcnc import SCTarget

Tool = namedtuple("Tool", "id zoffset")


# pylint: disable-next=too-few-public-methods
class FakeStat:
    """Stands in for `linuxcnc.stat`."""

    actual_position = (1.0, float("nan"))
    ini_filename = ""
    tool_table = (Tool(1, 2.5),)
    file = b"name"

    def poll(self) -> None:
        """Do nothing, as the real one reads shared memory."""


# pylint: disable-next=too-few-public-methods
class FakeCommand:
    """Stands in for `linuxcnc.command`."""

    def __init__(self) -> None:
        self.modes: list[int] = []
        self.done: threading.Event = threading.Event()
        self.timeouts: list[float] = []

    def mode(self, mode: int) -> None:
        """Remember the mode."""
        self.modes.append(mode)

    def wait_complete(self, timeout: float) -> int:
        """Return 1 once `done` is set, and -1 until then."""
        self.timeouts.append(timeout)
        return 1 if self.done.is_set() else -1


def fake_module() -> types.ModuleType:
    """Return a stand-in for the `linuxcnc` module."""
    module = types.ModuleType("linuxcnc")
    module.__dict__.update(
        MODE_MDI=3,
        version="2.9.10",
        stat=FakeStat,
        command=FakeCommand,
        error_channel=lambda: types.SimpleNamespace(poll=lambda: None),
        ini=lambda _file: types.SimpleNamespace(
            find=lambda _section, _option: "x.tbl"
        ),
    )
    return module


class TestBridge(unittest.TestCase):
    """The answers to request lines."""

    def setUp(self) -> None:
        self.stops: list[bool] = []
        self.bridge = lcnc_bridge.SCBridge(
            fake_module(), lambda: self.stops.append(True)
        )

    def ask(self, call: str, *args: Any) -> dict[str, Any]:
        """Send one request through JSON."""
        request = {"id": 7, "call": call, "args": list(args)}
        reply = self.bridge.answer(json.dumps(request).encode())
        self.assertEqual(reply["id"], 7)
        json.dumps(reply, allow_nan=False)
        return reply

    def test_ping(self) -> None:
        """`ping` names the protocol and LinuxCNC's version."""
        self.assertEqual(
            self.ask("ping")["result"],
            {"protocol": lcnc_bridge.PROTOCOL, "version": "2.9.10"},
        )

    def test_constants(self) -> None:
        """Only numbers and strings are constants."""
        result = self.ask("constants")["result"]
        self.assertEqual(result["MODE_MDI"], 3)
        self.assertNotIn("stat", result)

    def test_stat_converts_to_json(self) -> None:
        """Tuples, named tuples, bytes and NaN all get through JSON."""
        result = self.ask("stat")["result"]
        self.assertEqual(result["actual_position"], [1.0, None])
        self.assertEqual(result["tool_table"], [{"id": 1, "zoffset": 2.5}])
        self.assertEqual(result["file"], "name")
        self.assertNotIn("poll", result)

    def test_stat_names(self) -> None:
        """`stat` returns only what is named; a bad name is an error."""
        self.assertEqual(list(self.ask("stat", ["file"])["result"]), ["file"])
        self.assertIn("error", self.ask("stat", ["nope"]))
        self.assertIn("error", self.ask("stat", ["__class__"]))

    def test_command_with_constant(self) -> None:
        """A `{"constant": NAME}` argument becomes its value."""
        self.ask("command.mode", {"constant": "MODE_MDI"})
        self.assertEqual(self.bridge.command.modes, [3])

    def test_refused(self) -> None:
        """Only public methods of known objects can be called."""
        for call in (
            "command.__class__",
            "command.nope",
            "eval",
            "stat.poll",
            "linuxcnc.stat",
            "command.",
        ):
            self.assertIn("error", self.ask(call), call)
        reply = self.ask("command.mode", {"constant": "__loader__"})
        self.assertIn("error", reply)

    def test_bad_requests(self) -> None:
        """Bad requests get errors, and do not stop the bridge."""
        for line in (
            b"not json\n",
            b"[1]\n",
            b'{"call": "ping", "args": 1}\n',
        ):
            self.assertIn("error", self.bridge.answer(line))
        self.assertIn("result", self.ask("ping"))

    def test_shutdown(self) -> None:
        """`shutdown` calls what it was told to."""
        self.assertIsNone(self.ask("shutdown")["result"])
        self.assertEqual(self.stops, [True])

    def test_write_program(self) -> None:
        """Programs go into `programs/`, and nowhere else."""
        with tempfile.TemporaryDirectory() as directory:
            self.bridge.stat.ini_filename = f"{directory}/x.ini"
            path = self.ask("program.write", "a.ngc", "M2\n")["result"]
            self.assertEqual(path, str(Path(directory, "programs", "a.ngc")))
            self.assertEqual(Path(path).read_text("utf-8"), "M2\n")
            for name in (
                "../b.ngc",
                "/tmp/c.ngc",
                "d/e.ngc",
                "..",
                "",
                "f\\g.ngc",
            ):
                reply = self.ask("program.write", name, "M2\n")
                self.assertIn("error", reply, name)

    def test_read_program(self) -> None:
        """A program comes back; nothing else can be read."""
        with tempfile.TemporaryDirectory() as directory:
            self.bridge.stat.ini_filename = f"{directory}/x.ini"
            path = self.ask("program.write", "a.ngc", "M2\n")["result"]
            self.assertEqual(self.ask("program.read", path)["result"], "M2\n")
            secret = Path(directory, "secret.txt")
            secret.write_text("no", encoding="utf-8")
            programs = Path(directory, "programs")
            for name in (
                str(secret),
                str(programs / ".." / "secret.txt"),
                str(programs / "missing.ngc"),
                "a.ngc",
            ):
                self.assertIn("error", self.ask("program.read", name), name)

    def test_write_tool_table(self) -> None:
        """The tool table goes where the INI file says."""
        with tempfile.TemporaryDirectory() as directory:
            self.bridge.stat.ini_filename = f"{directory}/x.ini"
            text = "T1 P1 Z1.0 D0.25 ;a\n"
            path = self.ask("tool_table.write", text)["result"]
            self.assertEqual(path, str(Path(directory, "x.tbl")))
            self.assertEqual(Path(path).read_bytes().decode(), text)

    def test_wait_complete_times_out(self) -> None:
        """A command still running gives -1, after the time asked for."""
        reply = self.ask("command.wait_complete", 0.02)
        self.assertEqual(reply["result"], -1)
        self.assertGreater(len(self.bridge.command.timeouts), 1)

    def test_wait_complete_asks_once_with_zero(self) -> None:
        """A timeout of 0 asks once, and does not wait."""
        self.assertEqual(self.ask("command.wait_complete", 0)["result"], -1)
        self.assertEqual(self.bridge.command.timeouts, [0.0])

    def test_wait_complete_done(self) -> None:
        """A finished command gives its status."""
        self.bridge.command.done.set()
        self.assertEqual(self.ask("command.wait_complete")["result"], 1)


class TestWaitUntilReady(unittest.TestCase):
    """Waiting for `milltask` before opening the port."""

    def test_waits_for_ini_filename(self) -> None:
        """It returns only once `poll()` has filled in the name."""
        stat = types.SimpleNamespace(ini_filename="", polls=0)

        def poll() -> None:
            stat.polls += 1
            if stat.polls == 3:
                stat.ini_filename = "x.ini"

        stat.poll = poll
        lcnc_bridge.wait_until_ready(stat)
        self.assertEqual(stat.polls, 3)

    def test_gives_up(self) -> None:
        """A LinuxCNC that never becomes ready is an error."""
        with self.assertRaises(TimeoutError):
            lcnc_bridge.wait_until_ready(FakeStat(), timeout=0.0)


class TestClient(unittest.TestCase):
    """The client against the real server code, over a real socket."""

    def setUp(self) -> None:
        self.server = lcnc_bridge.SCServer(
            ("127.0.0.1", 0), lcnc_bridge.SCHandler
        )
        self.server.bridge = lcnc_bridge.SCBridge(fake_module(), lambda: None)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.addCleanup(self.finish)

    def finish(self) -> None:
        """Stop the server."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_calls(self) -> None:
        """Results come back, and errors become exceptions."""
        with lcnc_client.SCClient("127.0.0.1", self.port) as lcnc:
            self.assertEqual(lcnc.call("ping")["version"], "2.9.10")
            self.assertEqual(lcnc.stat("file"), {"file": "name"})
            with self.assertRaises(lcnc_client.SCBridgeError) as caught:
                lcnc.call("eval")
            self.assertEqual(caught.exception.kind, "ValueError")
            self.assertEqual(
                lcnc.call("ping")["protocol"], lcnc_bridge.PROTOCOL
            )

    def test_big_program_line(self) -> None:
        """A request far bigger than a socket buffer gets through."""
        with tempfile.TemporaryDirectory() as directory:
            assert self.server.bridge is not None
            self.server.bridge.stat.ini_filename = f"{directory}/x.ini"
            text = "G0 X1\n" * 200000
            with lcnc_client.SCClient("127.0.0.1", self.port) as lcnc:
                path = lcnc.call("program.write", "big.ngc", text)
            self.assertEqual(os.path.getsize(path), len(text))

    def test_two_connections(self) -> None:
        """Two clients can be connected at once."""
        with (
            lcnc_client.SCClient("127.0.0.1", self.port) as one,
            lcnc_client.SCClient("127.0.0.1", self.port) as two,
        ):
            self.assertEqual(one.call("ping"), two.call("ping"))

    def test_wait_does_not_hold_up_others(self) -> None:
        """Another connection is answered during a long wait."""
        assert self.server.bridge is not None
        command = self.server.bridge.command
        with (
            lcnc_client.SCClient("127.0.0.1", self.port) as one,
            lcnc_client.SCClient("127.0.0.1", self.port) as two,
        ):
            results: list[int] = []
            waiter = threading.Thread(
                target=lambda: results.append(
                    one.call("command.wait_complete", 30.0)
                )
            )
            waiter.start()
            self.addCleanup(waiter.join)
            self.addCleanup(command.done.set)
            while not command.timeouts:
                time.sleep(0.001)

            # It answers while the other still waits, then that ends.
            started = time.monotonic()
            self.assertEqual(two.call("ping")["version"], "2.9.10")
            self.assertLess(time.monotonic() - started, 5.0)
            self.assertEqual(results, [])
            command.done.set()
            waiter.join()
            self.assertEqual(results, [1])

    def test_client_port_matches(self) -> None:
        """The client, which imports nothing, has the bridge's port."""
        self.assertEqual(lcnc_client.PORT, lcnc_bridge.PORT)


class TestServe(unittest.TestCase):
    """`serve_linuxcnc.py`'s parts that need no target."""

    def test_start_command(self) -> None:
        """LinuxCNC starts in the bridge's directory, with no display."""
        target = SCTarget("t", ("r",), ("u",), "/home/x", True, "e")
        command = serve_linuxcnc.start_command(target)
        self.assertEqual(command[:3], ["u", "env", "-u"])
        self.assertEqual(command[3], "DISPLAY")
        self.assertIn("HOME=/home/x", command)
        self.assertIn("linuxcnc lcnc_sim.ini", command[-1])
        self.assertIn("/home/x/.local/share/scraftlinuxcnc", command[-1])

    def test_refuses_when_port_is_in_use(self) -> None:
        """A second LinuxCNC is not started."""
        target = SCTarget("t", ("r",), ("u",), "/home/x", True, "e")
        with (
            mock.patch.object(serve_linuxcnc, "serving", return_value=True),
            mock.patch.object(serve_linuxcnc, "run") as run,
            mock.patch("sys.stderr"),
        ):
            self.assertEqual(serve_linuxcnc.serve(target), 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
