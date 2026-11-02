#!/usr/bin/env python3
"""Give LinuxCNC's Python API to other programs, as JSON on a port.

LinuxCNC starts this as its `DISPLAY` program, in the target (the
`distrobox` box or WSL) where the `linuxcnc` module is.  It has no
window, and when it exits LinuxCNC shuts itself down.  It listens on
127.0.0.1, so any program on this computer can connect, with no
password; nothing else can.

A request and a reply are each one line of JSON.  Every request has
`call`, and may have `args` (a list) and `id` (returned in the reply):

```
{"id": 1, "call": "command.mdi", "args": ["G0 X1"]}
{"id": 1, "result": 1}
{"id": 2, "call": "stat", "args": [["actual_position"]]}
{"id": 2, "result": {"actual_position": [1.0, 0.0, 0.0, ...]}}
{"id": 3, "call": "command.nope"}
{"id": 3, "error": {"type": "ValueError", "message": "..."}}
```

The calls are:

* `ping`: The protocol's number and LinuxCNC's version.
* `constants`: The `linuxcnc` module's numbers and strings, by name.
* `stat`: `linuxcnc.stat` after a `poll()`: the attributes named by a
  list, or else all of them.
* `command.NAME`: A public method of `linuxcnc.command`.  In its
  arguments, `{"constant": "MODE_MDI"}` stands for that constant.
* `error_channel.poll`: The next error, as `[kind, text]`, or `null`.
* `ini.find`: `linuxcnc.ini(...).find(section, option)`, for the INI
  file that LinuxCNC is running.
* `program.write`: Writes a file (`[name, text]`) into `programs/`
  beside the INI file, and returns the path to give
  `command.program_open`, which can only read files in the target.
* `shutdown`: Replies, then exits, which shuts LinuxCNC down.

One request runs at a time, so a `command.wait_complete` holds up the
other connections until it finishes.
"""

import argparse
import json
import math
import signal
import socketserver
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any

# The protocol's number, changed when a change would break a client.
PROTOCOL: int = 1

# The port, which `sim/lcnc_sim.ini` also names.
PORT: int = 5008

# The longest request line (bytes), which holds a whole G-code file.
MAX_LINE: int = 64 * 1024 * 1024


# Function `to_json()`:
# One return for each kind of value reads best.
def to_json(value: Any) -> Any:  # pylint: disable=too-many-return-statements
    """Convert a value from the `linuxcnc` module to what JSON can hold.

    Arguments:
    * `value` (`Any`): The value.

    Returns:
    * (`Any`): The value, with tuples as lists, named tuples (such as
      `tool_table`'s entries) as objects, bytes as text, and a number
      that is not finite as `None`.
    """
    # Things JSON holds as they are.
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode(errors="replace")

    # Containers, whose items need converting too.
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    names: tuple[str, ...] = getattr(type(value), "__match_args__", ())
    if names:
        return {name: to_json(getattr(value, name)) for name in names}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    return str(value)


# Function `public_name()`:
def public_name(item: object, name: str) -> Any:
    """Return a public attribute of an object.

    Arguments:
    * `item` (`object`): The object.
    * `name` (`str`): The attribute's name.

    Returns:
    * (`Any`): The attribute.

    Raises:
    * `ValueError`: If it has no such public attribute.
    """
    if name.startswith("_") or not hasattr(item, name):
        raise ValueError(f"{type(item).__name__} has no {name!r}")
    return getattr(item, name)


