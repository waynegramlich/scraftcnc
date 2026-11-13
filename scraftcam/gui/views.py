"""The views in a window: the tree, and the panels beside it.

* `TreeView`: the one tree (`T.osiade~5.1.9` #121), the shop's and
  the design's files, as `tree.py` reads them; an item that does not
  read cleanly is red, with the problem as its tooltip (#125).  The
  roots open one level (#128); when the tree is read again, what was
  open stays open.
* `Panel`: shows one item (#122): a TOML file's text, read only and
  unwrapped (S3 brings its fields); a Python file's or package's top
  docstring (#74), or the problem for an item that does not read
  cleanly, both wrapped.
* `TreeWatcher`: reads the trees again whenever a file or directory
  in them changes outside the GUI (#11, #123), so there is no
  [Refresh].  The
  current panel (the one last clicked) is outlined.
"""

from pathlib import Path

from ..packages import require
from .app import App
from .tree import DIRECTORY, ERROR, FILE, PACKAGE, SHOP, Node, docstring

# `PySide6` lives in `~/.scraftcam/packages/`, so it is put on
# `sys.path` (and fetched, the first time) before it is imported.
require("PySide6")
# pylint: disable=wrong-import-position,wrong-import-order
from PySide6.QtCore import (  # noqa: E402
    QEvent,
    QFileSystemWatcher,
    QObject,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBrush, QColor  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QFrame,
    QLabel,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

# pylint: enable=wrong-import-position,wrong-import-order

# The color of an item, or a panel's text, that does not read cleanly.
ERROR_COLOR: str = "#c00000"

# The outline of the current panel, and of the others.
CURRENT_STYLE: str = "Panel { border: 2px solid palette(highlight); }"
OTHER_STYLE: str = "Panel { border: 2px solid transparent; }"

# How long the watcher waits for a burst of changes to end.
SETTLE_MS: int = 300

# Where an item keeps its path (the key into `TreeView.nodes`).
PATH_ROLE: int = Qt.ItemDataRole.UserRole


# Function `item_text()`:
def item_text(node: Node) -> str:
    """Return what a panel shows for an item.

    Arguments:
    * `node` (`Node`): The item.

    Returns:
    * (`str`): Its problem, its text, its docstring, or a count.
    """
    if node.kind == ERROR:
        return f"{node.path}:\n{node.error}"
    if node.kind in (SHOP, FILE):
        try:
            return node.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return f"{node.path}: can not be read: {error}"
    if node.kind == DIRECTORY:
        return f"{node.path}\n{len(node.children)} items."
    if node.kind == PACKAGE and not (node.path / "__init__.py").is_file():
        return f"{node.path}"
    return docstring(node.path)


# Class `Panel`:
class Panel(QFrame):
    """A panel: shows one item, outlined while it is the current one.

    Attributes:
    * `title` (`QLabel`): The item's label.
    * `text` (`QPlainTextEdit`): What the item holds, read only.
    * `node` (`Node | None`): The item shown, if any.
    * `clicked` (`Signal`): Sent when the panel is clicked.
    """

    clicked: Signal = Signal()

    def __init__(self, number: int) -> None:
        """Make an empty panel.

        Arguments:
        * `number` (`int`): Its number (from 1), until it shows an item.
        """
        super().__init__()
        self.node: Node | None = None
        self.title: QLabel = QLabel(f"Panel {number}: click an item.")
        self.title.setStyleSheet("color: grey")
        self.text: QPlainTextEdit = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.text, 1)
        self.text.viewport().installEventFilter(self)
        self.set_current(False)

    def eventFilter(  # pylint: disable=invalid-name
        self, watched: QObject, event: QEvent
    ) -> bool:
        """Notice a click on the text (Qt's name for it).

        Arguments:
        * `watched` (`QObject`): The text's viewport.
        * `event` (`QEvent`): Any event; a mouse press makes this the
          current panel.

        Returns:
        * (`bool`): False, so the text gets the event too.
        """
        if event.type() == QEvent.Type.MouseButtonPress:
            self.clicked.emit()
        return super().eventFilter(watched, event)

    def mousePressEvent(  # pylint: disable=invalid-name
        self, event: object
    ) -> None:
        """Make this the current panel when it is clicked.

        Arguments:
        * `event` (`object`): The mouse press (unused).
        """
        del event
        self.clicked.emit()

    def set_current(self, current: bool) -> None:
        """Outline the panel, or not.

        Arguments:
        * `current` (`bool`): True for the current panel.
        """
        self.setStyleSheet(CURRENT_STYLE if current else OTHER_STYLE)

    def show_node(self, node: Node) -> None:
        """Show an item.

        Arguments:
        * `node` (`Node`): The item.
        """
        self.node = node
        self.title.setText(node.label())
        self.title.setStyleSheet(
            f"color: {ERROR_COLOR}" if node.kind == ERROR else ""
        )
        self.text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
            if node.kind in (SHOP, FILE)
            else QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        self.text.setPlainText(item_text(node))


