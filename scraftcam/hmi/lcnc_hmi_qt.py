#!/usr/bin/env python3
"""The LinuxCNC HMI, in Qt (`T.hs~5.1.5`, `T.osiade~5.1.9` #21).

The same HMI as `lcnc_hmi.py`, laid out the same way, with the same
tabs, buttons and command port, built with Qt (`PySide6`, fetched into
`~/.scraftcam/packages/` the first time, by `scraftcam.packages`) in
place of `tkinter`.  Everything that does not draw (`HMIMachine`,
`CommandPort`, `SetupDrawer`, the timing and the keep-out checks) is
taken from `lcnc_hmi.py` as it is; see its docstring for what each tab
does, and for the command port's commands.

```
python3 -m scraftcam.lcnc.serve_linuxcnc &
python3 -m scraftcam.hmi.lcnc_hmi_qt demo.ngc
# The window alone:
python3 -m scraftcam.hmi.lcnc_hmi_qt --dry-run demo.ngc
# No window, for tests:
python3 -m scraftcam.hmi.lcnc_hmi_qt --headless --port 5007
```

With `--headless`, Qt draws offscreen (`QT_QPA_PLATFORM=offscreen`),
so no display is needed, and otherwise the same code runs, with its
buttons pressed through the command port.  A question that would open
a window then takes its answer from `ANSWERS`, in order (the port's
`answer VALUE`), or else the answer that does nothing (No, or no
file), and is added to `ASKED`.
"""

# The HMI's methods each need their docstring, so it passes 1000
# lines, as `lcnc_hmi.py` does.
# pylint: disable=too-many-lines

import argparse
import functools
import json
import math
import os
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from .. import shops
from ..assembly import Assembly, AssemblyItem
from ..carousel import gcode_sequence, plan_text
from ..geometry import RoundedPolygon
from ..keepout import assembly_zones
from ..lcnc.lcnc_client import PORT, BridgeError
from ..machine import Machine
from ..model_cache import ModelCache
from ..packages import require
from ..pybind.scraftpybind import PyBind, connect
from ..setup_comments import read_file
from ..setup_view import SetupView, named_origins
from ..tooling.shop_registries import use_shop
from ..tooling.tools import Point
from .lcnc_hmi import (
    AT_ORIGIN,
    AXES,
    BAD,
    BLANK,
    COMMENT,
    GOOD,
    INCH,
    INCREMENTAL,
    JOG_STEP,
    JOG_STEPS,
    MATERIAL,
    MAX_SPEED,
    METRIC,
    MIN_SPEED,
    POLL_MS,
    SHOP_FILE,
    SHOP_MACHINE,
    SHOWN,
    STEP_CHOSEN,
    TABS,
    TOGGLES,
    CommandPort,
    HMIMachine,
    HMIStatus,
    SetupDrawer,
    change_spans,
    jog_hit,
    line_kind,
    line_minutes,
    material_names,
    mdi_segments,
    next_tool_text,
    origin_lines,
    program_inches,
    setup_material,
    setup_origin,
    setup_warning,
    shop_name,
    tool_changes,
    tool_speeds,
)

# `PySide6` lives in `~/.scraftcam/packages/`, so it is put on
# `sys.path` (and fetched, the first time) before it is imported.
require("PySide6")
# pylint: disable=wrong-import-position,wrong-import-order
from PySide6.QtCore import (  # noqa: E402
    QMessageLogContext,
    Qt,
    QTimer,
    QtMsgType,
    qInstallMessageHandler,
)
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# pylint: enable=wrong-import-position,wrong-import-order

# True when Qt draws offscreen, with no one to answer questions.
HEADLESS: bool = False

# The answers waiting for questions, and the questions asked (headless).
ANSWERS: list[str] = []
ASKED: list[str] = []

# How many steps the speed slider has, from `MIN_SPEED` to its top.
SLIDER_STEPS: int = 1000

# What Qt's offscreen platform says each time a window is shown; it
# means nothing here, so `use_headless()` drops it.
OFFSCREEN_NOISE: str = "This plugin does not support propagateSizeHints()"


# Function `use_headless()`:
def use_headless() -> None:
    """Draw offscreen from now on, and answer questions from `ANSWERS`.

    It must be called before the `QApplication` is made.
    """
    # pylint: disable-next=global-statement
    global HEADLESS
    HEADLESS = True
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    qInstallMessageHandler(qt_message)


# Function `qt_message()`:
def qt_message(
    _kind: QtMsgType, _context: QMessageLogContext, message: str
) -> None:
    """Write a message from Qt, less `OFFSCREEN_NOISE` (headless).

    Arguments:
    * `_kind` (`QtMsgType`): Debug, warning and so on (ignored).
    * `_context` (`QMessageLogContext`): Where it came from (ignored).
    * `message` (`str`): The message.
    """
    if message != OFFSCREEN_NOISE:
        print(message, file=sys.stderr)


# Function `next_answer()`:
def next_answer(question: str) -> str:
    """Record a question asked headless, and return its answer.

    Arguments:
    * `question` (`str`): The question.

    Returns:
    * (`str`): The next of `ANSWERS`, or `""` when there is none.
    """
    ASKED.append(question)
    return ANSWERS.pop(0) if ANSWERS else ""


# Function `ask_yes_no()`:
def ask_yes_no(parent: QWidget, title: str, message: str) -> bool:
    """Ask a question, with No as the default.

    Arguments:
    * `parent` (`QWidget`): The HMI.
    * `title` (`str`): The window's title.
    * `message` (`str`): The question.

    Returns:
    * (`bool`): True for Yes.
    """
    if HEADLESS:
        return next_answer(f"{title}: {message}") == "yes"
    answer: QMessageBox.StandardButton = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


# Function `ask_choice()`:
def ask_choice(
    parent: QWidget, title: str, message: str, choices: list[str]
) -> str:
    """Ask the operator to pick one of a list.

    Arguments:
    * `parent` (`QWidget`): The HMI.
    * `title` (`str`): The window's title.
    * `message` (`str`): The question.
    * `choices` (`list[str]`): What may be picked.

    Returns:
    * (`str`): The choice, or `""` for Cancel (or, headless, an
      answer that is not one of `choices`).
    """
    if HEADLESS:
        answer: str = next_answer(f"{title}: {message}")
        return answer if answer in choices else ""
    choice: str
    accepted: bool
    choice, accepted = QInputDialog.getItem(
        parent, title, message, choices, 0, False
    )
    return choice if accepted else ""


# Function `ask_open_file()`:
def ask_open_file(parent: QWidget) -> str:
    """Ask for a G-code file.

    Arguments:
    * `parent` (`QWidget`): The HMI.

    Returns:
    * (`str`): The file, or `""` for Cancel.
    """
    if HEADLESS:
        return next_answer("Open G-code")
    path: str
    path, _ = QFileDialog.getOpenFileName(
        parent, "Open G-code", "", "G-code (*.ngc *.nc *.gcode);;All (*)"
    )
    return path


# Function `fixed_font()`:
def fixed_font() -> QFont:
    """Return the system's fixed width font.

    Returns:
    * (`QFont`): The font.
    """
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


