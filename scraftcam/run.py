#!/usr/bin/env python3
"""Start the `scraftcam` GUI (`T.osiade~5.1.9`).

```
python3 -m scraftcam.run [--shop=SHOP] [--design=DESIGN] [--port=PORT]
./scraftcam/run.py [--shop=SHOP] [--design=DESIGN] [--port=PORT]
```

`SHOP` is a shop's `shop.toml` or its directory; with none, the first
`shop.toml` in the current directory or one of its parents is used
(#83).  `DESIGN` is a Python file, or a package directory.  With
`--headless`, Qt draws offscreen, so no display is needed.  With
`--port`, the GUI answers commands on that port of 127.0.0.1, one
JSON line in, one out (`scraftcam/gui/port.py`):

```
echo '{"id": 1, "method": "status"}' | nc -q 1 127.0.0.1 5010
```
"""

import argparse
import sys
from pathlib import Path

# Run as a script, Python puts `scraftcam/` on `sys.path`, not the
# directory above it, so that one is added (#103).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from scraftcam.gui import window
from scraftcam.gui.app import SHOP_FILE, App, find_shop

# pylint: enable=wrong-import-position


# Function `shop_file()`:
def shop_file(shop: str) -> Path | None:
    """Find the shop's `shop.toml` from `--shop`, or from here (#83).

    Arguments:
    * `shop` (`str`): `--shop`: a file, a directory, or "".

    Returns:
    * (`Path | None`): The `shop.toml`, or None when there is none.
    """
    if not shop:
        return find_shop(Path.cwd())
    path: Path = Path(shop)
    if path.is_dir():
        path = path / SHOP_FILE
    return path.resolve() if path.is_file() else None


# Function `main()`:
def main(arguments: list[str]) -> int:
    """Start the GUI, and run it until its last window closes.

    Arguments:
    * `arguments` (`list[str]`): The command line, less the program.

    Returns:
    * (`int`): 0 when the GUI closed normally.
    """
    # The command line.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="scraftcam", description="The scraftcam GUI."
    )
    parser.add_argument("--shop", default="", help="shop.toml or its dir")
    parser.add_argument("--design", default="", help="design .py or dir")
    parser.add_argument(
        "--headless", action="store_true", help="draw offscreen"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="command port (0: none)"
    )
    options: argparse.Namespace = parser.parse_args(arguments)

    # The model, and a shop that was named but is not there.
    design: Path | None = Path(options.design) if options.design else None
    model: App = App(shop_file(options.shop), design)
    if options.shop and model.shop is None:
        model.say(f"No {SHOP_FILE} at {options.shop}.", problem=True)

    # Qt, then the first window, until the last one closes.
    return window.run(
        model, headless=options.headless, command_port=options.port
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
