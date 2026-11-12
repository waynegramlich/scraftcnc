"""Tests for the HMI's tool changes: the pause, the next tool, the time."""

import math
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, cast

from scraftcam import demo, shops
from scraftcam.hmi import lcnc_hmi, lcnc_hmi_headless
from scraftcam.setups import SHOP as EXAMPLE_SHOP
from scraftcam.tooling.shop_registries import use_shop
from tests.test_lcnc_hmi import RUNNING, client_machine


class TestToolChangePause(unittest.TestCase):
    """The pause at a tool change (`T.hs~5.1.5` S5)."""

    def test_demo_pauses(self) -> None:
        """The demo's carousel machine pauses only at its one swap."""
        use_shop(shops.read(EXAMPLE_SHOP))
        lines = demo.cut_demo()[0].gcode().splitlines()
        changes = [
            number
            for number, line in enumerate(lines)
            if lcnc_hmi.TOOL_CHANGE.search(line)
        ]
        self.assertGreater(len(changes), 1)
        paused = [number for number in changes if lines[number - 1] == "M0"]
        self.assertEqual(len(paused), 1)
        self.assertEqual(
            lines[paused[0] - 2],
            "(MSG, Swap tool 5 [black/green] with tool 8 [black/gray])",
        )
        self.assertEqual(sum(line == "M0" for line in lines), 1)

        # -Tool and +Tool land on the swap's message, else on the `M6`.
        starts = lcnc_hmi.tool_changes(lines)
        self.assertEqual(
            starts,
            [
                number - 1 if number in paused else number + 1
                for number in changes
            ],
        )

    def test_starts(self) -> None:
        """A change without a message starts at its `M6`."""
        lines = ["G20", "(MSG, Insert T01: a)", "M0", "T01 M6", "T02 M6"]
        self.assertEqual(lcnc_hmi.tool_changes(lines), [2, 5])

    def test_headless_goes_on(self) -> None:
        """Headless, the program's own pause goes on; Pause's does not."""
        lcnc_hmi.use_headless()
        machine, lcnc = client_machine()
        root: Any = lcnc_hmi_headless.Tk()
        panel = lcnc_hmi.HMI(cast(Any, root), machine, 10.0, None)
        lcnc.interp_state = RUNNING
        lcnc.values["paused"] = True
        lcnc.errors = [[13, "Insert T04: a drill"]]
        panel.running = True
        root.run_one()
        self.assertIn("Insert T04: a drill", panel.show()["message"])
        self.assertEqual(len(lcnc.sent("command.auto")), 1)

        # A pause from Pause waits for a person.
        panel.on_pause()
        sent = len(lcnc.sent("command.auto"))
        root.run_one()
        self.assertEqual(len(lcnc.sent("command.auto")), sent)


class TestNextTool(unittest.TestCase):
    """The next tool and the time left until it (`T.hs~5.1.5` S6)."""

    LINES: ClassVar[list[str]] = [
        "G20 G90",
        "G0 X0 Y0 Z1",
        "(MSG, Insert T01: a mill)",
        "M0",
        "T01 M6 G43 H01 (a mill)",
        "G0 X6",
        "G1 Z0 F10",
        "G2 X8 Y0 I1 J0",
        "(MSG, Insert T02: a drill)",
        "M0",
        "T02 M6 G43 H02 (a drill)",
        "G81 X8 Y0 Z-1 R0.1",
        "G80",
        "M2",
    ]

    def sums(self) -> list[float]:
        """Return the minutes up to each line."""
        sums = [0.0]
        for minutes in lcnc_hmi.line_minutes(self.LINES, 60.0):
            sums.append(sums[-1] + minutes)
        return sums

    def test_line_minutes(self) -> None:
        """Rapids, feeds, arcs and a drill cycle each take their time."""
        minutes = lcnc_hmi.line_minutes(self.LINES, 60.0)
        self.assertAlmostEqual(minutes[5], 6.0 / 60.0)  # Rapid X0 to X6.
        self.assertAlmostEqual(minutes[6], 1.0 / 10.0)  # Feed Z1 to Z0.
        self.assertAlmostEqual(minutes[7], math.pi / 10.0, places=2)
        # The cycle: up to its start (Z0 stays), down 1.1 at F10.
        self.assertAlmostEqual(minutes[11], 1.1 / 10.0 + 1.1 / 60.0)
        self.assertEqual(minutes[0], 0.0)

    def test_labels(self) -> None:
        """At the start, at a change, and after the last change."""
        sums = self.sums()
        spans = lcnc_hmi.change_spans(self.LINES)
        self.assertEqual(spans, [(3, 5), (9, 11)])
        text = lcnc_hmi.next_tool_text(self.LINES, sums, spans, 0, 1.0)
        self.assertEqual(text, "Next: T01 a mill in 0:00")
        text = lcnc_hmi.next_tool_text(self.LINES, sums, spans, 6, 1.0)
        self.assertEqual(text, "Next: T02 a drill in 0:31")
        text = lcnc_hmi.next_tool_text(self.LINES, sums, spans, 10, 1.0)
        self.assertEqual(text, "Now: T02 a drill, cut 0:08")
        text = lcnc_hmi.next_tool_text(self.LINES, sums, spans, 12, 1.0)
        self.assertEqual(text, "Last tool: 0:08 to the end")

    def test_override(self) -> None:
        """Twice the feed override, half the time."""
        sums = self.sums()
        spans = lcnc_hmi.change_spans(self.LINES)
        text = lcnc_hmi.next_tool_text(self.LINES, sums, spans, 6, 2.0)
        self.assertEqual(text, "Next: T02 a drill in 0:15")

    def test_demo_total(self) -> None:
        """The demo's lines add up to near its own estimate."""
        use_shop(shops.read(EXAMPLE_SHOP))
        cnc = demo.cut_demo()[0]
        lines = cnc.gcode().splitlines()
        total = sum(lcnc_hmi.line_minutes(lines, 60.0))
        self.assertAlmostEqual(total, cnc.minutes, delta=0.05 * cnc.minutes)

    def test_shown(self) -> None:
        """The HMI shows it, and `show` has it (headless)."""
        lcnc_hmi.use_headless()
        machine = lcnc_hmi.HMIMachine(True)
        root: Any = lcnc_hmi_headless.Tk()
        panel = lcnc_hmi.HMI(cast(Any, root), machine, 10.0, None)
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch, "two.ngc")
            path.write_text("\n".join(self.LINES) + "\n", encoding="utf-8")
            panel.open(str(path))
            root.run_one()
        self.assertEqual(panel.show()["next_tool"], "Next: T01 a mill in 0:00")
