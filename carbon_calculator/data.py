# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
수종별 탄소량 계산 데이터.

원본 MATLAB (Carbon_251002_5.mlapp) 의 TreeDataMap/TreeGrowthMap/TreeDiameterRangeMap +
ShrubDataMap/ShrubGrowthMap/ShrubDiameterRangeMap 을 단일 dict 구조로 통합.

수종 라벨·상대생장식(a, b)·변수·범위는 **`상대생장식 자료_최종본.xlsx` 의
「기초 DB 자료」 시트** 와 일치하도록 정합 (Ver. 1.2).

성장률(growth_y10/y20/y21)은 CSV에 없으므로 MATLAB 원본의 TreeGrowthMap / ShrubGrowthMap
에서 위치 매칭으로 가져옴.

CSV vs MATLAB 차이 (CSV를 출처상의 진실로 채택):
- 회양목      : CSV a=0.000018  (MATLAB 0.00018 - 10배 차이)
- 좀작살나무 : CSV a=0.0021     (MATLAB 0.00021 - 10배 차이)
- 수수꽃다리 : CF=0.45 (CSV에 CF 정보 없음; MATLAB 원본 값 유지)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class SpeciesData:
    a: float            # allometric 회귀계수 a
    b: float            # allometric 회귀계수 b
    cf: float           # 탄소전환계수 (biomass kg → C kg)
    diameter_min_native: float
    diameter_max_native: float
    growth_y10: float   # 1~10년 성장률 (cm/yr)
    growth_y20: float   # 11~20년 성장률 (cm/yr)
    growth_y21: float   # 21년 이후 성장률 (cm/yr)
    equation_diameter_unit: Literal["cm", "mm"] = "cm"

    @property
    def equation_diameter_scale(self) -> float:
        """Centimetre input을 원 상대생장식의 직경 단위로 변환하는 배율."""
        return 10.0 if self.equation_diameter_unit == "mm" else 1.0

    @property
    def diameter_min(self) -> float:
        """Assessment Application에 노출되는 최소 직경(cm)."""
        return self.diameter_min_native / self.equation_diameter_scale

    @property
    def diameter_max(self) -> float:
        """Assessment Application에 노출되는 최대 직경(cm)."""
        return self.diameter_max_native / self.equation_diameter_scale

    def to_equation_diameter(self, diameter_cm: float | object):
        """공개 입력(cm)을 계수 적합 시 사용된 원 직경 단위로 변환한다."""
        return diameter_cm * self.equation_diameter_scale

    def growth_at_year(self, year: int) -> float:
        if year <= 10:
            return self.growth_y10
        if year <= 20:
            return self.growth_y20
        return self.growth_y21


# 대상지 유형 — 프로젝트 구분 메타데이터이며, 아래 두 경로로만 계산에 관여한다.
#   ① 수종마다 대상지 3종의 레코드를 각각 보유하고, 선택된 대상지 것 하나만 적용한다
#      (대상지 공통 '기본식' 개념은 없다).
#   ② 그 위에 대상지 × 생장 티어(1·2·3) 보정계수가 연 직경 생장량에 추가로 곱해진다.
RESTORATION_ENVIRONMENTS = (
    "산불피해지 자연복원",
    "산불피해지 인공복원",
    "채석장 인공복원",
)
DEFAULT_ENVIRONMENT = RESTORATION_ENVIRONMENTS[0]

# 대상지 × 생장 티어 보정계수 — 대상지 3종 × 티어 3단계 = 9개.
# 수종마다 대상지별로 티어(1·2·3)가 지정되고(`SPECIES_GROWTH_TIERS`), 그 티어의 계수가
# 연 직경 생장량에 **추가로** 곱해진다. 1.0 은 보정 없음이다. 식(a·b·CF·범위)은
# 건드리지 않으므로 0년차 현재 저장량은 이 계수에 영향을 받지 않고 30년 시나리오만
# 달라진다.
GROWTH_TIERS = (1, 2, 3)
DEFAULT_GROWTH_TIER = 1


