#!/usr/bin/env python3
"""Generate the command classes of `scraftpybind.py`.

SolidCraft describes each of its commands (`solidcraft-cli commands`):
its id, its label and a free-text `params` description.  The few
commands that have been given a typed contract also have a JSON Schema
of their parameters (`engine.describe`).  This program fetches both,
keeps them in `scraftpybind_commands.json`, and rewrites the generated
region of `scraftpybind.py`: one class per namespace
(`SketchCommands` for `sketch.*`), with one method per command.

A command with a schema gets its parameters, types and required
parameters from the schema.  The others get their parameter names from
the free text, and a type only where the text is clear about it (`bool`,
`expr`, `[x,y]`, `a|b|c`, ...); every other parameter is `JSON`, and
every parameter is optional.  Since the text can hide a parameter
(`path | data`), every method also takes `**extra`, which it sends as
it is.

```
./scraftpybind_generate.py            # Fetch from `solidcraft-cli`.
./scraftpybind_generate.py --cached   # Use the kept JSON.
```
"""

# The generator is one long, plain pass over the command list; its
# size limits are not worth splitting it for.
# pylint: disable=too-many-lines,too-many-locals
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-return-statements

import argparse
import json
import keyword
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

# A JSON value, as `json.loads` returns it.  (The name is all capitals,
# not `pylint`'s `T`-prefixed type alias style.)
JSON: TypeAlias = (  # pylint: disable=invalid-name
    dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
)

# Where things are, relative to this program.
HERE: Path = Path(__file__).resolve().parent
TARGET: Path = HERE / "scraftpybind.py"
CACHE: Path = HERE / "scraftpybind_commands.json"
# The `solidcraft-cli` program, looked up on the `PATH` (as
# `scraftpybind.SCHeadlessTransport` does) unless `--cli` names another.
DEFAULT_CLI: str = "solidcraft-cli"

# The lines that bracket the generated region of `scraftpybind.py`.
BEGIN: str = "# Begin the generated command classes."
END: str = "# End the generated command classes."

# Where the parameters end and the description of the result starts.
RESULT_START: re.Pattern[str] = re.compile(r"(→|\bReturns?\b)")

# A sentence about the result, inside the parameters: `... . Returns`.
SENTENCE_RETURNS: re.Pattern[str] = re.compile(r"(?<=[.)])\s+(?=Returns?\b)")

# A parameter segment: `name`, `name?`, or `name?: description`.
SEGMENT: re.Pattern[str] = re.compile(
    r"^([a-z_][a-z0-9_]*)(\?)?\s*(?::(?!:)\s*(.*))?$", re.DOTALL
)

# A split point inside a segment: ` | name:` or ` or name:`.
ALTERNATIVE: re.Pattern[str] = re.compile(
    r"\s+(?:\||or)\s+(?=[a-z_][a-z0-9_]*\??\s*:(?!:))"
)

# An enumeration in the free text, such as `csv|json`.
ENUM: re.Pattern[str] = re.compile(r"^([A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+)+)")

# Words of the free text that name a type clearly enough to use it.
TEXT_TYPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^bool\b"), "bool"),
    (re.compile(r"^(?:angle |length )?expr\b"), "Expr"),
    (re.compile(r"^(?:mm|deg)\b(?![³²])"), "Expr"),
    (re.compile(r"^number\b"), "float"),
    (re.compile(r"^\[x,\s*y\](?=\s|$)"), "Point2D"),
    (re.compile(r"^\[x,\s*y,\s*z\](?=\s|$)"), "Point3D"),
)

# Names that the methods themselves need.
RESERVED: frozenset[str] = frozenset({"self", "extra"})

# Schema definitions with a type of their own in `scraftpybind.py`.
SCHEMA_REFS: dict[str, str] = {
    "AngleExpr": "Expr",
    "LengthExpr": "Expr",
    "Point2": "Point2D",
    "Point3": "Point3D",
    "PointExpr3": "Sequence[Expr]",
    "StringList": "Sequence[str]",
}


