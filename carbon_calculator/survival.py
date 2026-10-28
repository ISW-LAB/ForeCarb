# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""수종별 생존률을 연차별 개체 수와 탄소저장량에 반영한다.

세종수목원 탄소계산기(MATLAB 버전1)는 수종마다 표준지 '생존율' 하나를 받아
**현재 시점의 수량에 곱했다** (탄소 = B × CF × N × 생존율). 이 모듈은 그 값을
'현재 생존율' S0 으로 그대로 쓰고, 여기에 '연간 생존율' s 를 해마다 누적한다.

    N(t) = N0 × S0 × s^t        (t = 경과 연차, S0·s 는 0~1)

탄소량은 개체 수에 비례하므로 생존률 반영 곡선은 '전량 생존' 곡선에 같은
계수를 곱한 값이다. 기본값 100 % / 100 % 는 기존(전량 생존) 결과와 같다.
"""
from __future__ import annotations

import numpy as np

DEFAULT_SURVIVAL_PCT = 100.0
MIN_SURVIVAL_PCT = 0.0
MAX_SURVIVAL_PCT = 100.0


def validate_pct(value: float, what: str = "survival") -> float:
    """0~100 % 범위의 유한한 값인지 확인하고 float 로 돌려준다."""
    v = float(value)
    if not np.isfinite(v) or v < MIN_SURVIVAL_PCT or v > MAX_SURVIVAL_PCT:
        raise ValueError(f"{what} must be between 0 and 100 %, got {value!r}")
    return v


def survival_factors(initial_pct: float, annual_pct: float, years) -> np.ndarray:
    """연차별 생존 비율 S0 × s^t (0~1) 배열."""
    s0 = validate_pct(initial_pct, "initial survival") / 100.0
    s = validate_pct(annual_pct, "annual survival") / 100.0
    t = np.asarray(years, dtype=float)
    return s0 * np.power(s, t)


def surviving_individuals(quantity: float, initial_pct: float, annual_pct: float,
                          years) -> np.ndarray:
    """연차별 생존 개체 수 (기댓값이라 소수일 수 있다)."""
    return float(quantity) * survival_factors(initial_pct, annual_pct, years)


def is_default(initial_pct: float, annual_pct: float) -> bool:
    return (abs(float(initial_pct) - DEFAULT_SURVIVAL_PCT) < 1e-9
            and abs(float(annual_pct) - DEFAULT_SURVIVAL_PCT) < 1e-9)
