# The `scraftcam` GUI

One GUI for the shop, the designs and the machines.  It is being
built a step at a time (`TASKS/5.1.9_...`); this file grows with it.
So far: the top line (step 1).

## Starting It

From the repository's top directory:

```
python3 -m scraftcam.run [--shop=SHOP] [--design=DESIGN] [--port=PORT]
```

or, from anywhere (not on Windows), `scraftcam/run.py` with the same
arguments.

* `--shop`: the shop's `shop.toml`, or its directory.  With none, the
  first `shop.toml` in the current directory or one of its parents is
  used, as `git` finds its repository.
* `--design`: the design, a Python file or a package directory.
* `--port`: a command port on 127.0.0.1 (see below); none by default.
* `--headless`: Qt draws offscreen, so no display is needed (tests).

`PySide6` (Qt) is fetched into `~/.scraftcam/packages/` the first time.

## The Window

From the top down:

* **The top line**, left to right:
  * [Stop All]: only while more than one machine runs; stops them all.
  * [Tree]: shows or hides the tree on the left (empty until step 2).
  * The shop's name (its `name`, else its directory's) and the
    design's name; "(none)" when there is none.
  * The latest message; red for a problem.
  * [+ Panel]: adds a panel on the right.
  * [x] (narrow, to save room): closes the window.  A window that
    controls a running machine will not close ("Stop the shop mill
    first").
* **The action rows**: what can be done to the item selected.  For
  now only "No shop yet: [New Shop]".
* **The panels**, side by side; drag the splitters between them.

The window starts small (720 x 480), so SolidCraft fits beside it.

## A New Shop

With no shop, [New Shop] (which also opens by itself when the GUI
starts) asks:

* the directory (`shop/` under the current directory by default),
* the shop's name, with [Create] beside it (grey until there is a
  name; Enter presses it),
* its units: Imperial (in) or Metric (mm),
* which machines it has: computer controlled ones, then manual ones
  used for prep work (only the CNC mill can be driven so far).  More
  than one machine of a kind is entered later, with the shop's
  machines.

[Create] writes the directory's `shop.toml`; it never writes over an
existing one.  The shop is yours: keep it under version control.  When
it is not in a `git` or `hg` repository, the top line suggests one
(or says to install `git` or `hg`).

## The Command Port

With `--port`, each line sent is one JSON request, shaped like
JSON-RPC 2.0, and each answer is one JSON line, with `result` or
`error`:

```
echo '{"id": 1, "method": "status"}' | nc -q 1 127.0.0.1 5010
```

| Method | `params` | Does |
| --- | --- | --- |
| `status` | none | What the windows show. |
| `press` | `button`, `window` (from 0) | Presses a top line or action row button, as a person would; refused if it is hidden. |
| `new_shop` | `directory`, `name`, `units`, `machines` | Makes a shop, as [New Shop] would. |
| `quit` | none | Closes every window, unless one refuses. |

## The Code

* `app.py`: the model, with no Qt: what every window shows.
* `window.py`: the windows, the new shop dialog and the command port.
* `port.py`: the command port's requests and answers, with no Qt.
* `../run.py`: the command line.