# Class `Param`:
@dataclass(slots=True)
class Param:
    """One parameter of one command.

    Attributes:
    * `key` (`str`): The parameter's JSON key (e.g. `from`).
    * `name` (`str`): Its Python name (e.g. `from_`).
    * `hint` (`str`): Its Python type hint, without `| None`.
    * `required` (`bool`): True when it must be given.
    * `doc` (`str`): What it is, in SolidCraft's words.

    Constructor:
    * `Param(key, name, hint, required, doc)`
    """

    # Constructor arguments:
    key: str = field(init=True)
    name: str = field(init=True)
    hint: str = field(init=True)
    required: bool = field(init=True)
    doc: str = field(init=True)


# Class `Command`:
@dataclass(slots=True)
class Command:
    """One SolidCraft command, ready to become one method.

    Attributes:
    * `id` (`str`): The command id (e.g. `sketch.rectangle.center`).
    * `label` (`str`): Its label (e.g. `Center Rectangle`).
    * `namespace` (`str`): The first part of the id (e.g. `sketch`).
    * `method` (`str`): The method's name (e.g. `rectangle_center`).
    * `params` (`list[Param]`): Its parameters.
    * `positional` (`bool`):
      True when its required parameters come first, positionally
      (only for a command with a schema, whose required parameters
      are known).
    * `notes` (`str`): Free text that names no parameter.
    * `result` (`str`): What it returns, in SolidCraft's words.

    Constructor:
    * `Command(id, label, namespace, method, params, positional, notes,
      result)`
    """

    # Constructor arguments:
    id: str = field(init=True)
    label: str = field(init=True)
    namespace: str = field(init=True)
    method: str = field(init=True)
    params: list[Param] = field(init=True)
    positional: bool = field(init=True)
    notes: str = field(init=True)
    result: str = field(init=True)


# Function `python_name()`:
def python_name(name: str, taken: frozenset[str] = frozenset()) -> str:
    """Turn a SolidCraft name into a usable Python name.

    Arguments:
    * `name` (`str`): The name (e.g. `from`, `two-point`).
    * `taken` (`frozenset[str]`): Names that must not be used.

    Returns:
    * (`str`): A valid identifier, with `_` added when needed.

    Raises:
    * `ValueError`: If no identifier can be made from `name`.
    """
    # Replace the characters an identifier cannot have.
    result: str = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if result[:1].isdigit():  # pragma: no cover
        result = "_" + result
    if not result.isidentifier():  # pragma: no cover
        raise ValueError(f"{name=} cannot be made an identifier")

    # Keep clear of Python's keywords and the names already taken.
    while keyword.iskeyword(result) or result in taken:
        result += "_"
    return result


# Function `top_level()`:
def top_level(text: str) -> str:
    """Return `text` with everything inside brackets removed.

    Arguments:
    * `text` (`str`): Some free text.

    Returns:
    * (`str`): The text outside every `()`, `[]` and `{}`.
    """
    # Keep only the characters at bracket depth 0.
    depth: int = 0
    kept: list[str] = []
    character: str
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0:
            kept.append(character)
    return "".join(kept)


# Function `split_segments()`:
def split_segments(text: str) -> list[tuple[str, str]]:
    """Split parameter text at the `;` and `,` outside brackets.

    A piece is split again at a ` | name:` or ` or name:` outside
    brackets, which starts another parameter.

    Arguments:
    * `text` (`str`): A command's parameter text.

    Returns:
    * (`list[tuple[str, str]]`):
      Each stripped piece (empty ones left out) with the separator
      that followed it (`;`, `,`, `|`, `or`, or "" at the end).
    """
    # Split at the `;` and `,` at bracket depth 0.
    pieces: list[tuple[str, str]] = []
    depth: int = 0
    current: list[str] = []
    character: str
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        if depth == 0 and character in ";,":
            pieces.append(("".join(current), character))
            current = []
        else:
            current.append(character)
    pieces.append(("".join(current), ""))

    # Split again at the alternatives that start another parameter,
    # where they are outside brackets.
    segments: list[tuple[str, str]] = []
    piece: str
    separator: str
    for piece, separator in pieces:
        start: int = 0
        match: re.Match[str]
        for match in ALTERNATIVE.finditer(piece):
            if not open_brackets(piece[: match.start()]):
                segments.append(
                    (piece[start : match.start()], match.group().strip())
                )
                start = match.end()
        segments.append((piece[start:], separator))
    return [(text.strip(), sep) for text, sep in segments if text.strip()]