# Class `TreeView`:
class TreeView(QTreeWidget):
    """The one tree: the shop's and the design's files.

    Attributes:
    * `nodes` (`dict[str, Node]`): Each item's node, by its path.
    * `version` (`int`): The model's `tree_version` last shown.
    """

    def __init__(self) -> None:
        """Make an empty tree."""
        super().__init__()
        self.setHeaderHidden(True)
        self.nodes: dict[str, Node] = {}
        self.version: int = -1

    def fill(self, roots: list[Node], version: int) -> None:
        """Show the trees, keeping open what was open.

        Arguments:
        * `roots` (`list[Node]`): The shop's and the design's roots.
        * `version` (`int`): The model's `tree_version`.
        """
        # What was open, by path; the roots open at first (#128).
        first: bool = self.version < 0
        opened: set[str] = set()
        index: int
        for index in range(self.topLevelItemCount()):
            opened |= open_paths(self.topLevelItem(index))

        # The items, again.
        self.clear()
        self.nodes = {}
        root: Node
        for root in roots:
            item: QTreeWidgetItem = self.add(root, None, opened)
            if first:
                item.setExpanded(True)
        self.version = version

    def add(
        self, node: Node, parent: QTreeWidgetItem | None, opened: set[str]
    ) -> QTreeWidgetItem:
        """Add an item, and those under it.

        Arguments:
        * `node` (`Node`): The item.
        * `parent` (`QTreeWidgetItem | None`): Its parent; None for a
          root.
        * `opened` (`set[str]`): The paths of the items to open.

        Returns:
        * (`QTreeWidgetItem`): The item.
        """
        item: QTreeWidgetItem
        if parent is None:
            item = QTreeWidgetItem(self)
        else:
            item = QTreeWidgetItem(parent)
        key: str = str(node.path)
        item.setText(0, node.label())
        item.setData(0, PATH_ROLE, key)
        if node.kind == ERROR:
            item.setForeground(0, QBrush(QColor(ERROR_COLOR)))
            item.setToolTip(0, node.error)
        self.nodes[key] = node
        child: Node
        for child in node.children:
            self.add(child, item, opened)
        item.setExpanded(key in opened)
        return item

    def labels(self) -> list[object]:
        """Return what the tree shows (the command port's `tree`).

        Returns:
        * (`list[object]`): Per root, its label, then a list per
          child, nested as the tree is.
        """
        return [
            item_labels(self.topLevelItem(index))
            for index in range(self.topLevelItemCount())
        ]

    def node_of(self, item: QTreeWidgetItem) -> Node | None:
        """Return an item's node.

        Arguments:
        * `item` (`QTreeWidgetItem`): The item.

        Returns:
        * (`Node | None`): Its node, if it has one.
        """
        return self.nodes.get(str(item.data(0, PATH_ROLE)))

    def item_at_path(self, path: Path) -> QTreeWidgetItem | None:
        """Find the item for a path.

        Arguments:
        * `path` (`Path`): The item's file or directory.

        Returns:
        * (`QTreeWidgetItem | None`): The item, if there is one.
        """
        found: list[QTreeWidgetItem] = [
            item
            for item in self.findItems(
                "", Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive
            )
            if str(item.data(0, PATH_ROLE)) == str(path)
        ]
        return found[0] if found else None


