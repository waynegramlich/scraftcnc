#!/usr/bin/env python3
"""Serve a headless SolidCraft session on a control port.

`solidcraft-cli mcp --headless` talks only on its standard input and
output, so one program can use it.  This serves one such session the
way a GUI started with `solidcraft --control PORT` serves itself:
one JSON line per request, `{"id", "method", "params"}` (the first
on a connection with the launch's `token`), and one JSON line per
reply.  Several programs (the panel, the watcher) can then share it.
Requests are run one at a time; only `engine.execute` works, as in
`HeadlessTransport`.

```
python3 -m scraftcnc.pybind.headless_server PORT
```

It writes the token to `control_dir()/PORT.token` (removed again on
exit) and runs until killed.
"""

import json
import secrets
import signal
import socket
import sys
import threading
from pathlib import Path
from types import FrameType

from .scraftpybind import (
    JSON,
    HeadlessTransport,
    SolidCraftError,
    control_dir,
)


# Class `HeadlessServer`:
class HeadlessServer:
    """One headless session, served on a control port.

    Attributes:
    * `lock` (`threading.Lock`): Lets one request at a time through.
    * `port` (`int`): The control port.
    * `token` (`str`): The token each connection must send first.
    * `transport` (`HeadlessTransport`): The session.
    """

    # Method `HeadlessServer.__init__()`:
    def __init__(self, port: int, allow_paths: tuple[str, ...]) -> None:
        """Make the server; nothing starts yet.

        Arguments:
        * `port` (`int`): The control port.
        * `allow_paths` (`tuple[str, ...]`): Folders the session may
          read and write (the model cache's, for STEP files).
        """
        self.lock: threading.Lock = threading.Lock()
        self.port: int = port
        self.token: str = secrets.token_hex(16)
        self.transport: HeadlessTransport = HeadlessTransport(
            allow_paths=allow_paths
        )

    # Method `HeadlessServer.answer()`:
    def answer(self, line: str, trusted: bool) -> tuple[str, bool]:
        """Answer one request line.

        Arguments:
        * `line` (`str`): The request.
        * `trusted` (`bool`): True once the connection sent the token.

        Returns:
        * (`tuple[str, bool]`): The reply line, and whether the
          connection is trusted now.
        """
        request: JSON = json.loads(line)
        if not isinstance(request, dict):
            return json.dumps({"ok": False, "error": "not an object"}), False
        reply: dict[str, JSON] = {"id": request.get("id")}
        if not trusted and request.get("token") != self.token:
            reply.update(ok=False, error="wrong token")
            return json.dumps(reply), False
        params: JSON = request.get("params") or {}
        try:
            with self.lock:
                result: JSON = self.run(
                    str(request.get("method")),
                    params if isinstance(params, dict) else {},
                )
            reply.update(ok=True, result=result)
        except (
            SolidCraftError,
            ConnectionError,
            OSError,
            ValueError,
        ) as error:
            reply.update(ok=False, error=str(error))
        return json.dumps(reply), True

    # Method `HeadlessServer.run()`:
    def run(self, method: str, params: dict[str, JSON]) -> JSON:
        """Run one request in the session.

        `engine.batch` goes to the MCP server's `batch` tool, which
        takes the same steps (as `plot.send_batch()` does headless).

        Arguments:
        * `method` (`str`): The method.
        * `params` (`dict[str, JSON]`): Its parameters.

        Returns:
        * (`JSON`): The result.

        Raises:
        * `SolidCraftError`: If it fails.
        """
        if method != "engine.batch":
            return self.transport.request(method, params)
        if self.transport.process is None:
            self.transport.start()
        result: JSON = self.transport.call(
            "tools/call", {"name": "batch", "arguments": params}
        )
        text: str = ""
        if isinstance(result, dict):
            content: JSON = result.get("content")
            if isinstance(content, list) and content:
                first: JSON = content[0]
                if isinstance(first, dict):
                    text = str(first.get("text", ""))
            if result.get("isError") is True:
                raise SolidCraftError(method, text, False, False)
        parsed: JSON = json.loads(text)
        return parsed

    # Method `HeadlessServer.serve_one()`:
    def serve_one(self, connection: socket.socket) -> None:
        """Answer one connection's requests until it closes.

        Arguments:
        * `connection` (`socket.socket`): The connection.
        """
        trusted: bool = False
        with connection, connection.makefile("rw", encoding="utf-8") as io:
            line: str
            for line in io:
                if not line.strip():
                    continue
                reply: str
                reply, trusted = self.answer(line, trusted)
                io.write(reply + "\n")
                io.flush()
                if not trusted:
                    return

    # Method `HeadlessServer.serve()`:
    def serve(self) -> None:
        """Start the session, write the token, and serve forever."""
        self.transport.start()
        token_file: Path = control_dir() / f"{self.port}.token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with socket.create_server(("127.0.0.1", self.port)) as server:
                token_file.write_text(self.token + "\n", encoding="utf-8")
                print(f"serving on {self.port}", flush=True)
                while True:
                    connection: socket.socket = server.accept()[0]
                    threading.Thread(
                        target=self.serve_one, args=(connection,), daemon=True
                    ).start()
        finally:
            token_file.unlink(missing_ok=True)
            self.transport.close()


# Function `stop()`:
def stop(_number: int, _frame: FrameType | None) -> None:
    """End the server on `SIGTERM`, so its cleanup runs.

    Arguments:
    * `_number` (`int`): The signal (unused).
    * `_frame` (`FrameType | None`): Where it came (unused).
    """
    raise SystemExit(0)


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Serve a headless session on the port given.

    Arguments:
    * `arguments` (`list[str]`): The port.

    Returns:
    * (`int`): The exit status.
    """
    if len(arguments) != 1 or not arguments[0].isdigit():
        print("usage: headless_server PORT", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, stop)
    server: HeadlessServer = HeadlessServer(
        int(arguments[0]), (str(Path.home()),)
    )
    try:
        server.serve()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
