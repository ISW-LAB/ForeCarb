# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
ForeCarb Equation Library Manager (self-contained).

이 프로그램은 **ForeCarb(main.py)의 전체 코드 로직을 내부에 내장**하고
있어, 소스 폴더 없이 이 exe 하나만으로 새 수종 데이터(JSON)를 반영한 실행파일을
만들 수 있다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
동작 방식
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[① exe 재빌드 — 자체 완결]  통합 species_data.json 을 입력받아,
   내장된 소스(carbon_calculator + main.py + build_exe.py)를 임시 작업폴더로
   풀고 그 안에 JSON 을 넣은 뒤 PyInstaller 로 새 ForeCarb.exe 를 빌드한다.
   → 소스 트리를 옆에 둘 필요 없음. (단, PC 에 Python 3.10+ 이 있어야 컴파일 가능)

[② JSON 적용 — Python 불필요]  기존 ForeCarb.exe 옆에 JSON 을 복사만 한다.
   다음 실행 시 자동 반영. 재빌드가 필요 없을 때 가장 빠른 경로.

JSON 양식:  species_data.json (통합본 — 교목·관목·국내·국외 4개 섹션)

실행:
    python updater_app.py        (개발 모드)
    FORECAST-SW-Equation-Library-Manager.exe  (배포 모드 — 단독 실행)
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QSizePolicy, QStyledItemDelegate, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from carbon_calculator.equation_eval import evaluate as _safe_equation_evaluate
from carbon_calculator.qt_locale import apply_dialog_font, install_qt_translator
from carbon_calculator.species_names_en import ENVIRONMENT_EN as _ENVIRONMENT_EN
from carbon_calculator.version import __version__
from carbon_calculator.typography import (
    BODY_PT, CAPTION_PT, SMALL_PT, TITLE_PT, font_family, scaled_point_size,
)

# ── 표시 언어 ────────────────────────────────────────────────────────────
# 이 앱은 표시문자열에 자체 대응표를 사용한다. 수식 검증은 ForeCarb와 같은
# 허용목록 기반 평가기를 공유한다. 언어 설정은 같은 QSettings 키를 공유해
# 두 앱의 표시 언어가 함께 움직인다. 기존 설치의 설정 호환성을 위해 키는 유지한다.
_SETTINGS_ORG = "SejongArboretum"
_SETTINGS_APP = "CarbonStorageModule"
_SETTINGS_KEY = "language"

_EN: dict[str, str] = {
    "EXE 파일 이름": "EXE file name",
    "사용할 EXE 파일 이름을 입력하세요.": "Enter the output EXE file name.",
    "파일 이름에는 경로 또는 특수문자를 사용할 수 없습니다.": "The file name cannot contain a path or invalid characters.",
    "사용할 수 없는 파일 이름입니다.": "This file name is not allowed.",
    "수종 데이터 업데이터 (자체 완결형) - ForeCarb v{version}":
        "ForeCarb Equation Library Manager (self-contained, v{version})",
    "수종 데이터 JSON (통합 species_data.json)":
        "Species data JSON (combined species_data.json)",
    "— 파일을 선택하면 검증됩니다": "— select a file to validate it",
    "파일을 찾을 수 없습니다.": "File not found.",
    "열기...": "Open...",
    "폴더...": "Folder...",
    "파일/폴더 경로를 선택하거나 직접 입력하세요":
        "Choose a file or folder, or type a path",
    "① exe 재빌드   —   내장 소스로 새 ForeCarb.exe 생성 (권장)":
        "① Rebuild Assessment Application — build a new ForeCarb executable from the bundled "
        "sources (recommended)",
    "출력 폴더 (exe 저장 위치)": "Output folder (where the executable is written)",
    "새 exe 빌드 (PyInstaller)": "Build new executable (PyInstaller)",

    # ── 대상지별 편집 ──
    "수종별 상대생장식 (대상지별 · 추가/수정/삭제)":
        "Allometric equations by site category (add / edit / delete)",
    "성장률 보정계수": "Growth factor",
    "생장 티어": "Growth tier",
    "티어 {n}": "Tier {n}",
    "{where}: '{name}' 의 생장 티어는 1, 2, 3 중 하나여야 합니다":
        "{where}: the growth tier of '{name}' must be 1, 2 or 3",
    "각 수종의 연 직경 생장량에 그 수종 티어의 계수를 곱합니다 (1.0 = 보정 없음). "
    "티어는 표의 '생장 티어' 열에서 수종마다 지정합니다.":
        "Each species' annual diameter increment is multiplied by the factor of its tier "
        "(1.0 = no correction). Set each species' tier in the 'Growth tier' column.",
    "핵심": "Core",
    "최소": "Min",
    "최대": "Max",
    "{n}개 수종을 세 대상지에서 모두 삭제할까요?\n{names}":
        "Delete {n} species from all three site categories?\n{names}",
    "{where}: '{name}' 의 상대생장식이 비어 있습니다":
        "{where}: the allometric equation for '{name}' is empty",
    "{where}: '{name}' 식 평가 실패 — {error}":
        "{where}: could not evaluate the equation for '{name}' — {error}",
    "준비": "Ready",
    "빌드 중...": "Building...",
    "빌드 완료!": "Build complete",
    "빌드 실패 — 로그 확인": "Build failed — check the log",
    "먼저 species_data.json 을 선택하세요.": "Select species_data.json first.",
    "JSON 오류: {msg}": "JSON error: {msg}",
    "출력 폴더를 지정하세요.": "Specify an output folder.",
    "② JSON 적용   —   기존 exe 옆에 복사만 (Python 불필요)":
        "② Apply JSON — deploy it to an existing Assessment Application (no Python required)",
    "ForeCarb.exe 위치": "Location of the ForeCarb Assessment Application",
    "찾기...": "Browse...",
    "JSON 적용 (복사)": "Apply JSON (copy)",
    "완료 — JSON 복사됨": "Done — JSON copied",
    "JSON 검증에 실패했습니다 (상단 상태 확인).":
        "JSON validation failed (see the status above).",
    "ForeCarb.exe 위치를 선택하세요.":
        "Select the location of the ForeCarb Assessment Application.",
    "로그": "Log",
    "통합 species_data.json 선택": "Select the combined species_data.json",
    "JSON 파일 (*.json)": "JSON file (*.json)",
    "출력 폴더 선택": "Select output folder",
    "ForeCarb.exe 선택": "Select the ForeCarb Assessment Application",
    "실행 파일 (*.exe)": "Executable (*.exe)",
    # 검증 결과
    "JSON 파싱 오류: {error}": "JSON parse error: {error}",
    "유효한 수종 섹션이 없습니다. TREE_BASE / SHRUB_SPECIES / DOMESTIC_SPECIES / "
    "FOREIGN_SPECIES 중 하나 이상이 필요합니다.":
        "No valid species section found. At least one of TREE_BASE, SHRUB_SPECIES, "
        "DOMESTIC_SPECIES or FOREIGN_SPECIES is required.",
    "교목 {tree} · 관목 {shrub} · 국내 {dom} · 국외 {for_} 종":
        "{tree} trees · {shrub} shrubs · {dom} domestic · {for_} international species",
    # 빌드 워커
    "Python 인터프리터를 찾을 수 없습니다. Python 3.10+ 를 설치하세요.":
        "No Python interpreter found. Please install Python 3.10 or later.",
    "내장 소스를 찾을 수 없습니다: {path}\nupdater 를 build_updater.py 로 다시 빌드하세요.":
        "Bundled sources not found: {path}\nRebuild the Equation Library Manager with build_updater.py.",
    "[1/4] 작업폴더 준비: {path}": "[1/4] Preparing work folder: {path}",
    "[2/4] 수종 데이터 적용: {src} → {dst}":
        "[2/4] Applying species data: {src} → {dst}",
    "[3/4] 빌드 시작: {cmd}": "[3/4] Starting build: {cmd}",
    "      (최초 실행 시 빌드 전용 venv 생성으로 수 분 소요)":
        "      (the first run creates a dedicated build venv and takes a few minutes)",
    "PyInstaller 빌드가 실패했습니다. 위 로그를 확인하세요.":
        "The PyInstaller build failed. Check the log above.",
    "산출물을 찾을 수 없습니다: {path}": "Build output not found: {path}",
    "[4/4] 산출물 복사 → {path}": "[4/4] Copying build output → {path}",
    "[오류] {error}": "[Error] {error}",
    "[완료] 새 실행파일: {path}": "[Done] New executable: {path}",
    "[실패] {error}": "[Failed] {error}",
    "[완료] {name} → {path}": "[Done] {name} → {path}",
    "[정리] 구버전 JSON 제거: {names}": "[Cleanup] removed legacy JSON: {names}",
    "ForeCarb.exe 를 다시 실행하면 새 수종 데이터가 적용됩니다.":
        "Restart the ForeCarb Assessment Application to load the new species data.",
    # 언어 선택
    "언어 / Language": "Language",
    "한국어": "한국어",
    "English": "English",
    # ── 수종 데이터 편집기 ──
    "수종별 상대생장식 (JSON 미리보기 · 추가/수정/삭제)":
        "Growth equations by species (JSON preview · add / edit / delete)",
    "교목 (TREE_BASE)": "Trees (TREE_BASE)",
    "관목 (SHRUB_SPECIES)": "Shrubs (SHRUB_SPECIES)",
    "국내 수종 (DOMESTIC_SPECIES)": "Domestic species (DOMESTIC_SPECIES)",
    "국외 수종 (FOREIGN_SPECIES)": "International species (FOREIGN_SPECIES)",
    "수종명": "Species name", "학명": "Scientific name", "구분": "Type",
    "최소직경(cm)": "Min diameter (cm)", "최대직경(cm)": "Max diameter (cm)",
    "성장률(~10y)": "Growth rate (~10 y)", "성장률(11~20y)": "Growth rate (11–20 y)",
    "성장률(21y~)": "Growth rate (21 y~)",
    "최소직경": "Min", "최대직경": "Max",
    "생장량(1~10년)": "Growth rate (1–10 y)", "생장량(11~20년)": "Growth rate (11–20 y)",
    "생장량(21~30년)": "Growth rate (21–30 y)",
    "상대생장식": "Allometric equation", "범위 최소": "Range min", "범위 최대": "Range max",
    "변수1 라벨": "Variable 1 label", "변수2 라벨": "Variable 2 label",
    "변수2 최소": "Variable 2 min", "변수2 최대": "Variable 2 max", "변수2 기본값": "Variable 2 default",
    "셀을 더블클릭해 수정합니다 · 범위를 비우면 '범위 검사 없음' · 변수2 라벨을 비우면 단일변수 식 · "
    "식은 X(첫 변수)·H(두 번째 변수)·^·ln·exp 를 사용합니다":
        "Double-click a cell to edit · leave the range blank for 'no range check' · leave the "
        "variable-2 label blank for a single-variable equation · equations use X (first variable), "
        "H (second variable), ^, ln and exp",
    "모든 표시 직경은 cm입니다 · 교목식은 X=DBH(cm), 기존 관목식은 계수를 보존하여 "
    "X=10×RCD(cm)로 평가합니다":
        "All displayed diameters use cm · tree equations use X = DBH (cm), whereas legacy "
        "shrub coefficients are preserved and evaluated with X = 10 × RCD (cm)",
    "+ 새 수종 추가": "+ Add new species", "선택 삭제": "Delete selected",
    "JSON 파일로 저장": "Save to JSON file",
    "— JSON 파일을 선택하면 여기에 표시됩니다": "— select a JSON file to show it here",
    "변경됨 — 아직 파일에 저장되지 않았습니다": "Modified — not yet saved to the file",
    "변경 없음 (파일과 동기화됨)": "No changes (in sync with the file)",
    "새수종": "NewSpecies",
    "삭제할 행을 먼저 선택하세요.": "Select the rows to delete first.",
    "{n}개 수종을 삭제할까요?\n{names}": "Delete {n} species?\n{names}",
    "입력 오류": "Input error", "검증 실패": "Validation failed", "미저장 변경": "Unsaved changes",
    "교목": "Tree", "관목": "Shrub", "국내": "Domestic", "국외": "International",
    "식은 'Y=' 또는 'ln(Y)=' 로 시작해야 합니다": "The equation must start with 'Y=' or 'ln(Y)='",
    "{what}: 값이 비어 있습니다": "{what}: value is empty",
    "{what}: 숫자가 아닙니다 ({value})": "{what}: not a number ({value})",
    "{where}: 수종명이 비어 있습니다": "{where}: species name is empty",
    "{where}: 수종명 '{name}' 이 중복됩니다": "{where}: species name '{name}' is duplicated",
    "{label} '{name}': 최소직경({a})이 최대직경({b})보다 큽니다":
        "{label} '{name}': min diameter ({a}) exceeds max diameter ({b})",
    "{label} '{name}': 계수 a, b 는 0 보다 커야 합니다": "{label} '{name}': coefficients a and b must be > 0",
    "{label} '{name}': 상대생장식이 비어 있습니다": "{label} '{name}': the equation is empty",
    "{label} '{name}': 범위는 최소·최대를 둘 다 적거나 둘 다 비워야 합니다":
        "{label} '{name}': give both range min and max, or leave both blank",
    "{label} '{name}': 범위 최소({a})가 최대({b})보다 큽니다":
        "{label} '{name}': range min ({a}) exceeds max ({b})",
    "{label} '{name}': 변수2 최소가 최대보다 큽니다": "{label} '{name}': variable-2 min exceeds max",
    "{label} '{name}': 식에 H 가 있지만 변수2 라벨이 비어 있습니다":
        "{label} '{name}': the equation uses H but the variable-2 label is blank",
    "결과가 유한하지 않습니다 (Y={y})": "result is not finite (Y={y})",
    "{label} '{name}': 식 평가 실패 — {error}": "{label} '{name}': equation failed to evaluate — {error}",
    "저장할 JSON 파일 경로가 없습니다. 상단에서 species_data.json 을 지정하세요.":
        "No JSON path to save to. Specify species_data.json above.",
    "저장 전 검증에 실패했습니다:\n\n{errors}": "Validation failed before saving:\n\n{errors}",
    "[저장] {path}": "[Saved] {path}", "[백업] 이전 파일 → {path}": "[Backup] previous file → {path}",
    "저장 실패: {error}": "Save failed: {error}",
    "저장 완료 — 교목 {tree} · 관목 {shrub} · 국내 {dom} · 국외 {for_} 종":
        "Saved — {tree} trees · {shrub} shrubs · {dom} domestic · {for_} international species",
    "편집한 수종 데이터가 아직 파일에 저장되지 않았습니다.\n지금 저장하고 계속할까요?\n\n"
    "예 = 저장 후 진행 · 아니요 = 파일의 기존 내용으로 진행 · 취소 = 중단":
        "The edited species data has not been saved to the file yet.\nSave now and continue?\n\n"
        "Yes = save then continue · No = continue with the file as it is on disk · Cancel = stop",
    "편집 중인 내용을 버리고 새 파일을 불러올까요?": "Discard the current edits and load the new file?",
    "화면 배율": "Zoom",
    "수종 데이터 업데이터": "ForeCarb Equation Library Manager",
    "ForeCarb 상대생장식 라이브러리 관리": "ForeCarb Equation Library Manager",
    "JSON을 열고 수종·계수를 검토한 뒤 저장하여 ForeCarb에 적용합니다.":
        "Open the JSON, review species and coefficients, then save and deploy it to the Assessment Application.",
    "작업 순서: 1. JSON 열기  →  2. 수종·계수 편집  →  3. 저장·검증  →  4. exe 재빌드 또는 JSON 적용":
        "Workflow: 1. Open JSON  →  2. Edit species and coefficients  →  "
        "3. Save and validate  →  4. Rebuild the Assessment Application or apply JSON",
    "화면 배율을 조정합니다": "Adjust the interface zoom.",
}


