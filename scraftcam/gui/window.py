"""A window of the GUI: the top line, the action rows and the panels.

From the top down (`T.osiade~5.1.9` #82):

* The top line: [Stop All] (only while more than one machine runs,
  #2), [Tree] (shows or hides the tree, on the left edge, #70), the
  shop's and the design's names, the latest message (red for a
  problem, #95), [+ Panel] and [x].
* The action rows of the item selected (#73, #75); for now only
  [New Shop], while there is no shop, which opens `NewShopDialog`
  (#97, #98; it also opens by itself when the GUI starts with no
  shop, unless headless).
* The panels, side by side, with a splitter between them; [+ Panel]
  adds one (#94).

Each window draws from the one `App` (`app.py`), and redraws whenever
it changes, so all of the windows agree (#3).  A window that controls
a running machine refuses to close (#67).

With `--port`, `CommandServer` answers the command port (`port.py`,
#96): `status` (what the windows show), `press` (a top line button,
as a person would; `params`: `button`, and `window`, from 0) and
`new_shop` (makes a shop, as `NewShopDialog` would; `params`:
`directory`, `name`, `units`, `machines`) and `quit` (closes every
window, unless one refuses).
"""

import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ..packages import require
from . import port
from .app import (
    MACHINE_KINDS,
    MANUAL_PREFIX,
    NEW_SHOP_DIRECTORY,
    UNIT_LABELS,
    UNITS,
    App,
    Message,
)
from .editor import HINT, editor_command
from .port import Method, PortError, text_param
from .tree import Node, edit_path
from .views import Panel, TreeView, TreeWatcher

