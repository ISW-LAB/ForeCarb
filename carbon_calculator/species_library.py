# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""Unified equation library. Missing growth uses the explicit assumptions in
GROWTH_ASSUMPTIONS.md through the shared projections module.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from . import data as _data
from . import data2 as _data2
from .data import (
    DEFAULT_ENVIRONMENT, SpeciesData, growth_factor, shrub_species_for_env,
    tree_species_for_env,
)
from .data2 import CARBON_FACTOR, EquationSpecies, species_map
from .equation_eval import EvaluationError, evaluate
from .i18n import species_name, tr

KIND_TREE = "tree"
KIND_SHRUB = "shrub"

SOURCE_CORE = "core"
SOURCE_EXTENSION = "extension"

ORIGIN_DOMESTIC = "domestic"
ORIGIN_FOREIGN = "foreign"

# 직경축 곡선을 만들 때 사용할 표본 점 개수.
DIAMETER_CURVE_POINTS = 60

# 유효범위가 제공되지 않은 레코드(55종 중 20건)의 직경축 표현 폭.
# 출처가 정의역을 주지 않으므로 입력값 주변의 좁은 구간만 그리고,
# 호출측이 "유효범위 미제공"임을 화면에 함께 표시한다.
UNBOUNDED_SWEEP_LOW_RATIO = 0.5
UNBOUNDED_SWEEP_HIGH_RATIO = 1.5

# 로그 항이 들어간 식에서 X=0 이 발산하지 않도록 하는 하한.
_MIN_POSITIVE_X = 1e-6

# 설명변수가 DBH·RCD 가 아니어서 변수 기준으로 분류할 수 없는 레코드.
#   서양개암나무(지상부): 변수가 '수고 h + 엽면적지수 LAI' 이며 개암나무류는
#   관목이므로 관목으로 고정한다.
KIND_OVERRIDES: dict[str, str] = {
    "서양개암나무(지상부)": KIND_SHRUB,
}


class LibraryError(Exception):
    """레코드 범위 검증·식 평가 실패. 사용자에게 보여줄 번역된 메시지를 담는다."""


def _classify_kind(key: str, var1_label: str) -> str:
    """설명변수로 교목/관목을 판정한다 (RCD → 관목, 그 외 → 교목)."""
    override = KIND_OVERRIDES.get(key)
    if override is not None:
        return override
    return KIND_SHRUB if "RCD" in var1_label.upper() else KIND_TREE


@dataclass(frozen=True)
class LibraryRecord:
    """평가 화면이 다루는 수종 레코드 1건 (core·extension 공통 표현)."""

    key: str                       # 계산·집계에 쓰는 국명 키
    kind: str                      # KIND_TREE | KIND_SHRUB
    source: str                    # SOURCE_CORE | SOURCE_EXTENSION
    origin: str | None             # extension 만: ORIGIN_DOMESTIC | ORIGIN_FOREIGN
    var1_label: str                # 첫 번째 설명변수 라벨 ("DBH (cm)" 등)
    range_min: float | None
    range_max: float | None
    species_data: SpeciesData | None = None   # core 만
    equation: str | None = None               # extension 만
    var2_label: str | None = None             # extension 다변수만
    var2_min: float = 0.0
    var2_max: float = 100.0
    var2_default: float = 10.0
    growth_factor: float = 1.0                # extension 만: 가정 생장률에 곱할 티어 보정계수

    # ----- 분류 질의 -----

    @property
    def is_core(self) -> bool:
        return self.source == SOURCE_CORE

    @property
    def is_extension(self) -> bool:
        return self.source == SOURCE_EXTENSION

    @property
    def has_range(self) -> bool:
        return self.range_min is not None and self.range_max is not None

    @property
    def is_multivar(self) -> bool:
        """두 번째 변수(수고·임분밀도·LAI·길이) 입력이 필요한지."""
        return self.var2_label is not None

    @property
    def supports_year_projection(self) -> bool:
        """기존 생장량 또는 명시적 가정으로 연도별 추정이 가능한지."""
        return self.species_data is not None or self.equation is not None

    # ----- 표시용 -----

    @property
    def predictor_short(self) -> str:
        """축 라벨에 쓰는 짧은 변수명 ("DBH" · "RCD" · 원 라벨)."""
        upper = self.var1_label.upper()
        if "DBH" in upper:
            return "DBH"
        if "RCD" in upper:
            return "RCD"
        return self.var1_label

    def formula_text(self) -> str:
        """다이얼로그에 보여줄 상대생장식 문자열."""
        if self.is_core and self.species_data is not None:
            sp = self.species_data
            x_term = "(10 × X)" if sp.equation_diameter_unit == "mm" else "X"
            return (f"Y  =  {sp.a:g}  ×  {x_term}^{sp.b:g}"
                    f"      C  =  Y  ×  {sp.cf:g}  ×  N")
        return f"{self.equation}      C  =  Y  ×  {CARBON_FACTOR:g}  ×  N"

    def range_text(self) -> str:
        """유효범위 표시 문자열. 범위가 없으면 안내 문구."""
        if not self.has_range:
            return tr("유효범위 미제공 (출처에 정의역 없음)")
        return f"{self.range_min:g} ~ {self.range_max:g}  ({self.predictor_short})"


