#!/usr/bin/env python3
"""Drive SolidCraft from Python, one method per JSON command.

`SCPyBind` runs SolidCraft commands (`sketch.create`,
`solid.extrude`, ...) through a `SCTransport`:
* `SCControlTransport` talks to a running SolidCraft GUI over its
  control port (SolidCraft's `docs/control-protocol.md`: one JSON request per
  line, and one JSON reply per line), so the design can be watched.
* `SCHeadlessTransport` runs `solidcraft-cli mcp --headless`, a design
  session with no window, and talks MCP to it (SolidCraft's
  `docs/mcp.md`).

Each command is one method, in a class named after the command's
namespace: `sketch.rectangle.center` is
`SCPyBind.sketch.rectangle_center()`.  Parameters left at `None`
are not sent, so SolidCraft uses its own defaults for them.

Run directly, it builds a 100 x 60 x 10 mm plate with a 20 mm hole,
either in a GUI started with `solidcraft --control PORT`, or headless
(which is only useful with `file.export`, so it exports
`scraftpybind_plate.step`):

```
python3 scraftpybind.py 8080
python3 scraftpybind.py headless
```
"""

# The generated command classes keep SolidCraft's own command and
# parameter names (`format`, `type`, `connect`, ...), take one argument
# per SolidCraft parameter and one method per command, so these
# messages are expected there.
# pylint: disable=too-many-lines,too-many-arguments,redefined-builtin
# pylint: disable=redefined-outer-name,too-many-locals
# pylint: disable=too-many-public-methods,too-many-instance-attributes

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import IO, Literal, Self, TextIO, TypeAlias

# The package version, which `pyproject.toml` reads.
__version__: str = "0.2.0"

# A JSON value.  `Mapping` and `Sequence` (rather than `dict` and
# `list`) let a `list[str]` or a `tuple[float, float]` be passed where
# JSON is wanted.  (The type alias names follow `mypy`'s usage, not
# `pylint`'s `T`-prefixed style.)
JSON: TypeAlias = (  # pylint: disable=invalid-name
    Mapping[str, "JSON"] | Sequence["JSON"] | str | int | float | bool | None
)

# An expression: a number in the design's units, or a string such as
# "60 mm" or "width" (a parameter's name).
Expr: TypeAlias = float | str

# A point on a sketch, `[x, y]`, and a point in the world, `[x, y, z]`.
Point2D: TypeAlias = tuple[float, float]  # pylint: disable=invalid-name
Point3D: TypeAlias = tuple[float, float, float]  # pylint: disable=invalid-name

# The longest SolidCraft takes to answer a request (3600 s for
# `engine.batch`), plus a minute of slack.
REPLY_TIMEOUT: float = 3660.0

# Where SolidCraft is downloaded, for the message when it is missing.
RELEASES: str = "https://github.com/tangency-labs/solidcraft/releases"

# How long a headless session gets to exit, in seconds: after its
# output ends, or after its input is closed (it is then killed).
EXIT_TIMEOUT: float = 10.0


# Class `SCSolidCraftError`:
class SCSolidCraftError(Exception):
    """A SolidCraft request that failed.

    Attributes:
    * `method` (`str`): The request's method (e.g. `engine.execute`).
    * `error` (`str`): The error text SolidCraft sent back.
    * `running` (`bool`):
      True when the request timed out but is still running in the app;
      it has not failed, so it must not simply be sent again.
    * `busy` (`bool`):
      True when the request was refused, without running, because an
      earlier request on this connection is still running.
    """

    # Method `SCSolidCraftError.__init__()`:
    def __init__(
        self, method: str, error: str, running: bool, busy: bool
    ) -> None:
        """Record why a request failed.

        Arguments:
        * `method` (`str`): The request's method.
        * `error` (`str`): The error text SolidCraft sent back.
        * `running` (`bool`): True when it is still running.
        * `busy` (`bool`): True when it was refused as busy.
        """
        super().__init__(f"{method}: {error}")
        self.method: str = method
        self.error: str = error
        self.running: bool = running
        self.busy: bool = busy


# Function `control_dir()`:
def control_dir() -> Path:
    """Return the folder holding SolidCraft's port and token files.

    Only the Linux location is known so far; `SOLIDCRAFT_CONTROL_DIR`
    overrides it, as it does for SolidCraft itself.

    Returns:
    * (`Path`): The control folder.
    """
    # An explicit folder wins over the XDG data folder.
    explicit: str = os.environ.get("SOLIDCRAFT_CONTROL_DIR", "")
    if explicit:
        return Path(explicit)
    data_home: str = os.environ.get("XDG_DATA_HOME", "")
    data: Path = Path(data_home) if data_home else Path.home() / ".local/share"
    return data / "solidcraft" / "control"


# Class `SCTransport`:
@dataclass(slots=True)
class SCTransport:
    """The base of the ways to send requests to SolidCraft.

    A transport is a context manager, closing itself on exit.

    Constructor:
    * `SCTransport()`
    """

    # Method `SCTransport.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Send one request and return its result.

        Arguments:
        * `method` (`str`): The method (e.g. `engine.execute`).
        * `params` (`Mapping[str, JSON]`): The method's parameters.

        Returns:
        * (`JSON`): The request's result.

        Raises:
        * `NotImplementedError`: Always; each transport has its own.
        """
        raise NotImplementedError(f"{type(self).__name__}.request")

    # Method `SCTransport.close()`:
    def close(self) -> None:
        """Close the transport, if it is open."""

    # Method `SCTransport.__enter__()`:
    def __enter__(self) -> Self:
        """Return this transport for a `with` statement.

        Returns:
        * (`Self`): This transport.
        """
        return self

    # Method `SCTransport.__exit__()`:
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the transport at the end of a `with` statement.

        Arguments:
        * `exc_type` (`type[BaseException] | None`): Unused.
        * `exc_value` (`BaseException | None`): Unused.
        * `traceback` (`TracebackType | None`): Unused.
        """
        self.close()


# Class `SCControlTransport`:
@dataclass(slots=True)
class SCControlTransport(SCTransport):
    """A connection to a running SolidCraft GUI's control port.

    Each request is one line `{"id", "method", "params"}`, and each
    reply is one line `{"id", "ok": true, "result"}` or `{"id", "ok":
    false, "error"}`.  The first request on a connection also carries
    the launch's token.

    Attributes:
    * `port` (`int`):
      The control port, or 0 to use the one in `current.port`.  Only a
      SolidCraft on its default port (27878 and up) writes that file; a
      launch with `--control PORT` does not.
    * `host` (`str`): The host, which SolidCraft insists is local.
    * `token` (`str`):
      The launch's token, or "" to use `SOLIDCRAFT_CONTROL_TOKEN` or
      else the port's token file.
    * `next_id` (`int`): The id the next request gets.
    * `reader` (`TextIO | None`): Reads the replies, once connected.
    * `sock` (`socket.socket | None`): The socket, once connected.

    Constructor:
    * `SCControlTransport(port, host, token)`
    """

    # Constructor arguments:
    port: int = field(init=True, default=0)
    host: str = field(init=True, default="127.0.0.1")
    token: str = field(init=True, default="")

    # Connection state (alphabetized):
    next_id: int = field(init=False, default=1)
    reader: TextIO | None = field(init=False, default=None)
    sock: socket.socket | None = field(init=False, default=None)

    # Method `SCControlTransport.connect()`:
    def connect(self) -> None:
        """Connect to SolidCraft, finding the port and token if needed.

        Raises:
        * `FileNotFoundError`:
          If the port or token file is missing, which usually means
          that no SolidCraft GUI is running (it deletes its token file
          when it quits).
        * `ConnectionRefusedError`: If nothing listens on the port.
        * `OSError`: If a file cannot be read for another reason.
        """
        # Find the port of the most recently started SolidCraft.
        if self.port == 0:
            port_file: Path = control_dir() / "current.port"
            if not port_file.exists():
                raise FileNotFoundError(
                    f"{port_file} not found: is a SolidCraft GUI running"
                    " on its default port, as this user?"
                )
            self.port = int(port_file.read_text().strip())

        # Find this launch's token.
        if not self.token:
            self.token = os.environ.get("SOLIDCRAFT_CONTROL_TOKEN", "")
        if not self.token:
            token_file: Path = control_dir() / f"{self.port}.token"
            if not token_file.exists():
                raise FileNotFoundError(
                    f"{token_file} not found: is a SolidCraft GUI running"
                    f" with `--control {self.port}`, as this user?"
                )
            self.token = token_file.read_text().strip()

        # Open the connection; the token goes with the first request.
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=REPLY_TIMEOUT
            )
        except ConnectionRefusedError as error:
            raise ConnectionRefusedError(
                f"{self.host}:{self.port}: nothing is listening: is a"
                f" SolidCraft GUI running with `--control {self.port}`?"
            ) from error
        self.reader = self.sock.makefile("r", encoding="utf-8")
        self.next_id = 1

    # Method `SCControlTransport.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Send one request and return its result.

        Arguments:
        * `method` (`str`): The method (e.g. `engine.execute`).
        * `params` (`Mapping[str, JSON]`): The method's parameters.

        Returns:
        * (`JSON`): The reply's `result`.

        Raises:
        * `SCSolidCraftError`: If SolidCraft answers `"ok": false`.
        * `ConnectionError`:
          If the connection closes or the reply does not match.
        """
        # Connect on first use.
        if self.sock is None:
            self.connect()
        assert self.sock is not None and self.reader is not None

        # Send the request as one line.
        request_id: int = self.next_id
        self.next_id += 1
        message: dict[str, JSON] = {
            "id": request_id,
            "method": method,
            "params": params,
        }
        if request_id == 1:
            message["token"] = self.token
        line: str = json.dumps(message) + "\n"
        self.sock.sendall(line.encode("utf-8"))

        # Read the one line reply; check that it answers this request.
        reply_line: str = self.reader.readline()
        if not reply_line:
            raise ConnectionError(f"{method}: SolidCraft closed the port")
        reply: JSON = json.loads(reply_line)
        if not isinstance(reply, dict) or reply.get("id") != request_id:
            raise ConnectionError(f"{method}: unexpected reply {reply!r}")

        # Return the result, or raise the error.
        if reply.get("ok") is True:
            result: JSON = reply.get("result")
            return result
        raise SCSolidCraftError(
            method,
            str(reply.get("error", "")),
            reply.get("running") is True,
            reply.get("busy") is True,
        )

    # Method `SCControlTransport.close()`:
    def close(self) -> None:
        """Close the connection, if it is open."""
        # Close the reader first, since it wraps the socket.
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None


# Class `SCHeadlessTransport`:
@dataclass(slots=True)
class SCHeadlessTransport(SCTransport):
    """A headless SolidCraft session: `solidcraft-cli mcp --headless`.

    The session holds one design in memory, with no window.  It speaks
    MCP (JSON-RPC 2.0, one message per line) on its standard input and
    output; each `engine.execute` request becomes a call of its
    `execute` tool.  It reads and writes files only in `allow_paths`
    (and its own folders).

    Attributes:
    * `cli` (`str`):
      The `solidcraft-cli` program: a path, or a name to look up on the
      `PATH`.
    * `allow_paths` (`Sequence[str]`):
      The folders the session may read and write files in (default: the
      current folder).
    * `errors` (`IO[bytes] | None`):
      Keeps what the session writes to its standard error, while it
      runs.
    * `next_id` (`int`): The id the next message gets.
    * `process` (`subprocess.Popen[str] | None`):
      The session, once started.

    Constructor:
    * `SCHeadlessTransport(cli, allow_paths)`
    """

    # Constructor arguments:
    cli: str = field(init=True, default="solidcraft-cli")
    allow_paths: Sequence[str] = field(init=True, default=())

    # Session state (alphabetized):
    errors: IO[bytes] | None = field(init=False, default=None)
    next_id: int = field(init=False, default=1)
    process: subprocess.Popen[str] | None = field(init=False, default=None)

    # Method `SCHeadlessTransport.start()`:
    def start(self) -> None:
        """Start the session and complete the MCP handshake.

        Raises:
        * `FileNotFoundError`: If `cli` cannot be found.
        * `ConnectionError`: If the session does not start.
        """
        # Find the program, and the folders it may use.
        program: str | None = shutil.which(self.cli)
        if program is None:
            raise FileNotFoundError(
                f"{self.cli} not found: install SolidCraft"
                f" ({RELEASES}) and put `solidcraft-cli` on the `PATH`"
            )
        folders: Sequence[str] = self.allow_paths or (os.getcwd(),)
        command: list[str] = [program, "mcp", "--headless"]
        folder: str
        for folder in folders:
            command += ["--allow-path", str(Path(folder).resolve())]

        # Start it, keeping its standard error for when it fails (in a
        # file that lives as long as the session, so not in a `with`).
        # The process, too, lives as long as the session.
        self.errors = tempfile.TemporaryFile()  # noqa: SIM115
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
            encoding="utf-8",
        )
        self.next_id = 1

        # The handshake: `initialize`, then `notifications/initialized`.
        self.call(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "scraftpybind", "version": "0"},
            },
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # Method `SCHeadlessTransport.send()`:
    def send(self, message: Mapping[str, JSON]) -> None:
        """Send one MCP message as one line.

        Arguments:
        * `message` (`Mapping[str, JSON]`): The message.
        """
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    # Method `SCHeadlessTransport.call()`:
    def call(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Send one MCP request and return its `result`.

        Arguments:
        * `method` (`str`): The MCP method (e.g. `tools/call`).
        * `params` (`Mapping[str, JSON]`): Its parameters.

        Returns:
        * (`JSON`): The reply's `result`.

        Raises:
        * `SCSolidCraftError`: If the reply is a JSON-RPC error.
        * `ConnectionError`: If the session has stopped.
        """
        # Send the request.
        assert self.process is not None and self.process.stdout is not None
        request_id: int = self.next_id
        self.next_id += 1
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )

        # Read lines until the reply to it, skipping notifications.
        while True:
            line: str = self.process.stdout.readline()
            if not line:
                raise ConnectionError(f"{method}: {self.stopped()}")
            reply: JSON = json.loads(line)
            if isinstance(reply, dict) and reply.get("id") == request_id:
                break

        # Return the result, or raise the error.
        error: JSON = reply.get("error")
        if isinstance(error, dict):
            raise SCSolidCraftError(
                method, str(error.get("message", "")), False, False
            )
        result: JSON = reply.get("result")
        return result

    # Method `SCHeadlessTransport.stopped()`:
    def stopped(self) -> str:
        """Describe how the session stopped, with its last error text.

        Returns:
        * (`str`): Its exit status and the end of its standard error.
        """
        # Wait for the exit status (its output can end before it
        # exits), then read what it wrote.
        assert self.process is not None and self.errors is not None
        status: int | None
        try:
            status = self.process.wait(timeout=EXIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            status = None
        self.errors.seek(0)
        text: str = self.errors.read().decode("utf-8", "replace").strip()
        return f"the session stopped ({status=}): {text[-500:]}"

    # Method `SCHeadlessTransport.request()`:
    def request(self, method: str, params: Mapping[str, JSON]) -> JSON:
        """Send one request and return its result.

        Only `engine.execute` exists headless; the `ui.*` methods need
        the GUI.

        Arguments:
        * `method` (`str`): The method (`engine.execute`).
        * `params` (`Mapping[str, JSON]`): `command` and `params`.

        Returns:
        * (`JSON`): The command's result.

        Raises:
        * `SCSolidCraftError`:
          If the command fails, or `method` is not `engine.execute`.
        * `ConnectionError`: If the session has stopped.
        """
        # Start on first use.
        if method != "engine.execute":
            raise SCSolidCraftError(method, "needs the GUI", False, False)
        if self.process is None:
            self.start()

        # Call the `execute` tool, whose result is the command's JSON
        # result as text, or the error text when `isError` is set.
        result: JSON = self.call(
            "tools/call", {"name": "execute", "arguments": params}
        )
        if not isinstance(result, Mapping):
            raise ConnectionError(f"{method}: unexpected reply {result!r}")
        content: JSON = result.get("content")
        text: str = ""
        if isinstance(content, Sequence) and content:
            first: JSON = content[0]
            if isinstance(first, Mapping):
                text = str(first.get("text", ""))
        if result.get("isError") is True:
            raise SCSolidCraftError(method, text, False, False)
        try:
            parsed: JSON = json.loads(text)
        except json.JSONDecodeError:
            return text
        return parsed

    # Method `SCHeadlessTransport.close()`:
    def close(self) -> None:
        """Stop the session, if it is running."""
        # Closing its standard input ends the session.
        if self.process is not None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=EXIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            if self.process.stdout is not None:
                self.process.stdout.close()
            self.process = None
        if self.errors is not None:
            self.errors.close()
            self.errors = None


# Function `connect()`:
def connect(where: str) -> SCTransport:
    """Return a transport for a port number, or for `headless`.

    Arguments:
    * `where` (`str`):
      A GUI's control port (e.g. `8080`), or `headless` for a session
      with no window.

    Returns:
    * (`SCTransport`): The transport, which connects on first use.

    Raises:
    * `ValueError`: If `where` is neither.
    """
    if where == "headless":
        return SCHeadlessTransport()
    if not where.isdigit():
        raise ValueError(f"{where=} is not a port number or `headless`")
    return SCControlTransport(int(where))


# Class `SCNamespace`:
@dataclass(slots=True)
class SCNamespace:
    """The base of the classes that hold one namespace's commands.

    Attributes:
    * `transport` (`SCTransport`): How the commands are sent.

    Constructor:
    * `SCNamespace(transport)`
    """

    # Constructor arguments:
    transport: SCTransport = field(init=True)

    # Method `SCNamespace.execute()`:
    def execute(self, command: str, params: Mapping[str, JSON]) -> JSON:
        """Run one command, leaving out the parameters that are `None`.

        Arguments:
        * `command` (`str`): The command id (e.g. `sketch.create`).
        * `params` (`Mapping[str, JSON]`):
          The command's parameters; those that are `None` are not sent.

        Returns:
        * (`JSON`): The command's result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        sent: dict[str, JSON] = {
            name: value for name, value in params.items() if value is not None
        }
        return self.transport.request(
            "engine.execute", {"command": command, "params": sent}
        )


# Begin the generated command classes.
# Never edit them: they are written by `scraftpybind_generate.py`.

# The `format` of `assembly.bom`.
AssemblyBomFormat: TypeAlias = Literal["csv", "json"]

# The `folder` of `browser.group`.
BrowserGroupFolder: TypeAlias = Literal["bodies", "sketches", "construction"]

# The `folder` of `browser.visibility`.
BrowserVisibilityFolder: TypeAlias = Literal[
    "bodies", "sketches", "construction", "origin", "joints"
]

# The `base` of `construct.plane.at_angle`.
ConstructPlaneAtAngleBase: TypeAlias = Literal["XY", "XZ", "YZ", "plane"]

# The `base` of `construct.plane.offset`.
ConstructPlaneOffsetBase: TypeAlias = Literal["XY", "XZ", "YZ", "plane"]

# The `set` of `contact.edit`.
ContactEditSet: TypeAlias = Literal["id", "name"]

# The values of `Direction` in SolidCraft's schemas.
Direction: TypeAlias = Literal[
    "positive", "negative", "symmetric", "one_side", "reverse", "flip"
]

# The `names` of `doc.open`.
DocOpenNames: TypeAlias = Literal["auto", "solid", "product", "instance"]

# The `up` of `doc.open`.
DocOpenUp: TypeAlias = Literal["z", "y"]

# The `units` of `document.units`.
DocumentUnitsUnits: TypeAlias = Literal["mm", "cm", "m", "in", "ft"]

# The `view` of `explode.show`.
ExplodeShowView: TypeAlias = Literal["id", "name"]

# The `kind` of `expr.evaluate`.
ExprEvaluateKind: TypeAlias = Literal["length", "angle", "unitless"]

# The values of `ExtentKeyword` in SolidCraft's schemas.
ExtentKeyword: TypeAlias = Literal["through_all"]

# The values of `ExtrudeConvention` in SolidCraft's schemas.
ExtrudeConvention: TypeAlias = Literal["total_distance", "legacy_per_side"]

# The values of `ExtrudeOperation` in SolidCraft's schemas.
ExtrudeOperation: TypeAlias = Literal[
    "auto",
    "new",
    "join",
    "cut",
    "intersect",
    "new_body",
    "newbody",
    "new_component",
    "newcomponent",
    "union",
    "add",
    "subtract",
    "difference",
    "intersection",
]

# The `format` of `file.export`.
FileExportFormat: TypeAlias = Literal[
    "stl", "stla", "obj", "step", "3mf", "3mf-tagged", "urdf", "json"
]

# The `hidden` of `file.export_view_dxf`.
FileExportViewDxfHidden: TypeAlias = Literal["omit", "dashed"]

# The `compression` of `file.save_as`.
FileSaveAsCompression: TypeAlias = Literal["fast", "compact"]

# The `format` of `file.save_as`.
FileSaveAsFormat: TypeAlias = Literal["container", "json"]

# The `compression` of `file.save`.
FileSaveCompression: TypeAlias = Literal["fast", "compact"]

# The `format` of `file.save`.
FileSaveFormat: TypeAlias = Literal["container", "json"]

# The `format` of `file.save_mesh`.
FileSaveMeshFormat: TypeAlias = Literal["stl", "3mf", "3mf-tagged"]

# The `view` of `inspect.silhouette`.
InspectSilhouetteView: TypeAlias = Literal[
    "front", "back", "left", "right", "top", "bottom", "iso"
]

# The `follower` of `joint.cam`.
JointCamFollower: TypeAlias = Literal["knife", "roller", "flat"]

# The `type` of `joint.create`.
JointCreateType: TypeAlias = Literal[
    "rigid", "revolute", "slider", "cylindrical", "pin_slot", "planar", "ball"
]

# The `joint` of `joint.delete`.
JointDeleteJoint: TypeAlias = Literal["id", "name"]

# The `joint` of `joint.drive`.
JointDriveJoint: TypeAlias = Literal["id", "name"]

# The `joint` of `joint.inspect`.
JointInspectJoint: TypeAlias = Literal["id", "name"]

# The `occurrence` of `joint.origin`.
JointOriginOccurrence: TypeAlias = Literal["id", "name"]

# The `occurrence` of `joint.reach`.
JointReachOccurrence: TypeAlias = Literal["id", "name"]

# The `joint` of `joint.sweep`.
JointSweepJoint: TypeAlias = Literal["id", "name"]

# The `joint` of `motion.export_animation`.
MotionExportAnimationJoint: TypeAlias = Literal["id", "name"]

# The `study` of `motion.export_animation`.
MotionExportAnimationStudy: TypeAlias = Literal["id", "name"]

# The `study` of `motion.interference`.
MotionInterferenceStudy: TypeAlias = Literal["id", "name"]

# The `study` of `motion.play`.
MotionPlayStudy: TypeAlias = Literal["id", "name"]

# The `study` of `motion.plot`.
MotionPlotStudy: TypeAlias = Literal["id", "name"]

# The `joint` of `motion.trace`.
MotionTraceJoint: TypeAlias = Literal["id", "name"]

# The `joint` of `motion.trace.keep`.
MotionTraceKeepJoint: TypeAlias = Literal["id", "name"]

# The `occurrence` of `motion.trace.keep`.
MotionTraceKeepOccurrence: TypeAlias = Literal["id", "name"]

# The `study` of `motion.trace.keep`.
MotionTraceKeepStudy: TypeAlias = Literal["id", "name"]

# The `occurrence` of `motion.trace`.
MotionTraceOccurrence: TypeAlias = Literal["id", "name"]

# The `study` of `motion.trace`.
MotionTraceStudy: TypeAlias = Literal["id", "name"]

# The `space` of `occurrence.move`.
OccurrenceMoveSpace: TypeAlias = Literal["local", "world"]

# The values of `Operation` in SolidCraft's schemas.
Operation: TypeAlias = Literal[
    "new",
    "join",
    "cut",
    "intersect",
    "new_body",
    "newbody",
    "new_component",
    "newcomponent",
    "union",
    "add",
    "subtract",
    "difference",
    "intersection",
]

# The `format` of `parameters.export`.
ParametersExportFormat: TypeAlias = Literal["csv", "json"]

# The `filter` of `parameters.list`.
ParametersListFilter: TypeAlias = Literal[
    "all", "user", "sketch", "feature", "favorites"
]

# The `component` of `parts.resize`.
PartsResizeComponent: TypeAlias = Literal["id", "name"]

# The `side` of `plastic.lip`.
PlasticLipSide: TypeAlias = Literal["inside", "outside"]

# The `type` of `plastic.lip`.
PlasticLipType: TypeAlias = Literal["lip", "groove"]

# The `format` of `sheet.export_bend_table`.
SheetExportBendTableFormat: TypeAlias = Literal["csv", "json"]

# The `curves` of `sheet.export_dxf`.
SheetExportDxfCurves: TypeAlias = Literal["exact", "arcs"]

# The `text` of `sheet.export_dxf`.
SheetExportDxfText: TypeAlias = Literal["cut", "etch"]

# The `corner_relief_shape` of `sheet.flange`.
SheetFlangeCornerReliefShape: TypeAlias = Literal[
    "notch", "round", "rectangular", "tear"
]

# The `position` of `sheet.flange`.
SheetFlangePosition: TypeAlias = Literal["inside", "outside", "middle"]

# The `type` of `sheet.flange`.
SheetFlangeType: TypeAlias = Literal["base", "edge", "contour"]

# The `position` of `sheet.fold`.
SheetFoldPosition: TypeAlias = Literal["centerline", "start", "end", "mould"]

# The `corner_relief_shape` of `sheet.manage_rules`.
SheetManageRulesCornerReliefShape: TypeAlias = Literal[
    "notch", "round", "rectangular", "tear"
]

# The `continuity` of `sketch.blend_curve`.
SketchBlendCurveContinuity: TypeAlias = Literal["g1", "g2", "g3", "g4"]

# The `mode` of `sketch.constraint.horizontal_vertical`.
SketchConstraintHorizontalVerticalMode: TypeAlias = Literal[
    "horizontal", "vertical"
]

# The `type` of `sketch.dimension`.
SketchDimensionType: TypeAlias = Literal[
    "auto",
    "distance",
    "horizontal",
    "vertical",
    "length",
    "radius",
    "diameter",
    "angle",
]

# The `align` of `sketch.edit_text`.
SketchEditTextAlign: TypeAlias = Literal["left", "center", "right"]

# The `sketch` of `sketch.export_dxf`.
SketchExportDxfSketch: TypeAlias = Literal["id", "name"]

# The `sketch` of `sketch.glyphs`.
SketchGlyphsSketch: TypeAlias = Literal["id", "name"]

# The `sketch` of `sketch.inspect`.
SketchInspectSketch: TypeAlias = Literal["id", "name"]

# The `sketch` of `sketch.loose_ends`.
SketchLooseEndsSketch: TypeAlias = Literal["id", "name"]

# The `sketch` of `sketch.loose_ends.tie`.
SketchLooseEndsTieSketch: TypeAlias = Literal["id", "name"]

# The `direction` of `sketch.offset`.
SketchOffsetDirection: TypeAlias = Literal["one_side", "symmetric"]

# The `sketch` of `sketch.options`.
SketchOptionsSketch: TypeAlias = Literal["id", "name"]

# The `alignment` of `sketch.pattern.circular`.
SketchPatternCircularAlignment: TypeAlias = Literal["left", "center", "right"]

# The `alignment2` of `sketch.pattern.rectangular`.
SketchPatternRectangularAlignment2: TypeAlias = Literal[
    "left", "center", "right"
]

# The `align` of `sketch.text`.
SketchTextAlign: TypeAlias = Literal["left", "center", "right"]

# The `operation` of `solid.boundary_fill`.
SolidBoundaryFillOperation: TypeAlias = Literal[
    "new", "join", "cut", "intersect"
]

# The `section` of `solid.coil`.
SolidCoilSection: TypeAlias = Literal["circular", "square"]

# The `section_position` of `solid.coil`.
SolidCoilSectionPosition: TypeAlias = Literal["inside", "center", "outside"]

# The `operation` of `solid.combine`.
SolidCombineOperation: TypeAlias = Literal["join", "cut", "intersect"]

# The `mode` of `solid.emboss`.
SolidEmbossMode: TypeAlias = Literal["emboss", "deboss"]

# The `profiles` of `solid.extrude`.
SolidExtrudeProfiles: TypeAlias = (
    str
    | int
    | Sequence[int]
    | Sequence[JSON]
    | Sequence[Sequence[str] | JSON]
    | JSON
)

# The `corner` of `solid.fillet`.
SolidFilletCorner: TypeAlias = Literal["rolling", "g2"]

# The `fit` of `solid.fillet`.
SolidFilletFit: TypeAlias = Literal["exact", "reduce", "taper"]

# The `type` of `solid.hole`.
SolidHoleType: TypeAlias = Literal[
    "simple", "drilled", "counterbore", "countersink"
]

# The `rail_fit` of `solid.loft`.
SolidLoftRailFit: TypeAlias = Literal["scale", "stretch"]

# The `alignment` of `solid.pattern.circular`.
SolidPatternCircularAlignment: TypeAlias = Literal["left", "center", "right"]

# The `orientation` of `solid.pattern.path`.
SolidPatternPathOrientation: TypeAlias = Literal["identical", "path"]

# The `alignment2` of `solid.pattern.rectangular`.
SolidPatternRectangularAlignment2: TypeAlias = Literal[
    "left", "center", "right"
]

# The `convention` of `solid.revolve`.
SolidRevolveConvention: TypeAlias = Literal[
    "sketch_normal", "legacy_axis_start"
]

# The `direction` of `solid.rib`.
SolidRibDirection: TypeAlias = Literal["in_plane", "normal"]

# The `direction` of `solid.shell`.
SolidShellDirection: TypeAlias = Literal["inside", "outside", "both"]

# The `direction` of `solid.web`.
SolidWebDirection: TypeAlias = Literal["in_plane", "normal"]

# The `operation` of `surface.boundary`.
SurfaceBoundaryOperation: TypeAlias = Literal["new", "join"]

# The `direction` of `surface.extrude`.
SurfaceExtrudeDirection: TypeAlias = Literal[
    "positive", "negative", "symmetric"
]

# The `sketch` of `surface.extrude`.
SurfaceExtrudeSketch: TypeAlias = Literal["id", "name"]

# The `trim` of `surface.fillet`.
SurfaceFilletTrim: TypeAlias = Literal["both", "first", "none"]

# The `order` of `surface.match`.
SurfaceMatchOrder: TypeAlias = Literal["g1", "g2", "g3"]

# The `sketch` of `surface.patch`.
SurfacePatchSketch: TypeAlias = Literal["id", "name"]

# The `sketch` of `surface.revolve`.
SurfaceRevolveSketch: TypeAlias = Literal["id", "name"]

# The `corners` of `surface.ruled`.
SurfaceRuledCorners: TypeAlias = Literal["mitre", "round"]

# The `mode` of `surface.ruled`.
SurfaceRuledMode: TypeAlias = Literal[
    "normal", "tangent", "angle", "direction"
]

# The `sketch` of `surface.sweep`.
SurfaceSweepSketch: TypeAlias = Literal["id", "name"]

# The `operation` of `surface.thicken`.
SurfaceThickenOperation: TypeAlias = Literal["new", "join", "cut", "intersect"]

# The values of `ThinSide` in SolidCraft's schemas.
ThinSide: TypeAlias = Literal[
    "center",
    "inside",
    "outside",
    "two_sides",
    "centre",
    "centered",
    "centred",
    "symmetric",
    "side1",
    "side_1",
    "side2",
    "side_2",
    "both",
]

# The `feature` of `timeline.delete`.
TimelineDeleteFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.dependents`.
TimelineDependentsFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.edit`.
TimelineEditFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.inspect`.
TimelineInspectFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.redefine`.
TimelineRedefineFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.rename`.
TimelineRenameFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.reorder`.
TimelineReorderFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.roll_to`.
TimelineRollToFeature: TypeAlias = Literal["id", "name"]

# The `feature` of `timeline.suppress`.
TimelineSuppressFeature: TypeAlias = Literal["id", "name"]

# The `preset` of `view.graphics_preset`.
ViewGraphicsPresetPreset: TypeAlias = Literal["performance", "quality"]

# The `dock` of `view.history_layout`.
ViewHistoryLayoutDock: TypeAlias = Literal["bottom", "left", "under_browser"]

# The `mode` of `view.layout`.
ViewLayoutMode: TypeAlias = Literal["floating", "compact"]

# The `action` of `view.navigate`.
ViewNavigateAction: TypeAlias = Literal[
    "left",
    "right",
    "up",
    "down",
    "clockwise",
    "counterclockwise",
    "home",
    "fit",
]

# The `motion` of `view.navigate`.
ViewNavigateMotion: TypeAlias = Literal["pan", "orbit", "zoom"]


# Class `SCAppearanceCommands`:
@dataclass(slots=True)
class SCAppearanceCommands(SCNamespace):
    """The `appearance.*` commands.

    Constructor:
    * `SCAppearanceCommands(transport)`
    """

    # Method `SCAppearanceCommands.assign()`:
    def assign(
        self,
        *,
        bodies: JSON | None = None,
        faces: JSON | None = None,
        components: JSON | None = None,
        appearance: JSON | None = None,
        color: JSON | None = None,
        opacity: JSON | None = None,
        pbr: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Appearance.

        `appearance.assign`.

        omitted/null uses legacy scalar shading. Neither appearance nor
        color (or color: null): clear, so the face follows its body, the
        body its component, the component its material

        Arguments:
        * `bodies` (`JSON | None`):
          [names]
        * `faces` (`JSON | None`):
          [[x,y,z] on faces] (body?: which body, default the nearest)
        * `components` (`JSON | None`):
          [names or ids, or occurrence names]
        * `appearance` (`JSON | None`):
          library name (appearance.library)
        * `color` (`JSON | None`):
          "#rrggbb" or [r, g, b] (0–255)
        * `opacity` (`JSON | None`):
          (0–1, default 1)
        * `pbr` (`JSON | None`):
          {metallic:0..1, roughness:0.045..1, dielectric_ior:1..3}
          (requires color/appearance and opacity 1)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "appearance.assign",
            {
                "bodies": bodies,
                "faces": faces,
                "components": components,
                "appearance": appearance,
                "color": color,
                "opacity": opacity,
                "pbr": pbr,
                **extra,
            },
        )

    # Method `SCAppearanceCommands.library()`:
    def library(
        self,
        **extra: JSON,
    ) -> JSON:
        """Appearance Library.

        `appearance.library`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): the built-in appearances (name, colour, opacity)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "appearance.library",
            {
                **extra,
            },
        )

    # Method `SCAppearanceCommands.list()`:
    def list(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """List Appearances.

        `appearance.list`.

        Arguments:
        * `body` (`JSON | None`):
          name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): assigned appearances; with body, its resolved look
          and its faces' (face index, look)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "appearance.list",
            {
                "body": body,
                **extra,
            },
        )


# Class `SCAssemblyCommands`:
@dataclass(slots=True)
class SCAssemblyCommands(SCNamespace):
    """The `assembly.*` commands.

    Constructor:
    * `SCAssemblyCommands(transport)`
    """

    # Method `SCAssemblyCommands.bom()`:
    def bom(
        self,
        *,
        component: JSON | None = None,
        levels: JSON | None = None,
        group_by: JSON | None = None,
        group_children: JSON | None = None,
        path: JSON | None = None,
        format: AssemblyBomFormat | None = None,
        **extra: JSON,
    ) -> JSON:
        """Bill of Materials.

        `assembly.bom`.

        Arguments:
        * `component` (`JSON | None`):
          id or name (default the design)
        * `levels` (`JSON | None`):
          flat (default: every part at any depth, counted through its
          subassemblies) | top (the component's direct children,
          subassemblies as one row each)
        * `group_by` (`JSON | None`):
          ["part_number"] (default; components without a part number get
          a row per definition) | ["definition"]
        * `group_children` (`JSON | None`):
          true (a component with a part number is one row, the parts
          placed inside it listed under it as children: [{item,
          part_number, description, revision, each, count, definition}],
          not as rows of their own)
        * `path` (`JSON | None`):
          write a .csv or .json file (children as items 1.1, 1.2…)
        * `format` (`AssemblyBomFormat | None`):
          csv|json (default from the path)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): rows: [{item, part_number, description, revision,
          count, definition, components, properties, children?}] sorted
          by part number, total_occurrences (children included)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "assembly.bom",
            {
                "component": component,
                "levels": levels,
                "group_by": group_by,
                "group_children": group_children,
                "path": path,
                "format": format,
                **extra,
            },
        )


# Class `SCBodyCommands`:
@dataclass(slots=True)
class SCBodyCommands(SCNamespace):
    """The `body.*` commands.

    Constructor:
    * `SCBodyCommands(transport)`
    """

    # Method `SCBodyCommands.rename()`:
    def rename(
        self,
        *,
        body: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Body.

        `body.rename`.

        Arguments:
        * `body` (`JSON | None`):
          (required) its name
        * `name` (`JSON | None`):
          (required) the new name (features that use the body follow)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "body.rename",
            {
                "body": body,
                "name": name,
                **extra,
            },
        )


# Class `SCBrowserCommands`:
@dataclass(slots=True)
class SCBrowserCommands(SCNamespace):
    """The `browser.*` commands.

    Constructor:
    * `SCBrowserCommands(transport)`
    """

    # Method `SCBrowserCommands.group()`:
    def group(
        self,
        *,
        folder: BrowserGroupFolder | None = None,
        component: JSON | None = None,
        name: JSON | None = None,
        items: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Group.

        `browser.group`.

        Arguments:
        * `folder` (`BrowserGroupFolder | None`):
          (required) bodies|sketches|construction
        * `component` (`JSON | None`):
          id (default 0)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `items` (`JSON | None`):
          [keys] (they leave other groups)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.group",
            {
                "folder": folder,
                "component": component,
                "name": name,
                "items": items,
                **extra,
            },
        )

    # Method `SCBrowserCommands.move()`:
    def move(
        self,
        *,
        folder: JSON | None = None,
        component: JSON | None = None,
        items: JSON | None = None,
        group: JSON | None = None,
        before: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Browser Items.

        `browser.move`.

        Arguments:
        * `folder` (`JSON | None`):
          (required) See SolidCraft.
        * `component` (`JSON | None`):
          See SolidCraft.
        * `items` (`JSON | None`):
          (required) [keys]
        * `group` (`JSON | None`):
          id (into it; omit to take them out of groups)
        * `before` (`JSON | None`):
          key (position in the group)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.move",
            {
                "folder": folder,
                "component": component,
                "items": items,
                "group": group,
                "before": before,
                **extra,
            },
        )

    # Method `SCBrowserCommands.order()`:
    def order(
        self,
        *,
        folder: JSON | None = None,
        component: JSON | None = None,
        order: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Order Browser Items.

        `browser.order`.

        Arguments:
        * `folder` (`JSON | None`):
          (required) See SolidCraft.
        * `component` (`JSON | None`):
          See SolidCraft.
        * `order` (`JSON | None`):
          (required) [keys] (the folder's items in display order)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.order",
            {
                "folder": folder,
                "component": component,
                "order": order,
                **extra,
            },
        )

    # Method `SCBrowserCommands.rename_group()`:
    def rename_group(
        self,
        *,
        group: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Group.

        `browser.rename_group`.

        Arguments:
        * `group` (`JSON | None`):
          (required) id
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.rename_group",
            {
                "group": group,
                "name": name,
                **extra,
            },
        )

    # Method `SCBrowserCommands.ungroup()`:
    def ungroup(
        self,
        *,
        group: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Ungroup.

        `browser.ungroup`.

        Arguments:
        * `group` (`JSON | None`):
          (required) id (its items go back to the folder)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.ungroup",
            {
                "group": group,
                **extra,
            },
        )

    # Method `SCBrowserCommands.visibility()`:
    def visibility(
        self,
        *,
        visible: bool | None = None,
        items: JSON | None = None,
        joints: JSON | None = None,
        folder: BrowserVisibilityFolder | None = None,
        tree_folders: JSON | None = None,
        paths: JSON | None = None,
        isolate: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Show/Hide.

        `browser.visibility`.

        not an undo step

        Arguments:
        * `visible` (`bool | None`):
          (required) bool
        * `items` (`JSON | None`):
          [sketch id or name | body name | construction name | joint
          name | O|X|Y|Z|XY|XZ|YZ]
        * `joints` (`JSON | None`):
          [joint id or name] (their glyphs; they still constrain and
          move parts)
        * `folder` (`BrowserVisibilityFolder | None`):
          bodies|sketches|construction|origin|joints (all of it; showing
          also shows its browser folders and groups)
        * `tree_folders` (`JSON | None`):
          [browser folder or group key: c0/bodies, o:4/sketches, c0/g7,
          c0/joints, c0/canvases] (the folder or group itself: its items
          keep their own state)
        * `paths` (`JSON | None`):
          [[occurrence ids]] (exact placements and descendants)
        * `isolate` (`bool | None`):
          bool (requires paths and visible:true). Saved with the design
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "browser.visibility",
            {
                "visible": visible,
                "items": items,
                "joints": joints,
                "folder": folder,
                "tree_folders": tree_folders,
                "paths": paths,
                "isolate": isolate,
                **extra,
            },
        )


# Class `SCCanvasCommands`:
@dataclass(slots=True)
class SCCanvasCommands(SCNamespace):
    """The `canvas.*` commands.

    Constructor:
    * `SCCanvasCommands(transport)`
    """

    # Method `SCCanvasCommands.calibrate()`:
    def calibrate(
        self,
        *,
        canvas: JSON | None = None,
        a: JSON | None = None,
        b: JSON | None = None,
        distance: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Calibrate Canvas.

        `canvas.calibrate`.

        Arguments:
        * `canvas` (`JSON | None`):
          (required) id or name
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) two points on the canvas plane [x,y]
        * `distance` (`JSON | None`):
          (required) their true distance (mm): scales the image about a
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "canvas.calibrate",
            {
                "canvas": canvas,
                "a": a,
                "b": b,
                "distance": distance,
                **extra,
            },
        )

    # Method `SCCanvasCommands.decal()`:
    def decal(
        self,
        *,
        face: Point3D | None = None,
        width: Expr | None = None,
        angle: Expr | None = None,
        opacity: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Decal.

        `canvas.decal`.

        path | data

        Arguments:
        * `face` (`Point3D | None`):
          (required) [x,y,z] on a planar face (the image is centred
          there)
        * `width` (`Expr | None`):
          mm
        * `angle` (`Expr | None`):
          deg
        * `opacity` (`JSON | None`):
          (default 1)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "canvas.decal",
            {
                "face": face,
                "width": width,
                "angle": angle,
                "opacity": opacity,
                **extra,
            },
        )

    # Method `SCCanvasCommands.delete()`:
    def delete(
        self,
        *,
        canvas: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Canvas.

        `canvas.delete`.

        Arguments:
        * `canvas` (`JSON | None`):
          (required) id or name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "canvas.delete",
            {
                "canvas": canvas,
                **extra,
            },
        )

    # Method `SCCanvasCommands.edit()`:
    def edit(
        self,
        *,
        canvas: JSON | None = None,
        center: JSON | None = None,
        width: JSON | None = None,
        angle: Expr | None = None,
        opacity: JSON | None = None,
        flip: JSON | None = None,
        visible: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Canvas.

        `canvas.edit`.

        Arguments:
        * `canvas` (`JSON | None`):
          (required) id or name
        * `center` (`JSON | None`):
          See SolidCraft.
        * `width` (`JSON | None`):
          See SolidCraft.
        * `angle` (`Expr | None`):
          deg
        * `opacity` (`JSON | None`):
          See SolidCraft.
        * `flip` (`JSON | None`):
          See SolidCraft.
        * `visible` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "canvas.edit",
            {
                "canvas": canvas,
                "center": center,
                "width": width,
                "angle": angle,
                "opacity": opacity,
                "flip": flip,
                "visible": visible,
                "name": name,
                **extra,
            },
        )

    # Method `SCCanvasCommands.insert()`:
    def insert(
        self,
        *,
        plane: JSON | None = None,
        center: Point2D | None = None,
        at: Point3D | None = None,
        width: Expr | None = None,
        angle: Expr | None = None,
        opacity: JSON | None = None,
        flip: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Canvas.

        `canvas.insert`.

        path | data (base64 PNG or JPEG)

        Arguments:
        * `plane` (`JSON | None`):
          XY|XZ|YZ|{face: [x,y,z]}|… (default XY)
        * `center` (`Point2D | None`):
          [x,y] on the plane
        * `at` (`Point3D | None`):
          [x,y,z]
        * `width` (`Expr | None`):
          mm (default 100)
        * `angle` (`Expr | None`):
          deg
        * `opacity` (`JSON | None`):
          0…1 (default 0.5)
        * `flip` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "canvas.insert",
            {
                "plane": plane,
                "center": center,
                "at": at,
                "width": width,
                "angle": angle,
                "opacity": opacity,
                "flip": flip,
                "name": name,
                **extra,
            },
        )


# Class `SCComponentCommands`:
@dataclass(slots=True)
class SCComponentCommands(SCNamespace):
    """The `component.*` commands.

    Constructor:
    * `SCComponentCommands(transport)`
    """

    # Method `SCComponentCommands.activate()`:
    def activate(
        self,
        *,
        component: JSON | None = None,
        occurrence: JSON | None = None,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Activate Component.

        `component.activate`.

        Arguments:
        * `component` (`JSON | None`):
          (required) id or name (0 or "root" for the design)
        * `occurrence` (`JSON | None`):
          See SolidCraft.
        * `path` (`JSON | None`):
          exact placement used to author shared geometry
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.activate",
            {
                "component": component,
                "occurrence": occurrence,
                "path": path,
                **extra,
            },
        )

    # Method `SCComponentCommands.break_link()`:
    def break_link(
        self,
        *,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Break Link.

        `component.break_link`.

        Arguments:
        * `component` (`JSON | None`):
          (required) id or name of a linked component — keeps its bodies
          as they are and forgets the design file
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.break_link",
            {
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.capture_position()`:
    def capture_position(
        self,
        **extra: JSON,
    ) -> JSON:
        """Capture Position.

        `component.capture_position`.

        keeps pending occurrence moves

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.capture_position",
            {
                **extra,
            },
        )

    # Method `SCComponentCommands.create()`:
    def create(
        self,
        *,
        name: JSON | None = None,
        parent: JSON | None = None,
        parent_path: JSON | None = None,
        activate: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Component.

        `component.create`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `parent` (`JSON | None`):
          component id or name (default: the active one)
        * `parent_path` (`JSON | None`):
          exact parent placement
        * `activate` (`bool | None`):
          bool (default true)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.create",
            {
                "name": name,
                "parent": parent,
                "parent_path": parent_path,
                "activate": activate,
                **extra,
            },
        )

    # Method `SCComponentCommands.delete()`:
    def delete(
        self,
        *,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Component.

        `component.delete`.

        its subcomponents, occurrences and features

        Arguments:
        * `component` (`JSON | None`):
          (required) deletes it
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.delete",
            {
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.from_bodies()`:
    def from_bodies(
        self,
        *,
        bodies: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Create Components from Bodies.

        `component.from_bodies`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): one new component per body, named after it

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.from_bodies",
            {
                "bodies": bodies,
                **extra,
            },
        )

    # Method `SCComponentCommands.insert_design()`:
    def insert_design(
        self,
        *,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert Design.

        `component.insert_design`.

        Arguments:
        * `path` (`JSON | None`):
          (required) a .solidcraft design
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): a new component linked to it, holding its solid
          bodies as placed in that design; name? (default: the design's
          name); parent?: component id or name (default: the active
          one); translate?: [x,y,z]; reuse?: bool (default false):
          insert another occurrence of an existing link to the same file

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.insert_design",
            {
                "path": path,
                **extra,
            },
        )

    # Method `SCComponentCommands.links()`:
    def links(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Links.

        `component.links`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): linked components: component, name, path, file
          (resolved), found

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.links",
            {
                **extra,
            },
        )

    # Method `SCComponentCommands.list()`:
    def list(
        self,
        *,
        compact: bool | None = None,
        bodies: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """List Components.

        `component.list`.

        Arguments:
        * `compact` (`bool | None`):
          bool (counts of bodies, features, sketches and construction
          planes instead of their names; occurrences leave out identity
          transforms; children as occurrence ids)
        * `bodies` (`bool | None`):
          bool (with compact: body names, not their count)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.list",
            {
                "compact": compact,
                "bodies": bodies,
                **extra,
            },
        )

    # Method `SCComponentCommands.metadata()`:
    def metadata(
        self,
        *,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Part Properties.

        `component.metadata`.

        Arguments:
        * `component` (`JSON | None`):
          (required) id or name (0 or "root": the design's own
          properties)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): component, name, part_number, description, revision,
          metadata (as saved, other tools' keys too), properties: {name:
          text}

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.metadata",
            {
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.metadata_set()`:
    def metadata_set(
        self,
        *,
        component: JSON | None = None,
        part_number: JSON | None = None,
        description: JSON | None = None,
        revision: JSON | None = None,
        values: JSON | None = None,
        properties: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Change Part Properties.

        `component.metadata.set`.

        one undo step

        Arguments:
        * `component` (`JSON | None`):
          (required) id or name (not the root: use
          document.metadata.set)
        * `part_number` (`JSON | None`):
          See SolidCraft.
        * `description` (`JSON | None`):
          See SolidCraft.
        * `revision` (`JSON | None`):
          text (empty or null removes)
        * `values` (`JSON | None`):
          {key: value} (SolidCraft's keys project, part_number,
          revision, author, organization, description, license, or a
          reverse-DNS key holding an object)
        * `properties` (`JSON | None`):
          {name: text, …} (free properties; empty or null removes). All
          or nothing
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): component, metadata, properties, changed: [keys]

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.metadata.set",
            {
                "component": component,
                "part_number": part_number,
                "description": description,
                "revision": revision,
                "values": values,
                "properties": properties,
                **extra,
            },
        )

    # Method `SCComponentCommands.move_bodies()`:
    def move_bodies(
        self,
        *,
        bodies: JSON | None = None,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Bodies to Component.

        `component.move_bodies`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `component` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.move_bodies",
            {
                "bodies": bodies,
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.move_sketches()`:
    def move_sketches(
        self,
        *,
        sketches: JSON | None = None,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Sketches to Component.

        `component.move_sketches`.

        Arguments:
        * `sketches` (`JSON | None`):
          (required) [ids or names]
        * `component` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.move_sketches",
            {
                "sketches": sketches,
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.paste_new()`:
    def paste_new(
        self,
        *,
        component: JSON | None = None,
        occurrence: JSON | None = None,
        path: JSON | None = None,
        translate: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Paste New.

        `component.paste_new`.

        materials and styles; retained external links and omitted
        boundary joints are reported

        Arguments:
        * `component` (`JSON | None`):
          (required) independently copy its nested definition graph and
          history
        * `occurrence` (`JSON | None`):
          See SolidCraft.
        * `path` (`JSON | None`):
          selected source placement
        * `translate` (`JSON | None`):
          [x,y,z]. Reassigned external bodies become base geometry
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.paste_new",
            {
                "component": component,
                "occurrence": occurrence,
                "path": path,
                "translate": translate,
                **extra,
            },
        )

    # Method `SCComponentCommands.properties()`:
    def properties(
        self,
        *,
        component: JSON | None = None,
        descendants: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Component Physical Properties.

        `component.properties`.

        all placements for root, including pending moves; material-aware
        mass and center of mass in world coordinates

        Arguments:
        * `component` (`JSON | None`):
          id or name (default active)
        * `descendants` (`bool | None`):
          bool (default true). Measures the first placement
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.properties",
            {
                "component": component,
                "descendants": descendants,
                **extra,
            },
        )

    # Method `SCComponentCommands.relink()`:
    def relink(
        self,
        *,
        component: JSON | None = None,
        path: JSON | None = None,
        previous_path: JSON | None = None,
        warnings: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Relink Source.

        `component.relink`.

        preserving identities and placements; returns path, joint_errors
        and joint_conflicts

        Arguments:
        * `component` (`JSON | None`):
          (required) id or name of a linked component
        * `path` (`JSON | None`):
          (required) a saved .solidcraft design — replaces the source
          and linked bodies for all its occurrences
        * `previous_path` (`JSON | None`):
          (required) See SolidCraft.
        * `warnings` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.relink",
            {
                "component": component,
                "path": path,
                "previous_path": previous_path,
                "warnings": warnings,
                **extra,
            },
        )

    # Method `SCComponentCommands.rename()`:
    def rename(
        self,
        *,
        component: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Component.

        `component.rename`.

        Arguments:
        * `component` (`JSON | None`):
          (required) See SolidCraft.
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.rename",
            {
                "component": component,
                "name": name,
                **extra,
            },
        )

    # Method `SCComponentCommands.revert_position()`:
    def revert_position(
        self,
        *,
        occurrences: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Revert Position.

        `component.revert_position`.

        drops selected pending occurrence moves

        Arguments:
        * `occurrences` (`JSON | None`):
          [ids] (default all)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.revert_position",
            {
                "occurrences": occurrences,
                **extra,
            },
        )

    # Method `SCComponentCommands.unlock()`:
    def unlock(
        self,
        *,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Unlock Contents.

        `component.unlock`.

        so its parts move and take joints one by one

        Arguments:
        * `component` (`JSON | None`):
          (required) removes the rigid joints that hold its contents
          together (an imported assembly's rigid group)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): joints (the ids removed)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.unlock",
            {
                "component": component,
                **extra,
            },
        )

    # Method `SCComponentCommands.update_links()`:
    def update_links(
        self,
        *,
        component: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Update Links.

        `component.update_links`.

        Arguments:
        * `component` (`JSON | None`):
          id or name (default: every linked component) — reads the
          linked designs again and replaces their bodies where they
          changed
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "component.update_links",
            {
                "component": component,
                **extra,
            },
        )


# Class `SCConfigCommands`:
@dataclass(slots=True)
class SCConfigCommands(SCNamespace):
    """The `config.*` commands.

    Constructor:
    * `SCConfigCommands(transport)`
    """

    # Method `SCConfigCommands.activate()`:
    def activate(
        self,
        *,
        row: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Activate Configuration.

        `config.activate`.

        Arguments:
        * `row` (`JSON | None`):
          (required) name — sets its parameter values and suppressions
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.activate",
            {
                "row": row,
                **extra,
            },
        )

    # Method `SCConfigCommands.column()`:
    def column(
        self,
        *,
        delete: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Configuration Column.

        `config.column`.

        param? | feature? | material? | appearance? (target name)

        Arguments:
        * `delete` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.column",
            {
                "delete": delete,
                **extra,
            },
        )

    # Method `SCConfigCommands.configure()`:
    def configure(
        self,
        *,
        params: JSON | None = None,
        features: JSON | None = None,
        materials: JSON | None = None,
        appearances: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Configure.

        `config.configure`.

        Arguments:
        * `params` (`JSON | None`):
          [parameter names]
        * `features` (`JSON | None`):
          [feature names]
        * `materials` (`JSON | None`):
          [body names]
        * `appearances` (`JSON | None`):
          [body names] (columns to add; with no rows yet, a "Default"
          row takes the current values)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.configure",
            {
                "params": params,
                "features": features,
                "materials": materials,
                "appearances": appearances,
                **extra,
            },
        )

    # Method `SCConfigCommands.preview()`:
    def preview(
        self,
        *,
        row: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Preview Configuration.

        `config.preview`.

        Arguments:
        * `row` (`JSON | None`):
          (required) name — validates a rebuild without changing the
          design or history
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.preview",
            {
                "row": row,
                **extra,
            },
        )

    # Method `SCConfigCommands.row()`:
    def row(
        self,
        *,
        name: JSON | None = None,
        from_: JSON | None = None,
        values: JSON | None = None,
        rename: JSON | None = None,
        delete: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Configuration Row.

        `config.row`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `from_` (`JSON | None`):
          (row to copy; default current values) (sent as `from`)
        * `values` (`JSON | None`):
          {column key: expression, suppression, material name,
          appearance name or Look object}
        * `rename` (`JSON | None`):
          See SolidCraft.
        * `delete` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.row",
            {
                "name": name,
                "from": from_,
                "values": values,
                "rename": rename,
                "delete": delete,
                **extra,
            },
        )

    # Method `SCConfigCommands.rule()`:
    def rule(
        self,
        *,
        rule: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Configuration Rule.

        `config.rule`.

        id? + delete?; id? + index? (ordered move)

        Arguments:
        * `rule` (`JSON | None`):
          {id,name,enabled,condition,effect}
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.rule",
            {
                "rule": rule,
                **extra,
            },
        )

    # Method `SCConfigCommands.rules()`:
    def rules(
        self,
        **extra: JSON,
    ) -> JSON:
        """Configuration Rules.

        `config.rules`.

        ordered typed rules, rows and active state

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.rules",
            {
                **extra,
            },
        )

    # Method `SCConfigCommands.table()`:
    def table(
        self,
        **extra: JSON,
    ) -> JSON:
        """Display Configuration Table.

        `config.table`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): columns (param:<name> or suppress:<feature>), rows,
          the active row and whether the design still matches it

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "config.table",
            {
                **extra,
            },
        )


# Class `SCConstructCommands`:
@dataclass(slots=True)
class SCConstructCommands(SCNamespace):
    """The `construct.*` commands.

    Constructor:
    * `SCConstructCommands(transport)`
    """

    # Method `SCConstructCommands.axis_edge()`:
    def axis_edge(
        self,
        *,
        edge: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Axis Through Edge.

        `construct.axis.edge`.

        Arguments:
        * `edge` (`JSON | None`):
          (required) ref (a straight edge or sketch line)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.axis.edge",
            {
                "edge": edge,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.axis_normal_to_face()`:
    def axis_normal_to_face(
        self,
        *,
        face: JSON | None = None,
        point: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Axis Perpendicular To Face.

        `construct.axis.normal_to_face`.

        Arguments:
        * `face` (`JSON | None`):
          (required) ref
        * `point` (`JSON | None`):
          (required) ref (the axis goes through it, square to the face)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.axis.normal_to_face",
            {
                "face": face,
                "point": point,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.axis_through_cylinder()`:
    def axis_through_cylinder(
        self,
        *,
        face: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Axis Through Cylinder/Cone/Torus.

        `construct.axis.through_cylinder`.

        Arguments:
        * `face` (`JSON | None`):
          (required) ref (a cylinder, cone or torus face, or a circular
          edge)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.axis.through_cylinder",
            {
                "face": face,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.axis_two_planes()`:
    def axis_two_planes(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Axis Through Two Planes.

        `construct.axis.two_planes`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) plane or planar face refs
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.axis.two_planes",
            {
                "a": a,
                "b": b,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.axis_two_points()`:
    def axis_two_points(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Axis Through Two Points.

        `construct.axis.two_points`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) point refs (vertices, sketch points, points)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.axis.two_points",
            {
                "a": a,
                "b": b,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_along_path()`:
    def plane_along_path(
        self,
        *,
        path: JSON | None = None,
        t: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Plane Along Path.

        `construct.plane.along_path`.

        0…1 along it (default 0.5); name? The plane is square to the
        path there

        Arguments:
        * `path` (`JSON | None`):
          (required) edge or sketch curve ref
        * `t` (`Expr | None`):
          (required) expr
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.along_path",
            {
                "path": path,
                "t": t,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_at_angle()`:
    def plane_at_angle(
        self,
        *,
        base: ConstructPlaneAtAngleBase | None = None,
        axis: JSON | None = None,
        angle: Expr | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Plane at Angle.

        `construct.plane.at_angle`.

        Arguments:
        * `base` (`ConstructPlaneAtAngleBase | None`):
          (required) XY|XZ|YZ|plane name
        * `axis` (`JSON | None`):
          (required) X|Y|Z|construction axis name (where it is
          now)|{origin, dir}
        * `angle` (`Expr | None`):
          (required) expr
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.at_angle",
            {
                "base": base,
                "axis": axis,
                "angle": angle,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_midplane()`:
    def plane_midplane(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Midplane.

        `construct.plane.midplane`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) plane or planar face refs (halfway between;
          bisecting when they meet at an angle)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.midplane",
            {
                "a": a,
                "b": b,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_offset()`:
    def plane_offset(
        self,
        *,
        base: ConstructPlaneOffsetBase | None = None,
        offset: Expr | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Offset Plane.

        `construct.plane.offset`.

        a planar face {face: [x,y,z], body?, index?, path?}

        Arguments:
        * `base` (`ConstructPlaneOffsetBase | None`):
          (required) XY|XZ|YZ|plane name
        * `offset` (`Expr | None`):
          (required) expr
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.offset",
            {
                "base": base,
                "offset": offset,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_perpendicular()`:
    def plane_perpendicular(
        self,
        *,
        plane: JSON | None = None,
        line: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Perpendicular Plane.

        `construct.plane.perpendicular`.

        sketch line or axis ref; name? The plane holds the line and is
        square to the plane

        Arguments:
        * `plane` (`JSON | None`):
          (required) plane or planar face ref
        * `line` (`JSON | None`):
          (required) straight edge
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.perpendicular",
            {
                "plane": plane,
                "line": line,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_tangent()`:
    def plane_tangent(
        self,
        *,
        face: JSON | None = None,
        at: Point3D | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Tangent Plane.

        `construct.plane.tangent`.

        Arguments:
        * `face` (`JSON | None`):
          (required) ref (cylinder, cone, sphere or torus)
        * `at` (`Point3D | None`):
          [x,y,z] where it touches (default: the face pick)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.tangent",
            {
                "face": face,
                "at": at,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_three_points()`:
    def plane_three_points(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        c: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Plane Through Three Points.

        `construct.plane.three_points`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) See SolidCraft.
        * `c` (`JSON | None`):
          (required) point refs
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.three_points",
            {
                "a": a,
                "b": b,
                "c": c,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.plane_two_edges()`:
    def plane_two_edges(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Plane Through Two Edges.

        `construct.plane.two_edges`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) straight edge or line refs in one plane
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.plane.two_edges",
            {
                "a": a,
                "b": b,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_along_path()`:
    def point_along_path(
        self,
        *,
        path: JSON | None = None,
        t: Expr | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point Along Path.

        `construct.point.along_path`.

        0…1 along it (default 0.5)

        Arguments:
        * `path` (`JSON | None`):
          (required) edge or sketch curve ref
        * `t` (`Expr | None`):
          (required) expr
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.along_path",
            {
                "path": path,
                "t": t,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_center()`:
    def point_center(
        self,
        *,
        of: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point At Center Of Circle/Sphere/Torus.

        `construct.point.center`.

        Arguments:
        * `of` (`JSON | None`):
          (required) ref (circular edge, sketch circle or arc, sphere or
          torus face)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.center",
            {
                "of": of,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_edge_plane()`:
    def point_edge_plane(
        self,
        *,
        edge: JSON | None = None,
        plane: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point At Edge And Plane.

        `construct.point.edge_plane`.

        Arguments:
        * `edge` (`JSON | None`):
          (required) edge or line ref
        * `plane` (`JSON | None`):
          (required) plane or planar face ref
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.edge_plane",
            {
                "edge": edge,
                "plane": plane,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_three_planes()`:
    def point_three_planes(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        c: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point Through Three Planes.

        `construct.point.three_planes`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) See SolidCraft.
        * `c` (`JSON | None`):
          (required) plane or planar face refs
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.three_planes",
            {
                "a": a,
                "b": b,
                "c": c,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_two_edges()`:
    def point_two_edges(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point Through Two Edges.

        `construct.point.two_edges`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) edge or line refs (where they meet, or come
          closest)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.two_edges",
            {
                "a": a,
                "b": b,
                "name": name,
                **extra,
            },
        )

    # Method `SCConstructCommands.point_vertex()`:
    def point_vertex(
        self,
        *,
        point: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point At Vertex.

        `construct.point.vertex`.

        Arguments:
        * `point` (`JSON | None`):
          (required) ref (vertex, sketch point, point)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "construct.point.vertex",
            {
                "point": point,
                "name": name,
                **extra,
            },
        )


# Class `SCContactCommands`:
@dataclass(slots=True)
class SCContactCommands(SCNamespace):
    """The `contact.*` commands.

    Constructor:
    * `SCContactCommands(transport)`
    """

    # Method `SCContactCommands.check()`:
    def check(
        self,
        **extra: JSON,
    ) -> JSON:
        """Check Contact.

        `contact.check`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): pairs in contact sets that pass through each other
          now

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.check",
            {
                **extra,
            },
        )

    # Method `SCContactCommands.create()`:
    def create(
        self,
        *,
        occurrences: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Contact Set.

        `contact.create`.

        Arguments:
        * `occurrences` (`JSON | None`):
          (required) [ids or names] (two or more)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.create",
            {
                "occurrences": occurrences,
                "name": name,
                **extra,
            },
        )

    # Method `SCContactCommands.disable_all()`:
    def disable_all(
        self,
        **extra: JSON,
    ) -> JSON:
        """Disable Contact.

        `contact.disable_all`.

        contact off

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.disable_all",
            {
                **extra,
            },
        )

    # Method `SCContactCommands.edit()`:
    def edit(
        self,
        *,
        set: ContactEditSet | None = None,
        occurrences: JSON | None = None,
        name: JSON | None = None,
        suppressed: bool | None = None,
        delete: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Contact Set.

        `contact.edit`.

        Arguments:
        * `set` (`ContactEditSet | None`):
          (required) id|name
        * `occurrences` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `suppressed` (`bool | None`):
          bool
        * `delete` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.edit",
            {
                "set": set,
                "occurrences": occurrences,
                "name": name,
                "suppressed": suppressed,
                "delete": delete,
                **extra,
            },
        )

    # Method `SCContactCommands.enable_all()`:
    def enable_all(
        self,
        **extra: JSON,
    ) -> JSON:
        """Enable All Contact.

        `contact.enable_all`.

        every occurrence takes part in contact (one set of all)

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.enable_all",
            {
                **extra,
            },
        )

    # Method `SCContactCommands.enable_sets()`:
    def enable_sets(
        self,
        *,
        enabled: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Enable Contact Sets.

        `contact.enable_sets`.

        Arguments:
        * `enabled` (`bool | None`):
          bool (default true) — driving joints and motion studies stop
          where bodies in one contact set would pass through each other
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.enable_sets",
            {
                "enabled": enabled,
                **extra,
            },
        )

    # Method `SCContactCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Contact Sets.

        `contact.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): sets, enabled, all

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "contact.list",
            {
                **extra,
            },
        )


# Class `SCDiagnosticsCommands`:
@dataclass(slots=True)
class SCDiagnosticsCommands(SCNamespace):
    """The `diagnostics.*` commands.

    Constructor:
    * `SCDiagnosticsCommands(transport)`
    """

    # Method `SCDiagnosticsCommands.crash_report()`:
    def crash_report(
        self,
        *,
        id: JSON | None = None,
        location: JSON | None = None,
        backtrace: JSON | None = None,
        system: JSON | None = None,
        notes: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Crash Report.

        `diagnostics.crash_report`.

        app version and commit, the command that crashed and the recent
        ones, and design_path / replay_path when the crash can be
        replayed (`solidcraft-cli run <replay_path> --in <design_path>`)

        Arguments:
        * `id` (`JSON | None`):
          (required) report id. The whole report: message
        * `location` (`JSON | None`):
          (required) See SolidCraft.
        * `backtrace` (`JSON | None`):
          (required) See SolidCraft.
        * `system` (`JSON | None`):
          (required) See SolidCraft.
        * `notes` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "diagnostics.crash_report",
            {
                "id": id,
                "location": location,
                "backtrace": backtrace,
                "system": system,
                "notes": notes,
                **extra,
            },
        )

    # Method `SCDiagnosticsCommands.crash_reports()`:
    def crash_reports(
        self,
        *,
        limit: float | None = None,
        **extra: JSON,
    ) -> JSON:
        """Crash Reports.

        `diagnostics.crash_reports`.

        newest first: {dir, reports: [{id, kind, time, message, command,
        count, version, path, replayable}]}. kind: command_panic | panic
        | kernel_panic_recovered | unclean_exit. Read one with
        diagnostics.crash_report; reproduce it with `solidcraft-cli
        crashes replay <id>`

        Arguments:
        * `limit` (`float | None`):
          number (default 20). Lists this computer's crash reports
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "diagnostics.crash_reports",
            {
                "limit": limit,
                **extra,
            },
        )

    # Method `SCDiagnosticsCommands.crash_reports_clear()`:
    def crash_reports_clear(
        self,
        *,
        id: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Crash Reports.

        `diagnostics.crash_reports.clear`.

        Arguments:
        * `id` (`JSON | None`):
          one report (default: all).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns {deleted}

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "diagnostics.crash_reports.clear",
            {
                "id": id,
                **extra,
            },
        )

    # Method `SCDiagnosticsCommands.crash_test()`:
    def crash_test(
        self,
        *,
        mode: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Crash Test.

        `diagnostics.crash_test`.

        kernel = one inside the geometry kernel (caught), abort = the
        app ends at once (reported at the next start). Only when the
        SOLIDCRAFT_CRASH_TEST environment variable is set

        Arguments:
        * `mode` (`JSON | None`):
          (required) panic | kernel | abort. Checks that crash reports
          work: panic = an internal error in this command (caught; the
          design is unchanged)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "diagnostics.crash_test",
            {
                "mode": mode,
                **extra,
            },
        )


# Class `SCDocCommands`:
@dataclass(slots=True)
class SCDocCommands(SCNamespace):
    """The `doc.*` commands.

    Constructor:
    * `SCDocCommands(transport)`
    """

    # Method `SCDocCommands.open()`:
    def open(
        self,
        *,
        path: JSON | None = None,
        up: DocOpenUp | None = None,
        names: DocOpenNames | None = None,
        **extra: JSON,
    ) -> JSON:
        """Open.

        `doc.open`.

        a .step/.stp/.igs/.fcstd/.3dm/.3mf/.stl/.obj/.glb/.gltf file
        (STEP, IGES, FreeCAD, Rhino, 3MF, STL, OBJ or glTF; opens as a
        new design holding the file as a component named after it, as
        file.insert_step and file.insert_mesh make); IGES, FreeCAD,
        Rhino or glTF file (see file.insert_step and file.insert_mesh);
        IGES, FreeCAD or Rhino file (see file.insert_step)

        Arguments:
        * `path` (`JSON | None`):
          (required) .solidcraft design
        * `up` (`DocOpenUp | None`):
          z|y for a STEP
        * `names` (`DocOpenNames | None`):
          auto|solid|product|instance for a STEP
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "doc.open",
            {
                "path": path,
                "up": up,
                "names": names,
                **extra,
            },
        )

    # Method `SCDocCommands.recover()`:
    def recover(
        self,
        *,
        id: JSON | None = None,
        dir: JSON | None = None,
        discard: bool | None = None,
        unsaved: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Recover Design.

        `doc.recover`.

        Arguments:
        * `id` (`JSON | None`):
          (required) (from doc.recovery_list)
        * `dir` (`JSON | None`):
          See SolidCraft.
        * `discard` (`bool | None`):
          bool (delete the entry once open) — opens it with its file
          path
        * `unsaved` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "doc.recover",
            {
                "id": id,
                "dir": dir,
                "discard": discard,
                "unsaved": unsaved,
                **extra,
            },
        )

    # Method `SCDocCommands.recovery_discard()`:
    def recovery_discard(
        self,
        *,
        id: JSON | None = None,
        all: JSON | None = None,
        dir: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Discard Recovered Design.

        `doc.recovery_discard`.

        Arguments:
        * `id` (`JSON | None`):
          (required) See SolidCraft.
        * `all` (`JSON | None`):
          (required) true
        * `dir` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "doc.recovery_discard",
            {
                "id": id,
                "all": all,
                "dir": dir,
                **extra,
            },
        )

    # Method `SCDocCommands.recovery_list()`:
    def recovery_list(
        self,
        *,
        dir: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Recoverable Designs.

        `doc.recovery_list`.

        Arguments:
        * `dir` (`JSON | None`):
          (default: the recovery folder)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): designs autosaved by apps that crashed or closed
          with unsaved changes

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "doc.recovery_list",
            {
                "dir": dir,
                **extra,
            },
        )


# Class `SCDocumentCommands`:
@dataclass(slots=True)
class SCDocumentCommands(SCNamespace):
    """The `document.*` commands.

    Constructor:
    * `SCDocumentCommands(transport)`
    """

    # Method `SCDocumentCommands.inspect()`:
    def inspect(
        self,
        *,
        measure: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inspect Design.

        `document.inspect`.

        Arguments:
        * `measure` (`bool | None`):
          bool (include body measurements)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "document.inspect",
            {
                "measure": measure,
                **extra,
            },
        )

    # Method `SCDocumentCommands.metadata()`:
    def metadata(
        self,
        **extra: JSON,
    ) -> JSON:
        """Design Properties.

        `document.metadata`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): metadata: the design's metadata object as saved
          (other tools' keys too); properties: project, part_number,
          revision, author, organization, description and license, each
          its text or null (absent, or not text)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "document.metadata",
            {
                **extra,
            },
        )

    # Method `SCDocumentCommands.metadata_remove()`:
    def metadata_remove(
        self,
        *,
        key: JSON | None = None,
        keys: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Remove Design Property.

        `document.metadata.remove`.

        Arguments:
        * `key` (`JSON | None`):
          (required) See SolidCraft.
        * `keys` (`JSON | None`):
          (required) [keys] (any key, also one another tool wrote)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): metadata, removed: [keys that were there]

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "document.metadata.remove",
            {
                "key": key,
                "keys": keys,
                **extra,
            },
        )

    # Method `SCDocumentCommands.metadata_set()`:
    def metadata_set(
        self,
        *,
        values: JSON | None = None,
        part_number: JSON | None = None,
        revision: JSON | None = None,
        author: JSON | None = None,
        organization: JSON | None = None,
        description: JSON | None = None,
        license: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Change Design Properties.

        `document.metadata.set`.

        key and value, another tool's data goes under its reverse-DNS
        key such as com.example.tool (an object; null removes)

        Arguments:
        * `values` (`JSON | None`):
          (required) {key: value, …} (all or nothing, one undo step).
          SolidCraft's keys: project
        * `part_number` (`JSON | None`):
          (required) See SolidCraft.
        * `revision` (`JSON | None`):
          (required) See SolidCraft.
        * `author` (`JSON | None`):
          (required) See SolidCraft.
        * `organization` (`JSON | None`):
          (required) See SolidCraft.
        * `description` (`JSON | None`):
          (required) See SolidCraft.
        * `license` (`JSON | None`):
          (required) (text; "" or null removes)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): metadata, changed: [keys]

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "document.metadata.set",
            {
                "values": values,
                "part_number": part_number,
                "revision": revision,
                "author": author,
                "organization": organization,
                "description": description,
                "license": license,
                **extra,
            },
        )

    # Method `SCDocumentCommands.units()`:
    def units(
        self,
        *,
        units: DocumentUnitsUnits | None = None,
        **extra: JSON,
    ) -> JSON:
        """Change Design Units.

        `document.units`.

        Arguments:
        * `units` (`DocumentUnitsUnits | None`):
          (required) mm|cm|m|in|ft (display and unit-less parameters;
          values keep their meaning)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "document.units",
            {
                "units": units,
                **extra,
            },
        )


# Class `SCEditCommands`:
@dataclass(slots=True)
class SCEditCommands(SCNamespace):
    """The `edit.*` commands.

    Constructor:
    * `SCEditCommands(transport)`
    """

    # Method `SCEditCommands.checkpoint()`:
    def checkpoint(
        self,
        **extra: JSON,
    ) -> JSON:
        """Checkpoint.

        `edit.checkpoint`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): {checkpoint: id}: remember the design, active sketch
          and undo history (restore with edit.restore_checkpoint)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "edit.checkpoint",
            {
                **extra,
            },
        )

    # Method `SCEditCommands.redo()`:
    def redo(
        self,
        **extra: JSON,
    ) -> JSON:
        """Redo.

        `edit.redo`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "edit.redo",
            {
                **extra,
            },
        )

    # Method `SCEditCommands.restore_checkpoint()`:
    def restore_checkpoint(
        self,
        *,
        checkpoint: JSON | None = None,
        forget: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Restore Checkpoint.

        `edit.restore_checkpoint`.

        undo history included

        Arguments:
        * `checkpoint` (`JSON | None`):
          (required) id
        * `forget` (`bool | None`):
          bool (true = drop it without going back). Goes back to it
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "edit.restore_checkpoint",
            {
                "checkpoint": checkpoint,
                "forget": forget,
                **extra,
            },
        )

    # Method `SCEditCommands.undo()`:
    def undo(
        self,
        **extra: JSON,
    ) -> JSON:
        """Undo.

        `edit.undo`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "edit.undo",
            {
                **extra,
            },
        )


# Class `SCEngineCommands`:
@dataclass(slots=True)
class SCEngineCommands(SCNamespace):
    """The `engine.*` commands.

    Constructor:
    * `SCEngineCommands(transport)`
    """

    # Method `SCEngineCommands.commands()`:
    def commands(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Commands.

        `engine.commands`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "engine.commands",
            {
                **extra,
            },
        )

    # Method `SCEngineCommands.describe()`:
    def describe(
        self,
        command: str,
        **extra: JSON,
    ) -> JSON:
        """Describe Command.

        `engine.describe`.

        Arguments:
        * `command` (`str`):
          (required) The command's id, such as `solid.extrude`.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns {id, label, params, input, output} (and
          param_warnings in the warn parameter-check mode): the
          command's parameter documentation and, once the command has a
          typed contract, the JSON Schemas (2020-12) of its parameters
          and of a successful result (null otherwise). Read-only.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "engine.describe",
            {
                "command": command,
                **extra,
            },
        )


# Class `SCExplodeCommands`:
@dataclass(slots=True)
class SCExplodeCommands(SCNamespace):
    """The `explode.*` commands.

    Constructor:
    * `SCExplodeCommands(transport)`
    """

    # Method `SCExplodeCommands.create()`:
    def create(
        self,
        *,
        name: JSON | None = None,
        scale: JSON | None = None,
        moves: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Exploded View.

        `explode.create`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `scale` (`JSON | None`):
          (automatic: each occurrence pushed away from the assembly's
          centre by scale × its offset, default 1)
        * `moves` (`JSON | None`):
          [{occurrence, translate: [x,y,z]}] (instead of automatic)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "explode.create",
            {
                "name": name,
                "scale": scale,
                "moves": moves,
                **extra,
            },
        )

    # Method `SCExplodeCommands.delete()`:
    def delete(
        self,
        *,
        view: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Exploded View.

        `explode.delete`.

        Arguments:
        * `view` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "explode.delete",
            {
                "view": view,
                **extra,
            },
        )

    # Method `SCExplodeCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Exploded Views.

        `explode.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "explode.list",
            {
                **extra,
            },
        )

    # Method `SCExplodeCommands.show()`:
    def show(
        self,
        *,
        view: ExplodeShowView | None = None,
        **extra: JSON,
    ) -> JSON:
        """Show Exploded View.

        `explode.show`.

        the design keeps its placements

        Arguments:
        * `view` (`ExplodeShowView | None`):
          (required) id|name (or none: back to the assembled placement)
          — shown only
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "explode.show",
            {
                "view": view,
                **extra,
            },
        )


# Class `SCExprCommands`:
@dataclass(slots=True)
class SCExprCommands(SCNamespace):
    """The `expr.*` commands.

    Constructor:
    * `SCExprCommands(transport)`
    """

    # Method `SCExprCommands.evaluate()`:
    def evaluate(
        self,
        *,
        expression: JSON | None = None,
        kind: ExprEvaluateKind | None = None,
        **extra: JSON,
    ) -> JSON:
        """Evaluate Expression.

        `expr.evaluate`.

        Arguments:
        * `expression` (`JSON | None`):
          (required) See SolidCraft.
        * `kind` (`ExprEvaluateKind | None`):
          length|angle|unitless (or unit?: mm|in|deg…)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): ok, value (mm/rad), display_value, references, error

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "expr.evaluate",
            {
                "expression": expression,
                "kind": kind,
                **extra,
            },
        )


# Class `SCFaceCommands`:
@dataclass(slots=True)
class SCFaceCommands(SCNamespace):
    """The `face.*` commands.

    Constructor:
    * `SCFaceCommands(transport)`
    """

    # Method `SCFaceCommands.delete()`:
    def delete(
        self,
        *,
        faces: JSON | None = None,
        body: JSON | None = None,
        heal: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Face.

        `face.delete`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points on the faces, or face names from
          model.faces]
        * `body` (`JSON | None`):
          See SolidCraft.
        * `heal` (`bool | None`):
          bool (default true: the neighbouring planes close the gap, as
          when a rounded edge, hole or boss is taken off; false: the gap
          stays open and the faces left are a surface body)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "face.delete",
            {
                "faces": faces,
                "body": body,
                "heal": heal,
                **extra,
            },
        )


# Class `SCFileCommands`:
@dataclass(slots=True)
class SCFileCommands(SCNamespace):
    """The `file.*` commands.

    Constructor:
    * `SCFileCommands(transport)`
    """

    # Method `SCFileCommands.export()`:
    def export(
        self,
        *,
        path: JSON | None = None,
        format: FileExportFormat | None = None,
        bodies: JSON | None = None,
        effort: JSON | None = None,
        velocity: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export.

        `file.export`.

        urdf only: mesh_prefix? (before each mesh file name, e.g.
        package://robot/meshes/)

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `format` (`FileExportFormat | None`):
          stl|stla|obj|step|3mf|3mf-tagged|urdf|json (default from
          extension; 3mf-tagged: 3MF whose triangles carry their B-rep
          face, at full precision, for meshing and analysis tools;
          docs/formats/3mf-face-tags.md; urdf: the whole assembly as a
          robot, with STL meshes written next to it; docs/urdf.md)
        * `bodies` (`JSON | None`):
          [names] (JSON and URDF export the complete design)
        * `effort` (`JSON | None`):
          (default 1000)
        * `velocity` (`JSON | None`):
          (default 10)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.export",
            {
                "path": path,
                "format": format,
                "bodies": bodies,
                "effort": effort,
                "velocity": velocity,
                **extra,
            },
        )

    # Method `SCFileCommands.export_view_dxf()`:
    def export_view_dxf(
        self,
        *,
        camera: JSON | None = None,
        hidden: FileExportViewDxfHidden | None = None,
        tolerance: JSON | None = None,
        path: JSON | None = None,
        mm: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Current View as DXF.

        `file.export_view_dxf`.

        2D LINE/LWPOLYLINE entities on VISIBLE/HIDDEN layers (sketch
        curves on SKETCH), finished sketches are hidden behind bodies,
        the active sketch is drawn on top; perspective projected onto
        the camera target plane; no viewport crop or overlays.

        Arguments:
        * `camera` (`JSON | None`):
          (required) Camera (current view)
        * `hidden` (`FileExportViewDxfHidden | None`):
          omit|dashed (default omit)
        * `tolerance` (`JSON | None`):
          0.0001..1 mm (curve chord tolerance, default 0.01)
        * `path` (`JSON | None`):
          .dxf file (else returns dxf text). Visible placed bodies and
          shown sketches' profile curves (no construction geometry,
          points, dimensions or constraints)
        * `mm` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.export_view_dxf",
            {
                "camera": camera,
                "hidden": hidden,
                "tolerance": tolerance,
                "path": path,
                "mm": mm,
                **extra,
            },
        )

    # Method `SCFileCommands.insert_mesh()`:
    def insert_mesh(
        self,
        *,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert Mesh.

        `file.insert_mesh`.

        .stl, .obj, .glb or .gltf file (its meshes join the design as
        mesh bodies in a new component named after the file

        Arguments:
        * `path` (`JSON | None`):
          (required) .3mf
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): component, component_name, occurrence; a glTF file's
          node tree becomes nested components held as one rigid group
          until component.unlock, a mesh placed again another
          occurrence, its materials the bodies' appearances, and its
          metres millimetres); name?; up?: z|y for a glTF file (default
          y: glTF has Y up, so the import's component is turned a
          quarter turn about X, Y becoming Z → stand_up: its occurrence;
          z: the file's axes are kept)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.insert_mesh",
            {
                "path": path,
                **extra,
            },
        )

    # Method `SCFileCommands.insert_step()`:
    def insert_step(
        self,
        *,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert STEP.

        `file.insert_step`.

        IGES, FreeCAD .FCStd or Rhino .3dm file (its bodies join the
        design as an Import base feature in a new component named after
        the file, placed in the active component; an assembly's products
        become nested components, a repeated part one component with an
        occurrence per placement, all held as one rigid group until
        component.unlock

        Arguments:
        * `path` (`JSON | None`):
          (required) STEP
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): component, component_name, occurrence,
          subcomponents?, rigid_joints?); name? (the feature's and the
          component's); up?: z|y (default z: the file's axes are kept;
          y: the file has Y up, so the import's component is turned a
          quarter turn about X, Y becoming Z → stand_up: its
          occurrence); names?: auto|solid|product|instance (default
          auto: keep meaningful solid names, replace placeholders with
          the nearest named product, else instance; solid: the solid's
          own name; product: the part's name; instance: the occurrence's
          name, else the product's); matrix?: [12 or 16 numbers] (where
          the new component's occurrence sits in the active component,
          after `up`: a rigid row-major 3x4 rotation-and-translation or
          4x4 matrix, flat or as rows, as occurrence.move takes it; a
          scale, shear or mirror is refused before the file is read);
          tolerance? (see occurrence.move)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.insert_step",
            {
                "path": path,
                **extra,
            },
        )

    # Method `SCFileCommands.new()`:
    def new(
        self,
        *,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Design.

        `file.new`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.new",
            {
                "name": name,
                **extra,
            },
        )

    # Method `SCFileCommands.save()`:
    def save(
        self,
        *,
        path: JSON | None = None,
        format: FileSaveFormat | None = None,
        compression: FileSaveCompression | None = None,
        cache: bool | None = None,
        preview: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Save.

        `file.save`.

        Arguments:
        * `path` (`JSON | None`):
          (default: current file)
        * `format` (`FileSaveFormat | None`):
          container|json (default: json for .json, otherwise container)
        * `compression` (`FileSaveCompression | None`):
          fast|compact (default: fast)
        * `cache` (`bool | None`):
          bool (the evaluated model, so the design opens without
          rebuilding; default: true)
        * `preview` (`bool | None`):
          bool (saved display meshes, default: false)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.save",
            {
                "path": path,
                "format": format,
                "compression": compression,
                "cache": cache,
                "preview": preview,
                **extra,
            },
        )

    # Method `SCFileCommands.save_as()`:
    def save_as(
        self,
        *,
        path: JSON | None = None,
        format: FileSaveAsFormat | None = None,
        compression: FileSaveAsCompression | None = None,
        cache: bool | None = None,
        preview: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Save As.

        `file.save_as`.

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `format` (`FileSaveAsFormat | None`):
          container|json (default: json for .json, otherwise container)
        * `compression` (`FileSaveAsCompression | None`):
          fast|compact (default: fast)
        * `cache` (`bool | None`):
          bool (the evaluated model, so the design opens without
          rebuilding; default: true)
        * `preview` (`bool | None`):
          bool (saved display meshes, default: false)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.save_as",
            {
                "path": path,
                "format": format,
                "compression": compression,
                "cache": cache,
                "preview": preview,
                **extra,
            },
        )

    # Method `SCFileCommands.save_mesh()`:
    def save_mesh(
        self,
        *,
        path: JSON | None = None,
        format: FileSaveMeshFormat | None = None,
        bodies: JSON | None = None,
        ascii: bool | None = None,
        slicer: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Save As Mesh.

        `file.save_mesh`.

        name or program path from file.slicers (open the saved file
        there)

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `format` (`FileSaveMeshFormat | None`):
          stl|3mf|3mf-tagged (default from the extension, else stl;
          3mf-tagged: docs/formats/3mf-face-tags.md)
        * `bodies` (`JSON | None`):
          [names] (default: all)
        * `ascii` (`bool | None`):
          bool (STL)
        * `slicer` (`JSON | None`):
          id
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.save_mesh",
            {
                "path": path,
                "format": format,
                "bodies": bodies,
                "ascii": ascii,
                "slicer": slicer,
                **extra,
            },
        )

    # Method `SCFileCommands.slicers()`:
    def slicers(
        self,
        **extra: JSON,
    ) -> JSON:
        """Installed Slicers.

        `file.slicers`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): the slicers found on this machine: [{id, name,
          icon?}]; pass an id or name as file.save_mesh's `slicer`

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "file.slicers",
            {
                **extra,
            },
        )


# Class `SCInspectCommands`:
@dataclass(slots=True)
class SCInspectCommands(SCNamespace):
    """The `inspect.*` commands.

    Constructor:
    * `SCInspectCommands(transport)`
    """

    # Method `SCInspectCommands.accessibility()`:
    def accessibility(
        self,
        *,
        direction: Point3D | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Accessibility Analysis.

        `inspect.accessibility`.

        Arguments:
        * `direction` (`Point3D | None`):
          [x,y,z] the tool comes from (default Z, from above)
        * `clear` (`JSON | None`):
          true turns the analysis off
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.accessibility",
            {
                "direction": direction,
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.center_of_mass()`:
    def center_of_mass(
        self,
        *,
        bodies: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center of Mass.

        `inspect.center_of_mass`.

        Arguments:
        * `bodies` (`JSON | None`):
          [names] (default all): the centre of mass (uniform density) of
          each and of all together
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.center_of_mass",
            {
                "bodies": bodies,
                **extra,
            },
        )

    # Method `SCInspectCommands.clearance()`:
    def clearance(
        self,
        *,
        bodies: JSON | None = None,
        against: JSON | None = None,
        min_volume: JSON | None = None,
        clearance: Expr | None = None,
        nearest: JSON | None = None,
        skip_within: JSON | None = None,
        tolerance: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Clearance.

        `inspect.clearance`.

        Arguments:
        * `bodies` (`JSON | None`):
          [names] (default: every solid body, in world placement, but
          those in `against`; mesh bodies are not measured)
        * `against` (`JSON | None`):
          [names] (only pairs with one body in `bodies` and the other
          here)
        * `min_volume` (`JSON | None`):
          mm³ (default 0.01: smaller overlaps count as contact)
        * `clearance` (`Expr | None`):
          mm (default 0: report pairs closer than this)
        * `nearest` (`JSON | None`):
          n (each body of `bodies` gets its n nearest others)
        * `skip_within` (`JSON | None`):
          "occurrence" (pairs of bodies of one occurrence) | "component"
          (pairs of bodies inside one placed component, its
          subcomponents included) | null
        * `tolerance` (`Expr | None`):
          mm (default 1e-6: a gap below it is contact, 0)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): overlaps: [{a, b, volume_mm3, area_mm2, bbox,
          center}]; near: [{a, b, distance_mm, from, to, overlap_mm3?: a
          contact's shared volume below min_volume, exact?: false when
          measured on the meshes}], nearest by body (the same for pairs
          that overlap: 0); nearest: {body: [{body, distance_mm}]};
          unchecked: [{a, b, reason}] (pairs whose overlap could not be
          worked out; each mesh body, STL/3MF/OBJ import, is not
          measured and is listed as {a: name, b: null, reason: "mesh
          body: not checked"}, also when named in `bodies` or `against`;
          the result's `bodies` counts the solid bodies only);
          pairs_checked; pairs_reused (of those, measured by an earlier
          call: neither body changed or moved since); pairs_pruned
          (ruled out by their boxes); ms. Distances are measured on the
          exact faces and edges, the meshes only rule pairs out

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.clearance",
            {
                "bodies": bodies,
                "against": against,
                "min_volume": min_volume,
                "clearance": clearance,
                "nearest": nearest,
                "skip_within": skip_within,
                "tolerance": tolerance,
                **extra,
            },
        )

    # Method `SCInspectCommands.compare()`:
    def compare(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        tolerance: Expr | None = None,
        spacing: Expr | None = None,
        max_regions: JSON | None = None,
        color: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Compare Bodies.

        `inspect.compare`.

        in world placement; coarser for a body that would need more than
        max_points? (default 8 million, up to 50 million) samples

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) body names (default: the two selected bodies, or
          the design's only two)
        * `tolerance` (`Expr | None`):
          mm (0.001 to 10, default 0.01): surfaces closer than this
          agree
        * `spacing` (`Expr | None`):
          mm (default 0.5): the largest piece of a face sampled as one
          point
        * `max_regions` (`JSON | None`):
          (default 50)
        * `color` (`JSON | None`):
          true | {only_in_a?, only_in_b?: "#rrggbb"} (colours the faces
          that hold a region, red where only a has material and green
          where only b has: the faces mostly beyond the tolerance, else
          the one with the largest share; an undo step)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): a, b: volume_mm3, area_mm2, center_of_mass, bbox;
          difference: b − a; deviation: a_to_b, b_to_a (max_mm, mean_mm,
          at, area_beyond_mm2); regions, largest first: side (only_in_a
          | only_in_b), volume_mm3 (integrated along lines through the
          region: resolution), area_mm2, max_deviation_mm, at, center,
          bbox, faces_a, faces_b (face indices, as model.faces lists
          them); identical; verdict; warnings (a body whose surface does
          not enclose what it measures, lines left out). Works from the
          two surfaces, without a boolean of the bodies, so
          near-identical bodies compare too

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.compare",
            {
                "a": a,
                "b": b,
                "tolerance": tolerance,
                "spacing": spacing,
                "max_regions": max_regions,
                "color": color,
                **extra,
            },
        )

    # Method `SCInspectCommands.continuity()`:
    def continuity(
        self,
        *,
        body: JSON | None = None,
        edges: JSON | None = None,
        samples: JSON | None = None,
        gap_tolerance_mm: JSON | None = None,
        angle_tolerance_deg: JSON | None = None,
        curvature_tolerance_per_mm: JSON | None = None,
        add: JSON | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Continuity Analysis.

        `inspect.continuity`.

        ends included (default 33)

        Arguments:
        * `body` (`JSON | None`):
          name (default: the visible bodies)
        * `edges` (`JSON | None`):
          [x,y,z] points or {"index": i} (default: every edge of the
          body; a pick must match one body)
        * `samples` (`JSON | None`):
          3…257 stations along each edge
        * `gap_tolerance_mm` (`JSON | None`):
          (default 0.001)
        * `angle_tolerance_deg` (`JSON | None`):
          (default 1)
        * `curvature_tolerance_per_mm` (`JSON | None`):
          (default 0.01)
        * `add` (`JSON | None`):
          true keeps the seams already shaded and adds these (measuring
          an edge again replaces it)
        * `clear` (`JSON | None`):
          true turns the analysis off.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): each edge's worst gap (G0), normal angle (G1) and
          curvature jump (G2) as {value, at: [x,y,z], edge_fraction},
          its verdict (smooth, curvature_jump, sharp or gap) and a
          summary; the seams are shaded in the viewport

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.continuity",
            {
                "body": body,
                "edges": edges,
                "samples": samples,
                "gap_tolerance_mm": gap_tolerance_mm,
                "angle_tolerance_deg": angle_tolerance_deg,
                "curvature_tolerance_per_mm": curvature_tolerance_per_mm,
                "add": add,
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.curvature_comb()`:
    def curvature_comb(
        self,
        *,
        curves: JSON | None = None,
        edges: JSON | None = None,
        faces: JSON | None = None,
        density: JSON | None = None,
        scale: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Curvature Comb Analysis.

        `inspect.curvature_comb`.

        Arguments:
        * `curves` (`JSON | None`):
          [sketch curve ids] (sketch?: id|name, default active)
        * `edges` (`JSON | None`):
          [[x,y,z] points on body edges]
        * `faces` (`JSON | None`):
          [[x,y,z] points on faces] with count?: isoparametric curves
          each way (default 4; combs along the face's iso grid)
        * `density` (`JSON | None`):
          teeth per curve (default 40)
        * `scale` (`JSON | None`):
          comb length per unit curvature (default auto)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.curvature_comb",
            {
                "curves": curves,
                "edges": edges,
                "faces": faces,
                "density": density,
                "scale": scale,
                **extra,
            },
        )

    # Method `SCInspectCommands.curvature_map()`:
    def curvature_map(
        self,
        *,
        radius: Expr | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Curvature Map Analysis.

        `inspect.curvature_map`.

        Arguments:
        * `radius` (`Expr | None`):
          mm shown red (default: a tenth of the model's size)
        * `clear` (`JSON | None`):
          true turns the analysis off
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.curvature_map",
            {
                "radius": radius,
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.draft()`:
    def draft(
        self,
        *,
        pull: Point3D | None = None,
        angle: JSON | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Draft Analysis.

        `inspect.draft`.

        Arguments:
        * `pull` (`Point3D | None`):
          [x,y,z] direction (default Z)
        * `angle` (`JSON | None`):
          degrees (default 1)
        * `clear` (`JSON | None`):
          true turns the analysis off
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.draft",
            {
                "pull": pull,
                "angle": angle,
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.environment_map()`:
    def environment_map(
        self,
        *,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Environment Map Analysis.

        `inspect.environment_map`.

        Arguments:
        * `clear` (`JSON | None`):
          true turns the analysis off
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.environment_map",
            {
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.interference()`:
    def interference(
        self,
        *,
        bodies: JSON | None = None,
        budget_s: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Interference.

        `inspect.interference`.

        Arguments:
        * `bodies` (`JSON | None`):
          [names] (default: all, in world placement)
        * `budget_s` (`JSON | None`):
          seconds (default 240, at most 86400: pairs not finished by
          then are listed in unchecked as "not checked: the time budget
          … ran out" and the call returns)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): interferences: pairs that overlap with the overlap
          volume, area, bounding box and centre (a pin a hair off the
          axis of a hole of its size also has near_coaxial: {offset_mm,
          length_mm}, its volume the crescent the walls share);
          unchecked: [{a, b, reason}], the pairs that could not be
          checked, with the reason, and each mesh body (STL, 3MF or OBJ
          import: not intersected) as {a: name, b: null, reason: "mesh
          body: not checked"}, so count: 0 is not read as no overlap
          (checked counts the solid bodies). Bodies are pruned by
          bounding box first, then by their display meshes (pairs whose
          meshes stay apart by more than their chord tolerances, neither
          inside the other, are clear without a boolean), so any number
          of bodies is fine; the pairs left are intersected exactly, in
          parallel on desktop, the slowest first; at most 20000 pairs
          whose boxes overlap are intersected per call (truncated: true
          and skipped_pairs: n say when more were left out). Also:
          pairs_candidate (boxes overlap), pairs_cleared (by the
          meshes), pairs_intersected, pairs_not_checked,
          budget_exceeded, threads (worker threads; 0: on the calling
          thread), boolean_ms and tessellate_ms (kernel time summed over
          the pairs), slowest: [{a, b, ms, boolean_ms, tessellate_ms}]
          and ms

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.interference",
            {
                "bodies": bodies,
                "budget_s": budget_s,
                **extra,
            },
        )

    # Method `SCInspectCommands.isocurve()`:
    def isocurve(
        self,
        *,
        faces: JSON | None = None,
        count: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Isocurve Analysis.

        `inspect.isocurve`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z]…] points on faces
        * `count` (`JSON | None`):
          curves each way (default 8): the faces' isoparametric curves
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.isocurve",
            {
                "faces": faces,
                "count": count,
                **extra,
            },
        )

    # Method `SCInspectCommands.measure()`:
    def measure(
        self,
        *,
        bodies: JSON | None = None,
        items: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Measure.

        `inspect.measure`.

        Arguments:
        * `bodies` (`JSON | None`):
          [names] (default all)
        * `items` (`JSON | None`):
          (required) [1-2 selections]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): length/area/volume; diameter, radius, circumference
          or arc_length/angle_deg of circles, arcs and cylinders; slot
          sizes; min (distance_mm, from, to), max, center_distance
          (centre to centre, or from an axis) and angle

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.measure",
            {
                "bodies": bodies,
                "items": items,
                **extra,
            },
        )

    # Method `SCInspectCommands.minimum_radius()`:
    def minimum_radius(
        self,
        *,
        curves: JSON | None = None,
        edges: JSON | None = None,
        faces: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Minimum Radius Analysis.

        `inspect.minimum_radius`.

        the smallest radius of curvature of each and where it is

        Arguments:
        * `curves` (`JSON | None`):
          [sketch curve ids] (sketch?)
        * `edges` (`JSON | None`):
          [[x,y,z]…]
        * `faces` (`JSON | None`):
          [[x,y,z]…] (default: every face of every body)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.minimum_radius",
            {
                "curves": curves,
                "edges": edges,
                "faces": faces,
                **extra,
            },
        )

    # Method `SCInspectCommands.section()`:
    def section(
        self,
        *,
        plane: JSON | None = None,
        offset: Expr | None = None,
        at: Expr | None = None,
        flip: bool | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Section Analysis.

        `inspect.section`.

        the cut's world coordinate on the named plane's axis (XY: Z, XZ:
        Y, YZ: X), instead of offset; and for a named plane its axis and
        at

        Arguments:
        * `plane` (`JSON | None`):
          (required) XY|XZ|YZ | construction plane name or id | {origin,
          normal}
        * `offset` (`Expr | None`):
          expr along the plane's normal (XY: +Z, XZ: +Y, YZ: +X)
        * `at` (`Expr | None`):
          expr
        * `flip` (`bool | None`):
          bool
        * `clear` (`JSON | None`):
          (required) true.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns the cut's origin and normal

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.section",
            {
                "plane": plane,
                "offset": offset,
                "at": at,
                "flip": flip,
                "clear": clear,
                **extra,
            },
        )

    # Method `SCInspectCommands.silhouette()`:
    def silhouette(
        self,
        *,
        view: InspectSilhouetteView | None = None,
        camera: JSON | None = None,
        bodies: JSON | None = None,
        rows: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Silhouette.

        `inspect.silhouette`.

        Arguments:
        * `view` (`InspectSilhouetteView | None`):
          front|back|left|right|top|bottom|iso (default front)
        * `camera` (`JSON | None`):
          {target: [x,y,z], yaw, pitch, distance, fov?} (mm, radians;
          fov 0 means parallel)
        * `bodies` (`JSON | None`):
          [world body names] (default visible bodies, named hidden
          bodies included)
        * `rows` (`JSON | None`):
          mask height in pixels (default 240, clamped to 16..1024)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): tightly framed run-length mask, box_mm, mm_per_px,
          right/up, projection, body and triangle counts

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.silhouette",
            {
                "view": view,
                "camera": camera,
                "bodies": bodies,
                "rows": rows,
                **extra,
            },
        )

    # Method `SCInspectCommands.zebra()`:
    def zebra(
        self,
        *,
        stripes: float | None = None,
        clear: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Zebra Analysis.

        `inspect.zebra`.

        Arguments:
        * `stripes` (`float | None`):
          number across the view (default 12)
        * `clear` (`JSON | None`):
          true turns the analysis off
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "inspect.zebra",
            {
                "stripes": stripes,
                "clear": clear,
                **extra,
            },
        )


# Class `SCJointCommands`:
@dataclass(slots=True)
class SCJointCommands(SCNamespace):
    """The `joint.*` commands.

    Constructor:
    * `SCJointCommands(transport)`
    """

    # Method `SCJointCommands.as_built()`:
    def as_built(
        self,
        *,
        type: JSON | None = None,
        a: JSON | None = None,
        b: JSON | None = None,
        at: JSON | None = None,
        name: JSON | None = None,
        limits: JSON | None = None,
        quiet: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """As-Built Joint.

        `joint.as_built`.

        one on a or b is kept on its face or hole there, so the joint
        follows it as the design changes

        Arguments:
        * `type` (`JSON | None`):
          (required) See SolidCraft.
        * `a` (`JSON | None`):
          (required) occurrence
        * `b` (`JSON | None`):
          (required) occurrence (stay where they are)
        * `at` (`JSON | None`):
          joint origin (default: b's origin) — the joint's frame
        * `name` (`JSON | None`):
          See SolidCraft.
        * `limits` (`JSON | None`):
          [[min, max] | null…]
        * `quiet` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.as_built",
            {
                "type": type,
                "a": a,
                "b": b,
                "at": at,
                "name": name,
                "limits": limits,
                "quiet": quiet,
                **extra,
            },
        )

    # Method `SCJointCommands.cam()`:
    def cam(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        profile: JSON | None = None,
        follower: JointCamFollower | None = None,
        radius: JSON | None = None,
        tip: JSON | None = None,
        flip: bool | None = None,
        link: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Cam.

        `joint.cam`.

        a slider (a translating follower) or a revolute (an oscillating
        one), b driven by a; in a plane square to its axis, read again
        whenever the design changes; such as {circle: [x,y,z]} on the
        roller          (needed for an oscillating follower; a
        translating one's line runs through it, by default along its
        slider's axis)

        Arguments:
        * `a` (`JSON | None`):
          (required) the cam's joint (revolute)
        * `b` (`JSON | None`):
          (required) the follower's joint
        * `profile` (`JSON | None`):
          (required) {sketch: id|name, index?: the profile (default: the
          largest)} | {edges: [[x,y,z]…] (points on edges of
          the cam's bodies forming one closed loop, world),
          occurrence?}: the cam's outline
        * `follower` (`JointCamFollower | None`):
          knife|roller|flat (default knife; flat: a face square to a
          slider's line)
        * `radius` (`JSON | None`):
          the          roller's radius (mm, an expression or {circle:
          [x,y,z], occurrence?}: the roller's round face, which is its
          tip too)
        * `tip` (`JSON | None`):
          a          joint origin where the follower touches: its
          knife's point or its roller's centre
        * `flip` (`bool | None`):
          bool (ride the cam from the other side          than the one
          the follower is on now)
        * `link` (`JSON | None`):
          index (replace that motion link)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): link, lift: {min, max, rise, unit} (b's travel
          over a turn of the cam), reverse (the side it rides from),
          follower_offset (mm: how far a translating follower's line
          passes          from the cam's axis); b keeps where it is,
          also when the link replaces another (at the current pose)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.cam",
            {
                "a": a,
                "b": b,
                "profile": profile,
                "follower": follower,
                "radius": radius,
                "tip": tip,
                "flip": flip,
                "link": link,
                **extra,
            },
        )

    # Method `SCJointCommands.create()`:
    def create(
        self,
        *,
        type: JointCreateType | None = None,
        a: JSON | None = None,
        b: JSON | None = None,
        values: JSON | None = None,
        limits: JSON | None = None,
        flip: bool | None = None,
        offset: JSON | None = None,
        angle: JSON | None = None,
        name: JSON | None = None,
        quiet: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Joint.

        `joint.create`.

        a relation:
        parallel|perpendicular|angle|point_on_plane|point_on_line|line_on_plane
        (ties only some directions or points, made where the parts are;
        several between two parts add up); so the joint follows the
        parameters it names; a joint whose expression no longer works
        out (a parameter deleted) is left out of the solve with the
        reason in its errors

        Arguments:
        * `type` (`JointCreateType | None`):
          (required)
          rigid|revolute|slider|cylindrical|pin_slot|planar|ball
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) joint origins ({occurrence, face|circle|edge|point:
          [x,y,z] in world, or face|circle: "<face name>"; z? for a
          point, end?, x? as joint.origin} | origin name)
        * `values` (`JSON | None`):
          [angles in deg or expressions, distances]
        * `limits` (`JSON | None`):
          [[min, max] | null…]
        * `flip` (`bool | None`):
          bool (default false: the origins are mated, b's z against a's
          as two faces meet; true: b's z along a's, so two origins given
          at one point with the same z stay as they are)
        * `offset` (`JSON | None`):
          mm or an expression
        * `angle` (`JSON | None`):
          deg or an expression (an angle relation's tilt from mated; for
          other joints the default is none, or a half turn where that
          turns b less, so faces that already meet stay as they are)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `quiet` (`bool | None`):
          bool (leave out dof and fixed). An expression (text) is kept
          with the joint and worked out again whenever the design
          changes
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.create",
            {
                "type": type,
                "a": a,
                "b": b,
                "values": values,
                "limits": limits,
                "flip": flip,
                "offset": offset,
                "angle": angle,
                "name": name,
                "quiet": quiet,
                **extra,
            },
        )

    # Method `SCJointCommands.delete()`:
    def delete(
        self,
        *,
        joint: JointDeleteJoint | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Joint.

        `joint.delete`.

        Arguments:
        * `joint` (`JointDeleteJoint | None`):
          (required) id|name (or origin: name, link: index)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.delete",
            {
                "joint": joint,
                **extra,
            },
        )

    # Method `SCJointCommands.drive()`:
    def drive(
        self,
        *,
        joint: JointDriveJoint | None = None,
        value: JSON | None = None,
        values: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Drive Joints.

        `joint.drive`.

        Arguments:
        * `joint` (`JointDriveJoint | None`):
          (required) id|name
        * `value` (`JSON | None`):
          (required) See SolidCraft.
        * `values` (`JSON | None`):
          [angles in deg or expressions, distances] (values not given
          keep theirs; a value driven drops the expression joint.create
          gave it; clamped to the limits; the other joints of a closed
          loop follow, and the motion stops where the loop can no longer
          close
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): stopped_by_loop); quiet?: bool (leave out dof and
          fixed) → values: [{name, value, unit: deg|mm, limits}] as
          joint.list gives them; moved: whether any occurrence moved;
          reason: why the joint can move nothing (suppressed, its
          origins lost, or its chain joined to nothing grounded →
          unconnected: the occurrence named)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.drive",
            {
                "joint": joint,
                "value": value,
                "values": values,
                **extra,
            },
        )

    # Method `SCJointCommands.edit()`:
    def edit(
        self,
        *,
        joint: JSON | None = None,
        type: JSON | None = None,
        flip: JSON | None = None,
        offset: JSON | None = None,
        angle: JSON | None = None,
        suppressed: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Joint.

        `joint.edit`.

        Arguments:
        * `joint` (`JSON | None`):
          (required) See SolidCraft.
        * `type` (`JSON | None`):
          See SolidCraft.
        * `flip` (`JSON | None`):
          See SolidCraft.
        * `offset` (`JSON | None`):
          See SolidCraft.
        * `angle` (`JSON | None`):
          (a number, or an expression the joint then follows)
        * `suppressed` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.edit",
            {
                "joint": joint,
                "type": type,
                "flip": flip,
                "offset": offset,
                "angle": angle,
                "suppressed": suppressed,
                "name": name,
                **extra,
            },
        )

    # Method `SCJointCommands.gear()`:
    def gear(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        ra: JSON | None = None,
        rb: JSON | None = None,
        internal: bool | None = None,
        reverse: bool | None = None,
        link: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Gear.

        `joint.gear`.

        b driven by a; an expression, {circle: [x,y,z], occurrence?}:
        the round face there, its radius (read again whenever the design
        changes, so the ratio follows edits)

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) joints that turn (revolute)
        * `ra` (`JSON | None`):
          (required) See SolidCraft.
        * `rb` (`JSON | None`):
          (required) the gears' pitch radii (or tooth counts): mm
        * `internal` (`bool | None`):
          bool (one is a ring gear: both turn the same way; by default b
          turns the other way)
        * `reverse` (`bool | None`):
          bool
        * `link` (`JSON | None`):
          index (replace that motion link)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): link, ratio (b's degrees per a's); b keeps where it
          is, also when the link replaces another (at the current pose)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.gear",
            {
                "a": a,
                "b": b,
                "ra": ra,
                "rb": rb,
                "internal": internal,
                "reverse": reverse,
                "link": link,
                **extra,
            },
        )

    # Method `SCJointCommands.inspect()`:
    def inspect(
        self,
        *,
        joint: JointInspectJoint | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inspect Joint.

        `joint.inspect`.

        Arguments:
        * `joint` (`JointInspectJoint | None`):
          id|name (default: every joint)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): joints: [{id, name, type, suppressed, visible, flip,
          offset (mm), angle (deg), values: as joint.list gives them,
          dofs, expressions?: {offset?, angle?, values?}, a, b:
          {occurrence, occurrence_name, component, component_name, path
          (occurrence names from the top, `/` between), snap (as saved:
          type, pick, face, end, edge, corner, x, point, z, in the
          component's coordinates), references: [{role:
          face|end|x|edge|corner, name, role_in_feature?: (top,
          side:c1…), feature?: {id, name, type} (the feature that made
          the face; error when it is gone), sketch?: {id, name, curve,
          curve_type} (a face swept from a sketch curve), faces?: [an
          edge's two faces], unverified?: a name saved before exact
          names}], resolves, frame?: {origin, z, x} in the world,
          error?: why the origin is lost}, links: [{index, role:
          driver|driven, …as joint.list}], errors, conflicts}] (reads
          only: nothing changes)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.inspect",
            {
                "joint": joint,
                **extra,
            },
        )

    # Method `SCJointCommands.limits()`:
    def limits(
        self,
        *,
        joint: JSON | None = None,
        index: JSON | None = None,
        min: JSON | None = None,
        max: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Joint Limits.

        `joint.limits`.

        Arguments:
        * `joint` (`JSON | None`):
          (required) See SolidCraft.
        * `index` (`JSON | None`):
          value index (default 0)
        * `min` (`JSON | None`):
          See SolidCraft.
        * `max` (`JSON | None`):
          (omit both to clear)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.limits",
            {
                "joint": joint,
                "index": index,
                "min": min,
                "max": max,
                **extra,
            },
        )

    # Method `SCJointCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Joints.

        `joint.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): joints (type, occurrences, values, limits;
          expressions: {offset?, angle?, values?} when they were typed
          as expressions), origins, links, degrees of freedom,
          conflicts, floating: [{occurrences, joints}] (joint chains
          joined to nothing grounded: the solver places none of them, so
          driving them moves nothing)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.list",
            {
                **extra,
            },
        )

    # Method `SCJointCommands.motion_link()`:
    def motion_link(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        ratio: JSON | None = None,
        offset: JSON | None = None,
        ia: JSON | None = None,
        ib: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Motion Link.

        `joint.motion_link`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) joints
        * `ratio` (`JSON | None`):
          (required) (b = ratio · a + offset): b's units per a's (mm per
          deg for an angle driving a distance)
        * `offset` (`JSON | None`):
          in b's units (deg for an angle, mm for a distance, or an
          expression)
        * `ia` (`JSON | None`):
          See SolidCraft.
        * `ib` (`JSON | None`):
          value indices (default 0)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.motion_link",
            {
                "a": a,
                "b": b,
                "ratio": ratio,
                "offset": offset,
                "ia": ia,
                "ib": ib,
                **extra,
            },
        )

    # Method `SCJointCommands.origin()`:
    def origin(
        self,
        *,
        name: JSON | None = None,
        occurrence: JointOriginOccurrence | None = None,
        face: JSON | None = None,
        circle: JSON | None = None,
        edge: Point3D | None = None,
        point: Point3D | None = None,
        z: Point3D | None = None,
        body: JSON | None = None,
        end: JSON | None = None,
        x: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Joint Origin.

        `joint.origin`.

        and a circle its end, when the design changes

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `occurrence` (`JointOriginOccurrence | None`):
          id|name (default: from the pick, or the named face's
          component)
        * `face` (`JSON | None`):
          (required) [x,y,z] | "<name>" (centre of a planar face)
        * `circle` (`JSON | None`):
          [x,y,z] | "<name>" (centre of a round end: a point on its wall
          or rim, the end's centre, or the round face's name as
          model.faces lists it)
        * `edge` (`Point3D | None`):
          [x,y,z] (a point on an edge of a planar face: the edge's
          middle, z out of the face, y into it; on?: [x,y,z] a point on
          the face (default: the larger planar face beside the edge);
          corner?: [x,y,z] near one end: the corner there, x and y along
          its two edges into the face; found again by name, so it
          follows the face as it changes size)
        * `point` (`Point3D | None`):
          [x,y,z]
        * `z` (`Point3D | None`):
          [x,y,z]
        * `body` (`JSON | None`):
          the named face's body
        * `end` (`JSON | None`):
          "<name>" (a circle's end: the face across its rim there;
          default the end nearer the pick)
        * `x` (`JSON | None`):
          [x,y,z] (a direction, world) | "<face name>" | {face: [x,y,z]}
          (the frame's x: a direction, a plane's normal, or the way to
          another hole's axis; keeps a round origin's turn; a point's x
          is a direction, laid square to its z, default: chosen from z
          alone). Faces are kept by name: the origin follows its face
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.origin",
            {
                "name": name,
                "occurrence": occurrence,
                "face": face,
                "circle": circle,
                "edge": edge,
                "point": point,
                "z": z,
                "body": body,
                "end": end,
                "x": x,
                **extra,
            },
        )

    # Method `SCJointCommands.rack_pinion()`:
    def rack_pinion(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        radius: JSON | None = None,
        reverse: bool | None = None,
        link: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rack and Pinion.

        `joint.rack_pinion`.

        in either order, b driven by a

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) a joint that turns (revolute: the pinion) and one
          that slides (slider: the rack)
        * `radius` (`JSON | None`):
          (required) the pinion's pitch radius (mm, an expression, or
          {circle: [x,y,z], occurrence?}): the rack travels radius × the
          turn in radians
        * `reverse` (`bool | None`):
          bool
        * `link` (`JSON | None`):
          index (replace that motion link)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): link, ratio (mm per degree, or degrees per mm); b
          keeps where it is, also when the link replaces another (at the
          current pose)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.rack_pinion",
            {
                "a": a,
                "b": b,
                "radius": radius,
                "reverse": reverse,
                "link": link,
                **extra,
            },
        )

    # Method `SCJointCommands.reach()`:
    def reach(
        self,
        *,
        occurrence: JointReachOccurrence | None = None,
        point: Point3D | None = None,
        at: Point3D | None = None,
        z: Point3D | None = None,
        axis: Point3D | None = None,
        joints: JSON | None = None,
        quiet: bool | None = None,
        continuous: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Reach Point.

        `joint.reach`.

        within their limits, through motion links, keeping closed loops
        closed as joint.drive does          (contact sets are not
        checked)

        Arguments:
        * `occurrence` (`JointReachOccurrence | None`):
          (required) id|name
        * `point` (`Point3D | None`):
          (required) [x,y,z] (where its point goes, world)
        * `at` (`Point3D | None`):
          [x,y,z] (its point, in the world where it is now; default: the
          centre of          its bodies' box)
        * `z` (`Point3D | None`):
          [x,y,z] (the way its axis then points)
        * `axis` (`Point3D | None`):
          [x,y,z] (that axis, in the world now; default: its own z)
        * `joints` (`JSON | None`):
          [ids          or names] (only these move toward the point; the
          other joints of a closed loop they are in follow)
        * `quiet` (`bool | None`):
          bool
        * `continuous` (`bool | None`):
          bool (a frame          of a drag: the answer says continuous,
          and the app's command line doesn't echo it). Moves the values
          of the joints          on its chain from where they are to the
          nearest pose
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): reached; error_mm (and error_deg with z): how close
          it got; point: where its point is; values: [{joint, name,
          values}] of the joints that moved, as joint.list gives them;
          moved; stopped_by_limit: [{joint, value, limit: min|max}]: the
          limits it rests on          short of the point;
          stopped_by_loop: {joint}: the closed loop that stopped it (its
          chain alone gets closer); reason: why nothing can move

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.reach",
            {
                "occurrence": occurrence,
                "point": point,
                "at": at,
                "z": z,
                "axis": axis,
                "joints": joints,
                "quiet": quiet,
                "continuous": continuous,
                **extra,
            },
        )

    # Method `SCJointCommands.rigid_group()`:
    def rigid_group(
        self,
        *,
        occurrences: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rigid Group.

        `joint.rigid_group`.

        Arguments:
        * `occurrences` (`JSON | None`):
          (required) [ids or names] (move together, as they are)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.rigid_group",
            {
                "occurrences": occurrences,
                **extra,
            },
        )

    # Method `SCJointCommands.screw()`:
    def screw(
        self,
        *,
        joint: JSON | None = None,
        b: JSON | None = None,
        pitch: JSON | None = None,
        reverse: bool | None = None,
        link: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Screw.

        `joint.screw`.

        b driven by a

        Arguments:
        * `joint` (`JSON | None`):
          (required) a cylindrical joint (its turn drives its travel) |
          a
        * `b` (`JSON | None`):
          (required) a joint that turns and one that slides
        * `pitch` (`JSON | None`):
          (required) travel per turn (mm or an expression)
        * `reverse` (`bool | None`):
          bool (a left-hand thread)
        * `link` (`JSON | None`):
          index (replace that motion link)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): link, ratio (mm per degree, or degrees per mm); b
          keeps where it is, also when the link replaces another (at the
          current pose)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.screw",
            {
                "joint": joint,
                "b": b,
                "pitch": pitch,
                "reverse": reverse,
                "link": link,
                **extra,
            },
        )

    # Method `SCJointCommands.solve()`:
    def solve(
        self,
        **extra: JSON,
    ) -> JSON:
        """Solve Joints.

        `joint.solve`.

        re-place the occurrences from the joints

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): conflicts, errors, dof

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.solve",
            {
                **extra,
            },
        )

    # Method `SCJointCommands.sweep()`:
    def sweep(
        self,
        *,
        joint: JointSweepJoint | None = None,
        from_: JSON | None = None,
        to: JSON | None = None,
        index: JSON | None = None,
        step: JSON | None = None,
        refine: Expr | None = None,
        occurrences: JSON | None = None,
        contact_sets: JSON | None = None,
        report_gaps: bool | None = None,
        apply: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sweep Joint.

        `joint.sweep`.

        with against?: [ids or names] (the parts that stay: each of
        `occurrences` only against these)

        Arguments:
        * `joint` (`JointSweepJoint | None`):
          (required) id|name
        * `from_` (`JSON | None`):
          (required) See SolidCraft. (sent as `from`)
        * `to` (`JSON | None`):
          (required) its value the sweep runs between (degrees for
          angles, mm for distances, or expressions)
        * `index` (`JSON | None`):
          (which value, default 0)
        * `step` (`JSON | None`):
          (between samples, in the joint's unit; default: fine enough
          that no part passes through another between two)
        * `refine` (`Expr | None`):
          mm (the first contact is bisected until no part moves more
          than this between the last clear value and the touching one;
          default 0.01)
        * `occurrences` (`JSON | None`):
          [ids or names] (checked against each other; default every
          occurrence)
        * `contact_sets` (`JSON | None`):
          true (the pairs of the design's contact sets)
        * `report_gaps` (`bool | None`):
          bool (the nearest gap at every sample, default false)
        * `apply` (`bool | None`):
          bool (leave the design where the sweep stopped; default false:
          the design is not changed)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): stopped_at (the last value clear of contact, or
          where a loop or limit stopped it; null: it reached `to`),
          stopped_by: {a, b, at: [x,y,z] (where they touch, world)} |
          "loop" | "limit" | null, samples: [{value, min_gap_mm?,
          pair?}], min_gap? (report_gaps: {part: {mm, at_value, to}},
          the nearest each part came to another), unit, gap_method
          ("mesh": distances between the tessellations),
          gap_tolerance_mm (how far those can be off: 0 when every face
          is flat), pairs (checked), touching_at_start: [[a, b]] (pairs
          already touching at `from`, such as parts joined face to face
          or a door on its frame: these stop it only once they pass into
          each other deeper than they start), applied. The parts are
          tested at the samples and through the bisection; the motion is
          on a copy (closed loops follow, contact sets do not stop it)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "joint.sweep",
            {
                "joint": joint,
                "from": from_,
                "to": to,
                "index": index,
                "step": step,
                "refine": refine,
                "occurrences": occurrences,
                "contact_sets": contact_sets,
                "report_gaps": report_gaps,
                "apply": apply,
                **extra,
            },
        )


# Class `SCLibraryCommands`:
@dataclass(slots=True)
class SCLibraryCommands(SCNamespace):
    """The `library.*` commands.

    Constructor:
    * `SCLibraryCommands(transport)`
    """

    # Method `SCLibraryCommands.apply()`:
    def apply(
        self,
        *,
        path: JSON | None = None,
        entry: JSON | None = None,
        revision: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Apply Local Library Entry.

        `library.apply`.

        material conflicts are explicit

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `entry` (`JSON | None`):
          (required) qualified ID
        * `revision` (`JSON | None`):
          (required) exact content SHA-256
        * `targets` (`JSON | None`):
          {bodies?, faces?: [{body,point}], components?}
        * `name` (`JSON | None`):
          physical material name on import. Copies values in one undo
          step
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "library.apply",
            {
                "path": path,
                "entry": entry,
                "revision": revision,
                "targets": targets,
                "name": name,
                **extra,
            },
        )

    # Method `SCLibraryCommands.export()`:
    def export(
        self,
        *,
        path: JSON | None = None,
        id: JSON | None = None,
        name: JSON | None = None,
        provenance: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Design Library.

        `library.export`.

        overwrite? false. Copies assigned looks and design-local
        physical definitions; never changes the design

        Arguments:
        * `path` (`JSON | None`):
          (required) .json
        * `id` (`JSON | None`):
          (default user.local)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `provenance` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "library.export",
            {
                "path": path,
                "id": id,
                "name": name,
                "provenance": provenance,
                **extra,
            },
        )

    # Method `SCLibraryCommands.inspect()`:
    def inspect(
        self,
        *,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inspect Local Library.

        `library.inspect`.

        returns validated catalog and exact entry revisions, without
        changing the design

        Arguments:
        * `path` (`JSON | None`):
          (required) scalar library JSON
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "library.inspect",
            {
                "path": path,
                **extra,
            },
        )


# Class `SCMaterialCommands`:
@dataclass(slots=True)
class SCMaterialCommands(SCNamespace):
    """The `material.*` commands.

    Constructor:
    * `SCMaterialCommands(transport)`
    """

    # Method `SCMaterialCommands.assign()`:
    def assign(
        self,
        *,
        bodies: JSON | None = None,
        material: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Physical Material.

        `material.assign`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `material` (`JSON | None`):
          (required) name (Steel, Aluminum, ABS Plastic, …, or one made
          with material.create; `material.list`)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.assign",
            {
                "bodies": bodies,
                "material": material,
                **extra,
            },
        )

    # Method `SCMaterialCommands.create()`:
    def create(
        self,
        *,
        name: JSON | None = None,
        density_g_cm3: JSON | None = None,
        appearance: JSON | None = None,
        color: JSON | None = None,
        opacity: JSON | None = None,
        pbr: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Physical Material.

        `material.create`.

        Arguments:
        * `name` (`JSON | None`):
          (required) (not a built-in material's)
        * `density_g_cm3` (`JSON | None`):
          (required) (0, 1000]
        * `appearance` (`JSON | None`):
          library name (appearance.library)
        * `color` (`JSON | None`):
          "#rrggbb" or [r, g, b] (0–255)
        * `opacity` (`JSON | None`):
          (0–1)
        * `pbr` (`JSON | None`):
          {metallic:0..1, roughness:0.045..1, dielectric_ior:1..3}
          (opaque only, needs color/appearance): the default look.
          Optical edits do not change density. Assign it with
          material.assign
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.create",
            {
                "name": name,
                "density_g_cm3": density_g_cm3,
                "appearance": appearance,
                "color": color,
                "opacity": opacity,
                "pbr": pbr,
                **extra,
            },
        )

    # Method `SCMaterialCommands.delete()`:
    def delete(
        self,
        *,
        material: JSON | None = None,
        replace: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Physical Material.

        `material.delete`.

        Arguments:
        * `material` (`JSON | None`):
          (required) a material defined in this design
        * `replace` (`JSON | None`):
          material for the bodies and configuration cells that use it
          (without it, a material in use is refused)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.delete",
            {
                "material": material,
                "replace": replace,
                **extra,
            },
        )

    # Method `SCMaterialCommands.edit()`:
    def edit(
        self,
        *,
        material: JSON | None = None,
        name: JSON | None = None,
        density_g_cm3: JSON | None = None,
        opacity: JSON | None = None,
        pbr: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Physical Material.

        `material.edit`.

        appearance? | color?

        Arguments:
        * `material` (`JSON | None`):
          (required) a material defined in this design
        * `name` (`JSON | None`):
          (bodies and configuration cells follow)
        * `density_g_cm3` (`JSON | None`):
          See SolidCraft.
        * `opacity` (`JSON | None`):
          See SolidCraft.
        * `pbr` (`JSON | None`):
          (as material.create; color: null clears the look). Omitted
          appearance/color retains the entire current look
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.edit",
            {
                "material": material,
                "name": name,
                "density_g_cm3": density_g_cm3,
                "opacity": opacity,
                "pbr": pbr,
                **extra,
            },
        )

    # Method `SCMaterialCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Materials.

        `material.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): the built-in materials, then the design's own (user:
          true, with their look)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.list",
            {
                **extra,
            },
        )

    # Method `SCMaterialCommands.properties_directional()`:
    def properties_directional(
        self,
        *,
        card: JSON | None = None,
        direction: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Directional Elastic Modulus.

        `material.properties.directional`.

        Young modulus in Pa and source/condition review. Read-only
        constitutive query; no structural solver, persistence or
        body-axis assignment. See docs/physical-material-cards.md

        Arguments:
        * `card` (`JSON | None`):
          (required) schema_version 1 engineering material card
        * `direction` (`JSON | None`):
          (required) three finite nonzero-vector components in the
          card's material-local axes.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns normalized direction

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.properties.directional",
            {
                "card": card,
                "direction": direction,
                **extra,
            },
        )

    # Method `SCMaterialCommands.properties_validate()`:
    def properties_validate(
        self,
        *,
        card: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Validate Physical Material Data.

        `material.properties.validate`.

        derived isotropic moduli, missing conditions and sources needing
        review. Read-only; does not assign/save properties or provide an
        analysis solver. See docs/physical-material-cards.md

        Arguments:
        * `card` (`JSON | None`):
          (required) schema_version 1 engineering material card in SI
          units.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns numerical consistency

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "material.properties.validate",
            {
                "card": card,
                **extra,
            },
        )


# Class `SCMeshCommands`:
@dataclass(slots=True)
class SCMeshCommands(SCNamespace):
    """The `mesh.*` commands.

    Constructor:
    * `SCMeshCommands(transport)`
    """

    # Method `SCMeshCommands.convert()`:
    def convert(
        self,
        *,
        body: JSON | None = None,
        tolerance: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Convert Mesh.

        `mesh.convert`.

        with a parametric timeline feature

        Arguments:
        * `body` (`JSON | None`):
          mesh body name (default: the selected mesh body)
        * `tolerance` (`JSON | None`):
          length expression (default 0.05 mm): reconstruct a closed
          constant-section mechanical mesh as editable planar and
          cylindrical faces
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "mesh.convert",
            {
                "body": body,
                "tolerance": tolerance,
                "name": name,
                **extra,
            },
        )


# Class `SCModelCommands`:
@dataclass(slots=True)
class SCModelCommands(SCNamespace):
    """The `model.*` commands.

    Constructor:
    * `SCModelCommands(transport)`
    """

    # Method `SCModelCommands.edges()`:
    def edges(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """List Edges.

        `model.edges`.

        Arguments:
        * `body` (`JSON | None`):
          (required) name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "model.edges",
            {
                "body": body,
                **extra,
            },
        )

    # Method `SCModelCommands.faces()`:
    def faces(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """List Faces.

        `model.faces`.

        Arguments:
        * `body` (`JSON | None`):
          (required) name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): per face: index, name (what face.delete,
          sheet.convert `face`, solid.shell … take in place of a point),
          exact, area, centroid (not always on the face), plane_normal,
          point (a point on the face that picks it), cylinder? ({origin,
          axis, radius} of a cylindrical face), sheet_face? (a folded
          sheet's face: `sheet:<body>:<panel>:<side>`, panel base or a
          flange's tag F<feature>.<k>, side top | bottom | rim.<edge> |
          bend.inner | bend.outer; taken wherever a face name is, and it
          holds while sizes change and flanges come and go)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "model.faces",
            {
                "body": body,
                **extra,
            },
        )

    # Method `SCModelCommands.threads()`:
    def threads(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Threads.

        `model.threads`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "model.threads",
            {
                **extra,
            },
        )


# Class `SCMotionCommands`:
@dataclass(slots=True)
class SCMotionCommands(SCNamespace):
    """The `motion.*` commands.

    Constructor:
    * `SCMotionCommands(transport)`
    """

    # Method `SCMotionCommands.delete()`:
    def delete(
        self,
        *,
        study: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Motion Study.

        `motion.delete`.

        Arguments:
        * `study` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.delete",
            {
                "study": study,
                **extra,
            },
        )

    # Method `SCMotionCommands.export()`:
    def export(
        self,
        *,
        study: JSON | None = None,
        samples: JSON | None = None,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Motion Study.

        `motion.export`.

        Arguments:
        * `study` (`JSON | None`):
          (required) See SolidCraft.
        * `samples` (`JSON | None`):
          (default steps + 1)
        * `path` (`JSON | None`):
          (.json or .csv)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): occurrence positions per step (the design is not
          changed)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.export",
            {
                "study": study,
                "samples": samples,
                "path": path,
                **extra,
            },
        )

    # Method `SCMotionCommands.export_animation()`:
    def export_animation(
        self,
        *,
        study: MotionExportAnimationStudy | None = None,
        joint: MotionExportAnimationJoint | None = None,
        path: JSON | None = None,
        samples: JSON | None = None,
        width: JSON | None = None,
        height: JSON | None = None,
        camera: JSON | None = None,
        fps: JSON | None = None,
        grid: JSON | None = None,
        axes: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Motion Animation.

        `motion.export_animation`.

        a folder for PNG frames (frame-0001.png, frame-0002.png, …); the
        joint as it is driven, with the headless          renderer

        Arguments:
        * `study` (`MotionExportAnimationStudy | None`):
          (required) id|name
        * `joint` (`MotionExportAnimationJoint | None`):
          (required) id|name with from and to (degrees for angles, mm
          for distances, or expressions) and index?
        * `path` (`JSON | None`):
          (required) a .gif file
        * `samples` (`JSON | None`):
          (frames, 2…1000; default the          study's steps + 1, or
          100)
        * `width` (`JSON | None`):
          See SolidCraft.
        * `height` (`JSON | None`):
          (16…4096 pixels, default 800 × 500)
        * `camera` (`JSON | None`):
          {target, yaw, pitch, roll?,          distance, fov?, up?}
          (ui.camera's reply; fields left out keep the default view:
          view.apply's camera, or the home view          framing the
          model)
        * `fps` (`JSON | None`):
          (1…50, default 20)
        * `grid` (`JSON | None`):
          See SolidCraft.
        * `axes` (`JSON | None`):
          (default true: the ground grid and the origin's axes) - draws
          the study as it plays
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): path, format, frames, width, height, fps (GIF),
          bytes, renderer, stopped_at, stopped_by_loop,
          stopped_by_contact (the design is not changed)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.export_animation",
            {
                "study": study,
                "joint": joint,
                "path": path,
                "samples": samples,
                "width": width,
                "height": height,
                "camera": camera,
                "fps": fps,
                "grid": grid,
                "axes": axes,
                **extra,
            },
        )

    # Method `SCMotionCommands.interference()`:
    def interference(
        self,
        *,
        study: MotionInterferenceStudy | None = None,
        occurrences: JSON | None = None,
        contact_sets: JSON | None = None,
        samples: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Motion Interference.

        `motion.interference`.

        with against?: [ids or names] (then each of `occurrences` is
        checked only against these, such as an arm against the parts it
        must miss)

        Arguments:
        * `study` (`MotionInterferenceStudy | None`):
          (required) id|name
        * `occurrences` (`JSON | None`):
          [ids or names] (two or more, checked against each other;
          default every occurrence)
        * `contact_sets` (`JSON | None`):
          true (the pairs of the design's contact sets)
        * `samples` (`JSON | None`):
          (2…1000, default the study's steps + 1)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): collisions: [{a, b, first_step, last_step, steps:
          [[from, to]…] (the step ranges where they overlap), depth_mm
          (how far into each other, the most at deepest_step),
          volume_mm3 (their overlap there; null when it was not cheap to
          work out)}], clear, pairs (checked), samples (taken),
          truncated (the work budget ran out; checked_to: the last step
          checked), stopped_at, stopped_by_loop. The study plays as
          motion.play plays it but contact sets do not stop it, on a
          copy (the design is not changed). Parts are tested at the
          samples only: one that passes wholly through another between
          two samples is missed

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.interference",
            {
                "study": study,
                "occurrences": occurrences,
                "contact_sets": contact_sets,
                "samples": samples,
                **extra,
            },
        )

    # Method `SCMotionCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Motion Studies.

        `motion.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.list",
            {
                **extra,
            },
        )

    # Method `SCMotionCommands.play()`:
    def play(
        self,
        *,
        study: MotionPlayStudy | None = None,
        step: JSON | None = None,
        quiet: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Play Motion Study.

        `motion.play`.

        Arguments:
        * `study` (`MotionPlayStudy | None`):
          (required) id|name
        * `step` (`JSON | None`):
          (required) (0…steps) — sets the joints to the study's values
          there (contact sets stop them)
        * `quiet` (`bool | None`):
          bool (positions of only the occurrences that moved)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): values: [{joint, values: [{name, value, unit}]}],
          positions, moved: whether any occurrence moved, unmoved:
          [{joint, name, reason}] (keyed joints that can move nothing,
          such as a chain joined to nothing grounded)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.play",
            {
                "study": study,
                "step": step,
                "quiet": quiet,
                **extra,
            },
        )

    # Method `SCMotionCommands.plot()`:
    def plot(
        self,
        *,
        study: MotionPlotStudy | None = None,
        joints: JSON | None = None,
        samples: JSON | None = None,
        duration: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Plot Motion Study.

        `motion.plot`.

        occurrence? and point? (a point of a part to follow, as
        motion.trace takes them); 0.001 or more (velocities and
        accelerations then per second, else per step)

        Arguments:
        * `study` (`MotionPlotStudy | None`):
          (required) id|name
        * `joints` (`JSON | None`):
          [id|name] (default: every joint that moves)
        * `samples` (`JSON | None`):
          (3…1000, default the study's steps + 1)
        * `duration` (`JSON | None`):
          seconds the whole study takes
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): step: [the study step of each sample], time?: [s],
          joints: [{joint, name, index, dof, unit, value, velocity,
          acceleration, velocity_unit, acceleration_unit}] (degrees for
          angles, mm for distances; angles unwrapped), point?:
          {occurrence, position: [[x,y,z]…], velocity, acceleration
          (vectors), speed, acceleration_norm, unit, velocity_unit,
          acceleration_unit}, samples (taken), stopped_at,
          stopped_by_loop, stopped_by_contact. The study plays as
          motion.play plays it, each sample driven from the one before,
          on a copy (the design is not changed); velocities and
          accelerations are finite differences between samples (central,
          one-sided at the ends)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.plot",
            {
                "study": study,
                "joints": joints,
                "samples": samples,
                "duration": duration,
                **extra,
            },
        )

    # Method `SCMotionCommands.study()`:
    def study(
        self,
        *,
        name: JSON | None = None,
        study: JSON | None = None,
        steps: JSON | None = None,
        keys: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Motion Study.

        `motion.study`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `study` (`JSON | None`):
          (edit an existing one)
        * `steps` (`JSON | None`):
          (timeline length, default 100)
        * `keys` (`JSON | None`):
          (required) [{joint, index?, points: [[step, value], …]}]
          (values: degrees for angles, mm for distances, or expressions)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.study",
            {
                "name": name,
                "study": study,
                "steps": steps,
                "keys": keys,
                **extra,
            },
        )

    # Method `SCMotionCommands.trace()`:
    def trace(
        self,
        *,
        occurrence: MotionTraceOccurrence | None = None,
        point: Point3D | None = None,
        study: MotionTraceStudy | None = None,
        joint: MotionTraceJoint | None = None,
        samples: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Motion Trace.

        `motion.trace`.

        an occurrence path [ids] (an instance inside sub-assemblies);
        where it is placed now; closed loops following

        Arguments:
        * `occurrence` (`MotionTraceOccurrence | None`):
          (required) id|name
        * `point` (`Point3D | None`):
          (required) [x,y,z] world point on it
        * `study` (`MotionTraceStudy | None`):
          (required) id|name
        * `joint` (`MotionTraceJoint | None`):
          (required) id|name with from and to (degrees for angles, mm
          for distances, or expressions) and index? (which value,
          default 0)
        * `samples` (`JSON | None`):
          (2…500, default the study's steps + 1, or 100) - the point's
          path as the study plays or the joint is driven
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): points: [[x,y,z]…] world positions, samples (taken),
          stopped_at (the sample where the motion stopped short; the
          trace ends there), stopped_by_loop, stopped_by_contact (the
          design is not changed)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.trace",
            {
                "occurrence": occurrence,
                "point": point,
                "study": study,
                "joint": joint,
                "samples": samples,
                **extra,
            },
        )

    # Method `SCMotionCommands.trace_keep()`:
    def trace_keep(
        self,
        *,
        occurrence: MotionTraceKeepOccurrence | None = None,
        point: Point3D | None = None,
        study: MotionTraceKeepStudy | None = None,
        joint: MotionTraceKeepJoint | None = None,
        samples: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Keep Motion Trace.

        `motion.trace.keep`.

        an occurrence path [ids] (an instance inside sub-assemblies);
        where it is placed now; closed loops following

        Arguments:
        * `occurrence` (`MotionTraceKeepOccurrence | None`):
          (required) id|name
        * `point` (`Point3D | None`):
          (required) [x,y,z] world point on it
        * `study` (`MotionTraceKeepStudy | None`):
          (required) id|name
        * `joint` (`MotionTraceKeepJoint | None`):
          (required) id|name with from and to (degrees for angles, mm
          for distances, or expressions) and index? (which value,
          default 0)
        * `samples` (`JSON | None`):
          (2…500, default the study's steps + 1, or 100) - the point's
          path as the study plays or the joint is driven
        * `name` (`JSON | None`):
          (default Motion TraceN) - keeps the trace as a 3D sketch
          spline through its points (a new sketch with 3D Sketch on, in
          the root component, where no joint moves it; a fixed curve, it
          does not follow later changes)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): sketch, name, curves, points

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "motion.trace.keep",
            {
                "occurrence": occurrence,
                "point": point,
                "study": study,
                "joint": joint,
                "samples": samples,
                "name": name,
                **extra,
            },
        )


# Class `SCOccurrenceCommands`:
@dataclass(slots=True)
class SCOccurrenceCommands(SCNamespace):
    """The `occurrence.*` commands.

    Constructor:
    * `SCOccurrenceCommands(transport)`
    """

    # Method `SCOccurrenceCommands.copy()`:
    def copy(
        self,
        *,
        component: JSON | None = None,
        path: JSON | None = None,
        parent: JSON | None = None,
        translate: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Paste (Instance).

        `occurrence.copy`.

        including pending moves

        Arguments:
        * `component` (`JSON | None`):
          (required) (or occurrence): what to place again
        * `path` (`JSON | None`):
          validates selected occurrence
        * `parent` (`JSON | None`):
          component (default: the same parent)
        * `translate` (`JSON | None`):
          [x,y,z]. Copies the selected effective transform
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "occurrence.copy",
            {
                "component": component,
                "path": path,
                "parent": parent,
                "translate": translate,
                **extra,
            },
        )

    # Method `SCOccurrenceCommands.ground()`:
    def ground(
        self,
        *,
        occurrence: JSON | None = None,
        grounded: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Ground.

        `occurrence.ground`.

        Arguments:
        * `occurrence` (`JSON | None`):
          (required) See SolidCraft.
        * `grounded` (`bool | None`):
          bool (default toggles)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "occurrence.ground",
            {
                "occurrence": occurrence,
                "grounded": grounded,
                **extra,
            },
        )

    # Method `SCOccurrenceCommands.move()`:
    def move(
        self,
        *,
        occurrence: JSON | None = None,
        path: JSON | None = None,
        space: OccurrenceMoveSpace | None = None,
        translate: Point3D | None = None,
        axis: Point3D | None = None,
        angle: JSON | None = None,
        origin: Point3D | None = None,
        matrix: JSON | None = None,
        tolerance: JSON | None = None,
        capture: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Occurrence.

        `occurrence.move`.

        Arguments:
        * `occurrence` (`JSON | None`):
          (required) See SolidCraft.
        * `path` (`JSON | None`):
          exact placement
        * `space` (`OccurrenceMoveSpace | None`):
          local|world (default local)
        * `translate` (`Point3D | None`):
          [x,y,z]
        * `axis` (`Point3D | None`):
          [x,y,z]
        * `angle` (`JSON | None`):
          radians or "30 deg"
        * `origin` (`Point3D | None`):
          [x,y,z]
        * `matrix` (`JSON | None`):
          [12 or 16 numbers] (instead of translate/axis/angle/origin: a
          rigid move as a row-major 3x4 rotation-and-translation or 4x4
          matrix, flat or as rows; one that is a rotation only up to
          rounding is orthonormalised, a scale, shear or mirror is
          refused)
        * `tolerance` (`JSON | None`):
          largest accepted |RᵀR − I| (default 1e-9, at most 1e-3)
        * `capture` (`bool | None`):
          bool (default true; false keeps it pending until Capture
          Position). Nested occurrence definitions remain shared
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "occurrence.move",
            {
                "occurrence": occurrence,
                "path": path,
                "space": space,
                "translate": translate,
                "axis": axis,
                "angle": angle,
                "origin": origin,
                "matrix": matrix,
                "tolerance": tolerance,
                "capture": capture,
                **extra,
            },
        )

    # Method `SCOccurrenceCommands.properties()`:
    def properties(
        self,
        *,
        occurrence: JSON | None = None,
        path: JSON | None = None,
        descendants: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Occurrence Physical Properties.

        `occurrence.properties`.

        including pending moves

        Arguments:
        * `occurrence` (`JSON | None`):
          (required) id or name
        * `path` (`JSON | None`):
          [occurrence ids] (required if nested under multiple instances)
        * `descendants` (`bool | None`):
          bool (default true). Physical properties of this placement in
          world coordinates
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "occurrence.properties",
            {
                "occurrence": occurrence,
                "path": path,
                "descendants": descendants,
                **extra,
            },
        )


# Class `SCParametersCommands`:
@dataclass(slots=True)
class SCParametersCommands(SCNamespace):
    """The `parameters.*` commands.

    Constructor:
    * `SCParametersCommands(transport)`
    """

    # Method `SCParametersCommands.add()`:
    def add(
        self,
        *,
        name: JSON | None = None,
        expression: JSON | None = None,
        unit: JSON | None = None,
        comment: JSON | None = None,
        favorite: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Add User Parameter.

        `parameters.add`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `expression` (`JSON | None`):
          (required) See SolidCraft.
        * `unit` (`JSON | None`):
          See SolidCraft.
        * `comment` (`JSON | None`):
          See SolidCraft.
        * `favorite` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.add",
            {
                "name": name,
                "expression": expression,
                "unit": unit,
                "comment": comment,
                "favorite": favorite,
                **extra,
            },
        )

    # Method `SCParametersCommands.change()`:
    def change(
        self,
        *,
        name: JSON | None = None,
        expression: JSON | None = None,
        unit: JSON | None = None,
        comment: JSON | None = None,
        favorite: bool | None = None,
        new_name: JSON | None = None,
        delete: JSON | None = None,
        changes: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Change Parameters.

        `parameters.change`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `expression` (`JSON | None`):
          (required) (number or text)
        * `unit` (`JSON | None`):
          mm|cm|m|in|ft|deg|rad|"" (new parameters default to their
          value's unit)
        * `comment` (`JSON | None`):
          See SolidCraft.
        * `favorite` (`bool | None`):
          bool
        * `new_name` (`JSON | None`):
          rename (references follow)
        * `delete` (`JSON | None`):
          (required) name
        * `changes` (`JSON | None`):
          (required) {name: expression, …} (existing parameters, checked
          together and rebuilt once, all or nothing)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): changed?: {name: value} (with changes), recomputed:
          features rebuilt, restored: features whose earlier result for
          the same inputs was reused (e.g. a value set back)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.change",
            {
                "name": name,
                "expression": expression,
                "unit": unit,
                "comment": comment,
                "favorite": favorite,
                "new_name": new_name,
                "delete": delete,
                "changes": changes,
                **extra,
            },
        )

    # Method `SCParametersCommands.comment()`:
    def comment(
        self,
        *,
        name: JSON | None = None,
        comment: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Comment Parameter.

        `parameters.comment`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `comment` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.comment",
            {
                "name": name,
                "comment": comment,
                **extra,
            },
        )

    # Method `SCParametersCommands.complete()`:
    def complete(
        self,
        *,
        prefix: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Complete Expression.

        `parameters.complete`.

        Arguments:
        * `prefix` (`JSON | None`):
          the text before the cursor
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): word, suggestions [{text, kind:
          parameter|function|unit|constant, detail}]

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.complete",
            {
                "prefix": prefix,
                **extra,
            },
        )

    # Method `SCParametersCommands.delete()`:
    def delete(
        self,
        *,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Parameter.

        `parameters.delete`.

        Arguments:
        * `name` (`JSON | None`):
          (required) (refused while something uses it; the error lists
          the users)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.delete",
            {
                "name": name,
                **extra,
            },
        )

    # Method `SCParametersCommands.export()`:
    def export(
        self,
        *,
        format: ParametersExportFormat | None = None,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Parameters.

        `parameters.export`.

        Arguments:
        * `format` (`ParametersExportFormat | None`):
          csv|json (default csv, or from the path)
        * `path` (`JSON | None`):
          write to a file
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): text

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.export",
            {
                "format": format,
                "path": path,
                **extra,
            },
        )

    # Method `SCParametersCommands.favorite()`:
    def favorite(
        self,
        *,
        name: JSON | None = None,
        favorite: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Favourite Parameter.

        `parameters.favorite`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `favorite` (`bool | None`):
          bool (default true)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.favorite",
            {
                "name": name,
                "favorite": favorite,
                **extra,
            },
        )

    # Method `SCParametersCommands.graph()`:
    def graph(
        self,
        **extra: JSON,
    ) -> JSON:
        """Parameter Graph.

        `parameters.graph`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): nodes, edges [user, used] (users include
          Feature:<name>), cycles, errors

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.graph",
            {
                **extra,
            },
        )

    # Method `SCParametersCommands.import_()`:
    def import_(
        self,
        *,
        text: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Import Parameters.

        `parameters.import`.

        all or nothing

        Arguments:
        * `text` (`JSON | None`):
          (required) CSV (header with name, expression, unit?, comment?)
          or JSON [{name, expression, unit?, comment?}] | path
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.import",
            {
                "text": text,
                **extra,
            },
        )

    # Method `SCParametersCommands.list()`:
    def list(
        self,
        *,
        favorites: bool | None = None,
        filter: ParametersListFilter | None = None,
        **extra: JSON,
    ) -> JSON:
        """List Parameters.

        `parameters.list`.

        Arguments:
        * `favorites` (`bool | None`):
          bool (only favourites)
        * `filter` (`ParametersListFilter | None`):
          all|user|sketch|feature|favorites
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): parameters (name, expression, unit, value in its
          unit, source, feature/input, comment, favorite, uses, used_by,
          error) and cycles

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.list",
            {
                "favorites": favorites,
                "filter": filter,
                **extra,
            },
        )

    # Method `SCParametersCommands.move()`:
    def move(
        self,
        *,
        name: JSON | None = None,
        before: JSON | None = None,
        after: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Parameter.

        `parameters.move`.

        the user parameter is listed just before or after it

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `before` (`JSON | None`):
          (required) See SolidCraft.
        * `after` (`JSON | None`):
          another user parameter
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.move",
            {
                "name": name,
                "before": before,
                "after": after,
                **extra,
            },
        )

    # Method `SCParametersCommands.rename()`:
    def rename(
        self,
        *,
        name: JSON | None = None,
        new_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Parameter.

        `parameters.rename`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `new_name` (`JSON | None`):
          (required) (expressions, feature inputs and dimensions that
          use it follow)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.rename",
            {
                "name": name,
                "new_name": new_name,
                **extra,
            },
        )

    # Method `SCParametersCommands.users()`:
    def users(
        self,
        *,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Parameter Users.

        `parameters.users`.

        Arguments:
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): users (parameters, feature inputs, dimensions) and
          the features it drives

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parameters.users",
            {
                "name": name,
                **extra,
            },
        )


# Class `SCPartsCommands`:
@dataclass(slots=True)
class SCPartsCommands(SCNamespace):
    """The `parts.*` commands.

    Constructor:
    * `SCPartsCommands(transport)`
    """

    # Method `SCPartsCommands.fastener()`:
    def fastener(
        self,
        *,
        size: JSON | None = None,
        length: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert Fastener.

        `parts.fastener`.

        the Insert Part dialog's command (same as parts.insert): family,
        at?|point?+direction?

        Arguments:
        * `size` (`JSON | None`):
          (required) See SolidCraft.
        * `length` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parts.fastener",
            {
                "size": size,
                "length": length,
                "name": name,
                **extra,
            },
        )

    # Method `SCPartsCommands.insert()`:
    def insert(
        self,
        *,
        family: JSON | None = None,
        size: JSON | None = None,
        length: JSON | None = None,
        at: JSON | None = None,
        point: Point3D | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert Part.

        `parts.insert`.

        Arguments:
        * `family` (`JSON | None`):
          (required) (socket_head_cap_screw | hex_bolt | hex_nut |
          washer | set_screw | dowel_pin | bearing)
        * `size` (`JSON | None`):
          (required) ("M6", or "608" for bearings)
        * `length` (`JSON | None`):
          (mm; screws, bolts, set screws, pins; default a standard
          length near 2.5 d)
        * `at` (`JSON | None`):
          [x,y,z] on a hole's rim or wall (the part seats on the hole's
          face with a rigid joint)
        * `point` (`Point3D | None`):
          [x,y,z] with direction?: [x,y,z] (no joint)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parts.insert",
            {
                "family": family,
                "size": size,
                "length": length,
                "at": at,
                "point": point,
                "name": name,
                **extra,
            },
        )

    # Method `SCPartsCommands.library()`:
    def library(
        self,
        *,
        family: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Standard Parts.

        `parts.library`.

        Arguments:
        * `family` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): families (name, standard, sizes, lengths) and, with
          family, each size's dimensions (mm)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parts.library",
            {
                "family": family,
                **extra,
            },
        )

    # Method `SCPartsCommands.resize()`:
    def resize(
        self,
        *,
        component: PartsResizeComponent | None = None,
        size: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Change Part Size.

        `parts.resize`.

        length? — rebuilds it (joints keep it seated)

        Arguments:
        * `component` (`PartsResizeComponent | None`):
          (required) id|name of an inserted part
        * `size` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "parts.resize",
            {
                "component": component,
                "size": size,
                **extra,
            },
        )


# Class `SCPlasticCommands`:
@dataclass(slots=True)
class SCPlasticCommands(SCNamespace):
    """The `plastic.*` commands.

    Constructor:
    * `SCPlasticCommands(transport)`
    """

    # Method `SCPlasticCommands.assign_rule()`:
    def assign_rule(
        self,
        *,
        bodies: JSON | None = None,
        rule: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Assign Plastic Rule.

        `plastic.assign_rule`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `rule` (`JSON | None`):
          (required) name (empty: no rule) — plastic features on these
          bodies take its draft and clearance as defaults
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.assign_rule",
            {
                "bodies": bodies,
                "rule": rule,
                **extra,
            },
        )

    # Method `SCPlasticCommands.boss()`:
    def boss(
        self,
        *,
        position: Point3D | None = None,
        direction: JSON | None = None,
        diameter: JSON | None = None,
        height: JSON | None = None,
        hole_diameter: JSON | None = None,
        hole_depth: JSON | None = None,
        draft: JSON | None = None,
        fillet: JSON | None = None,
        ribs: JSON | None = None,
        rib_thickness: JSON | None = None,
        rib_length: JSON | None = None,
        rib_offset: JSON | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Boss.

        `plastic.boss`.

        Arguments:
        * `position` (`Point3D | None`):
          (required) [x,y,z] on a face
        * `direction` (`JSON | None`):
          (default: out of the face)
        * `diameter` (`JSON | None`):
          (required) See SolidCraft.
        * `height` (`JSON | None`):
          (required) See SolidCraft.
        * `hole_diameter` (`JSON | None`):
          See SolidCraft.
        * `hole_depth` (`JSON | None`):
          (default: to the face)
        * `draft` (`JSON | None`):
          (angle)
        * `fillet` (`JSON | None`):
          (root radius)
        * `ribs` (`JSON | None`):
          (count)
        * `rib_thickness` (`JSON | None`):
          See SolidCraft.
        * `rib_length` (`JSON | None`):
          (out from the wall)
        * `rib_offset` (`JSON | None`):
          (below the top)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.boss",
            {
                "position": position,
                "direction": direction,
                "diameter": diameter,
                "height": height,
                "hole_diameter": hole_diameter,
                "hole_depth": hole_depth,
                "draft": draft,
                "fillet": fillet,
                "ribs": ribs,
                "rib_thickness": rib_thickness,
                "rib_length": rib_length,
                "rib_offset": rib_offset,
                "body": body,
                **extra,
            },
        )

    # Method `SCPlasticCommands.lip()`:
    def lip(
        self,
        *,
        face: Point3D | None = None,
        width: JSON | None = None,
        height: JSON | None = None,
        type: PlasticLipType | None = None,
        gap: JSON | None = None,
        side: PlasticLipSide | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Lip.

        `plastic.lip`.

        Arguments:
        * `face` (`Point3D | None`):
          (required) [x,y,z] on the rim face of a shelled body
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `height` (`JSON | None`):
          (required) See SolidCraft.
        * `type` (`PlasticLipType | None`):
          lip|groove
        * `gap` (`JSON | None`):
          (groove clearance)
        * `side` (`PlasticLipSide | None`):
          inside|outside (which rim edge)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.lip",
            {
                "face": face,
                "width": width,
                "height": height,
                "type": type,
                "gap": gap,
                "side": side,
                "body": body,
                **extra,
            },
        )

    # Method `SCPlasticCommands.manage_rules()`:
    def manage_rules(
        self,
        *,
        name: JSON | None = None,
        from_: JSON | None = None,
        material: JSON | None = None,
        thickness: JSON | None = None,
        nominal_radius: JSON | None = None,
        clearance: JSON | None = None,
        knife_edge: JSON | None = None,
        reveal_height: JSON | None = None,
        thickness_variation: JSON | None = None,
        draft: JSON | None = None,
        max_thickness: JSON | None = None,
        min_thickness: JSON | None = None,
        min_draft: JSON | None = None,
        active: bool | None = None,
        delete: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Manage Plastic Rules.

        `plastic.manage_rules`.

        Arguments:
        * `name` (`JSON | None`):
          (required) (library or new rule; a new one starts from `from`,
          default ABS (1.5mm))
        * `from_` (`JSON | None`):
          See SolidCraft. (sent as `from`)
        * `material` (`JSON | None`):
          See SolidCraft.
        * `thickness` (`JSON | None`):
          See SolidCraft.
        * `nominal_radius` (`JSON | None`):
          See SolidCraft.
        * `clearance` (`JSON | None`):
          See SolidCraft.
        * `knife_edge` (`JSON | None`):
          See SolidCraft.
        * `reveal_height` (`JSON | None`):
          See SolidCraft.
        * `thickness_variation` (`JSON | None`):
          See SolidCraft.
        * `draft` (`JSON | None`):
          See SolidCraft.
        * `max_thickness` (`JSON | None`):
          See SolidCraft.
        * `min_thickness` (`JSON | None`):
          See SolidCraft.
        * `min_draft` (`JSON | None`):
          (expressions; `Thickness` is the rule's)
        * `active` (`bool | None`):
          bool (rule for bodies without one)
        * `delete` (`bool | None`):
          bool (a design rule; a library rule goes back to the library
          values)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.manage_rules",
            {
                "name": name,
                "from": from_,
                "material": material,
                "thickness": thickness,
                "nominal_radius": nominal_radius,
                "clearance": clearance,
                "knife_edge": knife_edge,
                "reveal_height": reveal_height,
                "thickness_variation": thickness_variation,
                "draft": draft,
                "max_thickness": max_thickness,
                "min_thickness": min_thickness,
                "min_draft": min_draft,
                "active": active,
                "delete": delete,
                **extra,
            },
        )

    # Method `SCPlasticCommands.rest()`:
    def rest(
        self,
        *,
        position: Point3D | None = None,
        direction: JSON | None = None,
        width: JSON | None = None,
        length: JSON | None = None,
        along: Point3D | None = None,
        height: JSON | None = None,
        draft: JSON | None = None,
        thickness: JSON | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rest.

        `plastic.rest`.

        Arguments:
        * `position` (`Point3D | None`):
          (required) [x,y,z] on a face (the rest's centre)
        * `direction` (`JSON | None`):
          (default: out of the face)
        * `width` (`JSON | None`):
          (required) (round: the diameter)
        * `length` (`JSON | None`):
          (a rectangle, along `along`)
        * `along` (`Point3D | None`):
          [x,y,z]
        * `height` (`JSON | None`):
          (required) See SolidCraft.
        * `draft` (`JSON | None`):
          (angle; default: the body's plastic rule)
        * `thickness` (`JSON | None`):
          (wall of a hollow rest)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.rest",
            {
                "position": position,
                "direction": direction,
                "width": width,
                "length": length,
                "along": along,
                "height": height,
                "draft": draft,
                "thickness": thickness,
                "body": body,
                **extra,
            },
        )

    # Method `SCPlasticCommands.rules()`:
    def rules(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Plastic Rules.

        `plastic.rules`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): rules with their expressions and values, the active
          rule and the rules assigned to bodies

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.rules",
            {
                **extra,
            },
        )

    # Method `SCPlasticCommands.snap_fit()`:
    def snap_fit(
        self,
        *,
        position: Point3D | None = None,
        direction: JSON | None = None,
        hook: Point3D | None = None,
        length: JSON | None = None,
        thickness: JSON | None = None,
        width: JSON | None = None,
        catch_depth: JSON | None = None,
        catch_length: JSON | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Snap Fit.

        `plastic.snap_fit`.

        Arguments:
        * `position` (`Point3D | None`):
          (required) [x,y,z] on a face
        * `direction` (`JSON | None`):
          (default: out of the face)
        * `hook` (`Point3D | None`):
          (required) [x,y,z] (the catch's direction)
        * `length` (`JSON | None`):
          (required) See SolidCraft.
        * `thickness` (`JSON | None`):
          (required) See SolidCraft.
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `catch_depth` (`JSON | None`):
          (required) See SolidCraft.
        * `catch_length` (`JSON | None`):
          (required) See SolidCraft.
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "plastic.snap_fit",
            {
                "position": position,
                "direction": direction,
                "hook": hook,
                "length": length,
                "thickness": thickness,
                "width": width,
                "catch_depth": catch_depth,
                "catch_length": catch_length,
                "body": body,
                **extra,
            },
        )


# Class `SCRenderCommands`:
@dataclass(slots=True)
class SCRenderCommands(SCNamespace):
    """The `render.*` commands.

    Constructor:
    * `SCRenderCommands(transport)`
    """

    # Method `SCRenderCommands.backends()`:
    def backends(
        self,
        **extra: JSON,
    ) -> JSON:
        """Render Backends.

        `render.backends`.

        No parameters.; does not start rendering or probe a GPU. See
        docs/render-backends.md

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns {schema_version: 1, default_backend:
          builtin, backends: [{id, label, availability, executors: [{id,
          availability, profiles, limits, scratch}]}]}. Metadata only

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.backends",
            {
                **extra,
            },
        )

    # Method `SCRenderCommands.cancel()`:
    def cancel(
        self,
        *,
        job: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Cancel Render.

        `render.cancel`.

        completed jobs remain completed. Late cancelled frames cannot be
        published.

        Arguments:
        * `job` (`JSON | None`):
          (required) {session, serial, generation}. Requests cooperative
          cancellation
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.cancel",
            {
                "job": job,
                **extra,
            },
        )

    # Method `SCRenderCommands.export()`:
    def export(
        self,
        *,
        job: JSON | None = None,
        path: JSON | None = None,
        overwrite: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Render Image.

        `render.export`.

        an existing destination is preserved on failure. See
        docs/render-jobs.md

        Arguments:
        * `job` (`JSON | None`):
          (required) {session, serial, generation}
        * `path` (`JSON | None`):
          (required) PNG destination
        * `overwrite` (`JSON | None`):
          false. Exports a retained completed image atomically
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.export",
            {
                "job": job,
                "path": path,
                "overwrite": overwrite,
                **extra,
            },
        )

    # Method `SCRenderCommands.preflight()`:
    def preflight(
        self,
        *,
        setup: JSON | None = None,
        transparent_background: JSON | None = None,
        replace: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Check Render Request.

        `render.preflight`.

        Arguments:
        * `setup` (`JSON | None`):
          saved name OR settings?: full RenderSetup
        * `transparent_background` (`JSON | None`):
          false
        * `replace` (`JSON | None`):
          false. Validates the installed image host and bounded captured
          product scene without starting work. Stale geometry is
          rejected. See docs/render-jobs.md
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.preflight",
            {
                "setup": setup,
                "transparent_background": transparent_background,
                "replace": replace,
                **extra,
            },
        )

    # Method `SCRenderCommands.scene()`:
    def scene(
        self,
        **extra: JSON,
    ) -> JSON:
        """Inspect Render Scene.

        `render.scene`.

        No parameters. Authoritative product-scene metadata, without
        modelling overlays or mesh payloads. Explicitly settles stale
        geometry; does not render an image. See docs/render-workspace.md

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.scene",
            {
                **extra,
            },
        )

    # Method `SCRenderCommands.settings_apply()`:
    def settings_apply(
        self,
        *,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Apply Render Camera.

        `render.settings.apply`.

        without modifying the document or starting a render.

        Arguments:
        * `name` (`JSON | None`):
          (required) saved setup. Applies its existing Camera snapshot
          including roll/up as view state
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.settings.apply",
            {
                "name": name,
                **extra,
            },
        )

    # Method `SCRenderCommands.settings_get()`:
    def settings_get(
        self,
        *,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Render Settings.

        `render.settings.get`.

        with name returns {name, setup}. Does not evaluate the model or
        apply a camera. See docs/render-settings.md

        Arguments:
        * `name` (`JSON | None`):
          saved setup. Without name returns {setups, defaults}
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.settings.get",
            {
                "name": name,
                **extra,
            },
        )

    # Method `SCRenderCommands.settings_set()`:
    def settings_set(
        self,
        *,
        name: JSON | None = None,
        set: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Save Render Settings.

        `render.settings.set`.

        validates atomically, one undo step; identical edits are no-ops.
        See docs/render-settings.md

        Arguments:
        * `name` (`JSON | None`):
          (required) setup name
        * `set` (`JSON | None`):
          (required) object of fields to replace (backend, mode, camera,
          width, height, format, exposure_ev, environment_rotation,
          environment_intensity, background). Creates from defaults
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.settings.set",
            {
                "name": name,
                "set": set,
                **extra,
            },
        )

    # Method `SCRenderCommands.start()`:
    def start(
        self,
        **extra: JSON,
    ) -> JSON:
        """Render Image.

        `render.start`.

        Same request as render.preflight. Captures an immutable product
        scene and queues a bounded image job.; captured scene_generation
        and progress. Does not change the design. See
        docs/render-jobs.md

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns its session-scoped job identity

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.start",
            {
                **extra,
            },
        )

    # Method `SCRenderCommands.status()`:
    def status(
        self,
        *,
        job: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Render Progress.

        `render.status`.

        error and completed frame metadata; no image bytes and no
        rendering in this call.

        Arguments:
        * `job` (`JSON | None`):
          (required) {session, serial, generation}. Non-blocking
          progress
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "render.status",
            {
                "job": job,
                **extra,
            },
        )


# Class `SCSelectCommands`:
@dataclass(slots=True)
class SCSelectCommands(SCNamespace):
    """The `select.*` commands.

    Constructor:
    * `SCSelectCommands(transport)`
    """

    # Method `SCSelectCommands.clear()`:
    def clear(
        self,
        **extra: JSON,
    ) -> JSON:
        """Clear Selection.

        `select.clear`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "select.clear",
            {
                **extra,
            },
        )

    # Method `SCSelectCommands.set()`:
    def set(
        self,
        *,
        items: JSON | None = None,
        add: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Select.

        `select.set`.

        Arguments:
        * `items` (`JSON | None`):
          (required) [{type:
          body|edge|face|feature|sketch_curve|sketch_point|profile, …}]
        * `add` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "select.set",
            {
                "items": items,
                "add": add,
                **extra,
            },
        )


# Class `SCSelectionCommands`:
@dataclass(slots=True)
class SCSelectionCommands(SCNamespace):
    """The `selection.*` commands.

    Constructor:
    * `SCSelectionCommands(transport)`
    """

    # Method `SCSelectionCommands.delete()`:
    def delete(
        self,
        *,
        items: JSON | None = None,
        components: JSON | None = None,
        occurrences: JSON | None = None,
        canvases: JSON | None = None,
        joints: JSON | None = None,
        dry_run: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete.

        `selection.delete`.

        Arguments:
        * `items` (`JSON | None`):
          [selection items]
        * `components` (`JSON | None`):
          See SolidCraft.
        * `occurrences` (`JSON | None`):
          See SolidCraft.
        * `canvases` (`JSON | None`):
          See SolidCraft.
        * `joints` (`JSON | None`):
          [ids or names]
        * `dry_run` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): deleted, deleted_joints, would_fail, skipped (one
          undo step)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "selection.delete",
            {
                "items": items,
                "components": components,
                "occurrences": occurrences,
                "canvases": canvases,
                "joints": joints,
                "dry_run": dry_run,
                **extra,
            },
        )


# Class `SCSheetCommands`:
@dataclass(slots=True)
class SCSheetCommands(SCNamespace):
    """The `sheet.*` commands.

    Constructor:
    * `SCSheetCommands(transport)`
    """

    # Method `SCSheetCommands.convert()`:
    def convert(
        self,
        *,
        body: JSON | None = None,
        face: Point3D | None = None,
        rule: JSON | None = None,
        bends: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Convert to Sheet Metal.

        `sheet.convert`.

        that face's name from model.faces

        Arguments:
        * `body` (`JSON | None`):
          (required) See SolidCraft.
        * `face` (`Point3D | None`):
          (required) [x,y,z] on its large flat face (a plate of even
          thickness; recesses in one face up to half the thickness deep,
          such as an engraved label, become pockets of the sheet)
        * `rule` (`JSON | None`):
          See SolidCraft.
        * `bends` (`JSON | None`):
          [[x,y,z] on sharp edges] (a solid or a shelled body: `face` is
          the fixed face and the flat faces reached from it across these
          edges become the sheet; a shell keeps its thickness, a solid
          takes the rule's inward; edges between two of those faces that
          are no bends are cut open with the rule's gap; a point in the
          middle of a chamfer between two faces, or on a bend modelled
          with its radius (a cylinder between two flat faces tangent to
          it, either skin), makes it one bend of the rule's radius at
          their virtual sharp; the faces' holes become cut-outs and
          their engravings, up to half the thickness deep, pockets)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.convert",
            {
                "body": body,
                "face": face,
                "rule": rule,
                "bends": bends,
                **extra,
            },
        )

    # Method `SCSheetCommands.export_bend_table()`:
    def export_bend_table(
        self,
        *,
        body: JSON | None = None,
        format: SheetExportBendTableFormat | None = None,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Bend Table.

        `sheet.export_bend_table`.

        Arguments:
        * `body` (`JSON | None`):
          See SolidCraft.
        * `format` (`SheetExportBendTableFormat | None`):
          csv|json (default csv)
        * `path` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): bend table in mm and degrees, including rule and
          flat centre-line coordinates; a bend that cut-outs split has a
          row for each piece

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.export_bend_table",
            {
                "body": body,
                "format": format,
                "path": path,
                **extra,
            },
        )

    # Method `SCSheetCommands.export_dxf()`:
    def export_dxf(
        self,
        *,
        body: JSON | None = None,
        path: JSON | None = None,
        curves: SheetExportDxfCurves | None = None,
        text: SheetExportDxfText | None = None,
        bend_notes: bool | None = None,
        note_height: Expr | None = None,
        per_body: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Flat Pattern as DXF.

        `sheet.export_dxf`.

        Arguments:
        * `body` (`JSON | None`):
          See SolidCraft.
        * `path` (`JSON | None`):
          See SolidCraft.
        * `curves` (`SheetExportDxfCurves | None`):
          exact|arcs (default exact: an ellipse as ELLIPSE, splines,
          text outlines and other Béziers as SPLINE; arcs: tangent arcs
          and lines within 0.001 mm, for machines that read only those)
        * `text` (`SheetExportDxfText | None`):
          cut|etch (default cut: letters that text cut through the sheet
          are cut contours on layer TEXT; etch: single contours on layer
          ETCH and the sheet keeps its material there; text machined to
          a depth is always on ETCH)
        * `bend_notes` (`bool | None`):
          bool (default false: a note beside each bend line on layer
          BEND_NOTES, `B1 UP 90%%d R1`)
        * `note_height` (`Expr | None`):
          mm (default 3)
        * `per_body` (`bool | None`):
          bool (a file for every sheet body, `<path>-<body>.dxf`, or
          their DXF texts without a path
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): files: [{body, path | dxf, bends}]; not with `body`)
          → DXF (AutoCAD 2000, mm): layers OUTLINE (the outer contour),
          CUT (what is cut out inside it), TEXT or ETCH (letters),
          BEND_UP and BEND_DOWN (dashed centre lines), BEND_NOTES,
          POCKET_<BOTTOM|TOP|INTERNAL>_Z<from>_TO_<to>_MM (one per side
          and depth) and PERFORATION; inner contours come before the
          outline

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.export_dxf",
            {
                "body": body,
                "path": path,
                "curves": curves,
                "text": text,
                "bend_notes": bend_notes,
                "note_height": note_height,
                "per_body": per_body,
                **extra,
            },
        )

    # Method `SCSheetCommands.flange()`:
    def flange(
        self,
        *,
        base: JSON | None = None,
        contour: JSON | None = None,
        edge: JSON | None = None,
        angle: JSON | None = None,
        radius: JSON | None = None,
        position: SheetFlangePosition | None = None,
        flip: JSON | None = None,
        body: JSON | None = None,
        corner_relief_shape: SheetFlangeCornerReliefShape | None = None,
        type: SheetFlangeType | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Flange.

        `sheet.flange`.

        K-factor and bend radius come from the rule
        (sheet.manage_rules); passing them here is refused, and so is
        the corner relief on a base or contour flange

        Arguments:
        * `base` (`JSON | None`):
          (required) sketch + profiles? (rule?, flip?)
        * `contour` (`JSON | None`):
          sketch + curves (open chain of lines) + distance (rule?,
          flip?, reverse?)
        * `edge` (`JSON | None`):
          edges: [[x,y,z] on top/bottom edges, or {point: [x,y,z],
          angle?, height?} for an edge with its own angle and height] +
          height (to the outer face)
        * `angle` (`JSON | None`):
          (default 90 deg)
        * `radius` (`JSON | None`):
          (default: rule)
        * `position` (`SheetFlangePosition | None`):
          inside|outside|middle
        * `flip` (`JSON | None`):
          See SolidCraft.
        * `body` (`JSON | None`):
          See SolidCraft.
        * `corner_relief_shape` (`SheetFlangeCornerReliefShape | None`):
          notch|round|rectangular|tear and corner_relief? (size across):
          the relief at the corners these flanges make (default: the
          rule's)
        * `type` (`SheetFlangeType | None`):
          base|edge|contour (default from the inputs)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          (the new body). Thickness
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.flange",
            {
                "base": base,
                "contour": contour,
                "edge": edge,
                "angle": angle,
                "radius": radius,
                "position": position,
                "flip": flip,
                "body": body,
                "corner_relief_shape": corner_relief_shape,
                "type": type,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSheetCommands.flat_pattern()`:
    def flat_pattern(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Create Flat Pattern.

        `sheet.flat_pattern`.

        Arguments:
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): flat size, outline loops and cut-outs (flat
          coordinates, as point lists), cutout_shapes (the same cut-outs
          exactly, in the same order: {circle: {center, radius}} for a
          round hole, else {segments: [{line: [a, b]} | {arc: {center,
          radius, start_deg, sweep_deg}} | {polyline: [...]}]}), pockets
          (with their own cutout_shapes), bend lines and the bend table

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.flat_pattern",
            {
                "body": body,
                **extra,
            },
        )

    # Method `SCSheetCommands.fold()`:
    def fold(
        self,
        *,
        line: JSON | None = None,
        points: JSON | None = None,
        angle: JSON | None = None,
        radius: JSON | None = None,
        position: SheetFoldPosition | None = None,
        fixed: Point3D | None = None,
        flip: JSON | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fold.

        `sheet.fold`.

        Arguments:
        * `line` (`JSON | None`):
          (required) sketch + curve (a sketch line on the sheet's base
          face; followed when the sketch changes)
        * `points` (`JSON | None`):
          [[x,y,z], [x,y,z]]
        * `angle` (`JSON | None`):
          (default 90 deg)
        * `radius` (`JSON | None`):
          (default: rule)
        * `position` (`SheetFoldPosition | None`):
          centerline|start|end|mould (where the line sits in the bend,
          default centerline)
        * `fixed` (`Point3D | None`):
          [x,y,z] on the side that stays (default: the larger side)
        * `flip` (`JSON | None`):
          (fold the other way)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.fold",
            {
                "line": line,
                "points": points,
                "angle": angle,
                "radius": radius,
                "position": position,
                "fixed": fixed,
                "flip": flip,
                "body": body,
                **extra,
            },
        )

    # Method `SCSheetCommands.hem()`:
    def hem(
        self,
        *,
        edges: JSON | None = None,
        length: JSON | None = None,
        gap: JSON | None = None,
        flip: JSON | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Hem.

        `sheet.hem`.

        Arguments:
        * `edges` (`JSON | None`):
          (required) [[x,y,z] on sheet edges]
        * `length` (`JSON | None`):
          (required) (to the outer face)
        * `gap` (`JSON | None`):
          (inner radius, default: rule)
        * `flip` (`JSON | None`):
          See SolidCraft.
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.hem",
            {
                "edges": edges,
                "length": length,
                "gap": gap,
                "flip": flip,
                "body": body,
                **extra,
            },
        )

    # Method `SCSheetCommands.manage_rules()`:
    def manage_rules(
        self,
        *,
        name: JSON | None = None,
        thickness: JSON | None = None,
        k_factor: JSON | None = None,
        bend_radius: JSON | None = None,
        relief_width: JSON | None = None,
        relief_depth: JSON | None = None,
        corner_relief: JSON | None = None,
        hem_gap: JSON | None = None,
        gap: JSON | None = None,
        corner_relief_shape: SheetManageRulesCornerReliefShape | None = None,
        active: bool | None = None,
        delete: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sheet Metal Rules.

        `sheet.manage_rules`.

        Arguments:
        * `name` (`JSON | None`):
          (required) (new or existing)
        * `thickness` (`JSON | None`):
          See SolidCraft.
        * `k_factor` (`JSON | None`):
          See SolidCraft.
        * `bend_radius` (`JSON | None`):
          See SolidCraft.
        * `relief_width` (`JSON | None`):
          See SolidCraft.
        * `relief_depth` (`JSON | None`):
          See SolidCraft.
        * `corner_relief` (`JSON | None`):
          See SolidCraft.
        * `hem_gap` (`JSON | None`):
          See SolidCraft.
        * `gap` (`JSON | None`):
          (expressions; `Thickness` is the rule's; gap: between flanges
          that meet at a corner, whose ends are closed toward each other
          at any angle)
        * `corner_relief_shape` (`SheetManageRulesCornerReliefShape | None`):
          notch|round|rectangular|tear (what is cut where two bends meet
          at a corner of the base: round and rectangular a relief
          `corner_relief` across; tear none, each bend's end is cut
          straight from the corner to its flange's end; default notch)
        * `active` (`bool | None`):
          bool
        * `delete` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.manage_rules",
            {
                "name": name,
                "thickness": thickness,
                "k_factor": k_factor,
                "bend_radius": bend_radius,
                "relief_width": relief_width,
                "relief_depth": relief_depth,
                "corner_relief": corner_relief,
                "hem_gap": hem_gap,
                "gap": gap,
                "corner_relief_shape": corner_relief_shape,
                "active": active,
                "delete": delete,
                **extra,
            },
        )

    # Method `SCSheetCommands.perforate()`:
    def perforate(
        self,
        *,
        diameter: JSON | None = None,
        pitch: Expr | None = None,
        margin: Expr | None = None,
        pattern: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Perforate.

        `sheet.perforate`.

        body? - a perforation field over the whole flat sheet: holes in
        the flat pattern (perforations), the DXF (layer PERFORATION) and
        the measured volume, not cut into the B-rep (#732)

        Arguments:
        * `diameter` (`JSON | None`):
          (required) See SolidCraft.
        * `pitch` (`Expr | None`):
          (required) expr
        * `margin` (`Expr | None`):
          expr (clear of edges, cut-outs and bends; default: the
          diameter)
        * `pattern` (`JSON | None`):
          staggered (60°, default) | square
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.perforate",
            {
                "diameter": diameter,
                "pitch": pitch,
                "margin": margin,
                "pattern": pattern,
                **extra,
            },
        )

    # Method `SCSheetCommands.refold()`:
    def refold(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Refold.

        `sheet.refold`.

        Arguments:
        * `body` (`JSON | None`):
          (default: the last unfolded sheet)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.refold",
            {
                "body": body,
                **extra,
            },
        )

    # Method `SCSheetCommands.rules()`:
    def rules(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Sheet Metal Rules.

        `sheet.rules`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): rules with their expressions and values, and the
          active one

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.rules",
            {
                **extra,
            },
        )

    # Method `SCSheetCommands.unfold()`:
    def unfold(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Unfold.

        `sheet.unfold`.

        Arguments:
        * `body` (`JSON | None`):
          (default: the last sheet body) — all bends
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sheet.unfold",
            {
                "body": body,
                **extra,
            },
        )


# Class `SCSketchCommands`:
@dataclass(slots=True)
class SCSketchCommands(SCNamespace):
    """The `sketch.*` commands.

    Constructor:
    * `SCSketchCommands(transport)`
    """

    # Method `SCSketchCommands.arc_center_point()`:
    def arc_center_point(
        self,
        *,
        center: JSON | None = None,
        start: JSON | None = None,
        end: JSON | None = None,
        sweep: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center Point Arc.

        `sketch.arc.center_point`.

        start

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `start` (`JSON | None`):
          (required) See SolidCraft.
        * `end` (`JSON | None`):
          (required) (counter-clockwise from start) | center
        * `sweep` (`JSON | None`):
          (required) signed degrees
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.arc.center_point",
            {
                "center": center,
                "start": start,
                "end": end,
                "sweep": sweep,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.arc_tangent()`:
    def arc_tangent(
        self,
        *,
        start: JSON | None = None,
        end: Point2D | None = None,
        curve: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Tangent Arc.

        `sketch.arc.tangent`.

        Arguments:
        * `start` (`JSON | None`):
          (required) end point of a line or arc ("l1.end")
        * `end` (`Point2D | None`):
          (required) [x,y]
        * `curve` (`JSON | None`):
          the curve to be tangent to (default: the one ending at start).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.arc.tangent",
            {
                "start": start,
                "end": end,
                "curve": curve,
                **extra,
            },
        )

    # Method `SCSketchCommands.arc_three_point()`:
    def arc_three_point(
        self,
        *,
        start: JSON | None = None,
        end: JSON | None = None,
        through: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """3-Point Arc.

        `sketch.arc.three_point`.

        Arguments:
        * `start` (`JSON | None`):
          (required) See SolidCraft.
        * `end` (`JSON | None`):
          (required) See SolidCraft.
        * `through` (`JSON | None`):
          (required) [x,y] or point ref (a referenced through point
          stays on the arc)
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.arc.three_point",
            {
                "start": start,
                "end": end,
                "through": through,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.auto_constrain()`:
    def auto_constrain(
        self,
        *,
        tolerance: Expr | None = None,
        angle_tolerance: Expr | None = None,
        dimensions: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """AutoConstrain.

        `sketch.auto_constrain`.

        then dimension until fully constrained

        Arguments:
        * `tolerance` (`Expr | None`):
          mm (default 0.01)
        * `angle_tolerance` (`Expr | None`):
          deg (default 1)
        * `dimensions` (`bool | None`):
          bool (default true): infer constraints
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.auto_constrain",
            {
                "tolerance": tolerance,
                "angle_tolerance": angle_tolerance,
                "dimensions": dimensions,
                **extra,
            },
        )

    # Method `SCSketchCommands.auto_constrain_from_datum()`:
    def auto_constrain_from_datum(
        self,
        *,
        datum: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """AutoConstrain from datum.

        `sketch.auto_constrain_from_datum`.

        like AutoConstrain with positions measured from the datum

        Arguments:
        * `datum` (`JSON | None`):
          (required) point ref (default origin)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.auto_constrain_from_datum",
            {
                "datum": datum,
                **extra,
            },
        )

    # Method `SCSketchCommands.auto_project()`:
    def auto_project(
        self,
        *,
        value: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Auto-Project Edges on Reference.

        `sketch.auto_project`.

        Arguments:
        * `value` (`bool | None`):
          bool (default toggles): project a face's edges when a sketch
          is created on it
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.auto_project",
            {
                "value": value,
                **extra,
            },
        )

    # Method `SCSketchCommands.blend_curve()`:
    def blend_curve(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        continuity: SketchBlendCurveContinuity | None = None,
        **extra: JSON,
    ) -> JSON:
        """Blend Curve.

        `sketch.blend_curve`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) end points of two curves ("l1.end", "a2.start")
        * `continuity` (`SketchBlendCurveContinuity | None`):
          g1|g2|g3|g4 (default g1: a tangent spline; g2…g4 match the
          reference curves' curvature, curvature rate and 4th derivative
          as well, as one Bézier of degree 5, 7 or 9).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.blend_curve",
            {
                "a": a,
                "b": b,
                "continuity": continuity,
                **extra,
            },
        )

    # Method `SCSketchCommands.break_()`:
    def break_(
        self,
        *,
        curve: JSON | None = None,
        at: Point2D | None = None,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Break.

        `sketch.break`.

        Arguments:
        * `curve` (`JSON | None`):
          (required) id
        * `at` (`Point2D | None`):
          (required) [x,y] (split at intersections)
        * `points` (`JSON | None`):
          [[x,y]…] (1…1000 positions projected onto the curve;
          duplicates are merged).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.break",
            {
                "curve": curve,
                "at": at,
                "points": points,
                **extra,
            },
        )

    # Method `SCSketchCommands.break_link()`:
    def break_link(
        self,
        *,
        link: JSON | None = None,
        entities: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Break Link.

        `sketch.break_link`.

        Arguments:
        * `link` (`JSON | None`):
          link id (j1)
        * `entities` (`JSON | None`):
          [curve or point ids]: linked geometry becomes normal sketch
          geometry
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.break_link",
            {
                "link": link,
                "entities": entities,
                **extra,
            },
        )

    # Method `SCSketchCommands.centerline()`:
    def centerline(
        self,
        *,
        curves: JSON | None = None,
        value: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Centerline.

        `sketch.centerline`.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [line ids]
        * `value` (`bool | None`):
          bool (default toggles): centerline line type (not in profiles;
          an axis)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.centerline",
            {
                "curves": curves,
                "value": value,
                **extra,
            },
        )

    # Method `SCSketchCommands.chain()`:
    def chain(
        self,
        *,
        curve: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Chain.

        `sketch.chain`.

        Arguments:
        * `curve` (`JSON | None`):
          (required) id: the curves joined to it end to end (what a
          double-click selects)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.chain",
            {
                "curve": curve,
                **extra,
            },
        )

    # Method `SCSketchCommands.chamfer_distance_angle()`:
    def chamfer_distance_angle(
        self,
        *,
        b: JSON | None = None,
        distance: JSON | None = None,
        angle: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Distance and Angle Chamfer.

        `sketch.chamfer.distance_angle`.

        point | a

        Arguments:
        * `b` (`JSON | None`):
          (required) a corner of two lines
        * `distance` (`JSON | None`):
          (required) along a
        * `angle` (`Expr | None`):
          (required) deg from a.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.chamfer.distance_angle",
            {
                "b": b,
                "distance": distance,
                "angle": angle,
                **extra,
            },
        )

    # Method `SCSketchCommands.chamfer_equal_distance()`:
    def chamfer_equal_distance(
        self,
        *,
        b: JSON | None = None,
        distance: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Equal Distance Chamfer.

        `sketch.chamfer.equal_distance`.

        point | a

        Arguments:
        * `b` (`JSON | None`):
          (required) a corner of two lines
        * `distance` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.chamfer.equal_distance",
            {
                "b": b,
                "distance": distance,
                **extra,
            },
        )

    # Method `SCSketchCommands.chamfer_two_distance()`:
    def chamfer_two_distance(
        self,
        *,
        b: JSON | None = None,
        distance: JSON | None = None,
        distance2: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Two Distance Chamfer.

        `sketch.chamfer.two_distance`.

        point | a

        Arguments:
        * `b` (`JSON | None`):
          (required) a corner of two lines
        * `distance` (`JSON | None`):
          (required) along a
        * `distance2` (`JSON | None`):
          (required) along b.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.chamfer.two_distance",
            {
                "b": b,
                "distance": distance,
                "distance2": distance2,
                **extra,
            },
        )

    # Method `SCSketchCommands.circle_center()`:
    def circle_center(
        self,
        *,
        center: JSON | None = None,
        radius: JSON | None = None,
        diameter: float | None = None,
        through: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center Diameter Circle.

        `sketch.circle.center`.

        Arguments:
        * `center` (`JSON | None`):
          (required) [x,y] or point ref
        * `radius` (`JSON | None`):
          (required) See SolidCraft.
        * `diameter` (`float | None`):
          number
        * `through` (`JSON | None`):
          point ref (a point the circle passes through, kept on it:
          where the tool's second click snapped)
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.circle.center",
            {
                "center": center,
                "radius": radius,
                "diameter": diameter,
                "through": through,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.circle_three_point()`:
    def circle_three_point(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        p2: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """3-Point Circle.

        `sketch.circle.three_point`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) See SolidCraft.
        * `p2` (`JSON | None`):
          (required) See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.circle.three_point",
            {
                "p0": p0,
                "p1": p1,
                "p2": p2,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.circle_three_tangent()`:
    def circle_three_tangent(
        self,
        *,
        curves: JSON | None = None,
        near: Point2D | None = None,
        **extra: JSON,
    ) -> JSON:
        """3-Tangent Circle.

        `sketch.circle.three_tangent`.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [three lines/circles/arcs]
        * `near` (`Point2D | None`):
          (required) [x,y] (which of the solutions).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.circle.three_tangent",
            {
                "curves": curves,
                "near": near,
                **extra,
            },
        )

    # Method `SCSketchCommands.circle_two_point()`:
    def circle_two_point(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """2-Point Circle.

        `sketch.circle.two_point`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) diameter ends
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.circle.two_point",
            {
                "p0": p0,
                "p1": p1,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.circle_two_tangent()`:
    def circle_two_tangent(
        self,
        *,
        curves: JSON | None = None,
        radius: JSON | None = None,
        diameter: Expr | None = None,
        near: Point2D | None = None,
        **extra: JSON,
    ) -> JSON:
        """2-Tangent Circle.

        `sketch.circle.two_tangent`.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [two lines/circles/arcs]
        * `radius` (`JSON | None`):
          (required) See SolidCraft.
        * `diameter` (`Expr | None`):
          expr
        * `near` (`Point2D | None`):
          (required) [x,y] (which of the solutions).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.circle.two_tangent",
            {
                "curves": curves,
                "radius": radius,
                "diameter": diameter,
                "near": near,
                **extra,
            },
        )

    # Method `SCSketchCommands.conic()`:
    def conic(
        self,
        *,
        start: JSON | None = None,
        end: JSON | None = None,
        apex: JSON | None = None,
        rho: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Conic Curve.

        `sketch.conic`.

        Arguments:
        * `start` (`JSON | None`):
          (required) See SolidCraft.
        * `end` (`JSON | None`):
          (required) See SolidCraft.
        * `apex` (`JSON | None`):
          (required) [x,y] or point refs
        * `rho` (`JSON | None`):
          0…1 (default 0.5: parabola).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.conic",
            {
                "start": start,
                "end": end,
                "apex": apex,
                "rho": rho,
                **extra,
            },
        )

    # Method `SCSketchCommands.constrainer()`:
    def constrainer(
        self,
        *,
        entities: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sketch Constrainer.

        `sketch.constrainer`.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [one or two sketch entity ids]: applies the
          constraint the geometry nearly has (horizontal/vertical,
          parallel, perpendicular, collinear, coincident, concentric,
          equal, tangent)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constrainer",
            {
                "entities": entities,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_coincident()`:
    def constraint_coincident(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Coincident.

        `sketch.constraint.coincident`.

        a point and a curve or sketch axis (x / y: the sketch's own
        axes, unless a curve has that id; an axis becomes a linked
        construction line on it, reported in created), two distinct
        lines (joins their closest endpoints)

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) points
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.coincident",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_collinear()`:
    def constraint_collinear(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Collinear.

        `sketch.constraint.collinear`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) lines or sketch axes (x / y: the sketch's own axes,
          unless a curve has that id; an axis becomes a linked
          construction line on it, reported in created)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.collinear",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_concentric()`:
    def constraint_concentric(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Concentric.

        `sketch.constraint.concentric`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) circles/arcs
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.concentric",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_curvature()`:
    def constraint_curvature(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Curvature.

        `sketch.constraint.curvature`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) two curves sharing an end point (curvature
          continuous, G2)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.curvature",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_equal()`:
    def constraint_equal(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Equal.

        `sketch.constraint.equal`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) lines or circles/arcs
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.equal",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_fix()`:
    def constraint_fix(
        self,
        *,
        entity: JSON | None = None,
        entities: JSON | None = None,
        fixed: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fix/UnFix.

        `sketch.constraint.fix`.

        Arguments:
        * `entity` (`JSON | None`):
          (required) point or curve
        * `entities` (`JSON | None`):
          [points and curves]
        * `fixed` (`bool | None`):
          bool (default: fix them all unless all are fixed, then unfix)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.fix",
            {
                "entity": entity,
                "entities": entities,
                "fixed": fixed,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_horizontal_vertical()`:
    def constraint_horizontal_vertical(
        self,
        *,
        line: JSON | None = None,
        points: JSON | None = None,
        mode: SketchConstraintHorizontalVerticalMode | None = None,
        **extra: JSON,
    ) -> JSON:
        """Horizontal/Vertical.

        `sketch.constraint.horizontal_vertical`.

        Arguments:
        * `line` (`JSON | None`):
          (required) id
        * `points` (`JSON | None`):
          [a, b] (point ids or {midpoint: line_id}; accepted midpoints
          reuse or create a point with a Midpoint constraint)
        * `mode` (`SketchConstraintHorizontalVerticalMode | None`):
          horizontal|vertical
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.horizontal_vertical",
            {
                "line": line,
                "points": points,
                "mode": mode,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_midpoint()`:
    def constraint_midpoint(
        self,
        *,
        point: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """MidPoint.

        `sketch.constraint.midpoint`.

        line | a, b in pick order: a point and a line (either way
        round), two lines whose midpoints meet (the first stays, the
        second moves)

        Arguments:
        * `point` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.midpoint",
            {
                "point": point,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_parallel()`:
    def constraint_parallel(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Parallel.

        `sketch.constraint.parallel`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) lines or sketch axes (x / y: the sketch's own axes,
          unless a curve has that id; an axis becomes a linked
          construction line on it, reported in created)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.parallel",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_perpendicular()`:
    def constraint_perpendicular(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Perpendicular.

        `sketch.constraint.perpendicular`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) lines or sketch axes (x / y: the sketch's own axes,
          unless a curve has that id; an axis becomes a linked
          construction line on it, reported in created)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.perpendicular",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_polygon()`:
    def constraint_polygon(
        self,
        *,
        lines: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Polygon.

        `sketch.constraint.polygon`.

        Arguments:
        * `lines` (`JSON | None`):
          (required) [line ids] of a closed chain: equal sides with
          every corner on one circle (a regular polygon)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.polygon",
            {
                "lines": lines,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_symmetry()`:
    def constraint_symmetry(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        line: JSON | None = None,
        point: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Symmetry.

        `sketch.constraint.symmetry`.

        x / y for the sketch's own axes (a curve with that id wins; an
        axis becomes a linked construction line on it, reported in
        created); each pair joined by a construction line it is the
        midpoint of

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) two points or two curves (lines mirror their ends,
          circles/arcs their centres)
        * `line` (`JSON | None`):
          (required) symmetry line id
        * `point` (`JSON | None`):
          (or a point id as line, "origin" too): symmetric about that
          point
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.symmetry",
            {
                "a": a,
                "b": b,
                "line": line,
                "point": point,
                **extra,
            },
        )

    # Method `SCSketchCommands.constraint_tangent()`:
    def constraint_tangent(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Tangent.

        `sketch.constraint.tangent`.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) curves or sketch axes (x / y: the sketch's own
          axes, unless a curve has that id; an axis becomes a linked
          construction line on it, reported in created)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.constraint.tangent",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.construction()`:
    def construction(
        self,
        *,
        curves: JSON | None = None,
        value: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Normal/Construction.

        `sketch.construction`.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [ids]
        * `value` (`bool | None`):
          bool (default: construction unless all of them already are)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.construction",
            {
                "curves": curves,
                "value": value,
                **extra,
            },
        )

    # Method `SCSketchCommands.copy()`:
    def copy(
        self,
        *,
        entities: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Copy Sketch Entities.

        `sketch.copy`.

        the constraints and dimensions among them come along

        Arguments:
        * `entities` (`JSON | None`):
          [curve or point ids] (default: the selected sketch geometry)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.copy",
            {
                "entities": entities,
                **extra,
            },
        )

    # Method `SCSketchCommands.create()`:
    def create(
        self,
        *,
        plane: JSON | None = None,
        fixed: JSON | None = None,
        offset: Expr | None = None,
        flip: JSON | None = None,
        project_edges: bool | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Create Sketch.

        `sketch.create`.

        new face attachments require a unique certified source (a flat
        face of a sheet metal body attaches to its panel instead, in the
        flat pattern's coordinates)

        Arguments:
        * `plane` (`JSON | None`):
          (required) XY|XZ|YZ | construction plane name or id |
          {origin?: [x,y,z] numbers in mm, default [0,0,0] (not an
          expression), x_dir, y_dir} | {face: [world x,y,z], body?:
          exact world body, index?: face index, path?: complete
          occurrence ids, fixed?: bool}
        * `fixed` (`JSON | None`):
          (required) true explicitly freezes the selected plane
        * `offset` (`Expr | None`):
          expr
        * `flip` (`JSON | None`):
          bool | "x" | "y" (not on a face: sketch the plane from its
          other side, so the normal and the default extrude direction
          are reversed; a half turn about the plane's own x or y axis,
          true picks the one keeping the sketch's y axis upward; offset
          still moves along the unflipped normal)
        * `project_edges` (`bool | None`):
          bool
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.create",
            {
                "plane": plane,
                "fixed": fixed,
                "offset": offset,
                "flip": flip,
                "project_edges": project_edges,
                "name": name,
                **extra,
            },
        )

    # Method `SCSketchCommands.cut()`:
    def cut(
        self,
        *,
        entities: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Cut Sketch Entities.

        `sketch.cut`.

        then deletes them (one undo step)

        Arguments:
        * `entities` (`JSON | None`):
          [curve or point ids] (default: the selected sketch geometry):
          copies them as sketch.copy does
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.cut",
            {
                "entities": entities,
                **extra,
            },
        )

    # Method `SCSketchCommands.delete()`:
    def delete(
        self,
        *,
        entities: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Sketch Entities.

        `sketch.delete`.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [curve, point or constraint ids]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.delete",
            {
                "entities": entities,
                **extra,
            },
        )

    # Method `SCSketchCommands.dimension()`:
    def dimension(
        self,
        *,
        entities: JSON | None = None,
        type: SketchDimensionType | None = None,
        value: JSON | None = None,
        text_at: JSON | None = None,
        arc: JSON | None = None,
        if_redundant: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sketch Dimension.

        `sketch.dimension`.

        `name = expression` (e.g. "width = 40"), which adds the user
        parameter `name` with that expression and dimensions with `name`
        (refused when the name is taken or reserved; the reply's
        `defined` names it); text_at across from them is the distance
        between them, above or below them horizontal, beside them
        vertical. Two lines: the angle between them (acute, or 180° − it
        when the value is nearer that) unless text_at picks a sector. A
        line and a circle or dimension the centre point for the distance
        to the centre. A dimension the sketch already determines is
        refused (naming what determines it); the whole sketch scales
        about its origin to the value instead of distorting.; and
        scaled: the factor when the sketch was scaled

        Arguments:
        * `entities` (`JSON | None`):
          (required) [refs]
        * `type` (`SketchDimensionType | None`):
          auto|distance|horizontal|vertical|length|radius|diameter|angle
        * `value` (`JSON | None`):
          number or expression (default: current; a bare number is in
          the design's units, e.g. 2 means 2 in in an inch design; give
          a unit such as "50 mm" to override)
        * `text_at` (`JSON | None`):
          [x, y]. Two points or a line off the axes: with auto
        * `arc` (`JSON | None`):
          the distance from the line to its edge (the gap, or how far
          the edge reaches past a line that cuts it; 0 is tangent)
        * `if_redundant` (`JSON | None`):
          "driven" places it as a driven (reference) dimension instead.
          scale_sketch?: bool (the dimension tool sends true): when this
          is the sketch's first length dimension and nothing in the
          sketch fixes a size (no other driving length dimension,
          nothing fixed or projected)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns measured in unit (mm or deg)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.dimension",
            {
                "entities": entities,
                "type": type,
                "value": value,
                "text_at": text_at,
                "arc": arc,
                "if_redundant": if_redundant,
                **extra,
            },
        )

    # Method `SCSketchCommands.dimension_text()`:
    def dimension_text(
        self,
        *,
        dimension: JSON | None = None,
        at: Point2D | None = None,
        reset: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Dimension Text.

        `sketch.dimension_text`.

        Arguments:
        * `dimension` (`JSON | None`):
          (required) constraint id or parameter name
        * `at` (`Point2D | None`):
          (required) [x,y] text centre (sketch coordinates)
        * `reset` (`JSON | None`):
          true (default place)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.dimension_text",
            {
                "dimension": dimension,
                "at": at,
                "reset": reset,
                **extra,
            },
        )

    # Method `SCSketchCommands.drag()`:
    def drag(
        self,
        *,
        entity: JSON | None = None,
        from_: Point2D | None = None,
        to: Point2D | None = None,
        live: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Drag Sketch Geometry.

        `sketch.drag`.

        bounded feasible steps minimize cursor distance. Splines slide
        by to - from; a circle or arc grabbed on its edge takes the
        radius to `to`. `with?`: [point or curve ids] moves the rest of
        a selection with the entity as one translation (circles keep
        their radii). Long moves retain the solution branch; arcs cannot
        sweep through their starts.; `at`: the grabbed position for the
        next frame, and `retry`: budget-limited progress can continue in
        another frame. `live: true` shares a work budget across
        held-solve decomposition and cursor correction; ordinary
        recovery and the final model evaluation retain their existing
        limits, not a wall-clock deadline. Later features stay stale
        until `sketch.drag_end`; `dof` stays from before the drag

        Arguments:
        * `entity` (`JSON | None`):
          (required) point or curve
        * `from_` (`Point2D | None`):
          (required) [x,y] where it was grabbed (sent as `from`)
        * `to` (`Point2D | None`):
          (required) [x,y]
        * `live` (`bool | None`):
          bool: points and the material point grabbed on a line move
          toward `to` within the design constraints. When exact
          placement is impossible
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns `reached`: progress projected onto the
          requested move (0..1)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.drag",
            {
                "entity": entity,
                "from": from_,
                "to": to,
                "live": live,
                **extra,
            },
        )

    # Method `SCSketchCommands.drag_end()`:
    def drag_end(
        self,
        *,
        constraint: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """End Sketch Drag.

        `sketch.drag_end`.

        then evaluates the whole model once; returns the constraint's
        result and the sketch's solved state and degrees of freedom

        Arguments:
        * `constraint` (`JSON | None`):
          {command: a sketch.constraint.* id, params}: ends a drag made
          of `sketch.drag` `live: true` frames: adds the constraint it
          let go on (not kept if it over-constrains the sketch)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.drag_end",
            {
                "constraint": constraint,
                **extra,
            },
        )

    # Method `SCSketchCommands.draw_dimensioned()`:
    def draw_dimensioned(
        self,
        *,
        command: JSON | None = None,
        params: JSON | None = None,
        dimensions: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Draw Dimensioned Sketch Geometry.

        `sketch.draw.dimensioned`.

        creates geometry and all driving dimensions atomically in one
        undo step.

        Arguments:
        * `command` (`JSON | None`):
          (required) sketch creation command
        * `params` (`JSON | None`):
          (required) object
        * `dimensions` (`JSON | None`):
          (required) object of role to numeric or expression value
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.draw.dimensioned",
            {
                "command": command,
                "params": params,
                "dimensions": dimensions,
                **extra,
            },
        )

    # Method `SCSketchCommands.edit()`:
    def edit(
        self,
        *,
        sketch: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Sketch.

        `sketch.edit`.

        Arguments:
        * `sketch` (`JSON | None`):
          (required) id or name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.edit",
            {
                "sketch": sketch,
                **extra,
            },
        )

    # Method `SCSketchCommands.edit_text()`:
    def edit_text(
        self,
        *,
        link: JSON | None = None,
        text: JSON | None = None,
        at: JSON | None = None,
        height: JSON | None = None,
        angle: Expr | None = None,
        font: JSON | None = None,
        bold: JSON | None = None,
        italic: bool | None = None,
        align: SketchEditTextAlign | None = None,
        letter_spacing: JSON | None = None,
        line_spacing: JSON | None = None,
        path: JSON | None = None,
        reverse: bool | None = None,
        edits: JSON | None = None,
        live: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Text.

        `sketch.edit_text`.

        the design rebuilt once (all or nothing; returns edits: each
        one's result)

        Arguments:
        * `link` (`JSON | None`):
          (required) the text's link id (or entity: one of its curves)
        * `text` (`JSON | None`):
          See SolidCraft.
        * `at` (`JSON | None`):
          See SolidCraft.
        * `height` (`JSON | None`):
          See SolidCraft.
        * `angle` (`Expr | None`):
          deg (numbers or expressions as in sketch.text; a number
          replaces an expression, and so does moving the text)
        * `font` (`JSON | None`):
          family or file path (empty: the built-in font)
        * `bold` (`JSON | None`):
          See SolidCraft.
        * `italic` (`bool | None`):
          bool (an installed family's bold or italic face; italic
          without one is slanted)
        * `align` (`SketchEditTextAlign | None`):
          left|center|right (the lines against `at`, or along the path)
        * `letter_spacing` (`JSON | None`):
          extra mm between letters
        * `line_spacing` (`JSON | None`):
          times the font's line distance (default 1)
        * `path` (`JSON | None`):
          a curve id of the sketch the baseline follows ("": none; `at`
          and `angle` then do not place the text; the curve becomes
          construction, a guide the letters stand on)
        * `reverse` (`bool | None`):
          bool (the other way along the path) (each kept when left out)
        * `edits` (`JSON | None`):
          (required) [{link or entity, text?, at?, …}]: several texts
          changed together
        * `live` (`bool | None`):
          bool: one frame of an interactive change (the sketch is
          solved, the features after it stay as they were until
          `sketch.drag_end`).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.edit_text",
            {
                "link": link,
                "text": text,
                "at": at,
                "height": height,
                "angle": angle,
                "font": font,
                "bold": bold,
                "italic": italic,
                "align": align,
                "letter_spacing": letter_spacing,
                "line_spacing": line_spacing,
                "path": path,
                "reverse": reverse,
                "edits": edits,
                "live": live,
                **extra,
            },
        )

    # Method `SCSketchCommands.ellipse()`:
    def ellipse(
        self,
        *,
        center: JSON | None = None,
        major: JSON | None = None,
        minor: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Ellipse.

        `sketch.ellipse`.

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `major` (`JSON | None`):
          (required) end of the major axis [x,y]
        * `minor` (`JSON | None`):
          (required) a point the ellipse passes through on the minor
          side [x,y] | minor_radius.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.ellipse",
            {
                "center": center,
                "major": major,
                "minor": minor,
                **extra,
            },
        )

    # Method `SCSketchCommands.export_dxf()`:
    def export_dxf(
        self,
        *,
        sketch: SketchExportDxfSketch | None = None,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Save As DXF.

        `sketch.export_dxf`.

        Arguments:
        * `sketch` (`SketchExportDxfSketch | None`):
          id|name (default active)
        * `path` (`JSON | None`):
          file to write (else the DXF text is returned)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.export_dxf",
            {
                "sketch": sketch,
                "path": path,
                **extra,
            },
        )

    # Method `SCSketchCommands.extend()`:
    def extend(
        self,
        *,
        curve: JSON | None = None,
        at: Point2D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Extend.

        `sketch.extend`.

        Arguments:
        * `curve` (`JSON | None`):
          (required) id
        * `at` (`Point2D | None`):
          (required) [x,y] near the end to extend (to the nearest curve)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.extend",
            {
                "curve": curve,
                "at": at,
                **extra,
            },
        )

    # Method `SCSketchCommands.fillet()`:
    def fillet(
        self,
        *,
        point: JSON | None = None,
        points: JSON | None = None,
        b: JSON | None = None,
        radius: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fillet.

        `sketch.fillet`.

        Arguments:
        * `point` (`JSON | None`):
          (required) corner shared by two curves ("l1.end")
        * `points` (`JSON | None`):
          [corners] (all rounded alike: one radius, the rest equal) | a
        * `b` (`JSON | None`):
          (required) two lines or arcs meeting at a corner
        * `radius` (`JSON | None`):
          (required) expr. A corner that dimensions or constraints
          measure to stays as a virtual sharp corner on both curves'
          extensions (`virtual_corners`; the moved ones in
          `moved_to_virtual_corner`).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.fillet",
            {
                "point": point,
                "points": points,
                "b": b,
                "radius": radius,
                **extra,
            },
        )

    # Method `SCSketchCommands.finish()`:
    def finish(
        self,
        **extra: JSON,
    ) -> JSON:
        """Finish Sketch.

        `sketch.finish`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.finish",
            {
                **extra,
            },
        )

    # Method `SCSketchCommands.finish_auto_constrain()`:
    def finish_auto_constrain(
        self,
        **extra: JSON,
    ) -> JSON:
        """Finish with AutoConstrain.

        `sketch.finish_auto_constrain`.

        like AutoConstrain, then Finish Sketch

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.finish_auto_constrain",
            {
                **extra,
            },
        )

    # Method `SCSketchCommands.fit_curves_to_section()`:
    def fit_curves_to_section(
        self,
        *,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fit Curves to Mesh Section.

        `sketch.fit_curves_to_section`.

        fitted with lines and arcs, as normal (unlinked) geometry.

        Arguments:
        * `body` (`JSON | None`):
          (required) name (a mesh or solid body): its section with the
          sketch plane
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.fit_curves_to_section",
            {
                "body": body,
                **extra,
            },
        )

    # Method `SCSketchCommands.glyphs()`:
    def glyphs(
        self,
        *,
        sketch: SketchGlyphsSketch | None = None,
        **extra: JSON,
    ) -> JSON:
        """Constraint Glyphs.

        `sketch.glyphs`.

        Arguments:
        * `sketch` (`SketchGlyphsSketch | None`):
          id|name: every constraint with where to draw its glyph (sketch
          coordinates)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.glyphs",
            {
                "sketch": sketch,
                **extra,
            },
        )

    # Method `SCSketchCommands.include_3d()`:
    def include_3d(
        self,
        *,
        refs: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Include 3D Geometry.

        `sketch.include_3d`.

        curves out of the sketch plane are flattened onto it.

        Arguments:
        * `refs` (`JSON | None`):
          (required) like Project (edges, vertices, sketch curves and
          points)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.include_3d",
            {
                "refs": refs,
                **extra,
            },
        )

    # Method `SCSketchCommands.infinite()`:
    def infinite(
        self,
        *,
        curves: JSON | None = None,
        value: bool | None = None,
        off: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Infinite Line.

        `sketch.infinite`.

        a normal line

        Arguments:
        * `curves` (`JSON | None`):
          (required) [line ids]
        * `value` (`bool | None`):
          bool (default toggles): infinite line type (#1359):
          construction geometry drawn across the whole view through the
          line's two points
        * `off` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.infinite",
            {
                "curves": curves,
                "value": value,
                "off": off,
                **extra,
            },
        )

    # Method `SCSketchCommands.insert_dxf()`:
    def insert_dxf(
        self,
        *,
        path: JSON | None = None,
        text: JSON | None = None,
        at: Point2D | None = None,
        scale: JSON | None = None,
        tolerance: Expr | None = None,
        plane: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert DXF.

        `sketch.insert_dxf`.

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `text` (`JSON | None`):
          ASCII DXF (blocks expanded)
        * `at` (`Point2D | None`):
          [x,y] offset
        * `scale` (`JSON | None`):
          See SolidCraft.
        * `tolerance` (`Expr | None`):
          mm within which ends join (default 0.0001)
        * `plane` (`JSON | None`):
          (when no sketch is active, a new sketch on it; default XY).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.insert_dxf",
            {
                "path": path,
                "text": text,
                "at": at,
                "scale": scale,
                "tolerance": tolerance,
                "plane": plane,
                **extra,
            },
        )

    # Method `SCSketchCommands.insert_svg()`:
    def insert_svg(
        self,
        *,
        path: JSON | None = None,
        text: JSON | None = None,
        at: Point2D | None = None,
        scale: JSON | None = None,
        tolerance: Expr | None = None,
        plane: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Insert SVG.

        `sketch.insert_svg`.

        Arguments:
        * `path` (`JSON | None`):
          (required) See SolidCraft.
        * `text` (`JSON | None`):
          SVG
        * `at` (`Point2D | None`):
          [x,y] offset
        * `scale` (`JSON | None`):
          See SolidCraft.
        * `tolerance` (`Expr | None`):
          mm within which ends join (default 0.0001)
        * `plane` (`JSON | None`):
          (when no sketch is active, a new sketch on it; default XY).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.insert_svg",
            {
                "path": path,
                "text": text,
                "at": at,
                "scale": scale,
                "tolerance": tolerance,
                "plane": plane,
                **extra,
            },
        )

    # Method `SCSketchCommands.inspect()`:
    def inspect(
        self,
        *,
        sketch: SketchInspectSketch | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inspect Sketch.

        `sketch.inspect`.

        Arguments:
        * `sketch` (`SketchInspectSketch | None`):
          id|name (default active)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.inspect",
            {
                "sketch": sketch,
                **extra,
            },
        )

    # Method `SCSketchCommands.intersect()`:
    def intersect(
        self,
        *,
        refs: JSON | None = None,
        linked: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Intersect.

        `sketch.intersect`.

        Arguments:
        * `refs` (`JSON | None`):
          (required) [{body}, {face: [x,y,z], body?}, {edge: [x,y,z],
          body?}, {sketch, curve}]: section curves (or points) with the
          sketch plane
        * `linked` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.intersect",
            {
                "refs": refs,
                "linked": linked,
                **extra,
            },
        )

    # Method `SCSketchCommands.intersection_curve()`:
    def intersection_curve(
        self,
        *,
        a: JSON | None = None,
        b: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Intersection Curve.

        `sketch.intersection_curve`.

        as linked 3D curves.

        Arguments:
        * `a` (`JSON | None`):
          (required) See SolidCraft.
        * `b` (`JSON | None`):
          (required) {body} | {face: [x,y,z], body?}: where they meet
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.intersection_curve",
            {
                "a": a,
                "b": b,
                **extra,
            },
        )

    # Method `SCSketchCommands.isoparametric_curve()`:
    def isoparametric_curve(
        self,
        *,
        face: Point3D | None = None,
        body: JSON | None = None,
        direction: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Isoparametric Curve.

        `sketch.isoparametric_curve`.

        Arguments:
        * `face` (`Point3D | None`):
          (required) [x,y,z] point on the face (the curve passes through
          it)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `direction` (`JSON | None`):
          u|v|[x,y,z] (default u): linked 3D curve.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.isoparametric_curve",
            {
                "face": face,
                "body": body,
                "direction": direction,
                **extra,
            },
        )

    # Method `SCSketchCommands.line()`:
    def line(
        self,
        *,
        points: JSON | None = None,
        closed: bool | None = None,
        construction: bool | None = None,
        ids: JSON | None = None,
        infer: bool | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Line.

        `sketch.line`.

        Arguments:
        * `points` (`JSON | None`):
          (required) [[x,y] | "l1.end" | {at, ref}…] (x and y each a
          number or an expression over the design's parameters, "W / 2":
          such a point is fixed where it comes to and follows the
          parameters; likewise wherever a point argument also takes a
          point id)
        * `closed` (`bool | None`):
          bool
        * `construction` (`bool | None`):
          bool
        * `ids` (`JSON | None`):
          [..]
        * `infer` (`bool | None`):
          bool (add horizontal/vertical)
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.line",
            {
                "points": points,
                "closed": closed,
                "construction": construction,
                "ids": ids,
                "infer": infer,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.line_midpoint()`:
    def line_midpoint(
        self,
        *,
        mid: JSON | None = None,
        end: Point2D | None = None,
        construction: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Midpoint Line.

        `sketch.line.midpoint`.

        Arguments:
        * `mid` (`JSON | None`):
          (required) [x,y] or point ref
        * `end` (`Point2D | None`):
          (required) [x,y]
        * `construction` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.line.midpoint",
            {
                "mid": mid,
                "end": end,
                "construction": construction,
                **extra,
            },
        )

    # Method `SCSketchCommands.line3d()`:
    def line3d(
        self,
        *,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """3D Line.

        `sketch.line3d`.

        joined end to end (needs 3D Sketch on).

        Arguments:
        * `points` (`JSON | None`):
          (required) [[x,y,z]…] world points (2 or more): one 3D line
          per segment
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.line3d",
            {
                "points": points,
                **extra,
            },
        )

    # Method `SCSketchCommands.loose_ends()`:
    def loose_ends(
        self,
        *,
        sketch: SketchLooseEndsSketch | None = None,
        untied: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Loose Ends.

        `sketch.loose_ends`.

        Arguments:
        * `sketch` (`SketchLooseEndsSketch | None`):
          id|name (default active): the ends of profile curves (not
          construction, projected or text) that can make a profile fail.
          open: [{point, curve, at}] ends that touch no other profile
          curve (no profile runs through them)
        * `untied` (`JSON | None`):
          (required) [{point, curve, at, touches: {point}|{curve}}] ends
          that touch another curve only by position (the profile closes
          now, but nothing keeps it closed when a dimension changes)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.loose_ends",
            {
                "sketch": sketch,
                "untied": untied,
                **extra,
            },
        )

    # Method `SCSketchCommands.loose_ends_tie()`:
    def loose_ends_tie(
        self,
        *,
        sketch: SketchLooseEndsTieSketch | None = None,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Tie Loose Ends.

        `sketch.loose_ends.tie`.

        coincident with another curve's end or on another curve.; and
        the untied ends left

        Arguments:
        * `sketch` (`SketchLooseEndsTieSketch | None`):
          id|name (default active)
        * `points` (`JSON | None`):
          [point ids] (default: every untied end): ties each untied end
          to what it touches
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns constraints: [ids added]

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.loose_ends.tie",
            {
                "sketch": sketch,
                "points": points,
                **extra,
            },
        )

    # Method `SCSketchCommands.mirror()`:
    def mirror(
        self,
        *,
        entities: JSON | None = None,
        line: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Mirror.

        `sketch.mirror`.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [curve/point ids]
        * `line` (`JSON | None`):
          (required) mirror line id (symmetry constraints are added).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.mirror",
            {
                "entities": entities,
                "line": line,
                **extra,
            },
        )

    # Method `SCSketchCommands.move()`:
    def move(
        self,
        *,
        entities: JSON | None = None,
        translate: JSON | None = None,
        angle: Expr | None = None,
        center: Point2D | None = None,
        copy: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move/Copy Sketch Entities.

        `sketch.move`.

        picking a text outline or linked point transforms its whole text
        source once, and copies remain editable text.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [ids]
        * `translate` (`JSON | None`):
          [dx,dy]
        * `angle` (`Expr | None`):
          deg
        * `center` (`Point2D | None`):
          [x,y]
        * `copy` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.move",
            {
                "entities": entities,
                "translate": translate,
                "angle": angle,
                "center": center,
                "copy": copy,
                **extra,
            },
        )

    # Method `SCSketchCommands.move3d()`:
    def move3d(
        self,
        *,
        wire: JSON | None = None,
        index: JSON | None = None,
        to: Point3D | None = None,
        by: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move 3D Point.

        `sketch.move3d`.

        points joined to it move too

        Arguments:
        * `wire` (`JSON | None`):
          (required) drawn 3D curve or point id
        * `index` (`JSON | None`):
          fit point (default 0)
        * `to` (`Point3D | None`):
          (required) [x,y,z]
        * `by` (`JSON | None`):
          [dx,dy,dz]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.move3d",
            {
                "wire": wire,
                "index": index,
                "to": to,
                "by": by,
                **extra,
            },
        )

    # Method `SCSketchCommands.move_point()`:
    def move_point(
        self,
        *,
        point: JSON | None = None,
        to: Point2D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Drag Sketch Point.

        `sketch.move_point`.

        Arguments:
        * `point` (`JSON | None`):
          (required) ref
        * `to` (`Point2D | None`):
          (required) [x,y]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.move_point",
            {
                "point": point,
                "to": to,
                **extra,
            },
        )

    # Method `SCSketchCommands.offset()`:
    def offset(
        self,
        *,
        curves: JSON | None = None,
        distance: JSON | None = None,
        side: Point2D | None = None,
        chain: bool | None = None,
        direction: SketchOffsetDirection | None = None,
        symmetric: bool | None = None,
        distance2: JSON | None = None,
        flip: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Offset.

        `sketch.offset`.

        listed in `sides`; `param`/`param2` name the driving dimensions.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [ids]
        * `distance` (`JSON | None`):
          (required) number in mm or length expression (creates an
          editable dimension; positive = left of the chain, or toward
          `side`)
        * `side` (`Point2D | None`):
          [x,y]
        * `chain` (`bool | None`):
          bool (default true: the connected chain)
        * `direction` (`SketchOffsetDirection | None`):
          one_side|symmetric (default one_side)
        * `symmetric` (`bool | None`):
          bool (the same distance each way; no `side`, whose job it
          takes over)
        * `distance2` (`JSON | None`):
          positive length expression (Two Sides: an independent distance
          the other way, as for `solid.extrude`). Each side is its own
          offset association
        * `flip` (`bool | None`):
          bool reverses the primary side
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.offset",
            {
                "curves": curves,
                "distance": distance,
                "side": side,
                "chain": chain,
                "direction": direction,
                "symmetric": symmetric,
                "distance2": distance2,
                "flip": flip,
                **extra,
            },
        )

    # Method `SCSketchCommands.offset_break()`:
    def offset_break(
        self,
        *,
        curve: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Break Offset Association.

        `sketch.offset.break`.

        Arguments:
        * `curve` (`JSON | None`):
          (required) derived offset curve id (retains geometry and makes
          its points editable)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.offset.break",
            {
                "curve": curve,
                **extra,
            },
        )

    # Method `SCSketchCommands.options()`:
    def options(
        self,
        *,
        sketch: SketchOptionsSketch | None = None,
        show_points: JSON | None = None,
        show_dimensions: JSON | None = None,
        show_constraints: JSON | None = None,
        show_projected: JSON | None = None,
        show_construction: JSON | None = None,
        grid: JSON | None = None,
        snap: JSON | None = None,
        slice: JSON | None = None,
        sketch_3d: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sketch Palette Options.

        `sketch.options`.

        any of show_profile

        Arguments:
        * `sketch` (`SketchOptionsSketch | None`):
          id|name (default active)
        * `show_points` (`JSON | None`):
          (required) See SolidCraft.
        * `show_dimensions` (`JSON | None`):
          (required) See SolidCraft.
        * `show_constraints` (`JSON | None`):
          (required) See SolidCraft.
        * `show_projected` (`JSON | None`):
          (required) See SolidCraft.
        * `show_construction` (`JSON | None`):
          (required) See SolidCraft.
        * `grid` (`JSON | None`):
          (required) See SolidCraft.
        * `snap` (`JSON | None`):
          (required) See SolidCraft.
        * `slice` (`JSON | None`):
          (required) See SolidCraft.
        * `sketch_3d` (`bool | None`):
          (required) bool.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns them all

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.options",
            {
                "sketch": sketch,
                "show_points": show_points,
                "show_dimensions": show_dimensions,
                "show_constraints": show_constraints,
                "show_projected": show_projected,
                "show_construction": show_construction,
                "grid": grid,
                "snap": snap,
                "slice": slice,
                "sketch_3d": sketch_3d,
                **extra,
            },
        )

    # Method `SCSketchCommands.paste()`:
    def paste(
        self,
        *,
        at: Point2D | None = None,
        translate: Point2D | None = None,
        sketch: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Paste Sketch Entities.

        `sketch.paste`.

        without either, offset from the original in its own sketch and
        at the same coordinates in another

        Arguments:
        * `at` (`Point2D | None`):
          [x, y] (sketch point the copy's centre goes to)
        * `translate` (`Point2D | None`):
          [x, y]
        * `sketch` (`JSON | None`):
          target (default: the active sketch)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.paste",
            {
                "at": at,
                "translate": translate,
                "sketch": sketch,
                **extra,
            },
        )

    # Method `SCSketchCommands.pattern_circular()`:
    def pattern_circular(
        self,
        *,
        entities: JSON | None = None,
        center: JSON | None = None,
        count: JSON | None = None,
        angle: JSON | None = None,
        alignment: SketchPatternCircularAlignment | None = None,
        reversed: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Circular Pattern.

        `sketch.pattern.circular`.

        reversed flips the direction and extra side for even totals.
        Partial arcs span angle with angle/(count-1) spacing; full turns
        use angle/count. Adds associative pattern constraints; a
        coordinate center creates a constrainable point.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [ids]
        * `center` (`JSON | None`):
          (required) [x,y] or point ref
        * `count` (`JSON | None`):
          (required) 2…500
        * `angle` (`JSON | None`):
          total deg (default 360)
        * `alignment` (`SketchPatternCircularAlignment | None`):
          left|center|right (default right)
        * `reversed` (`bool | None`):
          bool (default false). Quantity includes the original. Center
          balances copies around it
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns pattern and center ids. pattern?: existing
          pattern id to edit (omitted values retained; surviving
          instance ids retained).; Returns created: {points, curves,
          constraints, dimensions}: the ids of what it added (stable and
          never reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.pattern.circular",
            {
                "entities": entities,
                "center": center,
                "count": count,
                "angle": angle,
                "alignment": alignment,
                "reversed": reversed,
                **extra,
            },
        )

    # Method `SCSketchCommands.pattern_rectangular()`:
    def pattern_rectangular(
        self,
        *,
        entities: JSON | None = None,
        count: JSON | None = None,
        spacing: JSON | None = None,
        count2: JSON | None = None,
        spacing2: JSON | None = None,
        direction: JSON | None = None,
        direction2: JSON | None = None,
        dir: JSON | None = None,
        dir2: Point2D | None = None,
        alignment: JSON | None = None,
        alignment2: SketchPatternRectangularAlignment2 | None = None,
        reversed2: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rectangular Pattern.

        `sketch.pattern.rectangular`.

        reverses placement and the extra side of even centered totals.
        Quantities include the original. Adds associative pattern
        constraints.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [ids]
        * `count` (`JSON | None`):
          (required) See SolidCraft.
        * `spacing` (`JSON | None`):
          (required) See SolidCraft.
        * `count2` (`JSON | None`):
          See SolidCraft.
        * `spacing2` (`JSON | None`):
          See SolidCraft.
        * `direction` (`JSON | None`):
          See SolidCraft.
        * `direction2` (`JSON | None`):
          sketch line ids (live references)
        * `dir` (`JSON | None`):
          See SolidCraft.
        * `dir2` (`Point2D | None`):
          [x,y] vectors (defaults: sketch x, perpendicular to direction
          1)
        * `alignment` (`JSON | None`):
          See SolidCraft.
        * `alignment2` (`SketchPatternRectangularAlignment2 | None`):
          left|center|right (default right). Signed spacings reverse
          each direction. reversed?
        * `reversed2` (`bool | None`):
          bool (default false)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns pattern id. pattern?: existing pattern id to
          edit (omitted values retained; surviving instance ids
          retained).; Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.pattern.rectangular",
            {
                "entities": entities,
                "count": count,
                "spacing": spacing,
                "count2": count2,
                "spacing2": spacing2,
                "direction": direction,
                "direction2": direction2,
                "dir": dir,
                "dir2": dir2,
                "alignment": alignment,
                "alignment2": alignment2,
                "reversed2": reversed2,
                **extra,
            },
        )

    # Method `SCSketchCommands.point()`:
    def point(
        self,
        *,
        point: Point2D | None = None,
        id: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Point.

        `sketch.point`.

        Arguments:
        * `point` (`Point2D | None`):
          (required) [x,y] (each a number or an expression over the
          design's parameters: the point is then fixed where it comes to
          and follows them)
        * `id` (`JSON | None`):
          See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.point",
            {
                "point": point,
                "id": id,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.point3d()`:
    def point3d(
        self,
        *,
        point: Point3D | None = None,
        **extra: JSON,
    ) -> JSON:
        """3D Point.

        `sketch.point3d`.

        Arguments:
        * `point` (`Point3D | None`):
          (required) [x,y,z] world point (needs 3D Sketch on).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.point3d",
            {
                "point": point,
                **extra,
            },
        )

    # Method `SCSketchCommands.polygon_circumscribed()`:
    def polygon_circumscribed(
        self,
        *,
        center: JSON | None = None,
        radius: JSON | None = None,
        sides: JSON | None = None,
        angle: Expr | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Circumscribed Polygon.

        `sketch.polygon.circumscribed`.

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `radius` (`JSON | None`):
          (required) (to edge midpoints)
        * `sides` (`JSON | None`):
          (required) See SolidCraft.
        * `angle` (`Expr | None`):
          deg
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.polygon.circumscribed",
            {
                "center": center,
                "radius": radius,
                "sides": sides,
                "angle": angle,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.polygon_edge()`:
    def polygon_edge(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        sides: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edge Polygon.

        `sketch.polygon.edge`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) one edge
        * `sides` (`JSON | None`):
          (required) See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.polygon.edge",
            {
                "p0": p0,
                "p1": p1,
                "sides": sides,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.polygon_inscribed()`:
    def polygon_inscribed(
        self,
        *,
        center: JSON | None = None,
        radius: JSON | None = None,
        sides: JSON | None = None,
        angle: Expr | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inscribed Polygon.

        `sketch.polygon.inscribed`.

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `radius` (`JSON | None`):
          (required) (to vertices)
        * `sides` (`JSON | None`):
          (required) See SolidCraft.
        * `angle` (`Expr | None`):
          deg
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.polygon.inscribed",
            {
                "center": center,
                "radius": radius,
                "sides": sides,
                "angle": angle,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.project()`:
    def project(
        self,
        *,
        refs: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Project.

        `sketch.project`.

        Arguments:
        * `refs` (`JSON | None`):
          (required) [{edge: [x,y,z], body?} | {face: [x,y,z], body?}
          (its edge loops) | {body: name} (silhouette) | {vertex:
          [x,y,z], body?} | {sketch, curve} | {sketch, point} | "origin"
          | {axis: X|Y|Z} | {plane: XY|XZ|YZ|name}].
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.project",
            {
                "refs": refs,
                **extra,
            },
        )

    # Method `SCSketchCommands.project_to_surface()`:
    def project_to_surface(
        self,
        *,
        curves: JSON | None = None,
        face: Point3D | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Project To Surface.

        `sketch.project_to_surface`.

        as linked 3D curves.

        Arguments:
        * `curves` (`JSON | None`):
          (required) [{sketch, curve}…] (curves of other sketches)
        * `face` (`Point3D | None`):
          (required) [x,y,z] point on the target face
        * `body` (`JSON | None`):
          projected along the active sketch's normal onto the face
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.project_to_surface",
            {
                "curves": curves,
                "face": face,
                "body": body,
                **extra,
            },
        )

    # Method `SCSketchCommands.rectangle_center()`:
    def rectangle_center(
        self,
        *,
        center: JSON | None = None,
        corner: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center Rectangle.

        `sketch.rectangle.center`.

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `corner` (`JSON | None`):
          (required) See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns sides {bottom, right, top, left} (line ids)
          and corners {bottom_left, bottom_right, top_right, top_left}
          (point ids); Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.rectangle.center",
            {
                "center": center,
                "corner": corner,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.rectangle_rounded()`:
    def rectangle_rounded(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        radius: Expr | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rounded Rectangle.

        `sketch.rectangle.rounded`.

        construction?. A 2-point rectangle whose four corners are
        filleted alike: one radius dimension (`param`), the other arcs
        equal to it.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) opposite corners [x,y]
        * `radius` (`Expr | None`):
          (required) expr (the corner radius, less than half the shorter
          side)
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns sides {bottom, right, top, left} (line ids)
          and arcs (the corner arcs: bottom-left, bottom-right,
          top-right, top-left); Returns created: {points, curves,
          constraints, dimensions}: the ids of what it added (stable and
          never reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.rectangle.rounded",
            {
                "p0": p0,
                "p1": p1,
                "radius": radius,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.rectangle_three_point()`:
    def rectangle_three_point(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        p2: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """3-Point Rectangle.

        `sketch.rectangle.three_point`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) first edge
        * `p2` (`JSON | None`):
          (required) point on the opposite edge
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.rectangle.three_point",
            {
                "p0": p0,
                "p1": p1,
                "p2": p2,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.rectangle_two_point()`:
    def rectangle_two_point(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        construction: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """2-Point Rectangle.

        `sketch.rectangle.two_point`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) opposite corners [x,y]
        * `construction` (`JSON | None`):
          See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns sides {bottom, right, top, left} (line ids)
          and corners {bottom_left, bottom_right, top_right, top_left}
          (point ids); Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.rectangle.two_point",
            {
                "p0": p0,
                "p1": p1,
                "construction": construction,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.redefine()`:
    def redefine(
        self,
        *,
        sketch: JSON | None = None,
        plane: JSON | None = None,
        author_path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Redefine Sketch Plane.

        `sketch.redefine`.

        explicitly rebinds or freezes the plane while preserving
        geometry and dimension names

        Arguments:
        * `sketch` (`JSON | None`):
          (required) id or name
        * `plane` (`JSON | None`):
          (required) as sketch.create
        * `author_path` (`JSON | None`):
          exact owner occurrence ids
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.redefine",
            {
                "sketch": sketch,
                "plane": plane,
                "author_path": author_path,
                **extra,
            },
        )

    # Method `SCSketchCommands.scale()`:
    def scale(
        self,
        *,
        entities: JSON | None = None,
        base: JSON | None = None,
        factor: float | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sketch Scale.

        `sketch.scale`.

        Arguments:
        * `entities` (`JSON | None`):
          (required) [curve/point ids]
        * `base` (`JSON | None`):
          (required) [x,y] or point ref
        * `factor` (`float | None`):
          (required) number
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.scale",
            {
                "entities": entities,
                "base": base,
                "factor": factor,
                **extra,
            },
        )

    # Method `SCSketchCommands.slot_arc_center()`:
    def slot_arc_center(
        self,
        *,
        center: JSON | None = None,
        start: JSON | None = None,
        end: JSON | None = None,
        width: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center Point Arc Slot.

        `sketch.slot.arc_center`.

        Arguments:
        * `center` (`JSON | None`):
          (required) See SolidCraft.
        * `start` (`JSON | None`):
          (required) centre arc start
        * `end` (`JSON | None`):
          (required) direction of the centre arc end (counter-clockwise)
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.slot.arc_center",
            {
                "center": center,
                "start": start,
                "end": end,
                "width": width,
                **extra,
            },
        )

    # Method `SCSketchCommands.slot_arc_three_point()`:
    def slot_arc_three_point(
        self,
        *,
        start: JSON | None = None,
        through: JSON | None = None,
        end: JSON | None = None,
        width: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Three Point Arc Slot.

        `sketch.slot.arc_three_point`.

        Arguments:
        * `start` (`JSON | None`):
          (required) See SolidCraft.
        * `through` (`JSON | None`):
          (required) See SolidCraft.
        * `end` (`JSON | None`):
          (required) points on the centre arc
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.slot.arc_three_point",
            {
                "start": start,
                "through": through,
                "end": end,
                "width": width,
                **extra,
            },
        )

    # Method `SCSketchCommands.slot_center_point()`:
    def slot_center_point(
        self,
        *,
        center: JSON | None = None,
        end: JSON | None = None,
        width: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center Point Slot.

        `sketch.slot.center_point`.

        Arguments:
        * `center` (`JSON | None`):
          (required) slot centre
        * `end` (`JSON | None`):
          (required) one arc centre
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.slot.center_point",
            {
                "center": center,
                "end": end,
                "width": width,
                **extra,
            },
        )

    # Method `SCSketchCommands.slot_center_to_center()`:
    def slot_center_to_center(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        width: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Center to Center Slot.

        `sketch.slot.center_to_center`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) arc centres
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.slot.center_to_center",
            {
                "p0": p0,
                "p1": p1,
                "width": width,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.slot_overall()`:
    def slot_overall(
        self,
        *,
        p0: JSON | None = None,
        p1: JSON | None = None,
        width: JSON | None = None,
        connect: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Overall Slot.

        `sketch.slot.overall`.

        Arguments:
        * `p0` (`JSON | None`):
          (required) See SolidCraft.
        * `p1` (`JSON | None`):
          (required) overall ends
        * `width` (`JSON | None`):
          (required) See SolidCraft.
        * `connect` (`bool | None`):
          bool (default true: a new point landing exactly on an existing
          point, the origin too, is made coincident with it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.slot.overall",
            {
                "p0": p0,
                "p1": p1,
                "width": width,
                "connect": connect,
                **extra,
            },
        )

    # Method `SCSketchCommands.snap()`:
    def snap(
        self,
        *,
        at: Point2D | None = None,
        from_: Point2D | None = None,
        radius: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Snap Inference.

        `sketch.snap`.

        Arguments:
        * `at` (`Point2D | None`):
          (required) [x,y]
        * `from_` (`Point2D | None`):
          [x,y] (previous click) (sent as `from`)
        * `radius` (`Expr | None`):
          mm (snap distance, default 1): what a click there would snap
          to and infer
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.snap",
            {
                "at": at,
                "from": from_,
                "radius": radius,
                **extra,
            },
        )

    # Method `SCSketchCommands.solve()`:
    def solve(
        self,
        **extra: JSON,
    ) -> JSON:
        """Solve Sketch.

        `sketch.solve`.

        reports the solver status and degrees of freedom

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.solve",
            {
                **extra,
            },
        )

    # Method `SCSketchCommands.spline_control_point()`:
    def spline_control_point(
        self,
        *,
        points: JSON | None = None,
        cubic: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Control Point Spline.

        `sketch.spline.control_point`.

        Arguments:
        * `points` (`JSON | None`):
          (required) control points (2…500)
        * `cubic` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.spline.control_point",
            {
                "points": points,
                "cubic": cubic,
                **extra,
            },
        )

    # Method `SCSketchCommands.spline_control_point_5()`:
    def spline_control_point_5(
        self,
        *,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Control Point Spline (Degree 5).

        `sketch.spline.control_point_5`.

        degree 5.

        Arguments:
        * `points` (`JSON | None`):
          (required) control points (2…500)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.spline.control_point_5",
            {
                "points": points,
                **extra,
            },
        )

    # Method `SCSketchCommands.spline_fit_point()`:
    def spline_fit_point(
        self,
        *,
        points: JSON | None = None,
        periodic: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fit Point Spline.

        `sketch.spline.fit_point`.

        periodic cubic fit closes smoothly through at least 3 distinct
        samples.

        Arguments:
        * `points` (`JSON | None`):
          (required) [[x,y] or point refs…] (2…500): the spline passes
          through them
        * `periodic` (`JSON | None`):
          boolean (default false)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.spline.fit_point",
            {
                "points": points,
                "periodic": periodic,
                **extra,
            },
        )

    # Method `SCSketchCommands.spline3d()`:
    def spline3d(
        self,
        *,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """3D Spline.

        `sketch.spline3d`.

        Arguments:
        * `points` (`JSON | None`):
          (required) [[x,y,z]…] world fit points (2 or more): a smooth
          3D curve through them (needs 3D Sketch on).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.spline3d",
            {
                "points": points,
                **extra,
            },
        )

    # Method `SCSketchCommands.spun_profile()`:
    def spun_profile(
        self,
        *,
        body: JSON | None = None,
        axis: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Spun Profile.

        `sketch.spun_profile`.

        in the sketch plane.

        Arguments:
        * `body` (`JSON | None`):
          (required) name
        * `axis` (`JSON | None`):
          (required) a line of the active sketch (curve id) | X|Y|Z: the
          body's outline revolved about the axis
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.spun_profile",
            {
                "body": body,
                "axis": axis,
                **extra,
            },
        )

    # Method `SCSketchCommands.text()`:
    def text(
        self,
        *,
        text: JSON | None = None,
        at: JSON | None = None,
        height: JSON | None = None,
        angle: Expr | None = None,
        font: JSON | None = None,
        bold: JSON | None = None,
        italic: bool | None = None,
        align: SketchTextAlign | None = None,
        letter_spacing: JSON | None = None,
        line_spacing: JSON | None = None,
        path: JSON | None = None,
        reverse: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Text.

        `sketch.text`.

        at's x and y, height and angle each take a number or an
        expression over the design's parameters as a string
        ("plate_width / 2", "label_size"): the text keeps the
        expression, follows the parameters, and returns it in `exprs`;
        an expression naming no parameter is the number it comes to, a
        bare number in one is in the design's units, a .ttf/.otf file
        path (~ and %VAR% expand; default: the built-in Liberation Sans)

        Arguments:
        * `text` (`JSON | None`):
          (required) string (\\n breaks lines)
        * `at` (`JSON | None`):
          (required) baseline start [x,y]
        * `height` (`JSON | None`):
          capital height mm (default 5)
        * `angle` (`Expr | None`):
          deg
        * `font` (`JSON | None`):
          an installed font's family or full name
        * `bold` (`JSON | None`):
          See SolidCraft.
        * `italic` (`bool | None`):
          bool (an installed family's bold or italic face; italic
          without one is slanted)
        * `align` (`SketchTextAlign | None`):
          left|center|right (the lines against `at`, or along the path)
        * `letter_spacing` (`JSON | None`):
          extra mm between letters
        * `line_spacing` (`JSON | None`):
          times the font's line distance (default 1)
        * `path` (`JSON | None`):
          a curve id of the sketch the baseline follows ("": none; `at`
          and `angle` then do not place the text; the curve becomes
          construction, a guide the letters stand on)
        * `reverse` (`bool | None`):
          bool (the other way along the path).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.text",
            {
                "text": text,
                "at": at,
                "height": height,
                "angle": angle,
                "font": font,
                "bold": bold,
                "italic": italic,
                "align": align,
                "letter_spacing": letter_spacing,
                "line_spacing": line_spacing,
                "path": path,
                "reverse": reverse,
                **extra,
            },
        )

    # Method `SCSketchCommands.toggle_driven()`:
    def toggle_driven(
        self,
        *,
        constraint: JSON | None = None,
        driven: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Toggle Driven Dimension.

        `sketch.toggle_driven`.

        a driving dimension gets a parameter with its current value

        Arguments:
        * `constraint` (`JSON | None`):
          (required) dimension id
        * `driven` (`bool | None`):
          bool (default toggles)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.toggle_driven",
            {
                "constraint": constraint,
                "driven": driven,
                **extra,
            },
        )

    # Method `SCSketchCommands.trim()`:
    def trim(
        self,
        *,
        curve: JSON | None = None,
        at: Point2D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Trim.

        `sketch.trim`.

        Arguments:
        * `curve` (`JSON | None`):
          (required) id
        * `at` (`Point2D | None`):
          (required) [x,y] (the piece to remove: between the nearest
          intersections around it).
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): Returns created: {points, curves, constraints,
          dimensions}: the ids of what it added (stable and never
          reused: usable right away in sketch.dimension,
          sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.trim",
            {
                "curve": curve,
                "at": at,
                **extra,
            },
        )

    # Method `SCSketchCommands.trim_path()`:
    def trim_path(
        self,
        *,
        points: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Trim Along Path.

        `sketch.trim.path`.

        in the order the path crosses them; a piece crossed again after
        it is gone is not trimmed twice; projected geometry, infinite
        lines, offset outputs and pieces trim refuses are passed over
        (why in `skipped`). dry_run?: bool (report without changing the
        design). One undo step

        Arguments:
        * `points` (`JSON | None`):
          (required) [[x,y]…] (2…2000 positions: a path drawn across the
          sketch). Every piece the path crosses is removed as
          `sketch.trim` removes the piece at that crossing
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): trimmed: [each trim's result], removed: [[[x,y]…]]
          (each removed piece as a polyline). Returns created: {points,
          curves, constraints, dimensions}: the ids of what it added
          (stable and never reused: usable right away in
          sketch.dimension, sketch.constraint.*, sketch.delete…)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "sketch.trim.path",
            {
                "points": points,
                **extra,
            },
        )


# Class `SCSolidCommands`:
@dataclass(slots=True)
class SCSolidCommands(SCNamespace):
    """The `solid.*` commands.

    Constructor:
    * `SCSolidCommands(transport)`
    """

    # Method `SCSolidCommands.align()`:
    def align(
        self,
        *,
        bodies: JSON | None = None,
        from_: JSON | None = None,
        from_face: Point3D | None = None,
        from_plane: JSON | None = None,
        to: JSON | None = None,
        to_face: Point3D | None = None,
        to_plane: JSON | None = None,
        flip: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Align.

        `solid.align`.

        faces and planes also turn to meet

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `from_` (`JSON | None`):
          (required) [x,y,z] | "origin" | {snap:
          vertex|edge_mid|face_center|circle_center, at: [x,y,z]} (sent
          as `from`)
        * `from_face` (`Point3D | None`):
          [x,y,z]
        * `from_plane` (`JSON | None`):
          XY|XZ|YZ|construction or offset plane name or id|{origin,
          normal}
        * `to` (`JSON | None`):
          (required) (the same)
        * `to_face` (`Point3D | None`):
          [x,y,z]
        * `to_plane` (`JSON | None`):
          (a plane as from_plane; the point or face goes onto it along
          its normal, and the plane may move later: the bodies follow)
        * `flip` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.align",
            {
                "bodies": bodies,
                "from": from_,
                "from_face": from_face,
                "from_plane": from_plane,
                "to": to,
                "to_face": to_face,
                "to_plane": to_plane,
                "flip": flip,
                **extra,
            },
        )

    # Method `SCSolidCommands.boundary_fill()`:
    def boundary_fill(
        self,
        *,
        tools: JSON | None = None,
        cells: JSON | None = None,
        operation: SolidBoundaryFillOperation | None = None,
        remove_tools: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Boundary Fill.

        `solid.boundary_fill`.

        Arguments:
        * `tools` (`JSON | None`):
          (required) [bodies]
        * `cells` (`JSON | None`):
          (required) [[x,y,z] a point inside each cell to fill (a cell:
          inside some tools, outside the rest)]
        * `operation` (`SolidBoundaryFillOperation | None`):
          new|join|cut|intersect
        * `remove_tools` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.boundary_fill",
            {
                "tools": tools,
                "cells": cells,
                "operation": operation,
                "remove_tools": remove_tools,
                **extra,
            },
        )

    # Method `SCSolidCommands.bounding_solid()`:
    def bounding_solid(
        self,
        *,
        bodies: JSON | None = None,
        margin: Expr | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Bounding Solid.

        `solid.bounding_solid`.

        Arguments:
        * `bodies` (`JSON | None`):
          [names] (default: all)
        * `margin` (`Expr | None`):
          expr
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.bounding_solid",
            {
                "bodies": bodies,
                "margin": margin,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.box()`:
    def box(
        self,
        length: Expr,
        width: Expr,
        height: Expr,
        *,
        body_name: str | None = None,
        body_names: Sequence[str] | None = None,
        center: Sequence[Expr] | None = None,
        corner: Sequence[Expr] | None = None,
        name: str | None = None,
        operation: Operation | None = None,
        participants: Sequence[str] | None = None,
        targets: Sequence[str] | None = None,
        **extra: JSON,
    ) -> JSON:
        """Box.

        `solid.box`.

        Arguments:
        * `length` (`Expr`):
          (required) Size along X.
        * `width` (`Expr`):
          (required) Size along Y.
        * `height` (`Expr`):
          (required) Size along Z.
        * `body_name` (`str | None`):
          The new body's name.
        * `body_names` (`Sequence[str] | None`):
          Names for the new bodies, in order.
        * `center` (`Sequence[Expr] | None`):
          The box's centre, instead of `corner`.
        * `corner` (`Sequence[Expr] | None`):
          The box's minimum corner. Default: the origin. When both
          `corner` and `center` are given, `corner` is used.
        * `name` (`str | None`):
          The feature's name in the timeline.
        * `operation` (`Operation | None`):
          How the box combines with existing bodies. Default: new.
        * `participants` (`Sequence[str] | None`):
          The bodies taking part (the same as `targets` for a
          primitive).
        * `targets` (`Sequence[str] | None`):
          The bodies a join, cut or intersect works on. Default: the
          bodies the box meets.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.box",
            {
                "length": length,
                "width": width,
                "height": height,
                "body_name": body_name,
                "body_names": body_names,
                "center": center,
                "corner": corner,
                "name": name,
                "operation": operation,
                "participants": participants,
                "targets": targets,
                **extra,
            },
        )

    # Method `SCSolidCommands.chamfer()`:
    def chamfer(
        self,
        *,
        edges: JSON | None = None,
        distance: Expr | None = None,
        distance2: Expr | None = None,
        angle: Expr | None = None,
        flip: bool | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Chamfer.

        `solid.chamfer`.

        Arguments:
        * `edges` (`JSON | None`):
          (required) [[x,y,z] | {body, index}]
        * `distance` (`Expr | None`):
          (required) expr
        * `distance2` (`Expr | None`):
          expr (along the second face)
        * `angle` (`Expr | None`):
          expr (from the first face)
        * `flip` (`bool | None`):
          bool (which face is first: by default the one facing up most)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.chamfer",
            {
                "edges": edges,
                "distance": distance,
                "distance2": distance2,
                "angle": angle,
                "flip": flip,
                "body": body,
                **extra,
            },
        )

    # Method `SCSolidCommands.coil()`:
    def coil(
        self,
        *,
        diameter: JSON | None = None,
        height: JSON | None = None,
        pitch: JSON | None = None,
        section_size: JSON | None = None,
        section: SolidCoilSection | None = None,
        section_position: SolidCoilSectionPosition | None = None,
        base: Point3D | None = None,
        axis: JSON | None = None,
        start_angle: JSON | None = None,
        clockwise: bool | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Coil.

        `solid.coil`.

        two of revolutions (or turns)

        Arguments:
        * `diameter` (`JSON | None`):
          (required) See SolidCraft.
        * `height` (`JSON | None`):
          (required) See SolidCraft.
        * `pitch` (`JSON | None`):
          (required) See SolidCraft.
        * `section_size` (`JSON | None`):
          (required) See SolidCraft.
        * `section` (`SolidCoilSection | None`):
          circular|square
        * `section_position` (`SolidCoilSectionPosition | None`):
          inside|center|outside
        * `base` (`Point3D | None`):
          [x,y,z] (numbers in mm or length expressions; default: the
          origin)
        * `axis` (`JSON | None`):
          X|Y|Z|[x,y,z] (default Z)
        * `start_angle` (`JSON | None`):
          See SolidCraft.
        * `clockwise` (`bool | None`):
          bool
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.coil",
            {
                "diameter": diameter,
                "height": height,
                "pitch": pitch,
                "section_size": section_size,
                "section": section,
                "section_position": section_position,
                "base": base,
                "axis": axis,
                "start_angle": start_angle,
                "clockwise": clockwise,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.combine()`:
    def combine(
        self,
        *,
        target: JSON | None = None,
        tools: JSON | None = None,
        operation: SolidCombineOperation | None = None,
        keep_tools: bool | None = None,
        new_component: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Combine.

        `solid.combine`.

        Arguments:
        * `target` (`JSON | None`):
          (required) body
        * `tools` (`JSON | None`):
          (required) [body]
        * `operation` (`SolidCombineOperation | None`):
          join|cut|intersect
        * `keep_tools` (`bool | None`):
          bool
        * `new_component` (`bool | None`):
          bool (the result goes into a new component; component_name?)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.combine",
            {
                "target": target,
                "tools": tools,
                "operation": operation,
                "keep_tools": keep_tools,
                "new_component": new_component,
                **extra,
            },
        )

    # Method `SCSolidCommands.cylinder()`:
    def cylinder(
        self,
        *,
        height: Expr | None = None,
        base: Point3D | None = None,
        axis: JSON | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Cylinder.

        `solid.cylinder`.

        radius | diameter

        Arguments:
        * `height` (`Expr | None`):
          (required) expr
        * `base` (`Point3D | None`):
          [x,y,z] (centre of the bottom: numbers in mm or length
          expressions; default: the origin)
        * `axis` (`JSON | None`):
          X|Y|Z|[x,y,z] (default Z)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          [body]
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.cylinder",
            {
                "height": height,
                "base": base,
                "axis": axis,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.draft()`:
    def draft(
        self,
        *,
        faces: JSON | None = None,
        angle: Expr | None = None,
        neutral: JSON | None = None,
        pull: Point3D | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Draft.

        `solid.draft`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points, or face names from model.faces]
        * `angle` (`Expr | None`):
          (required) expr
        * `neutral` (`JSON | None`):
          (required) XY|XZ|YZ|plane name|{origin, normal}
        * `pull` (`Point3D | None`):
          [x,y,z] (default: neutral plane normal)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.draft",
            {
                "faces": faces,
                "angle": angle,
                "neutral": neutral,
                "pull": pull,
                "body": body,
                **extra,
            },
        )

    # Method `SCSolidCommands.emboss()`:
    def emboss(
        self,
        *,
        sketch: JSON | None = None,
        profiles: JSON | None = None,
        depth: JSON | None = None,
        mode: SolidEmbossMode | None = None,
        targets: JSON | None = None,
        face: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Emboss.

        `solid.emboss`.

        Arguments:
        * `sketch` (`JSON | None`):
          (required) See SolidCraft.
        * `profiles` (`JSON | None`):
          See SolidCraft.
        * `depth` (`JSON | None`):
          (required) See SolidCraft.
        * `mode` (`SolidEmbossMode | None`):
          emboss|deboss
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `face` (`JSON | None`):
          world point [x,y,z] selecting a planar or complete exterior
          cylindrical wall (inferred when exactly one supported tangent
          cylinder matches the selected profiles)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.emboss",
            {
                "sketch": sketch,
                "profiles": profiles,
                "depth": depth,
                "mode": mode,
                "targets": targets,
                "face": face,
                **extra,
            },
        )

    # Method `SCSolidCommands.extrude()`:
    def extrude(
        self,
        *,
        body: str | None = None,
        body_name: str | None = None,
        body_names: Sequence[str] | None = None,
        convention: ExtrudeConvention | None = None,
        curves: Sequence[str] | None = None,
        direction: Direction | None = None,
        distance: Expr | None = None,
        distance2: Expr | None = None,
        extent: ExtentKeyword | None = None,
        face: Point3D | None = None,
        face_body: str | None = None,
        faces: Sequence[Point3D] | None = None,
        from_: Point3D | None = None,
        name: str | None = None,
        operation: ExtrudeOperation | None = None,
        participants: Sequence[str] | None = None,
        profiles: SolidExtrudeProfiles | None = None,
        side: ThinSide | None = None,
        sketch: float | str | None = None,
        start_offset: Expr | None = None,
        taper: Expr | None = None,
        targets: Sequence[str] | None = None,
        thickness: Expr | None = None,
        thickness2: Expr | None = None,
        thin: bool | None = None,
        through_all: bool | None = None,
        to: Point3D | None = None,
        to_offset: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Extrude.

        `solid.extrude`.

        Arguments:
        * `body` (`str | None`):
          With `face`, among placed instances: the body whose placement
          `face` is read in (read by the engine's frame mapping, before
          the command runs). Default: `face_body`, else the body nearest
          the point.
        * `body_name` (`str | None`):
          The new body's name.
        * `body_names` (`Sequence[str] | None`):
          Names for the new bodies, in order.
        * `convention` (`ExtrudeConvention | None`):
          How a symmetric distance is read. Default: total_distance.
        * `curves` (`Sequence[str] | None`):
          With `thin`: the curves the wall follows. Default: every drawn
          curve of the sketch.
        * `direction` (`Direction | None`):
          Which way to extrude. Default: positive.
        * `distance` (`Expr | None`):
          How far: the length one way; with `direction: symmetric`, the
          total thickness (per side with `convention: legacy_per_side`);
          with `distance2`, the first side's length. Required unless
          `through_all` or `to` is given.
        * `distance2` (`Expr | None`):
          Two Sides: a second distance the other way from the first
          side, which may be `through_all` or `to`; with `direction:
          negative` the first side goes against the normal and
          `distance2` along it.
        * `extent` (`ExtentKeyword | None`):
          `"through_all"`, the same as `through_all: true`.
        * `face` (`Point3D | None`):
          A point on a planar body face to extrude instead of a sketch
          profile.
        * `face_body` (`str | None`):
          The body whose face to use, where faces of several bodies meet
          at `face` (or `faces`).
        * `faces` (`Sequence[Point3D] | None`):
          Several coplanar faces of one body to extrude together, by a
          point on each. Not with `face`, `sketch` or `profiles`.
        * `from_` (`Point3D | None`):
          Start at this face or point (From Object). (sent as `from`)
        * `name` (`str | None`):
          The feature's name in the timeline.
        * `operation` (`ExtrudeOperation | None`):
          How the extrusion combines with existing bodies. Default: new.
        * `participants` (`Sequence[str] | None`):
          The bodies taking part; overrides the default scope.
        * `profiles` (`SolidExtrudeProfiles | None`):
          Which of the sketch's profiles to extrude. Default: all of
          them. Ignored when `face` is given; not allowed with `thin`.
        * `side` (`ThinSide | None`):
          With `thin`: which side of the curves the wall lies on.
          Default: center.
        * `sketch` (`float | str | None`):
          The sketch to extrude, by id or name. Default: the active
          sketch, else the last one. Ignored when `face` is given.
        * `start_offset` (`Expr | None`):
          Start this far from the sketch plane, along its normal.
        * `taper` (`Expr | None`):
          Draft angle of the side walls.
        * `targets` (`Sequence[str] | None`):
          The bodies a join, cut or intersect works on. Default for a
          join from a body's face: that body.
        * `thickness` (`Expr | None`):
          With `thin`: the wall's thickness.
        * `thickness2` (`Expr | None`):
          With `thin` and `side: two_sides`: the thickness outside.
        * `thin` (`bool | None`):
          A thin wall along sketch curves instead of solid profiles.
        * `through_all` (`bool | None`):
          Extrude through everything in the way.
        * `to` (`Point3D | None`):
          Extrude up to this face, vertex or point (To Object).
        * `to_offset` (`Expr | None`):
          How far past `to` to go.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.extrude",
            {
                "body": body,
                "body_name": body_name,
                "body_names": body_names,
                "convention": convention,
                "curves": curves,
                "direction": direction,
                "distance": distance,
                "distance2": distance2,
                "extent": extent,
                "face": face,
                "face_body": face_body,
                "faces": faces,
                "from": from_,
                "name": name,
                "operation": operation,
                "participants": participants,
                "profiles": profiles,
                "side": side,
                "sketch": sketch,
                "start_offset": start_offset,
                "taper": taper,
                "targets": targets,
                "thickness": thickness,
                "thickness2": thickness2,
                "thin": thin,
                "through_all": through_all,
                "to": to,
                "to_offset": to_offset,
                **extra,
            },
        )

    # Method `SCSolidCommands.fillet()`:
    def fillet(
        self,
        *,
        edges: JSON | None = None,
        radius: Expr | None = None,
        body: JSON | None = None,
        type: JSON | None = None,
        radius2: JSON | None = None,
        start: Point3D | None = None,
        radii: JSON | None = None,
        knots: JSON | None = None,
        mid: JSON | None = None,
        smooth: bool | None = None,
        corner: SolidFilletCorner | None = None,
        fit: SolidFilletFit | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fillet.

        `solid.fillet`.

        Arguments:
        * `edges` (`JSON | None`):
          (required) [[x,y,z] point on edge | {body, index}]
        * `radius` (`Expr | None`):
          (required) expr
        * `body` (`JSON | None`):
          See SolidCraft.
        * `type` (`JSON | None`):
          constant|curvature (alias g2: curvature-continuous quintic
          between planar faces along straight edges, one planar end face
          at each end (including sloped ends); radius sets the
          equivalent circular setback, not constant curvature; exact fit
          only)|chord (radius is the width across)|variable (radius at
          the end nearest start, radius2 at the other; one end may be 0,
          where the round closes to the corner)|spline (the radius along
          the edge is a clamped B-spline from the end nearest start:
          radius is its first control radius, radii the rest, knots its
          knot vector from 0 to 1; one end may be 0)
        * `radius2` (`JSON | None`):
          See SolidCraft.
        * `start` (`Point3D | None`):
          [x,y,z]
        * `radii` (`JSON | None`):
          [expr, …]
        * `knots` (`JSON | None`):
          [number, …]
        * `mid` (`JSON | None`):
          [[position 0…1 from start, radius expr], …] (variable radii
          between the ends)
        * `smooth` (`bool | None`):
          bool (smooth instead of straight between the radii)
        * `corner` (`SolidFilletCorner | None`):
          rolling|g2 (rolling, the default: the corners where three
          blended edges meet are pieces of the rolling ball's sphere,
          tangent to each blend; g2: a patch repeating each blend's
          surface up to the second order, constant-radius exact fillets
          only, refused where it cannot be built)
        * `fit` (`SolidFilletFit | None`):
          exact|reduce|taper (exact, the default: a radius too large for
          the geometry around the edges is refused; reduce: where it
          doesn't fit it is reduced to the largest that does, one radius
          for edges sharing a face; the smallest used is returned as
          `radius_applied`, each edge's as `radii_applied: [{edge:
          [x,y,z], radius}]`, and noted in the feature's warning; taper:
          along each straight edge between planar faces where it doesn't
          fit, the radius follows the room there as a smooth spline,
          down to 0 where a face closes to a point, noted in the
          feature's warning)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.fillet",
            {
                "edges": edges,
                "radius": radius,
                "body": body,
                "type": type,
                "radius2": radius2,
                "start": start,
                "radii": radii,
                "knots": knots,
                "mid": mid,
                "smooth": smooth,
                "corner": corner,
                "fit": fit,
                **extra,
            },
        )

    # Method `SCSolidCommands.hole()`:
    def hole(
        self,
        *,
        position: JSON | None = None,
        flip: bool | None = None,
        single: bool | None = None,
        direction: Point3D | None = None,
        clearance: JSON | None = None,
        depth: JSON | None = None,
        to: Point3D | None = None,
        type: SolidHoleType | None = None,
        tip_angle: JSON | None = None,
        cb_diameter: JSON | None = None,
        cb_depth: JSON | None = None,
        cs_diameter: JSON | None = None,
        cs_angle: JSON | None = None,
        thread: JSON | None = None,
        targets: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Hole.

        `solid.hole`.

        diameter | thread (a tapped hole: the tap drill, major − pitch)

        Arguments:
        * `position` (`JSON | None`):
          (required) [x,y,z] on a face (numbers, or length expressions
          the hole follows) | sketch + points: [sketch point ids] (one
          hole each, perpendicular to the sketch, into the material on
          whichever side of the sketch plane it is) | sketch alone
          (every sketch point: standalone points and circle centres)
        * `flip` (`bool | None`):
          bool (sketch points: drill to the other side)
        * `single` (`bool | None`):
          bool (with one sketch point: a Single hole that follows the
          point, drilled into the face there)
        * `direction` (`Point3D | None`):
          [x,y,z] (default: into the face, against its outward normal;
          one that leaves the face is mirrored into it; ignored with
          sketch points unless single)
        * `clearance` (`JSON | None`):
          "M6" with fit?: close|normal|loose (ISO 273)
        * `depth` (`JSON | None`):
          (default through all)
        * `to` (`Point3D | None`):
          [x,y,z] (To Object: drill to that face or point)
        * `type` (`SolidHoleType | None`):
          simple|drilled|counterbore|countersink
        * `tip_angle` (`JSON | None`):
          See SolidCraft.
        * `cb_diameter` (`JSON | None`):
          See SolidCraft.
        * `cb_depth` (`JSON | None`):
          See SolidCraft.
        * `cs_diameter` (`JSON | None`):
          See SolidCraft.
        * `cs_angle` (`JSON | None`):
          See SolidCraft.
        * `thread` (`JSON | None`):
          "M6" (cosmetic)
        * `targets` (`JSON | None`):
          [body] (the bodies to drill; holes at the points of a sketch
          on a body's face default to that body, found along the holes'
          direction on it alone; explicit targets or participants
          override, ["*"] every body)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.hole",
            {
                "position": position,
                "flip": flip,
                "single": single,
                "direction": direction,
                "clearance": clearance,
                "depth": depth,
                "to": to,
                "type": type,
                "tip_angle": tip_angle,
                "cb_diameter": cb_diameter,
                "cb_depth": cb_depth,
                "cs_diameter": cs_diameter,
                "cs_angle": cs_angle,
                "thread": thread,
                "targets": targets,
                **extra,
            },
        )

    # Method `SCSolidCommands.loft()`:
    def loft(
        self,
        *,
        sections: JSON | None = None,
        rails: JSON | None = None,
        rail_fit: SolidLoftRailFit | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Loft.

        `solid.loft`.

        Arguments:
        * `sections` (`JSON | None`):
          (required) [{sketch, profiles?} | {sketch, point: id} (an
          apex)] (2…50, in order; matching hole counts, no holes at an
          apex)
        * `rails` (`JSON | None`):
          [{sketch, curves: [ids in order]}] (one or two guide rails
          from the first section to the last, through every section's
          outline: the loft follows them between the sections; not with
          sections that have holes)
        * `rail_fit` (`SolidLoftRailFit | None`):
          scale|stretch (default scale: with one rail the sections grow
          evenly with the rail's distance from their middle, with two
          with the distance between the rails; stretch: only that way)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.loft",
            {
                "sections": sections,
                "rails": rails,
                "rail_fit": rail_fit,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.mirror()`:
    def mirror(
        self,
        *,
        features: JSON | None = None,
        bodies: JSON | None = None,
        plane: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Mirror.

        `solid.mirror`.

        Arguments:
        * `features` (`JSON | None`):
          (required) [names]
        * `bodies` (`JSON | None`):
          [names] (combine?: join with the original)
        * `plane` (`JSON | None`):
          (required) XY|XZ|YZ|construction plane name or id|{origin,
          normal}|{origin, x_dir, y_dir} (origin coordinates may be
          length expressions; the mirror follows them, or a construction
          plane)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.mirror",
            {
                "features": features,
                "bodies": bodies,
                "plane": plane,
                **extra,
            },
        )

    # Method `SCSolidCommands.move()`:
    def move(
        self,
        *,
        bodies: JSON | None = None,
        translate: Point3D | None = None,
        axis: Point3D | None = None,
        angle: Expr | None = None,
        copy: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move/Copy.

        `solid.move`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `translate` (`Point3D | None`):
          [x,y,z] (exprs or numbers)
        * `axis` (`Point3D | None`):
          [x,y,z]
        * `angle` (`Expr | None`):
          expr
        * `copy` (`bool | None`):
          bool (default false: keeps the original bodies and transforms
          a new copy instead of moving them in place)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.move",
            {
                "bodies": bodies,
                "translate": translate,
                "axis": axis,
                "angle": angle,
                "copy": copy,
                **extra,
            },
        )

    # Method `SCSolidCommands.offset_face()`:
    def offset_face(
        self,
        *,
        faces: JSON | None = None,
        distance: Expr | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Offset Face.

        `solid.offset_face`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points on planar faces, or face names from
          model.faces]
        * `distance` (`Expr | None`):
          (required) expr (positive: outward)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.offset_face",
            {
                "faces": faces,
                "distance": distance,
                "body": body,
                **extra,
            },
        )

    # Method `SCSolidCommands.pattern_circular()`:
    def pattern_circular(
        self,
        *,
        features: JSON | None = None,
        bodies: JSON | None = None,
        components: JSON | None = None,
        axis: JSON | None = None,
        count: JSON | None = None,
        angle: JSON | None = None,
        alignment: SolidPatternCircularAlignment | None = None,
        reversed: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Circular Pattern.

        `solid.pattern.circular`.

        Arguments:
        * `features` (`JSON | None`):
          (required) [names]
        * `bodies` (`JSON | None`):
          [names]
        * `components` (`JSON | None`):
          [names]
        * `axis` (`JSON | None`):
          (required) X|Y|Z | construction axis name (followed when
          edited) | {origin, dir}
        * `count` (`JSON | None`):
          (required) See SolidCraft.
        * `angle` (`JSON | None`):
          (default 360 deg; partial arcs include both ends)
        * `alignment` (`SolidPatternCircularAlignment | None`):
          left|center|right (default right; original stays fixed)
        * `reversed` (`bool | None`):
          bool (Flip; selects the extra side for even centered counts)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.pattern.circular",
            {
                "features": features,
                "bodies": bodies,
                "components": components,
                "axis": axis,
                "count": count,
                "angle": angle,
                "alignment": alignment,
                "reversed": reversed,
                **extra,
            },
        )

    # Method `SCSolidCommands.pattern_path()`:
    def pattern_path(
        self,
        *,
        features: JSON | None = None,
        bodies: JSON | None = None,
        path_sketch: JSON | None = None,
        path: JSON | None = None,
        count: JSON | None = None,
        spacing: JSON | None = None,
        orientation: SolidPatternPathOrientation | None = None,
        flip: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Pattern on Path.

        `solid.pattern.path`.

        Arguments:
        * `features` (`JSON | None`):
          (required) [names]
        * `bodies` (`JSON | None`):
          [names]
        * `path_sketch` (`JSON | None`):
          (required) sketch
        * `path` (`JSON | None`):
          (required) [curve ids in order]
        * `count` (`JSON | None`):
          (required) See SolidCraft.
        * `spacing` (`JSON | None`):
          (required) (between instances) | distance (first to last)
        * `orientation` (`SolidPatternPathOrientation | None`):
          identical|path
        * `flip` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.pattern.path",
            {
                "features": features,
                "bodies": bodies,
                "path_sketch": path_sketch,
                "path": path,
                "count": count,
                "spacing": spacing,
                "orientation": orientation,
                "flip": flip,
                **extra,
            },
        )

    # Method `SCSolidCommands.pattern_rectangular()`:
    def pattern_rectangular(
        self,
        *,
        features: JSON | None = None,
        bodies: JSON | None = None,
        components: JSON | None = None,
        dir1: Point3D | None = None,
        count1: JSON | None = None,
        spacing1: JSON | None = None,
        dir2: JSON | None = None,
        count2: JSON | None = None,
        spacing2: JSON | None = None,
        alignment: JSON | None = None,
        alignment2: SolidPatternRectangularAlignment2 | None = None,
        reversed: JSON | None = None,
        reversed2: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rectangular Pattern.

        `solid.pattern.rectangular`.

        Arguments:
        * `features` (`JSON | None`):
          (required) [names]
        * `bodies` (`JSON | None`):
          [names]
        * `components` (`JSON | None`):
          [names]
        * `dir1` (`Point3D | None`):
          (required) [x,y,z]
        * `count1` (`JSON | None`):
          (required) See SolidCraft.
        * `spacing1` (`JSON | None`):
          (required) See SolidCraft.
        * `dir2` (`JSON | None`):
          See SolidCraft.
        * `count2` (`JSON | None`):
          See SolidCraft.
        * `spacing2` (`JSON | None`):
          See SolidCraft.
        * `alignment` (`JSON | None`):
          See SolidCraft.
        * `alignment2` (`SolidPatternRectangularAlignment2 | None`):
          left|center|right (default right; counts include the original)
        * `reversed` (`JSON | None`):
          See SolidCraft.
        * `reversed2` (`bool | None`):
          bool (Flip)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.pattern.rectangular",
            {
                "features": features,
                "bodies": bodies,
                "components": components,
                "dir1": dir1,
                "count1": count1,
                "spacing1": spacing1,
                "dir2": dir2,
                "count2": count2,
                "spacing2": spacing2,
                "alignment": alignment,
                "alignment2": alignment2,
                "reversed": reversed,
                "reversed2": reversed2,
                **extra,
            },
        )

    # Method `SCSolidCommands.pipe()`:
    def pipe(
        self,
        *,
        path_sketch: JSON | None = None,
        path: JSON | None = None,
        diameter: Expr | None = None,
        wall: Expr | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Pipe.

        `solid.pipe`.

        Arguments:
        * `path_sketch` (`JSON | None`):
          (required) sketch
        * `path` (`JSON | None`):
          (required) [curve ids in order]
        * `diameter` (`Expr | None`):
          (required) expr
        * `wall` (`Expr | None`):
          expr (hollow)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.pipe",
            {
                "path_sketch": path_sketch,
                "path": path,
                "diameter": diameter,
                "wall": wall,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.press_pull()`:
    def press_pull(
        self,
        *,
        face: Point3D | None = None,
        edges: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Press Pull.

        `solid.press_pull`.

        Arguments:
        * `face` (`Point3D | None`):
          (required) [x,y,z] and distance: expr (positive adds material,
          negative cuts)
        * `edges` (`JSON | None`):
          (required) [[x,y,z]…] and distance (a fillet)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.press_pull",
            {
                "face": face,
                "edges": edges,
                **extra,
            },
        )

    # Method `SCSolidCommands.remove()`:
    def remove(
        self,
        *,
        bodies: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Remove.

        `solid.remove`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names] (removed from here on in the timeline)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.remove",
            {
                "bodies": bodies,
                **extra,
            },
        )

    # Method `SCSolidCommands.replace_face()`:
    def replace_face(
        self,
        *,
        faces: JSON | None = None,
        target: JSON | None = None,
        target_face: Point3D | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Replace Face.

        `solid.replace_face`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points on planar faces, or face names from
          model.faces]
        * `target` (`JSON | None`):
          (required) plane (XY|XZ|YZ|construction plane|{origin,
          normal})
        * `target_face` (`Point3D | None`):
          [x,y,z] on a parallel planar face
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.replace_face",
            {
                "faces": faces,
                "target": target,
                "target_face": target_face,
                "body": body,
                **extra,
            },
        )

    # Method `SCSolidCommands.revolve()`:
    def revolve(
        self,
        *,
        axis: JSON | None = None,
        angle: Expr | None = None,
        angle2: Expr | None = None,
        direction: JSON | None = None,
        convention: SolidRevolveConvention | None = None,
        to: Point3D | None = None,
        sketch: JSON | None = None,
        profiles: JSON | None = None,
        face: Point3D | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Revolve.

        `solid.revolve`.

        Arguments:
        * `axis` (`JSON | None`):
          (required) sketch line id | x | y (sketch axes) | X|Y|Z
          (world) | construction axis name (followed when edited) |
          {origin, dir}
        * `angle` (`Expr | None`):
          expr (default 360 deg)
        * `angle2` (`Expr | None`):
          expr (Two Sides: the other side's angle)
        * `direction` (`JSON | None`):
          symmetric (angle split either side, independent of axis
          direction)
        * `convention` (`SolidRevolveConvention | None`):
          sketch_normal|legacy_axis_start (default sketch_normal; legacy
          retains older angular starts)
        * `to` (`Point3D | None`):
          [x,y,z] (To Object: turn until that face, vertex or point)
        * `sketch` (`JSON | None`):
          See SolidCraft.
        * `profiles` (`JSON | None`):
          See SolidCraft.
        * `face` (`Point3D | None`):
          [x,y,z] (a planar body face as the profile) and face_body?:
          name (whose face, where faces of several bodies meet)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.revolve",
            {
                "axis": axis,
                "angle": angle,
                "angle2": angle2,
                "direction": direction,
                "convention": convention,
                "to": to,
                "sketch": sketch,
                "profiles": profiles,
                "face": face,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.rib()`:
    def rib(
        self,
        *,
        sketch: JSON | None = None,
        curves: JSON | None = None,
        thickness: JSON | None = None,
        depth: JSON | None = None,
        flip: bool | None = None,
        direction: SolidRibDirection | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rib.

        `solid.rib`.

        Arguments:
        * `sketch` (`JSON | None`):
          (required) See SolidCraft.
        * `curves` (`JSON | None`):
          (required) [open curve ids, in order]
        * `thickness` (`JSON | None`):
          (required) (across the sketch plane, or across the curves when
          normal)
        * `depth` (`JSON | None`):
          (default: to the next face)
        * `flip` (`bool | None`):
          bool (fill to the other side)
        * `direction` (`SolidRibDirection | None`):
          in_plane|normal (grow across the sketch plane, the default, or
          along its normal)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.rib",
            {
                "sketch": sketch,
                "curves": curves,
                "thickness": thickness,
                "depth": depth,
                "flip": flip,
                "direction": direction,
                **extra,
            },
        )

    # Method `SCSolidCommands.scale()`:
    def scale(
        self,
        *,
        bodies: JSON | None = None,
        factor: Expr | None = None,
        factors: Point3D | None = None,
        origin: Point3D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Scale.

        `solid.scale`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names]
        * `factor` (`Expr | None`):
          (required) expr
        * `factors` (`Point3D | None`):
          [x, y, z] exprs
        * `origin` (`Point3D | None`):
          [x,y,z]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.scale",
            {
                "bodies": bodies,
                "factor": factor,
                "factors": factors,
                "origin": origin,
                **extra,
            },
        )

    # Method `SCSolidCommands.shell()`:
    def shell(
        self,
        *,
        faces: JSON | None = None,
        thickness: Expr | None = None,
        direction: SolidShellDirection | None = None,
        tangent_chain: bool | None = None,
        body: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Shell.

        `solid.shell`.

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points on the faces to remove, or face
          names from model.faces]
        * `thickness` (`Expr | None`):
          (required) expr
        * `direction` (`SolidShellDirection | None`):
          inside|outside|both
        * `tangent_chain` (`bool | None`):
          bool (also open faces joined smoothly to the picked ones)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.shell",
            {
                "faces": faces,
                "thickness": thickness,
                "direction": direction,
                "tangent_chain": tangent_chain,
                "body": body,
                **extra,
            },
        )

    # Method `SCSolidCommands.sphere()`:
    def sphere(
        self,
        *,
        radius: JSON | None = None,
        diameter: Expr | None = None,
        center: Point3D | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sphere.

        `solid.sphere`.

        Arguments:
        * `radius` (`JSON | None`):
          (required) See SolidCraft.
        * `diameter` (`Expr | None`):
          expr
        * `center` (`Point3D | None`):
          [x,y,z] (numbers in mm or length expressions; default: the
          origin)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          [body]
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.sphere",
            {
                "radius": radius,
                "diameter": diameter,
                "center": center,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.split_body()`:
    def split_body(
        self,
        *,
        body: JSON | None = None,
        plane: JSON | None = None,
        tool: JSON | None = None,
        sketch: JSON | None = None,
        line: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Split Body.

        `solid.split_body`.

        Arguments:
        * `body` (`JSON | None`):
          (required) name
        * `plane` (`JSON | None`):
          (required) XY|XZ|YZ|plane name|{origin, normal} —
        * `tool` (`JSON | None`):
          {body, point} (a face of a body, its surface extended) —
        * `sketch` (`JSON | None`):
          id
        * `line` (`JSON | None`):
          (required) curve id (a straight sketch line, along the
          sketch's normal)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.split_body",
            {
                "body": body,
                "plane": plane,
                "tool": tool,
                "sketch": sketch,
                "line": line,
                **extra,
            },
        )

    # Method `SCSolidCommands.split_face()`:
    def split_face(
        self,
        *,
        faces: JSON | None = None,
        body: JSON | None = None,
        tool: JSON | None = None,
        sketch: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Split Face.

        `solid.split_face`.

        and the splitting tool: plane: XY|XZ|YZ|plane name|{origin,
        normal} — or

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z] points on the faces to split, or face
          names from model.faces]
        * `body` (`JSON | None`):
          See SolidCraft.
        * `tool` (`JSON | None`):
          {body, point} (a face of a body, its surface extended) —
        * `sketch` (`JSON | None`):
          id or name (its curves, along the sketch's normal)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.split_face",
            {
                "faces": faces,
                "body": body,
                "tool": tool,
                "sketch": sketch,
                **extra,
            },
        )

    # Method `SCSolidCommands.sweep()`:
    def sweep(
        self,
        *,
        sketch: JSON | None = None,
        profiles: JSON | None = None,
        path_sketch: JSON | None = None,
        path: JSON | None = None,
        orientation: JSON | None = None,
        twist: Expr | None = None,
        scale: Expr | None = None,
        rails: JSON | None = None,
        rail_fit: JSON | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Sweep.

        `solid.sweep`.

        Arguments:
        * `sketch` (`JSON | None`):
          (required) profile sketch
        * `profiles` (`JSON | None`):
          See SolidCraft.
        * `path_sketch` (`JSON | None`):
          (required) sketch
        * `path` (`JSON | None`):
          (required) [curve ids in order]
        * `orientation` (`JSON | None`):
          perpendicular (default: square to the path, turning with it) |
          parallel (as drawn: the profile moves without turning; the
          path must keep crossing its plane) | [x,y,z] (square to the
          path, its turn about the path fixed by this direction)
        * `twist` (`Expr | None`):
          angle expr (the profile turns this much about the path over
          its length; within 4 turns)
        * `scale` (`Expr | None`):
          expr (the profile's scale at the end, linear along the path;
          0.01…100)
        * `rails` (`JSON | None`):
          [{sketch?: sketch (default path_sketch), curves: [curve ids in
          order]}] (guide rails, one or two, each meeting every plane
          square to the path once along it, from the end nearest the
          path's start: one rail turns the profile so its point where
          the rail starts stays on the rail and scales it with the
          rail's distance from the path; two rails carry it between
          them, its points where they start staying on both; rails take
          the default orientation, no twist and no scale, and a path
          without sharp corners)
        * `rail_fit` (`JSON | None`):
          scale (default: the profile grows and shrinks evenly) |
          stretch (only across to the rail, between the rails)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.sweep",
            {
                "sketch": sketch,
                "profiles": profiles,
                "path_sketch": path_sketch,
                "path": path,
                "orientation": orientation,
                "twist": twist,
                "scale": scale,
                "rails": rails,
                "rail_fit": rail_fit,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.thread()`:
    def thread(
        self,
        *,
        face: Point3D | None = None,
        designation: JSON | None = None,
        length: Expr | None = None,
        modeled: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Thread.

        `solid.thread`.

        model.threads lists it. Modeled: cuts the thread profile into
        the body; a shaft thicker than the thread is first turned down
        to its major diameter over the threaded length

        Arguments:
        * `face` (`Point3D | None`):
          (required) [x,y,z] on a cylindrical face
        * `designation` (`JSON | None`):
          ISO metric ("M8", "M8x1"; default: the size that fits)
        * `length` (`Expr | None`):
          expr (default: the whole face)
        * `modeled` (`bool | None`):
          bool (default false). Cosmetic: the model is unchanged
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.thread",
            {
                "face": face,
                "designation": designation,
                "length": length,
                "modeled": modeled,
                **extra,
            },
        )

    # Method `SCSolidCommands.torus()`:
    def torus(
        self,
        *,
        major: JSON | None = None,
        minor: Expr | None = None,
        center: Point3D | None = None,
        operation: JSON | None = None,
        targets: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Torus.

        `solid.torus`.

        Arguments:
        * `major` (`JSON | None`):
          (required) See SolidCraft.
        * `minor` (`Expr | None`):
          (required) expr (radii)
        * `center` (`Point3D | None`):
          [x,y,z] (numbers in mm or length expressions; default: the
          origin)
        * `operation` (`JSON | None`):
          See SolidCraft.
        * `targets` (`JSON | None`):
          [body]
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.torus",
            {
                "major": major,
                "minor": minor,
                "center": center,
                "operation": operation,
                "targets": targets,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSolidCommands.web()`:
    def web(
        self,
        *,
        sketch: JSON | None = None,
        curves: JSON | None = None,
        thickness: JSON | None = None,
        depth: JSON | None = None,
        flip: bool | None = None,
        direction: SolidWebDirection | None = None,
        **extra: JSON,
    ) -> JSON:
        """Web.

        `solid.web`.

        Arguments:
        * `sketch` (`JSON | None`):
          (required) See SolidCraft.
        * `curves` (`JSON | None`):
          (required) [open curve ids] (one wall each)
        * `thickness` (`JSON | None`):
          (required) See SolidCraft.
        * `depth` (`JSON | None`):
          (default: to the next face)
        * `flip` (`bool | None`):
          bool
        * `direction` (`SolidWebDirection | None`):
          in_plane|normal
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "solid.web",
            {
                "sketch": sketch,
                "curves": curves,
                "thickness": thickness,
                "depth": depth,
                "flip": flip,
                "direction": direction,
                **extra,
            },
        )


# Class `SCSurfaceCommands`:
@dataclass(slots=True)
class SCSurfaceCommands(SCNamespace):
    """The `surface.*` commands.

    Constructor:
    * `SCSurfaceCommands(transport)`
    """

    # Method `SCSurfaceCommands.blend()`:
    def blend(
        self,
        *,
        from_: JSON | None = None,
        to: JSON | None = None,
        continuity: JSON | None = None,
        bulge: JSON | None = None,
        align: JSON | None = None,
        seam: JSON | None = None,
        stitch: bool | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Blend Surface.

        `surface.blend`.

        Arguments:
        * `from_` (`JSON | None`):
          (required) See SolidCraft. (sent as `from`)
        * `to` (`JSON | None`):
          (required) {body, edges: [[x,y,z]]} (points on the edges of
          one chain of each body: two picks on the same edge is that one
          edge, more chain up)
        * `continuity` (`JSON | None`):
          [g0|g1|g2|g3, g0|g1|g2|g3] (each end, default g1: how much of
          the surface at the picked edges the blend repeats — the
          tangent plane, the curvature, or how that curvature changes)
        * `bulge` (`JSON | None`):
          [number, number] (default 0: how full each end leaves, -0.9
          flattest to 3 fullest)
        * `align` (`JSON | None`):
          [[x,y,z], [x,y,z]] (a point each end leaves towards, when the
          faces at the picks do not say)
        * `seam` (`JSON | None`):
          [[x,y,z], [x,y,z]] (a point on each chain its stations start
          from: two closed chains otherwise pair the way that keeps the
          blend from twisting; an open chain starts at the end nearer
          its point; a closed chain blends only to a closed chain)
        * `stitch` (`bool | None`):
          bool (sew the blend onto its two bodies where the boundaries
          meet, replacing them)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.blend",
            {
                "from": from_,
                "to": to,
                "continuity": continuity,
                "bulge": bulge,
                "align": align,
                "seam": seam,
                "stitch": stitch,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.boundary()`:
    def boundary(
        self,
        *,
        curves: JSON | None = None,
        continuity: JSON | None = None,
        crown: float | None = None,
        samples: JSON | None = None,
        v: JSON | None = None,
        operation: SurfaceBoundaryOperation | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Boundary Surface.

        `surface.boundary`.

        Either a loop of one sketch's curves — sketch?: id|name
        (default: the sketch being edited); each curve "id" (a curve of
        `sketch`) | {sketch?: id|name, curves: [ids meeting end to end]}
        (planar or 3D sketch curves) | {body: name, edges: [[x,y,z]]
        (points on a chain of its edges), continuity?: g0|g1|g2 (default
        g0; g1 the surface leaves tangent to the face beside a surface's
        open edges, g2 with its curvature too; on curves of one
        direction only)} | {point: [x,y,z]} (a side collapsed to a
        point: a three-sided patch)

        Arguments:
        * `curves` (`JSON | None`):
          (required) [2 to 4 sketch curve ids in loop order] (each one
          ends where the next begins and the last where the first does;
          two: the patch spans between them and leaves each boundary
          along the tangent across it; three or four: the flat patch of
          the loop, three collapsing the side opposite the first curve
          to the corner there)
        * `continuity` (`JSON | None`):
          g0|g1|g2|g3 | [one per curve] (default g1: how much of the
          surface across each boundary the patch repeats — a sketch
          curve's own plane, so g1 and up hold exactly and g0 lets the
          middle bow)
        * `crown` (`float | None`):
          number -0.9…3 (default 0: how full the middle is, without
          touching a boundary; two curves only)
        * `samples` (`JSON | None`):
          8…512 stations per boundary (default 25) — or a curve network
          — u: [curve] (two or more one way: the surface lofts through
          them)
        * `v` (`JSON | None`):
          [curve] (crossing every u-curve once: two each way give a
          Coons patch, more a Gordon surface through every curve; a
          curve that misses another by more than 0.01 mm is refused,
          naming the pair)
        * `operation` (`SurfaceBoundaryOperation | None`):
          new|join (default new; join sews the surface into the body of
          its first edge curve, a solid when it closes the gap). name?
        * `body_name` (`JSON | None`):
          (a surface body)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.boundary",
            {
                "curves": curves,
                "continuity": continuity,
                "crown": crown,
                "samples": samples,
                "v": v,
                "operation": operation,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.extend()`:
    def extend(
        self,
        *,
        body: JSON | None = None,
        edges: JSON | None = None,
        distance: Expr | None = None,
        mode: JSON | None = None,
        up_to: JSON | None = None,
        neighbours: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Extend.

        `surface.extend`.

        Arguments:
        * `body` (`JSON | None`):
          (required) surface name
        * `edges` (`JSON | None`):
          (required) [[x,y,z]] (points on boundary edges to push out)
        * `distance` (`Expr | None`):
          (required) expr (unless up_to)
        * `mode` (`JSON | None`):
          natural (the surface itself continued: exact for planes and
          surfaces of revolution, a B-spline's end spans continued; the
          default) | tangent (a ruled run-off face along each edge, G1)
          | curvature (a run-off face keeping the surface's curvature
          across the edge, G2)
        * `up_to` (`JSON | None`):
          plane (XY|XZ|YZ|plane name|{origin, normal}) | {body, point}
          (a face, its surface extended) | "bounds" (natural: back to
          the surface's own bounds, undoing a trim)
        * `neighbours` (`bool | None`):
          bool (default true: the edges next to an extended edge are
          lengthened to meet it; false: the extension's sides run square
          to the edge)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.extend",
            {
                "body": body,
                "edges": edges,
                "distance": distance,
                "mode": mode,
                "up_to": up_to,
                "neighbours": neighbours,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.extrude()`:
    def extrude(
        self,
        *,
        sketch: SurfaceExtrudeSketch | None = None,
        curves: JSON | None = None,
        distance: Expr | None = None,
        direction: SurfaceExtrudeDirection | None = None,
        distance2: Expr | None = None,
        start_offset: Expr | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Surface Extrude.

        `surface.extrude`.

        Arguments:
        * `sketch` (`SurfaceExtrudeSketch | None`):
          id|name
        * `curves` (`JSON | None`):
          [curve ids] (open or closed chains of curves meeting end to
          end) and/or profiles? (their boundaries; the default when no
          curves are given)
        * `distance` (`Expr | None`):
          (required) expr
        * `direction` (`SurfaceExtrudeDirection | None`):
          positive|negative|symmetric
        * `distance2` (`Expr | None`):
          expr
        * `start_offset` (`Expr | None`):
          expr
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          (a surface body: walls only, no caps)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.extrude",
            {
                "sketch": sketch,
                "curves": curves,
                "distance": distance,
                "direction": direction,
                "distance2": distance2,
                "start_offset": start_offset,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.fair()`:
    def fair(
        self,
        *,
        body: JSON | None = None,
        faces: JSON | None = None,
        strength: float | None = None,
        iterations: float | None = None,
        keep_edges: bool | None = None,
        tolerance: Expr | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Fair Surface.

        `surface.fair`.

        and the warning in the reply carries the energy before and after

        Arguments:
        * `body` (`JSON | None`):
          (required) surface name
        * `faces` (`JSON | None`):
          [[x,y,z]] points on the faces to fair (default: every face)
        * `strength` (`float | None`):
          number (0..1 of the full fairing step, default 1)
        * `iterations` (`float | None`):
          number (1..1000 steps, default 1)
        * `keep_edges` (`bool | None`):
          bool (default true: hold the boundary row and the row next to
          it, so a face keeps meeting its neighbours in position and in
          tangent)
        * `tolerance` (`Expr | None`):
          expr mm (how far a control vertex may move, default 0.001 of
          the body's size). Moves the interior control vertices of each
          B-spline face to flatten its curvature variation while the
          boundary stays put: the face keeps its edges and the body its
          shape within the tolerance
        * `name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.fair",
            {
                "body": body,
                "faces": faces,
                "strength": strength,
                "iterations": iterations,
                "keep_edges": keep_edges,
                "tolerance": tolerance,
                "name": name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.fillet()`:
    def fillet(
        self,
        *,
        planned: JSON | None = None,
        b: JSON | None = None,
        radius: Expr | None = None,
        trim: SurfaceFilletTrim | None = None,
        **extra: JSON,
    ) -> JSON:
        """Surface Fillet.

        `surface.fillet`.

        Arguments:
        * `planned` (`JSON | None`):
          (required) a
        * `b` (`JSON | None`):
          (required) {body, point} (two faces of separate bodies that
          meet or cross; the points pick the side the ball rolls on)
        * `radius` (`Expr | None`):
          (required) expr
        * `trim` (`SurfaceFilletTrim | None`):
          both|first|none
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.fillet",
            {
                "planned": planned,
                "b": b,
                "radius": radius,
                "trim": trim,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.loft()`:
    def loft(
        self,
        *,
        sections: JSON | None = None,
        continuity: JSON | None = None,
        crown: JSON | None = None,
        rails: JSON | None = None,
        rail_fit: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Surface Loft.

        `surface.loft`.

        Arguments:
        * `sections` (`JSON | None`):
          (required) [{sketch, curves?: [curve ids], profiles?} | {body,
          edges: [[x,y,z]]}] (2…50 in order; each one chain: a profile
          without holes, or curves meeting end to end; all open or all
          closed; a body edge chain takes the face the chain bounds as
          the surface the end repeats)
        * `continuity` (`JSON | None`):
          [g0|g1|g2|g3, g0|g1|g2|g3] (each end, default g0: how much of
          the surface at the first and last section the loft repeats —
          the tangent plane, the curvature, or how that curvature
          changes)
        * `crown` (`JSON | None`):
          [number, number] (default 0: how full each end leaves, -0.9
          flattest to 3 fullest)
        * `rails` (`JSON | None`):
          See SolidCraft.
        * `rail_fit` (`JSON | None`):
          (as solid.loft; sketch sections only, both ends g0)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          (a surface body: ruled between two sections, smooth through
          three or more; no caps)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.loft",
            {
                "sections": sections,
                "continuity": continuity,
                "crown": crown,
                "rails": rails,
                "rail_fit": rail_fit,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.match()`:
    def match(
        self,
        *,
        body: JSON | None = None,
        faces: JSON | None = None,
        target: JSON | None = None,
        edges: JSON | None = None,
        order: SurfaceMatchOrder | None = None,
        **extra: JSON,
    ) -> JSON:
        """Match Surface.

        `surface.match`.

        Arguments:
        * `body` (`JSON | None`):
          (required) surface name (the body whose face is rebuilt)
        * `faces` (`JSON | None`):
          [[x,y,z]] (points on that face, default: the body's first)
        * `target` (`JSON | None`):
          (required) body name (the body the seam must meet)
        * `edges` (`JSON | None`):
          (required) [[x,y,z]] (points on one edge chain of the target:
          the rebuilt boundary takes its place)
        * `order` (`SurfaceMatchOrder | None`):
          g1|g2|g3 (default g2: position and tangent plane, the
          curvature too, or how that curvature changes along the seam).
          The far boundary stays where it was and the body keeps its
          name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.match",
            {
                "body": body,
                "faces": faces,
                "target": target,
                "edges": edges,
                "order": order,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.offset()`:
    def offset(
        self,
        *,
        faces: JSON | None = None,
        body: JSON | None = None,
        distance: Expr | None = None,
        chain: bool | None = None,
        tolerance: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Offset Surface.

        `surface.offset`.

        other faces are fitted. A new surface body (a solid where its
        faces close)

        Arguments:
        * `faces` (`JSON | None`):
          (required) [[x,y,z]] (points on the faces)
        * `body` (`JSON | None`):
          See SolidCraft.
        * `distance` (`Expr | None`):
          (required) expr (signed, along the faces' normals; 0 copies
          the faces)
        * `chain` (`bool | None`):
          bool (each pick's whole smooth chain of faces)
        * `tolerance` (`Expr | None`):
          expr (how far a fitted face may stray, default 0.01 mm).
          Planes and cylinders move exactly
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.offset",
            {
                "faces": faces,
                "body": body,
                "distance": distance,
                "chain": chain,
                "tolerance": tolerance,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.patch()`:
    def patch(
        self,
        *,
        sketch: SurfacePatchSketch | None = None,
        edges: JSON | None = None,
        continuity: JSON | None = None,
        points: JSON | None = None,
        crown: float | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Patch.

        `surface.patch`.

        Arguments:
        * `sketch` (`SurfacePatchSketch | None`):
          id|name and profiles? (planar patches of sketch regions)
        * `edges` (`JSON | None`):
          [[x,y,z]] (points on a closed loop of a body's edges: one face
          on them, planar when the loop is, else a smooth B-spline
          surface) and body?
        * `continuity` (`JSON | None`):
          g0|g1|g2 (edges only, default g0: how the patch meets the
          faces beside the loop — g1 their tangent planes, g2 also their
          curvature across the edges) or [{edge: [x,y,z], g: g0|g1|g2}]
          (those edges so, the rest g0) or {all, edges}
        * `points` (`JSON | None`):
          [[x,y,z]] (edges only, up to 64: points the patch passes
          through)
        * `crown` (`float | None`):
          number −0.9…3 (default 0: only a fitted patch, whose middle
          becomes fuller by this many times the loop's size — the bump
          vanishes on the loop, so the face still meets the picked edges
          and the continuity across them; a loop that is planar and g0
          is the exact plane whatever the crown; with points, crown
          needs a g1 or g2 edge)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.patch",
            {
                "sketch": sketch,
                "edges": edges,
                "continuity": continuity,
                "points": points,
                "crown": crown,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.reverse_normal()`:
    def reverse_normal(
        self,
        *,
        body: JSON | None = None,
        faces: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Reverse Normal.

        `surface.reverse_normal`.

        Arguments:
        * `body` (`JSON | None`):
          (required) (a surface)
        * `faces` (`JSON | None`):
          [[x,y,z]] (points on the faces to turn over; default: all of
          them)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.reverse_normal",
            {
                "body": body,
                "faces": faces,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.revolve()`:
    def revolve(
        self,
        *,
        sketch: SurfaceRevolveSketch | None = None,
        curves: JSON | None = None,
        axis: JSON | None = None,
        angle: Expr | None = None,
        angle2: Expr | None = None,
        symmetric: bool | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Surface Revolve.

        `surface.revolve`.

        Arguments:
        * `sketch` (`SurfaceRevolveSketch | None`):
          id|name
        * `curves` (`JSON | None`):
          [curve ids] and/or profiles? (as surface.extrude)
        * `axis` (`JSON | None`):
          (required) sketch line id|x|y|X|Y|Z|construction axis
          name|{origin, dir}
        * `angle` (`Expr | None`):
          expr (default 360 deg)
        * `angle2` (`Expr | None`):
          expr (the other side)
        * `symmetric` (`bool | None`):
          bool
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          (a surface body, no caps; a solid where a full turn closes it)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.revolve",
            {
                "sketch": sketch,
                "curves": curves,
                "axis": axis,
                "angle": angle,
                "angle2": angle2,
                "symmetric": symmetric,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.ruled()`:
    def ruled(
        self,
        *,
        body: JSON | None = None,
        edges: JSON | None = None,
        distance: Expr | None = None,
        mode: SurfaceRuledMode | None = None,
        angle: Expr | None = None,
        direction: Point3D | None = None,
        face: Point3D | None = None,
        flip: bool | None = None,
        corners: SurfaceRuledCorners | None = None,
        **extra: JSON,
    ) -> JSON:
        """Ruled Surface.

        `surface.ruled`.

        cylinders and cones, other edges a fitted ruled B-spline. A new
        surface body

        Arguments:
        * `body` (`JSON | None`):
          (required) See SolidCraft.
        * `edges` (`JSON | None`):
          (required) [[x,y,z]] (points on a chain of its edges, open or
          closed)
        * `distance` (`Expr | None`):
          (required) expr (how far the strip reaches)
        * `mode` (`SurfaceRuledMode | None`):
          normal|tangent|angle|direction (default normal: along the
          normal of the face beside each edge; tangent: continuing it)
        * `angle` (`Expr | None`):
          expr (angle mode: from `direction`, else from the face's
          normal, turned away from the face; 90 deg from the normal is
          tangent)
        * `direction` (`Point3D | None`):
          [x,y,z] (direction mode: the rulings; angle mode: the
          reference, e.g. a pull direction for a draft)
        * `face` (`Point3D | None`):
          [x,y,z] (a point on the face the directions come from;
          default: the face beside the most picked edges)
        * `flip` (`bool | None`):
          bool (the other side)
        * `corners` (`SurfaceRuledCorners | None`):
          mitre|round (sharp corners of the chain; inside corners are
          always cut back). Lines and arcs give exact planes
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.ruled",
            {
                "body": body,
                "edges": edges,
                "distance": distance,
                "mode": mode,
                "angle": angle,
                "direction": direction,
                "face": face,
                "flip": flip,
                "corners": corners,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.stitch()`:
    def stitch(
        self,
        *,
        bodies: JSON | None = None,
        tolerance: Expr | None = None,
        **extra: JSON,
    ) -> JSON:
        """Stitch.

        `surface.stitch`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [names] (surfaces sewn into the first; a solid when
          they close)
        * `tolerance` (`Expr | None`):
          expr (default: tight)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.stitch",
            {
                "bodies": bodies,
                "tolerance": tolerance,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.sweep()`:
    def sweep(
        self,
        *,
        sketch: SurfaceSweepSketch | None = None,
        curves: JSON | None = None,
        path_sketch: JSON | None = None,
        path: JSON | None = None,
        orientation: JSON | None = None,
        twist: JSON | None = None,
        scale: JSON | None = None,
        rails: JSON | None = None,
        rail_fit: JSON | None = None,
        name: JSON | None = None,
        body_name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Surface Sweep.

        `surface.sweep`.

        Arguments:
        * `sketch` (`SurfaceSweepSketch | None`):
          id|name
        * `curves` (`JSON | None`):
          [curve ids] and/or profiles? (as surface.extrude)
        * `path_sketch` (`JSON | None`):
          (required) sketch
        * `path` (`JSON | None`):
          (required) [curve ids in order] (a path with corners, or 3D
          curves, gives ruled walls mitred at the corners)
        * `orientation` (`JSON | None`):
          See SolidCraft.
        * `twist` (`JSON | None`):
          See SolidCraft.
        * `scale` (`JSON | None`):
          See SolidCraft.
        * `rails` (`JSON | None`):
          See SolidCraft.
        * `rail_fit` (`JSON | None`):
          (as solid.sweep)
        * `name` (`JSON | None`):
          See SolidCraft.
        * `body_name` (`JSON | None`):
          (a surface body, no caps)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.sweep",
            {
                "sketch": sketch,
                "curves": curves,
                "path_sketch": path_sketch,
                "path": path,
                "orientation": orientation,
                "twist": twist,
                "scale": scale,
                "rails": rails,
                "rail_fit": rail_fit,
                "name": name,
                "body_name": body_name,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.thicken()`:
    def thicken(
        self,
        *,
        bodies: JSON | None = None,
        thickness: Expr | None = None,
        symmetric: bool | None = None,
        operation: SurfaceThickenOperation | None = None,
        targets: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Thicken.

        `surface.thicken`.

        Arguments:
        * `bodies` (`JSON | None`):
          (required) [surface names]
        * `thickness` (`Expr | None`):
          (required) expr (negative: against the normal)
        * `symmetric` (`bool | None`):
          bool
        * `operation` (`SurfaceThickenOperation | None`):
          new|join|cut|intersect
        * `targets` (`JSON | None`):
          See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.thicken",
            {
                "bodies": bodies,
                "thickness": thickness,
                "symmetric": symmetric,
                "operation": operation,
                "targets": targets,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.trim()`:
    def trim(
        self,
        *,
        body: JSON | None = None,
        plane: JSON | None = None,
        tool: JSON | None = None,
        curves: JSON | None = None,
        keep: JSON | None = None,
        keep_with: JSON | None = None,
        extend: bool | None = None,
        stitch: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Trim.

        `surface.trim`.

        each is cut where the other's surface (extended) meets it

        Arguments:
        * `body` (`JSON | None`):
          (required) surface name
        * `plane` (`JSON | None`):
          (required) XY|XZ|YZ|plane name|{origin, normal}
        * `tool` (`JSON | None`):
          {body, point} (a face, its surface extended)
        * `curves` (`JSON | None`):
          {sketch, curves?: [curve ids] (chains of curves meeting end to
          end; default every curve), direction?: normal|[x,y,z] (swept
          onto the surface along the sketch's normal, the default, or
          this direction)}
        * `keep` (`JSON | None`):
          (required) [x,y,z] (a point on the side to keep) or [[x,y,z],
          ...] (points on the regions to keep: the pieces that hang
          together once cut). Mutual trim: with: another surface (one
          face each; leave out plane, tool and curves)
        * `keep_with` (`JSON | None`):
          (required) [x,y,z] or [[x,y,z], ...] (what to keep of it)
        * `extend` (`bool | None`):
          bool (a surface that stops short of the other is extended to
          meet it)
        * `stitch` (`bool | None`):
          bool (the kept pieces sewn into `body`; `with` is then gone)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.trim",
            {
                "body": body,
                "plane": plane,
                "tool": tool,
                "curves": curves,
                "keep": keep,
                "keep_with": keep_with,
                "extend": extend,
                "stitch": stitch,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.unstitch()`:
    def unstitch(
        self,
        *,
        body: JSON | None = None,
        faces: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Unstitch.

        `surface.unstitch`.

        Arguments:
        * `body` (`JSON | None`):
          (required) See SolidCraft.
        * `faces` (`JSON | None`):
          [[x,y,z]] (points on the faces to take out, each its own
          surface body; the rest stay together under the body's name;
          default: every face its own surface body). A solid comes apart
          into surfaces
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.unstitch",
            {
                "body": body,
                "faces": faces,
                **extra,
            },
        )

    # Method `SCSurfaceCommands.untrim()`:
    def untrim(
        self,
        *,
        face: JSON | None = None,
        holes: JSON | None = None,
        outer: bool | None = None,
        in_place: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Untrim.

        `surface.untrim`.

        the face keeps its name

        Arguments:
        * `face` (`JSON | None`):
          (required) {body, point}
        * `holes` (`JSON | None`):
          all|[[x,y,z]] (points on the inner loops to remove; default:
          all)
        * `outer` (`bool | None`):
          bool (restore the outer boundary to the surface's natural
          bounds: a free-form surface's own, an analytic surface's span
          of the face)
        * `in_place` (`bool | None`):
          bool (untrim a surface body's face where it is; a solid's face
          is always copied out). A surface body
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "surface.untrim",
            {
                "face": face,
                "holes": holes,
                "outer": outer,
                "in_place": in_place,
                **extra,
            },
        )


# Class `SCTimelineCommands`:
@dataclass(slots=True)
class SCTimelineCommands(SCNamespace):
    """The `timeline.*` commands.

    Constructor:
    * `SCTimelineCommands(transport)`
    """

    # Method `SCTimelineCommands.add()`:
    def add(
        self,
        *,
        feature: JSON | None = None,
        params: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Add Recorded Feature.

        `timeline.add`.

        the feature goes at the marker

        Arguments:
        * `feature` (`JSON | None`):
          (required) a feature as the design file and timeline.inspect
          hold it ({type, name?, id?, …}; the name is kept even when
          another feature has it, the id is kept and refused when
          another feature has it, so later steps can refer to them)
        * `params` (`JSON | None`):
          [{name, expression, unit?, comment?}] (the model parameters
          its sketch dimensions use)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): feature, name, error, warning

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.add",
            {
                "feature": feature,
                "params": params,
                **extra,
            },
        )

    # Method `SCTimelineCommands.compute_all()`:
    def compute_all(
        self,
        **extra: JSON,
    ) -> JSON:
        """Compute All.

        `timeline.compute_all`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.compute_all",
            {
                **extra,
            },
        )

    # Method `SCTimelineCommands.copy()`:
    def copy(
        self,
        *,
        features: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Copy Features.

        `timeline.copy`.

        Arguments:
        * `features` (`JSON | None`):
          (required) [ids or names] (in timeline order on paste)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.copy",
            {
                "features": features,
                **extra,
            },
        )

    # Method `SCTimelineCommands.delete()`:
    def delete(
        self,
        *,
        feature: TimelineDeleteFeature | None = None,
        features: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete.

        `timeline.delete`.

        Arguments:
        * `feature` (`TimelineDeleteFeature | None`):
          (required) id|name
        * `features` (`JSON | None`):
          [id|name] (one undo step; a sketch takes its dependent
          features with it)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): deleted: [ids]; failing?: [{feature, error}] (later
          features that worked and now fail)

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.delete",
            {
                "feature": feature,
                "features": features,
                **extra,
            },
        )

    # Method `SCTimelineCommands.dependents()`:
    def dependents(
        self,
        *,
        feature: TimelineDependentsFeature | None = None,
        **extra: JSON,
    ) -> JSON:
        """Feature Dependents.

        `timeline.dependents`.

        Arguments:
        * `feature` (`TimelineDependentsFeature | None`):
          (required) id|name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): features deleted with it, and features that would
          fail without it

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.dependents",
            {
                "feature": feature,
                **extra,
            },
        )

    # Method `SCTimelineCommands.edit()`:
    def edit(
        self,
        *,
        feature: TimelineEditFeature | None = None,
        set: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Feature.

        `timeline.edit`.

        Arguments:
        * `feature` (`TimelineEditFeature | None`):
          (required) id|name
        * `set` (`JSON | None`):
          (required) {fields to change, merged into the feature's
          definition as timeline.inspect returns it, e.g. {"extent":
          {"distance": "30"}} (extrude), {"angle": "90 deg"} (revolve);
          a dotted key names a nested field ({"plane.distance": "8 mm"}
          = {"plane": {"distance": "8 mm"}}); expressions are text, or a
          number in mm or degrees}
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): recomputed: features rebuilt, restored: features
          whose earlier result for the same inputs was reused

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.edit",
            {
                "feature": feature,
                "set": set,
                **extra,
            },
        )

    # Method `SCTimelineCommands.export_script()`:
    def export_script(
        self,
        *,
        path: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Export Command Script.

        `timeline.export_script`.

        Arguments:
        * `path` (`JSON | None`):
          write the script to this file
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): script: {commands: [...]} that rebuilds the design
          (solidcraft-cli eval/run), steps, omitted: what the script
          leaves out (appearances, folders, views, configurations);
          components and assemblies are not supported yet

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.export_script",
            {
                "path": path,
                **extra,
            },
        )

    # Method `SCTimelineCommands.group()`:
    def group(
        self,
        *,
        name: JSON | None = None,
        features: JSON | None = None,
        parent: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Feature Folder.

        `timeline.group`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `features` (`JSON | None`):
          [id|name]
        * `parent` (`JSON | None`):
          folder id (features leave any other timeline folder)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.group",
            {
                "name": name,
                "features": features,
                "parent": parent,
                **extra,
            },
        )

    # Method `SCTimelineCommands.inspect()`:
    def inspect(
        self,
        *,
        feature: TimelineInspectFeature | None = None,
        **extra: JSON,
    ) -> JSON:
        """Inspect Feature.

        `timeline.inspect`.

        Arguments:
        * `feature` (`TimelineInspectFeature | None`):
          (required) id|name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): type, definition (the fields timeline.edit's set
          changes, with their current values), inputs: [{label, param,
          expression, unit}] (named inputs parameters.change can also
          set), error, warning

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.inspect",
            {
                "feature": feature,
                **extra,
            },
        )

    # Method `SCTimelineCommands.move_many()`:
    def move_many(
        self,
        *,
        features: JSON | None = None,
        groups: JSON | None = None,
        group: JSON | None = None,
        position: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Timeline Items.

        `timeline.move_many`.

        atomically changes folder membership and moves all selected
        contents as one block

        Arguments:
        * `features` (`JSON | None`):
          [id|name]
        * `groups` (`JSON | None`):
          [folder ids]
        * `group` (`JSON | None`):
          folder id
        * `position` (`JSON | None`):
          (required) insertion slot
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.move_many",
            {
                "features": features,
                "groups": groups,
                "group": group,
                "position": position,
                **extra,
            },
        )

    # Method `SCTimelineCommands.move_to_group()`:
    def move_to_group(
        self,
        *,
        features: JSON | None = None,
        groups: JSON | None = None,
        group: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Features to Folder.

        `timeline.move_to_group`.

        Arguments:
        * `features` (`JSON | None`):
          [id|name]
        * `groups` (`JSON | None`):
          [ids]
        * `group` (`JSON | None`):
          id (omit or null to move to the timeline root)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.move_to_group",
            {
                "features": features,
                "groups": groups,
                "group": group,
                **extra,
            },
        )

    # Method `SCTimelineCommands.paste()`:
    def paste(
        self,
        *,
        translate: Point3D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Paste Features.

        `timeline.paste`.

        the copies go at the marker

        Arguments:
        * `translate` (`Point3D | None`):
          [x,y,z] (moves the copies' geometry)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.paste",
            {
                "translate": translate,
                **extra,
            },
        )

    # Method `SCTimelineCommands.redefine()`:
    def redefine(
        self,
        *,
        feature: TimelineRedefineFeature | None = None,
        command: JSON | None = None,
        params: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Edit Feature.

        `timeline.redefine`.

        Arguments:
        * `feature` (`TimelineRedefineFeature | None`):
          (required) id|name
        * `command` (`JSON | None`):
          (required) the feature's command id
        * `params` (`JSON | None`):
          (required) its parameters (the feature is rebuilt in place)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.redefine",
            {
                "feature": feature,
                "command": command,
                "params": params,
                **extra,
            },
        )

    # Method `SCTimelineCommands.rename()`:
    def rename(
        self,
        *,
        feature: TimelineRenameFeature | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename.

        `timeline.rename`.

        Arguments:
        * `feature` (`TimelineRenameFeature | None`):
          (required) id|name
        * `name` (`JSON | None`):
          (required) (references to it follow)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.rename",
            {
                "feature": feature,
                "name": name,
                **extra,
            },
        )

    # Method `SCTimelineCommands.rename_group()`:
    def rename_group(
        self,
        *,
        group: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Feature Folder.

        `timeline.rename_group`.

        Arguments:
        * `group` (`JSON | None`):
          (required) id
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.rename_group",
            {
                "group": group,
                "name": name,
                **extra,
            },
        )

    # Method `SCTimelineCommands.reorder()`:
    def reorder(
        self,
        *,
        feature: TimelineReorderFeature | None = None,
        position: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Reorder Feature.

        `timeline.reorder`.

        refused when a feature that worked would fail

        Arguments:
        * `feature` (`TimelineReorderFeature | None`):
          (required) id|name
        * `position` (`JSON | None`):
          (required) its new index
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.reorder",
            {
                "feature": feature,
                "position": position,
                **extra,
            },
        )

    # Method `SCTimelineCommands.reorder_many()`:
    def reorder_many(
        self,
        *,
        features: JSON | None = None,
        position: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Reorder Features.

        `timeline.reorder_many`.

        selected features keep their relative order; refused when a
        feature that worked would fail

        Arguments:
        * `features` (`JSON | None`):
          (required) [id|name]
        * `position` (`JSON | None`):
          (required) insertion slot in the current history
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.reorder_many",
            {
                "features": features,
                "position": position,
                **extra,
            },
        )

    # Method `SCTimelineCommands.roll_to()`:
    def roll_to(
        self,
        *,
        position: float | None = None,
        feature: TimelineRollToFeature | None = None,
        **extra: JSON,
    ) -> JSON:
        """Roll History Marker.

        `timeline.roll_to`.

        "end" (omit = end)

        Arguments:
        * `position` (`float | None`):
          (required) number of features to keep active
        * `feature` (`TimelineRollToFeature | None`):
          id|name (the marker goes right after it)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.roll_to",
            {
                "position": position,
                "feature": feature,
                **extra,
            },
        )

    # Method `SCTimelineCommands.rollback()`:
    def rollback(
        self,
        *,
        position: float | None = None,
        **extra: JSON,
    ) -> JSON:
        """Move Timeline Marker.

        `timeline.rollback`.

        "end" (omit = end)

        Arguments:
        * `position` (`float | None`):
          (required) number of features to keep active
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.rollback",
            {
                "position": position,
                **extra,
            },
        )

    # Method `SCTimelineCommands.suppress()`:
    def suppress(
        self,
        *,
        feature: TimelineSuppressFeature | None = None,
        features: JSON | None = None,
        suppressed: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Suppress Feature.

        `timeline.suppress`.

        Arguments:
        * `feature` (`TimelineSuppressFeature | None`):
          (required) id|name
        * `features` (`JSON | None`):
          [id|name] (one undo step)
        * `suppressed` (`bool | None`):
          bool (default toggles: several features are all suppressed
          unless all of them already are, then all are unsuppressed)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): feature: id (or features: [ids]), suppressed

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.suppress",
            {
                "feature": feature,
                "features": features,
                "suppressed": suppressed,
                **extra,
            },
        )

    # Method `SCTimelineCommands.ungroup()`:
    def ungroup(
        self,
        *,
        group: JSON | None = None,
        groups: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Remove Feature Folders.

        `timeline.ungroup`.

        Arguments:
        * `group` (`JSON | None`):
          (required) id
        * `groups` (`JSON | None`):
          [ids] (features remain in the timeline)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "timeline.ungroup",
            {
                "group": group,
                "groups": groups,
                **extra,
            },
        )


# Class `SCViewCommands`:
@dataclass(slots=True)
class SCViewCommands(SCNamespace):
    """The `view.*` commands.

    Constructor:
    * `SCViewCommands(transport)`
    """

    # Method `SCViewCommands.ambient_occlusion()`:
    def ambient_occlusion(
        self,
        *,
        enabled: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """Ambient Occlusion.

        `view.ambient_occlusion`.

        Arguments:
        * `enabled` (`bool | None`):
          (required) bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): enabled; apply soft contact shading in the GPU
          viewport

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.ambient_occlusion",
            {
                "enabled": enabled,
                **extra,
            },
        )

    # Method `SCViewCommands.apply()`:
    def apply(
        self,
        *,
        view: JSON | None = None,
        camera: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Restore Named View.

        `view.apply`.

        Arguments:
        * `view` (`JSON | None`):
          front|back|top|bottom|left|right|iso|home (frames the model) |
          a named view's name
        * `camera` (`JSON | None`):
          {target: [x,y,z], yaw, pitch, distance, fov?} (radians, mm)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): camera. The viewport (and the MCP screenshot) moves
          there. View state: not saved, not an undo step

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.apply",
            {
                "view": view,
                "camera": camera,
                **extra,
            },
        )

    # Method `SCViewCommands.delete()`:
    def delete(
        self,
        *,
        view: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Delete Named View.

        `view.delete`.

        Arguments:
        * `view` (`JSON | None`):
          (required) name
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.delete",
            {
                "view": view,
                **extra,
            },
        )

    # Method `SCViewCommands.graphics_preset()`:
    def graphics_preset(
        self,
        *,
        preset: ViewGraphicsPresetPreset | None = None,
        **extra: JSON,
    ) -> JSON:
        """Graphics Preset.

        `view.graphics_preset`.

        Arguments:
        * `preset` (`ViewGraphicsPresetPreset | None`):
          (required) performance|quality
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): preset, enabled, display_quality, supersampling,
          supersampling_adaptive; Quality: AO, Fine, adaptive 2x SSAA;
          Performance: no AO, Normal, no SSAA

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.graphics_preset",
            {
                "preset": preset,
                **extra,
            },
        )

    # Method `SCViewCommands.history_layout()`:
    def history_layout(
        self,
        *,
        width: JSON | None = None,
        dock: ViewHistoryLayoutDock | None = None,
        collapsed: bool | None = None,
        **extra: JSON,
    ) -> JSON:
        """History layout.

        `view.history_layout`.

        Arguments:
        * `width` (`JSON | None`):
          1..1000000
        * `dock` (`ViewHistoryLayoutDock | None`):
          bottom|left|under_browser
        * `collapsed` (`bool | None`):
          bool
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): validated layout request; display only, never opens
          a dialog

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.history_layout",
            {
                "width": width,
                "dock": dock,
                "collapsed": collapsed,
                **extra,
            },
        )

    # Method `SCViewCommands.layout()`:
    def layout(
        self,
        *,
        mode: ViewLayoutMode | None = None,
        **extra: JSON,
    ) -> JSON:
        """Workspace layout.

        `view.layout`.

        Arguments:
        * `mode` (`ViewLayoutMode | None`):
          (required) floating|compact
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): validated workspace layout; display only, never
          opens a dialog

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.layout",
            {
                "mode": mode,
                **extra,
            },
        )

    # Method `SCViewCommands.list()`:
    def list(
        self,
        **extra: JSON,
    ) -> JSON:
        """List Named Views.

        `view.list`.

        Arguments:
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.list",
            {
                **extra,
            },
        )

    # Method `SCViewCommands.navigate()`:
    def navigate(
        self,
        *,
        camera: JSON | None = None,
        direction: Point3D | None = None,
        action: ViewNavigateAction | None = None,
        degrees: JSON | None = None,
        motion: ViewNavigateMotion | None = None,
        delta: JSON | None = None,
        free_orbit: bool | None = None,
        viewport: JSON | None = None,
        pivot: Point3D | None = None,
        factor: JSON | None = None,
        anchor: Point3D | None = None,
        **extra: JSON,
    ) -> JSON:
        """Navigate View.

        `view.navigate`.

        Arguments:
        * `camera` (`JSON | None`):
          (required) Camera
        * `direction` (`Point3D | None`):
          [x,y,z] in the camera's up-axis frame
        * `action` (`ViewNavigateAction | None`):
          (required)
          left|right|up|down|clockwise|counterclockwise|home|fit
        * `degrees` (`JSON | None`):
          0..180 (how far left|right|up|down turn; default 90)
        * `motion` (`ViewNavigateMotion | None`):
          (required) pan|orbit|zoom
        * `delta` (`JSON | None`):
          [dx,dy] (pixels, each ±10000)
        * `free_orbit` (`bool | None`):
          bool (orbit through poles, default false)
        * `viewport` (`JSON | None`):
          [width,height] (1..1000000, required for pan or pivot)
        * `pivot` (`Point3D | None`):
          [x,y,z]
        * `factor` (`JSON | None`):
          0.05..20 (required for zoom)
        * `anchor` (`Point3D | None`):
          [x,y,z]
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): camera, fit, continuous?

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.navigate",
            {
                "camera": camera,
                "direction": direction,
                "action": action,
                "degrees": degrees,
                "motion": motion,
                "delta": delta,
                "free_orbit": free_orbit,
                "viewport": viewport,
                "pivot": pivot,
                "factor": factor,
                "anchor": anchor,
                **extra,
            },
        )

    # Method `SCViewCommands.normal_to()`:
    def normal_to(
        self,
        *,
        camera: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Normal to Selection.

        `view.normal_to`.

        Arguments:
        * `camera` (`JSON | None`):
          Camera (default: current session camera or home view)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): camera; Look At the first selected planar face or
          plane, centered on the picked point; repeat while aligned to
          flip the side; preserves scale and projection

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.normal_to",
            {
                "camera": camera,
                **extra,
            },
        )

    # Method `SCViewCommands.rename()`:
    def rename(
        self,
        *,
        view: JSON | None = None,
        name: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """Rename Named View.

        `view.rename`.

        Arguments:
        * `view` (`JSON | None`):
          (required) name
        * `name` (`JSON | None`):
          (required) See SolidCraft.
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.rename",
            {
                "view": view,
                "name": name,
                **extra,
            },
        )

    # Method `SCViewCommands.save()`:
    def save(
        self,
        *,
        name: JSON | None = None,
        camera: JSON | None = None,
        **extra: JSON,
    ) -> JSON:
        """New Named View.

        `view.save`.

        Arguments:
        * `name` (`JSON | None`):
          See SolidCraft.
        * `camera` (`JSON | None`):
          (required) {target: [x,y,z], yaw, pitch, distance, fov?}
          (replaces a view of the same name)
        * `extra` (`JSON`):
          Any other parameters, sent as they are.

        Returns:
        * (`JSON`): The command result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return self.execute(
            "view.save",
            {
                "name": name,
                "camera": camera,
                **extra,
            },
        )


# Class `SCPyBind`:
@dataclass(slots=True)
class SCPyBind:
    """The top level of `scraftpybind`: SolidCraft's commands.

    The commands are grouped by namespace, so `sketch.create` is
    `SCPyBind.sketch.create()`.

    Attributes:
    * `transport` (`SCTransport`): How the commands are sent.
    * `appearance` (`SCAppearanceCommands`):
      The `appearance.*` commands.
    * `assembly` (`SCAssemblyCommands`):
      The `assembly.*` commands.
    * `body` (`SCBodyCommands`):
      The `body.*` commands.
    * `browser` (`SCBrowserCommands`):
      The `browser.*` commands.
    * `canvas` (`SCCanvasCommands`):
      The `canvas.*` commands.
    * `component` (`SCComponentCommands`):
      The `component.*` commands.
    * `config` (`SCConfigCommands`):
      The `config.*` commands.
    * `construct` (`SCConstructCommands`):
      The `construct.*` commands.
    * `contact` (`SCContactCommands`):
      The `contact.*` commands.
    * `diagnostics` (`SCDiagnosticsCommands`):
      The `diagnostics.*` commands.
    * `doc` (`SCDocCommands`):
      The `doc.*` commands.
    * `document` (`SCDocumentCommands`):
      The `document.*` commands.
    * `edit` (`SCEditCommands`):
      The `edit.*` commands.
    * `engine` (`SCEngineCommands`):
      The `engine.*` commands.
    * `explode` (`SCExplodeCommands`):
      The `explode.*` commands.
    * `expr` (`SCExprCommands`):
      The `expr.*` commands.
    * `face` (`SCFaceCommands`):
      The `face.*` commands.
    * `file` (`SCFileCommands`):
      The `file.*` commands.
    * `inspect` (`SCInspectCommands`):
      The `inspect.*` commands.
    * `joint` (`SCJointCommands`):
      The `joint.*` commands.
    * `library` (`SCLibraryCommands`):
      The `library.*` commands.
    * `material` (`SCMaterialCommands`):
      The `material.*` commands.
    * `mesh` (`SCMeshCommands`):
      The `mesh.*` commands.
    * `model` (`SCModelCommands`):
      The `model.*` commands.
    * `motion` (`SCMotionCommands`):
      The `motion.*` commands.
    * `occurrence` (`SCOccurrenceCommands`):
      The `occurrence.*` commands.
    * `parameters` (`SCParametersCommands`):
      The `parameters.*` commands.
    * `parts` (`SCPartsCommands`):
      The `parts.*` commands.
    * `plastic` (`SCPlasticCommands`):
      The `plastic.*` commands.
    * `render` (`SCRenderCommands`):
      The `render.*` commands.
    * `select` (`SCSelectCommands`):
      The `select.*` commands.
    * `selection` (`SCSelectionCommands`):
      The `selection.*` commands.
    * `sheet` (`SCSheetCommands`):
      The `sheet.*` commands.
    * `sketch` (`SCSketchCommands`):
      The `sketch.*` commands.
    * `solid` (`SCSolidCommands`):
      The `solid.*` commands.
    * `surface` (`SCSurfaceCommands`):
      The `surface.*` commands.
    * `timeline` (`SCTimelineCommands`):
      The `timeline.*` commands.
    * `view` (`SCViewCommands`):
      The `view.*` commands.

    Constructor:
    * `SCPyBind(transport)`
    """

    # Constructor arguments:
    transport: SCTransport = field(init=True)

    # The namespaces, made by `__post_init__()` (alphabetized):
    appearance: SCAppearanceCommands = field(init=False)
    assembly: SCAssemblyCommands = field(init=False)
    body: SCBodyCommands = field(init=False)
    browser: SCBrowserCommands = field(init=False)
    canvas: SCCanvasCommands = field(init=False)
    component: SCComponentCommands = field(init=False)
    config: SCConfigCommands = field(init=False)
    construct: SCConstructCommands = field(init=False)
    contact: SCContactCommands = field(init=False)
    diagnostics: SCDiagnosticsCommands = field(init=False)
    doc: SCDocCommands = field(init=False)
    document: SCDocumentCommands = field(init=False)
    edit: SCEditCommands = field(init=False)
    engine: SCEngineCommands = field(init=False)
    explode: SCExplodeCommands = field(init=False)
    expr: SCExprCommands = field(init=False)
    face: SCFaceCommands = field(init=False)
    file: SCFileCommands = field(init=False)
    inspect: SCInspectCommands = field(init=False)
    joint: SCJointCommands = field(init=False)
    library: SCLibraryCommands = field(init=False)
    material: SCMaterialCommands = field(init=False)
    mesh: SCMeshCommands = field(init=False)
    model: SCModelCommands = field(init=False)
    motion: SCMotionCommands = field(init=False)
    occurrence: SCOccurrenceCommands = field(init=False)
    parameters: SCParametersCommands = field(init=False)
    parts: SCPartsCommands = field(init=False)
    plastic: SCPlasticCommands = field(init=False)
    render: SCRenderCommands = field(init=False)
    select: SCSelectCommands = field(init=False)
    selection: SCSelectionCommands = field(init=False)
    sheet: SCSheetCommands = field(init=False)
    sketch: SCSketchCommands = field(init=False)
    solid: SCSolidCommands = field(init=False)
    surface: SCSurfaceCommands = field(init=False)
    timeline: SCTimelineCommands = field(init=False)
    view: SCViewCommands = field(init=False)

    # Method `SCPyBind.__post_init__()`:
    def __post_init__(self) -> None:
        """Make the namespaces, all sharing the one transport."""
        self.appearance = SCAppearanceCommands(self.transport)
        self.assembly = SCAssemblyCommands(self.transport)
        self.body = SCBodyCommands(self.transport)
        self.browser = SCBrowserCommands(self.transport)
        self.canvas = SCCanvasCommands(self.transport)
        self.component = SCComponentCommands(self.transport)
        self.config = SCConfigCommands(self.transport)
        self.construct = SCConstructCommands(self.transport)
        self.contact = SCContactCommands(self.transport)
        self.diagnostics = SCDiagnosticsCommands(self.transport)
        self.doc = SCDocCommands(self.transport)
        self.document = SCDocumentCommands(self.transport)
        self.edit = SCEditCommands(self.transport)
        self.engine = SCEngineCommands(self.transport)
        self.explode = SCExplodeCommands(self.transport)
        self.expr = SCExprCommands(self.transport)
        self.face = SCFaceCommands(self.transport)
        self.file = SCFileCommands(self.transport)
        self.inspect = SCInspectCommands(self.transport)
        self.joint = SCJointCommands(self.transport)
        self.library = SCLibraryCommands(self.transport)
        self.material = SCMaterialCommands(self.transport)
        self.mesh = SCMeshCommands(self.transport)
        self.model = SCModelCommands(self.transport)
        self.motion = SCMotionCommands(self.transport)
        self.occurrence = SCOccurrenceCommands(self.transport)
        self.parameters = SCParametersCommands(self.transport)
        self.parts = SCPartsCommands(self.transport)
        self.plastic = SCPlasticCommands(self.transport)
        self.render = SCRenderCommands(self.transport)
        self.select = SCSelectCommands(self.transport)
        self.selection = SCSelectionCommands(self.transport)
        self.sheet = SCSheetCommands(self.transport)
        self.sketch = SCSketchCommands(self.transport)
        self.solid = SCSolidCommands(self.transport)
        self.surface = SCSurfaceCommands(self.transport)
        self.timeline = SCTimelineCommands(self.transport)
        self.view = SCViewCommands(self.transport)

    # Method `SCPyBind.execute()`:
    def execute(self, command: str, params: Mapping[str, JSON]) -> JSON:
        """Run any SolidCraft command by its id (`engine.execute`).

        Arguments:
        * `command` (`str`): The command id (e.g. `sketch.create`).
        * `params` (`Mapping[str, JSON]`):
          The command's parameters; those that are `None` are not
          sent, as for the namespaces' methods.

        Returns:
        * (`JSON`): The command's result.

        Raises:
        * `SCSolidCraftError`: If the command fails.
        """
        return SCNamespace(self.transport).execute(command, params)


# End the generated command classes.


# Function `main()`:
def main() -> int:
    """Build the plate with a hole, in a GUI or headless.

    The one optional argument is a GUI's control port (default: the one
    in `current.port`, which only a SolidCraft on its default port
    writes), or `headless`, which exports `scraftpybind_plate.step`.

    Returns:
    * (`int`): The exit status.
    """
    # Connect to the GUI, or start a headless session; a SolidCraft
    # that is not there is reported in one line, not a traceback.
    where: str = sys.argv[1] if len(sys.argv) > 1 else "0"
    try:
        _plate(where)
    except OSError as error:
        print(f"scraftpybind: {error}", file=sys.stderr)
        return 1
    return 0


# Function `_plate()`:
def _plate(where: str) -> None:
    """Build the plate with a hole, in a GUI or headless.

    Arguments:
    * `where` (`str`): A GUI's control port, or `headless`.
    """
    with connect(where) as transport:
        solidcraft: SCPyBind = SCPyBind(transport)

        # Sketch a 100 x 60 mm rectangle with a 20 mm circle inside it.
        solidcraft.sketch.create(plane="XY", name="Plate")
        rectangle: JSON = solidcraft.sketch.rectangle_center(
            center=(0, 0), corner=(50, 30)
        )
        solidcraft.sketch.circle_center(center=(0, 0), diameter=20)
        solidcraft.sketch.finish()

        # Extrude only the profile inside the rectangle's sides, so the
        # circle stays a hole instead of being extruded too.
        assert isinstance(rectangle, Mapping)
        solidcraft.solid.extrude(
            distance=10,
            profiles=[{"curves": rectangle["curves"]}],
            body_name="Plate",
        )

        # Colour it light blue and show it from the isometric view;
        # headless, there is nothing to see, so export it instead.
        solidcraft.appearance.assign(bodies=["Plate"], color="#ADD8E6")
        solidcraft.view.apply(view="iso")
        if isinstance(transport, SCHeadlessTransport):
            step: Path = Path("scraftpybind_plate.step").resolve()
            solidcraft.file.export(path=str(step))
            print(f"Wrote {step}")


# Run as a program (only by the live tests).
if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
