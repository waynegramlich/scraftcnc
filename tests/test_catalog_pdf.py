"""Tests for `scraftcam.catalog.pdf` and the PDF side of `catxtract`.

The PDF is written by `write_pdf()` into a temporary directory, so no
binary file is kept in `git`.  The tests are skipped when `pdfplumber`
has not been fetched into `~/.scraftcam/packages/` (the tests never
fetch it).
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scraftcam.packages import PACKAGES_DIRECTORY

# Look where `scraftcam.packages` puts the PDF packages.
PDF_DIRECTORY: Path = PACKAGES_DIRECTORY / "pdfplumber"
if str(PDF_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PDF_DIRECTORY))
READY: bool = all(
    importlib.util.find_spec(name) is not None
    for name in ("pdfplumber", "pypdfium2")
)

# The page: US letter, in points.
WIDTH: float = 612.0
HEIGHT: float = 792.0

# The table: 3 columns and 4 rows, a header row and 3 data rows, with
# its top left corner at (72, 200) from the top of the page.
TABLE_LEFT: float = 72.0
TABLE_TOP: float = 200.0
COLUMN: float = 120.0
ROW: float = 20.0
CELLS: list[list[str]] = [
    ["Size", "Order", "Price"],
    ["1/4", "404-2118", "7.95"],
    ["3/8", "404-2119", "9.50"],
    ["1/2", "404-2120", "8.00"],
]

# The image: 2 by 2 gray pixels, drawn 100 points square at (350, 400)
# from the top of the page.
IMAGE: tuple[float, float, float] = (350.0, 400.0, 100.0)


# Function `content()`:
def content() -> bytes:
    """Return the page's drawing commands.

    Returns:
    * (`bytes`): A title, an indented line, the ruled table and the
      image, in PDF's coordinates (y up from the bottom).
    """
    # The text: a title, a plain line and an indented one.
    ops: list[str] = [
        "BT /F1 18 Tf 72 720 Td (Catalog Title) Tj ET",
        "BT /F1 10 Tf 72 690 Td (Plain line) Tj ET",
        "BT /F1 10 Tf 72 676 Td (    Indented line) Tj ET",
    ]

    # The table's rules.
    rows: int = len(CELLS)
    columns: int = len(CELLS[0])
    top: float = HEIGHT - TABLE_TOP
    bottom: float = top - rows * ROW
    right: float = TABLE_LEFT + columns * COLUMN
    ops.append("0.5 w")
    row: int
    for row in range(rows + 1):
        y: float = top - row * ROW
        ops.append(f"{TABLE_LEFT} {y} m {right} {y} l S")
    column: int
    for column in range(columns + 1):
        x: float = TABLE_LEFT + column * COLUMN
        ops.append(f"{x} {top} m {x} {bottom} l S")

    # The table's cells.
    text: str
    for row, cells in enumerate(CELLS):
        for column, text in enumerate(cells):
            x = TABLE_LEFT + column * COLUMN + 4
            y = top - (row + 1) * ROW + 6
            ops.append(f"BT /F1 10 Tf {x} {y} Td ({text}) Tj ET")

    # The image, inline.
    left, image_top, size = IMAGE
    ops.append(
        f"q {size} 0 0 {size} {left} {HEIGHT - image_top - size} cm "
        "BI /W 2 /H 2 /CS /G /BPC 8 ID \x40\xc0\xc0\x40 EI Q"
    )
    return "\n".join(ops).encode("latin-1")


# Function `write_pdf()`:
def write_pdf(path: Path) -> None:
    """Write a one page PDF, laid out by hand.

    Arguments:
    * `path` (`Path`):
      Where to write it.
    """
    # The objects, numbered from 1.
    stream: bytes = content()
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {WIDTH} {HEIGHT}]"
            " /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]

    # The file, with each object's offset in the cross reference table.
    data: bytearray = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    number: int
    body: bytes
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref: int = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    offset: int
    for offset in offsets:
        data += b"%010d 00000 n \n" % offset
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    data += b"startxref\n%d\n%%%%EOF\n" % xref
    path.write_bytes(bytes(data))


@unittest.skipUnless(READY, "pdfplumber or pypdfium2 missing")
class PdfTest(unittest.TestCase):
    """Tests of `Document`, `Page` and `catxtract`'s use of them."""

    # pylint: disable=import-outside-toplevel

    def setUp(self) -> None:
        """Write the PDF and open it."""
        from scraftcam.catalog import catxtract, pdf

        self.catxtract = catxtract
        self.pdf = pdf
        # `enterContext()` removes the directory after the test.
        # pylint: disable-next=consider-using-with
        directory: str = self.enterContext(tempfile.TemporaryDirectory())
        path: Path = Path(directory) / "test.pdf"
        write_pdf(path)
        self.document = pdf.Document(path)
        self.addCleanup(self.document.close)
        self.page = self.document[0]

    def test_rect(self) -> None:
        """`Rect` measures, combines and tests rectangles."""
        rect = self.pdf.Rect
        a = rect(0.0, 0.0, 10.0, 20.0)
        b = rect(5.0, 10.0, 30.0, 40.0)
        self.assertEqual(a.area(), 200.0)
        self.assertEqual(a.intersection(b), rect(5.0, 10.0, 10.0, 20.0))
        self.assertEqual(a.union(b), rect(0.0, 0.0, 30.0, 40.0))
        self.assertEqual(a.grow(1.0), rect(-1.0, -1.0, 11.0, 21.0))
        self.assertTrue(a.intersects(b))
        self.assertFalse(a.intersects(rect(10.0, 0.0, 20.0, 20.0)))
        self.assertTrue(a.contains(10.0, 20.0))
        self.assertFalse(a.contains(11.0, 5.0))
        self.assertEqual(rect(5.0, 5.0, 0.0, 0.0).area(), 0.0)

    def test_document(self) -> None:
        """The document has one page, of the right size."""
        self.assertEqual(len(self.document), 1)
        self.assertEqual(
            self.page.rect, self.pdf.Rect(0.0, 0.0, WIDTH, HEIGHT)
        )
        self.assertIs(self.document[0], self.page)

    def test_words_and_text(self) -> None:
        """Words and text come from the whole page or from a clip."""
        words: list[str] = [word[4] for word in self.page.words()]
        self.assertIn("Title", words)
        self.assertIn("404-2119", words)
        clip = self.pdf.Rect(60.0, 60.0, 400.0, 80.0)
        self.assertEqual(self.page.text(clip), "Catalog Title")
        self.assertEqual(
            self.page.words(self.pdf.Rect(-50.0, -50.0, -10.0, -10.0)), []
        )

    def test_lines_keep_indents(self) -> None:
        """`lines_inside()` keeps the indent of an indented line."""
        region = self.catxtract.Region("index", 60.0, 95.0, 400.0, 125.0)
        self.assertEqual(
            self.catxtract.lines_inside(self.page, region).splitlines(),
            ["Plain line", "    Indented line"],
        )

    def test_detect(self) -> None:
        """`detect()` finds the ruled table and the image."""
        found = self.catxtract.detect(self.page)
        kinds: list[str] = sorted(region.kind for region in found)
        self.assertEqual(kinds, ["image", "table"])
        table = next(r for r in found if r.kind == "table")
        self.assertAlmostEqual(table.x0, TABLE_LEFT, delta=1.0)
        self.assertAlmostEqual(table.y0, TABLE_TOP, delta=1.0)
        image = next(r for r in found if r.kind == "image")
        self.assertAlmostEqual(image.x0, IMAGE[0], delta=1.0)
        self.assertAlmostEqual(image.y1, IMAGE[1] + IMAGE[2], delta=1.0)

    def test_table_rows(self) -> None:
        """The table's words become its rows, header first."""
        table = next(
            r for r in self.catxtract.detect(self.page) if r.kind == "table"
        )
        rows: list[list[str]] = self.catxtract.table_rows(
            self.page.words(table.rect())
        )
        self.assertEqual(rows, CELLS)

    def test_png(self) -> None:
        """The page, or a part of it, is drawn as a PNG."""
        whole: bytes = self.page.png(0.5)
        self.assertTrue(whole.startswith(b"\x89PNG\r\n\x1a\n"))
        width: int = int.from_bytes(whole[16:20], "big")
        height: int = int.from_bytes(whole[20:24], "big")
        self.assertEqual((width, height), (306, 396))
        part: bytes = self.page.png(1.0, self.pdf.Rect(0.0, 0.0, 50.0, 40.0))
        self.assertEqual(int.from_bytes(part[16:20], "big"), 50)
        self.assertEqual(int.from_bytes(part[20:24], "big"), 40)


