"""Tests of `scraftcam.gui.port` and the GUI's `CommandServer`."""

import json
import socket
import tempfile
import time
import unittest
from pathlib import Path

from scraftcam.gui import port, window
from scraftcam.gui.app import App
from tests import qt_app


# Function `request()`:
def request(method: str, **params: object) -> str:
    """Return a request line.

    Arguments:
    * `method` (`str`): The method.
    * `params` (`object`): Its parameters.

    Returns:
    * (`str`): One line of JSON.
    """
    return json.dumps({"id": 7, "method": method, "params": params})


class ReplyTest(unittest.TestCase):
    """Tests of `reply()`, with no Qt."""

    def test_errors(self) -> None:
        """Bad lines, methods and parameters answer JSON-RPC errors."""

        def echo(params: dict[str, object]) -> object:
            return port.text_param(params, "text")

        methods: dict[str, port.Method] = {"echo": echo}
        cases: list[tuple[str, int]] = [
            ("{", port.PARSE_ERROR),
            ("[1]", port.INVALID_REQUEST),
            ("{}", port.INVALID_REQUEST),
            (request("nope"), port.METHOD_NOT_FOUND),
            ('{"method": "echo", "params": 3}', port.INVALID_PARAMS),
            (request("echo"), port.INVALID_PARAMS),
        ]
        line: str
        code: int
        for line, code in cases:
            answer: dict[str, object] = json.loads(port.reply(line, methods))
            error: object = answer["error"]
            assert isinstance(error, dict)
            self.assertEqual(error["code"], code, line)
        self.assertEqual(
            json.loads(port.reply(request("echo", text="hi"), methods)),
            {"jsonrpc": "2.0", "id": 7, "result": "hi"},
        )


class ServerTest(unittest.TestCase):
    """Tests of `CommandServer`, through a real socket."""

    def setUp(self) -> None:
        """A window and a server on a free port."""
        window.WINDOWS.clear()
        self.model: App = App(None, None)
        self.top: window.Window = window.Window(self.model, {"shop mill"})
        self.top.show()
        self.server: window.CommandServer = window.CommandServer(self.model)
        self.assertTrue(self.server.listen_local(0))
        self.connection: socket.socket = socket.create_connection(
            ("127.0.0.1", self.server.serverPort())
        )
        self.connection.settimeout(0.01)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.server.close)
        self.addCleanup(window.WINDOWS.clear)

    def ask(self, method: str, **params: object) -> dict[str, object]:
        """Send a request, and wait for its answer.

        Arguments:
        * `method` (`str`): The method.
        * `params` (`object`): Its parameters.

        Returns:
        * (`dict[str, object]`): The answer.
        """
        self.connection.sendall((request(method, **params) + "\n").encode())
        received: bytes = b""
        _try: int
        for _try in range(300):
            qt_app.process_events()
            try:
                received += self.connection.recv(4096)
            except TimeoutError:
                continue
            if received.endswith(b"\n"):
                break
        answer: object = json.loads(received)
        assert isinstance(answer, dict)
        return answer

    def test_status_press_quit(self) -> None:
        """`status`, `press` (hidden refused) and `quit` (refused)."""
        status: object = self.ask("status")["result"]
        assert isinstance(status, dict)
        self.assertEqual(status["shop"], "(none)")
        self.assertEqual(
            status["windows"],
            [
                {
                    "buttons": ["Tree", "+ Panel", "x", "New Shop"],
                    "tree": True,
                    "panels": 1,
                }
            ],
        )
        self.assertEqual(
            self.ask("press", button="Tree")["result"], "pressed Tree"
        )
        self.assertTrue(self.top.tree.isHidden())
        self.assertIn("error", self.ask("press", button="Stop All"))
        self.assertIn("error", self.ask("press", button="Tree", window=3))

        # `quit` refused while the window's machine runs, then done.
        self.model.start_machine("shop mill")
        refused: object = self.ask("quit")["error"]
        assert isinstance(refused, dict)
        self.assertEqual(refused["message"], "Stop the shop mill first")
        self.model.stop_machine("shop mill")
        self.assertEqual(self.ask("quit")["result"], "quitting")
        _try: int
        for _try in range(100):
            qt_app.process_events()
            if not self.top.isVisible():
                break
            time.sleep(0.01)
        self.assertEqual(window.WINDOWS, [])

    def test_new_shop(self) -> None:
        """`new_shop` makes a shop, or says why not."""
        with tempfile.TemporaryDirectory() as temporary:
            directory: str = str(Path(temporary) / "shop")
            made: dict[str, object] = self.ask(
                "new_shop",
                directory=directory,
                name="Lab",
                units="in",
                machines=["cnc_mill"],
            )
            self.assertTrue(str(made["result"]).endswith("shop.toml"))
            self.assertEqual(self.model.shop_title, "Lab")
            self.assertIn(
                "error",
                self.ask(
                    "new_shop",
                    directory=directory,
                    name="Lab",
                    units="in",
                    machines=[3],
                ),
            )

    def test_tree_and_select(self) -> None:
        """`tree` lists the items; `select` clicks one."""
        with tempfile.TemporaryDirectory() as temporary:
            directory: Path = Path(temporary) / "shop"
            self.ask(
                "new_shop",
                directory=str(directory),
                name="Lab",
                units="in",
                machines=[],
            )
            self.assertEqual(self.ask("tree")["result"], [["Lab (shop)"]])
            shown: object = self.ask(
                "select", path=str(directory / "shop.toml")
            )["result"]
            assert isinstance(shown, dict)
            self.assertEqual(shown["label"], "Lab (shop)")
            self.assertIn('name = "Lab"', str(shown["text"]))
            self.assertIn("error", self.ask("select", path="/nowhere"))


if __name__ == "__main__":
    unittest.main()
