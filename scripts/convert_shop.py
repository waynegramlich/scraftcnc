#!/usr/bin/env python3
"""Convert a shop from Nested TOML to directories, once (`T.osiade~5.1.9`).

The old layout: a top file (`home_shop.toml`) naming other files with
`"@FILE"` strings, some holding many items (`tools.toml`).  The new
one (#130): `shop.toml`, and one item per file in `machines/`,
`controllers/`, `tools/`, `tooling/` and `materials/`; a machine names
its controller by name, and holds its tool table.  Comments become
`notes` (#133): a comment block before a table, or before a key, or at
the end of a line, goes into the `notes` of the table it is in.

```
python3 scripts/convert_shop.py examples/shop/home_shop.toml NEW_DIRECTORY
```

Each file written is read back, and must give what was converted.
"""

import re
import sys
import tomllib
from pathlib import Path
from typing import Any

# Run as a script, Python puts `scripts/` on `sys.path`, not the
# directory above it, so that one is added.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from scraftcam.shop_writer import item_text
from scraftcam.shops import FORMAT_VERSION, KINDS

# pylint: enable=wrong-import-position

# A table's header line, and a comment (at the start, or after a value).
HEADER_LINE: re.Pattern[str] = re.compile(r"\s*(\[\[?)\s*([^\]]+?)\s*\]\]?")
COMMENT: re.Pattern[str] = re.compile(r"\s*#\s?(.*)")
TRAILING: re.Pattern[str] = re.compile(
    r"""^([^#"']*(?:"[^"]*"|'[^']*')?[^#"']*)#\s?(.*)$"""
)


