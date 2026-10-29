"""Tests of `lcnc_panel.py`'s Tools window text (no LinuxCNC)."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
