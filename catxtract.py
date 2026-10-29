#!/usr/bin/env python3
# These lines are inline script metadata (PEP 723) that the EZPkg
# bootstrap needs.  Never remove them.
# /// script
# requires-python = ">=3.12"
# dependencies = ["ezpkg>=0.0.4,<0.1", "pymupdf"]
# ///
"""Extract catalog information from PDF pages into Markdown files.

`catxtract` shows one PDF page at a time.  The user drags rectangles
over the page to mark regions (title, text, image or table).  Each
page gets its own directory, so the pages not done yet are easy to
see: saving writes the regions to `OUTDIR/page_NNN/page_NNN.md`, with
the region definitions in `page_NNN.json` beside it, so the page can
be redone later.

the next rectangle); `n` / `p` next / previous page;
`u` undo the newest rectangle (again and again); `[` / `]` select
the region above / below; `x` ignore the selected region; `q` quit.
A click selects a region, and the right mouse button ignores it.
A page with no saved regions starts with suggested ones.

Moving to another page, or quitting, saves the page first.

Usage: `catxtract.py PDF OUTDIR [SSS-EEE]`, where `SSS` and `EEE` are
the first and last pages to work on (e.g. `100-102`, or `100` alone).
"""

# pylint: disable=too-many-instance-attributes,too-many-locals

from __future__ import annotations

# The bootstrap below is pasted as is, so `ruff format` and `pylint`
# skip it.
# fmt: off
# pylint: disable=all
# Begin the EZPkg bootstrap.  Never edit it.
import hashlib
import importlib
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request as req

try:  # Do not edit try block!  See https://pypi.org/project/ezpkg/
    s = "find ezpkg"; t = pathlib.Path.home()/".ezpkg"; w = t/"ezpkg.whl"
    def g(u: str) -> bytes:  # Fetch u; curl if no certificates.
        try: return bytes(req.urlopen(u, None, 60).read())
        except urllib.error.URLError as y: z = y  # python.org Macs.
        try: return subprocess.run(["curl", "-fsSL", u],
                                   capture_output=True, check=True).stdout
        except Exception: raise z from None
    try: m = None; m = importlib.import_module("ezpkg")  # Present?
    except ImportError: pass
    if m is None and not w.is_file():  # Not downloaded yet.
        s = "download ezpkg"; d = g("https://pypi.org/pypi/ezpkg/json")
        e = next(e for e in json.loads(d)["urls"] if e["url"][-4:] == ".whl")
        r = g(e["url"])
        if hashlib.sha256(r).hexdigest() != e["digests"]["sha256"]:
            raise ValueError(f"{e['filename']} fails its SHA-256 check")
        t.mkdir(parents=True, exist_ok=True); p = t/"ezpkg.part"
        p.write_bytes(r); p.replace(w)  # The rename is atomic.
    if m is None:  # Python imports it straight from the wheel.
        s = "import ezpkg"; sys.path.insert(0, str(w))
        m = importlib.import_module("ezpkg")
    s = "fetch packages"; m.EZPkg().install(bootstrap="2026-10-26")
except Exception as x:  # Do not edit try block!
    raise SystemExit(f"ezpkg: {s} failed: {x!r}")
# End the EZPkg bootstrap.
# pylint: enable=all
# fmt: on

import bisect
import functools
import itertools
import tkinter as tk
from dataclasses import asdict, dataclass, field
from pathlib import Path

# PyMuPDF lives in EZPkg's cache, where `mypy` and `pylint` do not
# look.
# pylint: disable-next=import-error
import pymupdf  # type: ignore[import-not-found]

KINDS: dict[str, str] = {
    "1": "title",
    "2": "text",
    "3": "image",
    "4": "table",
}
COLORS: dict[str, str] = {
    "title": "red",
    "text": "blue",
    "image": "green",
    "table": "magenta",
}

# A word from `pymupdf`: (x0, y0, x1, y1, text).
type Word = tuple[float, float, float, float, str]


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
    def rect(self) -> pymupdf.Rect:
        """Return the region as a `pymupdf.Rect`.

        Returns:
        * (`pymupdf.Rect`): The region's rectangle.
        """
        return pymupdf.Rect(self.x0, self.y0, self.x1, self.y1)


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
        cells: list[str] = [cell.ljust(w) for cell, w in zip(row, widths)]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join("-" * w for w in widths) + " |")
    return "\n".join(lines)


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
    common: float = (a.rect() & b.rect()).get_area()
    total: float = a.rect().get_area() + b.rect().get_area() - common
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


