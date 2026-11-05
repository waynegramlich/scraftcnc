"""A grid plate without chamfers, for the tests.

`GRID_PLATE`'s 200 chamfers take minutes to model whenever its cache
key changes, and add nothing to the tests, so tests that model a setup
name this plate in its place.
"""

import dataclasses
import unittest
from unittest import mock

from scraftcnc.tooling import tools

# `GRID_PLATE` without its chamfers: the same shape for every check.
FLAT_PLATE: tools.GridPlate = dataclasses.replace(
    tools.GRID_PLATE, chamfer_depth=0.0
)


# Function `use_flat_plate()`:
def use_flat_plate() -> None:
    """Have setups name `FLAT_PLATE` until the test module ends.

    Call it from a test module's `setUpModule()`, after any
    `use_shop()`, which would put the chamfered plate back.
    """
    patcher = mock.patch.dict(
        tools.GridPlate.REGISTRY.items, {"grid_plate": FLAT_PLATE}
    )
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