# ─────────────────────────── 레코드 구성 ───────────────────────────

def _core_records(kind: str, environment: str = DEFAULT_ENVIRONMENT
                  ) -> dict[str, LibraryRecord]:
    """core 22종. 대상지별 식 오버라이드와 생장량 보정계수가 반영된 레코드를 쓴다."""
    table = (tree_species_for_env(environment) if kind == KIND_TREE
             else shrub_species_for_env(environment))
    label = "DBH (cm)" if kind == KIND_TREE else "RCD (cm)"
    return {
        name: LibraryRecord(
            key=name,
            kind=kind,
            source=SOURCE_CORE,
            origin=None,
            var1_label=label,
            range_min=float(sp.diameter_min),
            range_max=float(sp.diameter_max),
            species_data=sp,
        )
        for name, sp in table.items()
    }


def _extension_record(key: str, sp: EquationSpecies, origin: str,
                      environment: str = DEFAULT_ENVIRONMENT) -> LibraryRecord:
    return LibraryRecord(
        key=key,
        kind=_classify_kind(key, sp.var1_label),
        source=SOURCE_EXTENSION,
        origin=origin,
        var1_label=sp.var1_label,
        range_min=(float(sp.diameter_min) if sp.diameter_min is not None else None),
        range_max=(float(sp.diameter_max) if sp.diameter_max is not None else None),
        equation=sp.equation,
        var2_label=sp.var2_label,
        var2_min=float(sp.var2_min),
        var2_max=float(sp.var2_max),
        var2_default=float(sp.var2_default),
        growth_factor=growth_factor(key, environment),
    )


def all_records(environment: str = DEFAULT_ENVIRONMENT) -> dict[str, LibraryRecord]:
    """77개 레코드 전체 (core → extension 순). 키가 겹치면 core 를 유지한다.

    `data`·`data2` 는 import 시 `species_data.json` 으로 덮어써질 수 있으므로
    호출 시점에 다시 구성한다. core 레코드는 `environment` 에 맞게 해석된다.
    """
    records: dict[str, LibraryRecord] = {}
    records.update(_core_records(KIND_TREE, environment))
    records.update(_core_records(KIND_SHRUB, environment))
    for origin in (ORIGIN_DOMESTIC, ORIGIN_FOREIGN):
        for key, sp in species_map(origin, environment).items():
            if key in records:
                continue  # core 레코드가 우선 (현재 키 충돌은 없음)
            records[key] = _extension_record(key, sp, origin, environment)
    return records


def records_for_kind(kind: str, environment: str = DEFAULT_ENVIRONMENT
                     ) -> dict[str, LibraryRecord]:
    """해당 분류(교목/관목)의 레코드. core 를 먼저, 이어서 extension 을 둔다."""
    everything = all_records(environment)
    core = {k: r for k, r in everything.items()
            if r.kind == kind and r.is_core}
    extension = {k: r for k, r in everything.items()
                 if r.kind == kind and r.is_extension}
    core.update(extension)
    return core


