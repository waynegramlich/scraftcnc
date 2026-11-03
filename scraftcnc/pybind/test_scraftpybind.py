"""Tests for `scraftpybind` and `scraftpybind_generate`.

The offline tests always run.  `SCControlTransport` is tested against a
fake control port, and `SCHeadlessTransport` against a fake
`solidcraft-cli` (a Python script that speaks enough MCP).

The live tests run only when `solidcraft-cli` is on the `PATH`; they
build plates headless and measure the STEP files that SolidCraft
writes.  A GUI test also runs when `SCRAFTPYBIND_TEST_PORT` names the
control port of a running `solidcraft --control PORT` (it adds a plate
to the open design).

```
python3 -m unittest -v
```
"""

# One module holds every test, so it is longer than `pylint` likes.
# pylint: disable=too-many-lines

import contextlib
import inspect
import io
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import scraftpybind
import scraftpybind_generate
from scraftpybind import (
    JSON,
    SCControlTransport,
    SCHeadlessTransport,
    SCNamespace,
    SCPyBind,
    SCSolidCraftError,
    SCTransport,
)

# Where things are.
HERE: Path = Path(__file__).resolve().parent
MODULE: Path = HERE / "scraftpybind.py"
GENERATOR: Path = HERE / "scraftpybind_generate.py"
CACHE: Path = HERE / "scraftpybind_commands.json"
EXAMPLE: Path = HERE / "examples" / "plate_with_holes.py"

# The `solidcraft-cli` version that `scraftpybind_commands.json` came
# from; another version may well have other commands.
CACHED_VERSION: str = "solidcraft-cli 0.20.0"

# The `solidcraft-cli` on the `PATH`, if there is one.
CLI: str | None = shutil.which("solidcraft-cli")

# How far a measured volume may be from the exact one, relative to it
# (SolidCraft's measurements of the plates are about 5e-6 off).
VOLUME_TOLERANCE: float = 1e-4

# A GUI's control port for the GUI test, or "".
GUI_PORT: str = os.environ.get("SCRAFTPYBIND_TEST_PORT", "")

# A fake `solidcraft-cli mcp --headless`.  Its `execute` tool answers
# by the command: `echo` returns its arguments and parameters (after a
# notification, which must be skipped), `fail` is a tool error,
# `rpc_error` a JSON-RPC error, `text` a result that is not JSON,
# `list` a result that is not an object, and `die` stops the session
# with some error text (closing its output first, so the exit status is
# not ready when the output ends).  `linger` closes its output and
# never exits; `deaf` answers, then ignores the end of its input, so it
# has to be killed.  Any other command gets four curve ids, the way
# `sketch.rectangle.center` answers.
FAKE_CLI: str = '''
import json
import os
import sys
import time


def reply(request_id, result):
    """Send one reply."""
    message = {"jsonrpc": "2.0", "id": request_id, "result": result}
    print(json.dumps(message), flush=True)


deaf = False
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        reply(request_id, {"protocolVersion": "2025-06-18"})
    elif method == "tools/call":
        arguments = message["params"]["arguments"]
        command = arguments["command"]
        if command == "echo":
            print(json.dumps({"jsonrpc": "2.0", "method": "notice"}))
            text = json.dumps(
                {"argv": sys.argv[1:], "params": arguments["params"]}
            )
            reply(request_id, {"content": [{"type": "text", "text": text}]})
        elif command == "fail":
            reply(
                request_id,
                {
                    "content": [{"type": "text", "text": "it failed"}],
                    "isError": True,
                },
            )
        elif command == "rpc_error":
            error = {"code": -32000, "message": "bad rpc"}
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request_id, "error": error}
                ),
                flush=True,
            )
        elif command == "text":
            reply(request_id, {"content": [{"type": "text", "text": "hi"}]})
        elif command == "list":
            reply(request_id, [1, 2])
        elif command == "linger":
            os.close(1)
            time.sleep(60)
        elif command == "deaf":
            deaf = True
            reply(request_id, {"content": [{"type": "text", "text": "ok"}]})
        elif command == "die":
            os.close(1)
            time.sleep(0.5)
            print("dying words", file=sys.stderr, flush=True)
            sys.exit(3)
        else:
            text = json.dumps({"curves": ["c1", "c2", "c3", "c4"]})
            reply(request_id, {"content": [{"type": "text", "text": text}]})
if deaf:
    time.sleep(60)
'''


