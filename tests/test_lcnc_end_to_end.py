"""The whole path, end to end, with no display.

G-code from `demo.py`, through a `lcnc_hmi.py --headless`
pressed through its command port, to `serve_linuxcnc` and a real LinuxCNC
simulator.  This takes about two minutes and needs LinuxCNC installed
(`install_linuxcnc` from `scraftcam/lcnc/`) with nothing on its port, so
it runs only when asked:

```
SCRAFTCAM_LINUXCNC=1 python3 -m unittest -v test_lcnc_end_to_end
```
"""

# The server and the HMI outlive any `with` block, each thing that a
# person can do at the HMI is a test, and the path's test is one story.
# pylint: disable=consider-using-with,too-many-public-methods
# pylint: disable=too-many-locals

import itertools
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from scraftcam import shops
from scraftcam.lcnc import lcnc_client
from scraftcam.plot import PathMove, command_moves, read_gcode

HERE: Path = Path(__file__).resolve().parent.parent
SERVER_DIRECTORY: Path = HERE

# How near a position must be (inches).
NEAR: float = 0.001

# How long a step may take, and the whole demonstration (seconds).
STEP_TIME: float = 30.0
DEMO_TIME: float = 200.0

# A short program with two tools, and one long and slow move.
TWO_TOOLS: str = """G20 G90
T1 M6 G43 H1
G0 X0.5 Y0.5
T8 M6 G43 H8
G0 X1 Y1
M2
"""
SLOW_MOVE: str = """G20 G90
G1 X3 F6
M2
"""


# A straight line through space.
Segment = tuple[tuple[float, float, float], tuple[float, float, float]]

# How far a tool change can make the tip's Z read from the work (inches).
TOOL_CHANGE_Z: float = 20.0


def free_port() -> int:
    """Return a port that nothing is listening on."""
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port: int = unused.getsockname()[1]
    return port


