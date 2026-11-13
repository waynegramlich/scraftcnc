"""The GUI and the HMI, offscreen, for their tests.

Importing this makes the one `QApplication`, drawing offscreen,
before any window or HMI is made.
"""

import atexit
from typing import TYPE_CHECKING

from scraftcam.gui import window
from scraftcam.hmi import lcnc_hmi
from scraftcam.hmi.hmi_machine import HMIMachine

# Only for the type: importing `window` puts `PySide6` on `sys.path`.
if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

# Offscreen, before the one `QApplication` is made; the HMI's
# questions answered from `lcnc_hmi.ANSWERS`.
lcnc_hmi.use_headless()
APPLICATION: "QApplication" = window.make_application(headless=True)

# Every window and HMI deleted before Python's exit, ahead of PySide's
# own clean up, which crashed with many of them left.
atexit.register(window.delete_windows)


# Function `process_events()`:
def process_events() -> None:
    """Run Qt's waiting events (no event loop runs in the tests)."""
    APPLICATION.processEvents()


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
