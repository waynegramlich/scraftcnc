"""The fields of a shop item, as its panel edits them (no Qt).

`T.osiade~5.1.9` S3.4 (#72, #132): a row per field, in the order
`shops.KINDS` gives, with its value as typed, what is wrong with it,
and (for a measurement) the value in the shop's units.  A value is
checked as it is typed and never written while bad (#15); a good one
is written with `shop_writer.item_text()`.  Only plain values (a
measurement, a string, a choice, a number, a date) are edited here;
tables and lists stay TOML, read only.
"""

import datetime
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..shop_writer import is_table, item_text, table_lines
from ..shops import (
    HEADER,
    KINDS,
    UNITS,
    TableField,
    measure,
    scalar_problem,
)

# The sketches that `Tool_Models.md` shows, one per kind (or view),
# from the top of the tree.
SKETCHES: Path = Path(__file__).resolve().parents[2] / "docs" / "tool_models"

# The forms edited as one line of text.
PLAIN: tuple[str, ...] = (
    *UNITS,
    "string",
    "choice",
    "integer",
    "positive_integer",
    "boolean",
    "date",
    "version",
)

# The header keys shown but not edited: changing them changes what
# the file is.
FIXED: tuple[str, ...] = ("kind", "version")

# The unit each kind of measurement is shown in, for a shop in inches
# and in millimeters (a kind not listed is shown as typed).
SHOP_UNITS: dict[str, dict[str, str]] = {
    "in": {
        "length": "in",
        "feed": "in/min",
        "acceleration": "in/s^2",
        "surface_speed": "sfm",
        "feed_per_rev": "in/rev",
        "chip_load": "in/tooth",
    },
    "mm": {
        "length": "mm",
        "feed": "mm/min",
        "acceleration": "mm/s^2",
        "surface_speed": "m/min",
        "feed_per_rev": "mm/rev",
        "chip_load": "mm/tooth",
    },
}


# Class `Row`:
@dataclass(slots=True)
class Row:
    """One field of an item, as its panel shows it.

    Attributes:
    * `schema` (`TableField`): What the field is.
    * `text` (`str`): Its value, as typed (`""` if it is not there).
    * `editable` (`bool`): True if the panel edits it.
    * `problem` (`str`): What is wrong with `text`, or `""`.
    * `shown` (`str`): The value in the shop's units, or `""`.

    Constructor:
    * `Row(schema, text, editable)`
    """

    # Constructor arguments:
    schema: TableField = field(init=True)
    text: str = field(init=True)
    editable: bool = field(init=True)

    # Remaining attributes (alphabetized):
    problem: str = field(init=False, default="")
    shown: str = field(init=False, default="")


# Function `value_of()`:
def value_of(text: str, schema: TableField) -> tuple[object, str]:
    """Return the value that a field's text stands for.

    Arguments:
    * `text` (`str`): The text, as typed.
    * `schema` (`TableField`): What the value must be.

    Returns:
    * (`tuple[object, str]`): The value and `""`, or the text itself
      and what is wrong with it.
    """
    # Nothing typed: fine, unless it is required.
    if not text.strip():
        return None, ("required" if schema.required else "")

    # Numbers, booleans and dates are typed as TOML writes them.
    value: object = text
    form: str = schema.form
    try:
        if form in ("integer", "positive_integer"):
            value = int(text)
        elif form == "date":
            value = datetime.date.fromisoformat(text.strip())
    except ValueError:
        pass
    if form == "boolean" and text.strip() in ("true", "false"):
        value = text.strip() == "true"
    return value, scalar_problem(value, schema)