@unittest.skipUnless(READY, "pdfplumber or pypdfium2 missing")
class AppTest(unittest.TestCase):
    """Tests of `catxtract`'s window, drawn offscreen by Qt."""

    # pylint: disable=import-outside-toplevel

    def setUp(self) -> None:
        """Write the PDF, and open it in a window."""
        from scraftcam.catalog import catxtract
        from tests import qt_hmi

        self.catxtract = catxtract
        self.qt_hmi = qt_hmi
        # pylint: disable-next=consider-using-with
        directory: str = self.enterContext(tempfile.TemporaryDirectory())
        path: Path = Path(directory) / "test.pdf"
        write_pdf(path)
        self.out: Path = Path(directory) / "out"
        self.app = catxtract.App(path, self.out)
        self.addCleanup(self.app.close)

    def click(self, button: Any, x: float, y: float) -> None:
        """Press and release a mouse button at a point (PDF points).

        Arguments:
        * `button` (`Any`): The mouse button (`Qt.MouseButton`).
        * `x` (`float`): Across the page.
        * `y` (`float`): Down the page.
        """
        self.drag(button, (x, y), (x, y))

    def drag(
        self,
        button: Any,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> None:
        """Drag with a mouse button from one point to another (points).

        Arguments:
        * `button` (`Any`): The mouse button (`Qt.MouseButton`).
        * `start` (`tuple[float, float]`): Where the drag starts.
        * `end` (`tuple[float, float]`): Where it ends.
        """
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        zoom: float = self.app.zoom
        first: QPoint = QPoint(round(start[0] * zoom), round(start[1] * zoom))
        last: QPoint = QPoint(round(end[0] * zoom), round(end[1] * zoom))
        canvas: Any = self.app.canvas
        QTest.mousePress(canvas, button, pos=first)
        QTest.mouseRelease(canvas, button, pos=last)

    def test_draw_and_save(self) -> None:
        """A region dragged and made a title is saved on Quit."""
        from PySide6.QtCore import Qt

        # The page starts with its suggestions; clear them.
        self.assertIn("Suggested", self.app.status.text())
        self.app.command("c")
        self.assertEqual(self.app.regions, [])

        # Drag around the title, and make it a title.
        self.drag(Qt.MouseButton.LeftButton, (60.0, 50.0), (300.0, 80.0))
        self.assertEqual(len(self.app.regions), 1)
        self.assertEqual(self.app.selected, 0)
        self.app.kind_buttons["title"].click()
        self.assertEqual(self.app.regions[0].kind, "title")
        self.assertTrue(self.app.kind_buttons["title"].isChecked())
        self.assertFalse(self.app.kind_buttons["table"].isChecked())

        # Quit saves the page.
        self.app.command("q")
        markdown: str = (self.out / "page_001" / "page_001.md").read_text()
        self.assertTrue(markdown.startswith("# Page 1\n"))
        self.assertIn("## Catalog Title", markdown)
        saved: Any = json.loads(
            (self.out / "page_001" / "page_001.json").read_text()
        )
        self.assertEqual(saved["regions"][0]["kind"], "title")

    def test_click_and_ignore(self) -> None:
        """A click selects a region; the right button ignores it."""
        from PySide6.QtCore import Qt

        # A region, then a click inside it elsewhere selects it.
        self.app.command("c")
        self.drag(Qt.MouseButton.LeftButton, (60.0, 50.0), (300.0, 80.0))
        self.app.command("u")
        self.assertEqual(self.app.regions, [])
        self.drag(Qt.MouseButton.LeftButton, (60.0, 50.0), (300.0, 80.0))
        self.app.selected = -1
        self.click(Qt.MouseButton.LeftButton, 100.0, 60.0)
        self.assertEqual(self.app.selected, 0)

        # The right button moves it to the ignored regions.
        self.click(Qt.MouseButton.RightButton, 100.0, 60.0)
        self.assertEqual(self.app.regions, [])
        self.assertEqual(len(self.app.ignored), 1)

    def test_page_buttons(self) -> None:
        """With one page, the page buttons have nowhere to go."""
        self.assertEqual(
            {key: b.isEnabled() for key, b in self.app.page_buttons.items()},
            {"P": False, "p": False, "n": False, "N": False},
        )
        from PySide6.QtTest import QTest

        QTest.keyClicks(self.app.goto, "a1b234567")
        self.assertEqual(self.app.goto.text(), "12345")
        self.app.goto.clear()
        self.app.go_to()
        self.assertIn("Type a page number first.", self.app.status.text())


if __name__ == "__main__":
    unittest.main()
