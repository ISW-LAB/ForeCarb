# SPDX-License-Identifier: MIT
"""Site-area safeguards for combined tree and shrub inventories.

The per-individual planting areas are transparent, configurable input guards.
They prevent accidental over-entry; they are not species-specific ecological
planting recommendations or estimates of biological carrying capacity, and
they never enter the biomass or carbon calculation.

The defaults (1.00 m2 per tree, 0.25 m2 per shrub) correspond to a spacing of
1 m x 1 m and 0.5 m x 0.5 m.  Users can change both values for the running
session and for later sessions from Settings > Planting-area safeguard in the
Assessment Application; the values in use are written to every XLSX report.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


# Release defaults.  The two historical names are kept because other modules
# and the regression tests import them.
TREE_PLANTING_AREA_M2_PER_INDIVIDUAL = 1.0
SHRUB_PLANTING_AREA_M2_PER_INDIVIDUAL = 0.25
DEFAULT_TREE_PLANTING_AREA_M2 = TREE_PLANTING_AREA_M2_PER_INDIVIDUAL
DEFAULT_SHRUB_PLANTING_AREA_M2 = SHRUB_PLANTING_AREA_M2_PER_INDIVIDUAL

# Accepted range of a user-defined planting area per individual (m2).
MIN_PLANTING_AREA_M2 = 0.01
MAX_PLANTING_AREA_M2 = 100.0

_SETTINGS_KEY_TREE = "planting_area/tree_m2"
_SETTINGS_KEY_SHRUB = "planting_area/shrub_m2"

# Values in use for the running session (tree, shrub).
_unit_areas = [DEFAULT_TREE_PLANTING_AREA_M2, DEFAULT_SHRUB_PLANTING_AREA_M2]


def _validated(value: float, what: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v < MIN_PLANTING_AREA_M2 or v > MAX_PLANTING_AREA_M2:
        raise ValueError(
            f"{what} planting area must be between {MIN_PLANTING_AREA_M2:g} and "
            f"{MAX_PLANTING_AREA_M2:g} m2 per individual, got {value!r}")
    return v


def planting_unit_areas() -> tuple[float, float]:
    """Planting area per individual currently in use: (tree, shrub) in m2."""
    return _unit_areas[0], _unit_areas[1]


def set_planting_unit_areas(tree_m2: float, shrub_m2: float) -> tuple[float, float]:
    """Set the planting areas used by the safeguard for this session."""
    tree = _validated(tree_m2, "tree")
    shrub = _validated(shrub_m2, "shrub")
    _unit_areas[0], _unit_areas[1] = tree, shrub
    return tree, shrub


def reset_planting_unit_areas() -> tuple[float, float]:
    """Restore the release defaults (1.00 and 0.25 m2 per individual)."""
    return set_planting_unit_areas(DEFAULT_TREE_PLANTING_AREA_M2, DEFAULT_SHRUB_PLANTING_AREA_M2)


def is_default_unit_areas() -> bool:
    return (abs(_unit_areas[0] - DEFAULT_TREE_PLANTING_AREA_M2) < 1e-12
            and abs(_unit_areas[1] - DEFAULT_SHRUB_PLANTING_AREA_M2) < 1e-12)


def load_saved_unit_areas() -> tuple[float, float]:
    """Apply the planting areas saved by an earlier session, if any.

    Called once by the application entry point.  Missing or invalid saved
    values leave the defaults in place.
    """
    try:
        from PyQt5.QtCore import QSettings
        from .i18n import _APP, _ORG
        settings = QSettings(_ORG, _APP)
        tree = settings.value(_SETTINGS_KEY_TREE)
        shrub = settings.value(_SETTINGS_KEY_SHRUB)
        if tree is not None and shrub is not None:
            set_planting_unit_areas(float(tree), float(shrub))
    except Exception:  # noqa: BLE001 — keep the defaults on any problem
        pass
    return planting_unit_areas()


def save_unit_areas() -> None:
    """Persist the planting areas in use for later sessions."""
    try:
        from PyQt5.QtCore import QSettings
        from .i18n import _APP, _ORG
        settings = QSettings(_ORG, _APP)
        settings.setValue(_SETTINGS_KEY_TREE, float(_unit_areas[0]))
        settings.setValue(_SETTINGS_KEY_SHRUB, float(_unit_areas[1]))
        settings.sync()
    except Exception:  # noqa: BLE001
        pass


@dataclass(frozen=True)
class PlantingAreaBudget:
    """Resolved site and inventory areas for one calculation request."""

    site_area_m2: float
    tree_quantity: int
    shrub_quantity: int
    tree_area_m2: float
    shrub_area_m2: float
    required_area_m2: float
    tree_unit_area_m2: float = DEFAULT_TREE_PLANTING_AREA_M2
    shrub_unit_area_m2: float = DEFAULT_SHRUB_PLANTING_AREA_M2

    @property
    def excess_area_m2(self) -> float:
        return max(0.0, self.required_area_m2 - self.site_area_m2)

    @property
    def is_exceeded(self) -> bool:
        return self.required_area_m2 > self.site_area_m2 + 1e-9


def planting_area_budget(
    *,
    area_w: float,
    area_h: float,
    tree_quantity: int,
    shrub_quantity: int,
    tree_unit_area_m2: float | None = None,
    shrub_unit_area_m2: float | None = None,
) -> PlantingAreaBudget | None:
    """Return the combined planting-area budget, or ``None`` for an invalid site.

    When a unit area is not given, the value currently in use
    (``planting_unit_areas``) is applied.
    """
    current_tree, current_shrub = planting_unit_areas()
    if tree_unit_area_m2 is None:
        tree_unit_area_m2 = current_tree
    if shrub_unit_area_m2 is None:
        shrub_unit_area_m2 = current_shrub

    values = (area_w, area_h, tree_unit_area_m2, shrub_unit_area_m2)
    if not all(math.isfinite(float(value)) for value in values):
        return None
    if area_w <= 0 or area_h <= 0 or tree_unit_area_m2 < 0 or shrub_unit_area_m2 < 0:
        return None

    tree_quantity = max(0, int(tree_quantity))
    shrub_quantity = max(0, int(shrub_quantity))
    site_area_m2 = float(area_w) * float(area_h)
    tree_area_m2 = tree_quantity * float(tree_unit_area_m2)
    shrub_area_m2 = shrub_quantity * float(shrub_unit_area_m2)
    return PlantingAreaBudget(
        site_area_m2=site_area_m2,
        tree_quantity=tree_quantity,
        shrub_quantity=shrub_quantity,
        tree_area_m2=tree_area_m2,
        shrub_area_m2=shrub_area_m2,
        required_area_m2=tree_area_m2 + shrub_area_m2,
        tree_unit_area_m2=float(tree_unit_area_m2),
        shrub_unit_area_m2=float(shrub_unit_area_m2),
    )