# Function `paint()`:
def paint(entry: QLineEdit, color: str) -> None:
    """Color an entry's background, and remember the color for `show`.

    Arguments:
    * `entry` (`QLineEdit`): The entry.
    * `color` (`str`): A color, such as `GOOD`.
    """
    entry.setStyleSheet(f"QLineEdit {{ background: {color}; }}")
    entry.setProperty("background", color)


# Function `row()`:
def row(
    layout: QVBoxLayout, *widgets: QWidget, spaces: dict[int, int]
) -> None:
    """Add a row of widgets, centered, to a layout.

    Arguments:
    * `layout` (`QVBoxLayout`): Where the row goes, under what is
      there.
    * `widgets` (`QWidget`): The row, left to right.
    * `spaces` (`dict[int, int]`): Extra room (pixels) before the
      widgets at these indexes.
    """
    line: QHBoxLayout = QHBoxLayout()
    line.addStretch(1)
    index: int
    widget: QWidget
    for index, widget in enumerate(widgets):
        if index in spaces:
            line.addSpacing(spaces[index])
        line.addWidget(widget)
    line.addStretch(1)
    layout.addLayout(line)


# Class `HMI`:
# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class HMI(QWidget):
    """The HMI window, laid out as in `T.mlcp~3.4`.

    Attributes:
    * `coming` (`QPlainTextEdit`): The G-code coming next (read only).
    * `inches` (`bool`): True when the open program is in inches.
    * `assembly` (`Assembly | None`): The open program's setup.
    * `next_step_button` (`QPushButton`): Shows the setup's next item.
    * `note` (`str`): The setup step shown, kept ahead of any error.
    * `drawing` (`bool`): True while a setup is drawn (Start is
      greyed out).
    * `progress` (`QProgressBar`): How much of the setup is drawn.
    * `drawn` (`Assembly | None`): The setup (or the steps of it)
      last handed to `drawer`.
    * `toggles` (`dict[str, QCheckBox]`): The View tab's check
      buttons, by label (`TOGGLES`).
    * `setup_step` (`int`): How many of the setup's items Next Step
      has shown (0: the whole setup).
    * `origins` (`list[tuple[str, Point]]`): The open program's
      setup's named origins (work millimeters), or none.
    * `drawer` (`SetupDrawer | None`): What draws an opened
      program's setup in SolidCraft, or `None` to draw nothing.
    * `execute_button` (`QPushButton`): Runs the MDI line.
    * `executed` (`QPlainTextEdit`): The G-code already run (read
      only).
    * `home_button` (`QPushButton`): Rapids to the work origin.
    * `jog_buttons` (`list[QPushButton]`): -X, +X, -Y, +Y, -Z, +Z,
      and the step buttons.
    * `lines` (`list[str]`): The open program's lines.
    * `lines_file` (`str`): The file `lines` was read from.
    * `machine` (`HMIMachine`): The LinuxCNC back end.
    * `mdi_entry` (`QLineEdit`): The MDI line, colored as it is
      typed.
    * `message` (`QLabel`): LinuxCNC's last error message.
    * `origin_button` (`QPushButton`): The Set Origin button.
    * `paused` (`bool`): True while the program is paused.
    * `pause_button` (`QPushButton`): The Pause button.
    * `port` (`CommandPort | None`): The command port, if any.
    * `position` (`QLabel`): The work position and the tool.
    * `run_button` (`QPushButton`): The Start button (Resume while
      paused).
    * `running` (`bool`): True while a program runs (or is paused).
    * `scrolling` (`bool`): True once the whole program is in the two
      G-code windows, to scroll while paused.
    * `slider` (`QSlider`): The speed slider, `SLIDER_STEPS` steps
      on a logarithmic scale.
    * `speed_text` (`QLabel`): The feed override, shown.
    * `top_speed` (`float`): The slider's highest feed override.
    * `steps` (`QButtonGroup`): The jog step buttons (inches), one
      chosen at a time.
    * `start` (`int`): The line Start runs from (counted from 1; 0
      for the program's start), chosen with -Tool and +Tool.
    * `tool_buttons` (`list[QPushButton]`): -Tool and +Tool.
    * `material_chooser` (`QComboBox`): The material the Tools tab
      shows.
    * `next_tool` (`QLabel`): The next tool and the time left to it
      (`T.hs~5.1.5` S6).
    * `notebook` (`QTabWidget`): The tabs.
    * `operator_paused` (`bool`): True while paused by Pause (not by
      the program's own `M0`).
    * `axes_set` (`set[str]`): The axes whose origin is set since the
      program was opened.
    * `axis_buttons` (`dict[str, QPushButton]`): Set X, Set Y, Set Z.
    * `axis_entries` (`dict[str, QLineEdit]`): Their numbers'
      entries.
    * `jog_note` (`str`): Why jogs are not checked, once said.
    * `last_tool` (`int`): The tool in the spindle at the last poll.
    * `jog_refusal` (`str`): Why the last jog or MDI line was refused
      (`""` when it was not).
    * `tool_radii` (`dict[int, float]`): Each tool's widest radius,
      by its number.
    * `zones` (`list[RoundedPolygon] | None`): The setup's keep-outs
      (work inches), `None` without a setup.
    * `override` (`float`): The feed override (the speed slider).
    * `rapid` (`float`): How fast a rapid goes (inches per minute).
    * `spans` (`list[tuple[int, int]]`): The program's tool changes
      (`change_spans()`).
    * `sums` (`list[float]`): Minutes up to each line of the program
      (`time_program()`).
    * `origin_set` (`bool`): True once the open program's origin is
      set (`mark_origin_set()`); Start waits for it.
    * `program_machine` (`str`): The machine the program is for.
    * `program_material` (`str`): The material it cuts.
    * `tabs` (`dict[str, QWidget]`): Each tab, by its name.
    * `timer` (`QTimer`): Calls `poll()` every `POLL_MS`.
    * `tools_table` (`QPlainTextEdit`): The tools' speeds and feeds.
    """

    # Method `HMI.__init__()`:
    # pylint: disable-next=too-many-locals,too-many-statements
    def __init__(
        self,
        machine: HMIMachine,
        max_speed: float,
        port: CommandPort | None,
        parent: QWidget | None = None,
    ) -> None:
        """Build the window.

        It lays the whole window out in one place, so it has many
        locals and statements.

        Arguments:
        * `machine` (`HMIMachine`):
          The LinuxCNC back end.
        * `max_speed` (`float`):
          The speed slider's highest setting.
        * `port` (`CommandPort | None`):
          The command port, if any.
        * `parent` (`QWidget | None`):
          What it is shown in, or `None` for a window of its own.
        """
        super().__init__(parent)
        self.machine: HMIMachine = machine
        self.port: CommandPort | None = port
        self.paused: bool = False
        self.running: bool = False
        self.start: int = 0
        self.lines: list[str] = []
        self.lines_file: str = ""
        self.scrolling: bool = False
        self.drawer: SetupDrawer | None = None
        self.origins: list[tuple[str, Point]] = []
        self.inches: bool = False
        self.assembly: Assembly | None = None
        self.setup_step: int = 0
        self.note: str = ""
        self.drawn: Assembly | None = None
        self.drawing: bool = False
        self.program_material: str = MATERIAL
        self.program_machine: str = SHOP_MACHINE
        self.origin_set: bool = False
        self.operator_paused: bool = False
        self.override: float = 1.0
        self.zones: list[RoundedPolygon] | None = None
        self.tool_radii: dict[int, float] = {}
        self.jog_note: str = ""
        self.last_tool: int = 0
        self.jog_refusal: str = ""
        self.rapid: float = machine.rapid_speed()
        self.sums: list[float] = [0.0]
        self.spans: list[tuple[int, int]] = []
        self.setWindowTitle("SolidCraft LinuxCNC")
        layout: QVBoxLayout = QVBoxLayout(self)

        # Above the tabs, on every tab: the work position and the tool,
        # LinuxCNC's messages, and how much of the setup is drawn.
        self.position: QLabel = QLabel()
        self.position.setFont(fixed_font())
        layout.addWidget(self.position)
        self.message: QLabel = QLabel()
        self.message.setStyleSheet("QLabel { color: red; }")
        self.progress: QProgressBar = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(120)
        message_line: QHBoxLayout = QHBoxLayout()
        message_line.addWidget(self.message, 1)
        message_line.addWidget(self.progress)
        layout.addLayout(message_line)

        # The tabs, one for each task, in the order of `TABS`.
        self.notebook: QTabWidget = QTabWidget()
        layout.addWidget(self.notebook, 1)
        self.tabs: dict[str, QWidget] = {}
        name: str
        for name in TABS:
            self.tabs[name] = QWidget()
            self.notebook.addTab(self.tabs[name], name)
        self.notebook.currentChanged.connect(self.on_tab_changed)
        run_tab: QVBoxLayout = QVBoxLayout(self.tabs["Run"])

        # Run: the G-code run and coming, and below them the MDI line
        # and Execute.
        self.executed: QPlainTextEdit = self.scrolled_text(run_tab)
        self.coming: QPlainTextEdit = self.scrolled_text(run_tab)
        self.mdi_entry: QLineEdit = QLineEdit()
        self.mdi_entry.setFont(fixed_font())
        paint(self.mdi_entry, BLANK)
        self.execute_button: QPushButton = QPushButton("Execute")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self.on_execute)
        mdi_line: QHBoxLayout = QHBoxLayout()
        mdi_line.addWidget(self.mdi_entry, 1)
        mdi_line.addWidget(self.execute_button)
        run_tab.addLayout(mdi_line)
        self.mdi_entry.textChanged.connect(self.check_mdi)

        # Run: the run line, -Tool and +Tool, Start, Pause and Reset.
        self.tool_buttons: list[QPushButton] = []
        label: str
        step: int
        for label, step in (("-Tool", -1), ("+Tool", +1)):
            tool_button: QPushButton = QPushButton(label)
            tool_button.clicked.connect(functools.partial(self.on_tool, step))
            self.tool_buttons.append(tool_button)
        self.run_button: QPushButton = QPushButton("Start")
        self.run_button.clicked.connect(self.on_run)
        self.pause_button: QPushButton = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.on_pause)
        reset: QPushButton = QPushButton("Reset")
        reset.clicked.connect(self.on_stop)
        row(
            run_tab,
            *self.tool_buttons,
            self.run_button,
            self.pause_button,
            reset,
            spaces={2: 12},
        )

        # Run: the speed slider (logarithmic), and the next tool and
        # the time left (`T.hs~5.1.5` S6).
        self.top_speed: float = min(max_speed, MAX_SPEED)
        self.slider: QSlider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.valueChanged.connect(self.on_slider)
        self.speed_text: QLabel = QLabel("1x")
        self.speed_text.setMinimumWidth(
            self.speed_text.fontMetrics().horizontalAdvance("0.00x0")
        )
        slider_line: QHBoxLayout = QHBoxLayout()
        slider_line.addWidget(QLabel("speed"))
        slider_line.addWidget(self.slider, 1)
        slider_line.addWidget(self.speed_text)
        run_tab.addLayout(slider_line)
        self.next_tool: QLabel = QLabel("")
        run_tab.addWidget(self.next_tool)
        run_tab.addStretch(1)

        # Setup: Next Step, Set Origin and Home.
        setup_tab: QVBoxLayout = QVBoxLayout(self.tabs["Setup"])
        self.next_step_button: QPushButton = QPushButton("Next Step")
        self.next_step_button.clicked.connect(self.on_next_step)
        self.origin_button: QPushButton = QPushButton("Set Origin")
        self.origin_button.clicked.connect(self.on_set_origin)
        self.home_button: QPushButton = QPushButton("Home")
        self.home_button.clicked.connect(self.on_home)
        row(
            setup_tab,
            self.next_step_button,
            self.origin_button,
            self.home_button,
            spaces={1: 12},
        )

        # Setup: each axis of the origin set by hand, to a number.
        self.axis_entries: dict[str, QLineEdit] = {}
        self.axis_buttons: dict[str, QPushButton] = {}
        self.axes_set: set[str] = set()
        axis_widgets: list[QWidget] = []
        axis: str
        for axis in AXES:
            entry: QLineEdit = QLineEdit()
            entry.setFont(fixed_font())
            entry.setFixedWidth(
                entry.fontMetrics().horizontalAdvance("0" * 10)
            )
            paint(entry, BLANK)
            entry.textChanged.connect(self.check_axes)
            button: QPushButton = QPushButton(f"Set {axis}")
            button.setEnabled(False)
            button.clicked.connect(functools.partial(self.on_set_axis, axis))
            self.axis_entries[axis] = entry
            self.axis_buttons[axis] = button
            axis_widgets += [entry, button]
        row(setup_tab, *axis_widgets, spaces={2: 8, 4: 8})

        # Setup: the jog buttons and their step (one chosen at a time).
        jogs: tuple[tuple[str, int, int], ...] = (
            ("-X", 0, -1),
            ("+X", 0, +1),
            ("-Y", 1, -1),
            ("+Y", 1, +1),
            ("-Z", 2, -1),
            ("+Z", 2, +1),
        )
        self.jog_buttons: list[QPushButton] = []
        direction: int
        axis_number: int
        for label, axis_number, direction in jogs:
            jog: QPushButton = QPushButton(label)
            jog.clicked.connect(
                functools.partial(self.on_jog, axis_number, direction)
            )
            self.jog_buttons.append(jog)
        self.steps: QButtonGroup = QButtonGroup(self)
        self.steps.setExclusive(True)
        step_text: str
        for step_text in JOG_STEPS:
            choice: QPushButton = QPushButton(step_text)
            choice.setCheckable(True)
            choice.setChecked(step_text == JOG_STEP)
            choice.setStyleSheet(
                f"QPushButton:checked {{ background: {STEP_CHOSEN}; }}"
            )
            self.steps.addButton(choice)
            self.jog_buttons.append(choice)
        row(setup_tab, *self.jog_buttons, spaces={6: 12})
        setup_tab.addStretch(1)

        # Tools: a material, and the tools' speeds and feeds for it
        # (filled each time the tab is shown).
        tools_tab: QVBoxLayout = QVBoxLayout(self.tabs["Tools"])
        self.material_chooser: QComboBox = QComboBox()
        self.material_chooser.addItem(MATERIAL)
        self.material_chooser.setMinimumContentsLength(30)
        self.material_chooser.activated.connect(self.show_tools)
        tools_tab.addWidget(
            self.material_chooser, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.tools_table: QPlainTextEdit = QPlainTextEdit()
        self.tools_table.setReadOnly(True)
        self.tools_table.setFont(fixed_font())
        tools_tab.addWidget(self.tools_table, 1)

        # View: what SolidCraft shows.
        view_tab: QVBoxLayout = QVBoxLayout(self.tabs["View"])
        self.toggles: dict[str, QCheckBox] = {}
        shown: bool
        for label, _, shown in TOGGLES:
            self.toggles[label] = QCheckBox(label)
            self.toggles[label].setChecked(shown)
            self.toggles[label].clicked.connect(self.on_toggle)
            view_tab.addWidget(self.toggles[label])
        view_tab.addStretch(1)

        # Under the tabs, for every task: Open and Quit.
        open_button: QPushButton = QPushButton("Open")
        open_button.clicked.connect(self.on_open)
        quit_button: QPushButton = QPushButton("Quit")
        quit_button.clicked.connect(self.close)
        bottom: QHBoxLayout = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(open_button)
        bottom.addSpacing(12)
        bottom.addWidget(quit_button)
        layout.addLayout(bottom)

        # `poll()` runs every `POLL_MS`.
        self.timer: QTimer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    # Method `HMI.scrolled_text()`:
    @staticmethod
    def scrolled_text(layout: QVBoxLayout) -> QPlainTextEdit:
        """Make a read only text window, `SHOWN` lines high.

        Arguments:
        * `layout` (`QVBoxLayout`): The tab to put it in, under what
          is there already.

        Returns:
        * (`QPlainTextEdit`): The text window (it scrolls by itself).
        """
        text: QPlainTextEdit = QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        margins: int = round(
            2 * (text.frameWidth() + text.document().documentMargin())
        )
        text.setFixedHeight(text.fontMetrics().lineSpacing() * SHOWN + margins)
        text.setMinimumWidth(text.fontMetrics().horizontalAdvance("0" * 50))
        layout.addWidget(text)
        return text

    # Method `HMI.step()`:
    def step(self) -> str:
        """Return the jog step chosen.

        Returns:
        * (`str`): One of `JOG_STEPS` (inches).
        """
        chosen: QAbstractButton | None = self.steps.checkedButton()
        return chosen.text() if chosen is not None else JOG_STEP

    # Method `HMI.on_slider()`:
    def on_slider(self, position: int) -> None:
        """Take the feed override from the speed slider.

        Arguments:
        * `position` (`int`): Where the slider is, 0 to `SLIDER_STEPS`.
        """
        low: float = math.log10(MIN_SPEED)
        high: float = math.log10(self.top_speed)
        self.set_speed(10 ** (low + (high - low) * position / SLIDER_STEPS))

    # Method `HMI.set_speed()`:
    def set_speed(self, speed: float) -> None:
        """Set the feed override, the slider and the number shown.

        Arguments:
        * `speed` (`float`): The feed override, kept within the
          slider's range.
        """
        # The slider is moved without calling `on_slider()` again.
        speed = min(max(speed, MIN_SPEED), self.top_speed)
        self.override = speed
        low: float = math.log10(MIN_SPEED)
        high: float = math.log10(self.top_speed)
        blocked: bool = self.slider.blockSignals(True)
        self.slider.setValue(
            round((math.log10(speed) - low) / (high - low) * SLIDER_STEPS)
        )
        self.slider.blockSignals(blocked)
        self.speed_text.setText(f"{speed:.2g}x")
        self.machine.set_speed(speed)

    # Method `HMI.set_running()`:
    def set_running(self, running: bool, paused: bool) -> None:
        """Grey out the buttons that can not be pressed now.

        Arguments:
        * `running` (`bool`): True while a program runs (or is paused).
        * `paused` (`bool`): True while it is paused.
        """
        self.paused = paused
        self.running = running
        button: QPushButton
        for button in self.tool_buttons:
            button.setEnabled(not running)
        self.run_button.setText("Resume" if paused else "Start")
        self.run_button.setEnabled(
            not (
                (running and not paused) or self.drawing or not self.origin_set
            )
        )
        self.pause_button.setEnabled(running and not paused)

        # Jogs only while stopped: LinuxCNC 2.9 will not change modes
        # while a program runs or is paused.  (`poll()` sets Set Origin
        # and Home, which also depend on the position.)
        for button in self.jog_buttons:
            button.setEnabled(not running)
        self.check_mdi()
        self.check_axes()

    # Method `HMI.check_mdi()`:
    def check_mdi(self) -> None:
        """Color the MDI line; allow Execute when stopped and good.

        LinuxCNC 2.9 runs MDI only when no program is running or
        paused (its task refuses the change of mode).
        """
        kind: str = line_kind(self.mdi_entry.text())
        paint(self.mdi_entry, {"empty": BLANK, "good": GOOD, "bad": BAD}[kind])
        self.execute_button.setEnabled(not self.running and kind == "good")

    # Method `HMI.open()`:
    def open(self, path: str) -> None:
        """Open a program.

        Arguments:
        * `path` (`str`): The G-code file.

        Raises:
        * `ValueError`: If its setup is for another shop or machine.
        * `FileNotFoundError`: If there is no such file.
        """
        # A program for another shop or machine is refused, and the
        # one open before stays open.
        try:
            assembly: Assembly | None = read_file(path)
        except (OSError, ValueError):
            assembly = None  # `open_setup()` reports it.
        if assembly is not None:
            refusal: str = setup_warning(assembly, shop_name())
            if refusal:
                self.message.setText(refusal)
                raise ValueError(refusal)

        # Open it; it may not run until its origin is set.
        self.machine.open(path)
        self.start = 0
        self.lines_file = ""  # Read it again, even when the same file.
        self.message.setText("")
        self.origin_set = False
        self.zones = None
        self.jog_note = ""
        self.set_running(False, False)
        self.open_setup(path)
        self.mark_origin_set(self.origin_set)

    # Method `HMI.time_program()`:
    def time_program(self) -> None:
        """Time the program's lines, once per program read."""
        self.spans = change_spans(self.lines)
        self.sums = [0.0]
        minutes: float
        for minutes in line_minutes(self.lines, self.rapid):
            self.sums.append(self.sums[-1] + minutes)

    # Method `HMI.mark_origin_set()`:
    def mark_origin_set(self, origin_set: bool = True) -> None:
        """Mark whether the open program's origin is set.

        The one place the mark is set: Start stays greyed out until it
        is, and the message line says so.

        Arguments:
        * `origin_set` (`bool`): True once G54 is set for the program.
        """
        self.origin_set = origin_set
        self.axes_set = set(AXES) if origin_set else set()
        first: str = "Set the origin first"
        if not origin_set and not self.message.text():
            self.message.setText(first)
        elif origin_set and self.message.text().startswith(
            (first, "Origin still to set")
        ):
            self.message.setText("")
        self.set_running(self.running, self.paused)

    # Method `HMI.check_axes()`:
    def check_axes(self) -> None:
        """Color each axis entry, and grey out its button unless usable.

        A button can be pressed only while stopped, with a number in
        its entry.
        """
        axis: str
        for axis in AXES:
            text: str = self.axis_entries[axis].text().strip()
            number: bool = True
            try:
                float(text)
            except ValueError:
                number = False
            paint(
                self.axis_entries[axis],
                BLANK if not text else GOOD if number else BAD,
            )
            self.axis_buttons[axis].setEnabled(number and not self.running)

    # Method `HMI.on_set_axis()`:
    def on_set_axis(self, axis: str) -> None:
        """Make the current position on one axis read the number typed.

        It asks first (No is the default), as setting the origin on a
        real machine is a big deal.

        Arguments:
        * `axis` (`str`): `X`, `Y` or `Z`.
        """
        if self.running:
            return
        try:
            value: float = float(self.axis_entries[axis].text())
        except ValueError:
            return
        lines: list[str] = [
            "G20" if self.inches else "G21",
            f"G10 L20 P1 {axis}{value:g}",
        ]
        if not ask_yes_no(
            self,
            f"Set {axis}",
            f"Make the current {axis} read {value:g}: run {lines[-1]}?",
        ):
            return
        try:
            self.machine.mdi(*lines)
        except RuntimeError as error:
            self.message.setText(str(error))
            return

        # All three axes set, one by one, make the origin set.
        self.axes_set.add(axis)
        if self.axes_set == set(AXES):
            self.mark_origin_set()
        else:
            left: str = " ".join(a for a in AXES if a not in self.axes_set)
            self.message.setText(f"Origin still to set: {left}")

    # Method `HMI.use_setup()`:
    def use_setup(self, assembly: Assembly) -> None:
        """Take a setup's material, origins, and drawing.

        Arguments:
        * `assembly` (`Assembly`): The program's setup.
        """
        # The shop, so that its machine and materials can be checked.
        try:
            shop: dict[str, object] = shops.read(SHOP_FILE)
        except ValueError as error:
            self.message.setText(f"Shop not read: {error}")
            shop = {}
        self.program_material = (
            setup_material(assembly, material_names(shop)) or MATERIAL
        )

        # Its origin, when the shop places the machine's table (`open()`
        # has refused a program for another shop or machine).
        self.program_machine = assembly.machine or SHOP_MACHINE
        origin: tuple[float, float, float] | None = setup_origin(
            assembly, shop, SHOP_MACHINE
        )
        if origin is not None:
            if self.machine.set_work_origin(origin):
                self.origin_set = True
            else:
                self.message.setText("Origin not set: a program is running")

        # Its keep-outs and its tools' radii, for checking jogs.
        try:
            self.zones = assembly_zones(assembly)
            self.tool_radii = {
                tool.number: tool.widest_radius()
                for tool in shops.cnc_machine(
                    shop, SHOP_MACHINE, self.program_material
                ).tools
            }
        except (ValueError, KeyError) as error:
            self.zones = None
            self.message.setText(f"Setup keep-outs: {error}")

        # Its origins, for Set Origin, then its drawing.
        try:
            self.origins = named_origins(assembly)
        except ValueError as error:
            self.message.setText(f"Setup origins: {error}")
        if self.drawer is not None:
            self.drawn = assembly
            self.drawer.draw(assembly)
            self.drawing = True
            self.set_running(self.running, self.paused)

    # Method `HMI.set_material()`:
    def set_material(self, material: str) -> None:
        """Show a material in the Tools tab's chooser.

        Arguments:
        * `material` (`str`): The material's name.
        """
        index: int = self.material_chooser.findText(material)
        if index < 0:
            self.material_chooser.addItem(material)
            index = self.material_chooser.count() - 1
        self.material_chooser.setCurrentIndex(index)

    # Method `HMI.load_tools()`:
    def load_tools(self) -> None:
        """Send the tool table for the program's material, if idle."""
        self.set_material(self.program_material)
        try:
            if not self.machine.write_tool_table(self.program_material):
                self.message.setText(
                    "Tool table not sent: a program is running"
                )
        except (ValueError, RuntimeError, BridgeError) as error:
            self.message.setText(f"Tool table: {error}")

    # Method `HMI.open_setup()`:
    def open_setup(self, path: str) -> None:
        """Take a program's setup (its `SCC:` lines), if it has one.

        A program with no setup is run as is (`T.emsagc~5.2` #17); a
        wrong setup is reported, and the program is still open.  Either
        way the tool table is sent again, for the setup's material, or
        `MATERIAL` without one.

        Arguments:
        * `path` (`str`): The G-code file.
        """
        self.origins = []
        self.assembly = None
        self.setup_step = 0
        self.note = ""
        self.program_material = MATERIAL
        self.program_machine = SHOP_MACHINE
        try:
            assembly: Assembly | None = read_file(path)
            text: str = Path(path).read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            self.load_tools()
            self.message.setText(f"Setup not read: {error}")
            return
        self.inches = program_inches(text.splitlines())
        if assembly is not None:
            self.assembly = assembly
            self.use_setup(assembly)
        self.load_tools()

    # Method `HMI.on_open()`:
    def on_open(self) -> None:
        """Choose a program with a file window, and open it."""
        path: str = ask_open_file(self)
        if path:
            try:
                self.open(path)
            except (ValueError, OSError) as error:
                self.message.setText(str(error))

    # Method `HMI.show_tools()`:
    def show_tools(self) -> None:
        """Fill the Tools tab: the tools' speeds and feeds."""
        # The shop is read again each time, so edits to it show.
        text: str
        material: str = self.material_chooser.currentText()
        try:
            shop: dict[str, object] = shops.read(SHOP_FILE)
        except ValueError as error:
            text = f"The shop could not be read:\n{error}"
        else:
            blocked: bool = self.material_chooser.blockSignals(True)
            self.material_chooser.clear()
            self.material_chooser.addItems(material_names(shop))
            self.material_chooser.blockSignals(blocked)
            self.set_material(material)
            text = tool_speeds(shop, SHOP_MACHINE, material)

            # The carousel's slots and swaps for the program open.
            try:
                machine: Machine = shops.cnc_machine(
                    shop, SHOP_MACHINE, material
                )
                loads: list[str] = plan_text(
                    machine, gcode_sequence(self.lines)
                )
            except (ValueError, KeyError) as error:
                loads = [f"Carousel: {error}"]
            if loads:
                text = "\n".join([*loads, "", text])
        self.tools_table.setPlainText(text)

    # Method `HMI.tab()`:
    def tab(self) -> str:
        """Return the name of the tab shown.

        Returns:
        * (`str`): One of `TABS`.
        """
        return TABS[self.notebook.currentIndex()]

    # Method `HMI.select_tab()`:
    def select_tab(self, name: str) -> None:
        """Show a tab, as a person clicking it would.

        Arguments:
        * `name` (`str`): One of `TABS`.

        Raises:
        * `ValueError`: When there is no such tab.
        """
        if name not in self.tabs:
            raise ValueError(f"no tab {name} (tabs: {', '.join(TABS)})")
        self.notebook.setCurrentWidget(self.tabs[name])

    # Method `HMI.on_tab_changed()`:
    def on_tab_changed(self) -> None:
        """Bring the tab just shown up to date."""
        if self.tab() == "Tools":
            self.show_tools()

    # Method `HMI.on_run()`:
    def on_run(self) -> None:
        """Run the program, or resume it after a pause."""
        self.message.setText("")
        self.operator_paused = False
        if self.paused:
            self.machine.resume()
        else:
            self.machine.run(self.start)
        self.set_running(True, False)

    # Method `HMI.on_pause()`:
    def on_pause(self) -> None:
        """Pause the program; the editable lines may then be run."""
        self.operator_paused = True
        self.machine.pause()
        self.set_running(True, True)

    # Method `HMI.on_tool()`:
    def on_tool(self, step: int) -> None:
        """Move the start line to the next or previous tool change.

        Arguments:
        * `step` (`int`): +1 for the next, -1 for the previous.
        """
        changes: list[int] = [0, *tool_changes(self.lines)]
        if step > 0:
            later: list[int] = [line for line in changes if line > self.start]
            self.start = later[0] if later else self.start
        else:
            earlier: list[int] = [
                line for line in changes if line < self.start
            ]
            self.start = earlier[-1] if earlier else 0

    # Method `HMI.on_execute()`:
    def on_execute(self) -> None:
        """Run the MDI line, unless it would enter a keep-out."""
        line: str = self.mdi_entry.text().strip()
        self.jog_refusal = self.mdi_refusal(line)
        if self.jog_refusal:
            self.message.setText(self.jog_refusal)
            return
        try:
            self.machine.mdi(line)
        except RuntimeError as error:
            self.message.setText(str(error))

    # Method `HMI.unchecked()`:
    def unchecked(self) -> str:
        """Return why moves are not checked against keep-outs now.

        Keep-outs mean something only with a setup and its origin.

        Returns:
        * (`str`): `no setup`, `origin not set`, or `""` to check.
        """
        if self.zones is None:
            return "no setup"
        if not self.origin_set:
            return "origin not set"
        return ""

    # Method `HMI.mdi_refusal()`:
    def mdi_refusal(self, line: str) -> str:
        """Return why a typed line must not run, as for a jog.

        Its moves are checked against the keep-outs as a jog is (S12,
        `T.hs~5.1.5` #42).  Incremental (`G91`) moves are refused while
        keep-outs are checked, as they are not followed here; without
        a setup or an origin nothing is checked, which is said once.

        Arguments:
        * `line` (`str`): The typed line.

        Returns:
        * (`str`): Why it is refused, or `""` to run it.
        """
        # Nothing to check against: said once.
        unchecked: str = self.unchecked()
        if unchecked:
            if unchecked != self.jog_note:
                self.jog_note = unchecked
                self.message.setText(f"MDI not checked: {unchecked}")
            return ""

        # The distance mode and units: LinuxCNC's, unless the line sets
        # them.
        words: str = COMMENT.sub("", line)
        incremental, metric = self.machine.modes()
        if incremental or INCREMENTAL.search(words):
            return (
                "MDI refused: G91 moves are not checked against the "
                "keep-outs; use G90"
            )
        if METRIC.search(words):
            metric = True
        elif INCH.search(words):
            metric = False

        # Each piece of the move, checked as a jog is.
        status: HMIStatus = self.machine.status()
        try:
            pieces: list[
                tuple[tuple[float, float, float], tuple[float, float, float]]
            ] = mdi_segments(line, status.position, metric)
        except ValueError as error:
            return f"MDI refused: it can not be checked ({error})"
        radius: float = self.tool_radii.get(status.tool, 0.0)
        for start, end in pieces:
            hit: str = jog_hit(self.zones or [], start, end, radius)
            if hit:
                return f"MDI refused: it would enter {hit}"
        return ""

    # Method `HMI.on_stop()`:
    def on_stop(self) -> None:
        """Stop at once, ready to run again from the program's start."""
        self.message.setText("")
        self.operator_paused = False
        self.machine.stop()
        self.start = 0
        self.set_running(False, False)

    # Method `HMI.on_jog()`:
    def on_jog(self, axis: int, direction: int) -> None:
        """Jog one axis by the chosen step.

        Arguments:
        * `axis` (`int`): The axis: 0 for X, 1 for Y, 2 for Z.
        * `direction` (`int`): +1 or -1.
        """
        step: float = float(self.step())
        self.jog_refusal = ""

        # Nothing to check against: said once, and the jog is sent.
        unchecked: str = self.unchecked()
        if unchecked:
            if unchecked != self.jog_note:
                self.jog_note = unchecked
                self.message.setText(f"Jogs not checked: {unchecked}")
            self.machine.jog(axis, direction, step)
            return

        # A jog that would enter a keep-out is refused, not shortened.
        status: HMIStatus = self.machine.status()
        start: tuple[float, float, float] = status.position
        end: list[float] = list(start)
        end[axis] += direction * step
        x, y, z = end
        hit: str = jog_hit(
            self.zones or [],
            start,
            (x, y, z),
            self.tool_radii.get(status.tool, 0.0),
        )
        if hit:
            self.jog_refusal = (
                f"Jog refused: it would enter {hit}; choose a smaller "
                "step and try again"
            )
            self.message.setText(self.jog_refusal)
            return
        self.machine.jog(axis, direction, step)

    # Method `HMI.on_home()`:
    def on_home(self) -> None:
        """Rapid to the work origin."""
        try:
            self.machine.go_origin(self.machine.status().position[2])
        except RuntimeError as error:
            self.message.setText(str(error))

    # Method `HMI.on_set_origin()`:
    def on_set_origin(self) -> None:
        """Make the current position zero, after asking (No first).

        With a setup, the operator first picks which of its origins the
        tool tip is at, and the position is made to read that point.
        """
        if self.origins:
            self.set_named_origin()
            return
        if ask_yes_no(
            self, "Set Origin", "Make the current position the program's zero?"
        ):
            try:
                self.machine.set_origin()
            except RuntimeError as error:
                self.message.setText(str(error))
            else:
                self.mark_origin_set()

    # Method `HMI.on_next_step()`:
    def on_next_step(self) -> None:
        """Show the setup's next item, with its note (`T.emsagc~5.2` #14).

        Step N draws items 1 to N only, so each step adds one item;
        the step after the last shows the whole setup again.
        """
        if self.assembly is None:
            self.message.setText("This program has no setup.")
            return
        items: list[AssemblyItem] = self.assembly.items
        self.setup_step += 1
        shown: Assembly
        if self.setup_step > len(items):
            self.setup_step = 0
            shown = self.assembly
            text: str = f"Setup: all {len(items)} items."
        else:
            item: AssemblyItem = items[self.setup_step - 1]
            shown = Assembly(items[: self.setup_step])
            text = (
                f"Step {self.setup_step}/{len(items)}, "
                f"{item.name.replace('_', ' ')}: {item.note}"
            )
        self.note = text
        self.message.setText(text)
        if self.drawer is not None:
            self.drawn = shown
            self.drawer.draw(shown)

    # Method `HMI.on_toggle()`:
    def on_toggle(self) -> None:
        """Show or hide what the View tab's toggles say.

        Only visibility changes (`SetupView.apply_hidden()`); the
        setup is not drawn again, as nothing in it differs.  A drawing
        made later (Next Step, a new open) keeps the same choices.
        """
        if self.drawer is None:
            self.message.setText("No SolidCraft to show them in.")
            return
        self.drawer.hidden = {
            kind
            for label, kind, _ in TOGGLES
            if not self.toggles[label].isChecked()
        }
        if self.drawn is not None:
            self.drawer.draw(self.drawn)

    # Method `HMI.set_named_origin()`:
    def set_named_origin(self) -> None:
        """Pick the origin the tool tip is at, confirm, and set G54."""
        names: list[str] = [name for name, _ in self.origins]
        picked: str = ask_choice(
            self, "Set Origin", "Where is the tool tip now?", names
        )
        if not picked:
            return
        point: Point = dict(self.origins)[picked]
        lines: list[str] = origin_lines(point, self.inches)
        if ask_yes_no(
            self,
            "Set Origin",
            f"The tool tip is at {picked}: run {lines[-1]}?",
        ):
            try:
                self.machine.mdi(*lines)
            except RuntimeError as error:
                self.message.setText(str(error))
            else:
                self.mark_origin_set()

    # Method `HMI.buttons()`:
    def buttons(self) -> list[QAbstractButton]:
        """Return every button with a label, on every tab.

        Returns:
        * (`list[QAbstractButton]`): The buttons, check buttons and
          jog steps.
        """
        return [
            button
            for button in self.findChildren(QAbstractButton)
            if button.text()
        ]

    # Method `HMI.press()`:
    def press(self, label: str) -> str:
        """Press a button, as a person would.

        Arguments:
        * `label` (`str`): The text on it.

        Returns:
        * (`str`): `ok`, or `error: ...` when there is no such button
          or it is greyed out.
        """
        button: QAbstractButton
        for button in self.buttons():
            if button.text() == label:
                if not button.isEnabled():
                    return f"error: {label} is greyed out"
                self.jog_refusal = ""
                button.click()
                return (
                    f"error: {self.jog_refusal}" if self.jog_refusal else "ok"
                )
        return f"error: no button {label}"

    # Method `HMI.show_state()`:
    def show_state(self) -> dict[str, Any]:
        """Return what the window shows (`show()` is `QWidget`'s).

        Returns:
        * (`dict[str, Any]`): `executed` and `coming` (the G-code
          windows), `position`, `message`, `mdi` and `mdi_color` (the
          MDI line), `step` and `speed` (those shown), `buttons` (each
          button's state, `normal` or `disabled`, by its text) and
          `texts` (the contents of every text window, such as Tools),
          and `drawing` (True while a setup is being drawn in
          SolidCraft) and `origins` (the setup's named origins, work
          millimeters) and `setup_step` (how many setup items Next
          Step shows; 0 for all), `origin_set` (True once the
          program's origin is set), `toggles` (each View toggle, True
          when shown), `axes_set` (the axes set one by one, or all),
          `axis_entries` (the numbers typed for them), `next_tool`
          (the next tool and the time left until it), `tab` (the name
          of the tab shown), and `setup_progress` (how much of the
          setup is drawn, of how much).
        """
        return {
            "executed": self.executed.toPlainText(),
            "coming": self.coming.toPlainText(),
            "position": self.position.text(),
            "message": self.message.text(),
            "mdi": self.mdi_entry.text(),
            "mdi_color": str(self.mdi_entry.property("background")),
            "step": self.step(),
            "speed": self.speed_text.text(),
            "drawing": self.drawer is not None and self.drawer.busy,
            "origins": dict(self.origins),
            "setup_step": self.setup_step,
            "origin_set": self.origin_set,
            "toggles": {
                label: self.toggles[label].isChecked()
                for label, _, _ in TOGGLES
            },
            "axes_set": sorted(self.axes_set),
            "axis_entries": {
                axis: self.axis_entries[axis].text() for axis in AXES
            },
            "next_tool": self.next_tool.text(),
            "tab": self.tab(),
            "setup_progress": [self.progress.value(), self.progress.maximum()],
            "buttons": {
                button.text(): "normal" if button.isEnabled() else "disabled"
                for button in self.buttons()
            },
            "texts": [
                text.toPlainText()
                for text in self.findChildren(QPlainTextEdit)
            ],
        }

    # Method `HMI.ping()`:
    def ping(self) -> None:
        """Do nothing (the port's `ping`)."""

    # Method `HMI.handle()`:
    # A flat list of commands reads best, so it has many returns and
    # branches.
    # pylint: disable-next=too-many-return-statements,too-many-branches
    def handle(self, line: str) -> str:
        """Answer one command from the command port.

        Arguments:
        * `line` (`str`): The command.

        Returns:
        * (`str`): The answer: `ok`, the status, or `error: ...`.
        """
        word, _, rest = line.partition(" ")
        actions: dict[str, Any] = {
            "ping": self.ping,
            "run": self.on_run,
            "start": self.on_run,
            "pause": self.on_pause,
            "stop": self.on_stop,
            "reset": self.on_stop,
            "tool+": functools.partial(self.on_tool, +1),
            "tool-": functools.partial(self.on_tool, -1),
            "quit": self.close,
        }
        try:
            if word in actions:
                actions[word]()
            elif word == "press" and rest:
                return self.press(rest.strip())
            elif word == "origin" and rest:
                axis, _, value = rest.strip().partition(" ")
                if axis.upper() not in AXES:
                    return f"error: no axis {axis}"
                self.axis_entries[axis.upper()].setText(value.strip())
            elif word == "tab" and rest:
                self.select_tab(rest.strip())
            elif word == "type":
                self.mdi_entry.setText(rest)
            elif word == "show":
                return json.dumps(self.show_state())
            elif word == "answer" and HEADLESS:
                ANSWERS.append(rest.strip())
            elif word == "open" and rest:
                self.open(rest.strip())
            elif word == "speed" and rest:
                self.set_speed(float(rest))
            elif word == "status":
                status: HMIStatus = self.machine.status()
                x, y, z = status.position
                return (
                    f"file={status.file} line={status.line} "
                    f"x={x:.4f} y={y:.4f} z={z:.4f} tool={status.tool} "
                    f"start={self.start} state={status.state}"
                )
            elif word == "messages":
                return f"messages: {' | '.join(self.machine.messages)}"
            elif word == "log":
                return f"log: {' | '.join(self.machine.log)}"
            else:
                return f"error: unknown command {line!r}"
        except (ValueError, OSError, BridgeError) as error:
            return f"error: {error}"
        return "ok"

    # Method `HMI.follow_tool()`:
    def follow_tool(self, tool: int) -> None:
        """Hide a newly drawn tool's holder, when holders are hidden.

        `sim_solidcraft.py` draws a tool when it is changed to, so on
        a change the setup goes to the drawer again, which changes
        nothing but the visibility (`SetupView.apply_hidden()`).

        Arguments:
        * `tool` (`int`): The tool in the spindle now.
        """
        if tool == self.last_tool:
            return
        self.last_tool = tool
        if (
            self.drawer is not None
            and self.drawn is not None
            and "holder" in self.drawer.hidden
        ):
            self.drawer.draw(self.drawn)

    # Method `HMI.show_drawing()`:
    def show_drawing(self) -> None:
        """Show how far the setup's drawing is, and any error in it."""
        # While a setup is drawn, Start waits, and the bar shows how far.
        if self.drawer is None:
            return
        done, total = self.drawer.view.progress
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        if self.drawer.busy != self.drawing:
            self.drawing = self.drawer.busy
            self.set_running(self.running, self.paused)

        # A setup that could not be drawn (from the drawing thread); a
        # step's note stays first, the error after it.
        problem: str = self.drawer.message()
        if problem:
            self.message.setText(
                f"{self.note} ({problem})" if self.note else problem
            )

    # Method `HMI.show_program()`:
    def show_program(self, status: HMIStatus) -> None:
        """Show the program around the line being run.

        Before a run, the lines from the start line on are coming.
        While paused, the whole program is in the two windows, put
        there once so that they can be scrolled.

        Arguments:
        * `status` (`HMIStatus`): LinuxCNC's state.
        """
        current: int = status.line if self.running else max(0, self.start - 1)
        if self.paused and not self.scrolling:
            self.executed.setPlainText("\n".join(self.lines[:current]))
            self.coming.setPlainText("\n".join(self.lines[current:]))
            done: Any = self.executed.verticalScrollBar()
            done.setValue(done.maximum())
            self.coming.verticalScrollBar().setValue(0)
            self.scrolling = True
        elif not self.paused:
            self.scrolling = False
            self.executed.setPlainText(
                "\n".join(self.lines[max(0, current - SHOWN) : current])
            )
            self.coming.setPlainText(
                "\n".join(self.lines[current : current + SHOWN])
            )

    # Method `HMI.poll()`:
    def poll(self) -> None:
        """Show the machine's state, and answer the port (`timer`)."""
        # The setup's drawing.
        self.show_drawing()

        # A LinuxCNC that has gone is reported, while the port still
        # answers, and the window stays up to be read.
        try:
            status: HMIStatus = self.machine.status()
        except (OSError, BridgeError) as error:
            self.message.setText(f"LinuxCNC is not answering: {error}")
            if self.port is not None:
                self.port.poll(self.handle)
            return

        # The program, read once per file.  The buttons follow
        # LinuxCNC's state (a program may end, or be stopped, without
        # the HMI).
        if status.file != self.lines_file:
            self.lines_file = status.file
            self.lines = self.machine.program_lines(status.file)
            self.time_program()
        if status.state and (
            (status.state != "idle", status.state == "paused")
            != (self.running, self.paused)
        ):
            self.set_running(status.state != "idle", status.state == "paused")

        # A pause no one asked for is the program's (`M0`, at a tool
        # change; its `MSG` is on the message line).  A person presses
        # Start (Resume); with no one there (headless), it goes on.
        if status.state == "paused" and not self.operator_paused and HEADLESS:
            self.machine.resume()
            self.set_running(True, False)
        self.show_program(status)

        # Home only while stopped, away from the origin; Set Origin
        # also while this program's origin is not set yet.
        x, y, z = status.position
        away: bool = max(abs(x), abs(y), abs(z)) > AT_ORIGIN
        self.home_button.setEnabled(away and not self.running)
        self.origin_button.setEnabled(
            (away or not self.origin_set) and not self.running
        )

        # A tool drawn since (a tool change) follows the Holders toggle.
        self.follow_tool(status.tool)

        # The next tool, and the time left until it (cheap: the line
        # times are added up once per program).
        self.next_tool.setText(
            next_tool_text(
                self.lines,
                self.sums,
                self.spans,
                status.line if self.running else self.start,
                self.override,
            )
        )

        # The position, the tool and any message.
        self.position.setText(
            f"X {x:9.4f}  Y {y:9.4f}  Z {z:9.4f}  T{status.tool:02d}"
            f"  start line {self.start}  "
            f"{self.program_machine}, {self.program_material}"
        )
        if status.messages:
            self.message.setText(status.messages[-1])

        # Commands from the port.
        if self.port is not None:
            self.port.poll(self.handle)


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Show the HMI until its window is closed.

    Arguments:
    * `arguments` (`list[str]`):
      The command line arguments, less the program name.

    Returns:
    * (`int`): The exit status.
    """
    # The command line.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("program", nargs="?", help="G-code to open")
    parser.add_argument("--port", type=int, help="a command port on 127.0.0.1")
    parser.add_argument(
        "--lcnc-port",
        type=int,
        default=PORT,
        help="the port of serve_linuxcnc (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="use no LinuxCNC"
    )
    parser.add_argument(
        "--solidcraft",
        type=int,
        help="a SolidCraft control port, to draw each program's setup",
    )
    parser.add_argument(
        "--shop",
        type=Path,
        default=SHOP_FILE,
        help="the shop's file (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="draw nothing (Qt offscreen), for tests through --port",
    )
    options: argparse.Namespace = parser.parse_args(arguments)
    if options.headless:
        use_headless()

    # The machine, on and homed, and the command port.
    try:
        machine: HMIMachine = HMIMachine(options.dry_run, options.lcnc_port)
        machine.start()
        top_speed: float = machine.max_speed()
    except (OSError, RuntimeError, ValueError, BridgeError) as error:
        print(f"lcnc_hmi_qt.py: {error}", file=sys.stderr)
        return 1
    port: CommandPort | None = (
        CommandPort(options.port) if options.port else None
    )

    # The shop that names the tooling (`T.emsagc~5.2` #63), and the
    # SolidCraft the setups are drawn in, if any.
    try:
        use_shop(shops.read(options.shop))
    except shops.ShopError as error:
        print(f"lcnc_hmi_qt.py: {error}", file=sys.stderr)
        return 1
    drawer: SetupDrawer | None = (
        SetupDrawer(
            SetupView(PyBind(connect(str(options.solidcraft))), ModelCache())
        )
        if options.solidcraft
        else None
    )

    # The window.  An earlier HMI may have left another speed, and the
    # slider starts at the programmed feed.
    application: QApplication = QApplication(sys.argv[:1])
    hmi: HMI = HMI(machine, top_speed, port)
    hmi.set_speed(1.0)
    hmi.drawer = drawer

    # A `SIGTERM` closes it as Quit does (Python sees the signal at
    # the next `poll()`, as Qt's loop is not Python's).
    def terminate(_number: int, _frame: FrameType | None) -> None:
        """Close the window on a `SIGTERM`.

        Arguments:
        * `_number` (`int`): The signal (ignored).
        * `_frame` (`FrameType | None`): Where Python was (ignored).
        """
        hmi.close()

    signal.signal(signal.SIGTERM, terminate)
    if options.program:
        try:
            hmi.open(options.program)
        except (ValueError, OSError) as error:
            hmi.message.setText(str(error))
    hmi.show()
    return application.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
