"""Tests of `lcnc_panel.py` that need no LinuxCNC or window."""

import unittest
from unittest import mock

import lcnc_panel
import shops


class TestToolSpeeds(unittest.TestCase):
    """The tools' speeds and feeds, as the Tools window lists them."""

    def setUp(self) -> None:
        self.shop = shops.read(lcnc_panel.SHOP_FILE)

    def test_materials(self) -> None:
        """The chooser lists the shop's materials."""
        names = lcnc_panel.material_names(self.shop)
        self.assertIn("6061 aluminum", names)
        self.assertIn("hdpe", names)

    def test_table(self) -> None:
        """One line per loaded tool."""
        text = lcnc_panel.tool_speeds(
            self.shop, lcnc_panel.SHOP_MACHINE, "steel"
        )
        self.assertIn("cutting steel", text)
        self.assertIn("1630   6.5     6.5  15/64 in HSS jobber drill", text)

    def test_problem(self) -> None:
        """A problem is shown in place of the table."""
        text = lcnc_panel.tool_speeds(
            self.shop, lcnc_panel.SHOP_MACHINE, "unobtainium"
        )
        self.assertIn('"unobtainium" is not one of', text)


class TestMessages(unittest.TestCase):
    """LinuxCNC's messages, kept for the command port."""

    def test_messages(self) -> None:
        """Each message is kept, past the `status()` that read it."""
        machine = lcnc_panel.Machine(True)
        machine.linuxcnc = mock.MagicMock()
        machine.sim = mock.MagicMock()
        machine.sim.errors.poll.side_effect = [(1, "first"), None, None]
        machine.status()
        machine.status()
        self.assertEqual(machine.messages, ["first"])

        # The port shows them, and something when there are none.
        panel = mock.MagicMock(machine=machine)
        handle = lcnc_panel.Panel.handle
        self.assertEqual(handle(panel, "messages"), "messages: first")
        machine.messages = []
        self.assertEqual(handle(panel, "messages"), "messages: ")


if __name__ == "__main__":
    unittest.main()
