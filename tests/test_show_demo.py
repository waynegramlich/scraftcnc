#!/usr/bin/env python3
"""Tests of `show_demo.py` that start nothing."""

import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# Run as `./tests/test_show_demo.py` too: the repository root goes on
# the path, so that `show_demo` can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import show_demo
from scraftcnc.pybind import headless_server


class TestLeftovers(unittest.TestCase):
    """What may be removed of a SolidCraft that has gone."""

    def setUp(self) -> None:
        # pylint: disable-next=consider-using-with
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)

    def test_recovery_files_of_one_only(self) -> None:
        """Another SolidCraft's recovery files are left alone."""
        for name in (
            "100-386091-10.json",
            "100-386091-10.sc",
            "100-3860-10.sc",
            "386091.sc",
        ):
            (self.directory / name).write_text("", encoding="utf-8")
        found = show_demo.recovery_files(self.directory, 386091)
        self.assertEqual(
            sorted(path.name for path in found),
            ["100-386091-10.json", "100-386091-10.sc"],
        )

    def test_no_recovery_directory(self) -> None:
        """No directory means no files."""
        self.assertEqual(
            show_demo.recovery_files(self.directory / "none", 1), []
        )

    def test_stale_pid_file(self) -> None:
        """A dead process's file is stale; a living one's is not."""
        pid_file = self.directory / "8080.pid"
        pid_file.write_text("999999999 1\n", encoding="utf-8")
        self.assertEqual(
            show_demo.stale_pid_files(self.directory, 8080), [pid_file]
        )
        pid_file.write_text(f"{os.getpid()} 1\n", encoding="utf-8")
        self.assertEqual(show_demo.stale_pid_files(self.directory, 8080), [])
        self.assertEqual(show_demo.stale_pid_files(self.directory, 1), [])


class TestChecks(unittest.TestCase):
    """What stops a show before anything starts."""

    def test_port_in_use(self) -> None:
        """A port in use is refused, by name."""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with (
                mock.patch.dict(os.environ, {"DISPLAY": ":0"}),
                mock.patch("shutil.which", return_value="/x"),
                mock.patch.object(
                    show_demo,
                    "SERVER_PROJECT",
                    Path(__file__).parent.parent,
                ),
                self.assertRaisesRegex(
                    show_demo.DemoShowFailed, "for SolidCraft"
                ),
            ):
                show_demo.check_ready({"SolidCraft": port})

    def test_no_display(self) -> None:
        """With no display, nothing can be shown."""
        with (
            mock.patch.dict(os.environ, clear=True),
            self.assertRaisesRegex(show_demo.DemoShowFailed, "no display"),
        ):
            show_demo.check_ready({})

    def test_no_solidcraft(self) -> None:
        """A missing SolidCraft says where it looked."""
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch.object(show_demo, "SOLIDCRAFT_BESIDE", Path("/no/x")),
            self.assertRaisesRegex(show_demo.DemoShowFailed, "No SolidCraft"),
        ):
            show_demo.find_solidcraft("")


class TestReport(unittest.TestCase):
    """The session report, from inspected bodies and sketches."""

    def test_report(self) -> None:
        """Bodies, sketches, and the path's offset from the plate."""
        bodies: list[dict[str, Any]] = [
            {"name": "Plate", "bbox": {"min": [0, 0, -5], "max": [10, 20, 0]}},
            {"name": "Vise", "bbox": {"min": [-1, -1, -9], "max": [1, 1, -5]}},
        ]
        sketches: list[dict[str, Any]] = [
            {"name": "stock_1", "wires": [
                {"start": [-50, -50, 0], "end": [50, 50, 0]}]},
            {"name": "T01 path", "wires": [
                {"start": [1, 2, 3], "end": [11, 22, -1]},
                {"start": [11, 22, -1], "end": [3, 4, 5]}]},
            {"name": "empty", "wires": []},
        ]  # fmt: skip
        lines = show_demo.session_report(bodies, sketches)
        self.assertEqual(lines[0], "2 bodies:")
        self.assertIn(
            "  Plate: [0.00 0.00 -5.00] .. [10.00 20.00 0.00]", lines
        )
        self.assertIn("3 sketches:", lines)
        self.assertIn(
            "  T01 path: 2 wires, [1.00 2.00 -1.00] .. [11.00 22.00 5.00]",
            lines,
        )
        self.assertIn("  empty: 0 wires, empty", lines)
        self.assertEqual(
            lines[-1], "Path middle - plate middle: X 1.00 mm, Y 2.00 mm"
        )

    def test_edge_box(self) -> None:
        """A body's box comes from its edges' world points.

        `document.inspect` gives boxes in a component's own frame,
        which showed placed tooling at the origin (`T.hlp~3.3.1`).
        """
        edges: list[dict[str, Any]] = [
            {"start": [100, 200, 300], "mid": [110, 205, 300],
             "end": [120, 210, 300]},
            {"start": [120, 210, 300], "mid": [120, 210, 310],
             "end": [120, 210, 320]},
        ]  # fmt: skip
        self.assertEqual(
            show_demo.edge_box(edges),
            ((100, 200, 300), (120, 210, 320)),
        )
        self.assertIsNone(show_demo.edge_box([]))

    def test_no_plate(self) -> None:
        """With no plate there is no offset line."""
        lines = show_demo.session_report([], [])
        self.assertEqual(lines[-1], "Tool path: empty")


class TestHeadlessServer(unittest.TestCase):
    """The headless server's token and request handling."""

    def setUp(self) -> None:
        self.server = headless_server.HeadlessServer(0, ())
        self.calls: list[tuple[str, object]] = []

        def request(method: str, params: object) -> object:
            """Record a request, and answer it."""
            self.calls.append((method, params))
            return {"done": method}

        self.server.transport = mock.Mock(request=request)

    def test_token(self) -> None:
        """A wrong token is refused; the right one trusts the line."""
        reply, trusted = self.server.answer(
            json.dumps({"id": 1, "method": "m", "token": "no"}), False
        )
        self.assertFalse(trusted)
        self.assertEqual(json.loads(reply)["error"], "wrong token")
        reply, trusted = self.server.answer(
            json.dumps(
                {"id": 2, "method": "engine.execute", "params": {"a": 1},
                 "token": self.server.token}
            ),
            False,
        )  # fmt: skip
        self.assertTrue(trusted)
        self.assertEqual(
            json.loads(reply), {"id": 2, "ok": True, "result": {
                "done": "engine.execute"}}
        )  # fmt: skip
        self.assertEqual(self.calls, [("engine.execute", {"a": 1})])

    def test_error(self) -> None:
        """A failing request answers `ok: false` with the error."""
        self.server.transport = mock.Mock(
            request=mock.Mock(side_effect=ConnectionError("gone"))
        )
        reply, trusted = self.server.answer(
            json.dumps({"id": 3, "method": "x"}), True
        )
        self.assertTrue(trusted)
        self.assertEqual(json.loads(reply)["error"], "gone")


if __name__ == "__main__":
    unittest.main()
