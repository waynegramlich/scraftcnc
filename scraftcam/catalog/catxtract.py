#!/usr/bin/env python3
"""Extract catalog information from PDF pages into Markdown files.

`catxtract` shows one PDF page at a time.  The user drags rectangles
over the page to mark regions (title, text, image, table or index).
Each page gets its own directory, so the pages not done yet are easy to
see: saving writes the regions to `OUTDIR/page_NNN/page_NNN.md`, with
the region definitions in `page_NNN.json` beside it, so the page can
be redone later.

Everything is done with the mouse.  The Mode buttons choose the kind
(title, text, image, table, index) of the next rectangle, and of the selected
region if there is one.  The Page buttons move to the next / previous
page, or the next / previous page not extracted yet ("New"); typing a
page number into the box and pressing `Goto` (or Enter) moves to that
page (0 means 1, and a number past the end means the last page).
`Index Update` rewrites every saved page that has an index region, so
that its links reach the pages extracted since.
The Region buttons select the region above / below, cycle up (newer) /
down (older) through the regions, delete the selected region, undo the
newest rectangle (again and again), and clear all of the regions.
A click selects a region, and the right mouse button ignores it.
A page with no saved regions starts with suggested ones.

Moving to another page, or quitting, saves the page first.  Each
`.md` file starts with a `# Page NNN` heading and links to the nearest
saved pages before and after it; saving a page updates those links in
the pages on either side as well.

Usage: `python3 -m scraftcam.catalog.catxtract PDF OUTDIR`
"""

# pylint: disable=too-many-instance-attributes,too-many-locals

from __future__ import annotations

import bisect
import functools
import itertools
import json
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..packages import require
from .pdf import Document, Page, Rect, Word

