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

With `--program`, the first panel controls the machine (step 5,
`T.osiade~5.1.9` #52, #53): the HMI (`scraftcam.hmi.lcnc_hmi`), a
client of a `serve_linuxcnc` already running (`--lcnc-port`), opens
the program, stopped; it answers its own line commands on
`--hmi-port`, and draws the program's setup in the SolidCraft on
`--solidcraft`.  Nothing closes while the machine runs or its
spindle is on (#56):

```
python3 -m scraftcam.run --shop examples/shop --program demo.ngc \
    --hmi-port 5007 --solidcraft 8080
```
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

# Run as a script, Python puts `scraftcam/` on `sys.path`, not the
# directory above it, so that one is added (#103).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from scraftcam.gui import window
from scraftcam.gui.app import App, find_shop
from scraftcam.gui.views import MachineControl
from scraftcam.lcnc.lcnc_client import PORT as LINUXCNC_PORT
from scraftcam.shops import SHOP_FILE

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
    parser.add_argument("--program", default="", help="G-code to run")
    parser.add_argument(
        "--hmi-port", type=int, default=0, help="HMI line port (0: none)"
    )
    parser.add_argument(
        "--solidcraft", type=int, default=0, help="SolidCraft port"
    )
    parser.add_argument(
        "--lcnc-port",
        type=int,
        default=LINUXCNC_PORT,
        help="serve_linuxcnc's port (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="use no LinuxCNC"
    )
    options: argparse.Namespace = parser.parse_args(arguments)

    # The model, and a shop that was named but is not there.
    design: Path | None = Path(options.design) if options.design else None
    model: App = App(shop_file(options.shop), design)
    if options.shop and model.shop is None:
        model.say(f"No {SHOP_FILE} at {options.shop}.", problem=True)

    # Qt, then the first window, until the last one closes.
    return window.run(
        model,
        headless=options.headless,
        command_port=options.port,
        machine=machine_maker(model, options) if options.program else None,
    )


# Function `machine_maker()`:
def machine_maker(
    model: App, options: argparse.Namespace
) -> Callable[[], MachineControl | None]:
    """Return what makes the machine's controls, once Qt is up.

    Arguments:
    * `model` (`App`): The GUI's model, for its shop and messages.
    * `options` (`argparse.Namespace`): The command line.

    Returns:
    * (`Callable[[], MachineControl | None]`): Makes the HMI, with
      the program open; on failure, says why and gives `None`.
    """

    # Function `make()`:
    def make() -> MachineControl | None:
        """Make the HMI, with the program open."""
        # Only now: it needs LinuxCNC's client, which the GUI does not.
        # pylint: disable-next=import-outside-toplevel
        from scraftcam.hmi import lcnc_hmi

        if model.shop is None:
            model.say("--program needs a shop", problem=True)
            return None
        if options.headless:
            lcnc_hmi.use_headless()
        try:
            hmi: lcnc_hmi.HMI = lcnc_hmi.make_hmi(
                port=options.hmi_port,
                lcnc_port=options.lcnc_port,
                solidcraft=options.solidcraft,
                shop=model.shop,
                dry_run=options.dry_run,
            )
        except lcnc_hmi.HMIStartError as error:
            model.say(f"The machine did not start: {error}", problem=True)
            return None
        hmi.quit_button.hide()
        try:
            hmi.open(options.program)
        except (ValueError, OSError) as error:
            hmi.message.setText(str(error))
        return MachineControl(
            hmi.program_machine or "Machine", hmi, hmi.busy, hmi.on_stop
        )

    return make


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