# Function `slug()`:
def slug(name: str) -> str:
    """Return a file name for an item's name.

    Arguments:
    * `name` (`str`): The item's name.

    Returns:
    * (`str`): Lower case letters, digits and `_`, then `.toml`.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".toml"


# Function `comments()`:
def comments(text: str) -> dict[tuple[str | int, ...], list[str]]:
    """Find each comment, and the table it belongs to.

    Arguments:
    * `text` (`str`): A TOML file.

    Returns:
    * (`dict[tuple[str | int, ...], list[str]]`): The comments by the
      path of their table (`()` for the file; a list item's index is
      part of its path), in order.
    """
    found: dict[tuple[str | int, ...], list[str]] = {}
    counts: dict[tuple[str, ...], int] = {}
    table: tuple[str | int, ...] = ()
    waiting: list[str] = []
    line: str
    for line in text.splitlines():
        # A whole line comment waits for what it is about.
        whole: re.Match[str] | None = COMMENT.fullmatch(line)
        if whole is not None:
            waiting.append(whole.group(1).strip())
            continue

        # A table header: the waiting comments are about it.
        header: re.Match[str] | None = HEADER_LINE.match(line)
        if header is not None:
            keys: tuple[str, ...] = tuple(
                part.strip().strip('"') for part in header.group(2).split(".")
            )
            table = keys
            if header.group(1) == "[[":
                index: int = counts.get(keys, 0)
                counts[keys] = index + 1
                table = (*keys, index)
            table = resolve(table, counts)
        elif line.strip():
            # A key: waiting comments and a trailing one are its table's.
            trailing: re.Match[str] | None = TRAILING.match(line)
            if trailing is not None and trailing.group(2).strip():
                key: str = trailing.group(1).split("=")[0].strip()
                waiting.append(f"{key}: {trailing.group(2).strip()}")
        if waiting:
            found.setdefault(table, []).extend(waiting)
            waiting = []
    if waiting:
        found.setdefault(table, []).extend(waiting)
    return found


# Function `resolve()`:
def resolve(
    table: tuple[str | int, ...], counts: dict[tuple[str, ...], int]
) -> tuple[str | int, ...]:
    """Put list indices into a table path (`[a.b]` under `[[a]]`).

    Arguments:
    * `table` (`tuple[str | int, ...]`): The path, as its header says.
    * `counts` (`dict[tuple[str, ...], int]`): How many of each list
      of tables have been seen.

    Returns:
    * (`tuple[str | int, ...]`): The path, with the index of the last
      item of each list of tables on the way.
    """
    resolved: list[str | int] = []
    keys: list[str] = []
    part: str | int
    for position, part in enumerate(table):
        resolved.append(part)
        if isinstance(part, int):
            continue
        keys.append(part)
        last: bool = position == len(table) - 1
        following: bool = position + 1 < len(table) and isinstance(
            table[position + 1], int
        )
        if tuple(keys) in counts and not last and not following:
            resolved.append(counts[tuple(keys)] - 1)
    return tuple(resolved)


# Function `add_notes()`:
def add_notes(
    data: dict[str, Any], found: dict[tuple[str | int, ...], list[str]]
) -> None:
    """Put each comment into the `notes` of its table.

    Arguments:
    * `data` (`dict[str, Any]`): The file, as `tomllib` read it.
    * `found` (`dict[tuple[str | int, ...], list[str]]`): Its comments.
    """
    path: tuple[str | int, ...]
    lines: list[str]
    for path, lines in found.items():
        table: Any = data
        part: str | int
        for part in path:
            table = table[part]
        text: str = " ".join(line for line in lines if line)
        if text:
            old: str = str(table.get("notes", ""))
            table["notes"] = f"{old} {text}".strip()


# Function `load()`:
def load(path: Path) -> dict[str, Any]:
    """Read an old file, with its comments as notes.

    Arguments:
    * `path` (`Path`): The file.

    Returns:
    * (`dict[str, Any]`): Its contents.
    """
    text: str = path.read_text(encoding="utf-8")
    data: dict[str, Any] = tomllib.loads(text)
    add_notes(data, comments(text))
    return data


# Function `new_header()`:
def new_header(
    name: str, kind: str, language: str = "English"
) -> dict[str, Any]:
    """Return the header keys of a new item file.

    Arguments:
    * `name` (`str`): The item's name.
    * `kind` (`str`): Its kind.
    * `language` (`str`): Its language.

    Returns:
    * (`dict[str, Any]`): `name`, `kind`, `language`, `version`.
    """
    return {
        "name": name,
        "kind": kind,
        "language": language,
        "version": FORMAT_VERSION,
    }


# Function `write()`:
def write(path: Path, item: dict[str, Any]) -> None:
    """Write one item, and check that it reads back the same.

    Arguments:
    * `path` (`Path`): The file.
    * `item` (`dict[str, Any]`): The item.

    Raises:
    * `ValueError`: If it does not read back the same.
    """
    text: str = item_text(item)
    if tomllib.loads(text) != item:
        raise ValueError(f"{path}: does not read back the same")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")


# Function `named()`:
def named(old: Path, value: str) -> Path:
    """Return the old file an `"@FILE"` string names.

    Arguments:
    * `old` (`Path`): The old shop's directory.
    * `value` (`str`): The string.

    Returns:
    * (`Path`): The file.
    """
    return old / value.removeprefix("@")


# Function `plural_keys()`:
def plural_keys(collection: str) -> dict[str, str]:
    """Return a collection kind's list keys, by the kind they hold.

    Arguments:
    * `collection` (`str`): `tools` or `tooling`.

    Returns:
    * (`dict[str, str]`): E.g. `{"end_mills": "end_mill"}`.
    """
    return {field.key: field.of for field in KINDS[collection].fields}


# Function `convert_machines()`:
def convert_machines(old: Path, new: Path, shop: dict[str, Any]) -> None:
    """Write each machine, holding its tool table, and its controller.

    Arguments:
    * `old` (`Path`): The old shop's directory.
    * `new` (`Path`): The new shop's directory.
    * `shop` (`dict[str, Any]`): The old top file (its `machines`
      taken out).
    """
    machine_file: str
    for machine_file in shop.pop("machines"):
        machine: dict[str, Any] = load(named(old, machine_file))
        controller: dict[str, Any] = load(named(old, machine["controller"]))
        machine["controller"] = controller["name"]
        write(new / "controllers" / slug(controller["name"]), controller)
        table: dict[str, Any] = load(named(old, machine["tool_table"]))
        machine["tool_table"] = {
            key: value
            for key, value in table.items()
            if key not in ("name", "kind", "language", "version")
        }
        write(new / "machines" / slug(machine["name"]), machine)


# Function `convert_collection()`:
def convert_collection(
    old: Path, new: Path, shop: dict[str, Any], collection: str
) -> None:
    """Write each tool, or each piece of tooling, in a file of its own.

    A tools file's comments are about the shop's tools, so they go in
    the shop's notes; a tooling file's, in each piece's.

    Arguments:
    * `old` (`Path`): The old shop's directory.
    * `new` (`Path`): The new shop's directory.
    * `shop` (`dict[str, Any]`): The old top file (`collection` taken
      out).
    * `collection` (`str`): `tools` or `tooling`.
    """
    language: str = str(shop.get("language", "English"))
    collection_file: str
    for collection_file in shop.pop(collection, []):
        whole: dict[str, Any] = load(named(old, collection_file))
        notes: str = str(whole.get("notes", ""))
        if notes and collection == "tools":
            shop["notes"] = f"{shop.get('notes', '')} {notes}".strip()
        key: str
        kind: str
        for key, kind in plural_keys(collection).items():
            entry: dict[str, Any]
            for entry in whole.get(key, []):
                item: dict[str, Any] = new_header(
                    entry["name"], kind, language
                )
                item.update(entry)
                if notes and collection == "tooling":
                    item["notes"] = f"{notes} {item.get('notes', '')}".strip()
                write(new / collection / slug(entry["name"]), item)


# Function `convert()`:
def convert(top: Path, new: Path) -> None:
    """Convert one shop.

    Arguments:
    * `top` (`Path`): The old shop's top file.
    * `new` (`Path`): The new shop's directory.
    """
    old: Path = top.parent
    shop: dict[str, Any] = load(top)
    convert_machines(old, new, shop)
    convert_collection(old, new, shop, "tools")
    convert_collection(old, new, shop, "tooling")

    # The materials: the cutting data, and one file per material.
    materials: dict[str, Any] = load(named(old, shop.pop("materials")))
    material: dict[str, Any]
    for material in materials.pop("materials"):
        item: dict[str, Any] = new_header(
            material["name"], "material", str(shop.get("language", "English"))
        )
        item.update(material)
        write(new / "materials" / slug(material["name"]), item)
    materials["name"] = "Cutting data"
    write(new / "materials" / "cutting_data.toml", materials)

    # The shop itself.
    write(new / "shop.toml", shop)


if __name__ == "__main__":
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