# `PySide6` lives in `~/.scraftcam/packages/`, so it is put on
# `sys.path` (and fetched, the first time) before it is imported.
require("PySide6")
# pylint: disable=wrong-import-position,wrong-import-order
from PySide6.QtCore import (  # noqa: E402
    QCoreApplication,
    QEvent,
    QMessageLogContext,
    Qt,
    QTimer,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtGui import QCloseEvent, QDesktopServices  # noqa: E402
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# pylint: enable=wrong-import-position,wrong-import-order

# A new window's size (#109): small, so SolidCraft fits beside it.
WIDTH: int = 720
HEIGHT: int = 480

# The color of a problem on the top line.
PROBLEM_COLOR: str = "#c00000"

# What Qt's offscreen platform says each time a window is shown; it
# means nothing here, so `use_headless()` drops it.
OFFSCREEN_NOISE: str = "This plugin does not support propagateSizeHints()"

# The least width of `NewShopDialog`'s directory, in pixels.
DIRECTORY_WIDTH: int = 360

# The tree's share of the window's width when [Tree] shows it.
TREE_SHARE: float = 0.3

# How long `quit` waits, so its answer is sent before the GUI closes.
QUIT_DELAY_MS: int = 200

# Every open window, oldest first (the command port's `window`).
WINDOWS: list["Window"] = []


# Function `use_headless()`:
def use_headless() -> None:
    """Draw offscreen from now on (tests, and `--headless`).

    It must be called before the `QApplication` is made.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    qInstallMessageHandler(qt_message)


# Function `qt_message()`:
def qt_message(
    _kind: QtMsgType, _context: QMessageLogContext, message: str
) -> None:
    """Write a message from Qt, less `OFFSCREEN_NOISE`.

    Arguments:
    * `_kind` (`QtMsgType`): Debug, warning and so on (ignored).
    * `_context` (`QMessageLogContext`): Where it came from (ignored).
    * `message` (`str`): The message.
    """
    if message != OFFSCREEN_NOISE:
        print(message, file=sys.stderr)


# Function `make_application()`:
def make_application(*, headless: bool) -> QApplication:
    """Make the one `QApplication`, or return the one already made.

    Arguments:
    * `headless` (`bool`): True to draw offscreen (`use_headless()`).

    Returns:
    * (`QApplication`): The application.
    """
    if headless:
        use_headless()
    existing: object = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication(sys.argv[:1])


# Function `delete_windows()`:
def delete_windows() -> None:
    """Close and delete every top level widget, now.

    A widget whose signals are connected to its own methods is kept
    alive by them until Python exits; PySide then deletes what is
    left in no safe order, and with many widgets left (as the tests
    leave) that can crash Python after everything has passed.  Called
    before that (`atexit`), this deletes them in Qt's own order.
    """
    application: object = QApplication.instance()
    if not isinstance(application, QApplication):
        return
    top: QWidget
    for top in application.topLevelWidgets():
        top.close()
        top.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


# Function `run()`:
def run(model: App, *, headless: bool, command_port: int) -> int:
    """Show the first window, and run Qt until the last one closes.

    Arguments:
    * `model` (`App`): What every window shows.
    * `headless` (`bool`): True to draw offscreen.
    * `command_port` (`int`): The command port, or 0 for none.

    Returns:
    * (`int`): Qt's exit code, 0 normally, or 1 when the port can
      not be opened.
    """
    application: QApplication = make_application(headless=headless)
    first: Window = Window(model)
    first.show()
    watcher: TreeWatcher = TreeWatcher(model)

    # No shop: offer to make one (#97), when someone can answer.
    if model.shop is None and not headless:
        first.new_shop()

    # The command port, if asked for.
    if command_port:
        server: CommandServer = CommandServer(model)
        if not server.listen_local(command_port):
            print(
                f"Can not open port {command_port}: {server.errorString()}",
                file=sys.stderr,
            )
            return 1

    # Until the last window closes, with the trees watched.
    status: int = int(application.exec())
    model.forget(watcher.follow)
    return status


# Class `Window`:
# A window holds a widget for each thing it shows.
# pylint: disable-next=too-many-instance-attributes
class Window(QWidget):
    """One window of the GUI.

    Attributes:
    * `model` (`App`): What every window shows.
    * `controls` (`set[str]`): The machines this window controls.
    * `buttons` (`dict[str, QPushButton]`): The top line's buttons,
      by label (for the command port's `press`).
    * `design_label` (`QLabel`): The design's name.
    * `message_label` (`QLabel`): The latest message.
    * `action_rows` (`QWidget`): The action rows.
    * `edit_label` (`QLabel`): The selected item, before [Edit].
    * `edit_row` (`QWidget`): The action row with [Edit].
    * `new_shop_row` (`QWidget`): The action row with [New Shop].
    * `panels` (`list[Panel]`): The panels, left to right.
    * `shop_label` (`QLabel`): The shop's name.
    * `splitter` (`QSplitter`): The tree, then the panels.
    * `tree` (`TreeView`): The shop's and the design's files.
    * `current` (`int`): The current panel's index (#122).
    """

    def __init__(self, model: App, controls: set[str] | None = None) -> None:
        """Make a window, with one empty panel, and show what it shows.

        Arguments:
        * `model` (`App`): What every window shows.
        * `controls` (`set[str] | None`): The machines this window
          controls, if any.
        """
        super().__init__()
        self.model: App = model
        self.controls: set[str] = set() if controls is None else controls
        self.buttons: dict[str, QPushButton] = {}
        self.resize(WIDTH, HEIGHT)

        # The top line, left to right.
        top: QHBoxLayout = QHBoxLayout()
        self.add_button(top, "Stop All", self.stop_all)
        self.add_button(top, "Tree", self.toggle_tree)
        self.shop_label: QLabel = QLabel()
        self.design_label: QLabel = QLabel()
        self.message_label: QLabel = QLabel()
        self.message_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        top.addWidget(self.shop_label)
        top.addWidget(self.design_label)
        top.addWidget(self.message_label, 1)
        self.add_button(top, "+ Panel", self.add_panel)
        self.add_button(top, "x", self.close)
        close: QPushButton = self.buttons["x"]
        close.setFixedWidth(close.sizeHint().height())
        self.buttons["Stop All"].setStyleSheet(
            f"color: white; background: {PROBLEM_COLOR}"
        )

        # The action rows, under the top line: [New Shop], while there
        # is no shop.
        self.action_rows: QWidget = QWidget()
        rows: QVBoxLayout = QVBoxLayout(self.action_rows)
        rows.setContentsMargins(0, 0, 0, 0)
        self.new_shop_row: QWidget = self.action_row(
            rows, QLabel("No shop yet:"), "New Shop", self.new_shop
        )

        # The selected item's row: [Edit], for a file to edit by hand.
        self.edit_label: QLabel = QLabel()
        self.edit_row: QWidget = self.action_row(
            rows, self.edit_label, "Edit", self.edit
        )

        # The tree on the left, then the panels; the first is current.
        self.splitter: QSplitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree: TreeView = TreeView()
        self.tree.itemClicked.connect(self.select_item)
        self.splitter.addWidget(self.tree)
        self.panels: list[Panel] = []
        self.current: int = 0
        self.add_panel()
        tree_width: int = int(WIDTH * TREE_SHARE)
        self.splitter.setSizes([tree_width, WIDTH - tree_width])

        # The bands, top to bottom.
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.action_rows)
        layout.addWidget(self.splitter, 1)

        # Redraw whenever the model changes, starting now.
        model.listen(self.redraw)
        self.redraw()
        WINDOWS.append(self)

    def add_button(
        self, line: QHBoxLayout, label: str, action: Callable[[], object]
    ) -> None:
        """Add a button to the top line.

        Arguments:
        * `line` (`QHBoxLayout`): The top line.
        * `label` (`str`): The button's label.
        * `action` (`Callable[[], object]`): What a press calls.
        """
        button: QPushButton = QPushButton(label)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(action)
        line.addWidget(button)
        self.buttons[label] = button

    def action_row(
        self,
        rows: QVBoxLayout,
        label: QLabel,
        button: str,
        action: Callable[[], object],
    ) -> QWidget:
        """Add an action row: a label, then a button.

        Arguments:
        * `rows` (`QVBoxLayout`): The action rows.
        * `label` (`QLabel`): What the row is about.
        * `button` (`str`): The button's label.
        * `action` (`Callable[[], object]`): What a press calls.

        Returns:
        * (`QWidget`): The row.
        """
        row: QWidget = QWidget()
        line: QHBoxLayout = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(label)
        self.add_button(line, button, action)
        line.addStretch(1)
        rows.addWidget(row)
        return row

    def redraw(self) -> None:
        """Show what the model holds now."""
        model: App = self.model
        self.setWindowTitle(model.title())
        self.shop_label.setText(f"Shop: {model.shop_title}")
        self.design_label.setText(f"Design: {model.design_title()}")
        latest: Message = model.latest()
        self.message_label.setText(latest.text)
        self.message_label.setToolTip(latest.text)
        self.message_label.setStyleSheet(
            f"color: {PROBLEM_COLOR}" if latest.problem else ""
        )
        self.buttons["Stop All"].setVisible(model.stop_all_shown())
        self.new_shop_row.setVisible(model.shop is None)
        self.buttons["New Shop"].setVisible(model.shop is None)

        # The tree, when it was read again, and the panels' items;
        # then the selected item's action row.
        if self.tree.version != model.tree_version:
            roots: list[Node] = [
                root
                for root in (model.shop_root, model.design_root)
                if root is not None
            ]
            self.tree.fill(roots, model.tree_version)
            panel: Panel
            for panel in self.panels:
                if panel.node is not None:
                    node: Node | None = self.tree.nodes.get(
                        str(panel.node.path)
                    )
                    if node is not None:
                        panel.show_node(node)
        self.show_actions()

    def toggle_tree(self) -> None:
        """Show the tree if it is hidden, or hide it ([Tree])."""
        # Hide it; or show it, `TREE_SHARE` of the width, never squeezed
        # to nothing by the splitter.
        if not self.tree.isHidden():
            self.tree.hide()
            return
        self.tree.show()
        sizes: list[int] = self.splitter.sizes()
        total: int = sum(sizes)
        tree_width: int = int(total * TREE_SHARE)
        rest: int = max(1, len(sizes) - 1)
        self.splitter.setSizes(
            [tree_width] + [(total - tree_width) // rest] * (len(sizes) - 1)
        )

    def add_panel(self) -> None:
        """Add an empty panel on the right ([+ Panel]); it is current."""
        panel: Panel = Panel(len(self.panels) + 1)
        panel.clicked.connect(functools.partial(self.make_current, panel))
        self.panels.append(panel)
        self.splitter.addWidget(panel)
        self.make_current(panel)

    def make_current(self, panel: Panel) -> None:
        """Make a panel the current one: the next item shows there.

        Arguments:
        * `panel` (`Panel`): The panel.
        """
        self.current = self.panels.index(panel)
        other: Panel
        for other in self.panels:
            other.set_current(other is panel)
        self.show_actions()

    def select_item(self, item: QTreeWidgetItem) -> None:
        """Show a tree item in the current panel (#122).

        Arguments:
        * `item` (`QTreeWidgetItem`): The item clicked.
        """
        node: Node | None = self.tree.node_of(item)
        if node is not None:
            self.panels[self.current].show_node(node)
        self.show_actions()

    def show_actions(self) -> None:
        """Show the action rows of the current panel's item (#73)."""
        node: Node | None = (
            self.panels[self.current].node if self.panels else None
        )
        editable: bool = node is not None and edit_path(node) is not None
        self.edit_row.setVisible(editable)
        self.buttons["Edit"].setVisible(editable)
        if node is not None:
            self.edit_label.setText(f"{node.label()}:")

    def edit(self) -> None:
        """Open the current panel's file in an editor ([Edit], #124)."""
        # The file.
        node: Node | None = self.panels[self.current].node
        path: Path | None = None if node is None else edit_path(node)
        if path is None:
            return

        # `VISUAL`, `EDITOR` in a terminal, or why not.
        command: list[str]
        problem: str
        command, problem = editor_command(path, os.environ, shutil.which)
        if problem:
            self.model.say(problem, problem=True)
            return
        if command:
            try:
                subprocess.Popen(  # pylint: disable=consider-using-with
                    command, start_new_session=True
                )
            except OSError as error:
                self.model.say(f"{command[0]}: {error}", problem=True)
            return

        # Neither: the desktop's default, with the hint once a session.
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.model.say(f"No editor opened {path}.", problem=True)
        elif not self.model.editor_hinted:
            self.model.editor_hinted = True
            self.model.say(HINT)

    def stop_all(self) -> None:
        """Stop every machine ([Stop All])."""
        self.model.stop_all()

    def new_shop(self) -> None:
        """Ask about the new shop, and make it ([New Shop])."""
        dialog: NewShopDialog = NewShopDialog(self, self.model)
        dialog.open()

    def closeEvent(  # pylint: disable=invalid-name
        self, event: QCloseEvent
    ) -> None:
        """Close, unless this window controls a running machine (#67).

        (Qt's name for it; [x] and the window's own close come here.)

        Arguments:
        * `event` (`QCloseEvent`): Accepted, or ignored with the
          reason on the top line.
        """
        refusal: str = self.model.close_refusal(self.controls)
        if refusal:
            self.model.say(refusal, problem=True)
            event.ignore()
            return
        self.model.forget(self.redraw)
        if self in WINDOWS:
            WINDOWS.remove(self)
        event.accept()


# Class `CommandServer`:
class CommandServer(QTcpServer):
    """The command port (`port.py`): one JSON line in, one out.

    Attributes:
    * `model` (`App`): What every window shows.
    * `methods` (`dict[str, Method]`): The port's methods, by name.
    """

    def __init__(self, model: App) -> None:
        """Make the server; `listen()` opens its port.

        Arguments:
        * `model` (`App`): What every window shows.
        """
        super().__init__()
        self.model: App = model
        self.methods: dict[str, Method] = {
            "new_shop": self.new_shop,
            "press": self.press,
            "quit": self.quit,
            "select": self.select,
            "status": self.status,
            "tree": self.tree,
        }
        self.newConnection.connect(self.accept)

    def listen_local(self, number: int) -> bool:
        """Listen on a port of 127.0.0.1 only.

        Arguments:
        * `number` (`int`): The port, or 0 for any free one
          (`serverPort()` says which).

        Returns:
        * (`bool`): True when it listens.
        """
        return bool(
            self.listen(
                QHostAddress(QHostAddress.SpecialAddress.LocalHost), number
            )
        )

    def accept(self) -> None:
        """Take each new connection, and answer its lines."""
        while self.hasPendingConnections():
            socket: QTcpSocket = self.nextPendingConnection()
            socket.readyRead.connect(functools.partial(self.answer, socket))
            socket.disconnected.connect(socket.deleteLater)

    def answer(self, socket: QTcpSocket) -> None:
        """Answer every whole line a connection has sent.

        Arguments:
        * `socket` (`QTcpSocket`): The connection.
        """
        while socket.canReadLine():
            line: str = bytes(socket.readLine().data()).decode()
            reply_line: str = port.reply(line, self.methods)
            socket.write((reply_line + "\n").encode())
            socket.flush()

    @staticmethod
    def window(params: dict[str, object]) -> "Window":
        """Return the window a request names (`window`, from 0).

        Arguments:
        * `params` (`dict[str, object]`): The request's parameters.

        Returns:
        * (`Window`): The window.

        Raises:
        * `PortError`: If there is no such window.
        """
        index: object = params.get("window", 0)
        if not isinstance(index, int) or not 0 <= index < len(WINDOWS):
            raise PortError(f"no window {index}", port.INVALID_PARAMS)
        return WINDOWS[index]

    def status(self, _params: dict[str, object]) -> object:
        """Return what the windows show (`status`).

        Arguments:
        * `_params` (`dict[str, object]`): None needed.

        Returns:
        * (`object`): The model's state, and each window's.
        """
        model: App = self.model
        latest: Message = model.latest()
        return {
            "title": model.title(),
            "shop": model.shop_title,
            "design": model.design_title(),
            "message": latest.text,
            "problem": latest.problem,
            "running": sorted(model.running),
            "windows": [
                {
                    "buttons": [
                        label
                        for label, button in top.buttons.items()
                        if not button.isHidden()
                    ],
                    "tree": not top.tree.isHidden(),
                    "panels": len(top.panels),
                }
                for top in WINDOWS
            ],
        }

    def press(self, params: dict[str, object]) -> object:
        """Press a top line button, as a person would (`press`).

        Arguments:
        * `params` (`dict[str, object]`): `button` (its label) and
          `window` (from 0; 0 if not given).

        Returns:
        * (`object`): "pressed LABEL".

        Raises:
        * `PortError`: If there is no such button, or it is hidden.
        """
        top: Window = self.window(params)
        label: str = text_param(params, "button")
        button: QPushButton | None = top.buttons.get(label)
        if button is None:
            raise PortError(
                f"no button `{label}`; there are: {', '.join(top.buttons)}",
                port.INVALID_PARAMS,
            )
        if button.isHidden() or not button.isEnabled():
            raise PortError(f"`{label}` is not showing")
        button.click()
        return f"pressed {label}"

    def new_shop(self, params: dict[str, object]) -> object:
        """Make a new shop, as `NewShopDialog` would (`new_shop`).

        Arguments:
        * `params` (`dict[str, object]`): `directory`, `name`, `units`
          (strings) and `machines` (a list of kinds' keys).

        Returns:
        * (`object`): The new `shop.toml`'s path.

        Raises:
        * `PortError`: If an answer is not allowed, or it can not be
          written.
        """
        machines: object = params.get("machines", [])
        if not isinstance(machines, list) or not all(
            isinstance(kind, str) for kind in machines
        ):
            raise PortError(
                "`machines` must be a list of strings", port.INVALID_PARAMS
            )
        try:
            shop: Path = self.model.new_shop(
                Path(text_param(params, "directory")),
                text_param(params, "name"),
                text_param(params, "units"),
                [str(kind) for kind in machines],
            )
        except (ValueError, OSError) as error:
            raise PortError(str(error)) from error
        return str(shop)

    def tree(self, params: dict[str, object]) -> object:
        """Return what a window's tree shows (`tree`).

        Arguments:
        * `params` (`dict[str, object]`): `window` (from 0; 0 if not
          given).

        Returns:
        * (`object`): Per root, its label, then a list per child.
        """
        return self.window(params).tree.labels()

    def select(self, params: dict[str, object]) -> object:
        """Click a tree item, as a person would (`select`).

        Arguments:
        * `params` (`dict[str, object]`): `path` (the item's file or
          directory) and `window` (from 0; 0 if not given).

        Returns:
        * (`object`): What the current panel shows: `label`, `text`.

        Raises:
        * `PortError`: If no item has that path.
        """
        top: Window = self.window(params)
        path: str = text_param(params, "path")
        item: QTreeWidgetItem | None = top.tree.item_at_path(
            Path(path).resolve()
        )
        if item is None:
            raise PortError(f"no item for {path}", port.INVALID_PARAMS)
        top.select_item(item)
        panel: Panel = top.panels[top.current]
        return {
            "label": panel.title.text(),
            "text": panel.text.toPlainText(),
        }

    def quit(self, _params: dict[str, object]) -> object:
        """Close every window, unless one refuses (`quit`).

        The windows close `QUIT_DELAY_MS` after the answer is sent.

        Arguments:
        * `_params` (`dict[str, object]`): None needed.

        Returns:
        * (`object`): "quitting".

        Raises:
        * `PortError`: If a window controls a running machine.
        """
        top: Window
        for top in WINDOWS:
            refusal: str = self.model.close_refusal(top.controls)
            if refusal:
                raise PortError(refusal)
        QTimer.singleShot(QUIT_DELAY_MS, close_all)
        return "quitting"


# Function `close_all()`:
def close_all() -> None:
    """Close every window, newest first."""
    top: Window
    for top in reversed(list(WINDOWS)):
        top.close()


# Class `NewShopDialog`:
class NewShopDialog(QDialog):
    """The questions for a new shop (#98, #104).

    Where it goes (`shop/` under the current directory, unless
    changed), its name, its units, and a check box for each kind of
    machine (`MACHINE_KINDS`; those `scraftcam` can not drive yet say
    so).  [Create], beside the name, stays grey until there is one.

    Attributes:
    * `model` (`App`): What every window shows.
    * `directory` (`QLineEdit`): Where the shop goes.
    * `name` (`QLineEdit`): The shop's name.
    * `units` (`QComboBox`): The units it prefers.
    * `kinds` (`dict[str, QCheckBox]`): A check box per kind, by key.
    * `buttons` (`QDialogButtonBox`): [Cancel].
    * `make_button` (`QPushButton`): [Create], beside the name.
    """

    def __init__(self, parent: QWidget, model: App) -> None:
        """Make the dialog; `open()` shows it.

        Arguments:
        * `parent` (`QWidget`): The window it belongs to.
        * `model` (`App`): What every window shows.
        """
        super().__init__(parent)
        self.model: App = model
        self.setWindowTitle("New Shop")
        form: QFormLayout = QFormLayout(self)

        # Where, with [Browse...] to choose another directory.
        self.directory: QLineEdit = QLineEdit(
            str(Path.cwd() / NEW_SHOP_DIRECTORY)
        )
        self.directory.setMinimumWidth(DIRECTORY_WIDTH)
        browse: QPushButton = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        where: QHBoxLayout = QHBoxLayout()
        where.addWidget(self.directory, 1)
        where.addWidget(browse)
        form.addRow("Directory:", where)

        # The name, with [Create] beside it (#116; Enter presses it),
        # grey until there is a name.
        self.name: QLineEdit = QLineEdit()
        self.name.setPlaceholderText("e.g. Home shop")
        self.name.textChanged.connect(self.check)
        self.make_button: QPushButton = QPushButton("Create")
        self.make_button.setDefault(True)
        self.make_button.clicked.connect(self.make_shop)
        named: QHBoxLayout = QHBoxLayout()
        named.addWidget(self.name, 1)
        named.addWidget(self.make_button)
        form.addRow("Name:", named)

        # The units.
        self.units: QComboBox = QComboBox()
        unit: str
        for unit in UNITS:
            self.units.addItem(UNIT_LABELS[unit], unit)
        form.addRow("Units:", self.units)

        # A check box per kind of machine: computer controlled ones,
        # then manual ones (for prep work).
        form.addRow(QLabel("Which machines does the shop have?"))
        form.addRow(QLabel("Computer controlled:"))
        self.kinds: dict[str, QCheckBox] = {}
        kind: str
        label: str
        ready: bool
        for kind, label, ready in MACHINE_KINDS:
            if kind.startswith(MANUAL_PREFIX) and not any(
                key.startswith(MANUAL_PREFIX) for key in self.kinds
            ):
                form.addRow(QLabel("Manual, for prep work:"))
            box: QCheckBox = QCheckBox(
                label if ready else f"{label} (not supported yet)"
            )
            box.setChecked(kind == "cnc_mill")
            form.addRow(box)
            self.kinds[kind] = box

        # [Cancel].
        self.buttons: QDialogButtonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.check()

    def check(self) -> None:
        """Grey [Create], saying why, until there is a name."""
        named: bool = bool(self.name.text().strip())
        self.make_button.setEnabled(named)
        self.make_button.setToolTip("" if named else "Give the shop a name.")

    def browse(self) -> None:
        """Choose the shop's directory ([Browse...]).

        Qt's own dialog, not the desktop's: KDE's, opened from this
        dialog, did not show (#117).  It starts in the nearest
        directory that exists.
        """
        start: Path = Path(self.directory.text().strip()).expanduser()
        while not start.is_dir() and start != start.parent:
            start = start.parent
        chosen: str = QFileDialog.getExistingDirectory(
            self,
            "The shop's directory",
            str(start),
            QFileDialog.Option.ShowDirsOnly
            | QFileDialog.Option.DontUseNativeDialog,
        )
        if chosen:
            self.directory.setText(chosen)

    def make_shop(self) -> None:
        """Make the shop ([Create]); on a problem, say so and stay."""
        machines: list[str] = [
            kind for kind, box in self.kinds.items() if box.isChecked()
        ]
        try:
            self.model.new_shop(
                Path(self.directory.text().strip()).expanduser(),
                self.name.text(),
                str(self.units.currentData()),
                machines,
            )
        except (ValueError, OSError) as error:
            self.model.say(str(error), problem=True)
            return
        self.accept()