def _current_language() -> str:
    try:
        from PyQt5.QtCore import QSettings
        value = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY)
    except Exception:
        return "ko"
    return "en" if value == "en" else "ko"


def _save_language(code: str) -> None:
    try:
        from PyQt5.QtCore import QSettings
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_SETTINGS_KEY, "en" if code == "en" else "ko")
        s.sync()
    except Exception:
        pass


_LANG = "ko"


def tr(text: str) -> str:
    """한글 원문을 현재 언어로. 대응 항목이 없으면 원문 그대로."""
    return _EN.get(text, text) if _LANG == "en" else text


# ── 화면 스케일 (반응형) ────────────────────────────────────────────────
# 본 프로그램의 carbon_calculator.ui_scale / font_config 와 같은 규칙을 자체 구현한다
# (업데이터는 단독 배포이므로 패키지를 import 하지 않는다).
#  - 기준 해상도 1920×1080 의 사용 가능 영역에서 1.0, 작은 화면은 비례 축소(최소 0.70),
#    큰 화면은 최대 1.50 까지만 확대.
#  - 여기에 사용자가 고른 "화면 배율"(85~130%) 을 곱한다. 배율은 QSettings 에 저장.
_REF_W, _REF_H = 1920, 1080
_SCALE_MIN, _SCALE_MAX = 0.70, 1.50
_FONT_DELTA = 4                 # 기준 해상도에서 OS 기본값보다 4pt 크게 표시
_FONT_MIN_PT = 10               # 작은 화면에서도 편집 텍스트가 10pt 아래로 축소되지 않음
_SETTINGS_KEY_ZOOM = "updater_zoom"
_ZOOM_CHOICES = ((0.85, "85%"), (1.0, "100%"), (1.15, "115%"),
                 (1.3, "130%"), (1.45, "145%"))
_UI_SCALE = 1.0
_ZOOM = 1.0


def _enable_high_dpi() -> None:
    """고해상도 디스플레이 지원. **QApplication 생성 전** 호출."""
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        flag = getattr(Qt, attr, None)
        if flag is not None:
            try:
                QApplication.setAttribute(flag, True)
            except Exception:
                pass


def _screen_geometry():
    app = QApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return screen.availableGeometry() if screen is not None else None


def _load_zoom() -> float:
    try:
        from PyQt5.QtCore import QSettings
        v = float(QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY_ZOOM, 1.0))
        return v if 0.5 <= v <= 2.0 else 1.0
    except Exception:
        return 1.0


def _save_zoom(z: float) -> None:
    try:
        from PyQt5.QtCore import QSettings
        st = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        st.setValue(_SETTINGS_KEY_ZOOM, float(z))
        st.sync()
    except Exception:
        pass


def _compute_ui_scale(zoom: float = 1.0, geo=None) -> float:
    """모니터 사용 가능 영역 기준 자동 스케일 × 사용자 배율."""
    if geo is None:
        geo = _screen_geometry()
    auto = 1.0
    if geo is not None and geo.width() > 0 and geo.height() > 0:
        auto = min(geo.width() / _REF_W, geo.height() / _REF_H)
    auto = max(_SCALE_MIN, min(_SCALE_MAX, auto))
    return max(0.55, min(1.9, auto * zoom))


def _set_ui_scale(zoom: float) -> None:
    global _UI_SCALE, _ZOOM
    _ZOOM = zoom
    _UI_SCALE = _compute_ui_scale(zoom)


def _px(v: float) -> int:
    return max(1, round(v * _UI_SCALE))


def _pt(v: float) -> int:
    return scaled_point_size(v, _UI_SCALE)


_BASE_PT: int | None = None     # 앱 최초 기본 폰트 크기 — 배율을 바꿔도 항상 이 값에서 계산한다


def _apply_app_font(app: QApplication) -> None:
    """앱 기본 폰트를 스케일에 맞춘다 (모든 위젯에 일괄 반영).

    현재 폰트가 아니라 최초 기본 크기(_BASE_PT)에서 계산해야 배율을 여러 번 바꿔도
    크기가 누적되지 않는다.
    """
    global _BASE_PT
    f = app.font()
    if _BASE_PT is None:
        _BASE_PT = f.pointSize() if f.pointSize() > 0 else 9
    f.setFamily(font_family(_LANG))
    f.setPointSize(scaled_point_size(BODY_PT, _UI_SCALE))
    app.setFont(f)
    apply_dialog_font(app)
    install_qt_translator(app, _LANG)