def core_records_for_kind(kind: str, environment: str = DEFAULT_ENVIRONMENT
                          ) -> dict[str, SpeciesData]:
    """3D 시각화처럼 성장차가 필요한 경로가 쓰는 core 전용 맵."""
    return {k: r.species_data for k, r in _core_records(kind, environment).items()
            if r.species_data is not None}


# ─────────────────────────── 계산 ───────────────────────────

def check_range(record: LibraryRecord, x: float) -> None:
    """유효범위를 벗어나면 `LibraryError`. 범위가 없는 레코드는 검사하지 않는다."""
    if not record.has_range:
        return
    if record.range_min <= x <= record.range_max:
        return
    if record.is_core:
        raise LibraryError(
            tr("{species}의 유효 직경 범위는 {vmin:g} {unit} ~ {vmax:g} {unit} 입니다.")
            .format(species=species_name(record.key), vmin=record.range_min,
                    vmax=record.range_max, unit="cm")
        )
    raise LibraryError(
        tr("{species} 의 유효 {label} 범위는 {vmin:g} ~ {vmax:g} 입니다. (입력: {value:g})")
        .format(species=species_name(record.key), label=record.var1_label,
                vmin=record.range_min, vmax=record.range_max, value=x)
    )


def carbon_per_individual(record: LibraryRecord, x: float,
                          var2: float | None = None) -> float:
    """개체 1주의 탄소저장량 (kgC). 범위 검사는 하지 않는다(`check_range` 별도 호출).

    core 는 `a·X^b·CF`(계수가 mm 기준이면 식 평가 직전에만 10배 변환),
    extension 은 식 문자열을 평가한 바이오매스에 `CARBON_FACTOR` 를 곱한다.
    """
    if record.is_core and record.species_data is not None:
        sp = record.species_data
        biomass = sp.a * (sp.to_equation_diameter(float(x)) ** sp.b)
        return biomass * sp.cf

    if record.equation is None:
        raise LibraryError(tr("인식할 수 없는 식 형식: {equation!r}").format(equation=None))

    h = var2 if record.is_multivar else None
    try:
        biomass = evaluate(record.equation, float(x), h)
    except EvaluationError as exc:
        raise LibraryError(str(exc)) from exc
    if not math.isfinite(biomass) or biomass < 0:
        raise LibraryError(
            tr("{species} 의 식 평가값이 유효하지 않음 (Y={value})")
            .format(species=species_name(record.key), value=biomass)
        )
    return biomass * CARBON_FACTOR


def carbon_total(record: LibraryRecord, x: float, quantity: int,
                 var2: float | None = None) -> float:
    """수량을 곱한 총 탄소저장량 (kgC)."""
    return carbon_per_individual(record, x, var2) * int(quantity)


# ─────────────────────────── 직경축 곡선 ───────────────────────────

def diameter_axis(record: LibraryRecord, x: float,
                  points: int = DIAMETER_CURVE_POINTS) -> np.ndarray:
    """직경축 표본점. 유효범위가 있으면 그 구간, 없으면 입력값 주변 구간.

    로그 항이 있는 식에서 0 이 발산하지 않도록 하한을 양수로 고정한다.
    """
    if record.has_range:
        low = float(record.range_min)
        high = float(record.range_max)
    else:
        value = max(float(x), _MIN_POSITIVE_X)
        low = value * UNBOUNDED_SWEEP_LOW_RATIO
        high = value * UNBOUNDED_SWEEP_HIGH_RATIO

    low = max(low, _MIN_POSITIVE_X)
    if high <= low:
        high = low * (1.0 + UNBOUNDED_SWEEP_HIGH_RATIO)
    axis = np.linspace(low, high, max(2, int(points)))

    # 사용자가 입력한 값이 축에 반드시 포함되도록 가장 가까운 점을 대체한다
    # (호버 툴팁에서 입력값의 탄소량을 그대로 읽을 수 있게 한다).
    if low <= x <= high:
        axis[int(np.abs(axis - x).argmin())] = float(x)
    return axis


