"""Write shop files: TOML, in the key order `shops.KINDS` gives.

`tomllib` reads shop files; this writes them (`T.osiade~5.1.9` #18),
for the GUI and for the one time converter.  The keys come in the
order the field descriptions give (#4), so a file written again
changes only where a value did, and diffs in the user's version
control stay small.  `#` comments are not kept (#18); a kind's
`notes` key holds what they would have said (#133).

A file starts with its schema line (`shop_schema.schema_line()`),
then the header keys, then the kind's own keys: plain values first,
then each table (`[KEY]`) and list of tables (`[[KEY]]`), as TOML
needs them.  A string with a line break is written as a multi-line
literal string (`'''...'''`); a long one without, wrapped with line
ending backslashes, which TOML reads as one line; a long list, one
item per line (`WIDTH`).
"""

import datetime
import json
from collections.abc import Iterator

from .shop_schema import schema_line
from .shops import BARE_KEY, HEADER, KINDS, TableField, TableKind

# The widest line written, and the widest piece of a wrapped string.
WIDTH: int = 79
PIECE: int = 70


# Function `key_text()`:
def key_text(key: str) -> str:
    """Return a key as TOML writes it: bare when it can be.

    Arguments:
    * `key` (`str`): The key.

    Returns:
    * (`str`): The key, quoted if it must be.
    """
    return key if BARE_KEY.fullmatch(key) else json.dumps(key)


# Function `value_text()`:
def value_text(value: object) -> str:
    """Return a value that is not a table, as TOML writes it.

    Arguments:
    * `value` (`object`): A string, number, boolean, date or list.

    Returns:
    * (`str`): The TOML text.

    Raises:
    * `ValueError`: If it can not be written in one value.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, str):
        if "\n" in value and "'''" not in value:
            return f"'''\n{value}'''"
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(value_text(item) for item in value) + "]"
    raise ValueError(f"{value!r} can not be written as one TOML value")


# Function `pair_lines()`:
def pair_lines(key: str, value: object) -> list[str]:
    """Return the lines of one `KEY = VALUE`, wrapping a long string.

    Arguments:
    * `key` (`str`): The key.
    * `value` (`object`): Its value (not a table).

    Returns:
    * (`list[str]`): One line, or a long string's or list's lines.
    """
    line: str = f"{key_text(key)} = {value_text(value)}"
    if len(line) <= WIDTH:
        return [line]

    # A long list: one item per line.
    if isinstance(value, list):
        return (
            [f"{key_text(key)} = ["]
            + [f"  {value_text(item)}," for item in value]
            + ["]"]
        )
    if not isinstance(value, str) or "\n" in value:
        return [line]

    # Break after spaces, so each piece keeps them before its `\`.
    escaped: str = json.dumps(value, ensure_ascii=False)[1:-1]
    pieces: list[str] = []
    while len(escaped) > PIECE:
        cut: int = escaped.rfind(" ", 0, PIECE) + 1
        if cut <= 0:
            cut = escaped.find(" ", PIECE) + 1
            if cut <= 0:
                break
        while cut < len(escaped) and escaped[cut] == " ":
            cut += 1
        pieces.append(escaped[:cut])
        escaped = escaped[cut:]
    pieces.append(escaped)
    if len(pieces) == 1:
        return [line]
    return (
        [f'{key_text(key)} = """\\']
        + [f"  {piece}\\" for piece in pieces[:-1]]
        + [f'  {pieces[-1]}"""']
    )


# Function `ordered()`:
def ordered(
    table: dict[str, object], kind: TableKind | None, *, header: bool
) -> list[tuple[str, object, TableField | None]]:
    """Return a table's keys in the order the kind gives them.

    Arguments:
    * `table` (`dict[str, object]`): The table.
    * `kind` (`TableKind | None`): Its kind, if known.
    * `header` (`bool`): True to put the header keys first.

    Returns:
    * (`list[tuple[str, object, TableField | None]]`): Each key, its
      value, and its description (None for a key the kind lacks,
      which comes last, alphabetically).
    """
    fields: tuple[TableField, ...] = HEADER if header else ()
    if kind is not None:
        fields += kind.fields
    known: dict[str, TableField] = {schema.key: schema for schema in fields}
    order: list[str] = [key for key in known if key in table]
    order += sorted(key for key in table if key not in known)
    return [(key, table[key], known.get(key)) for key in order]