def tier_key(tier: int) -> str:
    """JSON 키: 1 → "TIER_1"."""
    return f"TIER_{int(tier)}"


# 구버전(대상지 × 교목/관목 = 6개) JSON 키 — 읽을 때 티어로 옮긴다.
GROWTH_FACTOR_SECTION_TREE = "TREE_BASE"
GROWTH_FACTOR_SECTION_SHRUB = "SHRUB_SPECIES"
_LEGACY_SECTION_TIER = {GROWTH_FACTOR_SECTION_TREE: 1, GROWTH_FACTOR_SECTION_SHRUB: 2}


def _unit_factors() -> dict[str, dict[str, float]]:
    return {env: {tier_key(t): 1.0 for t in GROWTH_TIERS} for env in RESTORATION_ENVIRONMENTS}


ENVIRONMENT_GROWTH_FACTORS: dict[str, dict[str, float]] = _unit_factors()

# 수종별 티어 — {수종명: {대상지: 1|2|3}}. 없으면 DEFAULT_GROWTH_TIER.
SPECIES_GROWTH_TIERS: dict[str, dict[str, int]] = {}

# 수종 단위 예외 — {수종명: {대상지: 계수}}. 있으면 티어 계수보다 우선한다.
SPECIES_GROWTH_FACTORS: dict[str, dict[str, float]] = {}


def _by_env(**per_env: SpeciesData) -> dict:
    """대상지별 레코드 묶음을 만든다 (키는 대상지 이름).

    호출 편의를 위해 위치 인자 대신 `_all_env` / `_each_env` 를 쓴다.
    """
    return {"by_env": dict(per_env)}


def _all_env(spec: SpeciesData) -> dict:
    """세 대상지에 같은 레코드를 부여한다.

    패키징 폴백 라이브러리에서 대상지별 근거가 아직 없는 수종의 초기 상태다.
    빌더에서 대상지별로 값을 나누어 넣으면 JSON 이 이 값을 대체한다.
    """
    return {"by_env": {env: spec for env in RESTORATION_ENVIRONMENTS}}


def _each_env(natural: SpeciesData, artificial: SpeciesData,
              quarry: SpeciesData) -> dict:
    """대상지별로 서로 다른 레코드를 부여한다 (원 자료에 근거가 있는 경우)."""
    return {"by_env": {
        RESTORATION_ENVIRONMENTS[0]: natural,
        RESTORATION_ENVIRONMENTS[1]: artificial,
        RESTORATION_ENVIRONMENTS[2]: quarry,
    }}


# 교목 (Tree) — 수종마다 대상지 3종의 레코드를 보유한다.
# 라벨/계수/범위 출처: 「기초 DB 자료」 시트 순번 1, 2, 3, 4, 5, 6, 7, 8, 9
#   순번 1·2·3 = 소나무의 대상지 3종. 그 외 수종은 대상지별 근거가 없어 세 대상지에
#   같은 값으로 초기화되며, 연 직경 생장량은 출처(MATLAB TreeGrowthMap)의 값을 쓴다.
TREE_BASE: dict[str, dict] = {
    "소나무":     _each_env(
        SpeciesData(0.0737, 2.5735, 0.5, 1, 15, 0.11, 0.20, 0.70),   # 순번 1 자연복원
        SpeciesData(0.0722, 2.6044, 0.5, 1, 22, 0.11, 0.20, 0.70),   # 순번 2 인공복원
        SpeciesData(0.1323, 2.2619, 0.5, 1, 25, 0.11, 0.20, 0.70),   # 순번 3 채석장
    ),
    "곰솔":       _all_env(SpeciesData(0.0679, 2.5770, 0.5, 1, 29, 0.24, 0.32, 0.32)),
    "편백":       _all_env(SpeciesData(0.3617, 2.0450, 0.5, 1, 50, 0.11, 0.23, 0.23)),
    "졸참나무":   _all_env(SpeciesData(0.2002, 2.3767, 0.5, 1, 30, 0.13, 0.30, 0.30)),
    "아까시나무": _all_env(SpeciesData(0.1391, 2.5016, 0.5, 1, 30, 0.14, 0.20, 0.20)),
    "붉가시나무": _all_env(SpeciesData(0.1926, 2.4300, 0.5, 1, 40, 0.12, 0.16, 0.16)),
    "신갈나무":   _all_env(SpeciesData(0.0147, 3.1075, 0.5, 6, 30, 0.40, 0.40, 0.40)),
}

