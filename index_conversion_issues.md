# Index Conversion Issues

Problems seen in the Shars index, `SharsMD/page_451` to `page_455`.
Nothing here has been compared with the PDF, so a wrong number or a
misspelling may be the catalog's own rather than the conversion's.
Line numbers are those of each `page_NNN.md` on 2026-10-30.

## Structure

1. **Section letters as rows.**  The letter tabs (`A`, `B`, ...) come
   out as items: 3, 4, 9, 4 and 4 rows on pages 451 to 455.  They
   mostly gather at the end of a table, far from their sections, and
   one lands in the middle of a list: `page_451.md:104` (`C`) comes
   between the `Blocks` entries.
2. **Lists split at column and page breaks.**  Each column is its own
   table, and the parent heading is not repeated, so the children of
   a split list have no parent:
   * `Counterbore` ends page 451 (`page_451.md:322`); its children
     start page 452 (`page_452.md:7`).
   * `Gages` runs from page 452 (`page_452.md:305`) onto page 453
     (`page_453.md:7`).
   * `page_454.md:176` (`Tilting`) has lost its bullet, and appears to
     belong to `Tables` in the column before.
3. **Generated `+ NNN` rows.**  A multiple page entry gets one extra
   row per page after the first: 81, 88, 44, 70 and 8 rows on pages
   451 to 455.  They look like items, and some only repeat the page
   (`page_451.md:9`).
4. **Ranges have one link.**  A range links only its first page (for
   `Coolant Through`, `179-182` goes to 179), and its `+` row keeps the
   whole range (`page_452.md:20`: `+ 25 | 25-27`).
5. **Lost bullets.**  These look like children shown as top level
   items:
   * `page_453.md:163`: `Pocket`, probably under `Level`, which is
     four rows above it.
   * `page_455.md:48`: `Jaw System`, probably under `Vises`; the next
     row is a child of it.

## Entries That Look Misfiled

6. `page_454.md:98`: `Scraper` under `Scale`, five rows above the real
   `Scraper` heading (`page_454.md:103`).

## Page Numbers to Check

7. `page_455.md:59`: `Grinding` is `423,124,426`; 124 is among the
   carbide end mills, so probably 424.

The same product is given different pages in different entries.  Many
differ by one, so a digit may have been misread:

| # | Product | One entry | Other entry |
| -- | --------------------- | ------------------------ | ------------------------ |
| 8 | Thread measuring wire | 365 (`page_453.md:16`) | 356 (`page_454.md:225`) |
| 9 | Small hole gage | 387 (`page_453.md:9`) | 386 (`page_454.md:127`) |
| 10 | Pin gage | 374,375 (`page_452.md:319`) | 373,374 (`page_454.md:8`) |
| 11 | Plug gage | 404 (`page_452.md:322`) | 402,403 (`page_454.md:22`) |
| 12 | Screw pitch gage | 405 (`page_453.md:7`) | 404 (`page_454.md:109`) |
| 13 | Radius gage | 405 (`page_452.md:323`) | 404 (`page_454.md:46`) |
| 14 | Metalworking fluid | 450 (`page_452.md:303`) | 449 (`page_453.md:246`) |
| 15 | Diamond files | 430 (`page_451.md:11`) | 429 (`page_452.md:84`) |
| 16 | Mounted points | 428 (`page_451.md:14`) | 430 (`page_452.md:85`, `page_453.md:242`) |
| 17 | Cut-off wheels | 427,428 (`page_452.md:36`) | 425-427 (`page_455.md:53`) |
| 18 | Surface plates | 410 (`page_453.md:23`) | 400 (`page_454.md:163`) |
| 19 | Angle plates | 406,407,411,412 (`page_451.md:43`) | 364,365 (`page_454.md:13`) |
| 20 | Keyway broaches | 150 (`page_451.md:177`) | 143 (`page_453.md:141`) |
| 21 | Hydraulic magnetic base | 392 (`page_453.md:72`) | 350 (`page_453.md:176`) |

Page 450 is known to hold fluids, and `page_451.md:43` agrees with the
other angle plate entries, so #14 and #19 may be the catalog's or the
conversion's slips on the other side.

## Misspellings

22. `page_452.md:171`: `Lettter`.
23. `page_453.md:110`: `Talstock`.
24. `page_454.md:203`: `Tap/Dill Set`.
25. `page_455.md:35`: `Horizontal &Vertcal`.
26. `page_455.md:57`: `Metal Finshing`.