# Class `SCRecordingTransport`:
class SCRecordingTransport(SCTransport):
    """A transport that records each request and answers `{}`.

    Attributes:
    * `requests` (`list[tuple[str, Mapping[str, JSON]]]`):
      Each request's method and parameters, in order.
    """

    # Method `SCRecordingTransport.__init__()`:
    def __init__(self) -> None:
        """Start with no requests."""
        self.requests: list[tuple[str, Mapping[str, JSON]]] = []

    # Method `SCRecordingTransport.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Record one request.

        Arguments:
        * `method` (`str`): The method.
        * `params` (`Mapping[str, JSON]`): Its parameters.

        Returns:
        * (`JSON`): An empty result.
        """
        self.requests.append((method, params))
        return {}


# Class `SCLoggingHeadlessTransport`:
@dataclass(slots=True)
class SCLoggingHeadlessTransport(SCHeadlessTransport):
    """A `SCHeadlessTransport` that also notes each command it sends.

    Attributes:
    * `sent` (`list[tuple[str, Mapping[str, JSON]]]`):
      Each command and its parameters, in order.

    Constructor:
    * `SCLoggingHeadlessTransport(cli, allow_paths)`
    """

    # Remaining attributes (alphabetized):
    sent: list[tuple[str, Mapping[str, JSON]]] = field(
        init=False, default_factory=list
    )

    # Method `SCLoggingHeadlessTransport.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Note the command, then send it.

        Arguments:
        * `method` (`str`): The method (`engine.execute`).
        * `params` (`Mapping[str, JSON]`): `command` and `params`.

        Returns:
        * (`JSON`): The command's result.
        """
        command_params: JSON = params.get("params")
        assert isinstance(command_params, Mapping)
        self.sent.append((str(params.get("command")), command_params))
        return SCHeadlessTransport.request(self, method, params)


# Class `SCFakeControlPort`:
class SCFakeControlPort:
    """A one-connection fake of a SolidCraft GUI's control port.

    Each request line is decoded, recorded and given to `answer`, whose
    reply (a JSON value) is sent back as one line; a `None` reply
    closes the connection instead.

    Attributes:
    * `answer` (`Callable[[dict[str, Any]], JSON]`): Makes the replies.
    * `listener` (`socket.socket`): The listening socket.
    * `port` (`int`): The port it listens on.
    * `requests` (`list[dict[str, Any]]`): The requests, in order.
    * `thread` (`threading.Thread`): Serves the connection.
    """

    # Method `SCFakeControlPort.__init__()`:
    def __init__(self, answer: Callable[[dict[str, Any]], JSON]) -> None:
        """Start listening on a free local port.

        Arguments:
        * `answer` (`Callable[[dict[str, Any]], JSON]`):
          Makes the reply to each request.
        """
        self.answer: Callable[[dict[str, Any]], JSON] = answer
        self.requests: list[dict[str, Any]] = []
        self.listener: socket.socket = socket.create_server(("127.0.0.1", 0))
        self.port: int = self.listener.getsockname()[1]
        self.thread: threading.Thread = threading.Thread(
            target=self.serve, daemon=True
        )
        self.thread.start()

    # Method `SCFakeControlPort.serve()`:
    def serve(self) -> None:
        """Answer the requests of one connection."""
        # Accept one connection, and answer it line by line.
        connection: socket.socket
        connection, _ = self.listener.accept()
        with connection, connection.makefile("rw", encoding="utf-8") as stream:
            line: str
            for line in stream:
                request: dict[str, Any] = json.loads(line)
                self.requests.append(request)
                reply: JSON = self.answer(request)
                if reply is None:
                    break
                stream.write(json.dumps(reply) + "\n")
                stream.flush()

    # Method `SCFakeControlPort.close()`:
    def close(self) -> None:
        """Stop listening, once the connection has been served."""
        self.thread.join(timeout=10)
        self.listener.close()


# Function `ok()`:
def ok(request: dict[str, Any]) -> JSON:
    """Answer a request with its own method and parameters.

    Arguments:
    * `request` (`dict[str, Any]`): The request.

    Returns:
    * (`JSON`): A successful reply.
    """
    result: JSON = {"method": request["method"], "params": request["params"]}
    return {"id": request["id"], "ok": True, "result": result}