# 관목 (Shrub, 15종).
# 공개 입력과 범위 표시는 RCD cm로 통일한다. 다만 기존 15개 상대생장식의
# 계수는 RCD mm로 적합되었으므로 식 평가 직전에만 cm×10 변환을 적용한다.
# 라벨/계수/범위 출처: 「기초 DB 자료」 시트 순번 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23, 21, 22, 24
def _legacy_shrub_species(*values: float) -> SpeciesData:
    return SpeciesData(*values, equation_diameter_unit="mm")


_SHRUB_SOURCE: dict[str, SpeciesData] = {
    "사철나무":     _legacy_shrub_species(0.0002,    2.50, 0.50,  6, 53, 0.30, 0.22, 0.22),
    "산철쭉":       _legacy_shrub_species(0.0003,    2.40, 0.50,  1, 22, 0.31, 0.17, 0.17),
    "조팝나무":     _legacy_shrub_species(0.00025,   2.60, 0.50,  5, 44, 0.20, 0.14, 0.14),
    # 순번 13 (Excel a=0.000022; MATLAB 원본 0.00022 의 1/10 — 회양목과 동일 패턴, Excel 채택)
    # 성장률은 MATLAB 원본 위치매칭값(0.38/0.25/0.25) 사용
    "화살나무":     _legacy_shrub_species(0.000022,  2.55, 0.50, 11, 67, 0.38, 0.25, 0.25),
    "회양목":       _legacy_shrub_species(0.000018,  2.70, 0.50,  8, 30, 0.24, 0.17, 0.17),
    "개나리":       _legacy_shrub_species(0.00028,   2.45, 0.50,  4, 26, 0.16, 0.16, 0.16),
    "남천":         _legacy_shrub_species(0.00031,   2.30, 0.50,  4, 35, 0.24, 0.22, 0.22),
    "덜꿩나무":     _legacy_shrub_species(0.00026,   2.50, 0.50,  7, 39, 0.35, 0.00, 0.00),
    "말발도리":     _legacy_shrub_species(0.00023,   2.60, 0.50,  4, 25, 0.30, 0.00, 0.00),
    "병꽃나무":     _legacy_shrub_species(0.00029,   2.40, 0.50,  6, 39, 0.30, 0.24, 0.24),
    "싸리":         _legacy_shrub_species(0.00015,   2.80, 0.50,  2, 17, 0.10, 0.06, 0.06),
    "수수꽃다리":   _legacy_shrub_species(0.00005,   2.64, 0.45,  5, 29, 0.25, 0.23, 0.23),
    "좀작살나무":   _legacy_shrub_species(0.0021,    2.65, 0.50,  7, 25, 0.24, 0.16, 0.16),
    "쥐똥나무":     _legacy_shrub_species(0.00019,   2.75, 0.50,  4, 35, 0.18, 0.21, 0.21),
    "흰말채나무":   _legacy_shrub_species(0.00027,   2.52, 0.50,  7, 52, 0.29, 0.26, 0.26),
}