def segment_distance(
    point: tuple[float, float, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> float:
    """Return how far a point is from a straight line segment."""
    along = [b - a for a, b in zip(start, end, strict=True)]
    length2 = sum(value * value for value in along)
    from_start = [p - a for p, a in zip(point, start, strict=True)]
    fraction = 0.0
    if length2 > 0.0:
        dot = sum(a * b for a, b in zip(along, from_start, strict=True))
        fraction = min(1.0, max(0.0, dot / length2))
    return math.dist(
        point, [a + fraction * b for a, b in zip(start, along, strict=True)]
    )


def path_segments(moves: list[PathMove]) -> list[Segment]:
    """Return the straight lines that the tool's tip may be on.

    `G43` at a tool change makes the tip's Z read differently while the
    machine stands still, by the difference in the tools' lengths, and
    the next move starts from there, which the moves do not show.  So a
    vertical line through each tool change is part of the path too.

    Arguments:
    * `moves` (`list[PathMove]`): The moves.

    Returns:
    * (`list[Segment]`): The lines.
    """
    segments: list[Segment] = [
        (
            (a[0], a[1], a[2]),
            (b[0], b[1], b[2]),
        )
        for move in moves
        for a, b in zip(move["pts"], move["pts"][1:], strict=False)
    ]
    for before, after in itertools.pairwise(moves):
        if before["tool"] != after["tool"]:
            x, y, _ = after["pts"][0]
            segments.append(((x, y, -TOOL_CHANGE_Z), (x, y, TOOL_CHANGE_Z)))
    return segments


@unittest.skipUnless(
    os.environ.get("SCRAFTCAM_LINUXCNC"), "SCRAFTCAM_LINUXCNC is not set"
)
class TestEndToEnd(unittest.TestCase):
    """A person's session at the HMI, against a real LinuxCNC."""

    directory: ClassVar[tempfile.TemporaryDirectory[str]]
    hmi: ClassVar[subprocess.Popen[bytes]]
    port: ClassVar[int]
    server: ClassVar[subprocess.Popen[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        """Start LinuxCNC's server, then the HMI."""
        cls.directory = tempfile.TemporaryDirectory()
        cls.server = subprocess.Popen(
            [sys.executable, "-u", "-m", "scraftcam.lcnc.serve_linuxcnc"],
            cwd=SERVER_DIRECTORY,
            stdout=subprocess.DEVNULL,
        )
        end: float = time.monotonic() + 120.0
        while True:
            try:
                with lcnc_client.BridgeClient(timeout=5.0):
                    break
            except OSError:
                if time.monotonic() > end or cls.server.poll() is not None:
                    cls.server.kill()
                    raise
                time.sleep(0.2)
        cls.start_hmi()
        cls.set_work_origin()

    @classmethod
    def set_work_origin(cls) -> None:
        """Set G54 to the demo's origin, (4, 3, -6) in, through the HMI.

        The HMI sets no origin when it starts (each program gets its
        own), and LinuxCNC keeps G54 from its last run.
        """

        def ask(line: str) -> str:
            with socket.create_connection(
                ("127.0.0.1", cls.port), 30.0
            ) as port:
                port.sendall(f"{line}\n".encode())
                return port.makefile().readline().strip()

        ask("type G20 G10 L2 P1 X4 Y3 Z-6")
        end: float = time.monotonic() + STEP_TIME
        while json.loads(ask("show"))["buttons"]["Execute"] != "normal":
            if time.monotonic() > end:
                raise TimeoutError("Execute never came up.")
            time.sleep(0.05)
        if ask("press Execute") != "ok":
            raise RuntimeError("The origin could not be set.")
        time.sleep(0.3)
        while "state=idle" not in ask("status"):
            if time.monotonic() > end:
                raise TimeoutError("The origin was never set.")
            time.sleep(0.05)
        ask("type ")

    @classmethod
    def start_hmi(cls) -> None:
        """Start an HMI, and wait until it answers."""
        cls.port = free_port()
        cls.hmi = subprocess.Popen(
            [sys.executable, "-m", "scraftcam.hmi.lcnc_hmi", "--headless",
             "--port", str(cls.port)],
            cwd=HERE,
        )  # fmt: skip
        end: float = time.monotonic() + STEP_TIME
        while time.monotonic() < end:
            try:
                socket.create_connection(("127.0.0.1", cls.port), 1.0).close()
                return
            except OSError:
                time.sleep(0.05)
        raise TimeoutError("The HMI never opened its port.")

    @classmethod
    def tearDownClass(cls) -> None:
        """Stop the HMI and LinuxCNC, and check that they stop."""
        cls.hmi.terminate()
        cls.hmi.wait(timeout=10.0)
        if cls.server.poll() is None:
            with lcnc_client.BridgeClient(timeout=10.0) as lcnc:
                lcnc.call("shutdown")
            cls.server.wait(timeout=60.0)
        cls.directory.cleanup()

    def setUp(self) -> None:
        """Start each test stopped, at the work origin, at full speed."""
        self.press("Reset")
        self.wait_idle()
        self.ask("speed 10")
        if self.shown()["buttons"]["Home"] == "normal":
            self.press("Home")
            self.wait_for("home", lambda: self.at(0.0, 0.0, 0.0))
            self.wait_idle()

    def ask(self, line: str) -> str:
        """Send one line to the HMI's port, and return its answer."""
        with socket.create_connection(("127.0.0.1", self.port), 30.0) as port:
            port.sendall(f"{line}\n".encode())
            return port.makefile().readline().strip()

    def press(self, label: str) -> None:
        """Press a button, which must not be greyed out."""
        self.assertEqual(self.ask(f"press {label}"), "ok", label)

    def shown(self) -> dict[str, Any]:
        """Return what the window shows."""
        shown: dict[str, Any] = json.loads(self.ask("show"))
        return shown

    def status(self) -> dict[str, str]:
        """Return the HMI's status, by name."""
        pairs = [word.split("=", 1) for word in self.ask("status").split()]
        return {pair[0]: pair[1] for pair in pairs}

    def position(self) -> tuple[float, float, float]:
        """Return the work position."""
        status = self.status()
        return (float(status["x"]), float(status["y"]), float(status["z"]))

    def at(self, x: float, y: float, z: float) -> bool:
        """Tell whether the machine is at a work position."""
        return math.dist(self.position(), (x, y, z)) < NEAR

    def wait_for(self, what: str, test: Callable[[], bool]) -> None:
        """Wait until something is true."""
        end: float = time.monotonic() + STEP_TIME
        while not test():
            if time.monotonic() > end:
                self.fail(f"Timed out waiting for {what}: {self.status()}")
            time.sleep(0.02)

    def wait_idle(self) -> None:
        """Wait until nothing is running."""
        self.wait_for("idle", lambda: self.status()["state"] == "idle")

    def execute(self, line: str) -> None:
        """Run an MDI line to its end, as a person would."""
        self.ask(f"type {line}")
        self.wait_for(
            "Execute",
            lambda: self.shown()["buttons"]["Execute"] == "normal",
        )
        self.press("Execute")
        time.sleep(0.3)
        self.wait_idle()

    def open_program(self, name: str, text: str) -> None:
        """Write a program here, and open it in the HMI.

        A program with no setup origin has its origin set where the
        tool is (the work origin, from `setUp()`), as an operator would.
        """
        file: Path = Path(self.directory.name, name)
        file.write_text(text, encoding="utf-8")
        self.assertEqual(self.ask(f"open {file}"), "ok")
        self.wait_for(
            "the program's lines",
            lambda: (
                self.shown()["coming"].split("\n")[0]
                == text.split("\n", maxsplit=1)[0]
            ),
        )
        if not self.shown()["origin_set"]:
            self.ask("answer yes")
            self.press("Set Origin")
            self.wait_idle()
        self.assertTrue(self.shown()["origin_set"])

    def messages(self) -> str:
        """Return every message LinuxCNC has sent, but tool prompts.

        The tool change prompts (`(MSG, Insert T..: ...)`, and a
        carousel's `(MSG, Swap tool ...)`) are left out: the headless
        HMI goes on from each one by itself.
        """
        text: str = self.ask("messages").removeprefix("messages:")
        return " | ".join(
            message.strip()
            for message in text.split(" | ")
            if message.strip()
            and not message.strip().startswith(("Insert T", "Swap tool"))
        )

    def test_start_up(self) -> None:
        """The HMI gets the shop's tools; the origin is well placed."""
        with lcnc_client.BridgeClient() as lcnc:
            table = lcnc.stat("tool_table")["tool_table"]
            g5x = lcnc.stat("g5x_offset")["g5x_offset"][:3]
        tools = {tool["id"] for tool in table if tool["id"] > 0}
        shop = shops.read(HERE / "examples/shop/home_shop.toml")
        self.assertEqual(tools, set(shops.loaded_tools(shop, "Shop mill")))
        self.assertEqual([round(value, 4) for value in g5x], [4.0, 3.0, -6.0])
        self.assertEqual(self.shown()["speed"], "10x")

    def test_mdi(self) -> None:
        """MDI lines move the machine; a bad one says why, and stays."""
        self.execute("G20 G90 G0 X1 Y2")
        self.assertTrue(self.at(1.0, 2.0, 0.0), self.position())
        before = self.position()
        self.execute("G0 Z30")
        self.wait_for(
            "a message",
            lambda: "work Z can reach only" in self.shown()["message"],
        )
        self.assertEqual(self.position(), before)

    def test_home(self) -> None:
        """Home goes to the origin, and greys out once there."""
        self.execute("G20 G90 G0 X1 Y1 Z1")
        self.assertEqual(self.shown()["buttons"]["Home"], "normal")
        self.press("Home")
        self.wait_for("home", lambda: self.at(0.0, 0.0, 0.0))
        self.wait_for(
            "Home to grey out",
            lambda: self.shown()["buttons"]["Home"] == "disabled",
        )

    def test_jog(self) -> None:
        """A jog moves one axis by the step chosen."""
        self.press(".1")
        self.press("+X")
        self.wait_for("+X", lambda: self.at(0.1, 0.0, 0.0))
        self.press(".01")
        self.press("-Z")
        self.wait_for("-Z", lambda: self.at(0.1, 0.0, -0.01))

    def test_set_origin(self) -> None:
        """Set Origin asks first; then the position is the new zero."""
        self.addCleanup(self.execute, "G20 G10 L2 P1 X4 Y3 Z-6")
        self.execute("G20 G90 G0 X1 Y1")
        self.press("Set Origin")
        time.sleep(0.3)
        self.assertTrue(self.at(1.0, 1.0, 0.0))
        self.ask("answer yes")
        self.press("Set Origin")
        self.wait_for("the new origin", lambda: self.at(0.0, 0.0, 0.0))

    def test_tool_buttons(self) -> None:
        """Start runs from where +Tool put the start line."""
        self.open_program("two_tools.ngc", TWO_TOOLS)
        self.press("+Tool")
        self.press("+Tool")
        self.wait_for(
            "the second tool's line",
            lambda: self.shown()["coming"].startswith("T8 M6"),
        )
        self.press("Start")
        self.wait_for("T8", lambda: self.status()["tool"] == "8")
        time.sleep(0.3)
        self.wait_idle()
        self.assertEqual(self.position()[:2], (1.0, 1.0))
        self.assertEqual(self.messages(), "")

    def test_pause_resume_reset(self) -> None:
        """Pause holds the position, Resume goes on, and Reset stops."""
        self.ask("speed 1")
        self.open_program("slow.ngc", SLOW_MOVE)
        self.press("Start")
        self.wait_for("moving", lambda: self.position()[0] > 0.05)
        self.wait_for(
            "Start to grey out",
            lambda: self.shown()["buttons"]["Start"] == "disabled",
        )
        self.assertIn("greyed out", self.ask("press +X"))
        self.press("Pause")
        self.wait_for("paused", lambda: self.status()["state"] == "paused")
        time.sleep(0.2)
        held = self.position()
        time.sleep(0.3)
        self.assertEqual(self.position(), held)
        self.wait_for(
            "Resume",
            lambda: self.shown()["buttons"].get("Resume") == "normal",
        )
        self.press("Resume")
        self.wait_for("moving", lambda: self.position()[0] > held[0])
        self.press("Reset")
        self.wait_idle()
        stopped = self.position()
        time.sleep(0.3)
        self.assertLess(stopped[0], 3.0)
        self.assertEqual(self.position(), stopped)
        self.assertEqual(self.shown()["buttons"]["Start"], "normal")

    def test_hmi_closed_and_opened(self) -> None:
        """LinuxCNC outlives the HMI; a new one keeps what it had."""
        self.open_program("kept.ngc", TWO_TOOLS)
        self.execute("G20 G90 G0 X2 Y1")
        self.press("Quit")
        self.assertEqual(self.hmi.wait(timeout=10.0), 0)
        self.assertIsNone(self.server.poll())
        self.start_hmi()
        self.assertTrue(self.at(2.0, 1.0, 0.0), self.position())
        self.assertTrue(self.status()["file"].endswith("kept.ngc"))
        self.wait_for(
            "the program's lines",
            lambda: self.shown()["coming"].startswith("G20 G90"),
        )

    def test_path_of_the_demonstration(self) -> None:
        """The whole demonstration: every sample lies on its path."""
        done = subprocess.run(
            [sys.executable, "-m", "scraftcam.demo"],
            cwd=HERE,
            capture_output=True,
            text=True,
            check=True,
        )
        moves: list[PathMove] = command_moves(read_gcode(done.stdout))
        self.open_program("demo.ngc", done.stdout)

        # Run it, following the machine.
        self.press("Start")
        samples: list[tuple[int, int, tuple[float, float, float]]] = []
        started: bool = False
        end: float = time.monotonic() + DEMO_TIME
        while time.monotonic() < end:
            status = self.status()
            state: str = status["state"]
            started = started or state != "idle"
            if started and state == "idle":
                break
            if started:
                samples.append(
                    (
                        int(status["line"]),
                        int(status["tool"]),
                        (
                            float(status["x"]),
                            float(status["y"]),
                            float(status["z"]),
                        ),
                    )
                )
            time.sleep(0.05)
        else:
            self.fail(f"Not done: {self.status()}")

        # The only messages are the tool change prompts (`MSG`), each
        # paused at and gone on from by the headless HMI.
        self.assertEqual(self.messages(), "")

        # The tools came in the program's order.
        tools: list[int] = []
        for _, tool, _ in samples:
            if tool and tool not in tools:
                tools.append(tool)
        planned: list[int] = []
        for move in moves:
            if move["tool"] and move["tool"] not in planned:
                planned.append(move["tool"])
        self.assertEqual(tools, planned)

        # Every sample lies on the path, from the first move that the
        # path knows the start of.  `line` counts from 1, `move` from 0.
        segments: list[Segment] = path_segments(moves)
        first: int = moves[0]["line"] + 1
        worst = sorted(
            (
                (
                    min(
                        segment_distance(point, *segment)
                        for segment in segments
                    ),
                    line,
                    tool,
                    point,
                )
                for line, tool, point in samples
                if line > first
            ),
            reverse=True,
        )
        self.assertGreater(len(worst), 500)
        self.assertLess(worst[0][0], NEAR, worst[:5])

        # It went through the whole program.
        lines: list[int] = [sample[0] for sample in samples]
        self.assertGreater(max(lines), moves[-1]["line"] - 5)

    def test_zz_server_stops_under_the_hmi(self) -> None:
        """The HMI reports a LinuxCNC that has gone, and stays up."""
        with lcnc_client.BridgeClient(timeout=10.0) as lcnc:
            lcnc.call("shutdown")
        self.server.wait(timeout=60.0)
        self.wait_for(
            "the message",
            lambda: "not answering" in self.shown()["message"],
        )
        self.assertEqual(self.ask("ping"), "ok")
        self.assertIsNone(self.hmi.poll())
