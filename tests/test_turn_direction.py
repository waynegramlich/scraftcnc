"""Tests of which way a quarter turn about Z goes.

Quarter turns follow the right hand rule: counterclockwise about +Z,
so one turn sends +X to +Y.  `setups.py` (`SCPlacement`) hands
SolidCraft `90 * turns` degrees, and `model_cache.placement_matrix()`
builds the same turn as a matrix; both assume that SolidCraft's angle
is counterclockwise-positive.  (`T.emsagc~5.2` #52.)
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from scraftcnc import model_cache
from scraftcnc.pybind.scraftpybind import SCHeadlessTransport, SCPyBind

HERE: Path = Path(__file__).resolve().parent.parent
CLI: Path = HERE / "solidcraft/squashfs-root/usr/bin/solidcraft-cli"
PROGRAM: str | None = shutil.which("solidcraft-cli") or (
    str(CLI) if CLI.exists() else None
)


class TestMatrix(unittest.TestCase):
    """The placement matrix turns by the right hand rule."""

    def test_one_turn(self) -> None:
        """One quarter turn sends +X to +Y."""
        matrix: model_cache.Matrix = model_cache.placement_matrix(
            1, (0.0, 0.0, 0.0)
        )
        point: list[float] = [
            row[0] * 1.0 + row[1] * 0.0 + row[2] * 0.0 + row[3]
            for row in matrix
        ]
        self.assertEqual(point, [0.0, 1.0, 0.0])


@unittest.skipUnless(PROGRAM, "no solidcraft-cli")
class TestSolidCraft(unittest.TestCase):
    """SolidCraft turns by the right hand rule."""

    def test_quarter_turn(self) -> None:
        """A box along +X runs along +Y after a 90 degree turn."""
        assert PROGRAM is not None
        with (
            tempfile.TemporaryDirectory() as directory,
            SCHeadlessTransport(PROGRAM, (directory,)) as transport,
        ):
            solidcraft: SCPyBind = SCPyBind(transport)

            # A lopsided box, from the origin along +X, turned as
            # `SCPlacement` turns one.
            solidcraft.solid.box(30, 10, 5, body_name="Lopsided")
            solidcraft.solid.move(
                bodies=["Lopsided"], axis=(0, 0, 1), angle="90 deg"
            )
            reply: Any = cast(Any, solidcraft.model.faces(body="Lopsided"))

        # The face centroids of a box span its bounding box.
        centroids: list[list[float]] = [
            face["centroid"] for face in reply["faces"]
        ]
        xs: list[float] = [centroid[0] for centroid in centroids]
        ys: list[float] = [centroid[1] for centroid in centroids]
        self.assertAlmostEqual(min(xs), -10.0, places=6)
        self.assertAlmostEqual(max(xs), 0.0, places=6)
        self.assertAlmostEqual(min(ys), 0.0, places=6)
        self.assertAlmostEqual(max(ys), 30.0, places=6)


if __name__ == "__main__":
    unittest.main()