# Class `SCBridge`:
class SCBridge:
    """Answers requests by calling the `linuxcnc` module.

    Attributes:
    * `linuxcnc` (`ModuleType`): The `linuxcnc` module.
    * `lock` (`threading.Lock`): Lets one request run at a time.
    * `on_shutdown` (`Callable[[], None]`): Called by `shutdown`.
    * `stat` (`Any`): The `linuxcnc.stat` object.
    * `command` (`Any`): The `linuxcnc.command` object.
    * `error_channel` (`Any`): The `linuxcnc.error_channel` object.
    """

    # Method `SCBridge.__init__()`:
    def __init__(
        self, linuxcnc: ModuleType, on_shutdown: Callable[[], None]
    ) -> None:
        """Connect to the running LinuxCNC.

        Arguments:
        * `linuxcnc` (`ModuleType`): The `linuxcnc` module.
        * `on_shutdown` (`Callable[[], None]`): Called by `shutdown`.
        """
        self.linuxcnc: ModuleType = linuxcnc
        self.lock: threading.Lock = threading.Lock()
        self.on_shutdown: Callable[[], None] = on_shutdown
        self.stat: Any = linuxcnc.stat()
        self.command: Any = linuxcnc.command()
        self.error_channel: Any = linuxcnc.error_channel()

    # Method `SCBridge.constant()`:
    def constant(self, argument: Any) -> Any:
        """Replace a `{"constant": NAME}` argument by its value.

        Arguments:
        * `argument` (`Any`): An argument from a request.

        Returns:
        * (`Any`): The value to call with.
        """
        if isinstance(argument, dict) and set(argument) == {"constant"}:
            return public_name(self.linuxcnc, str(argument["constant"]))
        return argument

    # Method `SCBridge.constants()`:
    def constants(self) -> dict[str, Any]:
        """Return the `linuxcnc` module's numbers and strings.

        Returns:
        * (`dict[str, Any]`): Their values, by name.
        """
        return {
            name: value
            for name, value in vars(self.linuxcnc).items()
            if not name.startswith("_")
            and isinstance(value, (int, float, str))
        }

    # Method `SCBridge.read_stat()`:
    def read_stat(self, names: list[str] | None = None) -> dict[str, Any]:
        """Return attributes of `linuxcnc.stat`, after a `poll()`.

        Arguments:
        * `names` (`list[str] | None`):
          The attributes to return, or `None` for all of them.

        Returns:
        * (`dict[str, Any]`): Their values, by name.
        """
        self.stat.poll()
        if names is None:
            names = [
                name
                for name in dir(self.stat)
                if not name.startswith("_")
                and not callable(getattr(self.stat, name))
            ]
        return {name: public_name(self.stat, name) for name in names}

    # Method `SCBridge.write_program()`:
    def write_program(self, name: str, text: str) -> str:
        """Write a file into `programs/`, beside the INI file.

        Arguments:
        * `name` (`str`): The file's name, with no directory.
        * `text` (`str`): Its contents.

        Returns:
        * (`str`): Its path, for `command.program_open`.

        Raises:
        * `ValueError`: If `name` is not a plain file name.
        """
        if name in ("", ".", "..") or Path(name).name != name or "\\" in name:
            raise ValueError(f"{name!r} is not a plain file name")
        self.stat.poll()
        directory: Path = Path(self.stat.ini_filename).parent / "programs"
        directory.mkdir(exist_ok=True)
        path: Path = directory / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    # Method `SCBridge.dispatch()`:
    # A flat list of calls reads best, so it has many returns.
    # pylint: disable-next=too-many-return-statements
    def dispatch(self, call: str, args: list[Any]) -> Any:
        """Run one call.

        Arguments:
        * `call` (`str`): What to call.
        * `args` (`list[Any]`): Its arguments.

        Returns:
        * (`Any`): What it returned.

        Raises:
        * `ValueError`: If there is no such call.
        """
        # The calls that have a fixed name.
        if call == "ping":
            version: str = str(getattr(self.linuxcnc, "version", ""))
            return {"protocol": PROTOCOL, "version": version}
        if call == "constants":
            return self.constants()
        if call == "stat":
            return self.read_stat(*args)
        if call == "error_channel.poll":
            return self.error_channel.poll()
        if call == "ini.find":
            self.stat.poll()
            return self.linuxcnc.ini(self.stat.ini_filename).find(*args)
        if call == "program.write":
            return self.write_program(*args)
        if call == "shutdown":
            self.on_shutdown()
            return None

        # The methods of `linuxcnc.command`.
        group, _, name = call.partition(".")
        if group == "command":
            method: Any = public_name(self.command, name)
            return method(*[self.constant(item) for item in args])
        raise ValueError(f"no call named {call!r}")

    # Method `SCBridge.answer()`:
    def answer(self, line: bytes) -> dict[str, Any]:
        """Answer one request line.

        Nothing a client sends may stop the bridge, so every exception
        becomes an error reply.

        Arguments:
        * `line` (`bytes`): The line of JSON.

        Returns:
        * (`dict[str, Any]`): The reply.
        """
        reply: dict[str, Any] = {}
        try:
            request: Any = json.loads(line)
            if not isinstance(request, dict):
                raise TypeError("a request must be a JSON object")
            if "id" in request:
                reply["id"] = request["id"]
            args: Any = request.get("args", [])
            if not isinstance(args, list):
                raise TypeError("`args` must be a list")
            with self.lock:
                result: Any = self.dispatch(str(request.get("call")), args)
            reply["result"] = to_json(result)
        # pylint: disable-next=broad-exception-caught
        except Exception as error:  # noqa: BLE001
            reply["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        return reply


# Class `SCServer`:
class SCServer(socketserver.ThreadingTCPServer):
    """The listening socket, with a thread for each connection.

    Attributes:
    * `bridge` (`SCBridge | None`): What answers the requests.
    """

    allow_reuse_address = True
    daemon_threads = True
    bridge: SCBridge | None = None


# Class `SCHandler`:
class SCHandler(socketserver.StreamRequestHandler):
    """Answers the request lines of one connection."""

    # Method `SCHandler.handle()`:
    def handle(self) -> None:
        """Answer each line until the client closes the connection."""
        assert isinstance(self.server, SCServer)
        bridge: SCBridge | None = self.server.bridge
        assert bridge is not None
        while True:
            line: bytes = self.rfile.readline(MAX_LINE + 1)
            if not line or len(line) > MAX_LINE:
                return
            reply: dict[str, Any] = bridge.answer(line)
            text: str = json.dumps(reply, allow_nan=False)
            self.wfile.write(f"{text}\n".encode())
            self.wfile.flush()


# Function `main()`:
def main() -> int:
    """Serve the port until told to stop.

    Returns:
    * (`int`): The exit status.
    """
    # The `linuxcnc` script runs its display with `-ini FILE`.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Give LinuxCNC's Python API to programs, on a port."
    )
    parser.add_argument("-ini", help="the INI file (given by LinuxCNC)")
    parser.add_argument("--port", type=int, default=PORT, help="the port")
    options: argparse.Namespace = parser.parse_args()

    # Imported here, since it exists only in the target, and the tests
    # of this file run anywhere.
    # pylint: disable-next=import-outside-toplevel,import-error
    import linuxcnc  # type: ignore[import-not-found]

    with SCServer(("127.0.0.1", options.port), SCHandler) as server:
        # `server.shutdown()` waits for `serve_forever()` to return, so
        # it can not be called from the thread running that.
        def stop() -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        def on_signal(_number: int, _frame: FrameType | None) -> None:
            stop()

        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)
        server.bridge = SCBridge(linuxcnc, stop)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