# `PySide6` lives in `~/.scraftcam/packages/`, so it is put on
# `sys.path` (and fetched, the first time) before it is imported.
require("PySide6")
# pylint: disable=wrong-import-position,wrong-import-order
from PySide6.QtCore import (  # noqa: E402
    QPoint,
    QRect,
    QRectF,
    QRegularExpression,
    Qt,
)
from PySide6.QtGui import (  # noqa: E402
    QCloseEvent,
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRegularExpressionValidator,
    QScreen,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# pylint: enable=wrong-import-position,wrong-import-order

KINDS: dict[str, str] = {
    "1": "title",
    "2": "text",
    "3": "image",
    "4": "table",
    "5": "index",
}
COLORS: dict[str, str] = {
    "title": "red",
    "text": "blue",
    "image": "green",
    "table": "magenta",
    "index": "darkorange",
}

# An index line: `SOME_TEXT.....NNN`, where the page numbers may be a
# range (`NNN~MMM` or `NNN-MMM`), a list (`NNN,MMM`) or a mix.  The dots may be
# periods or ellipsis characters, with spaces among them.
INDEX_LINE: re.Pattern[str] = re.compile(
    r"(?P<item>.*?)[\s.…]*[.…]{2}[\s.…]*"
    r"(?P<pages>\d+(?:\s*[~,-]\s*\d+)*)\s*"
)


# Class `Region`:
@dataclass(slots=True)
class Region:
    """A rectangular region of a page, in PDF points.

    Attributes:
    * `kind` (`str`): One of the values of `KINDS`.
    * `x0` (`float`): The left edge.
    * `y0` (`float`): The top edge.
    * `x1` (`float`): The right edge.
    * `y1` (`float`): The bottom edge.

    Constructor:
    * `Region(kind, x0, y0, x1, y1)`
    """

    # Constructor arguments:
    kind: str = field(init=True)
    x0: float = field(init=True)
    y0: float = field(init=True)
    x1: float = field(init=True)
    y1: float = field(init=True)

    # Method `Region.rect()`:
    def rect(self) -> Rect:
        """Return the region as a `Rect`.

        Returns:
        * (`Rect`): The region's rectangle.
        """
        return Rect(self.x0, self.y0, self.x1, self.y1)


# Function `group_rows()`:
def group_rows(words: list[Word]) -> list[list[Word]]:
    """Group words into rows, top to bottom, each sorted left to right.

    Arguments:
    * `words` (`list[Word]`):
      The words to group.

    Returns:
    * (`list[list[Word]]`): The rows, whose vertical centers are close.
    """
    ordered: list[Word] = sorted(words, key=lambda w: (w[1] + w[3]) / 2)
    rows: list[list[Word]] = [[ordered[0]]]
    word: Word
    for word in ordered[1:]:
        last: Word = rows[-1][-1]
        height: float = last[3] - last[1]
        if (word[1] + word[3]) / 2 - (last[1] + last[3]) / 2 > height / 2:
            rows.append([])
        rows[-1].append(word)
    return [sorted(row, key=lambda w: w[0]) for row in rows]


# Function `find_dividers()`:
def find_dividers(rows: list[list[Word]]) -> list[float]:
    """Find the x positions that divide a table's columns.

    A divider goes in the middle of each run of x positions (in points)
    that few rows have a word over.

    Arguments:
    * `rows` (`list[list[Word]]`):
      The rows to find the columns of.

    Returns:
    * (`list[float]`): The dividers, left to right.
    """
    # Count, for each x position, the rows with a word over it.
    left: int = int(min(w[0] for row in rows for w in row))
    right: int = int(max(w[2] for row in rows for w in row)) + 1
    coverage: list[int] = [0] * (right - left + 1)
    row: list[Word]
    x: int
    for row in rows:
        covered: set[int] = set()
        for word in row:
            covered.update(range(int(word[0]) - left, int(word[2]) - left))
        for x in covered:
            coverage[x] += 1

    # Put a divider in the middle of each thinly covered run.
    thin: int = max(1, len(rows) // 10)
    dividers: list[float] = []
    start: int = -1
    for x, count in enumerate(coverage):
        if count < thin:
            start = x if start < 0 else start
        elif start >= 0:
            if start > 0:
                dividers.append(left + (start + x) / 2)
            start = -1
    return dividers


# Function `is_header()`:
def is_header(row: list[Word]) -> bool:
    """Return whether a row looks like a header row.

    Data rows in a catalog table are mostly numbers (sizes, part
    numbers, prices), so a row is a header row when fewer than half of
    its words have a digit.

    Arguments:
    * `row` (`list[Word]`):
      The row to look at.

    Returns:
    * (`bool`): True if the row looks like a header row.
    """
    digits: int = sum(any(c.isdigit() for c in w[4]) for w in row)
    return 2 * digits < len(row)


# Function `header_rows()`:
def header_rows(
    head: list[list[Word]], dividers: list[float]
) -> list[list[str]]:
    """Put each phrase of the header rows in the column under it.

    A phrase is words separated by no more than a space (e.g. "3 Flute
    Square End"), so it stays in one cell instead of being split
    across columns.

    Arguments:
    * `head` (`list[list[Word]]`):
      The header rows.
    * `dividers` (`list[float]`):
      The column dividers.

    Returns:
    * (`list[list[str]]`): The header cells, row by row.
    """
    table: list[list[str]] = []
    row: list[Word]
    for row in head:
        # Split the row into phrases.
        phrases: list[list[Word]] = [[row[0]]]
        word: Word
        for word in row[1:]:
            last: Word = phrases[-1][-1]
            if word[0] - last[2] > (last[3] - last[1]) / 2:
                phrases.append([])
            phrases[-1].append(word)

        # Put each phrase in the column under its center.
        cells: list[list[str]] = [[] for _ in range(len(dividers) + 1)]
        phrase: list[Word]
        for phrase in phrases:
            middle: float = (phrase[0][0] + phrase[-1][2]) / 2
            cells[bisect.bisect(dividers, middle)].append(
                " ".join(w[4] for w in phrase)
            )
        table.append([" ".join(cell) for cell in cells])
    return table


# Function `table_rows()`:
def table_rows(words: list[Word]) -> list[list[str]]:
    """Arrange the words of a table into rows and columns.

    Rows are words whose vertical centers are close.  The columns come
    from the data rows alone, so a header that spans several columns
    does not split them; the leading rows that look like headers keep
    their phrases whole.  This is generic: it uses only
    word positions, nothing catalog specific.

    Arguments:
    * `words` (`list[Word]`):
      The words inside the table's rectangle.

    Returns:
    * (`list[list[str]]`): The cell text, row by row, with any header
      rows first.
    """
    if not words:
        return []

    # Split the rows into header rows and data rows.
    rows: list[list[Word]] = group_rows(words)
    count: int = 0
    while count < len(rows) and is_header(rows[count]):
        count += 1
    if count == len(rows):
        count = 0
    head: list[list[Word]] = rows[:count]
    body: list[list[Word]] = rows[count:]

    # Put each data word in the cell of its row and column.
    dividers: list[float] = find_dividers(body)
    table: list[list[str]] = header_rows(head, dividers)
    row: list[Word]
    word: Word
    for row in body:
        cells: list[list[str]] = [[] for _ in range(len(dividers) + 1)]
        for word in row:
            column: int = bisect.bisect(dividers, (word[0] + word[2]) / 2)
            cells[column].append(word[4])
        table.append([" ".join(cell) for cell in cells])
    return table


# Function `markdown_table()`:
def markdown_table(table: list[list[str]]) -> str:
    """Format a table as a Markdown pipe table.

    The first row becomes the header row.

    Arguments:
    * `table` (`list[list[str]]`):
      The cell text, row by row.

    Returns:
    * (`str`): The Markdown table.
    """
    if not table:
        return ""
    # Escape the cells and find each column's width.
    rows: list[list[str]] = [
        [cell.replace("|", "\\|") for cell in row] for row in table
    ]
    widths: list[int] = [
        max(3, *(len(row[c]) for row in rows)) for c in range(len(rows[0]))
    ]

    # Pad every cell to its column's width, so the `|`s line up.
    lines: list[str] = []
    index: int
    row: list[str]
    for index, row in enumerate(rows):
        cells: list[str] = [
            cell.ljust(w) for cell, w in zip(row, widths, strict=False)
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join("-" * w for w in widths) + " |")
    return "\n".join(lines)


# Function `lines_inside()`:
def lines_inside(page: Page, region: Region) -> str:
    """Return the lines of text whose centers are inside a region.

    A hand drawn rectangle often clips a neighboring line (e.g. a page
    footer), and the text that touches a rectangle includes it.  The
    lines are the PDF's own (pdfminer's layout), which a column gap
    splits, but which keep a page wide footer whole.

    Arguments:
    * `page` (`Page`):
      The page to look at.
    * `region` (`Region`):
      The region to look inside.

    Returns:
    * (`str`): The lines, in the order of the page, with their indents.
    """
    # Keep the lines whose centers are inside.
    box: Rect = region.rect()
    inside: list[tuple[Rect, str]] = [
        (line, text)
        for line, text in page.lines()
        if box.contains((line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2)
    ]

    # Put them top to bottom, since pdfminer may not (e.g. a large
    # heading letter).
    def top(item: tuple[Rect, str]) -> tuple[float, float]:
        return (item[0].y0, item[0].x0)

    return "\n".join(text for _line, text in sorted(inside, key=top))


# Function `page_link()`:
def page_link(label: str, pages: str, out_dir: Path) -> str:
    """Link a label to the first page of a list, if its file exists.

    Arguments:
    * `label` (`str`):
      The text to link.
    * `pages` (`str`):
      The page numbers (e.g. `7`, `66-76` or `66-76,83`).
    * `out_dir` (`Path`):
      The directory the Markdown goes into.

    Returns:
    * (`str`): The Markdown link, or just `label` if there is no file.
    """
    name: str = f"page_{int(re.split('[-,]', pages)[0]):03d}"
    if (out_dir / name / f"{name}.md").exists():
        return f"[{label}](../{name}/{name}.md)"
    return label


# Function `index_rows()`:
def index_rows(text: str, out_dir: Path) -> list[list[str]]:
    """Convert the lines of an index into table rows, one row per line.

    This is generic for any index whose lines look like `INDEX_LINE`.
    A line with no page numbers (e.g. a heading over indented lines)
    gets a row with no pages.  Otherwise, the item links to the `.md`
    file of the first page listed, if that file exists, and each `~`
    becomes a `-`.  An indented line starts with `* `.  Each page or
    range after a comma gets a row of its own as well, whose item is
    `+ ` and its first page number, linked the same way.

    Arguments:
    * `text` (`str`):
      The text of the index, one entry per line.
    * `out_dir` (`Path`):
      The directory the Markdown goes into.

    Returns:
    * (`list[list[str]]`): The header row, then an item and its pages
      for each line, or nothing if there are no lines.
    """
    table: list[list[str]] = []
    line: str
    for line in text.splitlines():
        # Split the line into its item and its page numbers.
        match: re.Match[str] | None = INDEX_LINE.fullmatch(line.rstrip())
        item: str = match["item"] if match else line.rstrip()
        pages: str = "".join(match["pages"].split()) if match else ""

        pages = pages.replace("~", "-")

        # Make the spaces single, link the item, and mark any indent.
        words: list[str] = item.split()
        if words:
            label: str = " ".join(words)
            if pages:
                label = page_link(label, pages, out_dir)
            indent: str = "* " if item[0].isspace() else ""
            table.append([indent + label, pages])

            # Add a row for each page or range after a comma.
            more: str
            for more in pages.split(",")[1:]:
                first: str = more.split("-")[0]
                table.append(["+ " + page_link(first, more, out_dir), more])
    return [["Item", "Pages"], *table] if table else []


# Function `overlap()`:
def overlap(a: Region, b: Region) -> float:
    """Return how much two regions overlap.

    Arguments:
    * `a` (`Region`):
      The first region.
    * `b` (`Region`):
      The second region.

    Returns:
    * (`float`): The area they share over the area they cover (0 to 1).
    """
    common: float = a.rect().intersection(b.rect()).area()
    total: float = a.rect().area() + b.rect().area() - common
    return common / total if total > 0 else 0.0


# Function `load_regions()`:
def load_regions(path: Path) -> tuple[list[Region], list[Region]]:
    """Read a page's region file.

    Arguments:
    * `path` (`Path`):
      The `.json` file.

    Returns:
    * (`tuple[list[Region], list[Region]]`): The regions kept and the
      regions ignored.
    """
    data: (
        list[dict[str, str | float]] | dict[str, list[dict[str, str | float]]]
    ) = json.loads(path.read_text())

    # The first files were a plain list of the regions kept, with
    # `description` for text.
    saved: dict[str, list[dict[str, str | float]]] = (
        {"regions": data, "ignored": []} if isinstance(data, list) else data
    )
    lists: list[list[Region]] = [
        [
            Region(
                {"description": "text"}.get(str(r["kind"]), str(r["kind"])),
                float(r["x0"]),
                float(r["y0"]),
                float(r["x1"]),
                float(r["y1"]),
            )
            for r in saved.get(name, [])
        ]
        for name in ("regions", "ignored")
    ]
    return lists[0], lists[1]


# Function `best_match()`:
def best_match(old: Region, candidates: list[Region]) -> Region:
    """Return the candidate that overlaps `old` the most.

    Arguments:
    * `old` (`Region`):
      A region from an earlier page.
    * `candidates` (`list[Region]`):
      The regions found on this page; there must be at least one.

    Returns:
    * (`Region`): The candidate with the largest overlap.
    """
    best: Region = candidates[0]
    candidate: Region
    for candidate in candidates[1:]:
        if overlap(candidate, old) > overlap(best, old):
            best = candidate
    return best


# Function `detect()`:
def detect(page: Page) -> list[Region]:
    """Find the images and tables on a page.

    This is generic.  Images are the page's embedded images, with the
    pieces that nearly touch merged, except tiny ones (icons) and ones
    covering most of the page (backgrounds).
    Tables are what `pdfplumber` finds, kept only when at least 3 of their
    rows look like data rather than headers (which drops page footers).

    Arguments:
    * `page` (`Page`):
      The page to look at.

    Returns:
    * (`list[Region]`): The images and tables found.
    """
    # Merge the embedded images that nearly touch, since a picture is
    # often made of pieces (e.g. a photo and the parts of a diagram).
    boxes: list[Rect] = page.image_boxes()
    merged: bool = True
    while merged:
        merged = False
        i: int
        j: int
        for i, j in itertools.combinations(range(len(boxes)), 2):
            if boxes[i].grow(10).intersects(boxes[j]):
                boxes[i] = boxes[i].union(boxes.pop(j))
                merged = True
                break

    # Keep the pictures that are neither icons (under 40 points on each
    # side) nor most of the page (backgrounds).  A picture can be thin
    # (e.g. a drill seen from the side).
    page_area: float = page.rect.area()
    found: list[Region] = [
        Region("image", box.x0, box.y0, box.x1, box.y1)
        for box in boxes
        if max(box.width(), box.height()) > 40
        and min(box.width(), box.height()) > 10
        and box.area() < 0.8 * page_area
    ]

    # Find the tables.
    box: Rect
    for box in page.table_boxes():
        words: list[Word] = page.words(box)
        rows: list[list[Word]] = group_rows(words) if words else []
        if sum(not is_header(row) for row in rows) >= 3:
            found.append(Region("table", box.x0, box.y0, box.x1, box.y1))
    return found


# Function `snap()`:
def snap(region: Region, words: list[Word]) -> Region | None:
    """Fit a region to the words that it touches.

    Arguments:
    * `region` (`Region`):
      A region from another page.
    * `words` (`list[Word]`):
      The words of this page.

    Returns:
    * (`Region | None`): The region around the words it touches, or
      `None` if it touches none.
    """
    box: Rect = region.rect()
    touched: list[Word] = [w for w in words if box.intersects(Rect(*w[:4]))]
    if not touched:
        return None
    return Region(
        region.kind,
        min(w[0] for w in touched) - 2,
        min(w[1] for w in touched) - 2,
        max(w[2] for w in touched) + 2,
        max(w[3] for w in touched) + 2,
    )


# Function `suggest()`:
def suggest(
    page: Page, previous: list[Region], ignored: list[Region]
) -> list[Region]:
    """Suggest regions for a page, helped by an earlier page.

    This is generic.  A region kept on the earlier page is replaced by
    a matching image or table found on this page; otherwise a title
    or text is fitted to the words it touches here.  The images
    and tables found that match nothing are added, unless they match a
    region ignored on the earlier page (such as a repeated logo).

    Arguments:
    * `page` (`Page`):
      The page to suggest regions for.
    * `previous` (`list[Region]`):
      The regions kept on the earlier page.
    * `ignored` (`list[Region]`):
      The regions ignored on the earlier page.

    Returns:
    * (`list[Region]`): The suggested regions.
    """
    found: list[Region] = detect(page)
    words: list[Word] = page.words()
    regions: list[Region] = []

    # Carry over the earlier page's regions.
    old: Region
    for old in previous:
        same: list[Region] = [
            f for f in found if f.kind == old.kind and overlap(f, old) > 0.3
        ]
        if same:
            best: Region = best_match(old, same)
            found.remove(best)
            regions.append(best)
        elif old.kind in ("title", "text", "index"):
            fitted: Region | None = snap(old, words)
            if fitted is not None:
                regions.append(fitted)

    # Add the rest of what was found, except what was ignored before
    # and what overlaps a region already suggested.
    regions += [
        f
        for f in found
        if all(overlap(f, i) < 0.5 for i in ignored)
        and all(overlap(f, r) < 0.3 for r in regions)
    ]
    return regions


# Class `PageView`:
class PageView(QWidget):
    """Shows a page and its regions, and passes the mouse to `App`.

    Attributes:
    * `app` (`App`): The window it is in.
    * `dragging` (`bool`): True while a rectangle is being dragged.
    * `pixmap` (`QPixmap`): The page, drawn at `App.zoom`.
    * `rubber` (`QRect`): The rectangle being dragged (screen
      pixels).
    """

    # Method `PageView.__init__()`:
    def __init__(self, app: App) -> None:
        """Make an empty view.

        Arguments:
        * `app` (`App`):
          The window it is in.
        """
        super().__init__(app)
        self.app: App = app
        self.pixmap: QPixmap = QPixmap()
        self.rubber: QRect = QRect()
        self.dragging: bool = False
        self.setCursor(Qt.CursorShape.CrossCursor)

    # Method `PageView.show_png()`:
    def show_png(self, png: bytes) -> None:
        """Show a page, and fit the view to it.

        Arguments:
        * `png` (`bytes`):
          The page, as a PNG image.
        """
        self.pixmap.loadFromData(png)
        self.setFixedSize(self.pixmap.size())
        self.update()

    # Method `PageView.paintEvent()`:
    def paintEvent(  # pylint: disable=invalid-name
        self, _event: QPaintEvent
    ) -> None:
        """Draw the page, its regions and the rectangle being dragged.

        Qt names this method; the selected region is drawn thick and
        dashed.

        Arguments:
        * `_event` (`QPaintEvent`):
          What to draw (ignored: all of it is drawn).
        """
        # The page.
        painter: QPainter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)

        # The regions.
        z: float = self.app.zoom
        index: int
        region: Region
        for index, region in enumerate(self.app.regions):
            chosen: bool = index == self.app.selected
            pen: QPen = QPen(QColor(COLORS[region.kind]), 5 if chosen else 2)
            if chosen:
                pen.setDashPattern([6.0 / 5, 3.0 / 5])
            painter.setPen(pen)
            painter.drawRect(
                QRectF(
                    region.x0 * z,
                    region.y0 * z,
                    (region.x1 - region.x0) * z,
                    (region.y1 - region.y0) * z,
                )
            )

        # The rectangle being dragged.
        if self.dragging:
            painter.setPen(QPen(QColor(COLORS[self.app.kind]), 1))
            painter.drawRect(self.rubber.normalized())
        painter.end()

    # Method `PageView.mousePressEvent()`:
    def mousePressEvent(  # pylint: disable=invalid-name
        self, event: QMouseEvent
    ) -> None:
        """Start a drag (left button), or ignore a region (right).

        Arguments:
        * `event` (`QMouseEvent`):
          The mouse press.
        """
        x: float = event.position().x()
        y: float = event.position().y()
        if event.button() == Qt.MouseButton.LeftButton:
            self.app.on_press(x, y)
            corner: QPoint = event.position().toPoint()
            self.rubber = QRect(corner, corner)
            self.dragging = True
        elif event.button() == Qt.MouseButton.RightButton:
            self.app.on_delete(x, y)

    # Method `PageView.mouseMoveEvent()`:
    def mouseMoveEvent(  # pylint: disable=invalid-name
        self, event: QMouseEvent
    ) -> None:
        """Stretch the rectangle being dragged.

        Arguments:
        * `event` (`QMouseEvent`):
          The mouse motion.
        """
        if self.dragging:
            self.rubber.setBottomRight(event.position().toPoint())
            self.update()

    # Method `PageView.mouseReleaseEvent()`:
    def mouseReleaseEvent(  # pylint: disable=invalid-name
        self, event: QMouseEvent
    ) -> None:
        """Finish the rectangle being dragged.

        Arguments:
        * `event` (`QMouseEvent`):
          The mouse release.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            self.update()
            self.app.on_release(event.position().x(), event.position().y())


# Class `App`:
class App(QWidget):
    """The `catxtract` window.

    Attributes:
    * `canvas` (`PageView`): Shows the page and its regions.
    * `closed` (`bool`): True once the window is closed (the page
      saved and the PDF closed).
    * `doc` (`Document`): The PDF being extracted.
    * `drag` (`tuple[float, float]`): Where the current drag started
      (screen pixels).
    * `ignored` (`list[Region]`): The regions ignored on this page.
    * `kind` (`str`): The kind of the next region.
    * `kind_buttons` (`dict[str, QPushButton]`): The mode buttons, by
      kind; the one for `kind` stays pressed.
    * `goto` (`QLineEdit`): Holds the page number to go to.
    * `out_dir` (`Path`): The directory the Markdown goes into.
    * `page_buttons` (`dict[str, QPushButton]`): The page moving
      buttons, by key, so they can be greyed out.
    * `page_no` (`int`): The current page, counting from 0.
    * `progress` (`str`): How many pages have been edited, as of the
      last page change.
    * `regions` (`list[Region]`): The current page's regions.
    * `message` (`str`): Says what last happened, on the status line.
    * `modes` (`QButtonGroup`): The mode buttons, one pressed at a
      time.
    * `selected` (`int`): The index of the selected region, or -1.
    * `status` (`QLabel`): Shows the page number and kind.
    * `zoom` (`float`): Screen pixels per PDF point.
    """

    # Method `App.__init__()`:
    # pylint: disable-next=too-many-statements
    def __init__(
        self, pdf: Path, out_dir: Path, parent: QWidget | None = None
    ) -> None:
        """Open the PDF and create the window.

        Arguments:
        * `pdf` (`Path`):
          The PDF to extract from.
        * `out_dir` (`Path`):
          The directory the Markdown goes into.
        * `parent` (`QWidget | None`):
          What it is shown in, or `None` for a window of its own.
        """
        super().__init__(parent)
        self.doc: Document = Document(pdf)
        self.out_dir: Path = out_dir
        # Start at the first page not extracted yet (with no directory).
        self.page_no: int = next(
            (
                n - 1
                for n in range(1, len(self.doc) + 1)
                if not self.page_dir(n).exists()
            ),
            0,
        )
        self.kind: str = "table"
        self.regions: list[Region] = []
        self.ignored: list[Region] = []
        self.selected: int = -1
        self.message: str = ""
        self.progress: str = ""
        self.drag: tuple[float, float] = (0.0, 0.0)
        self.closed: bool = False
        self.setWindowTitle("catxtract")
        layout: QVBoxLayout = QVBoxLayout(self)

        # Fit the page to the screen height.
        page_height: float = self.doc[0].rect.height()
        screen: QScreen | None = QApplication.primaryScreen()
        screen_height: int = (
            screen.availableGeometry().height() if screen is not None else 900
        )
        self.zoom: float = (screen_height - 190) / page_height

        # Put the page buttons in the first row.
        pages: QHBoxLayout = self.button_row(layout, "Page:")
        key: str
        label: str
        self.page_buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("P", "Prev. New"),
            ("p", "Prev."),
            ("n", "Next"),
            ("N", "Next New"),
        ):
            self.page_buttons[key] = self.button(pages, label, key)

        # Then the `Goto` button with its page number box (at most 5
        # digits), `Index Update` and `Quit`.
        goto_button: QPushButton = QPushButton("Goto")
        goto_button.clicked.connect(self.go_to)
        pages.addWidget(goto_button)
        self.goto: QLineEdit = QLineEdit()
        self.goto.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,5}"), self)
        )
        self.goto.setFixedWidth(
            self.goto.fontMetrics().horizontalAdvance("0" * 7)
        )
        self.goto.returnPressed.connect(self.go_to)
        pages.addWidget(self.goto)
        index_button: QPushButton = QPushButton("Index Update")
        index_button.clicked.connect(self.update_indexes)
        pages.addWidget(index_button)
        self.button(pages, "Quit", "q")
        pages.addStretch(1)

        # Put the region buttons in the second row.
        regions: QHBoxLayout = self.button_row(layout, "Region:")
        for key, label in (
            ("[", "Region Up"),
            ("]", "Region Down"),
            ("Y", "Cycle Up"),
            ("y", "Cycle Down"),
            ("d", "Delete"),
            ("u", "Undo"),
            ("c", "Clear"),
        ):
            self.button(regions, label, key)
        regions.addStretch(1)

        # Put the mode buttons (which stay pressed to show the kind of
        # the next region) in the third row.
        modes: QHBoxLayout = self.button_row(layout, "Mode:")
        self.modes: QButtonGroup = QButtonGroup(self)
        self.modes.setExclusive(True)
        self.kind_buttons: dict[str, QPushButton] = {}
        kind: str
        for key, kind in KINDS.items():
            mode: QPushButton = self.button(modes, kind.title(), key)
            mode.setCheckable(True)
            mode.setChecked(kind == self.kind)
            mode.setStyleSheet(f"QPushButton {{ color: {COLORS[kind]}; }}")
            self.modes.addButton(mode)
            self.kind_buttons[kind] = mode
        modes.addStretch(1)

        # The status line, then the page.
        self.status: QLabel = QLabel()
        layout.addWidget(self.status)
        self.canvas: PageView = PageView(self)
        layout.addWidget(self.canvas)
        layout.addStretch(1)
        self.show_page()

    # Method `App.button_row()`:
    @staticmethod
    def button_row(layout: QVBoxLayout, title: str) -> QHBoxLayout:
        """Add a row of buttons, with its title on the left.

        Arguments:
        * `layout` (`QVBoxLayout`):
          The window's layout, to add the row under what is there.
        * `title` (`str`):
          The row's title (e.g. `Page:`).

        Returns:
        * (`QHBoxLayout`): The row, to add the buttons to.
        """
        row: QHBoxLayout = QHBoxLayout()
        row.addWidget(QLabel(title))
        layout.addLayout(row)
        return row

    # Method `App.button()`:
    def button(self, row: QHBoxLayout, label: str, key: str) -> QPushButton:
        """Add a button that does a command.

        Arguments:
        * `row` (`QHBoxLayout`):
          Where the button goes, after what is there.
        * `label` (`str`):
          The text on it.
        * `key` (`str`):
          The command it does (`command()`).

        Returns:
        * (`QPushButton`): The button.
        """
        button: QPushButton = QPushButton(label)
        button.clicked.connect(functools.partial(self.command, key))
        row.addWidget(button)
        return button

    # Method `App.go_to()`:
    def go_to(self) -> None:
        """Go to the page whose number is in the `goto` box.

        0 goes to the first page, and a number past the end goes to the
        last page.
        """
        text: str = self.goto.text()
        if text:
            self.change_page(min(max(int(text), 1), len(self.doc)) - 1)
        else:
            self.message = "Type a page number first."
            self.draw_regions()
        self.canvas.setFocus()

    # Method `App.change_page()`:
    def change_page(self, page_no: int) -> None:
        """Save the current page, then show another.

        Arguments:
        * `page_no` (`int`):
          The page to show, counting from 0.
        """
        self.save_if_marked()
        self.page_no = page_no
        self.show_page()

    # Method `App.json_path()`:
    def json_path(self) -> Path:
        """Return the path of the current page's region file.

        Returns:
        * (`Path`): The `.json` file.
        """
        return (
            self.page_dir(self.page_no + 1)
            / f"page_{self.page_no + 1:03d}.json"
        )

    # Method `App.page_dir()`:
    def page_dir(self, number: int) -> Path:
        """Return the directory of a page's files.

        Each page has its own directory, so the pages not done yet are
        easy to see.

        Arguments:
        * `number` (`int`):
          The page number, counting from 1.

        Returns:
        * (`Path`): The page's directory (e.g. `OUTDIR/page_100`).
        """
        return self.out_dir / f"page_{number:03d}"

    # Method `App.show_page()`:
    def show_page(self) -> None:
        """Show the current page and load its saved regions."""
        # Render the page.
        page: Page = self.doc[self.page_no]
        self.canvas.show_png(page.png(self.zoom))

        # Load the regions saved before, or else suggest some, helped
        # by the nearest earlier page that was saved.
        self.selected = -1
        if self.json_path().exists():
            self.regions, self.ignored = load_regions(self.json_path())
            how: str = "Loaded"
        else:
            previous: list[Region] = []
            ignored: list[Region] = []
            number: int
            for number in range(self.page_no, 0, -1):
                path: Path = self.page_dir(number) / f"page_{number:03d}.json"
                if path.exists():
                    previous, ignored = load_regions(path)
                    break
            self.regions = suggest(page, previous, ignored)
            self.ignored = []
            how = "Suggested"
        self.message = f"{how} {len(self.regions)} regions."

        # Count the pages edited so far (those with a directory).
        edited: int = sum(
            self.page_dir(n).exists() for n in range(1, len(self.doc) + 1)
        )
        self.progress = (
            f"Edited {edited}/{len(self.doc)}="
            f"{100 * edited / len(self.doc):.0f}%"
        )
        self.draw_regions()

    # Method `App.draw_regions()`:
    def draw_regions(self) -> None:
        """Draw the regions and update the status line."""
        self.canvas.update()

        # Grey out the page buttons that have nowhere to go.
        targets: dict[str, int] = {
            "N": self.empty_page(1),
            "n": self.page_no + 1 if self.page_no < len(self.doc) - 1 else -1,
            "p": self.page_no - 1,
            "P": self.empty_page(-1),
        }
        key: str
        button: QPushButton
        for key, button in self.page_buttons.items():
            button.setEnabled(targets[key] >= 0)
        self.status.setText(
            f"Page {self.page_no + 1} of {len(self.doc)}  "
            f"{self.progress}  "
            f"Next region: {self.kind}  {self.message}"
        )

    # Method `App.empty_page()`:
    def empty_page(self, step: int) -> int:
        """Find the nearest page not extracted yet in one direction.

        Arguments:
        * `step` (`int`):
          1 to look forward, or -1 to look back.

        Returns:
        * (`int`): The page, counting from 0, or -1 if there is none.
        """
        end: int = len(self.doc) if step > 0 else -1
        return next(
            (
                n
                for n in range(self.page_no + step, end, step)
                if not self.page_dir(n + 1).exists()
            ),
            -1,
        )

    # Method `App.on_press()`:
    def on_press(self, x: float, y: float) -> None:
        """Start dragging a new region.

        Arguments:
        * `x` (`float`):
          Where the mouse was pressed, across (screen pixels).
        * `y` (`float`):
          Where the mouse was pressed, down (screen pixels).
        """
        self.drag = (x, y)

    # Method `App.on_release()`:
    def on_release(self, x: float, y: float) -> None:
        """Finish the region being dragged, or select by a click.

        Arguments:
        * `x` (`float`):
          Where the mouse was released, across (screen pixels).
        * `y` (`float`):
          Where the mouse was released, down (screen pixels).
        """
        x0: float = min(self.drag[0], x) / self.zoom
        x1: float = max(self.drag[0], x) / self.zoom
        y0: float = min(self.drag[1], y) / self.zoom
        y1: float = max(self.drag[1], y) / self.zoom
        if x1 - x0 > 3 and y1 - y0 > 3:
            # Select the new region, so a mode button can fix its kind.
            self.regions.append(Region(self.kind, x0, y0, x1, y1))
            self.selected = len(self.regions) - 1
        else:
            self.select_at(x, y)
        self.draw_regions()

    # Method `App.select_at()`:
    def select_at(self, x: float, y: float) -> None:
        """Select the smallest region under the mouse, if any.

        Arguments:
        * `x` (`float`):
          Where the mouse is, across (screen pixels).
        * `y` (`float`):
          Where the mouse is, down (screen pixels).
        """
        under: list[int] = [
            i
            for i, r in enumerate(self.regions)
            if r.rect().contains(x / self.zoom, y / self.zoom)
        ]

        # The smallest one wins.
        def area(index: int) -> float:
            return self.regions[index].rect().area()

        self.selected = min(under, key=area, default=-1)

    # Method `App.on_delete()`:
    def on_delete(self, x: float, y: float) -> None:
        """Ignore the smallest region under the mouse.

        Arguments:
        * `x` (`float`):
          Where the mouse was pressed, across (screen pixels).
        * `y` (`float`):
          Where the mouse was pressed, down (screen pixels).
        """
        self.select_at(x, y)
        self.command("x")

    # Method `App.closeEvent()`:
    def closeEvent(  # pylint: disable=invalid-name
        self, event: QCloseEvent
    ) -> None:
        """Save the page and close the PDF as the window closes.

        Qt names this method; Quit and the window's close button both
        come here, and only the first close saves and closes the PDF.

        Arguments:
        * `event` (`QCloseEvent`):
          The close, accepted.
        """
        if not self.closed:
            self.closed = True
            self.save_if_marked()
            self.doc.close()
        event.accept()

    # Method `App.command()`:
    def command(self, key: str) -> None:
        """Do the command of a button.

        Arguments:
        * `key` (`str`):
          The command's key, which names it (e.g. `n` for the next
          page).
        """
        # The mode buttons share one method; the rest have one each.
        actions: dict[str, Callable[[], None]] = {
            "n": self._next_page,
            "p": self._previous_page,
            "N": self._next_new_page,
            "P": self._previous_new_page,
            "u": self._undo_region,
            "c": self._clear_regions,
            "]": self._region_down,
            "[": self._region_up,
            "y": self._cycle_older,
            "Y": self._cycle_newer,
            "d": self._delete_region,
            "x": self._ignore_region,
        }
        if key == "q":
            self.close()
            return
        if key in KINDS:
            self._set_kind(KINDS[key])
        elif key in actions:
            actions[key]()
        self.draw_regions()

    # Method `App._set_kind()`:
    def _set_kind(self, kind: str) -> None:
        """Set the kind of the next region, and of the selected one.

        Arguments:
        * `kind` (`str`):
          The kind (e.g. `table`).
        """
        self.kind = kind
        self.kind_buttons[kind].setChecked(True)
        if 0 <= self.selected < len(self.regions):
            self.regions[self.selected].kind = kind

    # Method `App._next_page()`:
    def _next_page(self) -> None:
        """Move to the next page, if there is one."""
        if self.page_no < len(self.doc) - 1:
            self.change_page(self.page_no + 1)

    # Method `App._previous_page()`:
    def _previous_page(self) -> None:
        """Move to the previous page, if there is one."""
        if self.page_no > 0:
            self.change_page(self.page_no - 1)

    # Method `App._next_new_page()`:
    def _next_new_page(self) -> None:
        """Move to the next page not extracted yet, if there is one."""
        page_no: int = self.empty_page(1)
        if page_no >= 0:
            self.change_page(page_no)

    # Method `App._previous_new_page()`:
    def _previous_new_page(self) -> None:
        """Move to the previous page not extracted yet, if any."""
        page_no: int = self.empty_page(-1)
        if page_no >= 0:
            self.change_page(page_no)

    # Method `App._undo_region()`:
    def _undo_region(self) -> None:
        """Remove the newest region, and select the one before it."""
        if self.regions:
            self.regions.pop()
            self.selected = len(self.regions) - 1

    # Method `App._clear_regions()`:
    def _clear_regions(self) -> None:
        """Remove every region, and forget the ignored ones."""
        self.regions = []
        self.ignored = []
        self.selected = -1
        self.message = "Cleared."

    # Method `App._region_down()`:
    def _region_down(self) -> None:
        """Select the next region down the page (wrapping)."""
        self._step_region(1)

    # Method `App._region_up()`:
    def _region_up(self) -> None:
        """Select the next region up the page (wrapping)."""
        self._step_region(-1)

    # Method `App._step_region()`:
    def _step_region(self, step: int) -> None:
        """Step through the regions top to bottom (or back up).

        Arguments:
        * `step` (`int`):
          1 to step down the page, -1 to step up.
        """
        if not self.regions:
            return

        # Order the regions top to bottom, then left to right.
        def position(index: int) -> tuple[float, float]:
            return (self.regions[index].y0, self.regions[index].x0)

        order: list[int] = sorted(range(len(self.regions)), key=position)
        here: int = (
            order.index(self.selected)
            if self.selected in order
            else (-1 if step > 0 else 0)
        )
        self.selected = order[(here + step) % len(order)]

    # Method `App._cycle_older()`:
    def _cycle_older(self) -> None:
        """Step down to older regions, wrapping to the newest."""
        if self.regions:
            self.selected = (
                len(self.regions) - 1
                if self.selected < 0
                else (self.selected - 1) % len(self.regions)
            )

    # Method `App._cycle_newer()`:
    def _cycle_newer(self) -> None:
        """Step up to newer regions, wrapping to the oldest."""
        if self.regions:
            self.selected = (self.selected + 1) % len(self.regions)

    # Method `App._delete_region()`:
    def _delete_region(self) -> None:
        """Delete the selected region, and select the one before it.

        Selecting the one before it lets cycling carry on from there.
        """
        if 0 <= self.selected < len(self.regions):
            self.regions.pop(self.selected)
            self.selected = (
                (self.selected - 1) % len(self.regions) if self.regions else -1
            )

    # Method `App._ignore_region()`:
    def _ignore_region(self) -> None:
        """Ignore the selected region, so it is not suggested again."""
        if 0 <= self.selected < len(self.regions):
            self.ignored.append(self.regions.pop(self.selected))
            self.selected = -1

    # Method `App.update_indexes()`:
    def update_indexes(self) -> None:
        """Rewrite every saved page that has an index region.

        The current page stays on the screen.  It is saved first if it
        was saved before or has an index region; otherwise it stays
        unsaved, since saving would mark it as extracted.
        """
        # Save the current page, and remember what is on the screen.
        if self.json_path().exists() or any(
            r.kind == "index" for r in self.regions
        ):
            self.save()
        here: tuple[int, list[Region], list[Region]] = (
            self.page_no,
            self.regions,
            self.ignored,
        )

        # Rewrite the saved pages with an index region.
        count: int = 0
        path: Path
        for path in sorted(self.out_dir.glob("page_*/page_*.json")):
            regions: list[Region]
            ignored: list[Region]
            regions, ignored = load_regions(path)
            if any(r.kind == "index" for r in regions):
                self.page_no = int(path.stem[5:]) - 1
                self.regions = regions
                self.ignored = ignored
                self.save()
                count += 1

        # Put the current page back.
        self.page_no, self.regions, self.ignored = here
        self.message = f"Updated {count} index pages."
        self.draw_regions()

    # Method `App.save_if_marked()`:
    def save_if_marked(self) -> None:
        """Save the current page if it has (or had) any regions."""
        if self.regions or self.ignored or self.json_path().exists():
            self.save()

    # Method `App.save()`:
    def save(self) -> None:
        """Write the current page's Markdown, images and regions."""
        # Save the regions, so that the page can be redone.
        self.json_path().parent.mkdir(parents=True, exist_ok=True)
        stem: str = f"page_{self.page_no + 1:03d}"
        self.json_path().write_text(
            json.dumps(
                {
                    "regions": [asdict(r) for r in self.regions],
                    "ignored": [asdict(r) for r in self.ignored],
                },
                indent=2,
            )
            + "\n"
        )

        # Write each region, top to bottom, except that the index regions
        # (usually columns, whose tops differ a little) go left to right.
        def across(region: Region) -> tuple[float, float]:
            return (region.x0, region.y0)

        def down(region: Region) -> tuple[float, float]:
            return (region.y0, region.x0)

        page: Page = self.doc[self.page_no]
        columns: Iterator[Region] = iter(
            sorted((r for r in self.regions if r.kind == "index"), key=across)
        )
        parts: list[str] = [f"# Page {self.page_no + 1}"]
        image_count: int = 0
        region: Region
        for region in sorted(self.regions, key=down):
            if region.kind == "index":
                region = next(columns)
                parts.append(
                    markdown_table(
                        index_rows(lines_inside(page, region), self.out_dir)
                    )
                )
                continue
            text: str = " ".join(page.text(region.rect()).split())
            if region.kind == "title":
                parts.append(f"## {text}")
            elif region.kind == "text":
                parts.append(text)
            elif region.kind == "image":
                image_count += 1
                name: str = f"{stem}_{image_count}.png"
                (self.json_path().parent / name).write_bytes(
                    page.png(150 / 72, region.rect())
                )
                parts.append(f"![image]({name})")
            else:
                words: list[Word] = page.words(region.rect())
                parts.append(markdown_table(table_rows(words)))
        md_path: Path = self.json_path().parent / f"{stem}.md"
        md_path.write_text("\n\n".join(parts) + "\n")
        self.status.setText(f"Saved {md_path}")

        # Link this page to its saved neighbors, and them to it.
        saved: list[int] = sorted(
            int(path.stem[5:])
            for path in self.out_dir.glob("page_*/page_*.md")
        )
        here: int = saved.index(self.page_no + 1)
        index: int
        for index in range(max(here - 1, 0), min(here + 2, len(saved))):
            write_links(
                self.out_dir,
                saved[index],
                saved[index - 1] if index > 0 else 0,
                saved[index + 1] if index + 1 < len(saved) else 0,
            )


# Function `write_links()`:
def write_links(out_dir: Path, number: int, before: int, after: int) -> None:
    """Put the links to the neighboring pages under a page's heading.

    The links line is the second paragraph of the page's `.md` file;
    a file written before there were links gets one added.

    Arguments:
    * `out_dir` (`Path`):
      The directory the Markdown goes into.
    * `number` (`int`):
      The page to update, counting from 1.
    * `before` (`int`):
      The nearest earlier saved page, or 0 if there is none.
    * `after` (`int`):
      The nearest later saved page, or 0 if there is none.
    """
    # Make the links line.
    links: list[str] = []
    label: str
    other: int
    for label, other in (("Previous", before), ("Next", after)):
        if other:
            name: str = f"page_{other:03d}"
            links.append(f"{label}: [Page {other}](../{name}/{name}.md)")
        else:
            links.append(f"{label}: none")
    line: str = " | ".join(links)

    # Replace the old links line (if any) after the heading.
    path: Path = out_dir / f"page_{number:03d}" / f"page_{number:03d}.md"
    parts: list[str] = path.read_text().rstrip("\n").split("\n\n")
    if len(parts) > 1 and parts[1].startswith("Previous: "):
        parts[1] = line
    else:
        parts.insert(1, line)
    path.write_text("\n\n".join(parts) + "\n")


# Function `main()`:
def main() -> None:
    """Run `catxtract` with the command line arguments."""
    # Check the arguments.
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    # Run the window until it is closed.
    application: QApplication = QApplication(sys.argv[:1])
    app: App = App(Path(sys.argv[1]), Path(sys.argv[2]))
    app.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
