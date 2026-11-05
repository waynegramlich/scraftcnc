"""Fill the name registries from the shop in use.

Shops are independent: the registries of `SCCutter`, `SCMillTable`,
`SCMachineVise`, `SCParallel` and `SCGridPlate` hold the objects of
one shop at a time, never of two shops mixed.  `use_shop()` empties
them all and fills them from the shop it is given.

The shop files do not describe mill tables, machine vises or
parallels yet, so those come from the built-in constants of
`tools.py` (`MILL_TABLES`, `MIKINI_1610L`, `KURT_D688`, `PARALLELS`).
Grid plates are the shop's own; only a shop that lists none gets the
built-in `GRID_PLATE`.
"""

from ..shops import grid_plates
from .cutter_models import SCCutter, register_cutters
from .tools import (
    GRID_PLATE,
    KURT_D688,
    MIKINI_1610L,
    MILL_TABLES,
    PARALLELS,
    SCGridPlate,
    SCMachineVise,
    SCMillTable,
    SCParallel,
)


# Function `use_shop()`:
def use_shop(shop: dict[str, object]) -> None:
    """Empty every name registry and fill it from one shop.

    Arguments:
    * `shop` (`dict[str, object]`): The shop, from `shops.read()`.
    """
    # Empty them all, so nothing of an earlier shop is left.
    SCCutter.REGISTRY.items.clear()
    SCMillTable.REGISTRY.items.clear()
    SCMachineVise.REGISTRY.items.clear()
    SCParallel.REGISTRY.items.clear()
    SCGridPlate.REGISTRY.items.clear()

    # The shop files: its cutters and grid plates (the built-in grid
    # plate only when the shop lists none).
    register_cutters(shop, SCCutter.REGISTRY)
    plates: dict[str, dict[str, object]] = grid_plates(shop)
    for name, plate in plates.items():
        SCGridPlate.REGISTRY.add(name, SCGridPlate.from_shop(plate))
    if not plates:
        SCGridPlate.REGISTRY.add(GRID_PLATE.name, GRID_PLATE)

    # Not in the shop files yet: the built-in tooling.
    for table in (*MILL_TABLES, MIKINI_1610L):
        SCMillTable.REGISTRY.add(table.name, table)
    SCMachineVise.REGISTRY.add(KURT_D688.name, KURT_D688)
    for parallel in PARALLELS:
        SCParallel.REGISTRY.add(parallel.name, parallel)
