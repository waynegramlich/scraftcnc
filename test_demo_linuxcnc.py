"""Tests for `demo_linuxcnc.py` that need no LinuxCNC or target."""

import tarfile
import tempfile
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
            (project / "notes.md").write_text("not packed\n")
            (root / "other").mkdir()
            (root / "other/lib.py").write_text("X = 1\n")
            # How a Windows checkout writes a symbolic link.
            (project / "lib.py").write_text("../other/lib.py")
            tarball = root / "demo.tar"
            self.assertEqual(demo_linuxcnc.pack(project, tarball), 3)
            with tarfile.open(tarball) as tar:
                names = sorted(tar.getnames())
                contents: dict[str, bytes] = {}
                for name in names:
                    member = tar.extractfile(name)
                    assert member is not None
                    contents[name] = member.read()
        self.assertEqual(names, ["a.py", "lcnc_sim/mill.ini", "lib.py"])
        self.assertEqual(contents["lcnc_sim/mill.ini"], b"[EMC]\nA = 1\n")
        self.assertEqual(contents["a.py"], b"print(1)\n")
        self.assertEqual(contents["lib.py"], b"X = 1\n")

    def test_place_project_shared(self) -> None:
        """A box that sees the project uses it where it is."""
        box = Target(
            name="the box",
            root=("podman", "exec", "-u", "root", "box"),
            user=("podman", "exec", "box"),
            home="/home/me",
            joined=False,
            shares_home=True,
            enter="",
        )
        with mock.patch.object(demo_linuxcnc, "run", return_value=True):
            self.assertEqual(
                demo_linuxcnc.place_project(box), str(demo_linuxcnc.PROJECT)
            )

    def test_place_project_copied(self) -> None:
        """Another target gets a copy, unpacked as the user."""
        vm = Target(
            name="the VM",
            root=("ssh", "vm", "sudo"),
            user=("ssh", "vm"),
            home="/home/debian",
            joined=True,
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
            where = demo_linuxcnc.place_project(vm)
        self.assertEqual(where, "/home/debian/scraftcnc_demo")
        self.assertEqual(
            commands[0],
            ["ssh", "vm", "sudo", "sh -c 'cat > /tmp/scraftcnc_demo.tar'"],
        )
        self.assertEqual(commands[1][:2], ["ssh", "vm"])
        self.assertIn("tar -xf /tmp/scraftcnc_demo.tar", commands[1][2])


if __name__ == "__main__":
    unittest.main()
