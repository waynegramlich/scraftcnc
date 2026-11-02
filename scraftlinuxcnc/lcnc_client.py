"""Talk to `lcnc_bridge.py`, from any Python on this computer.

It needs only the standard library, so it runs on the host (Linux or
Windows), outside the target that LinuxCNC is in:

```python
with SCClient() as lcnc:
    lcnc.call("command.state", constant("STATE_ESTOP_RESET"))
    print(lcnc.stat("task_state"))
```
"""

import json
import socket
from types import TracebackType
from typing import Any, Self

from scraftlinuxcnc.lcnc_bridge import PORT


# Class `SCBridgeError`:
class SCBridgeError(Exception):
    """The bridge answered a request with an error.

    Attributes:
    * `kind` (`str`): The name of the exception in the bridge.
    """

    # Method `SCBridgeError.__init__()`:
    def __init__(self, kind: str, message: str) -> None:
        """Keep what the bridge said.

        Arguments:
        * `kind` (`str`): The name of the exception in the bridge.
        * `message` (`str`): Its message.
        """
        super().__init__(f"{kind}: {message}")
        self.kind: str = kind


# Function `constant()`:
def constant(name: str) -> dict[str, str]:
    """Return the argument that stands for a `linuxcnc` constant.

    Arguments:
    * `name` (`str`): Its name (e.g. `MODE_MDI`).

    Returns:
    * (`dict[str, str]`): The argument for `SCClient.call()`.
    """
    return {"constant": name}


# Class `SCClient`:
class SCClient:
    """One connection to `lcnc_bridge.py`.

    Attributes:
    * `connection` (`socket.socket`): The connection.
    * `lines` (`Any`): The file that reads its replies.
    * `next_id` (`int`): The next request's `id`.
    """

    # Method `SCClient.__init__()`:
    def __init__(
        self, host: str = "localhost", port: int = PORT, timeout: float = 60.0
    ) -> None:
        """Connect to the bridge.

        Arguments:
        * `host` (`str`): The computer it is on.
        * `port` (`int`): Its port.
        * `timeout` (`float`): How long to wait for a reply (seconds).

        Raises:
        * `OSError`: If it can not be reached.
        """
        self.connection: socket.socket = socket.create_connection(
            (host, port), timeout
        )
        self.lines: Any = self.connection.makefile("rb")
        self.next_id: int = 1

    # Method `SCClient.__enter__()`:
    def __enter__(self) -> Self:
        """Start a `with` block.

        Returns:
        * (`Self`): This connection.
        """
        return self

    # Method `SCClient.__exit__()`:
    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Close the connection at the end of a `with` block."""
        self.close()

    # Method `SCClient.close()`:
    def close(self) -> None:
        """Close the connection."""
        self.lines.close()
        self.connection.close()

    # Method `SCClient.call()`:
    def call(self, name: str, *args: Any) -> Any:
        """Send one request and wait for its reply.

        Arguments:
        * `name` (`str`): The call (e.g. `command.mdi`).
        * `args` (`Any`): Its arguments.

        Returns:
        * (`Any`): The call's result.

        Raises:
        * `SCBridgeError`: If the bridge answered with an error.
        * `ConnectionError`: If the connection closed first.
        """
        # Send it.
        request_id: int = self.next_id
        self.next_id += 1
        request: dict[str, Any] = {
            "id": request_id,
            "call": name,
            "args": list(args),
        }
        self.connection.sendall(f"{json.dumps(request)}\n".encode())

        # Read its reply.
        line: bytes = self.lines.readline()
        if not line:
            raise ConnectionError("The bridge closed the connection.")
        reply: dict[str, Any] = json.loads(line)
        if "error" in reply:
            error: dict[str, str] = reply["error"]
            raise SCBridgeError(error["type"], error["message"])
        return reply["result"]

    # Method `SCClient.stat()`:
    def stat(self, *names: str) -> dict[str, Any]:
        """Read `linuxcnc.stat`.

        Arguments:
        * `names` (`str`): The attributes to read; none means all.

        Returns:
        * (`dict[str, Any]`): Their values, by name.
        """
        result: dict[str, Any] = self.call(
            "stat", *([list(names)] if names else [])
        )
        return result
