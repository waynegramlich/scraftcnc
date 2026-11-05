"""The parts of `tkinter` that `lcnc_hmi.py` uses, with no display.

`lcnc_hmi.py --headless` builds its window from these, in place of
`tkinter`, `ttk`, `filedialog` and `messagebox`, so the same code runs
as with a real window, and tests can press its buttons through its
command port.  Each widget keeps its options and its contents, and
behaves as the real one does where the panel depends on that: a
disabled button does nothing, and a disabled `Text` ignores changes.
Nothing is drawn, so layout options are kept but mean nothing.

A question that would open a window takes its answer from `ANSWERS`,
in order, or else the answer that does nothing (No, or no file), and
is added to `ASKED`.
"""

import heapq
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

# The answers waiting for questions, and the questions asked.
ANSWERS: list[str] = []
ASKED: list[str] = []


# Function `_next_answer()`:
def _next_answer(question: str) -> str:
    """Record a question, and return its answer.

    Arguments:
    * `question` (`str`): The question.

    Returns:
    * (`str`): The next of `ANSWERS`, or `""` when there is none.
    """
    ASKED.append(question)
    return ANSWERS.pop(0) if ANSWERS else ""


# Function `askyesno()`:
def askyesno(title: str, message: str, **_options: Any) -> bool:
    """Stand in for `messagebox.askyesno()`.

    Arguments:
    * `title` (`str`): The window's title.
    * `message` (`str`): The question.

    Returns:
    * (`bool`): True when the answer waiting is `yes`.
    """
    return _next_answer(f"{title}: {message}") == "yes"


# Function `askchoice()`:
def askchoice(title: str, message: str, choices: list[str]) -> str:
    """Stand in for the panel's list window: pick one of the choices.

    Arguments:
    * `title` (`str`): The window's title.
    * `message` (`str`): The question.
    * `choices` (`list[str]`): What may be picked.

    Returns:
    * (`str`): The answer waiting, when it is one of the choices,
      else `""` (as Cancel).
    """
    answer: str = _next_answer(f"{title}: {message}")
    return answer if answer in choices else ""


# Function `showerror()`:
def showerror(title: str, message: str) -> None:
    """Stand in for `messagebox.showerror()`.

    Arguments:
    * `title` (`str`): The window's title.
    * `message` (`str`): The message.
    """
    ASKED.append(f"{title}: {message}")


# Function `askopenfilename()`:
def askopenfilename(**options: Any) -> str:
    """Stand in for `filedialog.askopenfilename()`.

    Arguments:
    * `options` (`Any`): Its options; `title` is used.

    Returns:
    * (`str`): The answer waiting, or `""` for none chosen.
    """
    return _next_answer(str(options.get("title", "")))


# Class `StringVar`:
class StringVar:
    """Stands in for `tkinter.StringVar` and `tkinter.DoubleVar`.

    Attributes:
    * `traces` (`list[Callable[..., object]]`): Called on each `set()`.
    * `value` (`Any`): The value.
    """

    # Method `StringVar.__init__()`:
    def __init__(self, value: Any = "") -> None:
        """Hold a value.

        Arguments:
        * `value` (`Any`): The first value.
        """
        self.value: Any = value
        self.traces: list[Callable[..., object]] = []

    # Method `StringVar.get()`:
    def get(self) -> Any:
        """Return the value.

        Returns:
        * (`Any`): The value.
        """
        return self.value

    # Method `StringVar.set()`:
    def set(self, value: Any) -> None:
        """Change the value, and tell what follows it.

        Arguments:
        * `value` (`Any`): The new value.
        """
        self.value = value
        for trace in self.traces:
            trace("", "", "write")

    # Method `StringVar.trace_add()`:
    def trace_add(self, _mode: str, callback: Callable[..., object]) -> None:
        """Follow the value.

        Arguments:
        * `callback` (`Callable[..., object]`): Called on each `set()`.
        """
        self.traces.append(callback)


