#!/usr/bin/env python3
"""JSON Schemas of the shop files, made from `shops.KINDS`.

`shops.KINDS` is the one description of every kind of shop file
(`T.osiade~5.1.9` #129); this writes it as JSON Schema, so that
editors which check TOML against a schema (VS Code's Even Better TOML,
Taplo) check hand edits too.  Each shop file starts with a line naming
its kind's schema (`schema_line()`):

```
#:schema https://raw.githubusercontent.com/.../schemas/end_mill.json
```

`scraftcam/schemas/` holds `shop.schema.json` (every kind, under
`$defs`) and one small file per kind that refers to it.  They are
written from `KINDS`, never by hand, and a test checks that they are
current:

```
python3 -m scraftcam.shop_schema scraftcam/schemas
```

The schemas check less than `shops.read()` does (a choice's capitals,
a tool named in a tool table, a version that is too new), but they
catch most typing mistakes as they are made.
"""

import json
import re
import sys
from pathlib import Path

from .shops import HEADER, KINDS, UNITS, TableField, TableKind

# Where the schemas are published, and where they are in the package.
SCHEMA_URL: str = (
    "https://raw.githubusercontent.com/waynegramlich/scraftcam/main/"
    "scraftcam/schemas/"
)
SCHEMA_DIRECTORY: Path = Path(__file__).resolve().parent / "schemas"

# The file with every kind, under `$defs`.
ALL_KINDS: str = "shop.schema.json"

# A number, as `shops.MEASUREMENT` takes it: a decimal, a fraction, or
# a whole number and a fraction joined by `-`.
NUMBER: str = r"[-+]?(?:(?:\d+-)?\d+/\d+|(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"


# The schemas of the forms that need nothing from their key.
SIMPLE: dict[str, dict[str, object]] = {
    "string": {"type": "string"},
    "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
    "integer": {"type": "integer"},
    "positive_integer": {"type": "integer", "minimum": 1},
    "boolean": {"type": "boolean"},
    "date": {"format": "date"},
    "holder_list": {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 2,
    },
    "t_numbers": {
        "type": "object",
        "propertyNames": {"pattern": r"^\d{1,2}$"},
        "additionalProperties": {"type": "string"},
    },
}


# Function `measurement_pattern()`:
def measurement_pattern(units: dict[str, float]) -> str:
    """Return a pattern for a measurement in one of some units.

    Arguments:
    * `units` (`dict[str, float]`): The units (`shops.UNITS`' values).

    Returns:
    * (`str`): An ECMA 262 pattern, as JSON Schema takes it.
    """
    alternatives: str = "|".join(
        re.escape(unit) for unit in sorted(units, key=len, reverse=True)
    )
    return rf"^\s*{NUMBER}\s*(?:{alternatives})\s*$"


# Function `field_schema()`:
def field_schema(schema: TableField) -> dict[str, object]:
    """Return the JSON Schema of one key's value.

    Arguments:
    * `schema` (`TableField`): The key.

    Returns:
    * (`dict[str, object]`): Its schema, with its meaning as the
      description.
    """
    form: str = schema.form
    value: dict[str, object]
    if form in UNITS:
        value = {"type": "string", "pattern": measurement_pattern(UNITS[form])}
    elif form in SIMPLE:
        value = dict(SIMPLE[form])
    elif form == "choice":
        value = {"type": "string", "examples": list(schema.choices)}
    elif form == "choice_list":
        value = {
            "type": "array",
            "items": {"type": "string", "examples": list(schema.choices)},
        }
    elif form == "table":
        value = reference(schema.of)
    elif form == "list":
        value = {"type": "array", "items": reference(schema.of)}
    elif form == "by_material":
        value = {
            "type": "object",
            "additionalProperties": reference(schema.of),
        }
    else:
        raise ValueError(f"{schema.key}: no schema for form {form!r}")
    meaning: str = schema.meaning
    if form in ("choice", "choice_list"):
        meaning += "  One of: " + ", ".join(schema.choices) + "."
    return {"description": meaning, **value}


# Function `reference()`:
def reference(kind: str) -> dict[str, object]:
    """Return a reference to a kind's schema.

    A table may also be given by name (a machine's controller, in the
    shop's `controllers/` directory), so a string is taken too.

    Arguments:
    * `kind` (`str`): The kind.

    Returns:
    * (`dict[str, object]`): The reference.
    """
    return {"anyOf": [{"$ref": f"#/$defs/{kind}"}, {"type": "string"}]}


# Function `kind_schema()`:
def kind_schema(kind: TableKind) -> dict[str, object]:
    """Return the JSON Schema of one kind of table.

    Arguments:
    * `kind` (`TableKind`): The kind.

    Returns:
    * (`dict[str, object]`): Its schema.
    """
    properties: dict[str, object] = {
        schema.key: field_schema(schema) for schema in HEADER + kind.fields
    }
    properties["kind"] = {
        "description": "What the rest of the file is.",
        "const": kind.kind,
    }
    required: list[str] = [
        schema.key for schema in kind.fields if schema.required
    ]
    return {
        "description": kind.summary,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# Function `schemas()`:
def schemas() -> dict[str, str]:
    """Return every schema file's text, by its name.

    Returns:
    * (`dict[str, str]`): `ALL_KINDS`, and `KIND.json` per kind.
    """
    every: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_URL + ALL_KINDS,
        "title": "scraftcam shop files",
        "$defs": {name: kind_schema(kind) for name, kind in KINDS.items()},
    }
    texts: dict[str, str] = {ALL_KINDS: json.dumps(every, indent=2) + "\n"}
    name: str
    for name in KINDS:
        one: dict[str, object] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": SCHEMA_URL + f"{name}.json",
            "title": f"scraftcam `{name}` file",
            "$ref": f"{ALL_KINDS}#/$defs/{name}",
        }
        texts[f"{name}.json"] = json.dumps(one, indent=2) + "\n"
    return texts


# Function `schema_line()`:
def schema_line(kind: str) -> str:
    """Return the first line of a shop file of a kind.

    Arguments:
    * `kind` (`str`): The kind (a key of `KINDS`).

    Returns:
    * (`str`): `#:schema URL`, with no newline.
    """
    return f"#:schema {SCHEMA_URL}{kind}.json"


# Function `write()`:
def write(directory: Path) -> list[Path]:
    """Write every schema file, and remove those of kinds now gone.

    Arguments:
    * `directory` (`Path`): Where (`SCHEMA_DIRECTORY`).

    Returns:
    * (`list[Path]`): The files written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = schemas()
    old: Path
    for old in directory.glob("*.json"):
        if old.name not in texts:
            old.unlink()
    written: list[Path] = []
    name: str
    text: str
    for name, text in texts.items():
        path: Path = directory / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Write the schemas into a directory (default `SCHEMA_DIRECTORY`).

    Arguments:
    * `arguments` (`list[str]`): The command line, less the program.

    Returns:
    * (`int`): 0.
    """
    directory: Path = Path(arguments[0]) if arguments else SCHEMA_DIRECTORY
    print(f"Wrote {len(write(directory))} schemas into {directory}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
