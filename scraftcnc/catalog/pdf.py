"""PDF pages, read with `pdfplumber` and drawn with `pypdfium2`.

This is the only module of `catxtract` that touches the PDF libraries,
which are fetched into `~/.scraftcnc/packages/` the first time they
are needed (`scraftcnc.packages`).  Both are permissively licensed
(`pdfplumber` and `pdfminer.six` MIT, `pypdfium2` Apache/BSD).

All coordinates are PDF points, measured from the top left corner of
the page, with y going down (as both `pdfplumber` and the screen do).
"""

from __future__ import annotations

import functools
import importlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from ..packages import require

# A word: (x0, y0, x1, y1, text).
Word: TypeAlias = tuple[float, float, float, float, str]


# Class `Rect`:
@dataclass(frozen=True, slots=True)
class Rect:
    """A rectangle, in PDF points.

    Attributes:
    * `x0` (`float`): The left edge.
    * `y0` (`float`): The top edge.
    * `x1` (`float`): The right edge.
    * `y1` (`float`): The bottom edge.

    Constructor:
    * `Rect(x0, y0, x1, y1)`
    """

    # Constructor arguments:
    x0: float = field(init=True)
    y0: float = field(init=True)
    x1: float = field(init=True)
    y1: float = field(init=True)

    # Method `Rect.width()`:
    def width(self) -> float:
        """Return the width (0 if the rectangle is empty).

        Returns:
        * (`float`): The width.
        """
        return max(self.x1 - self.x0, 0.0)

    # Method `Rect.height()`:
    def height(self) -> float:
        """Return the height (0 if the rectangle is empty).

        Returns:
        * (`float`): The height.
        """
        return max(self.y1 - self.y0, 0.0)

    # Method `Rect.area()`:
    def area(self) -> float:
        """Return the area (0 if the rectangle is empty).

        Returns:
        * (`float`): The area.
        """
        return self.width() * self.height()

    # Method `Rect.grow()`:
    def grow(self, margin: float) -> Rect:
        """Return the rectangle grown by a margin on every side.

        Arguments:
        * `margin` (`float`):
          How much to add on each side.

        Returns:
        * (`Rect`): The bigger rectangle.
        """
        return Rect(
            self.x0 - margin,
            self.y0 - margin,
            self.x1 + margin,
            self.y1 + margin,
        )

    # Method `Rect.intersection()`:
    def intersection(self, other: Rect) -> Rect:
        """Return the part shared with another rectangle.

        Arguments:
        * `other` (`Rect`):
          The other rectangle.

        Returns:
        * (`Rect`): The shared part, which may be empty.
        """
        return Rect(
            max(self.x0, other.x0),
            max(self.y0, other.y0),
            min(self.x1, other.x1),
            min(self.y1, other.y1),
        )

    # Method `Rect.union()`:
    def union(self, other: Rect) -> Rect:
        """Return the smallest rectangle around both rectangles.

        Arguments:
        * `other` (`Rect`):
          The other rectangle.

        Returns:
        * (`Rect`): The rectangle around both.
        """
        return Rect(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    # Method `Rect.intersects()`:
    def intersects(self, other: Rect) -> bool:
        """Return whether the rectangles share some area.

        Arguments:
        * `other` (`Rect`):
          The other rectangle.

        Returns:
        * (`bool`): `True` if they overlap.
        """
        return self.intersection(other).area() > 0.0

    # Method `Rect.contains()`:
    def contains(self, x: float, y: float) -> bool:
        """Return whether a point is inside the rectangle.

        Arguments:
        * `x` (`float`):
          The point's x.
        * `y` (`float`):
          The point's y.

        Returns:
        * (`bool`): `True` if the point is inside (or on an edge).
        """
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


# Function `box_of()`:
def box_of(item: dict[str, Any]) -> Rect:
    """Return the rectangle of a `pdfplumber` object (word, image, ...).

    Arguments:
    * `item` (`dict[str, Any]`):
      The object, with `x0`, `top`, `x1` and `bottom`.

    Returns:
    * (`Rect`): Its rectangle.
    """
    return Rect(
        float(item["x0"]),
        float(item["top"]),
        float(item["x1"]),
        float(item["bottom"]),
    )


# Class `Page`:
class Page:
    """One page of a PDF.

    Attributes:
    * `document` (`Document`): The PDF the page is in.
    * `index` (`int`): The page's index, counting from 0.
    * `pdfium` (`Any`): The `pypdfium2` page (drawing).
    * `plumber` (`Any`): The `pdfplumber` page (text, images, tables).
    * `rect` (`Rect`): The whole page.
    """

    # Method `Page.__init__()`:
    def __init__(self, document: Document, index: int) -> None:
        """Open a page from each library.

        Arguments:
        * `document` (`Document`):
          The PDF the page is in.
        * `index` (`int`):
          The page's index, counting from 0.
        """
        self.document: Document = document
        self.index: int = index
        plumber: Any = document.plumber.pages[index]
        self.plumber: Any = plumber
        self.pdfium: Any = document.pdfium[index]
        self.rect: Rect = Rect(
            0.0, 0.0, float(plumber.width), float(plumber.height)
        )

    # Method `Page.cropped()`:
    def cropped(self, clip: Rect | None) -> Any:
        """Return the `pdfplumber` page, cut down to a rectangle.

        Objects that touch the rectangle are kept whole, as PyMuPDF's
        `clip` did.

        Arguments:
        * `clip` (`Rect | None`):
          The rectangle, or `None` for the whole page.

        Returns:
        * (`Any`): The `pdfplumber` page or cropped page.
        """
        if clip is None:
            return self.plumber
        box: Rect = clip.intersection(self.rect)
        if box.area() <= 0.0:
            return None
        return self.plumber.crop(
            (box.x0, box.y0, box.x1, box.y1), strict=False
        )

    # Method `Page.words()`:
    def words(self, clip: Rect | None = None) -> list[Word]:
        """Return the words that touch a rectangle.

        Arguments:
        * `clip` (`Rect | None`):
          The rectangle, or `None` for the whole page.

        Returns:
        * (`list[Word]`): The words, in the order of the page.
        """
        page: Any = self.cropped(clip)
        if page is None:
            return []
        return [
            (*_corners(box_of(word)), str(word["text"]))
            for word in page.extract_words()
        ]

    # Method `Page.text()`:
    def text(self, clip: Rect | None = None) -> str:
        """Return the text that touches a rectangle.

        Arguments:
        * `clip` (`Rect | None`):
          The rectangle, or `None` for the whole page.

        Returns:
        * (`str`): The text, line by line.
        """
        page: Any = self.cropped(clip)
        return "" if page is None else str(page.extract_text())

    # Method `Page.lines()`:
    def lines(self) -> list[tuple[Rect, str]]:
        """Return the page's lines of text, as pdfminer lays them out.

        pdfminer splits a line at a wide gap (e.g. between columns),
        but keeps a page wide line (e.g. a footer) whole, and keeps
        leading spaces, which mark indented lines (e.g. in an index).
        Working out the layout takes about a second a page, so it is
        done only here.

        Returns:
        * (`list[tuple[Rect, str]]`): Each line's rectangle and text
          (with no line end), in the order pdfminer finds them.
        """
        page: Any = self.document.layout().pages[self.index]
        return [
            (box_of(line), str(line["text"]).rstrip())
            for line in page.objects.get("textlinehorizontal", [])
        ]

    # Method `Page.image_boxes()`:
    def image_boxes(self) -> list[Rect]:
        """Return where the embedded images are, cut to the page.

        Returns:
        * (`list[Rect]`): The images' rectangles.
        """
        return [
            box_of(image).intersection(self.rect)
            for image in self.plumber.images
        ]

    # Method `Page.table_boxes()`:
    def table_boxes(self) -> list[Rect]:
        """Return where `pdfplumber` finds tables (from ruled lines).

        Returns:
        * (`list[Rect]`): The tables' rectangles.
        """
        return [
            Rect(*(float(value) for value in table.bbox))
            for table in self.plumber.find_tables()
        ]

    # Method `Page.png()`:
    def png(self, scale: float, clip: Rect | None = None) -> bytes:
        """Draw the page, or a part of it, as a PNG image.

        Arguments:
        * `scale` (`float`):
          Pixels per PDF point (e.g. 150 / 72 for 150 dots per inch).
        * `clip` (`Rect | None`):
          The part to draw, or `None` for the whole page.

        Returns:
        * (`bytes`): The PNG image.
        """
        image: Any = self.pdfium.render(scale=scale).to_pil()
        if clip is not None:
            box: Rect = clip.intersection(self.rect)
            image = image.crop(
                tuple(round(value * scale) for value in _corners(box))
            )
        data: io.BytesIO = io.BytesIO()
        image.save(data, format="PNG")
        return data.getvalue()


# Function `_corners()`:
def _corners(rect: Rect) -> tuple[float, float, float, float]:
    """Return a rectangle as `(x0, y0, x1, y1)`.

    Arguments:
    * `rect` (`Rect`):
      The rectangle.

    Returns:
    * (`tuple[float, float, float, float]`): Its edges.
    """
    return (rect.x0, rect.y0, rect.x1, rect.y1)


# Class `Document`:
class Document:
    """A PDF, opened by both libraries.

    Attributes:
    * `path` (`Path`): The PDF's file.
    * `pdfplumber` (`Any`): The `pdfplumber` module.
    * `pdfium` (`Any`): The `pypdfium2` document.
    * `plumber` (`Any`): The `pdfplumber` document.
    * `plumber_layout` (`Any`): The `pdfplumber` document that works
      out pdfminer's layout, opened when first needed, or `None`.
    * `size` (`int`): The number of pages.
    """

    # Method `Document.__init__()`:
    def __init__(self, path: Path) -> None:
        """Open a PDF, fetching the PDF packages the first time.

        The packages are fetched here, not on import, so that nothing
        is fetched until a PDF is really opened.  They are imported by
        name, since they live in `~/.scraftcnc/packages/`, where
        `mypy` and `pylint` do not look.

        Arguments:
        * `path` (`Path`):
          The PDF.

        Raises:
        * `SystemExit`: If the packages can not be fetched.
        """
        require("pdfplumber", "pdfplumber>=0.11")
        self.pdfplumber: Any = importlib.import_module("pdfplumber")
        pypdfium2: Any = importlib.import_module("pypdfium2")
        self.path: Path = path
        self.plumber: Any = self.pdfplumber.open(path)
        self.plumber_layout: Any = None
        self.pdfium: Any = pypdfium2.PdfDocument(path)
        self.size: int = len(self.pdfium)

    # Method `Document.__len__()`:
    def __len__(self) -> int:
        """Return the number of pages.

        Returns:
        * (`int`): The number of pages.
        """
        return self.size

    # Method `Document.__getitem__()`:
    def __getitem__(self, index: int) -> Page:
        """Return a page, counting from 0.

        Arguments:
        * `index` (`int`):
          The page's index.

        Returns:
        * (`Page`): The page.
        """
        return self.page(index)

    # Method `Document.page()`:
    # The cache holds on to `self`, which is fine: there is one
    # `Document`, open for the whole run.
    @functools.lru_cache(maxsize=4)  # noqa: B019
    def page(self, index: int) -> Page:
        """Return a page, counting from 0, keeping the last few.

        Arguments:
        * `index` (`int`):
          The page's index.

        Returns:
        * (`Page`): The page.
        """
        return Page(self, index)

    # Method `Document.close()`:
    def close(self) -> None:
        """Close the PDF in both libraries."""
        self.page.cache_clear()
        self.plumber.close()
        if self.plumber_layout is not None:
            self.plumber_layout.close()
            self.plumber_layout = None
        self.pdfium.close()

    # Method `Document.layout()`:
    def layout(self) -> Any:
        """Return the `pdfplumber` document that works out the layout.

        Returns:
        * (`Any`): The document, opened the first time.
        """
        if self.plumber_layout is None:
            self.plumber_layout = self.pdfplumber.open(self.path, laparams={})
        return self.plumber_layout