# Function `measure()`:
def measure(step: Path) -> dict[str, Any]:  # pragma: no cover
    """Measure the one body of a STEP file with `solidcraft-cli eval`.

    Arguments:
    * `step` (`Path`): The STEP file.

    Returns:
    * (`dict[str, Any]`): The body's measurements (`volume_mm3`, ...).
    """
    assert CLI is not None
    output: str = subprocess.run(
        [CLI, "eval", "--in", str(step)],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    report: dict[str, Any] = json.loads(output)
    bodies: list[dict[str, Any]] = report["bodies"]
    assert len(bodies) == 1, bodies
    return bodies[0]


# Function `relative_error()`:
def relative_error(measured: float, exact: float) -> float:  # pragma: no cover
    """Return how far a measurement is from the exact value, relatively.

    Arguments:
    * `measured` (`float`): The measured value.
    * `exact` (`float`): The exact value (not 0).

    Returns:
    * (`float`): `abs(measured - exact) / abs(exact)`.
    """
    return abs(measured - exact) / abs(exact)


# Function `run_python()`:
def run_python(  # pragma: no cover
    arguments: list[str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run a Python program, able to import `scraftpybind`.

    Arguments:
    * `arguments` (`list[str]`): The program and its arguments.
    * `cwd` (`Path`): The folder to run it in.

    Returns:
    * (`subprocess.CompletedProcess[str]`): What it did.
    """
    environment: dict[str, str] = dict(os.environ, PYTHONPATH=str(HERE))
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


# Function `namespaces()`:
def namespaces(solidcraft: SCPyBind) -> dict[str, SCNamespace]:
    """Return the namespaces of a `SCPyBind`, by attribute name.

    Arguments:
    * `solidcraft` (`SCPyBind`): The bindings.

    Returns:
    * (`dict[str, SCNamespace]`): Each namespace object.
    """
    found: dict[str, SCNamespace] = {}
    name: str
    for name in dir(solidcraft):
        value: object = getattr(solidcraft, name)
        if isinstance(value, SCNamespace):
            found[name] = value
    return found


# Class `TestNamespace`:
class TestNamespace(unittest.TestCase):
    """The generated methods and `SCNamespace.execute()`."""

    # Method `TestNamespace.test_none_is_not_sent()`:
    def test_none_is_not_sent(self) -> None:
        """Parameters left at `None` are left out; `extra` is sent."""
        transport: SCRecordingTransport = SCRecordingTransport()
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.sketch.rectangle_center(
            center=(0, 0), corner=(50, 30), color="red"
        )
        self.assertEqual(
            transport.requests,
            [
                (
                    "engine.execute",
                    {
                        "command": "sketch.rectangle.center",
                        "params": {
                            "center": (0, 0),
                            "corner": (50, 30),
                            "color": "red",
                        },
                    },
                )
            ],
        )

    # Method `TestNamespace.test_top_level_execute()`:
    def test_top_level_execute(self) -> None:
        """`SCPyBind.execute()` leaves out `None`, too."""
        transport: SCRecordingTransport = SCRecordingTransport()
        solidcraft: SCPyBind = SCPyBind(transport)
        solidcraft.execute("sketch.create", {"plane": "XY", "name": None})
        self.assertEqual(
            transport.requests,
            [
                (
                    "engine.execute",
                    {"command": "sketch.create", "params": {"plane": "XY"}},
                )
            ],
        )

    # Method `TestNamespace.test_every_command_has_a_method()`:
    def test_every_command_has_a_method(self) -> None:
        """Each cached command is sent by exactly one method."""
        # The commands that SolidCraft has.
        data: dict[str, Any] = json.loads(CACHE.read_text(encoding="utf-8"))
        wanted: list[str] = sorted(
            str(entry["id"]) for entry in data["commands"]
        )

        # Call every method (giving its required arguments a 0), and
        # note the command each one sends.
        transport: SCRecordingTransport = SCRecordingTransport()
        solidcraft: SCPyBind = SCPyBind(transport)
        sent: list[str] = []
        namespace_name: str
        namespace: SCNamespace
        for namespace_name, namespace in namespaces(solidcraft).items():
            method_name: str
            for method_name in dir(namespace):
                if method_name.startswith("_") or method_name in (
                    "execute",
                    "transport",
                ):
                    continue
                method: Callable[..., JSON] = getattr(namespace, method_name)
                required: dict[str, JSON] = {
                    parameter.name: 0
                    for parameter in inspect.signature(
                        method
                    ).parameters.values()
                    if parameter.default is inspect.Parameter.empty
                    and parameter.kind is not inspect.Parameter.VAR_KEYWORD
                }
                transport.requests.clear()
                method(**required)
                self.assertEqual(len(transport.requests), 1)
                params: Mapping[str, JSON] = transport.requests[0][1]
                command: JSON = params["command"]
                assert isinstance(command, str)
                self.assertEqual(
                    command.split(".")[0],
                    namespace_name,
                    f"{namespace_name}.{method_name}",
                )
                sent.append(command)
        self.assertEqual(sorted(sent), wanted)

    # Method `TestNamespace.test_namespaces_share_the_transport()`:
    def test_namespaces_share_the_transport(self) -> None:
        """Every namespace sends through the one transport."""
        transport: SCRecordingTransport = SCRecordingTransport()
        solidcraft: SCPyBind = SCPyBind(transport)
        found: dict[str, SCNamespace] = namespaces(solidcraft)
        self.assertIn("sketch", found)
        self.assertIn("solid", found)
        namespace: SCNamespace
        for namespace in found.values():
            self.assertIs(namespace.transport, transport)


# Class `TestTransport`:
class TestTransport(unittest.TestCase):
    """The `SCTransport` base class."""

    # Method `TestTransport.test_request()`:
    def test_request(self) -> None:
        """The base class has no way to send a request."""
        with (
            SCTransport() as transport,
            self.assertRaisesRegex(NotImplementedError, "SCTransport.request"),
        ):
            transport.request("engine.execute", {})


# Class `TestConnect`:
class TestConnect(unittest.TestCase):
    """`connect()` and `control_dir()`."""

    # Method `TestConnect.test_connect()`:
    def test_connect(self) -> None:
        """A port number, `headless`, and anything else."""
        transport: SCTransport = scraftpybind.connect("8080")
        assert isinstance(transport, SCControlTransport)
        self.assertEqual(transport.port, 8080)
        self.assertIsNone(transport.sock)
        self.assertIsInstance(
            scraftpybind.connect("headless"), SCHeadlessTransport
        )
        with self.assertRaises(ValueError):
            scraftpybind.connect("gui")

    # Method `TestConnect.test_control_dir()`:
    def test_control_dir(self) -> None:
        """`SOLIDCRAFT_CONTROL_DIR`, then `XDG_DATA_HOME`, then home."""
        with mock.patch.dict(
            os.environ,
            {"SOLIDCRAFT_CONTROL_DIR": "/a", "XDG_DATA_HOME": "/b"},
        ):
            self.assertEqual(scraftpybind.control_dir(), Path("/a"))
        with mock.patch.dict(
            os.environ, {"SOLIDCRAFT_CONTROL_DIR": "", "XDG_DATA_HOME": "/b"}
        ):
            self.assertEqual(
                scraftpybind.control_dir(), Path("/b/solidcraft/control")
            )
        with mock.patch.dict(
            os.environ, {"SOLIDCRAFT_CONTROL_DIR": "", "XDG_DATA_HOME": ""}
        ):
            self.assertEqual(
                scraftpybind.control_dir(),
                Path.home() / ".local/share/solidcraft/control",
            )


# Class `TestControlTransport`:
class TestControlTransport(unittest.TestCase):
    """`SCControlTransport`, against a fake control port."""

    # Method `TestControlTransport.test_requests()`:
    def test_requests(self) -> None:
        """Ids count up, and only the first request has the token."""
        fake: SCFakeControlPort = SCFakeControlPort(ok)
        with SCControlTransport(fake.port, token="secret") as transport:
            first: JSON = transport.request("engine.execute", {"a": 1})
            second: JSON = transport.request("ui.ping", {})
        fake.close()
        self.assertEqual(
            first, {"method": "engine.execute", "params": {"a": 1}}
        )
        self.assertEqual(second, {"method": "ui.ping", "params": {}})
        self.assertEqual(
            fake.requests,
            [
                {
                    "id": 1,
                    "method": "engine.execute",
                    "params": {"a": 1},
                    "token": "secret",
                },
                {"id": 2, "method": "ui.ping", "params": {}},
            ],
        )
        self.assertIsNone(transport.sock)
        self.assertIsNone(transport.reader)

    # Method `TestControlTransport.test_port_and_token_files()`:
    def test_port_and_token_files(self) -> None:
        """Port 0 reads `current.port`; the token comes from a file."""
        fake: SCFakeControlPort = SCFakeControlPort(ok)
        with tempfile.TemporaryDirectory() as folder:
            control: Path = Path(folder)
            (control / "current.port").write_text(f"{fake.port}\n")
            (control / f"{fake.port}.token").write_text("from-file\n")
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "SOLIDCRAFT_CONTROL_DIR": folder,
                        "SOLIDCRAFT_CONTROL_TOKEN": "",
                    },
                ),
                SCControlTransport() as transport,
            ):
                transport.request("engine.execute", {})
                self.assertEqual(transport.port, fake.port)
        fake.close()
        self.assertEqual(fake.requests[0]["token"], "from-file")

    # Method `TestControlTransport.test_token_variable()`:
    def test_token_variable(self) -> None:
        """`SOLIDCRAFT_CONTROL_TOKEN` wins over the token file."""
        fake: SCFakeControlPort = SCFakeControlPort(ok)
        with (
            mock.patch.dict(
                os.environ, {"SOLIDCRAFT_CONTROL_TOKEN": "from-variable"}
            ),
            SCControlTransport(fake.port) as transport,
        ):
            transport.request("engine.execute", {})
        fake.close()
        self.assertEqual(fake.requests[0]["token"], "from-variable")

    # Method `TestControlTransport.test_no_gui()`:
    def test_no_gui(self) -> None:
        """No GUI (no port or token file, or no listener) says so."""
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.dict(
                os.environ,
                {
                    "SOLIDCRAFT_CONTROL_DIR": folder,
                    "SOLIDCRAFT_CONTROL_TOKEN": "",
                },
            ),
        ):
            # No `current.port` file.
            with self.assertRaises(FileNotFoundError) as caught:
                SCControlTransport().connect()
            self.assertIn("default port", str(caught.exception))

            # No token file for the port.
            with self.assertRaises(FileNotFoundError) as caught:
                SCControlTransport(8080).connect()
            self.assertIn("`--control 8080`", str(caught.exception))

            # A port that nothing listens on.
            probe: socket.socket = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port: int = probe.getsockname()[1]
            probe.close()
            with self.assertRaises(ConnectionRefusedError) as refused:
                SCControlTransport(port, token="t").connect()
            self.assertIn("nothing is listening", str(refused.exception))

            # The demonstration reports it in one line.
            errors: io.StringIO = io.StringIO()
            with (
                mock.patch.object(sys, "argv", ["scraftpybind", "8080"]),
                contextlib.redirect_stderr(errors),
            ):
                self.assertEqual(scraftpybind.main(), 1)
            self.assertTrue(errors.getvalue().startswith("scraftpybind: "))
            self.assertEqual(errors.getvalue().count("\n"), 1)

    # Method `TestControlTransport.test_error()`:
    def test_error(self) -> None:
        """An `"ok": false` reply raises `SCSolidCraftError`."""

        # Function `refuse()`:
        def refuse(request: dict[str, Any]) -> JSON:
            """Refuse a request as busy and still running.

            Arguments:
            * `request` (`dict[str, Any]`): The request.

            Returns:
            * (`JSON`): A failed reply.
            """
            return {
                "id": request["id"],
                "ok": False,
                "error": "no way",
                "running": True,
                "busy": True,
            }

        fake: SCFakeControlPort = SCFakeControlPort(refuse)
        with (
            SCControlTransport(fake.port, token="t") as transport,
            self.assertRaises(SCSolidCraftError) as caught,
        ):
            transport.request("engine.execute", {})
        fake.close()
        self.assertEqual(caught.exception.method, "engine.execute")
        self.assertEqual(caught.exception.error, "no way")
        self.assertTrue(caught.exception.running)
        self.assertTrue(caught.exception.busy)
        self.assertEqual(str(caught.exception), "engine.execute: no way")

    # Method `TestControlTransport.test_closed()`:
    def test_closed(self) -> None:
        """A port that closes raises `ConnectionError`."""
        fake: SCFakeControlPort = SCFakeControlPort(lambda request: None)
        with (
            SCControlTransport(fake.port, token="t") as transport,
            self.assertRaisesRegex(ConnectionError, "closed the port"),
        ):
            transport.request("engine.execute", {})
        fake.close()

    # Method `TestControlTransport.test_wrong_id()`:
    def test_wrong_id(self) -> None:
        """A reply to another request raises `ConnectionError`."""
        fake: SCFakeControlPort = SCFakeControlPort(
            lambda request: {"id": 99, "ok": True, "result": None}
        )
        with (
            SCControlTransport(fake.port, token="t") as transport,
            self.assertRaisesRegex(ConnectionError, "unexpected reply"),
        ):
            transport.request("engine.execute", {})
        fake.close()


# Class `TestHeadlessTransport`:
class TestHeadlessTransport(unittest.TestCase):
    """`SCHeadlessTransport`, against a fake `solidcraft-cli`.

    Attributes:
    * `folder` (`tempfile.TemporaryDirectory[str]`): Holds the fake.
    * `cli` (`str`): The fake `solidcraft-cli` program.
    """

    folder: tempfile.TemporaryDirectory[str]
    cli: str

    # Method `TestHeadlessTransport.setUp()`:
    def setUp(self) -> None:
        """Write the fake `solidcraft-cli`, ready to run."""
        # The folder outlives this method; `tearDown()` removes it.
        # pylint: disable-next=consider-using-with
        self.folder = tempfile.TemporaryDirectory()
        program: Path = Path(self.folder.name) / "fake-solidcraft-cli"
        program.write_text(f"#!{sys.executable}\n{FAKE_CLI}")
        program.chmod(0o755)
        self.cli = str(program)

    # Method `TestHeadlessTransport.tearDown()`:
    def tearDown(self) -> None:
        """Remove the fake."""
        self.folder.cleanup()

    # Method `TestHeadlessTransport.test_execute()`:
    def test_execute(self) -> None:
        """A command's result comes back parsed, past a notification."""
        with SCHeadlessTransport(self.cli, ["/tmp"]) as transport:
            solidcraft: SCPyBind = SCPyBind(transport)
            first: JSON = solidcraft.sketch.execute("echo", {"x": 1})
            second: JSON = solidcraft.sketch.execute("echo", {"y": None})
            process: subprocess.Popen[str] | None = transport.process
            self.assertIsNotNone(process)
        self.assertEqual(
            first,
            {
                "argv": ["mcp", "--headless", "--allow-path", "/tmp"],
                "params": {"x": 1},
            },
        )
        assert isinstance(second, dict)
        self.assertEqual(second["params"], {})
        self.assertIsNone(transport.process)
        self.assertIsNone(transport.errors)
        assert process is not None
        self.assertEqual(process.returncode, 0)

    # Method `TestHeadlessTransport.test_default_allow_path()`:
    def test_default_allow_path(self) -> None:
        """With no `allow_paths`, the current folder is allowed."""
        with SCHeadlessTransport(self.cli) as transport:
            result: JSON = transport.request(
                "engine.execute", {"command": "echo", "params": {}}
            )
        assert isinstance(result, dict)
        self.assertEqual(
            result["argv"][2:], ["--allow-path", str(Path.cwd().resolve())]
        )

    # Method `TestHeadlessTransport.test_text_result()`:
    def test_text_result(self) -> None:
        """A result that is not JSON comes back as its text."""
        with SCHeadlessTransport(self.cli) as transport:
            result: JSON = transport.request(
                "engine.execute", {"command": "text", "params": {}}
            )
        self.assertEqual(result, "hi")

    # Method `TestHeadlessTransport.test_errors()`:
    def test_errors(self) -> None:
        """Tool errors and JSON-RPC errors raise `SCSolidCraftError`."""
        with SCHeadlessTransport(self.cli) as transport:
            with self.assertRaises(SCSolidCraftError) as caught:
                transport.request(
                    "engine.execute", {"command": "fail", "params": {}}
                )
            self.assertEqual(caught.exception.error, "it failed")
            with self.assertRaises(SCSolidCraftError) as caught:
                transport.request(
                    "engine.execute", {"command": "rpc_error", "params": {}}
                )
            self.assertEqual(caught.exception.error, "bad rpc")
            self.assertEqual(caught.exception.method, "tools/call")

            # The session still works after them.
            self.assertEqual(
                transport.request(
                    "engine.execute", {"command": "text", "params": {}}
                ),
                "hi",
            )

    # Method `TestHeadlessTransport.test_needs_the_gui()`:
    def test_needs_the_gui(self) -> None:
        """A method other than `engine.execute` is refused unsent."""
        with SCHeadlessTransport(self.cli) as transport:
            with self.assertRaisesRegex(SCSolidCraftError, "needs the GUI"):
                transport.request("ui.screenshot", {})
            self.assertIsNone(transport.process)

    # Method `TestHeadlessTransport.test_stopped()`:
    def test_stopped(self) -> None:
        """A session that stops reports its status and error text."""
        with (
            SCHeadlessTransport(self.cli) as transport,
            self.assertRaisesRegex(
                ConnectionError, r"status=3\).*dying words"
            ),
        ):
            transport.request(
                "engine.execute", {"command": "die", "params": {}}
            )

    # Method `TestHeadlessTransport.test_not_an_object()`:
    def test_not_an_object(self) -> None:
        """A tool result that is not an object raises."""
        with (
            SCHeadlessTransport(self.cli) as transport,
            self.assertRaisesRegex(ConnectionError, "unexpected reply"),
        ):
            transport.request(
                "engine.execute", {"command": "list", "params": {}}
            )

    # Method `TestHeadlessTransport.test_never_exits()`:
    def test_never_exits(self) -> None:
        """A session that ends its output but never exits is killed."""
        with mock.patch.object(scraftpybind, "EXIT_TIMEOUT", 0.2):
            transport: SCHeadlessTransport = SCHeadlessTransport(self.cli)
            with (
                transport,
                self.assertRaisesRegex(ConnectionError, r"status=None\)"),
            ):
                transport.request(
                    "engine.execute", {"command": "linger", "params": {}}
                )
        self.assertIsNone(transport.process)

    # Method `TestHeadlessTransport.test_killed()`:
    def test_killed(self) -> None:
        """A session that ignores the end of its input is killed."""
        # Time the `close()` that kills it, instead of waiting a minute.
        transport: SCHeadlessTransport = SCHeadlessTransport(self.cli)
        transport.request("engine.execute", {"command": "deaf", "params": {}})
        process: subprocess.Popen[str] | None = transport.process
        started: float = time.monotonic()
        with mock.patch.object(scraftpybind, "EXIT_TIMEOUT", 0.2):
            transport.close()
        assert process is not None
        self.assertNotEqual(process.returncode, 0)
        self.assertLess(time.monotonic() - started, 5)

    # Method `TestHeadlessTransport.test_main()`:
    def test_main(self) -> None:
        """`main()` sends the plate's commands, then names its file."""
        # Run `main()` headless, on the fake.
        transport: SCLoggingHeadlessTransport = SCLoggingHeadlessTransport(
            self.cli
        )
        output: io.StringIO = io.StringIO()
        with (
            mock.patch.object(
                scraftpybind, "connect", return_value=transport
            ) as connect,
            mock.patch.object(sys, "argv", ["scraftpybind.py", "headless"]),
            contextlib.redirect_stdout(output),
        ):
            status: int = scraftpybind.main()
        connect.assert_called_once_with("headless")
        self.assertEqual(status, 0)
        self.assertIsNone(transport.process)

        # The commands, with the rectangle's curves passed on to the
        # extrusion, and the file it was told to write.
        step: Path = Path("scraftpybind_plate.step").resolve()
        self.assertEqual(
            transport.sent,
            [
                ("sketch.create", {"plane": "XY", "name": "Plate"}),
                (
                    "sketch.rectangle.center",
                    {"center": (0, 0), "corner": (50, 30)},
                ),
                ("sketch.circle.center", {"center": (0, 0), "diameter": 20}),
                ("sketch.finish", {}),
                (
                    "solid.extrude",
                    {
                        "distance": 10,
                        "profiles": [{"curves": ["c1", "c2", "c3", "c4"]}],
                        "body_name": "Plate",
                    },
                ),
                (
                    "appearance.assign",
                    {"bodies": ["Plate"], "color": "#ADD8E6"},
                ),
                ("view.apply", {"view": "iso"}),
                ("file.export", {"path": str(step)}),
            ],
        )
        self.assertEqual(output.getvalue(), f"Wrote {step}\n")

    # Method `TestHeadlessTransport.test_not_found()`:
    def test_not_found(self) -> None:
        """A `cli` that cannot be found raises `FileNotFoundError`."""
        with (
            SCHeadlessTransport("no-such-solidcraft-cli") as transport,
            self.assertRaises(FileNotFoundError) as caught,
        ):
            transport.request("engine.execute", {})
        self.assertIn("`PATH`", str(caught.exception))


# Class `TestGenerator`:
class TestGenerator(unittest.TestCase):
    """`scraftpybind_generate.py`."""

    # Method `TestGenerator.run_generator()`:
    def run_generator(self, folder: Path, *arguments: str) -> None:
        """Run the generator, in this process, on copies in `folder`.

        Arguments:
        * `folder` (`Path`): An empty scratch folder.
        * `arguments` (`str`): The generator's arguments.
        """
        # Copy what the generator reads and writes (`ruff.toml` too,
        # which sets the line length that `ruff format` uses).
        name: str
        for name in (
            "scraftpybind.py",
            "scraftpybind_commands.json",
            "ruff.toml",
        ):
            shutil.copy(HERE / name, folder / name)

        # Point the generator at the copies, and run it.
        output: io.StringIO = io.StringIO()
        with (
            mock.patch.object(
                scraftpybind_generate, "TARGET", folder / "scraftpybind.py"
            ),
            mock.patch.object(
                scraftpybind_generate,
                "CACHE",
                folder / "scraftpybind_commands.json",
            ),
            mock.patch.object(
                sys, "argv", ["scraftpybind_generate.py", *arguments]
            ),
            contextlib.redirect_stdout(output),
        ):
            status: int = scraftpybind_generate.main()
        self.assertEqual(status, 0)
        self.assertIn("407 commands", output.getvalue())

    # Method `TestGenerator.test_cached()`:
    @unittest.skipIf(shutil.which("ruff") is None, "needs `ruff`")
    def test_cached(self) -> None:
        """`--cached` writes `scraftpybind.py` exactly as it is."""
        with tempfile.TemporaryDirectory() as name:
            folder: Path = Path(name)
            self.run_generator(folder, "--cached")
            self.assertEqual(
                (folder / "scraftpybind.py").read_text(encoding="utf-8"),
                MODULE.read_text(encoding="utf-8"),
            )

    # Method `TestGenerator.test_fetch()`:
    @unittest.skipIf(CLI is None, "needs `solidcraft-cli` on the PATH")
    @unittest.skipIf(shutil.which("ruff") is None, "needs `ruff`")
    def test_fetch(self) -> None:  # pragma: no cover
        """Fetching from `solidcraft-cli` gives the cached commands."""
        # Only the version that made the cache must agree with it.
        assert CLI is not None
        version: str = subprocess.run(
            [CLI, "--version"], capture_output=True, check=True, text=True
        ).stdout.strip()
        if version != CACHED_VERSION:
            self.skipTest(f"{version}, not {CACHED_VERSION}")

        # Fetch and generate, then compare both files.
        with tempfile.TemporaryDirectory() as name:
            folder: Path = Path(name)
            self.run_generator(folder)
            self.assertEqual(
                (folder / "scraftpybind_commands.json").read_text(
                    encoding="utf-8"
                ),
                CACHE.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (folder / "scraftpybind.py").read_text(encoding="utf-8"),
                MODULE.read_text(encoding="utf-8"),
            )


# Class `TestHeadlessLive`:
@unittest.skipIf(CLI is None, "needs `solidcraft-cli` on the PATH")
class TestHeadlessLive(unittest.TestCase):  # pragma: no cover
    """Headless SolidCraft sessions that build and measure plates."""

    # Method `TestHeadlessLive.test_module_plate()`:
    def test_module_plate(self) -> None:
        """`scraftpybind.py headless` exports a plate with a hole."""
        with tempfile.TemporaryDirectory() as name:
            folder: Path = Path(name)
            done: subprocess.CompletedProcess[str] = run_python(
                [str(MODULE), "headless"], folder
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            body: dict[str, Any] = measure(folder / "scraftpybind_plate.step")
        self.assertLess(
            relative_error(
                body["volume_mm3"], 100 * 60 * 10 - math.pi * 10**2 * 10
            ),
            VOLUME_TOLERANCE,
        )
        self.assertEqual(body["bbox"]["min"], [-50.0, -30.0, 0.0])
        self.assertEqual(body["bbox"]["max"], [50.0, 30.0, 10.0])

    # Method `TestHeadlessLive.test_example_plate()`:
    def test_example_plate(self) -> None:
        """`examples/plate_with_holes.py` exports a plate, 4 holes."""
        with tempfile.TemporaryDirectory() as name:
            folder: Path = Path(name)
            step: Path = folder / "plate.step"
            done: subprocess.CompletedProcess[str] = run_python(
                [str(EXAMPLE), "headless", str(step)], folder
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            body: dict[str, Any] = measure(step)
        self.assertLess(
            relative_error(
                body["volume_mm3"], 100 * 60 * 10 - 4 * math.pi * 4**2 * 10
            ),
            VOLUME_TOLERANCE,
        )
        self.assertEqual(body["face_types"], {"cylinder": 4, "plane": 6})

    # Method `TestHeadlessLive.test_example_usage()`:
    def test_example_usage(self) -> None:
        """The example with no arguments prints its usage."""
        with tempfile.TemporaryDirectory() as name:
            done: subprocess.CompletedProcess[str] = run_python(
                [str(EXAMPLE)], Path(name)
            )
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage:", done.stderr)

    # Method `TestHeadlessLive.test_results_and_errors()`:
    def test_results_and_errors(self) -> None:
        """Results come back as JSON; a failed command raises."""
        with SCHeadlessTransport() as transport:
            solidcraft: SCPyBind = SCPyBind(transport)
            solidcraft.sketch.create(plane="XY", name="Square")
            square: JSON = solidcraft.sketch.rectangle_center(
                center=(0, 0), corner=(5, 5)
            )
            assert isinstance(square, dict)
            self.assertEqual(len(square["curves"]), 4)
            with self.assertRaises(SCSolidCraftError) as caught:
                solidcraft.sketch.execute("no.such.command", {})
            self.assertEqual(caught.exception.method, "engine.execute")
            self.assertFalse(caught.exception.running)


# Class `TestGuiLive`:
@unittest.skipUnless(
    GUI_PORT, "needs `SCRAFTPYBIND_TEST_PORT` (a GUI's control port)"
)
class TestGuiLive(unittest.TestCase):  # pragma: no cover
    """A SolidCraft GUI started with `solidcraft --control PORT`."""

    # Method `TestGuiLive.test_module_plate()`:
    def test_module_plate(self) -> None:
        """`scraftpybind.py PORT` builds the plate in the GUI."""
        with tempfile.TemporaryDirectory() as name:
            done: subprocess.CompletedProcess[str] = run_python(
                [str(MODULE), GUI_PORT], Path(name)
            )
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
