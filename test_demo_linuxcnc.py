"""Tests for `demo_linuxcnc.py` that need no LinuxCNC or target."""

import socket
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import demo_linuxcnc
from install_linuxcnc import Target

# What `sim_linuxcnc.py` prints at the end of a good run, and of one
# where LinuxCNC sent an error.
GOOD: str = """tools: /x/shop_mill.tbl
running /x/demo.ngc
 294.000   600    0.1000    0.2000    2.0000
done: 5895 samples in 295.1 s, in sim_positions.txt
exit 0"""
BAD: str = """running /x/demo.ngc
error: Requested tool 8 not found in the tool table
exit 0"""


class TestDemoLinuxCNC(unittest.TestCase):
    """The parts of the demonstration runner that work offline."""

    def test_parse_result(self) -> None:
        """The samples, the time and LinuxCNC's errors are found."""
        result = demo_linuxcnc.parse_result(GOOD)
        self.assertEqual((result.samples, result.seconds), (5895, 295.1))
        self.assertEqual(result.errors, [])
        result = demo_linuxcnc.parse_result(BAD)
        self.assertEqual(result.samples, 0)
        self.assertEqual(
            result.errors, ["Requested tool 8 not found in the tool table"]
        )

    def test_pack(self) -> None:
        """Files are packed with Unix line endings, links resolved."""
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            project = root / "project"
            (project / "lcnc_sim").mkdir(parents=True)
            (project / "lcnc_sim/mill.ini").write_bytes(b"[EMC]\r\nA = 1\r\n")
            (project / "a.py").write_bytes(b"print(1)\r\n")
            (project / "run.py").write_bytes(b"#!/bin/sh\r\n")
            (project / "notes.md").write_text("not packed\n")
            (root / "other").mkdir()
            (root / "other/lib.py").write_text("X = 1\n")
            # How a Windows checkout writes a symbolic link.
            (project / "lib.py").write_text("../other/lib.py")
            tarball = root / "demo.tar"
            self.assertEqual(demo_linuxcnc.pack(project, tarball), 4)
            with tarfile.open(tarball) as tar:
                names = sorted(tar.getnames())
                self.assertEqual(tar.getmember("run.py").mode, 0o755)
                self.assertEqual(tar.getmember("a.py").mode, 0o644)
                contents: dict[str, bytes] = {}
                for name in names:
                    member = tar.extractfile(name)
                    assert member is not None
                    contents[name] = member.read()
        self.assertEqual(
            names, ["a.py", "lcnc_sim/mill.ini", "lib.py", "run.py"]
        )
        self.assertEqual(contents["lcnc_sim/mill.ini"], b"[EMC]\nA = 1\n")
        self.assertEqual(contents["a.py"], b"print(1)\n")
        self.assertEqual(contents["lib.py"], b"X = 1\n")
        self.assertEqual(contents["run.py"], b"#!/bin/sh\n")

    def test_xvfb_listen(self) -> None:
        """TCP only when the socket directory can not be written."""
        listen = demo_linuxcnc.xvfb_listen
        with tempfile.TemporaryDirectory() as scratch:
            sockets = Path(scratch)
            self.assertEqual(listen(sockets / "none")[1], "")
            self.assertEqual(listen(sockets), (["-nolisten", "tcp"], ""))
            with mock.patch("os.access", return_value=False):
                arguments, host = listen(sockets)
        self.assertEqual(arguments, ["-listen", "tcp", "-nolisten", "unix"])
        self.assertEqual(host, "127.0.0.1")

    def test_panel_errors(self) -> None:
        """Messages are found; no answer counts as a problem."""
        errors = demo_linuxcnc.panel_errors
        self.assertEqual(errors("messages: "), [])
        # What `ask_panel()` returns for no messages: its space stripped.
        self.assertEqual(errors("messages:"), [])
        self.assertEqual(errors("messages: a | b"), ["a", "b"])
        self.assertEqual(len(errors("")), 1)

    def test_ask_panel(self) -> None:
        """A line goes to the port and its answer comes back."""
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            port = server.getsockname()[1]

            def answer() -> None:
                connection = server.accept()[0]
                with connection:
                    if connection.recv(100) == b"ping\n":
                        connection.sendall(b"ok\n")

            thread = threading.Thread(target=answer)
            thread.start()
            self.assertEqual(demo_linuxcnc.ask_panel("ping", port), "ok")
            thread.join()

        # Nobody is listening now.
        self.assertEqual(demo_linuxcnc.ask_panel("ping", port), "")

    def test_place_project_shared(self) -> None:
        """A box that sees the project uses it where it is."""
        box = Target(
            name="the box",
            root=("podman", "exec", "-u", "root", "box"),
            user=("podman", "exec", "box"),
            home="/home/me",
            shares_home=True,
            enter="",
        )
        with mock.patch.object(demo_linuxcnc, "run", return_value=True):
            self.assertEqual(
                demo_linuxcnc.place_project(box), str(demo_linuxcnc.PROJECT)
            )

    def test_place_project_copied(self) -> None:
        """Another target gets a copy, unpacked as the user."""
        wsl = Target(
            name="WSL",
            root=("wsl.exe", "-u", "root"),
            user=("wsl.exe",),
            home="/home/lcnc",
            shares_home=False,
            enter="",
        )
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> bool:
            commands.append(command)
            return True

        with (
            tempfile.TemporaryDirectory() as scratch,
            mock.patch.object(demo_linuxcnc, "run", fake_run),
            mock.patch("install_linuxcnc.run", fake_run),
            mock.patch("install_linuxcnc.CACHE", Path(scratch)),
        ):
            where = demo_linuxcnc.place_project(wsl)
        self.assertEqual(where, "/home/lcnc/scraftcnc_demo")
        self.assertEqual(
            commands[0],
            [
                "wsl.exe",
                "-u",
                "root",
                "sh",
                "-c",
                "cat > /tmp/scraftcnc_demo.tar",
            ],
        )
        self.assertEqual(commands[1][:3], ["wsl.exe", "sh", "-c"])
        self.assertIn("tar -xf /tmp/scraftcnc_demo.tar", commands[1][3])


if __name__ == "__main__":
    unittest.main()
