"""The GUI's command port: one JSON line in, one JSON line out.

Each request is one line of JSON, shaped like JSON-RPC 2.0
(`T.osiade~5.1.9` #110), so that an MCP server can wrap the port
later (#86):

```
{"jsonrpc": "2.0", "id": 1, "method": "press", "params": {"button": "Tree"}}
{"jsonrpc": "2.0", "id": 1, "result": "pressed Tree"}
```

A failure answers `error` (`code` and `message`) in place of
`result`.  This module has no Qt in it: `reply()` turns a request
line into its answer line, given the methods; `window.py` has the
methods and listens on the port (`--port`, on 127.0.0.1 only).
"""

import json
from collections.abc import Callable

# JSON-RPC 2.0's error codes, and one of our own for a refused request.
PARSE_ERROR: int = -32700
INVALID_REQUEST: int = -32600
METHOD_NOT_FOUND: int = -32601
INVALID_PARAMS: int = -32602
REFUSED: int = -32000

# A method of the port: its parameters in, its result out.
Method = Callable[[dict[str, object]], object]


# Class `PortError`:
class PortError(Exception):
    """A request the port refuses, with its JSON-RPC error code.

    Attributes:
    * `code` (`int`): The error code, `REFUSED` unless given.
    * `identifier` (`object`): The request's `id`, if known here.
    """

    def __init__(
        self, message: str, code: int = REFUSED, identifier: object = None
    ) -> None:
        """Make the error.

        Arguments:
        * `message` (`str`): What went wrong, one line.
        * `code` (`int`): The JSON-RPC error code.
        * `identifier` (`object`): The request's `id`, if known here.
        """
        super().__init__(message)
        self.code: int = code
        self.identifier: object = identifier


# Function `answer()`:
def answer(identifier: object, result: object) -> str:
    """Return a result's line.

    Arguments:
    * `identifier` (`object`): The request's `id`.
    * `result` (`object`): The result (anything JSON can hold).

    Returns:
    * (`str`): One line of JSON, with no newline.
    """
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result})


# Function `failure()`:
def failure(identifier: object, code: int, message: str) -> str:
    """Return an error's line.

    Arguments:
    * `identifier` (`object`): The request's `id` (None if unknown).
    * `code` (`int`): The JSON-RPC error code.
    * `message` (`str`): What went wrong.

    Returns:
    * (`str`): One line of JSON, with no newline.
    """
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": identifier,
            "error": {"code": code, "message": message},
        }
    )


# Function `text_param()`:
def text_param(params: dict[str, object], name: str) -> str:
    """Return a parameter that must be a string.

    Arguments:
    * `params` (`dict[str, object]`): The request's parameters.
    * `name` (`str`): The parameter's name.

    Returns:
    * (`str`): Its value.

    Raises:
    * `PortError`: If it is missing or not a string.
    """
    value: object = params.get(name)
    if not isinstance(value, str):
        raise PortError(f"`{name}` must be a string", INVALID_PARAMS)
    return value


# Function `parse()`:
def parse(
    line: str, methods: dict[str, Method]
) -> tuple[object, str, dict[str, object]]:
    """Read a request line.

    Arguments:
    * `line` (`str`): The request, one line of JSON.
    * `methods` (`dict[str, Method]`): The methods, by name.

    Returns:
    * (`tuple[object, str, dict[str, object]]`): Its `id`, method
      and parameters.

    Raises:
    * `PortError`: If it is not a request for one of `methods`.
    """
    # The line must be a JSON object.
    try:
        request: object = json.loads(line)
    except json.JSONDecodeError as error:
        raise PortError(f"not JSON: {error}", PARSE_ERROR) from error
    if not isinstance(request, dict):
        raise PortError("not a JSON object", INVALID_REQUEST)

    # Its method and parameters.
    identifier: object = request.get("id")
    name: object = request.get("method")
    params: object = request.get("params", {})
    if not isinstance(name, str):
        raise PortError("no `method`", INVALID_REQUEST, identifier)
    if name not in methods:
        raise PortError(
            f"no method `{name}`; there are: {', '.join(sorted(methods))}",
            METHOD_NOT_FOUND,
            identifier,
        )
    if not isinstance(params, dict):
        raise PortError("`params` not an object", INVALID_PARAMS, identifier)
    return identifier, name, params


# Function `reply()`:
def reply(line: str, methods: dict[str, Method]) -> str:
    """Answer one request line.

    Arguments:
    * `line` (`str`): The request, one line of JSON.
    * `methods` (`dict[str, Method]`): The methods, by name.

    Returns:
    * (`str`): The answer, one line of JSON, with no newline.
    """
    identifier: object = None
    try:
        identifier, name, params = parse(line, methods)
        return answer(identifier, methods[name](params))
    except PortError as error:
        return failure(
            identifier if error.identifier is None else error.identifier,
            error.code,
            str(error),
        )
