"""Light and dark: the GUI follows the desktop (`T.osiade~5.1.9` #24).

The desktop's choice comes from `QStyleHints.colorScheme()` (Qt 6.5
and later; on Linux, from the desktop portal).  The GUI uses Qt's
Fusion style with a palette of its own for each scheme, so that it
looks the same on every desktop, and every color it sets itself comes
from `colors()`, never a constant.  The sketches from `Tool_Models.md`
are drawn for paper; `sketch_text()` recolors them for the scheme.
When the desktop switches, `follow()` switches the GUI and calls back
so that the windows draw themselves again.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from ..packages import require

# `PySide6` lives in `~/.scraftcam/packages/`, so it is put on
# `sys.path` (and fetched, the first time) before it is imported.
require("PySide6")
# pylint: disable=wrong-import-position,wrong-import-order
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

# pylint: enable=wrong-import-position,wrong-import-order


# Class `Colors`:
@dataclass(frozen=True, slots=True)
class Colors:
    """The colors the GUI sets itself, for one scheme.

    Attributes:
    * `problem` (`str`): Text that reports a problem.
    * `bad` (`str`): The background of an entry holding a bad value.
    * `quiet` (`str`): Text that is there but not to be read first
      (a value in the shop's units, an empty panel's title).
    * `paper` (`str`): A sketch's background, and its holes.
    * `ink` (`str`): A sketch's lines and letters.
    * `tool` (`str`): A sketch's solid parts.
    * `pocket` (`str`): A sketch's pocket floors and tapped holes.

    Constructor:
    * `Colors(problem, bad, quiet, paper, ink, tool, pocket)`
    """

    # Constructor arguments:
    problem: str = field(init=True)
    bad: str = field(init=True)
    quiet: str = field(init=True)
    paper: str = field(init=True)
    ink: str = field(init=True)
    tool: str = field(init=True)
    pocket: str = field(init=True)


# The two schemes.  `LIGHT`'s sketch colors are those the sketches are
# written with (`tool_models.py`).
LIGHT: Colors = Colors(
    problem="#c00000",
    bad="#ffd0d0",
    quiet="#808080",
    paper="white",
    ink="#222222",
    tool="#dfe4e8",
    pocket="#aab4bd",
)
DARK: Colors = Colors(
    problem="#ff6b6b",
    bad="#6b2626",
    quiet="#9a9a9a",
    paper="#1e1f22",
    ink="#e4e4e4",
    tool="#454b53",
    pocket="#7a858f",
)

# What the windows do when the scheme changes, set by `follow()`.
_REDRAW: list[Callable[[], None]] = []


# Function `dark()`:
def dark() -> bool:
    """Return True if the desktop asks for a dark scheme.

    Returns:
    * (`bool`): True for dark; False for light, or when it does not
      say.
    """
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


# Function `colors()`:
def colors() -> Colors:
    """Return the colors of the scheme in use.

    Returns:
    * (`Colors`): `DARK` or `LIGHT`.
    """
    return DARK if dark() else LIGHT


# Function `palette()`:
def palette(scheme: Colors) -> QPalette:
    """Return Fusion's palette for a scheme.

    Arguments:
    * `scheme` (`Colors`): `LIGHT` or `DARK`.

    Returns:
    * (`QPalette`): Fusion's own for light; a dark one for dark.
    """
    if scheme is LIGHT:
        return QApplication.style().standardPalette()
    made: QPalette = QPalette()
    role: QPalette.ColorRole
    color: str
    for role, color in (
        (QPalette.ColorRole.Window, "#2b2d30"),
        (QPalette.ColorRole.WindowText, scheme.ink),
        (QPalette.ColorRole.Base, scheme.paper),
        (QPalette.ColorRole.AlternateBase, "#26282b"),
        (QPalette.ColorRole.ToolTipBase, "#3c3f41"),
        (QPalette.ColorRole.ToolTipText, scheme.ink),
        (QPalette.ColorRole.PlaceholderText, scheme.quiet),
        (QPalette.ColorRole.Text, scheme.ink),
        (QPalette.ColorRole.Button, "#3c3f41"),
        (QPalette.ColorRole.ButtonText, scheme.ink),
        (QPalette.ColorRole.BrightText, "#ff8080"),
        (QPalette.ColorRole.Light, "#4a4d50"),
        (QPalette.ColorRole.Midlight, "#404346"),
        (QPalette.ColorRole.Mid, "#5a5d60"),
        (QPalette.ColorRole.Dark, "#1a1b1d"),
        (QPalette.ColorRole.Shadow, "#000000"),
        (QPalette.ColorRole.Highlight, "#2f65ca"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.Link, "#6ea8fe"),
    ):
        made.setColor(role, QColor(color))
    made.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(scheme.quiet),
    )
    made.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(scheme.quiet),
    )
    return made


# Function `apply()`:
def apply(application: QApplication) -> None:
    """Style the application for the desktop's scheme.

    Arguments:
    * `application` (`QApplication`): The application.
    """
    application.setStyle("Fusion")
    application.setPalette(palette(colors()))


# Function `follow()`:
def follow(application: QApplication, redraw: Callable[[], None]) -> None:
    """Apply the scheme now, and again whenever the desktop switches.

    Arguments:
    * `application` (`QApplication`): The application.
    * `redraw` (`Callable[[], None]`): What draws the windows again
      (their own colors, and the sketches).
    """
    apply(application)
    _REDRAW.append(redraw)
    if len(_REDRAW) > 1:
        return

    # Function `switched()`:
    def switched(_scheme: Qt.ColorScheme) -> None:
        """Apply the new scheme, then draw everything again."""
        apply(application)
        for again in _REDRAW:
            again()

    QGuiApplication.styleHints().colorSchemeChanged.connect(switched)


# Function `sketch_text()`:
def sketch_text(text: str) -> str:
    """Return a sketch's SVG, recolored for the scheme in use.

    Arguments:
    * `text` (`str`): The SVG, as `tool_models.py` writes it (`LIGHT`'s
      colors).

    Returns:
    * (`str`): The SVG in the scheme's colors.
    """
    scheme: Colors = colors()
    if scheme is LIGHT:
        return text
    for light, dark_color in (
        (LIGHT.paper, scheme.paper),
        (LIGHT.ink, scheme.ink),
        (LIGHT.tool, scheme.tool),
        (LIGHT.pocket, scheme.pocket),
    ):
        text = text.replace(f'"{light}"', f'"{dark_color}"')
    return text
