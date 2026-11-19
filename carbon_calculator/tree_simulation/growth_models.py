# SPDX-License-Identifier: MIT
"""기존 직경 성장자료를 렌더 상태로 변환하는 함수.

탄소량은 이 모듈에서 계산하지 않는다. 수고와 수관 fallback은 오직 geometry용이다.
"""
from __future__ import annotations

import math

import numpy as np

from .models import ModelValue, RenderState, RegionVisualizationSnapshot
from .species_profiles import SpeciesRenderProfile, growth_sensitivity, profile_by_key


VISUAL_FALLBACK_SOURCE = "Carbon1 3D visual fallback (not a scientific height/crown model)"


def diameter_timeline(species_data, starting_diameter: float, *, years: int = 30) -> np.ndarray:
    """DBH/RCD 공통 cm 계약으로 직경 timeline을 만든다 (적합범위 상한에서 멈춘다)."""
    from ..extrapolation import hold_at_upper_limit

    values = np.zeros(years + 1, dtype=float)
    values[0] = starting_diameter
    for year in range(1, years + 1):
        values[year] = values[year - 1] + species_data.growth_at_year(year)
    return hold_at_upper_limit(species_data.diameter_max, values)


def visual_development(elapsed_year: int) -> float:
    """실제 수령이 아닌 현재 상태 이후 경과 연도의 시각적 발달도(0..1)."""
    return max(0.0, min(1.0, elapsed_year / 50.0))


def _base_visual_height(initial_diameter_m: float, profile: SpeciesRenderProfile,
                        kind: str) -> float:
    """Year 0의 자연스러운 외형만 정하는 시각화용 기준 높이."""
    base = 0.58 if kind == "shrub" else 1.3
    rate = 8.0 if kind == "shrub" else 3.8
    scaled = 1.0 - math.exp(-rate * max(0.0, initial_diameter_m) * profile.height_scale)
    return base + (profile.height_limit_m - base) * (0.68 if kind == "shrub" else 0.78) * scaled


def diameter_growth_ratio(current_diameter: float, initial_diameter: float) -> float:
    """현재 상태(Year 0) 직경 대비 실제 DBH/RCD 성장비."""
    if initial_diameter <= 0:
        return 1.0
    return max(1.0, current_diameter / initial_diameter)


def rendered_height(species: str, diameter_value: float, diameter_unit: str,
                    profile: SpeciesRenderProfile, kind: str,
                    elapsed_year: int = 0, initial_diameter: float | None = None) -> ModelValue:
    initial = diameter_value if initial_diameter is None else initial_diameter
    del diameter_unit  # 공개 시각화 입력은 DBH/RCD 모두 cm이다.
    base_height = _base_visual_height(initial / 100.0, profile, kind)
    ratio = diameter_growth_ratio(diameter_value, initial)
    sensitivity = growth_sensitivity(kind)
    visual_height = min(
        profile.height_limit_m * sensitivity.safety_scale,
        base_height * ratio ** sensitivity.height_exponent,
    )
    return ModelValue(
        visual_height, "m", "visual_fallback",
        VISUAL_FALLBACK_SOURCE,
    )


def rendered_trunk_diameter(diameter_m: float, profile: SpeciesRenderProfile) -> ModelValue:
    """실제 DBH/RCD와 분리된 단순 geometry용 줄기 표시 직경."""
    boost = 1.0 + profile.trunk_visual_boost * math.exp(
        -diameter_m / profile.trunk_boost_decay_m
    )
    value = max(profile.trunk_min_visible_m, diameter_m * boost)
    return ModelValue(value, "m", "visual_fallback", "3D visibility adjustment")


def rendered_crown(profile: SpeciesRenderProfile, initial_diameter_m: float,
                   growth_ratio: float, base_height_m: float, kind: str) -> tuple[ModelValue, ModelValue]:
    min_width = 0.65 if kind == "shrub" else 0.55
    sensitivity = growth_sensitivity(kind)
    base_width_limit = base_height_m * (1.65 if kind == "shrub" else 0.78)
    base_width = min(
        base_width_limit,
        min_width + profile.crown_width_scale * math.sqrt(max(initial_diameter_m, 0.001)) * 4.0,
    )
    base_length = max(0.25, base_height_m * profile.crown_length_ratio)
    width = min(
        base_width * sensitivity.safety_scale,
        base_width * growth_ratio ** sensitivity.crown_width_exponent,
    )
    length = min(
        base_length * sensitivity.safety_scale,
        base_length * growth_ratio ** sensitivity.crown_length_exponent,
    )
    source = "Carbon1 3D visual crown fallback (not a scientific crown model)"
    return (
        ModelValue(width, "m", "visual_fallback", source),
        ModelValue(length, "m", "visual_fallback", source),
    )


def render_states(snapshot: RegionVisualizationSnapshot, year: int) -> tuple[RenderState, ...]:
    year = max(0, min(30, int(year)))
    groups = {g.group_id: g for g in snapshot.groups}
    states: list[RenderState] = []
    for instance in snapshot.instances:
        group = groups[instance.group_id]
        profile = profile_by_key(group.profile_key)
        diameter = float(group.diameter_by_year[year])
        diameter_m = diameter / 100.0
        initial_diameter_m = group.initial_diameter / 100.0
        growth_ratio = diameter_growth_ratio(diameter, group.initial_diameter)
        height = rendered_height(
            group.species, diameter, group.diameter_unit, profile, group.kind, year,
            group.initial_diameter,
        )
        base_height = _base_visual_height(initial_diameter_m, profile, group.kind)
        crown_width, crown_length = rendered_crown(
            profile, initial_diameter_m, growth_ratio, base_height, group.kind,
        )
        states.append(RenderState(
            instance_id=instance.instance_id,
            profile_key=group.profile_key,
            kind=group.kind,
            x_m=instance.x_m,
            y_m=instance.y_m,
            diameter_m=diameter_m,
            diameter_growth_ratio=growth_ratio,
            rendered_trunk_diameter_m=rendered_trunk_diameter(diameter_m, profile),
            rendered_height_m=height,
            rendered_crown_width_m=crown_width,
            rendered_crown_length_m=crown_length,
            visual_development=visual_development(year),
        ))
    return tuple(states)