# Function `open_brackets()`:
def open_brackets(text: str) -> int:
    """Return how many brackets are still open at the end of `text`.

    Arguments:
    * `text` (`str`): Some free text.

    Returns:
    * (`int`): The bracket depth (0 when every bracket is closed).
    """
    # Count the opening and closing brackets, never going below 0.
    depth: int = 0
    character: str
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
    return depth


# Function `text_hint()`:
def text_hint(description: str) -> str:
    """Work out a type hint from a parameter's free-text description.

    Arguments:
    * `description` (`str`): The text after the parameter's `:`.

    Returns:
    * (`str`): A type hint, or `JSON` when the text is not clear.
    """
    # An enumeration such as `csv|json (default csv)`, with no other
    # alternatives after it.
    outside: str = top_level(description)
    enum: re.Match[str] | None = ENUM.match(description)
    if enum is not None:
        rest: str = top_level(description[enum.end() :])
        if "|" not in rest and " or " not in rest:
            values: list[str] = enum.group(1).split("|")
            return "Literal[" + ", ".join(f'"{v}"' for v in values) + "]"
        return "JSON"

    # Anything with alternatives is left as `JSON`.
    if "|" in outside or " or " in outside:
        return "JSON"

    # A word that names the type.
    pattern: re.Pattern[str]
    hint: str
    for pattern, hint in TEXT_TYPES:
        if pattern.match(description):
            return hint
    return "JSON"


# Function `text_command()`:
def text_command(entry: dict[str, JSON]) -> Command:
    """Make a `Command` from its free-text parameter description.

    Arguments:
    * `entry` (`dict[str, JSON]`): One entry of `solidcraft-cli
      commands`.

    Returns:
    * (`Command`): The command, with every parameter optional.
    """
    # Everything after a `→` describes the result, and so does each
    # sentence that starts with `Returns`, which becomes its own
    # segment.
    text: str = str(entry.get("params") or "")
    results: list[str] = []
    arrow: int = text.find("→")
    if arrow >= 0:
        results.append(text[arrow + 1 :].strip())
        text = text[:arrow]
    text = SENTENCE_RETURNS.sub("; ", text)

    # Each segment that starts with a name is a parameter; the others
    # are kept as notes.  A parameter after `or` (or `|`) is one of
    # several alternatives, so it is not required.
    params: list[Param] = []
    notes: list[str] = []
    seen: set[str] = set()
    segment: str
    separator: str
    previous: str = ""
    for segment, separator in split_segments(text):
        alternative: bool = previous in ("or", "|") or segment.startswith(
            "or "
        )
        previous = separator
        if re.match(r"Returns?\b", segment):
            results.insert(len(results) - (arrow >= 0), segment)
            continue
        segment = re.sub(r"^or\s+", "", segment)
        head: str = segment.split(" (")[0].rstrip(".")
        match: re.Match[str] | None = SEGMENT.match(head)
        if match is None or (match.group(3) is None and " " in head):
            notes.append(note(segment, separator))
            continue
        key: str = match.group(1)
        if key in seen:
            notes.append(note(segment, separator))
            continue
        seen.add(key)
        description: str = (
            segment[segment.find(":") + 1 :].strip()
            if (match.group(3) is not None)
            else segment[len(head) :].strip(" .")
        )
        hint: str = (
            text_hint(description) if match.group(3) is not None else "JSON"
        )
        params.append(
            Param(
                key,
                python_name(key, RESERVED),
                hint,
                match.group(2) is None and not alternative,
                description,
            )
        )
    result: str = "; ".join(results)
    joined: str = " ".join(notes).rstrip(";,|").strip()
    return make_command(entry, params, False, joined, result)