# Function `is_table()`:
def is_table(value: object) -> bool:
    """Tell whether a value is written as a table of its own.

    Arguments:
    * `value` (`object`): The value.

    Returns:
    * (`bool`): True for a table, or a list of tables.
    """
    return isinstance(value, dict) or (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) for item in value)
    )


# Function `of_kind()`:
def of_kind(schema: TableField | None) -> TableKind | None:
    """Return the kind of a table key's tables, if it has one.

    Arguments:
    * `schema` (`TableField | None`): The key's description.

    Returns:
    * (`TableKind | None`): The kind, or None.
    """
    if schema is None or not schema.of:
        return None
    return KINDS.get(schema.of)


# Function `table_lines()`:
def table_lines(
    table: dict[str, object],
    kind: TableKind | None,
    prefix: tuple[str, ...],
    *,
    header: bool = False,
) -> Iterator[str]:
    """Yield the lines of a table: its plain keys, then its tables.

    Arguments:
    * `table` (`dict[str, object]`): The table.
    * `kind` (`TableKind | None`): Its kind, if known.
    * `prefix` (`tuple[str, ...]`): The keys leading to it.
    * `header` (`bool`): True for a whole file (header keys first).

    Yields:
    * (`str`): Each line, with no newline.
    """
    # Plain keys first: TOML puts them before any table.
    keys: list[tuple[str, object, TableField | None]] = ordered(
        table, kind, header=header
    )
    key: str
    value: object
    schema: TableField | None
    for key, value, _schema in keys:
        if not is_table(value):
            yield from pair_lines(key, value)

    # Then each table, and each list of tables.
    for key, value, schema in keys:
        path: tuple[str, ...] = (*prefix, key)
        name: str = ".".join(key_text(part) for part in path)
        if isinstance(value, dict):
            yield from by_material_lines(value, schema, path, name)
        elif is_table(value):
            assert isinstance(value, list)
            item: object
            for item in value:
                assert isinstance(item, dict)
                yield ""
                yield f"[[{name}]]"
                yield from table_lines(item, of_kind(schema), path)


# Function `by_material_lines()`:
def by_material_lines(
    value: dict[str, object],
    schema: TableField | None,
    path: tuple[str, ...],
    name: str,
) -> Iterator[str]:
    """Yield a table, or a `by_material` table of tables.

    Arguments:
    * `value` (`dict[str, object]`): The table.
    * `schema` (`TableField | None`): Its key's description.
    * `path` (`tuple[str, ...]`): The keys leading to it.
    * `name` (`str`): `path`, as a TOML table name.

    Yields:
    * (`str`): Each line, with no newline.
    """
    # A `by_material` table: one table per material.
    if schema is not None and schema.form == "by_material":
        material: str
        item: object
        for material, item in value.items():
            assert isinstance(item, dict)
            yield ""
            yield f"[{name}.{key_text(material)}]"
            yield from table_lines(item, of_kind(schema), (*path, material))
        return

    # Any other table.
    yield ""
    yield f"[{name}]"
    yield from table_lines(value, of_kind(schema), path)


# Function `item_text()`:
def item_text(item: dict[str, object]) -> str:
    """Write one shop file: one item, of the kind its `kind` names.

    Arguments:
    * `item` (`dict[str, object]`): The item, as `tomllib` reads it.

    Returns:
    * (`str`): The file's text, starting with its schema line.

    Raises:
    * `ValueError`: If its `kind` is not one of `KINDS`.
    """
    kind_name: object = item.get("kind")
    if not isinstance(kind_name, str) or kind_name not in KINDS:
        raise ValueError(f"{kind_name!r} is not a kind of shop file")
    lines: list[str] = [schema_line(kind_name)]
    lines.extend(table_lines(item, KINDS[kind_name], (), header=True))
    return "\n".join(lines) + "\n"
