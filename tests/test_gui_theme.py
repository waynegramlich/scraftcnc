"""Tests of `scraftcam.gui.theme`: light and dark (#24)."""

import unittest
from unittest import mock

from scraftcam.gui import theme
from tests import qt_app

# A sketch's text, in `LIGHT`'s colors.
SKETCH: str = (
    '<rect fill="white" /><path fill="#dfe4e8" stroke="#222222" />'
    '<circle fill="#aab4bd" />'
)


class ThemeTest(unittest.TestCase):
    """The colors, the palettes and the recolored sketches."""

    def test_sketch_text(self) -> None:
        """Light leaves a sketch alone; dark swaps each color."""
        with mock.patch.object(theme, "dark", return_value=False):
            self.assertEqual(theme.sketch_text(SKETCH), SKETCH)
        with mock.patch.object(theme, "dark", return_value=True):
            dark: str = theme.sketch_text(SKETCH)
        for color in ("white", "#dfe4e8", "#222222", "#aab4bd"):
            self.assertNotIn(f'"{color}"', dark)
        for color in (theme.DARK.paper, theme.DARK.tool, theme.DARK.ink):
            self.assertIn(f'"{color}"', dark)

    def test_palettes(self) -> None:
        """Dark's window is darker than its text; light's the other way."""
        qt_app.process_events()
        dark = theme.palette(theme.DARK)
        light = theme.palette(theme.LIGHT)
        window = dark.color(dark.ColorRole.Window).lightness()
        text = dark.color(dark.ColorRole.WindowText).lightness()
        self.assertLess(window, text)
        window = light.color(light.ColorRole.Window).lightness()
        text = light.color(light.ColorRole.WindowText).lightness()
        self.assertGreater(window, text)

    def test_follow(self) -> None:
        """A switch on the desktop restyles and calls back."""
        calls: list[str] = []

        # Function `redraw()`:
        def redraw() -> None:
            """Note the call."""
            calls.append("redraw")

        with mock.patch.object(theme, "_REDRAW", []):
            theme.follow(qt_app.APPLICATION, redraw)
            hints = qt_app.APPLICATION.styleHints()
            hints.colorSchemeChanged.emit(hints.colorScheme())
        self.assertEqual(calls, ["redraw"])


if __name__ == "__main__":
    unittest.main()