# Function `note()`:
def note(segment: str, separator: str) -> str:
    """Return a segment of notes with the separator that followed it.

    Arguments:
    * `segment` (`str`): The segment.
    * `separator` (`str`): What followed it (`;`, `,`, `|`, `or`, "").

    Returns:
    * (`str`): The segment, as it read in the original text.
    """
    if separator in (";", ","):
        return segment + separator
    if separator:
        return f"{segment} {separator}"
    return segment


# Function `schema_hint()`:
def schema_hint(
    schema: JSON, defs: dict[str, JSON], aliases: dict[str, str]
) -> str:
    """Turn a JSON Schema into a Python type hint.

    Arguments:
    * `schema` (`JSON`): The schema of one value.
    * `defs` (`dict[str, JSON]`): The schema's `$defs`.
    * `aliases` (`dict[str, str]`):
      The `Literal` type aliases made so far, by name, which this adds
      to.

    Returns:
    * (`str`): A type hint, without `| None`.
    """
    # Only an object says anything about the type.
    if not isinstance(schema, dict):  # pragma: no cover
        return "JSON"

    # A reference: a type of `scraftpybind.py`'s own, or an enumeration
    # (which gets a type alias), or whatever the definition is.
    ref: JSON = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name: str = ref.removeprefix("#/$defs/")
        if name in SCHEMA_REFS:
            return SCHEMA_REFS[name]
        definition: JSON = defs.get(name)
        if isinstance(definition, dict) and "enum" in definition:
            hint: str = schema_hint(definition, defs, aliases)
            aliases[name] = hint
            return name
        return schema_hint(definition, defs, aliases)

    # An enumeration of strings.
    enum: JSON = schema.get("enum")
    if isinstance(enum, list) and all(isinstance(v, str) for v in enum):
        return "Literal[" + ", ".join(f'"{v}"' for v in enum) + "]"

    # A choice, with `null` taken out (`None` is every default).
    choices: JSON = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(choices, list):
        hints: list[str] = [
            schema_hint(choice, defs, aliases)
            for choice in choices
            if not (isinstance(choice, dict) and choice.get("type") == "null")
        ]
        return " | ".join(dict.fromkeys(hints)) if hints else "JSON"

    # A plain type, or a list of them.
    types: JSON = schema.get("type")
    names: list[str] = (
        [str(t) for t in types if t != "null"]
        if isinstance(types, list)
        else [str(types)]
        if isinstance(types, str)
        else []  # pragma: no cover
    )
    simple: dict[str, str] = {
        "boolean": "bool",
        "integer": "int",
        "number": "float",
        "string": "str",
    }
    if names and all(n in simple for n in names):
        return " | ".join(simple[n] for n in names)
    if names == ["array"]:
        return f"Sequence[{schema_hint(schema.get('items'), defs, aliases)}]"
    return "JSON"


# Function `schema_command()`:
def schema_command(
    entry: dict[str, JSON], schema: dict[str, JSON], aliases: dict[str, str]
) -> Command:
    """Make a `Command` from its parameters' JSON Schema.

    Arguments:
    * `entry` (`dict[str, JSON]`): One entry of `solidcraft-cli
      commands`.
    * `schema` (`dict[str, JSON]`): Its input schema.
    * `aliases` (`dict[str, str]`):
      The type aliases, which this adds to.

    Returns:
    * (`Command`): The command, required parameters first.
    """
    # The definitions, the properties and the required ones.
    defs: JSON = schema.get("$defs")
    defs_map: dict[str, JSON] = defs if isinstance(defs, dict) else {}
    properties: JSON = schema.get("properties")
    properties_map: dict[str, JSON] = (
        properties if isinstance(properties, dict) else {}
    )
    required: JSON = schema.get("required")
    required_keys: list[str] = (
        [str(r) for r in required] if isinstance(required, list) else []
    )

    # One parameter per property, the required ones first in their own
    # order and the rest as the schema lists them.
    order: list[str] = required_keys + [
        key for key in properties_map if key not in required_keys
    ]
    params: list[Param] = []
    key: str
    for key in order:
        prop: JSON = properties_map.get(key)
        doc: str = describe_schema(prop, defs_map)
        params.append(
            Param(
                key,
                python_name(key, RESERVED),
                schema_hint(prop, defs_map, aliases),
                key in required_keys,
                doc,
            )
        )

    # The result is described in the free text.
    text: str = str(entry.get("params") or "")
    found: re.Match[str] | None = RESULT_START.search(text)
    result: str = (
        text[found.start() :].lstrip("→ ").strip() if found is not None else ""
    )
    return make_command(entry, params, True, "", result)