# 관목도 교목과 같은 구조로 대상지 3종의 레코드를 보유한다. 원 자료에 대상지별
# 관목식이 없으므로 초기값은 세 대상지가 동일하며, 빌더에서 나누어 넣을 수 있다.
SHRUB_BASE: dict[str, dict] = {
    name: _all_env(spec) for name, spec in _SHRUB_SOURCE.items()
}


# ----- 대상지별 조회 함수 -----

def _record_for_env(entry: dict, environment: str) -> SpeciesData:
    """대상지 레코드 조회. 해당 대상지가 없으면 정의된 첫 대상지로 폴백한다."""
    by_env = entry.get("by_env") or {}
    spec = by_env.get(environment)
    if spec is not None:
        return spec
    if by_env:
        return next(iter(by_env.values()))
    # 아주 오래된 JSON 호환 (대상지 구분 없이 단일 레코드만 있던 시절)
    return entry["default"]

def growth_tier(species: str, environment: str) -> int:
    """수종·대상지의 생장 티어 (지정이 없으면 DEFAULT_GROWTH_TIER)."""
    try:
        tier = int((SPECIES_GROWTH_TIERS.get(species) or {}).get(environment, DEFAULT_GROWTH_TIER))
    except (TypeError, ValueError):
        return DEFAULT_GROWTH_TIER
    return tier if tier in GROWTH_TIERS else DEFAULT_GROWTH_TIER


def growth_factor(species: str, environment: str) -> float:
    """해당 수종·대상지에 적용할 연 직경 생장량 보정계수.

    우선순위: 수종별 예외(`SPECIES_GROWTH_FACTORS`) → 대상지 × 티어
    (`ENVIRONMENT_GROWTH_FACTORS[대상지][TIER_n]`) → 1.0(보정 없음).
    """
    per_species = SPECIES_GROWTH_FACTORS.get(species)
    if per_species is not None and environment in per_species:
        try:
            value = float(per_species[environment])
        except (TypeError, ValueError):
            value = 1.0
        return value if value > 0 else 1.0

    by_env = ENVIRONMENT_GROWTH_FACTORS.get(environment) or {}
    try:
        value = float(by_env.get(tier_key(growth_tier(species, environment)), 1.0))
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _apply_growth_factor(spec: SpeciesData, factor: float) -> SpeciesData:
    if factor == 1.0:
        return spec
    return replace(
        spec,
        growth_y10=spec.growth_y10 * factor,
        growth_y20=spec.growth_y20 * factor,
        growth_y21=spec.growth_y21 * factor,
    )


def tree_species_for_env(environment: str) -> dict[str, SpeciesData]:
    """주어진 대상지 유형의 {수종명: SpeciesData}.

    수종마다 보유한 대상지 3종의 레코드 중 해당 대상지 것을 쓰고, 그 레코드의
    연 직경 생장량에 대상지 × 티어 보정계수를 추가로 곱한다.
    """
    return {
        name: _apply_growth_factor(_record_for_env(entry, environment),
                                   growth_factor(name, environment))
        for name, entry in TREE_BASE.items()
    }


def shrub_species_for_env(environment: str) -> dict[str, SpeciesData]:
    """주어진 대상지 유형의 관목 레코드 (교목과 동일한 규칙)."""
    return {
        name: _apply_growth_factor(_record_for_env(entry, environment),
                                   growth_factor(name, environment))
        for name, entry in SHRUB_BASE.items()
    }


def tree_names() -> list[str]:
    """교목 수종(기본명) 목록."""
    return list(TREE_BASE.keys())


def shrub_names() -> list[str]:
    return list(SHRUB_BASE.keys())


# 하위 호환 기본 export (환경 미지정 = 기본 환경). 기존 코드/검증 스크립트가 참조.
TREE_SPECIES = tree_species_for_env(DEFAULT_ENVIRONMENT)
SHRUB_SPECIES = shrub_species_for_env(DEFAULT_ENVIRONMENT)
TREE_NAMES = list(TREE_SPECIES.keys())
SHRUB_NAMES = list(SHRUB_SPECIES.keys())


