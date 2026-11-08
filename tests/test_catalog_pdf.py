"""Tests for `scraftcnc.catalog.pdf` and the PDF side of `catxtract`.

The PDF is written by `write_pdf()` into a temporary directory, so no
binary file is kept in `git`.  The tests are skipped when `pdfplumber`
has not been fetched into `~/.scraftcnc/packages/` (the tests never
fetch it), or when `tkinter` is missing.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from scraftcnc.packages import PACKAGES_DIRECTORY

# Look where `scraftcnc.packages` puts the PDF packages.
if str(PACKAGES_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIRECTORY))
READY: bool = all(
    importlib.util.find_spec(name) is not None
    for name in ("pdfplumber", "pypdfium2", "tkinter")
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


@unittest.skipUnless(READY, "pdfplumber, pypdfium2 or tkinter missing")
class PdfTest(unittest.TestCase):
    """Tests of `Document`, `Page` and `catxtract`'s use of them."""

    # pylint: disable=import-outside-toplevel

    def setUp(self) -> None:
        """Write the PDF and open it."""
        from scraftcnc.catalog import catxtract, pdf

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


if __name__ == "__main__":
    unittest.main()
