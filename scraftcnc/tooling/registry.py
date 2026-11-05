"""Name registries: look tooling up by a short identifier.

Each tooling class (`MillTable`, `MachineVise`, `Parallel`,
`GridPlate`) keeps an `Registry` of its objects, keyed by a short
identifier made from each object's name (`key()`: "Kurt D688" is
`kurt_d688`).  `named()` takes either the identifier or the name, so
setups that give display names keep working.  A user interface shows
each underscore of a key as a space.
"""

import re
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

# What a key may not hold: anything but lower case letters and digits.
_NOT_KEY: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


# Function `key()`:
def key(name: str) -> str:
    """Return the short identifier for a name.

    Arguments:
    * `name` (`str`):
      A display name (e.g. "Kurt D688") or an identifier.

    Returns:
    * (`str`): The name in lower case, each run of other characters
      turned into one underscore (e.g. `kurt_d688`).
    """
    return _NOT_KEY.sub("_", name.lower()).strip("_")


# Class `Registry`:
@dataclass(slots=True)
class Registry(Generic[T]):
    """The objects of one class, by key.

    Attributes:
    * `kind` (`str`): What the objects are, for messages (e.g.
      "machine vise").
    * `items` (`dict[str, T]`): The objects, by key.

    Constructor:
    * `Registry(kind)`
    """

    # Constructor arguments:
    kind: str = field(init=True)

    # Remaining attributes (alphabetized):
    items: dict[str, T] = field(init=False, default_factory=dict)

    # Method `Registry.add()`:
    def add(self, name: str, item: T) -> T:
        """Add an object under the key of its name.

        Adding an object equal to the one already there keeps the first.

        Arguments:
        * `name` (`str`):
          The object's name, from which its key is made.
        * `item` (`T`):
          The object.

        Returns:
        * (`T`): `item`, so that a definition can register itself.

        Raises:
        * `ValueError`: If a different object already has the key.
        """
        name_key: str = key(name)
        old: T | None = self.items.get(name_key)
        if old is not None and old != item:
            raise ValueError(
                f"Two {self.kind}s have the key {name_key!r}: "
                f"{old!r} and {item!r}"
            )
        if old is None:
            self.items[name_key] = item
        return item

    # Method `Registry.named()`:
    def named(self, name: str) -> T:
        """Return the object with a key or name.

        Arguments:
        * `name` (`str`):
          Its key (e.g. `kurt_d688`) or its name ("Kurt D688").

        Returns:
        * (`T`): The object.

        Raises:
        * `KeyError`: If there is none, listing the known keys.
        """
        name_key: str = key(name)
        if name_key not in self.items:
            known: str = ", ".join(sorted(self.items))
            raise KeyError(f"No {self.kind} is named {name!r}; known: {known}")
        return self.items[name_key]
