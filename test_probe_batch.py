"""Tests of `probe_batch.py`'s grouping and steps (no SolidCraft)."""

import itertools
import math
import unittest

from probe_batch import (
    MAX_POINTS,
    arc_steps,
    group_moves,
    path_steps,
    sketch_steps,
)
from scplot import Move, SpacePoint, command_moves, read_gcode

# A small program: a rapid, a cut, a jump, an arc, a tool change.
GCODE: str = """(Tool 4)
T04 M6 G43 H04
G0 X0 Y0 Z1
G1 Z0 F10
G1 X1
G0 Z1
G0 X2 Y0
G1 Z0
G3 X2 Y0 I1 J0
T08 M6 G43 H08
G0 Z1
G1 X3 Z0.5
"""


def _move(code: int, points: list[SpacePoint], tool: int = 1) -> Move:
    """Return a move for a test."""
    return {"g": code, "line": 0, "pts": points, "f": 1.0, "tool": tool}


class TestProbeBatch(unittest.TestCase):
    """The grouping and the batch steps."""

    def test_group_moves(self) -> None:
        """Moves group by tool, cuts apart from rapids, in order."""
        moves: list[Move] = command_moves(read_gcode(GCODE))
        groups: dict[str, list[Move]] = group_moves(moves, False)
        self.assertEqual(
            list(groups), ["T04 cuts", "T04 rapids", "T08 rapids", "T08 cuts"]
        )
        self.assertTrue(all(m["g"] == 0 for m in groups["T04 rapids"]))
        self.assertTrue(all(m["g"] != 0 for m in groups["T04 cuts"]))
        mixed: dict[str, list[Move]] = group_moves(moves, True)
        self.assertEqual(list(mixed), ["T04 path", "T08 path"])
        self.assertEqual(sum(map(len, mixed.values())), len(moves))

    def test_jumps_split_polylines(self) -> None:
        """A jump starts a new `sketch.line3d`; joined moves share one."""
        moves: list[Move] = [
            _move(1, [[0, 0, 0], [1, 0, 0]]),
            _move(1, [[1, 0, 0], [1, 1, 0]]),
            _move(1, [[5, 5, 0], [6, 5, 0]]),
            _move(1, [[6, 5, 0], [6, 5, 0]]),
        ]
        steps = path_steps(moves, 2.0, False)
        self.assertEqual(
            [step["params"] for step in steps],
            [
                {"points": [[0, 0, 0], [2, 0, 0], [2, 2, 0]]},
                {"points": [[10, 10, 0], [12, 10, 0]]},
            ],
        )

    def test_long_polylines_split(self) -> None:
        """A polyline longer than `MAX_POINTS` shares its split points."""
        count: int = 2 * MAX_POINTS + 10
        points: list[SpacePoint] = [[i, 0.0, 0.0] for i in range(count)]
        steps = path_steps([_move(1, points)], 1.0, False)
        pieces: list[list[SpacePoint]] = []
        for step in steps:
            params = step["params"]
            assert isinstance(params, dict)
            piece = params["points"]
            assert isinstance(piece, list)
            self.assertLessEqual(len(piece), MAX_POINTS)
            pieces.append(piece)
        self.assertEqual(len(pieces), 3)
        for first, second in itertools.pairwise(pieces):
            self.assertEqual(first[-1], second[0])
        self.assertEqual(sum(len(p) - 1 for p in pieces), count - 1)

    def test_arcs(self) -> None:
        """A planar arc is one `sketch.arc3d`, a circle two; not helices."""
        moves: list[Move] = command_moves(read_gcode(GCODE))
        steps = path_steps(moves, 1.0, True)
        commands: list[object] = [step["command"] for step in steps]
        self.assertEqual(commands.count("sketch.arc3d"), 2)
        circle = [s["params"] for s in steps if s["command"] == "sketch.arc3d"]
        for params in circle:
            assert isinstance(params, dict)
            for key in ("start", "through", "end"):
                point = params[key]
                assert isinstance(point, list)
                self.assertAlmostEqual(
                    math.dist([float(str(v)) for v in point], [3, 0, 0]), 1.0
                )
        helix: list[SpacePoint] = [
            [math.cos(a / 10), math.sin(a / 10), a / 100] for a in range(11)
        ]
        steps = path_steps([_move(3, helix)], 1.0, True)
        self.assertEqual(
            [step["command"] for step in steps], ["sketch.line3d"]
        )

    def test_arc_steps_half(self) -> None:
        """An open arc is one step, through its middle point."""
        points: list[SpacePoint] = [[0, 0, 0], [1, 1, 0], [2, 0, 0]]
        self.assertEqual(
            arc_steps(points)[0]["params"],
            {"start": [0, 0, 0], "through": [1, 1, 0], "end": [2, 0, 0]},
        )

    def test_sketch_steps(self) -> None:
        """A batch is create, options, drawing, finish, and maybe hide."""
        steps = sketch_steps("T01 cuts", [], True)
        self.assertEqual(
            [step["command"] for step in steps],
            [
                "sketch.create",
                "sketch.options",
                "sketch.finish",
                "browser.visibility",
            ],
        )
        self.assertEqual(len(sketch_steps("T01 cuts", [], False)), 3)


if __name__ == "__main__":
    unittest.main()