def _positive(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def parse_growth_settings(raw_factors, raw_tiers, shrub_names=()) -> tuple[dict, dict]:
    """JSON 의 보정계수·티어 → (ENVIRONMENT_GROWTH_FACTORS, SPECIES_GROWTH_TIERS).

    구버전(대상지 × 교목/관목 6개) 파일은 교목 계수 → 티어 1, 관목 계수 → 티어 2 로
    옮기고, 티어 지정이 없으면 관목 수종을 티어 2 에 두어 계산 결과를 그대로 유지한다.
    """
    factors = _unit_factors()
    legacy_used = False
    for env, slot in (raw_factors.items() if isinstance(raw_factors, dict) else ()):
        if not isinstance(slot, dict):
            continue
        target = factors.setdefault(env, {tier_key(t): 1.0 for t in GROWTH_TIERS})
        has_tiers = any(tier_key(t) in slot for t in GROWTH_TIERS)
        for t in GROWTH_TIERS:
            value = _positive(slot.get(tier_key(t)))
            if value is not None:
                target[tier_key(t)] = value
        if not has_tiers:
            for section, t in _LEGACY_SECTION_TIER.items():
                value = _positive(slot.get(section))
                if value is not None:
                    target[tier_key(t)] = value
                    legacy_used = legacy_used or value != 1.0

    tiers: dict[str, dict[str, int]] = {}
    for species, envs in (raw_tiers.items() if isinstance(raw_tiers, dict) else ()):
        if not isinstance(envs, dict):
            continue
        slot = {}
        for env, tier in envs.items():
            try:
                tier = int(tier)
            except (TypeError, ValueError):
                continue
            if tier in GROWTH_TIERS:
                slot[env] = tier
        if slot:
            tiers[species] = slot
    if legacy_used and not isinstance(raw_tiers, dict):
        tiers = {name: {env: 2 for env in factors} for name in shrub_names}
    return factors, tiers


def _load_from_bundled_json() -> None:
    """통합 species_data.json(또는 구 carbon1_species_data.json)으로
    TREE_BASE·SHRUB_SPECIES 를 덮어쓴다.

    파일 탐색 우선순위 (처음 발견된 파일을 사용):
      exe 실행 시 — ① exe 옆 디렉터리 (사용자 업데이트) → ② sys._MEIPASS (번들 기본값)
      개발 모드   — ③ 프로젝트 루트
    각 디렉터리 안에서는 통합본(species_data.json) 을 우선하고,
    없으면 구버전(carbon1_species_data.json) 을 사용한다.
    JSON 파싱 실패 시 기존 Python 상수를 그대로 유지한다.
    """
    import json as _json
    import pathlib as _pl
    import sys as _sys

    _meipass = getattr(_sys, '_MEIPASS', None)
    if _meipass:
        _candidates = [_pl.Path(_sys.executable).parent, _pl.Path(_meipass)]
    else:
        _candidates = [_pl.Path(__file__).resolve().parent.parent]

    _json_path = next(
        (_b / _fn
         for _b in _candidates
         for _fn in ('species_data.json', 'carbon1_species_data.json')
         if (_b / _fn).exists()),
        None,
    )
    if _json_path is None:
        return

    try:
        _raw = _json.loads(_json_path.read_text(encoding='utf-8'))
    except Exception:
        return

    # 영문 표기(SPECIES_EN·ENVIRONMENTS_EN)도 같은 JSON 에서 가져온다 —
    # Equation Library Manager로 새 수종을 넣으면 학명도 함께 갱신되도록.
    from .i18n import load_json_overrides as _load_i18n_overrides
    _load_i18n_overrides(_raw)

    global TREE_BASE, SHRUB_BASE, SHRUB_SPECIES, TREE_SPECIES, TREE_NAMES, SHRUB_NAMES
    global ENVIRONMENT_GROWTH_FACTORS, SPECIES_GROWTH_FACTORS, SPECIES_GROWTH_TIERS

    _schema = _raw.get('_schema') if isinstance(_raw.get('_schema'), dict) else {}
    _shrub_equation_unit = _schema.get('SHRUB_SPECIES_equation_diameter_unit', 'mm')
    if _shrub_equation_unit not in ('cm', 'mm'):
        _shrub_equation_unit = 'mm'

    def _parse_section(_section: dict, _unit: str) -> dict:
        """대상지별 레코드(8개 값) 를 읽는다.

        `by_env` 가 있으면 그것만 쓴다(대상지 3종 각각의 전체 레코드). 구버전
        JSON 의 단일 레코드(`default` 또는 배열)는 세 대상지에 같은 값으로 펼친다.
        """
        _out: dict = {}
        for _name, _entry in (_section or {}).items():
            _by_env: dict = {}
            if isinstance(_entry, dict):
                for _env, _arr in (_entry.get('by_env') or {}).items():
                    if not isinstance(_arr, (list, tuple)) or len(_arr) < 8:
                        continue
                    try:
                        _by_env[_env] = SpeciesData(
                            *(float(_v) for _v in _arr[:8]),
                            equation_diameter_unit=_unit,
                        )
                    except (TypeError, ValueError):
                        continue
                if not _by_env and isinstance(_entry.get('default'), (list, tuple)):
                    try:
                        _single = SpeciesData(*_entry['default'],
                                              equation_diameter_unit=_unit)
                        _by_env = {_env: _single for _env in RESTORATION_ENVIRONMENTS}
                    except (TypeError, ValueError):
                        pass
            elif isinstance(_entry, (list, tuple)):
                try:
                    _single = SpeciesData(*_entry, equation_diameter_unit=_unit)
                    _by_env = {_env: _single for _env in RESTORATION_ENVIRONMENTS}
                except (TypeError, ValueError):
                    pass
            if _by_env:
                _out[_name] = {'by_env': _by_env}
        return _out

    _new_tree = _parse_section(_raw.get('TREE_BASE'), 'cm')
    _new_shrub_base = _parse_section(_raw.get('SHRUB_SPECIES'), _shrub_equation_unit)

    # 대상지 × 티어 보정계수, 수종별 티어, 수종별 예외 (없으면 기본 1.0 · 티어 1)
    _shrub_keys = list((_new_shrub_base or SHRUB_BASE).keys())
    ENVIRONMENT_GROWTH_FACTORS, SPECIES_GROWTH_TIERS = parse_growth_settings(
        _raw.get('ENVIRONMENT_GROWTH_FACTORS'), _raw.get('SPECIES_GROWTH_TIERS'), _shrub_keys)

    _raw_species_factors = _raw.get('SPECIES_GROWTH_FACTORS')
    if isinstance(_raw_species_factors, dict):
        _new_species_factors: dict = {}
        for _species, _envs in _raw_species_factors.items():
            if not isinstance(_envs, dict):
                continue
            _slot = {}
            for _env, _value in _envs.items():
                try:
                    _value = float(_value)
                except (TypeError, ValueError):
                    continue
                if _value > 0:
                    _slot[_env] = _value
            if _slot:
                _new_species_factors[_species] = _slot
        SPECIES_GROWTH_FACTORS = _new_species_factors

    if _new_tree:
        TREE_BASE = _new_tree
    if _new_shrub_base:
        SHRUB_BASE = _new_shrub_base

    TREE_SPECIES = tree_species_for_env(DEFAULT_ENVIRONMENT)
    SHRUB_SPECIES = shrub_species_for_env(DEFAULT_ENVIRONMENT)
    TREE_NAMES = list(TREE_SPECIES.keys())
    SHRUB_NAMES = list(SHRUB_SPECIES.keys())


_load_from_bundled_json()