def carbon_by_diameter(record: LibraryRecord, axis: Iterable[float],
                       quantity: int, var2: float | None = None) -> np.ndarray:
    """직경축 각 점의 총 탄소저장량. 평가 불가한 점은 NaN 으로 남겨 선을 끊는다."""
    axis_arr = np.asarray(axis, dtype=float)

    if record.is_core and record.species_data is not None:
        sp = record.species_data
        equation_x = sp.to_equation_diameter(axis_arr)
        return sp.a * (equation_x ** sp.b) * sp.cf * int(quantity)

    values = np.empty(axis_arr.size, dtype=float)
    for i, x in enumerate(axis_arr):
        try:
            values[i] = carbon_per_individual(record, float(x), var2) * int(quantity)
        except LibraryError:
            values[i] = np.nan
    return values


# ─────────────────────────── 식 식별자 · 라이브러리 식별 ───────────────────────────

# 컬렉션 코드 → species_data.json 의 섹션 이름. 보고서의 '식 ID' 는 이 코드에
# 섹션 안 순번(1부터)을 붙인 값이다 (예: T01, S10, D21, I03).
COLLECTION_SECTIONS: dict[str, str] = {
    "T": "TREE_BASE",
    "S": "SHRUB_SPECIES",
    "D": "DOMESTIC_SPECIES",
    "I": "FOREIGN_SPECIES",
}


def _collection_keys() -> dict[str, list[str]]:
    """컬렉션별 레코드 키를 라이브러리 파일의 순서대로 돌려준다.

    `data`·`data2` 의 모듈 전역은 JSON 로드 때 교체되므로 호출 시점에 읽는다.
    """
    return {
        "T": list(_data.TREE_BASE.keys()),
        "S": list(_data.SHRUB_BASE.keys()),
        "D": list(_data2.DOMESTIC_BY_ENV.keys()),
        "I": list(_data2.FOREIGN_BY_ENV.keys()),
    }


def equation_ids() -> dict[str, str]:
    """{레코드 키: 식 ID}. ID = 컬렉션 코드(T·S·D·I) + 섹션 안 순번 두 자리.

    순번은 불러온 `species_data.json` 의 순서를 따르므로 같은 라이브러리 파일에서는
    항상 같은 값이다. 라이브러리를 고치면 순번이 달라질 수 있으므로 보고서에는
    레코드 키와 라이브러리 지문(`library_identity`)을 함께 기록한다.
    """
    ids: dict[str, str] = {}
    for code, keys in _collection_keys().items():
        for index, key in enumerate(keys, start=1):
            ids.setdefault(key, f"{code}{index:02d}")
    return ids


def equation_id(key: str) -> str:
    """레코드 키의 식 ID. 라이브러리에 없는 키는 빈 문자열."""
    return equation_ids().get(key, "")


def collection_code(record: LibraryRecord) -> str:
    """레코드가 속한 컬렉션 코드 (T 교목 · S 관목 · D 국내 · I 국외)."""
    if record.is_core:
        return "T" if record.kind == KIND_TREE else "S"
    return "D" if record.origin == ORIGIN_DOMESTIC else "I"


def collection_label(code: str) -> str:
    """컬렉션 코드의 표시 이름 (현재 언어)."""
    return {"T": tr("교목"), "S": tr("관목"), "D": tr("국내"), "I": tr("국외")}.get(code, code)


def library_identity() -> dict:
    """불러온 식 라이브러리의 식별 정보 — 파일 이름, 스키마 버전, 내용 지문.

    지문은 JSON 내용을 정규화(키 정렬·공백 제거)한 문자열의 SHA-256 이므로
    줄바꿈 방식이나 들여쓰기가 달라도 내용이 같으면 같은 값이 나온다.
    파일을 찾지 못하면(내장 기본값 사용) 값이 모두 None 이다.
    """
    import hashlib
    import json
    import pathlib
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates = [pathlib.Path(sys.executable).parent, pathlib.Path(meipass)]
    else:
        candidates = [pathlib.Path(__file__).resolve().parent.parent]
    for base in candidates:
        path = base / "species_data.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 읽지 못하면 내장 기본값이 쓰인다
            continue
        canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        schema = raw.get("_schema") if isinstance(raw.get("_schema"), dict) else {}
        return {
            "file": path.name,
            "schema_version": schema.get("version"),
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
    return {"file": None, "schema_version": None, "sha256": None}