# Function `describe_schema()`:
def describe_schema(schema: JSON, defs: dict[str, JSON]) -> str:
    """Return a schema's description, or its definition's.

    Arguments:
    * `schema` (`JSON`): The schema of one value.
    * `defs` (`dict[str, JSON]`): The schema's `$defs`.

    Returns:
    * (`str`): The description, or "" when there is none.
    """
    # The schema's own description wins.
    if not isinstance(schema, dict):  # pragma: no cover
        return ""
    description: JSON = schema.get("description")
    if isinstance(description, str):
        return description

    # Otherwise the first referenced definition that has one.
    choices: JSON = (  # pragma: no cover
        schema.get("anyOf") or schema.get("oneOf") or [schema]
    )
    choice: JSON
    for choice in (  # pragma: no cover
        choices if isinstance(choices, list) else []
    ):
        if isinstance(choice, dict) and isinstance(choice.get("$ref"), str):
            name: str = str(choice["$ref"]).removeprefix("#/$defs/")
            found: str = describe_schema(defs.get(name), {})
            if found:
                return found
    return ""  # pragma: no cover


# Function `make_command()`:
def make_command(
    entry: dict[str, JSON],
    params: list[Param],
    positional: bool,
    notes: str,
    result: str,
) -> Command:
    """Name a command's namespace and method, and make the `Command`.

    Arguments:
    * `entry` (`dict[str, JSON]`): One entry of `solidcraft-cli
      commands`.
    * `params` (`list[Param]`): Its parameters.
    * `positional` (`bool`): True to put required parameters first.
    * `notes` (`str`): Free text that names no parameter.
    * `result` (`str`): What it returns.

    Returns:
    * (`Command`): The command.

    Raises:
    * `ValueError`: If the id has no namespace.
    """
    # `sketch.rectangle.center` is `Sketch.rectangle_center()`; the
    # names `SCNamespace` itself uses are avoided.
    command_id: str = str(entry["id"])
    parts: list[str] = command_id.split(".")
    if len(parts) < 2:  # pragma: no cover
        raise ValueError(f"{command_id=} has no namespace")
    method: str = python_name(
        "_".join(parts[1:]), frozenset({"execute", "transport"})
    )
    return Command(
        command_id,
        str(entry.get("label") or command_id),
        parts[0],
        method,
        params,
        positional,
        notes,
        result,
    )


