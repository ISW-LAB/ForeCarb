# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
탄소량 계산 핵심 로직.

원본 MATLAB의 calculateTreeCarbon / calculateShrubCarbon / plotTreeGraph / plotShrubGraph
와 동일한 수식을 보존한다.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from .data import SpeciesData
from .i18n import species_name, tr


class RangeViolation(Exception):
    """입력 직경이 수종별 유효 범위를 벗어났을 때 발생."""
    def __init__(self, species: str, value: float, vmin: float, vmax: float, unit: str):
        self.species = species
        self.value = value
        self.vmin = vmin
        self.vmax = vmax
        self.unit = unit
        super().__init__(
            tr("{species}의 유효 직경 범위는 {vmin:g} {unit} ~ {vmax:g} {unit} 입니다.")
            .format(species=species_name(species), vmin=vmin, vmax=vmax, unit=unit)
        )


@dataclass
class CarbonRow:
    species: str
    diameter: float
    quantity: int
    carbon_kg: float

    def as_table_row(self) -> list:
        return [self.species, self.diameter, self.quantity, round(self.carbon_kg, 2)]


def area_normalized_carbon_density(
    total_carbon_kg: float,
    site_area_m2: float,
) -> float:
    """Return site carbon stock normalized by site area in kg C m^-2.

    Normalization changes only the reporting denominator. It does not rescale
    the submitted inventory or its total carbon stock. Both inputs must be
    finite, the site area must be positive, and carbon stock cannot be
    negative.
    """
    total = float(total_carbon_kg)
    area = float(site_area_m2)
    if not math.isfinite(total):
        raise ValueError("total_carbon_kg must be finite")
    if total < 0:
        raise ValueError("total_carbon_kg cannot be negative")
    if not math.isfinite(area) or area <= 0:
        raise ValueError("site_area_m2 must be finite and greater than zero")
    return total / area


@dataclass(frozen=True)
class SiteCarbonMetrics:
    """Carbon metrics reported for one accepted site inventory."""

    tree_carbon_kg: float
    shrub_carbon_kg: float
    total_carbon_kg: float
    site_area_m2: float
    area_normalized_kg_m2: float


def calculate_site_carbon_metrics(
    tree_carbon_kg: float,
    shrub_carbon_kg: float,
    site_area_m2: float,
) -> SiteCarbonMetrics:
    """Aggregate component stocks and calculate the area-normalized metric."""
    tree = float(tree_carbon_kg)
    shrub = float(shrub_carbon_kg)
    for label, value in (("tree_carbon_kg", tree), ("shrub_carbon_kg", shrub)):
        if not math.isfinite(value):
            raise ValueError(f"{label} must be finite")
        if value < 0:
            raise ValueError(f"{label} cannot be negative")
    total = tree + shrub
    return SiteCarbonMetrics(
        tree_carbon_kg=tree,
        shrub_carbon_kg=shrub,
        total_carbon_kg=total,
        site_area_m2=float(site_area_m2),
        area_normalized_kg_m2=area_normalized_carbon_density(total, site_area_m2),
    )


def calculate_carbon(species_name: str,
                     species_data: SpeciesData,
                     diameter_cm: float,
                     quantity: int,
                     unit: str = "cm") -> CarbonRow | None:
    """
    한 입력 슬롯에 대한 탄소량 계산.
    공개 입력 직경은 교목 DBH와 관목 RCD 모두 cm이다. 계수가 mm 기준으로
    적합된 레코드는 ``SpeciesData.to_equation_diameter``가 식 평가 직전에만
    원 단위로 변환한다.
    수량이 0이면 None (계산에서 제외).
    유효 범위 위반 시 RangeViolation 예외.
    """
    if quantity <= 0:
        return None

    if diameter_cm < species_data.diameter_min or diameter_cm > species_data.diameter_max:
        raise RangeViolation(
            species_name, diameter_cm,
            species_data.diameter_min, species_data.diameter_max, unit,
        )

    equation_diameter = species_data.to_equation_diameter(diameter_cm)
    biomass = species_data.a * (equation_diameter ** species_data.b)
    carbon_per_individual = biomass * species_data.cf
    total_carbon = carbon_per_individual * quantity
    return CarbonRow(species_name, diameter_cm, quantity, total_carbon)


def weighted_average_diameter(rows: Iterable[CarbonRow]) -> float:
    """결과 행들의 수량 가중평균 직경. 합이 0이면 0 반환."""
    rows = list(rows)
    total_qty = sum(r.quantity for r in rows)
    if total_qty == 0:
        return 0.0
    return sum(r.diameter * r.quantity for r in rows) / total_qty


def project_future_carbon(species_data: SpeciesData,
                          starting_diameter: float,
                          total_quantity: int,
                          years: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """
    cm 단위의 starting_diameter부터 매년 cm 성장률을 더해 총 탄소량 변동 계산.

    Returns:
        years_arr (0..N), carbon_arr (각 연도의 총 탄소량 kgC)

    계수 적합 단위가 mm인 레코드는 직경 시계열 자체가 아니라 식 평가 입력만
    원 단위로 변환하므로 DBH와 RCD 시나리오가 동일한 cm 계약을 사용한다.
    직경은 식의 적합범위 상한에 닿으면 그 값에서 멈춘다(범위 밖 추정 없음).
    """
    from .extrapolation import hold_at_upper_limit

    years_arr = np.arange(0, years + 1)
    diameter_arr = np.zeros(years + 1, dtype=float)
    diameter_arr[0] = starting_diameter

    for i in range(1, years + 1):
        growth = species_data.growth_at_year(i)
        diameter_arr[i] = diameter_arr[i - 1] + growth
    diameter_arr = hold_at_upper_limit(species_data.diameter_max, diameter_arr)

    equation_diameters = species_data.to_equation_diameter(diameter_arr)
    carbon_per = species_data.a * (equation_diameters ** species_data.b) * species_data.cf
    return years_arr, carbon_per * total_quantity
