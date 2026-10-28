"""Tests for `scplot.py`: run `python3 -m unittest -v`."""

import json
import math
import re
import unittest
from typing import Any, cast

from scgeometry import SCArc
from scplot import (
    command_moves,
    path_moves,
    plot_html,
    read_gcode,
    sketch_path,
)
from solidcraftcnc import SCCNC
from test_scgeometry import square
from test_solidcraftcnc import milling


# Class `TestPlot`:
class TestPlot(unittest.TestCase):
    """The moves a plot draws, and the page that draws them."""

    # Method `TestPlot.test_moves()`:
    def test_moves(self) -> None:
        """Lines go straight, and arcs and helices are broken up."""
        cnc: SCCNC = milling()
        cnc.rapid(x=1.0, y=0.0)
        cnc.linear(z=-0.1)
        cnc.arc(
            SCArc((1.0, 0.0), (0.0, 1.0), (0.0, 0.0), 1.0, math.pi / 2),
            z=-0.2,
        )
        moves = path_moves(cnc)

        # The rapids start where X and Y are not known yet.
        self.assertEqual([move["g"] for move in moves], [1, 3])
        self.assertEqual(moves[0]["pts"], [[1.0, 0.0, 2.0], [1.0, 0.0, -0.1]])
        self.assertEqual((moves[0]["f"], moves[0]["tool"]), (12.0, 1))
        arc = moves[1]["pts"]
        self.assertEqual(len(arc), 19)
        for point in arc:
            self.assertAlmostEqual(math.hypot(point[0], point[1]), 1.0)
        self.assertAlmostEqual(arc[9][2], -0.15)
        self.assertEqual(arc[-1], [0.0, 1.0, -0.2])

    # Method `TestPlot.test_drilling()`:
    def test_drilling(self) -> None:
        """A canned cycle is drawn as over, down, through and up."""
        cnc: SCCNC = milling()
        cnc.change_tool(2)
        cnc.rapid(x=0.0, y=0.0)
        cnc.drill([(1.0, 1.0), (2.0, 1.0)], -0.2)
        moves = path_moves(cnc)
        holes = [move for move in moves if move["g"] == 1]
        self.assertEqual(len(holes), 2)
        self.assertEqual(holes[1]["pts"], [[2.0, 1.0, 0.05], [2.0, 1.0, -0.2]])
        self.assertEqual((holes[1]["f"], holes[1]["tool"]), (4.0, 2))
        self.assertEqual(moves[-1]["pts"][-1], [2.0, 1.0, 1.0])

    # Method `TestPlot.test_read_gcode()`:
    def test_read_gcode(self) -> None:
        """A program's G-code reads back into the same moves."""
        cnc: SCCNC = milling()
        cnc.change_tool(2)
        cnc.rapid(x=0.0, y=0.0)
        cnc.drill([(1.0, 1.0), (2.0, 1.0)], -0.2)
        cnc.change_tool(1)
        cnc.rapid(x=1.0, y=0.0)
        cnc.linear(z=-0.1)
        cnc.arc(
            SCArc((1.0, 0.0), (0.0, 1.0), (0.0, 0.0), 1.0, math.pi / 2),
            z=-0.2,
        )
        commands = read_gcode(cnc.gcode())
        self.assertEqual(len(commands), len(cnc.commands))
        self.assertEqual(commands[0], {"comment": cnc.name})
        expected = path_moves(cnc)
        moves = command_moves(commands)
        self.assertEqual(len(moves), len(expected))
        for move, want in zip(moves, expected):
            self.assertEqual(
                (move["g"], move["line"], move["tool"]),
                (want["g"], want["line"], want["tool"]),
            )
            self.assertAlmostEqual(move["f"], want["f"])
            self.assertEqual(len(move["pts"]), len(want["pts"]))
            for point, want_point in zip(move["pts"], want["pts"]):
                for value, want_value in zip(point, want_point):
                    self.assertAlmostEqual(value, want_value, places=3)

    # Method `TestPlot.test_page()`:
    def test_page(self) -> None:
        """The page carries the program, its moves and the outlines."""
        cnc: SCCNC = milling()
        cnc.pocket(square(1.0, 0.125), -0.2, 0.1)
        cnc.finish()
        page: str = plot_html(cnc, [(square(1.0, 0.125), 0.0)], "A </b> test")
        self.assertIn("<title>A &lt;/b&gt; test</title>", page)
        found = re.search(r'id="path-data">(.*?)</script>', page, re.DOTALL)
        assert found is not None
        data = json.loads(found.group(1))
        self.assertEqual(data["lines"], cnc.gcode().splitlines())
        self.assertEqual(len(data["outlines"]), 1)
        self.assertEqual(len(data["outlines"][0]["pts"]), 8 * 8)
        self.assertGreater(len(data["moves"]), 10)

    # Method `TestPlot.test_sketch()`:
    def test_sketch(self) -> None:
        """The path goes into one 3D sketch per operation and kind."""
        cnc: SCCNC = milling()
        cnc.profile(square(1.0, 0.25), -0.1, 0.1)
        cnc.finish()
        fake: FakeSolidCraft = FakeSolidCraft()
        names: list[str] = sketch_path(cast(Any, fake), cnc, 25.4)
        self.assertEqual(
            names,
            [
                "Profile Square outside to Z-0.1 rapids",
                "Profile Square outside to Z-0.1 cuts",
            ],
        )
        self.assertEqual(
            [call[0] for call in fake.calls[:2]], ["create", "options"]
        )
        self.assertEqual(fake.calls[1][1], {"sketch_3d": True})

        # The cuts: the plunge and the sides are lines, the corners and
        # leads are splines, all in millimeters.  The corners are the
        # longest segments, so the cut starts in the middle of one,
        # which makes 5 corner splines and 2 leads.
        cuts: list[tuple[str, dict[str, Any]]] = fake.calls[
            [call[0] for call in fake.calls].index("create", 1) :
        ]
        kinds: list[str] = [call[0] for call in cuts]
        self.assertEqual(kinds.count("spline3d"), 7)
        first: list[list[float]] = cuts[2][1]["points"]
        self.assertAlmostEqual(first[0][2], 0.05 * 25.4)
        self.assertAlmostEqual(first[1][2], -0.1 * 25.4)


# Class `FakeSolidCraft`:
# Its commands come from `__getattr__()`, so `pylint` sees no public
# methods.
class FakeSolidCraft:  # pylint: disable=too-few-public-methods
    """Stands in for `SolidCraftPyBind`, recording the sketch commands.

    Attributes:
    * `calls` (`list[tuple[str, dict[str, Any]]]`): Each command's name
      and arguments.
    * `sketch` (`FakeSolidCraft`): Itself, for `solidcraft.sketch.X()`.
    """

    # Method `FakeSolidCraft.__init__()`:
    def __init__(self) -> None:
        """Start with no calls."""
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sketch: FakeSolidCraft = self

    # Method `FakeSolidCraft.__getattr__()`:
    def __getattr__(self, name: str) -> Any:
        """Return a function that records a call of a command.

        Arguments:
        * `name` (`str`): The command's name.

        Returns:
        * (`Any`): The recording function.
        """

        # Function `record()`:
        def record(**arguments: Any) -> dict[str, Any]:
            """Record a call.

            Arguments:
            * `arguments` (`Any`): The command's arguments.

            Returns:
            * (`dict[str, Any]`): An empty result.
            """
            self.calls.append((name, arguments))
            return {}

        return record


if __name__ == "__main__":
    unittest.main()
