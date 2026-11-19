# SPDX-License-Identifier: MIT
"""Shared 30-year scenarios. Assumptions are documented in GROWTH_ASSUMPTIONS.md."""
from __future__ import annotations
import numpy as np
from . import extrapolation
from . import species_library as lib

PROJECTION_YEARS = 30
ASSUMED_ANNUAL_RATE = 0.02

def unconstrained_predictor(record, starting_value, years=PROJECTION_YEARS):
    """Predictor trajectory of the growth scenario before the upper limit is applied."""
    axis = np.arange(years + 1, dtype=int)
    values = np.empty(years + 1, dtype=float)
    values[0] = starting_value
    if record.species_data is not None:
        for year in range(1, years + 1):
            values[year] = values[year - 1] + record.species_data.growth_at_year(year)
    else:
        values = float(starting_value) * (1.0 + ASSUMED_ANNUAL_RATE * record.growth_factor) ** axis
    return values


def held_at_upper_limit(record, starting_value, years=PROJECTION_YEARS):
    """Years in which the record is held at its upper fitted limit (None: no published range)."""
    return extrapolation.held_at_upper_limit(
        record.range_max, unconstrained_predictor(record, starting_value, years))


def project_record(record, starting_value, quantity, var2=None, years=PROJECTION_YEARS):
    """Return year, predictor and carbon arrays; retain the original equation.

    The predictor grows until it reaches the upper fitted limit of the record
    and is held there, so no estimate is obtained outside the fitted range.
    Records without a published range grow for the whole period.
    """
    axis = np.arange(years + 1, dtype=int)
    values = extrapolation.hold_at_upper_limit(
        record.range_max, unconstrained_predictor(record, starting_value, years))
    carbon = lib.carbon_by_diameter(record, values, quantity, var2)
    if not np.all(np.isfinite(carbon)):
        raise lib.LibraryError(f"{record.key}: scenario equation is undefined within years 0–{years}")
    return axis, values, carbon

def assumption_note(record):
    if record.species_data is not None:
        return ""
    suffix = "; H constant" if record.is_multivar else ""
    rate = 1.0 + ASSUMED_ANNUAL_RATE * record.growth_factor
    return f"{record.key}: X(t)=X(0) × {rate:g}^t{suffix} (assumed)"