# Function `text_of()`:
def text_of(value: object) -> str:
    """Return a plain value as a field shows it.

    Arguments:
    * `value` (`object`): The value, as `tomllib` reads it.

    Returns:
    * (`str`): Its text (`""` for no value).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


# Function `in_shop_units()`:
def in_shop_units(text: str, schema: TableField, units: str) -> str:
    """Return a measurement in the shop's units, if it is not already.

    Arguments:
    * `text` (`str`): The measurement, good, as typed.
    * `schema` (`TableField`): What it is.
    * `units` (`str`): The shop's units, `"in"` or `"mm"`.

    Returns:
    * (`str`): Such as `"6.35 mm"`, or `""` if there is nothing to add.
    """
    unit: str = SHOP_UNITS.get(units, {}).get(schema.form, "")
    if not unit or schema.form not in UNITS:
        return ""
    table: dict[str, float] = UNITS[schema.form]
    words: list[str] = text.split()
    if words and words[-1] == unit:
        return ""

    # `table` gives each unit in the units used inside.
    number: float = measure(text, table) / table[unit]
    return f"{number:.6g} {unit}"


# Function `check()`:
def check(row: Row, text: str, units: str) -> None:
    """Take a field's new text, and say what is wrong with it.

    Arguments:
    * `row` (`Row`): The field.
    * `text` (`str`): Its text, as typed.
    * `units` (`str`): The shop's units.
    """
    row.text = text
    row.problem = value_of(text, row.schema)[1]
    row.shown = (
        in_shop_units(text, row.schema, units)
        if text.strip() and not row.problem
        else ""
    )


# Function `fields()`:
def fields(item: dict[str, object]) -> tuple[TableField, ...]:
    """Return the fields of an item's kind, header first.

    Arguments:
    * `item` (`dict[str, object]`): The item.

    Returns:
    * (`tuple[TableField, ...]`): Its fields, or `()` if its kind is
      not one of `KINDS`.
    """
    kind: object = item.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return ()
    return HEADER + KINDS[kind].fields


# Function `rows()`:
def rows(item: dict[str, object], units: str) -> list[Row]:
    """Return the plain fields of an item, as its panel shows them.

    Arguments:
    * `item` (`dict[str, object]`): The item, as `tomllib` reads it.
    * `units` (`str`): The shop's units.

    Returns:
    * (`list[Row]`): A row per plain field, in `KINDS` order (those
      not there included, empty), or `[]` if the kind is unknown.
    """
    result: list[Row] = []
    schema: TableField
    for schema in fields(item):
        if schema.form not in PLAIN:
            continue
        value: object = item.get(schema.key)
        row: Row = Row(
            schema,
            text_of(value),
            schema.key not in FIXED and not is_table(value),
        )
        check(row, row.text, units)
        result.append(row)
    return result


# Function `rest_text()`:
def rest_text(item: dict[str, object]) -> str:
    """Return the TOML of the keys that are not plain fields.

    Arguments:
    * `item` (`dict[str, object]`): The item.

    Returns:
    * (`str`): Their TOML text, read only in the panel (`""` if none).
    """
    plain: set[str] = {
        schema.key for schema in fields(item) if schema.form in PLAIN
    }
    rest: dict[str, object] = {
        key: value for key, value in item.items() if key not in plain
    }
    return "\n".join(table_lines(rest, None, ())).strip("\n")


# Function `with_value()`:
def with_value(item: dict[str, object], row: Row) -> dict[str, object] | None:
    """Return the item with a field's new value, if it is good.

    Arguments:
    * `item` (`dict[str, object]`): The item.
    * `row` (`Row`): The field, with its text as typed.

    Returns:
    * (`dict[str, object] | None`): The new item (the key removed
      for an empty field), or None if the value is bad (#15).
    """
    value: object
    problem: str
    value, problem = value_of(row.text, row.schema)
    if problem:
        return None
    changed: dict[str, object] = dict(item)
    if value is None:
        changed.pop(row.schema.key, None)
    else:
        changed[row.schema.key] = value
    return changed


# Function `read_item()`:
def read_item(path: Path) -> tuple[dict[str, object], str]:
    """Read a shop file.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`tuple[dict[str, object], str]`): The item and `""`, or `{}`
      and what stops it being read.
    """
    try:
        with path.open("rb") as file:
            return tomllib.load(file), ""
    except (OSError, tomllib.TOMLDecodeError) as error:
        return {}, f"{path}: {error}"


# Function `write_item()`:
def write_item(path: Path, item: dict[str, object]) -> str:
    """Write a shop file, unless it would be the same.

    Arguments:
    * `path` (`Path`): The file.
    * `item` (`dict[str, object]`): The item.

    Returns:
    * (`str`): The text the file now holds.
    """
    text: str = item_text(item)
    try:
        old: str = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        old = ""
    if text != old:
        path.write_text(text, encoding="utf-8")
    return text


# Function `shop_units()`:
def shop_units(shop: Path | None) -> str:
    """Return the units a shop prefers.

    Arguments:
    * `shop` (`Path | None`): Its `shop.toml`, if any.

    Returns:
    * (`str`): `"in"` or `"mm"` (`"in"` when it does not say).
    """
    if shop is None:
        return "in"
    item: dict[str, object] = read_item(shop)[0]
    units: object = item.get("units")
    return units if isinstance(units, str) and units in SHOP_UNITS else "in"


# Function `sketch()`:
def sketch(item: dict[str, object]) -> Path | None:
    """Return the sketch of an item's kind, from `Tool_Models.md`.

    A kind with one sketch has `KIND.svg`; one with several views
    (e.g. `grid_plate_section.svg`, `grid_plate_top.svg`) shows the
    first, alphabetically (`T.osiade~5.1.9` #5, #14).

    Arguments:
    * `item` (`dict[str, object]`): The shop item, as read.

    Returns:
    * (`Path | None`): Its SVG file, or `None` when its kind has none.
    """
    kind: object = item.get("kind")
    if not isinstance(kind, str) or not kind:
        return None
    one: Path = SKETCHES / f"{kind}.svg"
    if one.is_file():
        return one
    views: list[Path] = sorted(SKETCHES.glob(f"{kind}_*.svg"))
    return views[0] if views else None