def _apply_readability_theme(app: QApplication) -> None:
    """큰 글꼴에서도 경계, 상태, 동작 우선순위가 명확한 편집기 테마를 적용한다."""
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QMainWindow, QScrollArea, QWidget#updaterRoot {{
            background: #F4F7F5;
        }}
        QLabel {{ color: #24342B; }}
        QMessageBox QLabel {{ font-size: {_pt(BODY_PT)}pt; }}
        QLabel#pageTitle {{
            color: #195C39;
            font-size: {_pt(TITLE_PT)}pt;
            font-weight: 700;
        }}
        QLabel#pageSubtitle {{ color: #4F6257; font-size: {_pt(SMALL_PT)}pt; }}
        QLabel#workflowHint {{
            color: #315C45;
            background: #EAF4EE;
            border: 1px solid #BCD6C6;
            border-radius: {_px(6)}px;
            padding: {_px(7)}px {_px(10)}px;
            font-size: {_pt(SMALL_PT)}pt;
        }}
        QGroupBox {{
            background: #FFFFFF;
            border: 1px solid #C7D4CC;
            border-radius: {_px(8)}px;
            margin-top: {_px(16)}px;
            padding-top: {_px(9)}px;
            font-weight: 600;
            color: #244E37;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {_px(12)}px;
            padding: 0 {_px(6)}px;
        }}
        QLineEdit, QComboBox, QTableWidget, QAbstractItemView {{
            font-size: {_pt(BODY_PT)}pt;
        }}
        QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {{
            background: #FFFFFF;
            border: 1px solid #AEBEB4;
            border-radius: {_px(4)}px;
            selection-background-color: #CFE6D7;
            selection-color: #173325;
        }}
        QLineEdit, QComboBox {{
            min-height: {_px(32)}px;
            padding: {_px(3)}px {_px(8)}px;
        }}
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTableWidget:focus {{
            border: 2px solid #2E7D52;
        }}
        QPushButton {{
            min-height: {_px(34)}px;
            padding: {_px(5)}px {_px(13)}px;
            border: 1px solid #9FB1A6;
            border-radius: {_px(5)}px;
            background: #F8FAF9;
            color: #24342B;
        }}
        QPushButton:hover {{ background: #EAF4EE; border-color: #4E8B67; }}
        QPushButton:pressed {{ background: #D9EADF; }}
        QPushButton:disabled {{ color: #8B9690; background: #EEF1EF; border-color: #D3DAD6; }}
        QPushButton#primaryAction {{
            background: #246B43;
            color: white;
            border-color: #1C5736;
            font-weight: 700;
        }}
        QPushButton#primaryAction:hover {{ background: #2F7E51; }}
        QPushButton#destructiveAction {{ color: #9A2E2E; border-color: #D7AAAA; }}
        QTabWidget::pane {{ border: 1px solid #B8C8BE; background: white; }}
        QTabBar {{ font-size: {_pt(BODY_PT)}pt; font-weight: 700; }}
        QTabBar::tab {{
            background: #E9EFEB;
            border: 1px solid #C2CFC7;
            padding: {_px(8)}px {_px(15)}px;
            min-height: {_px(24)}px;
        }}
        QTabBar::tab:selected {{
            background: #FFFFFF;
            color: #1E6941;
            font-weight: 700;
            border-bottom-color: #FFFFFF;
        }}
        QHeaderView::section {{
            background: #E8F1EB;
            color: #244E37;
            border: 0;
            border-right: 1px solid #C7D4CC;
            border-bottom: 1px solid #AEBEB4;
            padding: {_px(6)}px {_px(8)}px;
            font-size: {_pt(BODY_PT)}pt;
            font-weight: 700;
        }}
        QTableWidget {{ gridline-color: #D6DFD9; alternate-background-color: #F6FAF7; }}
        QTableWidget::item {{ padding: {_px(4)}px {_px(6)}px; }}
        QCheckBox {{ spacing: {_px(7)}px; }}
        QCheckBox::indicator {{ width: {_px(18)}px; height: {_px(18)}px; }}
        QToolTip {{
            background: #24342B;
            color: white;
            border: 1px solid #24342B;
            padding: {_px(5)}px;
        }}
    """)


def _fit_window(win: QWidget, wfrac: float = 0.92, hfrac: float = 0.92,
                min_w: int = 1080, min_h: int = 700) -> None:
    """창을 화면 비율로 맞추고 화면을 넘지 않게 클램프한 뒤 중앙에 둔다."""
    geo = _screen_geometry()
    if geo is None:
        win.resize(1180, 900)
        return
    aw, ah = geo.width(), geo.height()
    eff_w, eff_h = min(_px(min_w), aw), min(_px(min_h), ah)
    win.setMinimumSize(eff_w, eff_h)
    w = max(eff_w, min(int(aw * wfrac), aw))
    h = max(eff_h, min(int(ah * hfrac), ah))
    win.resize(w, h)
    win.move(geo.x() + (aw - w) // 2, geo.y() + (ah - h) // 2)


def _fit_dialog(dlg: QWidget, width: int, height: int, margin: int = 48) -> None:
    w, h = _px(width), _px(height)
    geo = _screen_geometry()
    if geo is not None:
        w, h = min(w, geo.width() - margin), min(h, geo.height() - margin)
    dlg.resize(max(360, w), max(240, h))


_STATUS_INDENT: int | None = None   # 상태 라벨 들여쓰기 — 창이 라벨 폭을 계산해 채운다


def _status_css(color) -> str:
    c = "color: %s; " % color if color else ""
    indent = _STATUS_INDENT if _STATUS_INDENT is not None else _px(223)
    return "%smargin-left: %dpx;" % (c, indent)


_IS_EXE = hasattr(sys, '_MEIPASS')
HERE = Path(sys.executable).parent if _IS_EXE else Path(__file__).resolve().parent

# 내장 소스 루트:
#   frozen  → PyInstaller 가 _MEIPASS/bundled_src 로 풀어놓은 소스
#   dev     → 이 파일이 있는 Code 폴더 자체
if _IS_EXE:
    SRC_ROOT = Path(sys._MEIPASS) / "bundled_src"   # type: ignore[attr-defined]
else:
    SRC_ROOT = HERE

BUILD_VENV    = Path.home() / ".carboncalc_build_venv"
JSON_NAME     = "species_data.json"

# ── 플랫폼별 venv 레이아웃 / 실행파일 확장자 ──────────────────────────────
_VENV_BIN     = "Scripts" if os.name == "nt" else "bin"
_EXE_EXT      = ".exe" if os.name == "nt" else ""
MAIN_APP_NAME = "ForeCarb"
MAIN_EXE_NAME = f"{MAIN_APP_NAME}{_EXE_EXT}"
# build_exe.py(APP_NAME) 가 dist/ 에 실제로 만드는 산출물 이름 — 반드시 일치해야 한다.
_BUILT_APP_NAME = "FORECAST-SW"
_BUILT_EXE_NAME = f"{_BUILT_APP_NAME}{_EXE_EXT}"

# 작업폴더로 복사할 때 제외할 항목
_COPY_IGNORE = shutil.ignore_patterns(
    "build", "dist", "__pycache__", "*.pyc", ".git",
    ".build_venv", "*.spec",
)


def _find_python() -> Path | None:
    """빌드용 Python 탐색: 빌드 venv → 시스템 PATH."""
    p = BUILD_VENV / _VENV_BIN / f"python{_EXE_EXT}"
    if p.exists():
        return p
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            try:
                r = subprocess.run([found, "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return Path(found)
            except Exception:
                pass
    return None


def _auto_find_main_exe() -> Path | None:
    """ForeCarb.exe 를 자동 탐색 (현재 폴더 / dist/)."""
    for exe in (MAIN_EXE_NAME, _BUILT_EXE_NAME):
        for candidate in [
            HERE / exe,
            HERE / "dist" / exe,
            HERE / "dist" / Path(exe).stem / exe,
        ]:
            if candidate.exists():
                return candidate
    return None


# ─────────────────────────── JSON 검증 ───────────────────────────

def _validate_species_json(path: Path) -> tuple[bool, str]:
    """통합 species_data.json 검증. 4개 섹션 중 하나 이상 존재하면 유효."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        return False, tr("JSON 파싱 오류: {error}").format(error=e)

    n_tree = len(data.get('TREE_BASE', {}))
    n_shrub = len(data.get('SHRUB_SPECIES', {}))
    n_dom = len(data.get('DOMESTIC_SPECIES', {}))
    n_for = len(data.get('FOREIGN_SPECIES', {}))

    if (n_tree + n_shrub + n_dom + n_for) == 0:
        return False, (tr("유효한 수종 섹션이 없습니다. "
                       "TREE_BASE / SHRUB_SPECIES / DOMESTIC_SPECIES / FOREIGN_SPECIES 중 "
                       "하나 이상이 필요합니다."))

    return True, tr("교목 {tree} · 관목 {shrub} · 국내 {dom} · 국외 {for_} 종").format(
        tree=n_tree, shrub=n_shrub, dom=n_dom, for_=n_for)


# ─────────────────────────── 빌드 워커 ───────────────────────────

def _normalize_exe_name(value: str) -> str:
    """Accept a Windows basename, with an optional .exe extension."""
    name = value.strip()
    if not name:
        raise ValueError(tr("사용할 EXE 파일 이름을 입력하세요."))
    if any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name):
        raise ValueError(tr("파일 이름에는 경로 또는 특수문자를 사용할 수 없습니다."))
    stem = name[:-4] if name.lower().endswith(".exe") else name
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update(f"{prefix}{i}" for prefix in ("COM", "LPT") for i in "123456789¹²³")
    if (not stem or stem.endswith((".", " "))
            or stem.split(".")[0].upper() in reserved
            or len((stem + ".exe").encode("utf-16-le")) // 2 > 255):
        raise ValueError(tr("사용할 수 없는 파일 이름입니다."))
    return stem + ".exe"


class BuildWorker(QThread):
    """임시 작업폴더 구성 → build_exe.py 실행 → 산출물 복사 를 백그라운드로 수행."""
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # (성공여부, 산출물 경로 또는 오류메시지)

    def __init__(self, json_path: Path, out_dir: Path, options: list[str],
                 exe_name: str = MAIN_EXE_NAME):
        super().__init__()
        self.json_path = json_path
        self.out_dir = out_dir
        self.options = options
        self.exe_name = _normalize_exe_name(exe_name)

    def _emit(self, msg: str):
        self.log_line.emit(msg)

    def run(self):
        workdir = None
        try:
            python = _find_python()
            if python is None:
                self.finished.emit(False,
                    tr("Python 인터프리터를 찾을 수 없습니다. Python 3.10+ 를 설치하세요."))
                return

            if not (SRC_ROOT / "build_exe.py").exists():
                self.finished.emit(False,
                    tr("내장 소스를 찾을 수 없습니다: {path}\n"
                       "updater 를 build_updater.py 로 다시 빌드하세요.")
                    .format(path=SRC_ROOT))
                return

            # ── 1) 내장 소스를 임시 작업폴더로 복사 ──────────────────────
            workdir = Path(tempfile.mkdtemp(prefix="carboncalc_build_"))
            self._emit(tr("[1/4] 작업폴더 준비: {path}").format(path=workdir))
            shutil.copytree(SRC_ROOT, workdir, dirs_exist_ok=True, ignore=_COPY_IGNORE)

            # ── 2) 사용자 JSON 투입 (구 carbon1/2 파일은 충돌 방지 위해 제거) ──
            for _old in ("carbon1_species_data.json", "carbon2_species_data.json"):
                _p = workdir / _old
                if _p.exists():
                    _p.unlink()
            shutil.copy2(self.json_path, workdir / JSON_NAME)
            self._emit(tr("[2/4] 수종 데이터 적용: {src} → {dst}")
                       .format(src=self.json_path.name, dst=JSON_NAME))

            # ── 3) build_exe.py 실행 (PyInstaller) ──────────────────────
            cmd = [str(python), str(workdir / "build_exe.py")] + self.options
            self._emit(tr("[3/4] 빌드 시작: {cmd}").format(cmd=" ".join(cmd)))
            self._emit(tr("      (최초 실행 시 빌드 전용 venv 생성으로 수 분 소요)"))
            self._emit("=" * 70)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                cwd=str(workdir),
            )
            for line in proc.stdout:
                self._emit(line.rstrip())
            proc.wait()

            if proc.returncode != 0:
                self.finished.emit(False, tr("PyInstaller 빌드가 실패했습니다. 위 로그를 확인하세요."))
                return

            # ── 4) 산출물 복사 ─────────────────────────────────────────
            onedir = "--onedir" in self.options
            if onedir:
                produced = workdir / "dist" / _BUILT_APP_NAME
            else:
                produced = workdir / "dist" / _BUILT_EXE_NAME

            if not produced.exists():
                self.finished.emit(
                    False,
                    tr("산출물을 찾을 수 없습니다: {path}").format(path=produced))
                return

            self.out_dir.mkdir(parents=True, exist_ok=True)
            self._emit("=" * 70)
            self._emit(tr("[4/4] 산출물 복사 → {path}").format(path=self.out_dir))

            if onedir:
                dest = self.out_dir / Path(self.exe_name).stem
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(produced, dest)
                final = dest / self.exe_name
                if final.name != _BUILT_EXE_NAME:
                    (dest / _BUILT_EXE_NAME).rename(final)
            else:
                final = self.out_dir / self.exe_name
                shutil.copy2(produced, final)

            self.finished.emit(True, str(final))

        except Exception as e:
            self.finished.emit(False, tr("[오류] {error}").format(error=e))
        finally:
            if workdir and workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)


# ─────────────────────────── UI 헬퍼 ───────────────────────────

class FilePickRow(QWidget):
    def __init__(self, label: str, btn_label: str | None = None, parent=None,
                 label_width: int | None = None):
        super().__init__(parent)
        if btn_label is None:
            btn_label = tr("열기...")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_px(8))
        self.label_w = QLabel(label)
        # 라벨 폭은 폰트 크기에 따라 창이 계산해 넘긴다(큰 배율에서 글자가 잘리지 않도록)
        self.label_w.setFixedWidth(label_width or _px(215))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("파일/폴더 경로를 선택하거나 직접 입력하세요"))
        self.edit.setClearButtonEnabled(True)
        self.btn = QPushButton(btn_label)
        button_w = self.btn.fontMetrics().horizontalAdvance(btn_label) + _px(28)
        self.btn.setMinimumWidth(max(_px(92), button_w))
        layout.addWidget(self.label_w)
        layout.addWidget(self.edit)
        layout.addWidget(self.btn)

    @property
    def path(self) -> Path | None:
        t = self.edit.text().strip()
        return Path(t) if t else None


# ─────────────────────────── 수종 데이터 편집기 ───────────────────────────
# species_data.json 의 4개 섹션(교목·관목·국내·국외)을 표로 보여주고 셀 단위로
# 추가·수정·삭제한 뒤 같은 파일에 저장한다. 저장 시 형식은 data.py / data2.py 의
# 로더가 읽는 그대로 유지한다:
#   TREE_BASE      : {"default": [a,b,cf,dmin,dmax,g10,g20,g21]}
#   SHRUB_SPECIES  : [a,b,cf,dmin,dmax,g10,g20,g21]
#   DOMESTIC/FOREIGN: {"equation", "range": [min,max]|[null,null], "var1", "var2"?}
# 학명(SPECIES_EN)은 꼬리표를 뗀 기본 수종명 기준으로 함께 갱신한다.

_SECTION_TREE, _SECTION_SHRUB, _SECTION_DOM, _SECTION_FOR = (
    "TREE_BASE", "SHRUB_SPECIES", "DOMESTIC_SPECIES", "FOREIGN_SPECIES")

# 열 정의: (표시 헤더, 내부 키). 헤더는 tr() 로 번역된다.
_COEF_KEYS = ("a", "b", "cf", "dmin", "dmax", "g10", "g20", "g21")
_ROLE_TRUE_NAME = Qt.UserRole + 1  # 수종명 셀이 학명으로 표시(영문 모드·읽기전용)될 때 실제 저장 키(국문)

# 기본 대상지 목록 — JSON 의 ENVIRONMENTS 가 없을 때의 폴백
_DEFAULT_ENVIRONMENTS = (
    "산불피해지 자연복원",
    "산불피해지 인공복원",
    "채석장 인공복원",
)

def _apply_tab_font(tabs: QTabWidget) -> None:
    """탭 막대 글꼴을 굵게 못 박는다.

    스타일시트가 선택된 탭만 굵게(font-weight: 700) 그리면, 탭 폭은 보통 굵기로
    계산되어 선택된 탭의 글자가 잘린다. 처음부터 굵은 글꼴로 폭을 계산하게 한다.
    """
    f = QFont(font_family(_LANG), _pt(BODY_PT))
    f.setBold(True)
    tabs.tabBar().setFont(f)


def _env_label(env: str, data: dict | None = None) -> str:
    """대상지 탭에 표시할 이름 — 영문 모드에서는 ENVIRONMENTS_EN 을 따른다.

    우선순위는 불러온 JSON 의 ENVIRONMENTS_EN → 내장 대응표 → 원문(국문)이다.
    """
    if _LANG != "en" or not env:
        return env
    from_json = (data or {}).get("ENVIRONMENTS_EN") or {}
    if isinstance(from_json, dict):
        name = from_json.get(env)
        if isinstance(name, str) and name.strip():
            return name
    return _ENVIRONMENT_EN.get(env, env)


# ── 대상지별 통합 표 ──────────────────────────────────────────────────────
# 한 대상지·생장형의 전체 수종을 하나의 표로 보여주기 위해 계수형(핵심 22종)과
# 식형(확장 55종)의 열을 합쳐 둔다. 행 종류에 따라 해당 없는 열은 비어 있고
# 읽기 전용이 된다.
# '구분'(핵심/국내/국외)은 값을 입력하는 열이 아니라 행의 성격 표시이므로 맨 뒤에 둔다.
_MERGED_COLS = [
    ("수종명", "name"), ("학명", "sci"),
    ("a", "a"), ("b", "b"), ("CF", "cf"),
    ("최소직경", "dmin"), ("최대직경", "dmax"),
    ("생장량(1~10년)", "g10"), ("생장량(11~20년)", "g20"), ("생장량(21~30년)", "g21"),
    ("생장 티어", "tier"),
    ("상대생장식", "eq"), ("변수1 라벨", "v1"), ("변수2 라벨", "v2"),
    ("변수2 최소", "v2min"), ("변수2 최대", "v2max"), ("변수2 기본값", "v2def"),
    ("구분", "origin"),
]
(_COL_NAME, _COL_SCI, _COL_A, _COL_B, _COL_CF, _COL_DMIN, _COL_DMAX,
 _COL_G10, _COL_G20, _COL_G21, _COL_TIER, _COL_EQ, _COL_V1, _COL_V2, _COL_V2MIN, _COL_V2MAX,
 _COL_V2DEF, _COL_ORIGIN) = range(len(_MERGED_COLS))

# 계수형 행이 쓰는 열 (저장 배열 순서와 같다: a, b, cf, dmin, dmax, g10, g20, g21)
_COL_CORE = (_COL_A, _COL_B, _COL_CF, _COL_DMIN, _COL_DMAX,
             _COL_G10, _COL_G20, _COL_G21)
# 식형 행이 쓰는 열
_COL_EQ_FIELDS = (_COL_DMIN, _COL_DMAX, _COL_EQ, _COL_V1, _COL_V2,
                  _COL_V2MIN, _COL_V2MAX, _COL_V2DEF)
# 행 종류별로 비워 두는 열
_COL_EQ_ONLY = tuple(c for c in _COL_EQ_FIELDS if c not in _COL_CORE)
_COL_CORE_ONLY = tuple(c for c in _COL_CORE if c not in _COL_EQ_FIELDS)

_ROLE_ROW_KIND = Qt.UserRole + 2   # 행 종류: 핵심(_ROW_CORE) / 국내 / 국외
_ROW_CORE = "core"
_ORIGIN_DOM = "domestic"
_ORIGIN_FOR = "foreign"

_KIND_TREE, _KIND_SHRUB = "tree", "shrub"

# 확장 레코드의 교목/관목 분류 — carbon_calculator/species_library.py 의 규칙과
# 같아야 한다. Manager exe 는 numpy 를 번들하지 않으므로 그 모듈을 import 하지 않고
# 규칙만 복제한다.
_KIND_OVERRIDES = {
    "서양개암나무(지상부)": _KIND_SHRUB,   # 변수가 수고 h + LAI 이며 개암나무류는 관목
}


def _classify_kind(name: str, var1_label: str) -> str:
    """설명변수로 교목/관목을 판정한다 (RCD → 관목, 그 외 → 교목)."""
    override = _KIND_OVERRIDES.get(name)
    if override is not None:
        return override
    return _KIND_SHRUB if "RCD" in (var1_label or "").upper() else _KIND_TREE


def _coef_record(entry, env: str):
    """계수형 섹션에서 대상지 레코드(8개 값) 를 꺼낸다. 없으면 None."""
    if isinstance(entry, dict):
        by_env = entry.get("by_env")
        if isinstance(by_env, dict) and by_env:
            arr = by_env.get(env)
            if arr is None:
                arr = next(iter(by_env.values()))
            return list(arr) if isinstance(arr, (list, tuple)) else None
        if isinstance(entry.get("default"), (list, tuple)):
            return list(entry["default"])
        return None
    if isinstance(entry, (list, tuple)):
        return list(entry)
    return None


def _eq_record(entry, env: str):
    """식형 섹션에서 대상지 레코드(dict) 를 꺼낸다. 없으면 None."""
    if not isinstance(entry, dict):
        return None
    by_env = entry.get("by_env")
    if isinstance(by_env, dict) and by_env:
        rec = by_env.get(env)
        if rec is None:
            rec = next(iter(by_env.values()))
        return rec if isinstance(rec, dict) else None
    return entry if entry.get("equation") else None



# 생장 티어 — 대상지 3종 × 티어 3단계 = 보정계수 9개. 수종마다 대상지별 티어를 갖는다.
# carbon_calculator/data.py 의 parse_growth_settings 와 같은 규칙이어야 한다 (Manager exe 는
# 그 모듈을 import 하지 않는다).
_TIERS = (1, 2, 3)
_DEFAULT_TIER = 1
_LEGACY_SECTION_TIER = {_SECTION_TREE: 1, _SECTION_SHRUB: 2}


_GROWTH_FACTOR_NOTE = (
    "ENVIRONMENT_GROWTH_FACTORS[대상지][TIER_1|TIER_2|TIER_3] 는 대상지 3종 × 생장 티어 3단계 = "
    "9개 보정계수이다. SPECIES_GROWTH_TIERS[수종][대상지] 로 지정한 티어의 계수가 그 수종의 "
    "연 직경 생장량(생장량이 없는 확장 레코드는 가정 생장률 2%)에 추가로 곱해지며 1.0 은 보정 "
    "없음이다. 티어 지정이 없으면 티어 1 이다. 식(a·b·CF·범위)은 바꾸지 않으므로 0년차 저장량은 "
    "변하지 않고 30년 시나리오만 달라진다. SPECIES_GROWTH_FACTORS[수종][대상지] 가 있으면 그 값이 "
    "우선한다.")


def _tier_key(tier: int) -> str:
    return "TIER_%d" % tier


def _positive(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _growth_settings(data: dict | None) -> tuple[dict, dict]:
    """JSON → ({대상지: {티어: 계수}}, {수종: {대상지: 티어}}).

    구버전(대상지 × 교목/관목 6개) 파일은 교목 계수 → 티어 1, 관목 계수 → 티어 2 로
    옮기고, 티어 지정이 없으면 관목 수종을 티어 2 에 둔다.
    """
    data = data or {}
    raw = data.get("ENVIRONMENT_GROWTH_FACTORS")
    factors: dict = {}
    legacy_used = False
    for env, slot in (raw.items() if isinstance(raw, dict) else ()):
        if not isinstance(slot, dict):
            continue
        target = factors.setdefault(env, {t: 1.0 for t in _TIERS})
        if any(_tier_key(t) in slot for t in _TIERS):
            for t in _TIERS:
                value = _positive(slot.get(_tier_key(t)))
                if value is not None:
                    target[t] = value
        else:
            for section, t in _LEGACY_SECTION_TIER.items():
                value = _positive(slot.get(section))
                if value is not None:
                    target[t] = value
                    legacy_used = legacy_used or value != 1.0
    raw_tiers = data.get("SPECIES_GROWTH_TIERS")
    tiers: dict = {}
    for name, envs in (raw_tiers.items() if isinstance(raw_tiers, dict) else ()):
        if isinstance(envs, dict):
            tiers[name] = {e: int(t) for e, t in envs.items()
                           if str(t).strip() in ("1", "2", "3")}
    if legacy_used and not isinstance(raw_tiers, dict):
        tiers = {name: {env: 2 for env in factors}
                 for name in (data.get(_SECTION_SHRUB) or {})}
    return factors, tiers


class _TierDelegate(QStyledItemDelegate):
    """'생장 티어' 열 — 1·2·3 중에서 고르는 콤보 편집기."""

    def createEditor(self, parent, _option, _index):    # noqa: N802 — Qt 시그니처
        combo = QComboBox(parent)
        combo.addItems([str(t) for t in _TIERS])
        return combo

    def setEditorData(self, editor, index):              # noqa: N802
        i = editor.findText(str(index.data() or _DEFAULT_TIER).strip())
        editor.setCurrentIndex(max(0, i))

    def setModelData(self, editor, model, index):        # noqa: N802
        model.setData(index, editor.currentText())


def _section_equation_unit(data: dict | None, section: str) -> str:
    """Return the source-equation diameter unit declared by the JSON schema."""
    schema = (data or {}).get("_schema")
    schema = schema if isinstance(schema, dict) else {}
    default = "mm" if section == _SECTION_SHRUB else "cm"
    unit = schema.get(f"{section}_equation_diameter_unit", default)
    return unit if unit in ("cm", "mm") else default


def _display_scale(data: dict | None, section: str) -> float:
    """Raw equation-domain value divided by this scale gives the displayed cm value."""
    return 10.0 if _section_equation_unit(data, section) == "mm" else 1.0


def _set_true_name(item, name: str) -> None:
    item.setData(_ROLE_TRUE_NAME, name)


def _get_true_name(item) -> str:
    """0열(수종명) 셀의 실제 저장 키. 편집 가능한 상태(한국어 모드, 또는 학명이 아직
    없는 새 행)면 화면 텍스트가 곧 키다. 학명으로 치환되어 읽기전용이 된 상태에서만
    숨겨둔 원본(국문) 이름을 쓴다 — 그래야 편집 중인 텍스트가 저장 키로 조용히
    무시되는 일이 없다."""
    if item is None:
        return ""
    if not (item.flags() & Qt.ItemIsEditable):
        stored = item.data(_ROLE_TRUE_NAME)
        if stored:
            return stored
    return item.text()

def _eval_equation(equation: str, x: float, h: float | None = None) -> float:
    """본 프로그램과 동일한 허용목록 기반 평가기로 식을 검증한다."""
    return _safe_equation_evaluate(equation, x, h)


def _fmt_num(v) -> str:
    """JSON 숫자 → 표 셀 문자열. 지수표기 없이, 불필요한 0 없이."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e12:
            return str(int(v))
        s = ("%.10f" % v).rstrip("0").rstrip(".")
        return s if s not in ("", "-0", "-") else repr(v)
    return str(v)


def _parse_num(text: str, what: str, allow_blank: bool = False) -> float | None:
    t = (text or "").strip()
    if not t:
        if allow_blank:
            return None
        raise ValueError(tr("{what}: 값이 비어 있습니다").format(what=what))
    try:
        return float(t)
    except ValueError:
        raise ValueError(tr("{what}: 숫자가 아닙니다 ({value})").format(what=what, value=t))


def _num_out(v: float | None):
    """저장용: 정수값이면 int 로 (JSON 을 원본처럼 깔끔하게)."""
    if v is None:
        return None
    return int(v) if float(v) == int(v) and abs(v) < 1e12 else float(v)


def _base_name(name: str) -> str:
    """'후박나무(지상부)' → '후박나무'. 학명(SPECIES_EN) 키."""
    return name.split("(", 1)[0].strip()


def _tidy_columns(t: QTableWidget) -> None:
    """내용 기준으로 열 폭을 잡되, 긴 식/경로 열은 상한을 두어 다른 열이 밀리지 않게 한다."""
    t.resizeColumnsToContents()
    cap = _px(420)
    floor = _px(88)
    for c in range(t.columnCount()):
        t.setColumnWidth(c, max(floor, min(t.columnWidth(c), cap)))


def _mk_item(text: str, editable: bool = True) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if text and len(text) > 24:
        it.setToolTip(text)          # 긴 식·라벨은 마우스를 올리면 전체가 보인다
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        it.setForeground(Qt.darkGray)
    return it


class SpeciesEditor(QGroupBox):
    """대상지별 상대생장식 표 편집기.

    구성은 **대상지 3탭 × (교목 / 관목)** 이며, 각 표는 그 대상지·생장형의
    **전체 수종**(핵심 계수형 + 확장 식형)을 열을 합친 하나의 표로 보여준다.
    대상지 공통 '기본식' 개념은 없다 — 수종마다 대상지 3종의 레코드를 각각 보유하고
    프로그램은 선택된 대상지 것 하나만 적용한다.

    성장률 보정계수는 각 대상지 탭 상단에 있으며, 그 대상지 레코드의 연 직경
    생장량에 **추가로** 곱해진다(1.0 = 보정 없음).
    """

    dirty_changed = pyqtSignal(bool)
    save_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(tr("수종별 상대생장식 (대상지별 · 추가/수정/삭제)"), parent)
        self._data: dict | None = None      # 마지막으로 불러온/저장한 원본 dict
        self._dirty = False
        self._loading = False
        self._env_list: list[str] = list(_DEFAULT_ENVIRONMENTS)
        self._tiers: dict = {}               # {수종: {대상지: 티어}} — 불러온 값
        self._tier_delegate = _TierDelegate(self)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────
    def _new_table(self) -> QTableWidget:
        t = QTableWidget(0, len(_MERGED_COLS))
        # 표 글꼴을 본문 크기로 못 박는다. 스타일시트가 걸린 위젯은 앱 기본 폰트를
        # 잃고 스타일 기본값(작은 글씨)으로 돌아갈 수 있어, 표만 작게 보였다.
        cell_font = QFont(font_family(_LANG), _pt(BODY_PT))
        header_font = QFont(cell_font)
        header_font.setBold(True)
        t.setFont(cell_font)
        t.horizontalHeader().setFont(header_font)
        t.verticalHeader().setFont(cell_font)
        t.setHorizontalHeaderLabels([tr(h) for h, _k in _MERGED_COLS])
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                          | QAbstractItemView.AnyKeyPressed)
        t.setAlternatingRowColors(True)
        t.setWordWrap(False)
        t.setTextElideMode(Qt.ElideRight)
        t.verticalHeader().setDefaultSectionSize(max(_px(40), t.fontMetrics().height() + _px(14)))
        t.verticalHeader().setMinimumSectionSize(_px(32))
        t.horizontalHeader().setMinimumHeight(_px(38))
        t.horizontalHeader().setMinimumSectionSize(_px(70))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        t.horizontalHeader().setStretchLastSection(True)
        t.setMinimumHeight(_px(250))
        t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        t.setItemDelegateForColumn(_COL_TIER, self._tier_delegate)
        t.itemChanged.connect(self._on_item_changed)
        return t

    def _build_ui(self):
        v = QVBoxLayout(self)

        self.tabs = QTabWidget()
        _apply_tab_font(self.tabs)
        self.env_tables: dict[tuple, QTableWidget] = {}
        self.factor_spins: dict[tuple, QDoubleSpinBox] = {}
        self._inner_tabs: dict[str, QTabWidget] = {}

        for env in self._env_list:
            self.tabs.addTab(self._build_env_tab(env), _env_label(env))
        self.tabs.currentChanged.connect(self._sync_buttons)
        v.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton(tr("+ 새 수종 추가"))
        self.del_btn = QPushButton(tr("선택 삭제"))
        self.del_btn.setObjectName("destructiveAction")
        self.add_btn.clicked.connect(self.add_row)
        self.del_btn.clicked.connect(self.delete_selected)
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        v.addLayout(row)

        status_row = QHBoxLayout()
        self.status = QLabel("")
        self.save_btn = QPushButton(tr("JSON 파일로 저장"))
        self.save_btn.setObjectName("primaryAction")
        self.save_btn.setMinimumWidth(_px(190))
        self.save_btn.clicked.connect(self.save_requested.emit)
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        status_row.addWidget(self.save_btn)
        v.addLayout(status_row)
        self._set_dirty(False)
        self._sync_buttons()

    def _build_env_tab(self, env: str) -> QWidget:
        """대상지 1개 탭 — 상단 보정계수 + 하위 교목/관목 표."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(6, 6, 6, 6)
        col.setSpacing(6)

        factor_row = QHBoxLayout()
        factor_row.setSpacing(8)
        title = QLabel(tr("성장률 보정계수"))
        hint = tr("각 수종의 연 직경 생장량에 그 수종 티어의 계수를 곱합니다 (1.0 = 보정 없음). "
                  "티어는 표의 '생장 티어' 열에서 수종마다 지정합니다.")
        title.setToolTip(hint)
        factor_row.addWidget(title)
        for tier in _TIERS:
            label = QLabel(tr("티어 {n}").format(n=tier))
            label.setToolTip(hint)
            factor_row.addWidget(label)
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.setRange(0.001, 100.0)
            spin.setValue(1.0)
            spin.setMinimumWidth(_px(96))
            spin.valueChanged.connect(lambda _v: self._on_factor_changed())
            spin.setToolTip(hint)
            self.factor_spins[(env, tier)] = spin
            factor_row.addWidget(spin)
        factor_row.addStretch(1)
        col.addLayout(factor_row)

        inner = QTabWidget()
        _apply_tab_font(inner)
        for kind, title in ((_KIND_TREE, tr("교목")), (_KIND_SHRUB, tr("관목"))):
            t = self._new_table()
            self.env_tables[(env, kind)] = t
            inner.addTab(t, title)
        inner.currentChanged.connect(self._sync_buttons)
        self._inner_tabs[env] = inner
        col.addWidget(inner, 1)
        return page

    def _on_factor_changed(self) -> None:
        if not self._loading:
            self._set_dirty(True)

    def _sync_buttons(self, *_):
        loaded = self._data is not None
        self.add_btn.setEnabled(loaded)
        self.del_btn.setEnabled(loaded)

    # ── 상태 ──────────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        return self._dirty

    def is_loaded(self) -> bool:
        return self._data is not None

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        if self._data is None:
            self.status.setText(tr("— JSON 파일을 선택하면 여기에 표시됩니다"))
            self.status.setStyleSheet("color: gray;")
        elif dirty:
            self.status.setText(tr("변경됨 — 아직 파일에 저장되지 않았습니다"))
            self.status.setStyleSheet("color: #b35c00; font-weight: bold;")
        else:
            self.status.setText(tr("변경 없음 (파일과 동기화됨)"))
            self.status.setStyleSheet("color: gray;")
        self.save_btn.setEnabled(self._data is not None and dirty)
        self.dirty_changed.emit(dirty)

    def _on_item_changed(self, _item):
        if not self._loading:
            self._set_dirty(True)

    def _current_env(self) -> str:
        idx = self.tabs.currentIndex()
        if 0 <= idx < len(self._env_list):
            return self._env_list[idx]
        return self._env_list[0]

    def _current_kind(self) -> str:
        inner = self._inner_tabs.get(self._current_env())
        if inner is not None and inner.currentIndex() == 1:
            return _KIND_SHRUB
        return _KIND_TREE

    def _current_table(self) -> QTableWidget:
        return self.env_tables[(self._current_env(), self._current_kind())]

    # ── 불러오기 ──────────────────────────────────────────────────
    def load(self, data: dict):
        """JSON dict 를 대상지별 표에 채운다. 저장 상태로 초기화."""
        self._loading = True
        try:
            self._data = data
            sci = data.get("SPECIES_EN") or {}
            # 불러온 파일이 자체 영문명을 갖고 있으면 탭 이름을 그것으로 맞춘다.
            for i, env in enumerate(self._env_list):
                if i < self.tabs.count():
                    self.tabs.setTabText(i, _env_label(env, data))
            factors, self._tiers = _growth_settings(data)
            for env in self._env_list:
                for tier in _TIERS:
                    spin = self.factor_spins.get((env, tier))
                    if spin is not None:
                        spin.setValue((factors.get(env) or {}).get(tier, 1.0))
                for kind in (_KIND_TREE, _KIND_SHRUB):
                    self._fill_env_table(env, kind, data, sci)
        finally:
            self._loading = False
        self._set_dirty(False)
        self._sync_buttons()

    def _fill_env_table(self, env: str, kind: str, data: dict, sci: dict) -> None:
        t = self.env_tables[(env, kind)]
        t.setRowCount(0)

        core_section = _SECTION_TREE if kind == _KIND_TREE else _SECTION_SHRUB
        scale = _display_scale(data, core_section)
        for name, entry in (data.get(core_section) or {}).items():
            arr = _coef_record(entry, env)
            if arr is None:
                continue
            display = list(arr)
            if len(display) >= 5 and scale != 1.0:
                display[3] = float(display[3]) / scale
                display[4] = float(display[4]) / scale
            self._append_core_row(t, name, sci.get(_base_name(name), ""), display,
                                  self._tier_of(name, env))

        for section, origin in ((_SECTION_DOM, _ORIGIN_DOM), (_SECTION_FOR, _ORIGIN_FOR)):
            for name, entry in (data.get(section) or {}).items():
                rec = _eq_record(entry, env)
                if rec is None:
                    continue
                if _classify_kind(name, rec.get("var1") or "DBH (cm)") != kind:
                    continue
                self._append_eq_row(t, name, sci.get(_base_name(name), ""), rec, origin,
                                    self._tier_of(name, env))
        _tidy_columns(t)

    def _tier_of(self, name: str, env: str) -> int:
        tier = (self._tiers.get(name) or {}).get(env, _DEFAULT_TIER)
        return tier if tier in _TIERS else _DEFAULT_TIER

    def _append_core_row(self, t: QTableWidget, name: str, sci_name: str,
                         arr: list, tier: int = _DEFAULT_TIER) -> None:
        r = self._new_row(t, name, sci_name, _ROW_CORE, tr("핵심"), tier)
        for i, col in enumerate(_COL_CORE):
            t.setItem(r, col, _mk_item(_fmt_num(arr[i] if i < len(arr) else None)))
        for col in _COL_EQ_ONLY:
            t.setItem(r, col, _mk_item("", editable=False))

    def _append_eq_row(self, t: QTableWidget, name: str, sci_name: str, rec: dict,
                       origin: str, tier: int = _DEFAULT_TIER) -> None:
        label = tr("국내") if origin == _ORIGIN_DOM else tr("국외")
        r = self._new_row(t, name, sci_name, origin, label, tier)
        rng = rec.get("range") or [None, None]
        v2 = rec.get("var2") or {}
        values = {
            _COL_DMIN: _fmt_num(rng[0]), _COL_DMAX: _fmt_num(rng[1]),
            _COL_EQ: rec.get("equation") or "",
            _COL_V1: rec.get("var1") or "DBH (cm)",
            _COL_V2: v2.get("label") or "",
            _COL_V2MIN: _fmt_num(v2.get("min")) if v2 else "",
            _COL_V2MAX: _fmt_num(v2.get("max")) if v2 else "",
            _COL_V2DEF: _fmt_num(v2.get("default")) if v2 else "",
        }
        for col, text in values.items():
            t.setItem(r, col, _mk_item(text))
        for col in _COL_CORE_ONLY:
            t.setItem(r, col, _mk_item("", editable=False))

    def _new_row(self, t: QTableWidget, name: str, sci_name: str, row_kind: str,
                 origin_label: str, tier: int = _DEFAULT_TIER) -> int:
        r = t.rowCount()
        t.insertRow(r)
        swap = (_LANG == "en" and bool(sci_name))
        name_it = _mk_item(sci_name if swap else name, editable=not swap)
        _set_true_name(name_it, name)
        name_it.setData(_ROLE_ROW_KIND, row_kind)
        t.setItem(r, _COL_NAME, name_it)
        t.setItem(r, _COL_SCI, _mk_item(sci_name))
        t.setItem(r, _COL_ORIGIN, _mk_item(origin_label, editable=False))
        tier_it = _mk_item(str(tier))
        tier_it.setTextAlignment(Qt.AlignCenter)
        t.setItem(r, _COL_TIER, tier_it)
        return r

    @staticmethod
    def _row_kind(t: QTableWidget, r: int) -> str:
        item = t.item(r, _COL_NAME)
        return (item.data(_ROLE_ROW_KIND) if item else None) or _ROW_CORE

    # ── 추가 / 삭제 (세 대상지에 함께 적용) ───────────────────────
    def add_row(self):
        kind = self._current_kind()
        name = tr("새수종")
        existing = {
            _get_true_name(self.env_tables[(self._env_list[0], k)].item(r, _COL_NAME))
            for k in (_KIND_TREE, _KIND_SHRUB)
            for r in range(self.env_tables[(self._env_list[0], k)].rowCount())
        }
        candidate, n = name, 2
        while candidate in existing:
            candidate, n = "%s%d" % (name, n), n + 1

        arr = ([0.1, 2.5, 0.5, 1, 30, 0.1, 0.1, 0.1] if kind == _KIND_TREE
               else [0.0002, 2.5, 0.5, 0.5, 4.0, 0.2, 0.2, 0.2])
        self._loading = True
        try:
            for env in self._env_list:
                self._append_core_row(self.env_tables[(env, kind)], candidate, "",
                                      list(arr))
        finally:
            self._loading = False

        t = self._current_table()
        r = t.rowCount() - 1
        t.scrollToItem(t.item(r, _COL_NAME))
        t.setCurrentCell(r, _COL_NAME)
        t.editItem(t.item(r, _COL_NAME))
        self._set_dirty(True)

    def delete_selected(self):
        t = self._current_table()
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.information(self, tr("선택 삭제"), tr("삭제할 행을 먼저 선택하세요."))
            return
        names = [_get_true_name(t.item(r, _COL_NAME)) for r in reversed(rows)]
        if QMessageBox.question(
                self, tr("선택 삭제"),
                tr("{n}개 수종을 세 대상지에서 모두 삭제할까요?\n{names}")
                .format(n=len(rows), names=", ".join(names)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        targets = set(names)
        self._loading = True
        try:
            for (_env, _kind), table in self.env_tables.items():
                for r in range(table.rowCount() - 1, -1, -1):
                    if _get_true_name(table.item(r, _COL_NAME)) in targets:
                        table.removeRow(r)
        finally:
            self._loading = False
        self._set_dirty(True)

    # ── 검증 + JSON 조립 ──────────────────────────────────────────
    def validate_and_build(self) -> tuple[list[str], dict | None]:
        """표 내용을 검증하고 저장할 dict 를 만든다. (오류목록, dict|None)"""
        if self._data is None:
            return [tr("먼저 species_data.json 을 선택하세요.")], None
        errors: list[str] = []
        sci_map: dict[str, str] = {}
        out = dict(self._data)

        sections: dict[str, dict] = {
            _SECTION_TREE: {}, _SECTION_SHRUB: {},
            _SECTION_DOM: {}, _SECTION_FOR: {},
        }

        tiers: dict = {}
        for env in self._env_list:
            for kind in (_KIND_TREE, _KIND_SHRUB):
                self._collect_env_table(env, kind, sections, sci_map, errors, tiers)
        if errors:
            return errors, None

        for section, table in sections.items():
            out[section] = table
        out["ENVIRONMENT_GROWTH_FACTORS"] = self._collect_factors()
        out["SPECIES_GROWTH_TIERS"] = tiers

        schema = dict(out.get("_schema") or {})
        schema["assessment_diameter_unit"] = "cm"
        schema["TREE_BASE_equation_diameter_unit"] = _section_equation_unit(
            self._data, _SECTION_TREE)
        schema["SHRUB_SPECIES_equation_diameter_unit"] = _section_equation_unit(
            self._data, _SECTION_SHRUB)
        schema["growth_diameter_unit"] = "cm/year"
        schema["growth_factor_note"] = _GROWTH_FACTOR_NOTE
        out["_schema"] = schema

        old_sci = dict(self._data.get("SPECIES_EN") or {})
        live = {_base_name(n) for section in sections.values() for n in section}
        new_sci = {b: v for b, v in old_sci.items() if b in live}
        new_sci.update(sci_map)
        out["SPECIES_EN"] = new_sci

        ordered = {}
        for k in ("_schema", "ENVIRONMENTS", "ENVIRONMENTS_EN", "SPECIES_EN",
                  "ENVIRONMENT_GROWTH_FACTORS", "SPECIES_GROWTH_TIERS", "SPECIES_GROWTH_FACTORS",
                  _SECTION_TREE, _SECTION_SHRUB, _SECTION_DOM, _SECTION_FOR):
            if k in out:
                ordered[k] = out[k]
        for k, v in out.items():
            ordered.setdefault(k, v)
        return [], ordered

    def _collect_factors(self) -> dict:
        result: dict = {}
        for env in self._env_list:
            slot = {}
            for tier in _TIERS:
                spin = self.factor_spins.get((env, tier))
                slot[_tier_key(tier)] = _num_out(spin.value() if spin is not None else 1.0)
            result[env] = slot
        return result

    def _collect_env_table(self, env: str, kind: str, sections: dict,
                           sci_map: dict, errors: list, tiers: dict) -> None:
        t = self.env_tables[(env, kind)]
        core_section = _SECTION_TREE if kind == _KIND_TREE else _SECTION_SHRUB
        storage_scale = _display_scale(self._data, core_section)
        kind_label = tr("교목") if kind == _KIND_TREE else tr("관목")
        seen: set[str] = set()

        for r in range(t.rowCount()):
            name = _get_true_name(t.item(r, _COL_NAME)).strip()
            where = "%s / %s #%d" % (_env_label(env, self._data), kind_label, r + 1)
            if not name:
                errors.append(tr("{where}: 수종명이 비어 있습니다").format(where=where))
                continue
            if name in seen:
                errors.append(tr("{where}: 수종명 '{name}' 이 중복됩니다")
                              .format(where=where, name=name))
                continue
            seen.add(name)

            tier_text = (t.item(r, _COL_TIER).text() if t.item(r, _COL_TIER) else "").strip()
            if tier_text not in ("1", "2", "3"):
                errors.append(tr("{where}: '{name}' 의 생장 티어는 1, 2, 3 중 하나여야 합니다")
                              .format(where=where, name=name))
                continue
            tiers.setdefault(name, {})[env] = int(tier_text)

            row_kind = self._row_kind(t, r)
            sci_text = t.item(r, _COL_SCI).text() if t.item(r, _COL_SCI) else ""
            base = _base_name(name)
            if sci_text.strip() and base not in sci_map:
                sci_map[base] = sci_text.strip()

            if row_kind == _ROW_CORE:
                record = self._read_core_row(t, r, name, where, storage_scale, errors)
                if record is not None:
                    slot = sections[core_section].setdefault(name, {"by_env": {}})
                    slot["by_env"][env] = record
            else:
                section = _SECTION_DOM if row_kind == _ORIGIN_DOM else _SECTION_FOR
                record = self._read_eq_row(t, r, name, where, errors)
                if record is not None:
                    slot = sections[section].setdefault(name, {"by_env": {}})
                    slot["by_env"][env] = record

    def _read_core_row(self, t: QTableWidget, r: int, name: str, where: str,
                       storage_scale: float, errors: list):
        values = []
        for i, col in enumerate(_COL_CORE):
            what = "%s '%s' / %s" % (where, name, tr(_MERGED_COLS[col][0]))
            cell = t.item(r, col)
            try:
                values.append(_num_out(_parse_num(cell.text() if cell else "", what)))
            except ValueError as exc:
                errors.append(str(exc))
                return None
        if values[3] > values[4]:
            errors.append(tr("{label} '{name}': 최소직경({a})이 최대직경({b})보다 큽니다")
                          .format(label=where, name=name,
                                  a=_fmt_num(values[3]), b=_fmt_num(values[4])))
            return None
        if values[0] <= 0 or values[1] <= 0:
            errors.append(tr("{label} '{name}': 계수 a, b 는 0 보다 커야 합니다")
                          .format(label=where, name=name))
            return None
        if storage_scale != 1.0:
            values[3] = _num_out(float(values[3]) * storage_scale)
            values[4] = _num_out(float(values[4]) * storage_scale)
        return values

    def _read_eq_row(self, t: QTableWidget, r: int, name: str, where: str,
                     errors: list):
        g = lambda c: (t.item(r, c).text() if t.item(r, c) else "").strip()
        equation = g(_COL_EQ)
        if not equation:
            errors.append(tr("{where}: '{name}' 의 상대생장식이 비어 있습니다")
                          .format(where=where, name=name))
            return None

        rmin_text, rmax_text = g(_COL_DMIN), g(_COL_DMAX)
        rng = [None, None]
        if rmin_text or rmax_text:
            try:
                rng = [_num_out(_parse_num(rmin_text, "%s / %s" % (where, tr("최소")))),
                       _num_out(_parse_num(rmax_text, "%s / %s" % (where, tr("최대"))))]
            except ValueError as exc:
                errors.append(str(exc))
                return None
            if rng[0] > rng[1]:
                errors.append(tr("{label} '{name}': 최소직경({a})이 최대직경({b})보다 큽니다")
                              .format(label=where, name=name,
                                      a=_fmt_num(rng[0]), b=_fmt_num(rng[1])))
                return None

        var2_label = g(_COL_V2)
        var2 = None
        if var2_label:
            try:
                var2 = {
                    "label": var2_label,
                    "min": _num_out(_parse_num(g(_COL_V2MIN) or "0",
                                               "%s / %s" % (where, tr("변수2 최소")))),
                    "max": _num_out(_parse_num(g(_COL_V2MAX) or "100",
                                               "%s / %s" % (where, tr("변수2 최대")))),
                    "default": _num_out(_parse_num(g(_COL_V2DEF) or "10",
                                                   "%s / %s" % (where, tr("변수2 기본값")))),
                }
            except ValueError as exc:
                errors.append(str(exc))
                return None

        sample_x = rng[0] if rng[0] else 10.0
        if not sample_x or sample_x <= 0:
            sample_x = 10.0
        try:
            _eval_equation(equation, float(sample_x),
                           float(var2["default"]) if var2 else None)
        except Exception as exc:  # noqa: BLE001 — 평가 실패 메시지를 그대로 보여준다
            errors.append(tr("{where}: '{name}' 식 평가 실패 — {error}")
                          .format(where=where, name=name, error=exc))
            return None

        record = {"equation": equation, "range": rng,
                  "var1": g(_COL_V1) or "DBH (cm)"}
        if var2 is not None:
            record["var2"] = var2
        return record

    def mark_saved(self, data: dict):
        """저장 완료 후 원본을 갱신하고 '변경 없음' 으로."""
        self._data = data
        self._set_dirty(False)

    # ── 언어 전환 시 표 내용 보존 ─────────────────────────────────
    def snapshot(self) -> dict:
        rows = {}
        for (env, kind), t in self.env_tables.items():
            cells_all = []
            for r in range(t.rowCount()):
                cells = [(t.item(r, c).text() if t.item(r, c) else "")
                         for c in range(t.columnCount())]
                cells[_COL_NAME] = _get_true_name(t.item(r, _COL_NAME))
                cells_all.append([self._row_kind(t, r)] + cells)
            rows["%s\x00%s" % (env, kind)] = cells_all
        factors = {"%s\x00%s" % (env, tier): spin.value()
                   for (env, tier), spin in self.factor_spins.items()}
        return {"data": self._data, "dirty": self._dirty, "rows": rows,
                "factors": factors, "tab": self.tabs.currentIndex()}

    def restore(self, snap: dict):
        self._loading = True
        try:
            self._data = snap.get("data")
            for (env, tier), spin in self.factor_spins.items():
                value = (snap.get("factors") or {}).get("%s\x00%s" % (env, tier))
                if value:
                    spin.setValue(float(value))
            for (env, kind), t in self.env_tables.items():
                t.setRowCount(0)
                for packed in (snap.get("rows") or {}).get("%s\x00%s" % (env, kind), []):
                    row_kind, cells = packed[0], packed[1:]
                    r = t.rowCount()
                    t.insertRow(r)
                    true_name = cells[_COL_NAME] if cells else ""
                    sci_name = cells[_COL_SCI] if len(cells) > _COL_SCI else ""
                    swap = (_LANG == "en" and bool(sci_name))
                    editable_cols = (_COL_CORE if row_kind == _ROW_CORE
                                     else _COL_EQ_FIELDS) + (_COL_TIER,)
                    for c, text in enumerate(cells):
                        if c == _COL_NAME:
                            it = _mk_item(sci_name if swap else true_name,
                                          editable=not swap)
                            _set_true_name(it, true_name)
                            it.setData(_ROLE_ROW_KIND, row_kind)
                        elif c == _COL_SCI:
                            it = _mk_item(text)
                        elif c == _COL_ORIGIN:
                            it = _mk_item(text, editable=False)
                        else:
                            it = _mk_item(text, editable=c in editable_cols)
                        t.setItem(r, c, it)
                _tidy_columns(t)
            self.tabs.setCurrentIndex(snap.get("tab", 0))
        finally:
            self._loading = False
        self._set_dirty(bool(snap.get("dirty")))
        self._sync_buttons()


# ─────────────────────────── 메인 창 ───────────────────────────

class UpdaterWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            tr("수종 데이터 업데이터 (자체 완결형) - ForeCarb v{version}")
            .format(version=__version__)
        )
        self.setMinimumWidth(960)
        self._worker: BuildWorker | None = None
        self._out_user_edited = False   # 출력 폴더를 사용자가 직접 지정했는지
        self._editor_loaded_path: Path | None = None   # 편집기에 올라간 JSON 경로
        self._setup_ui()
        self._auto_detect()

    def _on_language_changed(self, _index: int) -> None:
        """언어를 저장하고 창을 다시 만들어 즉시 반영한다 (입력값은 그대로 유지)."""
        global _LANG
        code = self.lang_combo.currentData()
        if code == _LANG:
            return
        _LANG = code
        _save_language(code)
        _apply_app_font(QApplication.instance())
        self._rebuild_ui()

    def _on_zoom_changed(self, _index: int) -> None:
        """화면 배율을 저장하고 폰트·여백을 다시 계산해 창을 재구성한다."""
        zoom = self.zoom_combo.currentData()
        if zoom is None or abs(zoom - _ZOOM) < 1e-6:
            return
        _save_zoom(zoom)
        _set_ui_scale(zoom)
        _apply_app_font(QApplication.instance())
        _apply_readability_theme(QApplication.instance())
        self._rebuild_ui()
        _fit_window(self)

    def _rebuild_ui(self) -> None:
        """중앙 위젯을 새로 만들되 입력 경로·편집 중인 표 내용은 그대로 유지한다."""
        keep = (self.json_row.edit.text(), self.out_row.edit.text(),
                self.exe_row.edit.text(), self._out_user_edited, self.exe_name_edit.text())
        snap = self.editor.snapshot()
        self.setWindowTitle(
            tr("수종 데이터 업데이터 (자체 완결형) - ForeCarb v{version}")
            .format(version=__version__)
        )
        old = self.centralWidget()
        self._setup_ui()
        old.deleteLater()
        # 경로를 되돌릴 때 편집기가 다시 로드되지 않도록 먼저 스냅샷을 복원한다
        self.editor.restore(snap)
        self.json_row.edit.blockSignals(True)
        self.json_row.edit.setText(keep[0])
        self.json_row.edit.blockSignals(False)
        self._recheck_json(load_editor=False)
        self.out_row.edit.setText(keep[1])
        self.exe_row.edit.setText(keep[2])
        self._out_user_edited = keep[3]
        self.exe_name_edit.setText(keep[4])

    def _setup_ui(self):
        root = QWidget()
        root.setObjectName("updaterRoot")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        v = QVBoxLayout(root)
        v.setSpacing(_px(14))
        v.setContentsMargins(_px(18), _px(16), _px(18), _px(18))

        # ── 화면 제목·작업 안내·표시 설정 ────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(_px(20))
        brand = QVBoxLayout()
        brand.setSpacing(_px(3))
        page_title = QLabel(tr("ForeCarb 상대생장식 라이브러리 관리"))
        page_title.setObjectName("pageTitle")
        page_subtitle = QLabel(tr("JSON을 열고 수종·계수를 검토한 뒤 저장하여 ForeCarb에 적용합니다."))
        page_subtitle.setObjectName("pageSubtitle")
        page_subtitle.setWordWrap(True)
        brand.addWidget(page_title)
        brand.addWidget(page_subtitle)
        header_row.addLayout(brand, 1)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(_px(8))
        settings_row.addWidget(QLabel(tr("언어 / Language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("한국어", "ko")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setCurrentIndex(1 if _LANG == "en" else 0)
        self.lang_combo.setMinimumWidth(_px(150))
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        settings_row.addWidget(self.lang_combo)
        settings_row.addSpacing(_px(10))
        settings_row.addWidget(QLabel(tr("화면 배율")))
        self.zoom_combo = QComboBox()
        for z, label in _ZOOM_CHOICES:
            self.zoom_combo.addItem(label, z)
        idx = min(range(len(_ZOOM_CHOICES)), key=lambda i: abs(_ZOOM_CHOICES[i][0] - _ZOOM))
        self.zoom_combo.setCurrentIndex(idx)
        self.zoom_combo.setMinimumWidth(_px(100))
        self.zoom_combo.setToolTip(tr("화면 배율을 조정합니다"))
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)
        settings_row.addWidget(self.zoom_combo)
        header_row.addLayout(settings_row)
        v.addLayout(header_row)

        workflow_hint = QLabel(
            tr("작업 순서: 1. JSON 열기  →  2. 수종·계수 편집  →  3. 저장·검증  →  4. exe 재빌드 또는 JSON 적용"))
        workflow_hint.setObjectName("workflowHint")
        workflow_hint.setWordWrap(True)
        v.addWidget(workflow_hint)

        # 세 경로 행의 라벨 폭을 현재 폰트로 잰 가장 긴 라벨에 맞춘다 (배율이 커져도 잘리지 않음)
        global _STATUS_INDENT
        fm = self.fontMetrics()
        _label_texts = ("species_data.json", tr("출력 폴더 (exe 저장 위치)"), tr("ForeCarb.exe 위치"))
        self._label_w = max(_px(215), max(fm.horizontalAdvance(t) for t in _label_texts) + _px(16))
        _STATUS_INDENT = self._label_w + _px(8)

        # ── 통합 JSON 선택 ─────────────────────────────────────────
        json_grp = QGroupBox(tr("수종 데이터 JSON (통합 species_data.json)"))
        jl = QVBoxLayout(json_grp)
        self.json_row = FilePickRow("species_data.json", label_width=self._label_w)
        self.json_row.btn.clicked.connect(self._pick_json)
        self.json_row.edit.textChanged.connect(self._recheck_json)
        self.json_status = QLabel(tr("— 파일을 선택하면 검증됩니다"))
        self.json_status.setWordWrap(True)      # 긴 메시지가 창 폭을 밀어올리지 않도록
        self.json_status.setStyleSheet(_status_css("gray"))
        jl.addWidget(self.json_row)
        jl.addWidget(self.json_status)
        v.addWidget(json_grp)

        # ── 수종 데이터 편집기 (표) ─────────────────────────────────
        self.editor = SpeciesEditor()
        self.editor.save_requested.connect(self._save_editor)
        v.addWidget(self.editor, 3)

        # ── ① exe 재빌드 (자체 완결) ───────────────────────────────
        build_grp = QGroupBox(tr("① exe 재빌드   —   내장 소스로 새 ForeCarb.exe 생성 (권장)"))
        build_grp.setStyleSheet("QGroupBox { font-weight: bold; }")
        bl = QVBoxLayout(build_grp)

        self.out_row = FilePickRow(tr("출력 폴더 (exe 저장 위치)"), tr("폴더..."), label_width=self._label_w)
        self.out_row.btn.clicked.connect(self._pick_out_dir)
        self.out_row.edit.textEdited.connect(self._mark_out_edited)
        bl.addWidget(self.out_row)

        name_row = QHBoxLayout()
        name_label = QLabel(tr("EXE 파일 이름"))
        name_label.setFixedWidth(self._label_w)
        self.exe_name_edit = QLineEdit(MAIN_EXE_NAME)
        self.exe_name_edit.setPlaceholderText(MAIN_EXE_NAME)
        name_row.addWidget(name_label)
        name_row.addWidget(self.exe_name_edit)
        bl.addLayout(name_row)

        self.build_btn = QPushButton(tr("새 exe 빌드 (PyInstaller)"))
        self.build_btn.setObjectName("primaryAction")
        self.build_btn.setFixedHeight(_px(48))
        f = self.build_btn.font(); f.setBold(True)   # 크기는 앱 폰트(스케일 적용)를 그대로 따른다
        self.build_btn.setFont(f)
        self.build_btn.clicked.connect(self._start_build)
        bl.addWidget(self.build_btn)

        self.build_status = QLabel(tr("준비"))
        self.build_status.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.build_status)
        v.addWidget(build_grp)

        # ── ② JSON 적용 (Python 불필요) ────────────────────────────
        apply_grp = QGroupBox(tr("② JSON 적용   —   기존 exe 옆에 복사만 (Python 불필요)"))
        al = QVBoxLayout(apply_grp)
        self.exe_row = FilePickRow(tr("ForeCarb.exe 위치"), tr("찾기..."), label_width=self._label_w)
        self.exe_row.btn.clicked.connect(self._pick_exe)
        self.exe_row.edit.textChanged.connect(self._recheck_exe)
        self.exe_status = QLabel("")
        self.exe_status.setWordWrap(True)       # 긴 exe 경로가 창의 최소 폭을 키우지 않도록
        self.exe_status.setStyleSheet(_status_css(None))
        al.addWidget(self.exe_row)
        al.addWidget(self.exe_status)

        self.apply_btn = QPushButton(tr("JSON 적용 (복사)"))
        self.apply_btn.setObjectName("primaryAction")
        self.apply_btn.setFixedHeight(_px(42))
        self.apply_btn.clicked.connect(self._apply_json)
        al.addWidget(self.apply_btn)

        self.apply_status = QLabel(tr("준비"))
        self.apply_status.setAlignment(Qt.AlignCenter)
        al.addWidget(self.apply_status)
        v.addWidget(apply_grp)

        # ── 로그 ──────────────────────────────────────────────────
        log_grp = QGroupBox(tr("로그"))
        ll = QVBoxLayout(log_grp)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont(font_family(_LANG), _pt(CAPTION_PT)))
        self.log.setMinimumHeight(_px(180))
        ll.addWidget(self.log)
        v.addWidget(log_grp, 1)

    # ── 자동 탐색 ──────────────────────────────────────────────────

    def _auto_detect(self):
        # 내장/근처 JSON 자동 채움
        for cand in (HERE / JSON_NAME, SRC_ROOT / JSON_NAME):
            if cand.exists():
                self.json_row.edit.setText(str(cand))
                break
        # 출력 폴더 기본값 = updater 위치
        self.out_row.edit.setText(str(HERE))
        # 기존 exe 자동 탐색
        exe = _auto_find_main_exe()
        if exe:
            self.exe_row.edit.setText(str(exe))

    # ── JSON 선택·검증 ──────────────────────────────────────────────

    def _pick_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("통합 species_data.json 선택"), str(HERE), tr("JSON 파일 (*.json)"))
        if path:
            self.json_row.edit.setText(path)
            # "해당 디렉토리에 빌드" — 출력 폴더를 선택한 JSON 이 있는 폴더로 자동 지정
            # (사용자가 이미 직접 바꾼 경우는 존중)
            if not self._out_user_edited:
                self.out_row.edit.blockSignals(True)
                self.out_row.edit.setText(str(Path(path).parent))
                self.out_row.edit.blockSignals(False)

    def _recheck_json(self, load_editor: bool = True):
        p = self.json_row.path
        if not p:
            self.json_status.setText(tr("— 파일을 선택하면 검증됩니다"))
            self.json_status.setStyleSheet(_status_css("gray"))
        elif p.exists():
            ok, msg = _validate_species_json(p)
            # 정상 파일이면 표가 곧바로 채워져 결과가 보이므로 확인 문구를 띄우지 않고,
            # 문제가 있을 때만 사유를 표시한다.
            self.json_status.setText("" if ok else "✗ %s" % msg)
            self.json_status.setStyleSheet(_status_css(None if ok else "red"))
            if ok and load_editor:
                self._load_into_editor(p)
        else:
            self.json_status.setText(tr("파일을 찾을 수 없습니다."))
            self.json_status.setStyleSheet(_status_css("red"))

    def _pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("출력 폴더 선택"), str(HERE))
        if d:
            self._out_user_edited = True
            self.out_row.edit.setText(d)

    def _mark_out_edited(self, _text: str):
        self._out_user_edited = True

    # ── exe 선택 (② 모드) ──────────────────────────────────────────

    def _pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("ForeCarb.exe 선택"), str(HERE), tr("실행 파일 (*.exe)"))
        if path:
            self.exe_row.edit.setText(path)

    def _recheck_exe(self):
        p = self.exe_row.path
        if p and p.exists():
            self.exe_status.setText(f"✓ {p}")
            self.exe_status.setStyleSheet(_status_css("green"))
        elif p:
            self.exe_status.setText(tr("파일을 찾을 수 없습니다."))
            self.exe_status.setStyleSheet(_status_css("red"))
        else:
            self.exe_status.setText("")

    # ── ① exe 재빌드 ────────────────────────────────────────────────

    def _start_build(self):
        if self._worker and self._worker.isRunning():
            return
        if not self._ensure_editor_saved():
            return

        json_path = self.json_row.path
        if not json_path or not json_path.exists():
            self._set_build_status(tr("먼저 species_data.json 을 선택하세요."), "red")
            return
        ok, msg = _validate_species_json(json_path)
        if not ok:
            self._set_build_status(tr("JSON 오류: {msg}").format(msg=msg), "red")
            return

        out_dir = self.out_row.path
        if not out_dir:
            self._set_build_status(tr("출력 폴더를 지정하세요."), "red")
            return

        try:
            exe_name = _normalize_exe_name(self.exe_name_edit.text())
        except ValueError as exc:
            self._set_build_status(str(exc), "red")
            return
        self.exe_name_edit.setText(exe_name)

        # 표준 릴리스 빌드(onefile · 콘솔 숨김 · UPX 없음)만 지원한다 — 나머지는
        # 개발자용 CLI 플래그로만 남겨둔다 (build_exe.py --help 참고).
        options: list[str] = []

        self.log.clear()
        self.build_btn.setEnabled(False)
        self._set_build_status(tr("빌드 중..."), "black")

        self._worker = BuildWorker(json_path, out_dir, options, exe_name=exe_name)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_build_done)
        self._worker.start()

    def _on_build_done(self, success: bool, info: str):
        self.build_btn.setEnabled(True)
        self.log.appendPlainText("=" * 70)
        if success:
            self._set_build_status(tr("빌드 완료!"), "green")
            self.log.appendPlainText(tr("[완료] 새 실행파일: {path}").format(path=info))
        else:
            self._set_build_status(tr("빌드 실패 — 로그 확인"), "red")
            self.log.appendPlainText(tr("[실패] {error}").format(error=info))

    def _set_build_status(self, text: str, color: str):
        self.build_status.setText(text)
        self.build_status.setStyleSheet(f"color: {color};")

    # ── ② JSON 적용 ────────────────────────────────────────────────

    def _apply_json(self):
        if not self._ensure_editor_saved():
            return
        json_path = self.json_row.path
        if not json_path or not json_path.exists():
            self.apply_status.setText(tr("먼저 species_data.json 을 선택하세요."))
            self.apply_status.setStyleSheet("color: red;")
            return
        ok, _ = _validate_species_json(json_path)
        if not ok:
            self.apply_status.setText(tr("JSON 검증에 실패했습니다 (상단 상태 확인)."))
            self.apply_status.setStyleSheet("color: red;")
            return

        exe_path = self.exe_row.path
        if not exe_path or not exe_path.exists():
            self.apply_status.setText(tr("ForeCarb.exe 위치를 선택하세요."))
            self.apply_status.setStyleSheet("color: red;")
            return

        target_dir = exe_path.parent
        dst = target_dir / JSON_NAME
        shutil.copy2(json_path, dst)
        # 구버전 분리 JSON 이 남아 통합본을 가리지 않도록 정리
        removed = []
        for _old in ("carbon1_species_data.json", "carbon2_species_data.json"):
            _p = target_dir / _old
            if _p.exists():
                try:
                    _p.unlink()
                    removed.append(_old)
                except Exception:
                    pass

        self.log.clear()
        self.log.appendPlainText(
            tr("[완료] {name} → {path}").format(name=JSON_NAME, path=dst))
        if removed:
            self.log.appendPlainText(
                tr("[정리] 구버전 JSON 제거: {names}").format(names=", ".join(removed)))
        self.log.appendPlainText("")
        self.log.appendPlainText(tr("ForeCarb.exe 를 다시 실행하면 새 수종 데이터가 적용됩니다."))
        self.apply_status.setText(tr("완료 — JSON 복사됨"))
        self.apply_status.setStyleSheet("color: green;")

    # ── 수종 데이터 편집기 ───────────────────────────────────────────

    def _load_into_editor(self, path: Path):
        """검증된 JSON 을 표에 올린다. 같은 파일이면 다시 올리지 않는다."""
        try:
            same = self._editor_loaded_path is not None and path.resolve() == self._editor_loaded_path.resolve()
        except OSError:
            same = False
        if same and self.editor.is_loaded():
            return
        if self.editor.is_dirty():
            if QMessageBox.question(
                    self, tr("미저장 변경"), tr("편집 중인 내용을 버리고 새 파일을 불러올까요?"),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            self._append_log(tr("JSON 파싱 오류: {error}").format(error=e))
            return
        self.editor.load(data)
        self._editor_loaded_path = path

    def _save_editor(self) -> bool:
        """표 내용을 검증해 JSON 파일에 쓴다. 성공하면 True."""
        path = self.json_row.path
        if not path:
            QMessageBox.warning(self, tr("검증 실패"),
                                tr("저장할 JSON 파일 경로가 없습니다. 상단에서 species_data.json 을 지정하세요."))
            return False
        errors, data = self.editor.validate_and_build()
        if errors:
            text = "\n".join("• " + e for e in errors[:30])
            if len(errors) > 30:
                text += "\n…"
            QMessageBox.warning(self, tr("검증 실패"),
                                tr("저장 전 검증에 실패했습니다:\n\n{errors}").format(errors=text))
            for e in errors:
                self._append_log("[!] " + e)
            return False
        try:
            if path.exists():
                bak = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, bak)
                self._append_log(tr("[백업] 이전 파일 → {path}").format(path=bak))
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
        except Exception as e:
            QMessageBox.warning(self, tr("검증 실패"), tr("저장 실패: {error}").format(error=e))
            return False
        self.editor.mark_saved(data)
        self._editor_loaded_path = path
        self._recheck_json(load_editor=False)
        self._append_log(tr("[저장] {path}").format(path=path))
        self._append_log(tr("저장 완료 — 교목 {tree} · 관목 {shrub} · 국내 {dom} · 국외 {for_} 종").format(
            tree=len(data.get("TREE_BASE", {})), shrub=len(data.get("SHRUB_SPECIES", {})),
            dom=len(data.get("DOMESTIC_SPECIES", {})), for_=len(data.get("FOREIGN_SPECIES", {}))))
        return True

    def _ensure_editor_saved(self) -> bool:
        """빌드/적용 직전: 미저장 변경이 있으면 저장할지 묻는다. 진행 가능하면 True."""
        if not self.editor.is_dirty():
            return True
        r = QMessageBox.question(
            self, tr("미저장 변경"),
            tr("편집한 수종 데이터가 아직 파일에 저장되지 않았습니다.\n지금 저장하고 계속할까요?\n\n"
               "예 = 저장 후 진행 · 아니요 = 파일의 기존 내용으로 진행 · 취소 = 중단"),
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            return self._save_editor()
        return r == QMessageBox.No

    # ── 로그 ──────────────────────────────────────────────────────

    def _append_log(self, line: str):
        self.log.appendPlainText(line)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())


def main():
    global _LANG
    _enable_high_dpi()                   # QApplication 생성 전
    app = QApplication(sys.argv)
    _LANG = _current_language()          # 본 프로그램에서 고른 언어를 그대로 따른다
    _set_ui_scale(_load_zoom())          # 모니터 크기 × 저장된 배율
    _apply_app_font(app)
    _apply_readability_theme(app)
    win = UpdaterWindow()
    _fit_window(win)                     # 화면 비율로 크기·중앙 배치 (화면 초과 방지)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
