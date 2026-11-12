"""The Qt HMI, offscreen, for the HMI tests.

Importing this makes Qt draw offscreen (`lcnc_hmi_qt.use_headless()`)
and makes the one `QApplication`, before any HMI is made.
"""

from typing import Any

from scraftcam.hmi import lcnc_hmi_qt
from scraftcam.hmi.lcnc_hmi import HMIMachine

# Offscreen, before the one `QApplication` is made.
lcnc_hmi_qt.use_headless()
# pylint: disable-next=wrong-import-order,wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

APPLICATION: Any = QApplication.instance() or QApplication([])


# Function `make_hmi()`:
def make_hmi(machine: HMIMachine) -> lcnc_hmi_qt.HMI:
    """Make an HMI, with no questions waiting.

    Its timer runs, but nothing runs Qt's loop, so `poll()` runs only
    when a test calls it.

    Arguments:
    * `machine` (`HMIMachine`): The LinuxCNC back end.

    Returns:
    * (`lcnc_hmi_qt.HMI`): The HMI, its speed slider up to 10x.
    """
    lcnc_hmi_qt.ANSWERS.clear()
    lcnc_hmi_qt.ASKED.clear()
    return lcnc_hmi_qt.HMI(machine, 10.0, None)
