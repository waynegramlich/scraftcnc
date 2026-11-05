"""Fill the name registries from the shop in use.

Shops are independent: the registries of `Cutter`, `MillTable`,
`MachineVise`, `Parallel` and `GridPlate` hold the objects of
one shop at a time, never of two shops mixed.  `use_shop()` empties
them all and fills them from the shop it is given.

The shop files do not describe mill tables, machine vises or
parallels yet, so those come from the built-in constants of
`tools.py` (`MILL_TABLES`, `MIKINI_1610L`, `KURT_D688`, `PARALLELS`).
Grid plates are the shop's own; only a shop that lists none gets the
built-in `GRID_PLATE`.
"""

from ..shops import grid_plates
from .cutter_models import Cutter, register_cutters
from .tools import (
    GRID_PLATE,
    KURT_D688,
    MIKINI_1610L,
    MILL_TABLES,
    PARALLELS,
    GridPlate,
    MachineVise,
    MillTable,
    Parallel,
)


# Function `use_shop()`:
def use_shop(shop: dict[str, object]) -> None:
    """Empty every name registry and fill it from one shop.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.
    """
    # Empty them all, so nothing of an earlier shop is left.
    Cutter.REGISTRY.items.clear()
    MillTable.REGISTRY.items.clear()
    MachineVise.REGISTRY.items.clear()
    Parallel.REGISTRY.items.clear()
    GridPlate.REGISTRY.items.clear()

    # The shop files: its cutters and grid plates (the built-in grid
    # plate only when the shop lists none).
    register_cutters(shop, Cutter.REGISTRY)
    plates: dict[str, dict[str, object]] = grid_plates(shop)
    for name, plate in plates.items():
        GridPlate.REGISTRY.add(name, GridPlate.from_shop(plate))
    if not plates:
        GridPlate.REGISTRY.add(GRID_PLATE.name, GRID_PLATE)

    # Not in the shop files yet: the built-in tooling.
    for table in (*MILL_TABLES, MIKINI_1610L):
        MillTable.REGISTRY.add(table.name, table)
    MachineVise.REGISTRY.add(KURT_D688.name, KURT_D688)
    for parallel in PARALLELS:
        Parallel.REGISTRY.add(parallel.name, parallel)