DoubleVar = StringVar


# Class `Widget`:
class Widget:
    """Stands in for any `tkinter` widget, keeping its options.

    Attributes:
    * `children` (`list[Widget]`): The widgets inside it.
    * `kind` (`str`): The class that `winfo_class()` reports.
    * `options` (`dict[str, Any]`): Its options.
    """

    kind: str = "Widget"

    # Method `Widget.__init__()`:
    def __init__(self, parent: "Widget | None" = None, **options: Any) -> None:
        """Make a widget.

        Arguments:
        * `parent` (`Widget | None`): What it is inside, if anything.
        * `options` (`Any`): Its options.
        """
        self.children: list[Widget] = []
        self.options: dict[str, Any] = options
        if parent is not None:
            parent.children.append(self)

    # Method `Widget.configure()`:
    def configure(self, **options: Any) -> None:
        """Change options.

        Arguments:
        * `options` (`Any`): The options.
        """
        self.options.update(options)

    # Method `Widget.cget()`:
    def cget(self, name: str) -> Any:
        """Return an option.

        Arguments:
        * `name` (`str`): Its name.

        Returns:
        * (`Any`): Its value, or `""` when it was never set.
        """
        return self.options.get(name, "")

    # Method `Widget.winfo_class()`:
    def winfo_class(self) -> str:
        """Return the widget's class.

        Returns:
        * (`str`): Its name in Tk.
        """
        return self.kind

    # Method `Widget.winfo_children()`:
    def winfo_children(self) -> list["Widget"]:
        """Return the widgets inside this one.

        Returns:
        * (`list[Widget]`): The widgets.
        """
        return list(self.children)

    # Method `Widget.pack()`:
    def pack(self, **_options: Any) -> None:
        """Do nothing, as nothing is drawn."""

    # Method `Widget.grid()`:
    def grid(self, **_options: Any) -> None:
        """Do nothing, as nothing is drawn."""

    # Method `Widget.bind()`:
    def bind(self, _event: str, _callback: Callable[..., object]) -> None:
        """Do nothing, as no events happen."""

    # Method `Widget.title()`:
    def title(self, text: str) -> None:
        """Set the window's title.

        Arguments:
        * `text` (`str`): The title.
        """
        self.options["title"] = text


# Class `Frame`:
class Frame(Widget):
    """Stands in for `ttk.Frame`."""

    kind = "TFrame"


# Class `Label`:
class Label(Widget):
    """Stands in for `ttk.Label`."""

    kind = "TLabel"


# Class `Progressbar`:
class Progressbar(Widget):
    """Stands in for `ttk.Progressbar`."""

    kind = "TProgressbar"


# Class `Scale`:
class Scale(Widget):
    """Stands in for `ttk.Scale`."""

    kind = "TScale"


# Class `Combobox`:
class Combobox(Widget):
    """Stands in for `ttk.Combobox`."""

    kind = "TCombobox"


# Class `Toplevel`:
class Toplevel(Widget):
    """Stands in for `tkinter.Toplevel`."""

    kind = "Toplevel"


# Class `Button`:
class Button(Widget):
    """Stands in for `ttk.Button`."""

    kind = "TButton"

    # Method `Button.invoke()`:
    def invoke(self) -> None:
        """Press it: nothing happens when it is disabled."""
        command: Any = self.options.get("command")
        if command is not None and self.cget("state") != "disabled":
            command()


# Class `Radiobutton`:
class Radiobutton(Button):
    """Stands in for `tkinter.Radiobutton`."""

    kind = "Radiobutton"

    # Method `Radiobutton.invoke()`:
    def invoke(self) -> None:
        """Press it: its variable takes its value, unless disabled."""
        if self.cget("state") != "disabled":
            self.options["variable"].set(self.options["value"])
            Button.invoke(self)


# Class `Scrollbar`:
class Scrollbar(Widget):
    """Stands in for `ttk.Scrollbar`."""

    kind = "TScrollbar"

    # Method `Scrollbar.set()`:
    def set(self, *_where: Any) -> None:
        """Do nothing, as nothing is drawn."""