# Function `detect()`:
def detect(page: pymupdf.Page) -> list[Region]:
    """Find the images and tables on a page.

    This is generic.  Images are the page's embedded images, with the
    pieces that nearly touch merged, except tiny ones (icons) and ones
    covering most of the page (backgrounds).
    Tables are what `pymupdf` finds, kept only when at least 3 of their
    rows look like data rather than headers (which drops page footers).

    Arguments:
    * `page` (`pymupdf.Page`):
      The page to look at.

    Returns:
    * (`list[Region]`): The images and tables found.
    """
    # Merge the embedded images that nearly touch, since a picture is
    # often made of pieces (e.g. a photo and the parts of a diagram).
    boxes: list[pymupdf.Rect] = [
        pymupdf.Rect(info["bbox"]) & page.rect
        for info in page.get_image_info()
    ]
    merged: bool = True
    while merged:
        merged = False
        i: int
        j: int
        for i, j in itertools.combinations(range(len(boxes)), 2):
            if (boxes[i] + (-10, -10, 10, 10)).intersects(boxes[j]):
                boxes[i] |= boxes.pop(j)
                merged = True
                break

    # Keep the pictures that are neither icons (under 40 points on each
    # side) nor most of the page (backgrounds).  A picture can be thin
    # (e.g. a drill seen from the side).
    page_area: float = page.rect.get_area()
    found: list[Region] = [
        Region("image", *box)
        for box in boxes
        if max(box.width, box.height) > 40
        and min(box.width, box.height) > 10
        and box.get_area() < 0.8 * page_area
    ]

    # Find the tables.
    for table in page.find_tables().tables:
        box = pymupdf.Rect(table.bbox)
        words: list[Word] = [w[:5] for w in page.get_text("words", clip=box)]
        rows: list[list[Word]] = group_rows(words) if words else []
        if sum(not is_header(row) for row in rows) >= 3:
            found.append(Region("table", *box))
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
    box: pymupdf.Rect = region.rect()
    touched: list[Word] = [w for w in words if box.intersects(w[:4])]
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
    page: pymupdf.Page, previous: list[Region], ignored: list[Region]
) -> list[Region]:
    """Suggest regions for a page, helped by an earlier page.

    This is generic.  A region kept on the earlier page is replaced by
    a matching image or table found on this page; otherwise a title
    or text is fitted to the words it touches here.  The images
    and tables found that match nothing are added, unless they match a
    region ignored on the earlier page (such as a repeated logo).

    Arguments:
    * `page` (`pymupdf.Page`):
      The page to suggest regions for.
    * `previous` (`list[Region]`):
      The regions kept on the earlier page.
    * `ignored` (`list[Region]`):
      The regions ignored on the earlier page.

    Returns:
    * (`list[Region]`): The suggested regions.
    """
    found: list[Region] = detect(page)
    words: list[Word] = [w[:5] for w in page.get_text("words")]
    regions: list[Region] = []

    # Carry over the earlier page's regions.
    old: Region
    for old in previous:
        same: list[Region] = [
            f for f in found if f.kind == old.kind and overlap(f, old) > 0.3
        ]
        if same:
            best: Region = max(same, key=lambda f: overlap(f, old))
            found.remove(best)
            regions.append(best)
        elif old.kind in ("title", "text"):
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