# Function `fetch()`:
# Only the live `test_fetch` runs it, since it needs `solidcraft-cli`.
def fetch(cli: str) -> dict[str, JSON]:  # pragma: no cover
    """Fetch the commands, and each command's schemas, from SolidCraft.

    Arguments:
    * `cli` (`str`):
      The `solidcraft-cli` program: a path, or a name on the `PATH`.

    Returns:
    * (`dict[str, JSON]`):
      `commands` (as `solidcraft-cli commands` prints them) and
      `schemas` (each command's input schema, for those that have one).

    Raises:
    * `subprocess.CalledProcessError`: If `solidcraft-cli` fails.
    """
    # The commands.
    listing: str = subprocess.run(
        [cli, "commands"], capture_output=True, check=True, text=True
    ).stdout
    commands: JSON = json.loads(listing)
    assert isinstance(commands, list)

    # Each command's schema, from `engine.describe`.
    schemas: dict[str, JSON] = {}
    entry: JSON
    for entry in commands:
        assert isinstance(entry, dict)
        request: str = json.dumps({"command": entry["id"]})
        described: str = subprocess.run(
            [cli, "exec", "engine.describe", request],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        description: JSON = json.loads(described)
        assert isinstance(description, dict)
        if description.get("input") is not None:
            schemas[str(entry["id"])] = description["input"]
    return {"commands": commands, "schemas": schemas}


# Function `docstring()`:
def docstring(command: Command, indent: str) -> list[str]:
    """Write a method's docstring, one line per list entry.

    Arguments:
    * `command` (`Command`): The command.
    * `indent` (`str`): The method body's indentation.

    Returns:
    * (`list[str]`): The docstring's lines, quotes included.
    """

    # Function `wrap()`:
    def wrap(text: str, first: str, rest: str) -> list[str]:
        """Wrap `text` to 72 columns.

        Arguments:
        * `text` (`str`): The text.
        * `first` (`str`): The first line's prefix.
        * `rest` (`str`): The other lines' prefix.

        Returns:
        * (`list[str]`): The lines.
        """
        safe: str = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        return textwrap.wrap(
            safe,
            width=72,
            initial_indent=first,
            subsequent_indent=rest,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [first.rstrip()]  # pragma: no cover

    # The summary, the command id and the notes.
    label: str = command.label.rstrip(".…")
    lines: list[str] = wrap(f"{label}.", indent + '"""', indent)
    lines.append("")
    lines += wrap(f"`{command.id}`.", indent, indent)
    if command.notes:
        lines.append("")
        lines += wrap(command.notes, indent, indent)

    # One bullet per parameter, then `extra`.
    lines += ["", f"{indent}Arguments:"]
    param: Param
    for param in command.params:
        required: str = "(required) " if param.required else ""
        lines.append(
            f"{indent}* `{param.name}` (`{hint_of(command, param)}`):"
        )
        text: str = required + (param.doc or "See SolidCraft.")
        if param.name != param.key:
            text += f" (sent as `{param.key}`)"
        lines += wrap(text, indent + "  ", indent + "  ")
    lines.append(f"{indent}* `extra` (`JSON`):")
    lines += wrap(
        "Any other parameters, sent as they are.", indent + "  ", indent + "  "
    )

    # What it returns and raises.
    lines += ["", f"{indent}Returns:"]
    lines += wrap(
        f"* (`JSON`): {command.result or 'The command result.'}",
        indent,
        indent + "  ",
    )
    lines += ["", f"{indent}Raises:"]
    lines.append(f"{indent}* `SCSolidCraftError`: If the command fails.")
    lines.append(f'{indent}"""')
    return lines


# Function `hint_of()`:
def hint_of(command: Command, param: Param) -> str:
    """Return a parameter's full type hint.

    Arguments:
    * `command` (`Command`): Its command.
    * `param` (`Param`): The parameter.

    Returns:
    * (`str`): The hint, with `| None` unless it is positional.
    """
    if command.positional and param.required:
        return param.hint
    return f"{param.hint} | None"


# Function `method_lines()`:
def method_lines(command: Command, class_name: str) -> list[str]:
    """Write the method for one command.

    Arguments:
    * `command` (`Command`): The command.
    * `class_name` (`str`): The class the method belongs to.

    Returns:
    * (`list[str]`): The method's lines.
    """
    # The signature: positional required parameters (schema commands
    # only), then keyword-only ones, then `extra`.
    lines: list[str] = [
        f"    # Method `{class_name}.{command.method}()`:",
        f"    def {command.method}(",
        "        self,",
    ]
    param: Param
    keyword_only: bool = False
    for param in command.params:
        hint: str = hint_of(command, param)
        if command.positional and param.required:
            lines.append(f"        {param.name}: {hint},")
            continue
        if not keyword_only:
            lines.append("        *,")
            keyword_only = True
        lines.append(f"        {param.name}: {hint} = None,")
    lines.append("        **extra: JSON,")
    lines.append("    ) -> JSON:")

    # The docstring and the call.
    lines += docstring(command, "        ")
    lines.append("        return self.execute(")
    lines.append(f'            "{command.id}",')
    lines.append("            {")
    for param in command.params:
        lines.append(f'                "{param.key}": {param.name},')
    lines.append("                **extra,")
    lines.append("            },")
    lines.append("        )")
    return lines


# Function `generate()`:
def generate(data: dict[str, JSON]) -> list[str]:
    """Write the generated region of `scraftpybind.py`.

    Arguments:
    * `data` (`dict[str, JSON]`): `commands` and `schemas`, as `fetch`
      returns them.

    Returns:
    * (`list[str]`): The region's lines, its bracketing lines included.
    """
    # Make the commands, from schemas where there are any.
    entries: JSON = data["commands"]
    schemas: JSON = data["schemas"]
    assert isinstance(entries, list) and isinstance(schemas, dict)
    aliases: dict[str, str] = {}
    commands: list[Command] = []
    entry: JSON
    for entry in entries:
        assert isinstance(entry, dict)
        schema: JSON = schemas.get(str(entry["id"]))
        if isinstance(schema, dict):
            commands.append(schema_command(entry, schema, aliases))
        else:
            commands.append(text_command(entry))

    # A `Literal`, or a hint too wide for its docstring bullet, gets a
    # type alias named after its command and parameter.
    comments: dict[str, str] = {
        name: f"The values of `{name}` in SolidCraft's schemas."
        for name in aliases
    }
    command: Command
    param: Param
    for command in commands:
        for param in command.params:
            bullet: str = f"        * `{param.name}` (`{param.hint} | None`):"
            if param.hint.startswith("Literal[") or len(bullet) > 72:
                alias: str = "".join(
                    part.capitalize()
                    for part in re.split(r"[._]", command.id + "." + param.key)
                )
                assert aliases.get(alias, param.hint) == param.hint, alias
                aliases[alias] = param.hint
                comments[alias] = f"The `{param.key}` of `{command.id}`."
                param.hint = alias

    # Group them by namespace, each namespace a class.
    namespaces: dict[str, list[Command]] = {}
    for command in sorted(commands, key=lambda c: c.id):
        namespaces.setdefault(command.namespace, []).append(command)
    class_names: dict[str, str] = {
        namespace: "SC"
        + "".join(
            part.capitalize() for part in python_name(namespace).split("_")
        )
        + "Commands"
        for namespace in namespaces
    }
    taken: set[str] = set(aliases) & set(class_names.values())
    assert not taken, f"type aliases and classes share names: {taken}"

    # The region starts with the type aliases.
    lines: list[str] = [
        BEGIN,
        "# Never edit them: they are written by `scraftpybind_generate.py`.",
        "",
    ]
    name: str
    for name in sorted(aliases):
        lines.append(f"# {comments[name]}")
        lines.append(f"{name}: TypeAlias = {aliases[name]}")
        lines.append("")

    # One class per namespace.
    namespace: str
    for namespace, members in namespaces.items():
        class_name: str = class_names[namespace]
        lines += [
            "",
            f"# Class `{class_name}`:",
            "@dataclass(slots=True)",
            f"class {class_name}(SCNamespace):",
            f'    """The `{namespace}.*` commands.',
            "",
            "    Constructor:",
            f"    * `{class_name}(transport)`",
            '    """',
        ]
        for command in members:
            lines.append("")
            lines += method_lines(command, class_name)
        lines.append("")

    # `SCPyBind`, with one attribute per namespace.
    lines += scraftpybind_lines(class_names)
    lines.append(END)
    return lines


# Function `scraftpybind_lines()`:
def scraftpybind_lines(class_names: dict[str, str]) -> list[str]:
    """Write the `SCPyBind` class.

    Arguments:
    * `class_names` (`dict[str, str]`): Each namespace's class name.

    Returns:
    * (`list[str]`): The class's lines.
    """
    # The class docstring lists every namespace.
    attributes: dict[str, str] = {
        python_name(namespace, frozenset({"transport", "execute"})): (
            class_name
        )
        for namespace, class_name in class_names.items()
    }
    lines: list[str] = [
        "",
        "# Class `SCPyBind`:",
        "@dataclass(slots=True)",
        "class SCPyBind:",
        '    """The top level of `scraftpybind`: SolidCraft\'s commands.',
        "",
        "    The commands are grouped by namespace, so `sketch.create` is",
        "    `SCPyBind.sketch.create()`.",
        "",
        "    Attributes:",
        "    * `transport` (`SCTransport`): How the commands are sent.",
    ]
    attribute: str
    class_name: str
    for attribute, class_name in attributes.items():
        lines.append(f"    * `{attribute}` (`{class_name}`):")
        lines.append(f"      The `{attribute}.*` commands.")
    lines += [
        "",
        "    Constructor:",
        "    * `SCPyBind(transport)`",
        '    """',
        "",
        "    # Constructor arguments:",
        "    transport: SCTransport = field(init=True)",
        "",
        "    # The namespaces, made by `__post_init__()` (alphabetized):",
    ]
    for attribute, class_name in attributes.items():
        lines.append(f"    {attribute}: {class_name} = field(init=False)")

    # `__post_init__()` makes the namespaces.
    lines += [
        "",
        "    # Method `SCPyBind.__post_init__()`:",
        "    def __post_init__(self) -> None:",
        '        """Make the namespaces, all sharing the one transport."""',
    ]
    for attribute, class_name in attributes.items():
        lines.append(
            f"        self.{attribute} = {class_name}(self.transport)"
        )

    # `execute()`, for any command by its id.
    lines += [
        "",
        "    # Method `SCPyBind.execute()`:",
        # A generated line, kept whole so that it can be searched for.
        "    def execute(self, command: str, params: Mapping[str, JSON]) -> JSON:",
        '        """Run any SolidCraft command by its id (`engine.execute`).',
        "",
        "        Arguments:",
        "        * `command` (`str`): The command id (e.g. `sketch.create`).",
        "        * `params` (`Mapping[str, JSON]`):",
        "          The command's parameters; those that are `None` are not",
        "          sent, as for the namespaces' methods.",
        "",
        "        Returns:",
        "        * (`JSON`): The command's result.",
        "",
        "        Raises:",
        "        * `SCSolidCraftError`: If the command fails.",
        '        """',
        "        return SCNamespace(self.transport).execute(command, params)",
        "",
        "",
        "",
    ]
    return lines


# Function `main()`:
def main() -> int:
    """Fetch the commands if asked, and rewrite the generated region.

    Returns:
    * (`int`): The exit status.
    """
    # Read the arguments.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Generate the command classes of `scraftpybind.py`."
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help=f"use {CACHE.name} instead of asking solidcraft-cli",
    )
    parser.add_argument(
        "--cli",
        default=DEFAULT_CLI,
        help="the solidcraft-cli program (default: %(default)s)",
    )
    arguments: argparse.Namespace = parser.parse_args()

    # Fetch the commands (keeping them), or read the kept ones.
    data: JSON
    if arguments.cached:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    else:  # pragma: no cover  (only the live tests fetch)
        data = fetch(arguments.cli)
        CACHE.write_text(
            json.dumps(data, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    assert isinstance(data, dict)

    # Replace the region between the bracketing lines.
    source: list[str] = TARGET.read_text(encoding="utf-8").split("\n")
    begin: int = source.index(BEGIN)
    end: int = source.index(END)
    source[begin : end + 1] = generate(data)
    TARGET.write_text("\n".join(source), encoding="utf-8")

    # Let `ruff format` lay out the long lines.
    subprocess.run(["ruff", "format", "--quiet", str(TARGET)], check=True)
    entries: JSON = data["commands"]
    schemas: JSON = data["schemas"]
    assert isinstance(entries, list) and isinstance(schemas, dict)
    print(
        f"{TARGET.name}: {len(entries)} commands, "
        f"{len(schemas)} of them from schemas"
    )
    return 0


# Run as a program (the tests call `main()` instead).
if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