# Class `Entry`:
class Entry(Widget):
    """Stands in for `tkinter.Entry`."""

    kind = "Entry"

    # Method `Entry.get()`:
    def get(self) -> str:
        """Return the text.

        Returns:
        * (`str`): Its variable's value.
        """
        return str(self.options["textvariable"].get())


# Class `Text`:
class Text(Widget):
    """Stands in for `tkinter.Text`, holding one string.

    Attributes:
    * `contents` (`str`): The text.
    """

    kind = "Text"

    # Method `Text.__init__()`:
    def __init__(self, parent: Widget | None = None, **options: Any) -> None:
        """Make an empty text window.

        Arguments:
        * `parent` (`Widget | None`): What it is inside.
        * `options` (`Any`): Its options.
        """
        Widget.__init__(self, parent, **options)
        self.contents: str = ""

    # Method `Text.delete()`:
    def delete(self, _first: str, _last: str) -> None:
        """Remove all of the text, unless disabled."""
        if self.cget("state") != "disabled":
            self.contents = ""

    # Method `Text.insert()`:
    def insert(self, _where: str, text: str) -> None:
        """Add to the text, unless disabled.

        Arguments:
        * `text` (`str`): What to add.
        """
        if self.cget("state") != "disabled":
            self.contents += text

    # Method `Text.get()`:
    def get(self, _first: str, _last: str) -> str:
        """Return all of the text.

        Returns:
        * (`str`): The text.
        """
        return self.contents

    # Method `Text.see()`:
    def see(self, _where: str) -> None:
        """Do nothing, as nothing is drawn."""

    # Method `Text.yview()`:
    def yview(self, *_where: Any) -> None:
        """Do nothing, as nothing is drawn."""

    # Method `Text.yview_moveto()`:
    def yview_moveto(self, _where: float) -> None:
        """Do nothing, as nothing is drawn."""


# Class `Tk`:
class Tk(Widget):
    """Stands in for `tkinter.Tk`: the top window and its event loop.

    Attributes:
    * `alive` (`bool`): False once `destroy()` is called.
    * `count` (`int`): How many callbacks have been scheduled.
    * `due` (`list[tuple[float, int, Callable[[], object]]]`): When
      each callback is due, as a heap.
    """

    kind = "Tk"

    # Method `Tk.__init__()`:
    def __init__(self) -> None:
        """Make the top window."""
        Widget.__init__(self)
        self.alive: bool = True
        self.count: int = 0
        self.due: list[tuple[float, int, Callable[[], object]]] = []

    # Method `Tk.after()`:
    def after(self, milliseconds: int, callback: Callable[[], object]) -> None:
        """Call something later.

        Arguments:
        * `milliseconds` (`int`): How much later.
        * `callback` (`Callable[[], object]`): What to call.
        """
        self.count += 1
        heapq.heappush(
            self.due,
            (
                time.monotonic() + milliseconds / 1000.0,
                self.count,
                callback,
            ),
        )

    # Method `Tk.run_one()`:
    def run_one(self) -> None:
        """Run the next callback, even if it is not due yet.

        As in `tkinter`, an exception in it is printed, not raised.
        """
        _, _, callback = heapq.heappop(self.due)
        try:
            callback()
        # pylint: disable-next=broad-exception-caught
        except Exception:  # noqa: BLE001
            print("Exception in Tkinter callback", file=sys.stderr)
            traceback.print_exc()

    # Method `Tk.mainloop()`:
    def mainloop(self) -> None:
        """Run the callbacks as they come due, until `destroy()`."""
        while self.alive and self.due:
            time.sleep(max(0.0, self.due[0][0] - time.monotonic()))
            self.run_one()

    # Method `Tk.destroy()`:
    def destroy(self) -> None:
        """Close the window, which ends `mainloop()`."""
        self.alive = False