# Class `App`:
class App:
    """The `catxtract` window.

    Attributes:
    * `canvas` (`tk.Canvas`): Shows the page and its regions.
    * `doc` (`pymupdf.Document`): The PDF being extracted.
    * `drag` (`tuple[float, float]`): Where the current drag started.
    * `ignored` (`list[Region]`): The regions ignored on this page.
    * `kind_var` (`tk.StringVar`): Shows `kind` on the kind buttons.
    * `kind` (`str`): The kind of the next region.
    * `out_dir` (`Path`): The directory the Markdown goes into.
    * `first` (`int`): The first page to work on, counting from 0.
    * `last` (`int`): The last page to work on, counting from 0.
    * `page_no` (`int`): The current page, counting from 0.
    * `photo` (`tk.PhotoImage`): The current page's image.
    * `regions` (`list[Region]`): The current page's regions.
    * `root` (`tk.Tk`): The main window.
    * `rubber` (`int`): The canvas id of the rectangle being dragged.
    * `message` (`str`): Says what last happened, on the status line.
    * `selected` (`int`): The index of the selected region, or -1.
    * `status` (`tk.Label`): Shows the page number and kind.
    * `zoom` (`float`): Screen pixels per PDF point.
    """

    # Method `App.__init__()`:
    def __init__(
        self, pdf: Path, out_dir: Path, first: int, last: int
    ) -> None:
        """Open the PDF and create the window.

        Arguments:
        * `pdf` (`Path`):
          The PDF to extract from.
        * `out_dir` (`Path`):
          The directory the Markdown goes into.
        * `first` (`int`):
          The first page to work on, counting from 0.
        * `last` (`int`):
          The last page to work on, counting from 0 (or -1 for the
          document's last page).
        """
        self.doc: pymupdf.Document = pymupdf.open(pdf)
        self.out_dir: Path = out_dir
        last = len(self.doc) - 1 if last < 0 else last
        if not 0 <= first <= last < len(self.doc):
            raise SystemExit(
                f"Pages {first + 1}-{last + 1} are not all in {pdf} "
                f"(1-{len(self.doc)})"
            )
        self.first: int = first
        self.last: int = last
        self.page_no: int = first
        self.kind: str = "table"
        self.regions: list[Region] = []
        self.ignored: list[Region] = []
        self.selected: int = -1
        self.message: str = ""
        self.drag: tuple[float, float] = (0.0, 0.0)
        self.rubber: int = 0

        # Fit the page to the screen height.
        self.root: tk.Tk = tk.Tk()
        page_height: float = self.doc[0].rect.height
        self.zoom: float = (self.root.winfo_screenheight() - 190) / page_height

        # Put the action buttons in the first row, and the mode buttons
        # (which stay pressed to show the kind of the next region) in
        # the second.
        self.kind_var: tk.StringVar = tk.StringVar(value=self.kind)
        actions: tk.Frame = tk.Frame(self.root)
        actions.pack(fill="x")
        tk.Label(actions, text="Actions:").pack(side="left")
        key: str
        label: str
        for key, label in (
            ("p", "Previous"),
            ("n", "Next"),
            ("u", "Undo"),
            ("[", "Region Up"),
            ("]", "Region Down"),
            ("x", "Ignore"),
            ("q", "Quit"),
        ):
            tk.Button(
                actions,
                text=f"{label} ({key})",
                command=functools.partial(self.command, key),
            ).pack(side="left")
        modes: tk.Frame = tk.Frame(self.root)
        modes.pack(fill="x")
        tk.Label(modes, text="Mode:").pack(side="left")
        kind: str
        for key, kind in KINDS.items():
            tk.Radiobutton(
                modes,
                text=f"{kind.title()} ({key})",
                fg=COLORS[kind],
                variable=self.kind_var,
                value=kind,
                indicatoron=False,
                command=functools.partial(self.command, key),
            ).pack(side="left")
        self.status: tk.Label = tk.Label(self.root, anchor="w")
        self.status.pack(fill="x")
        self.canvas: tk.Canvas = tk.Canvas(self.root, cursor="crosshair")
        self.canvas.pack()
        self.photo: tk.PhotoImage = tk.PhotoImage()

        # Bind the mouse and keys.
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.on_delete)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol(
            "WM_DELETE_WINDOW", functools.partial(self.command, "q")
        )
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
        page: pymupdf.Page = self.doc[self.page_no]
        pixmap: pymupdf.Pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(self.zoom, self.zoom)
        )
        self.photo = tk.PhotoImage(data=pixmap.tobytes("png"))
        self.canvas.config(width=pixmap.width, height=pixmap.height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

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
        self.draw_regions()

    # Method `App.draw_regions()`:
    def draw_regions(self) -> None:
        """Draw the regions and update the status line."""
        self.canvas.delete("region")
        z: float = self.zoom
        index: int
        region: Region
        for index, region in enumerate(self.regions):
            chosen: bool = index == self.selected
            self.canvas.create_rectangle(
                region.x0 * z,
                region.y0 * z,
                region.x1 * z,
                region.y1 * z,
                outline=COLORS[region.kind],
                width=5 if chosen else 2,
                dash=(6, 3) if chosen else (),
                tags="region",
            )
        self.status.config(
            text=f"Page {self.page_no + 1} "
            f"(of {self.first + 1}-{self.last + 1})  "
            f"Next region: {self.kind}  "
            "(drag to add a region, click to select one, "
            "right click to ignore one)  "
            f"{self.message}"
        )

    # Method `App.on_press()`:
    def on_press(self, event: tk.Event[tk.Canvas]) -> None:
        """Start dragging a new region.

        Arguments:
        * `event` (`tk.Event[tk.Canvas]`):
          The mouse press.
        """
        self.drag = (event.x, event.y)
        self.rubber = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=COLORS[self.kind]
        )

    # Method `App.on_motion()`:
    def on_motion(self, event: tk.Event[tk.Canvas]) -> None:
        """Stretch the region being dragged.

        Arguments:
        * `event` (`tk.Event[tk.Canvas]`):
          The mouse motion.
        """
        self.canvas.coords(self.rubber, *self.drag, event.x, event.y)

    # Method `App.on_release()`:
    def on_release(self, event: tk.Event[tk.Canvas]) -> None:
        """Finish the region being dragged.

        Arguments:
        * `event` (`tk.Event[tk.Canvas]`):
          The mouse release.
        """
        self.canvas.delete(self.rubber)
        x0: float = min(self.drag[0], event.x) / self.zoom
        x1: float = max(self.drag[0], event.x) / self.zoom
        y0: float = min(self.drag[1], event.y) / self.zoom
        y1: float = max(self.drag[1], event.y) / self.zoom
        if x1 - x0 > 3 and y1 - y0 > 3:
            self.regions.append(Region(self.kind, x0, y0, x1, y1))
            self.selected = -1
        else:
            self.select_at(event)
        self.draw_regions()

    # Method `App.select_at()`:
    def select_at(self, event: tk.Event[tk.Canvas]) -> None:
        """Select the smallest region under the mouse, if any.

        Arguments:
        * `event` (`tk.Event[tk.Canvas]`):
          The mouse event.
        """
        point: pymupdf.Point = pymupdf.Point(event.x, event.y) / self.zoom
        under: list[int] = [
            i for i, r in enumerate(self.regions) if point in r.rect()
        ]
        self.selected = min(
            under, key=lambda i: self.regions[i].rect().get_area(), default=-1
        )

    # Method `App.on_delete()`:
    def on_delete(self, event: tk.Event[tk.Canvas]) -> None:
        """Ignore the smallest region under the mouse.

        Arguments:
        * `event` (`tk.Event[tk.Canvas]`):
          The mouse press.
        """
        self.select_at(event)
        self.command("x")

    # Method `App.on_key()`:
    def on_key(self, event: tk.Event[tk.Misc]) -> None:
        """Handle a key press.

        Arguments:
        * `event` (`tk.Event[tk.Misc]`):
          The key press.
        """
        self.command(event.char)

    # Method `App.command()`:
    def command(self, key: str) -> None:
        """Do the command of a key or button.

        Arguments:
        * `key` (`str`):
          The command's key (e.g. `n` for the next page).
        """
        if key in KINDS:
            self.kind = KINDS[key]
            self.kind_var.set(self.kind)
        elif key == "n" and self.page_no < self.last:
            self.save_if_marked()
            self.page_no += 1
            self.show_page()
        elif key == "p" and self.page_no > self.first:
            self.save_if_marked()
            self.page_no -= 1
            self.show_page()
        elif key == "u" and self.regions:
            self.regions.pop()
            self.selected = -1
        elif key in "[]" and key and self.regions:
            # Step through the regions top to bottom (or back up).
            order: list[int] = sorted(
                range(len(self.regions)),
                key=lambda i: (self.regions[i].y0, self.regions[i].x0),
            )
            step: int = 1 if key == "]" else -1
            here: int = (
                order.index(self.selected)
                if self.selected in order
                else (-1 if step > 0 else 0)
            )
            self.selected = order[(here + step) % len(order)]
        elif key == "x" and 0 <= self.selected < len(self.regions):
            self.ignored.append(self.regions.pop(self.selected))
            self.selected = -1
        elif key == "q":
            self.save_if_marked()
            self.root.destroy()
            return
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

        # Write each region, top to bottom.
        page: pymupdf.Page = self.doc[self.page_no]
        parts: list[str] = [f"# Page {self.page_no + 1}"]
        image_count: int = 0
        region: Region
        for region in sorted(self.regions, key=lambda r: (r.y0, r.x0)):
            text: str = " ".join(
                page.get_text("text", clip=region.rect()).split()
            )
            if region.kind == "title":
                parts.append(f"## {text}")
            elif region.kind == "text":
                parts.append(text)
            elif region.kind == "image":
                image_count += 1
                name: str = f"{stem}_{image_count}.png"
                page.get_pixmap(dpi=150, clip=region.rect()).save(
                    self.json_path().parent / name
                )
                parts.append(f"![image]({name})")
            else:
                words: list[Word] = [
                    w[:5] for w in page.get_text("words", clip=region.rect())
                ]
                parts.append(markdown_table(table_rows(words)))
        md_path: Path = self.json_path().parent / f"{stem}.md"
        md_path.write_text("\n\n".join(parts) + "\n")
        self.status.config(text=f"Saved {md_path}")


# Function `main()`:
def main() -> None:
    """Run `catxtract` with the command line arguments."""
    # Check the arguments, and get the page range.
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(1)
    span: list[str] = (sys.argv[3] if len(sys.argv) == 4 else "1-0").split("-")
    if len(span) > 2 or not all(n.isdigit() for n in span):
        raise SystemExit(f"{sys.argv[3]!r} is not a page range like 100-102")
    first: int = int(span[0]) - 1
    last: int = int(span[-1]) - 1

    # Run the window.
    app: App = App(Path(sys.argv[1]), Path(sys.argv[2]), first, last)
    app.root.mainloop()


if __name__ == "__main__":
    main()
