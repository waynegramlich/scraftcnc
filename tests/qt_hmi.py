"""The Qt HMI, offscreen, for the HMI tests.

Importing this makes Qt draw offscreen (`lcnc_hmi.use_headless()`)
and makes the one `QApplication`, before any HMI is made.
"""

from typing import Any

from scraftcam.hmi import lcnc_hmi
from scraftcam.hmi.hmi_machine import HMIMachine

# Offscreen, before the one `QApplication` is made.
lcnc_hmi.use_headless()
# pylint: disable-next=wrong-import-order,wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

APPLICATION: Any = QApplication.instance() or QApplication([])


# Function `make_hmi()`:
def make_hmi(machine: HMIMachine) -> lcnc_hmi.HMI:
    """Make an HMI, with no questions waiting.

    Its timer runs, but nothing runs Qt's loop, so `poll()` runs only
    when a test calls it.

    Arguments:
    * `machine` (`HMIMachine`): The LinuxCNC back end.

    Returns:
    * (`lcnc_hmi.HMI`): The HMI, its speed slider up to 10x.
    """
    lcnc_hmi.ANSWERS.clear()
    lcnc_hmi.ASKED.clear()
    return lcnc_hmi.HMI(machine, 10.0, None)
