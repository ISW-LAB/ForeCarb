# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""Upper fitted limit of growth scenarios and the fitted-range audit.

The entry and calculation guards test the *initial* predictor value
``D_i(0)``.  During a growth scenario the projected value would eventually
exceed the fitted range of the selected equation.  ForeCarb does not
extrapolate: the predictor is held at the upper fitted limit once it is
reached,

    D_i(t) = min(D_i(t-1) + g_i(t), D_max,i),

so every estimate is evaluated inside the fitted range.  This module provides
that limit, the audit flag

    v_i(t) = 1  while the record is still growing (below the limit)
             0  once it is held at the upper fitted limit (or, for a record
                that bypassed the entry guard, outside the range)

and the site-level share of the carbon stock that comes from records held at
the limit.  Stocks of such records are constant, so later totals are
conservative.

The module is free of Qt so that the graphical interface, the XLSX report and
the regression tests all use the same numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

# Accumulating period-specific increments in floating point can leave a value
# a few ulps above a limit it should equal (for example 1.5 + 8 * 0.3 against a
# limit of 3.9).  The limits are inclusive, so a small tolerance keeps such a
# value inside the range.
RANGE_TOLERANCE = 1e-9


def within_fitted_range(range_min: Optional[float], range_max: Optional[float],
                        values: Iterable[float]) -> Optional[np.ndarray]:
    """Boolean array ``v_i(t)``: True where the predictor is inside the fitted range.

    Returns ``None`` when the source publishes no fitted range, because the
    status of such an estimate cannot be assessed.
    """
    if range_min is None or range_max is None:
        return None
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values,
                     dtype=float)
    return (arr >= float(range_min) - RANGE_TOLERANCE) & (arr <= float(range_max) + RANGE_TOLERANCE)


def upper_growth_limit(range_max: Optional[float], starting_value: float) -> Optional[float]:
    """Largest predictor value a growth scenario may reach (``None``: no published range).

    A starting value above the fitted range is never reduced; such a record is
    rejected by the entry guard and only stays where it started.
    """
    if range_max is None:
        return None
    return max(float(range_max), float(starting_value))


def hold_at_upper_limit(range_max: Optional[float], values: Iterable[float]) -> np.ndarray:
    """Predictor trajectory with growth stopped at the upper fitted limit."""
    arr = np.array(values, dtype=float)
    if arr.size == 0:
        return arr
    limit = upper_growth_limit(range_max, arr[0])
    return arr if limit is None else np.minimum(arr, limit)


def held_at_upper_limit(range_max: Optional[float], values: Iterable[float]) -> Optional[np.ndarray]:
    """Boolean array: True for the years in which unconstrained growth exceeds the limit.

    ``values`` is the *unconstrained* trajectory.  Returns ``None`` when the
    source publishes no fitted range.
    """
    arr = np.array(values, dtype=float)
    if range_max is None or arr.size == 0:
        return None
    return arr > upper_growth_limit(range_max, arr[0]) + RANGE_TOLERANCE


def first_year_outside(inside: Optional[np.ndarray]) -> Optional[int]:
    """First scenario year with ``v_i(t) = 0`` (``None`` if never).

    With growth held at the upper fitted limit this is the first year in which
    the record is held at that limit.
    """
    if inside is None:
        return None
    outside = np.flatnonzero(~np.asarray(inside, dtype=bool))
    return int(outside[0]) if outside.size else None


@dataclass(frozen=True)
class ExtrapolationSummary:
    """Year-by-year split of a carbon total into audited parts (kg C).

    ``total = within + extrapolated + unassessed``.  ``extrapolated`` keeps its
    historical name: it is the stock of the records with ``v_i(t) = 0``, that
    is, of the records held at the upper fitted limit.  ``unassessed`` collects
    the records whose source gives no fitted range.
    """

    total: np.ndarray
    extrapolated: np.ndarray
    unassessed: np.ndarray

    @property
    def within(self) -> np.ndarray:
        return self.total - self.extrapolated - self.unassessed

    @property
    def share_pct(self) -> np.ndarray:
        """Share of the total held at the upper limit, in percent (0 where the total is 0)."""
        share = np.zeros_like(self.total, dtype=float)
        positive = self.total > 0
        share[positive] = 100.0 * self.extrapolated[positive] / self.total[positive]
        return share

    def share_at(self, year: int) -> float:
        return float(self.share_pct[int(year)])


def summarize(curves: Sequence[np.ndarray],
              inside_flags: Sequence[Optional[np.ndarray]],
              length: Optional[int] = None) -> ExtrapolationSummary:
    """Split the summed carbon trajectories of several records by audit status.

    ``curves[k]`` is the carbon trajectory of record ``k`` and
    ``inside_flags[k]`` its ``v_i(t)`` array (or ``None`` when no fitted range is
    published).  With no records the result is an all-zero summary of
    ``length`` years.
    """
    if len(curves) != len(inside_flags):
        raise ValueError("curves and inside_flags must have the same length")
    if not curves:
        zeros = np.zeros(int(length or 0), dtype=float)
        return ExtrapolationSummary(zeros, zeros.copy(), zeros.copy())

    n = len(np.asarray(curves[0]))
    total = np.zeros(n, dtype=float)
    extrapolated = np.zeros(n, dtype=float)
    unassessed = np.zeros(n, dtype=float)
    for curve, inside in zip(curves, inside_flags):
        carbon = np.asarray(curve, dtype=float)
        if carbon.shape != (n,):
            raise ValueError("all carbon trajectories must cover the same years")
        total += carbon
        if inside is None:
            unassessed += carbon
        else:
            flags = np.asarray(inside, dtype=bool)
            if flags.shape != (n,):
                raise ValueError("audit flags must cover the same years as the trajectory")
            extrapolated += np.where(flags, 0.0, carbon)
    return ExtrapolationSummary(total, extrapolated, unassessed)


def combine(*summaries: ExtrapolationSummary) -> ExtrapolationSummary:
    """Add summaries of the same length (for example trees + shrubs = site)."""
    parts = [s for s in summaries if s is not None and len(s.total)]
    if not parts:
        zeros = np.zeros(0, dtype=float)
        return ExtrapolationSummary(zeros, zeros.copy(), zeros.copy())
    return ExtrapolationSummary(
        sum(s.total for s in parts),
        sum(s.extrapolated for s in parts),
        sum(s.unassessed for s in parts),
    )