# Function `open_paths()`:
def open_paths(item: QTreeWidgetItem | None) -> set[str]:
    """Return the paths of the open items at and under an item.

    Arguments:
    * `item` (`QTreeWidgetItem | None`): The item (None: none).

    Returns:
    * (`set[str]`): Their paths.
    """
    opened: set[str] = set()
    if item is None:
        return opened
    if item.isExpanded():
        opened.add(str(item.data(0, PATH_ROLE)))
    index: int
    for index in range(item.childCount()):
        opened |= open_paths(item.child(index))
    return opened


# Function `item_labels()`:
def item_labels(item: QTreeWidgetItem | None) -> list[object]:
    """Return an item's label, then a list per child, nested.

    Arguments:
    * `item` (`QTreeWidgetItem | None`): The item (None: none).

    Returns:
    * (`list[object]`): The labels.
    """
    if item is None:
        return []
    return [
        item.text(0),
        *[
            item_labels(item.child(index))
            for index in range(item.childCount())
        ],
    ]


# Function `node_paths()`:
def node_paths(node: Node | None) -> list[str]:
    """Return the paths of an item and of every item under it.

    Arguments:
    * `node` (`Node | None`): The item (None: none).

    Returns:
    * (`list[str]`): Their paths, the item's first.
    """
    if node is None:
        return []
    paths: list[str] = [str(node.path)]
    child: Node
    for child in node.children:
        paths.extend(node_paths(child))
    return paths


# Class `TreeWatcher`:
class TreeWatcher(QFileSystemWatcher):
    """Reads the trees again when their files change (#123).

    A burst of changes (an editor saving, `git checkout`) is read once,
    `SETTLE_MS` after the last.

    Attributes:
    * `model` (`App`): What every window shows.
    * `timer` (`QTimer`): Waits for a burst of changes to end.
    * `version` (`int`): The model's `tree_version` last watched.
    """

    def __init__(self, model: App) -> None:
        """Watch the model's trees.

        Arguments:
        * `model` (`App`): What every window shows.
        """
        super().__init__()
        self.model: App = model
        self.timer: QTimer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(SETTLE_MS)
        self.timer.timeout.connect(self.reload)
        self.fileChanged.connect(self.changed)
        self.directoryChanged.connect(self.changed)
        self.version: int = -1
        self.watch()
        model.listen(self.follow)

    def watch(self) -> None:
        """Watch every file and directory now in the trees."""
        # Directories show files added and removed; files, edits.
        watched: list[str] = self.files() + self.directories()
        if watched:
            self.removePaths(watched)
        paths: list[str] = node_paths(self.model.shop_root) + node_paths(
            self.model.design_root
        )
        shop: Path | None = self.model.shop
        if shop is not None:
            paths.append(str(shop.parent))
        design: Path | None = self.model.design
        if design is not None and design.is_file():
            paths.append(str(design.parent))
        existing: list[str] = sorted(
            {path for path in paths if Path(path).exists()}
        )
        if existing:
            self.addPaths(existing)
        self.version = self.model.tree_version

    def follow(self) -> None:
        """Watch the trees again once they are read again (a new shop)."""
        if self.version != self.model.tree_version:
            self.watch()

    def changed(self, _path: str) -> None:
        """Note a change; read the trees once the burst is over.

        Arguments:
        * `_path` (`str`): What changed (ignored).
        """
        self.timer.start()

    def reload(self) -> None:
        """Read the trees again (`follow()` then watches them)."""
        self.model.reload_tree()
