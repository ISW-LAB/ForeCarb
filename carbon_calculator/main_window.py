# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
FORECAST-SW - PyQt5 메인 윈도우.

레이아웃:
- 좌측: TabWidget 2개 (교목 / 관목)
    * 각 탭 상단에 "추가" 버튼 → 팝업 다이얼로그로 1행 추가
    * 추가된 행은 스크롤 영역에 누적되며 각 행마다 [삭제] 버튼 보유
- 우측 상단: 게이지 3개 (교목/관목/총합) + 숫자 표시
- 우측 중단: 공통 연도 선택 + 교목·관목 그래프 8개 및 시각화
- 우측 하단: 결과 테이블 (그래프 ↔ 테이블 세로 스플리터)
"""
from __future__ import annotations

import datetime
import io
import math
import random
import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTableWidget,
    QTableWidgetItem, QToolButton, QButtonGroup,
    QVBoxLayout, QWidget,
)

from .calculations import (
    CarbonRow, RangeViolation, calculate_carbon, project_future_carbon,
)
from .i18n import environment_name, species_name, tr
from . import species_library as lib
from .species_library import LibraryError, LibraryRecord
from .input_limits import (
    SHRUB_PLANTING_AREA_M2_PER_INDIVIDUAL,
    TREE_PLANTING_AREA_M2_PER_INDIVIDUAL,
    planting_area_budget,
)
from .version import __version__
from .data import (
    DEFAULT_ENVIRONMENT, RESTORATION_ENVIRONMENTS, SpeciesData, shrub_species_for_env,
    tree_species_for_env,
)
from .excel_export import export_carbon1_to_excel
from .plotting import MatplotlibCanvas
from .projections import project_record, assumption_note
from .survival import DEFAULT_SURVIVAL_PCT, survival_factors
from . import preset_io
from .ui_scale import apply_dialog_size, pt, px
from .typography import HEADING_PT, PLOT_ANNOTATION_PT, PLOT_TITLE_PT, SMALL_PT, VALUE_PT
from .widgets import (
    LinearGauge, NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox, ResultTable,
    SearchableComboBox,
)
from .tree_simulation.models import VisualizationInputGroup
from .tree_simulation.snapshot import build_snapshot, input_fingerprint
from .tree_simulation.visualization_tab import VegetationVisualizationTab


# 한 행의 계산 결과 + 그래프 투영에 필요한 모든 정보를 담는 경량 컨테이너.
# label / curve 는 계산 후 `_build_curves` 에서 채워진다.
#   curve      : 기존 생장량 또는 명시적 가정으로 계산한 연도축 곡선
#   d_axis/d_curve : 직경축 곡선 (77종 전부)
@dataclass
class _Entry:
    species: str
    record: LibraryRecord      # core·extension 공통 레코드
    species_data: Optional[SpeciesData]   # core 만: 오버라이드가 적용된 최종 계수
    diameter: float
    quantity: int
    carbon_kg: float
    unit: str
    var2: Optional[float] = None   # 다변수 식의 두 번째 입력(수고·밀도·LAI·길이)
    label: str = ""
    curve: object = None       # numpy 배열 (연도별)
    d_axis: object = None      # numpy 배열 (직경축 x)
    d_curve: object = None     # numpy 배열 (직경축 탄소저장량)
    # 생존율(%) — 현재(0년차 수량에 적용)·연간(해마다 누적). 100/100 = 전량 생존.
    survival_initial: float = DEFAULT_SURVIVAL_PCT
    survival_annual: float = DEFAULT_SURVIVAL_PCT
    surv_factor: object = None  # 연차별 생존 비율 S0 × s^t
    surv_curve: object = None   # 생존률 반영 연도별 탄소저장량 (= curve × surv_factor)

    @property
    def supports_year_projection(self) -> bool:
        """연도축 추정이 가능한 항목인지."""
        return self.record.supports_year_projection


# 사용자 편집 가능한 (a, b, CF) 오버라이드 타입.
OverrideCoeffs = Tuple[float, float, float]

# 추정 그래프 x축 기준.
BASIS_YEAR = "year"
BASIS_DIAMETER = "diameter"
BASIS_SURVIVAL = "survival"     # 기여도 원형그래프: 생존률 반영 값 기준
_PIE_SUFFIX = {BASIS_YEAR: "", BASIS_DIAMETER: "_diameter", BASIS_SURVIVAL: "_survival"}

# 그래프 영역 선택 버튼 (탭 두 줄 대신 한 줄).
_SEG_BUTTON_QSS = (
    "QToolButton#segButton { padding: 1px 12px; border: 1px solid #C4CCD3; border-radius: 5px;"
    " background: #FFFFFF; color: #24342B; }"
    "QToolButton#segButton:hover { background: #EEF4EF; }"
    "QToolButton#segButton:checked { background: #2E8B57; color: #FFFFFF; border-color: #2E8B57;"
    " font-weight: bold; }"
    "QToolButton#segButton:disabled { color: #AAB3BA; background: #F4F6F8; }"
)

TEST_TREE_QUANTITY_RANGE = (3, 10)
TEST_SHRUB_QUANTITY_RANGE = (3, 12)
TEST_DIAMETER_MARGIN_RATIO = 0.10


def _coeffs_equal(a1: OverrideCoeffs, a2: OverrideCoeffs, tol: float = 1e-9) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a1, a2))


# 우측 패널에서 주 디스플레이(예측 그래프·시각화 탭)가 차지할 최소 높이 비율.
# 글꼴이 커지면 게이지·결과 표가 높이를 먼저 가져가 그래프가 찌그러지므로,
# 창 크기 변경·스플리터 드래그 때마다 이 비율 이상을 그래프에 보장한다.
MAIN_DISPLAY_MIN_RATIO = 0.50
# 결과 표를 최소(머리글 + 1행)로 두면 목표 비율에 조금 못 미칠 때는 표를 남기고,
# 그래프가 이 비율 아래로 내려가야 할 때만 표 영역을 접는다.
MAIN_DISPLAY_FLOOR_RATIO = 0.40


class _MainDisplayGuard(QObject):
    """세로 스플리터의 첫 칸(그래프)이 패널 높이의 일정 비율 이상이 되도록 유지."""

    def __init__(self, panel: QWidget, splitter: QSplitter, ratio: float = MAIN_DISPLAY_MIN_RATIO):
        super().__init__(panel)
        self._panel, self._splitter, self._ratio = panel, splitter, ratio
        self._busy = False
        self._auto_collapsed = False   # 이 가드가 표 영역을 접었는지 (그때만 다시 편다)
        panel.installEventFilter(self)
        splitter.installEventFilter(self)       # 스플리터 크기는 패널보다 늦게 확정된다
        splitter.splitterMoved.connect(lambda *_: self.enforce())

    def eventFilter(self, obj, event):  # noqa: N802 — Qt 시그니처
        if obj in (self._panel, self._splitter) and event.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self.enforce)
        return False

    def enforce(self) -> None:
        if self._busy:
            return
        sizes = self._splitter.sizes()
        total = sum(sizes)
        if len(sizes) != 2 or total <= 0:
            return
        lower = self._splitter.widget(1)
        lower_min = max(lower.minimumSizeHint().height(), lower.minimumHeight())
        panel_h = self._panel.height()
        wanted = int(panel_h * self._ratio)
        if total - wanted >= lower_min:
            best = [wanted, total - wanted]               # 목표 비율 + 나머지는 표
        elif total - lower_min >= panel_h * MAIN_DISPLAY_FLOOR_RATIO:
            best = [total - lower_min, lower_min]         # 표는 최소, 그래프는 최대한
        else:
            best = [total, 0]                             # 표 영역을 접는다
        if sizes[1] == 0 and self._auto_collapsed and best[1] > 0:
            new = best                                    # 자동으로 접었던 표를 공간이 생기면 다시 편다
        elif sizes[0] < best[0]:
            new = best
        else:
            return                                    # 비율 충족 (사용자가 직접 접은 표는 그대로 둔다)
        self._busy = True
        try:
            self._splitter.setSizes(new)
            self._auto_collapsed = new[1] == 0
        finally:
            self._busy = False


def _survival_spin(value: float = DEFAULT_SURVIVAL_PCT) -> NoWheelDoubleSpinBox:
    """생존율(%) 입력 — 0~100, 소수 1자리."""
    spin = NoWheelDoubleSpinBox()
    spin.setRange(0.0, 100.0)
    spin.setDecimals(1)
    spin.setSingleStep(1.0)
    spin.setValue(float(value))
    return spin


# ------------------------------ 입력 다이얼로그 ------------------------------

class AddSpeciesDialog(QDialog):
    """
    수종/직경/수량 + 상대생장식 (a, b, CF) 편집 다이얼로그.

    좌측 패널: 카테고리(수종) · 변수(DBH/RCD) · 개수(수량)
    우측 패널:
      (1) 상대생장식 [a, b, CF 편집 가능 — 수정하면 그 행 계산에 반영]
      (2) CSV 권장 정보 (유효 범위, 성장차 - 읽기 전용)
    """

    def __init__(self, kind: str, species_map: dict, names: list, parent=None):
        super().__init__(parent)
        self.kind = kind  # "tree" or "shrub"
        is_tree = kind == "tree"

        self.setWindowTitle(tr("교목 추가") if is_tree else tr("관목 추가"))
        self.setModal(True)
        apply_dialog_size(self, 820, 560)

        # 통합 라이브러리 레코드 맵/목록을 호출측(MainWindow)에서 주입받는다.
        # core(계수 a·b·CF + 성장차)와 extension(식 문자열)이 함께 들어온다.
        self._species_map = species_map
        self._names = list(names)
        self._last_random_test_values: tuple[str, float, int] | None = None
        self._diameter_unit = "cm"
        diameter_label = tr("변수 ({var} · {unit})").format(
            var="DBH" if is_tree else "RCD", unit=self._diameter_unit)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_left_panel(names, diameter_label), 1)
        body.addWidget(self._build_right_panel(), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.random_test_button = QPushButton(tr("테스트 랜덤"))
        self.random_test_button.setToolTip(tr("유효 범위 안의 테스트 입력값을 자동으로 채웁니다."))
        buttons.addButton(self.random_test_button, QDialogButtonBox.ActionRole)
        buttons.button(QDialogButtonBox.Ok).setText(tr("추가 (Ctrl+Enter)"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("취소"))
        # 일반 Enter 로는 추가되지 않도록 기본 버튼 해제 (keyPressEvent 에서 Ctrl+Enter 만 허용)
        buttons.button(QDialogButtonBox.Ok).setAutoDefault(False)
        buttons.button(QDialogButtonBox.Ok).setDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.random_test_button.clicked.connect(self._fill_random_test_values)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

        # 콤보 변경 시 우측 정보 자동 갱신 + 기본값 로드
        self.combo.currentIndexChanged.connect(
            lambda _i: self._on_species_changed(self.combo.current_data())
        )
        self.a_spin.valueChanged.connect(self._refresh_formula)
        self.b_spin.valueChanged.connect(self._refresh_formula)
        self.cf_spin.valueChanged.connect(self._refresh_formula)
        self._on_species_changed(self.combo.current_data())

    def keyPressEvent(self, event) -> None:
        """일반 Enter 로는 닫히지 않게 하고, Ctrl+Enter 일 때만 '추가'(accept)."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ControlModifier:
                self.accept()
            # 일반 Enter: 다이얼로그 동작 없음 (검색창 추천 선택은 별도 처리됨)
            event.accept()
            return
        super().keyPressEvent(event)

    # ----- 좌/우 패널 빌드 -----

    def _build_left_panel(self, names: List[str], diameter_label: str) -> QWidget:
        group = QGroupBox(tr("입력"))
        form = QFormLayout(group)
        form.setSpacing(10)

        self.combo = SearchableComboBox(tr("🔍 수종 검색 (예: 소나무, 회양목)"))
        self.combo.set_items([(species_name(n), n) for n in names])
        form.addRow(tr("카테고리 (수종)"), self.combo)

        # DBH와 RCD 모두 cm로 입력하며, 1 mm에 해당하는 0.1 cm도 표현할 수 있다.
        # 입력 자체는 넓게 열고 검증은 '추가' 클릭 시 수행한다.
        self.diameter_spin = NoWheelDoubleSpinBox()
        self.diameter_spin.setDecimals(2)
        self.diameter_spin.setSingleStep(0.1)
        self.diameter_spin.setRange(0.01, 100000.0)
        self.diameter_spin.setValue(1.0)
        self._diameter_label_widget = QLabel(diameter_label)
        form.addRow(self._diameter_label_widget, self.diameter_spin)

        # 다변수 식(수고·임분밀도·LAI·길이)에서만 보이는 두 번째 입력.
        self.var2_spin = NoWheelDoubleSpinBox()
        self.var2_spin.setDecimals(2)
        self.var2_spin.setSingleStep(0.5)
        self.var2_spin.setRange(0.0, 1000000.0)
        self.var2_spin.setValue(10.0)
        self._var2_label_widget = QLabel(tr("두 번째 변수"))
        form.addRow(self._var2_label_widget, self.var2_spin)
        self._var2_label_widget.setVisible(False)
        self.var2_spin.setVisible(False)

        self.quantity_spin = NoWheelSpinBox()
        self.quantity_spin.setRange(1, 99999)
        self.quantity_spin.setValue(1)
        form.addRow(tr("개수 (수량)"), self.quantity_spin)

        # 생존율: 현재(0년차 수량에 적용) · 연간(해마다 누적). 기본 100 % = 전량 생존.
        self.survival_initial_spin = _survival_spin()
        self.survival_annual_spin = _survival_spin()
        form.addRow(tr("현재 생존율 (%)"), self.survival_initial_spin)
        form.addRow(tr("연간 생존율 (%/년)"), self.survival_annual_spin)
        hint = QLabel(tr("N(t) = 수량 × 현재 생존율 × 연간 생존율^t"))
        hint.setStyleSheet("color: #6B7780;")
        hint.setWordWrap(True)
        form.addRow(hint)

        return group

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # (1) 상대생장식 편집
        eq_group = QGroupBox(tr("(1) 상대생장식 — 값 수정 시 이 행의 계산에 반영"))
        eq_layout = QVBoxLayout(eq_group)
        eq_layout.setSpacing(8)

        self.formula_label = QLabel()
        self.formula_label.setStyleSheet(
            "background: #F0F8F0; padding: 8px; border: 1px solid #C8E0C8; "
            "border-radius: 3px; font-weight: bold;"
        )
        self.formula_label.setAlignment(Qt.AlignCenter)
        eq_layout.addWidget(self.formula_label)

        form = QFormLayout()
        form.setSpacing(8)

        self.a_spin = NoWheelDoubleSpinBox()
        self.a_spin.setRange(0.0, 9999.0)
        self.a_spin.setDecimals(8)
        self.a_spin.setSingleStep(0.0001)
        form.addRow(tr("계수 a"), self.a_spin)

        self.b_spin = NoWheelDoubleSpinBox()
        self.b_spin.setRange(0.0, 20.0)
        self.b_spin.setDecimals(4)
        self.b_spin.setSingleStep(0.01)
        form.addRow(tr("지수 b"), self.b_spin)

        self.cf_spin = NoWheelDoubleSpinBox()
        self.cf_spin.setRange(0.0, 1.0)
        self.cf_spin.setDecimals(2)
        self.cf_spin.setSingleStep(0.05)
        form.addRow(tr("탄소전환계수 CF"), self.cf_spin)
        eq_layout.addLayout(form)

        self.reset_button = QPushButton(tr("기본값으로 복원"))
        self.reset_button.clicked.connect(self._reset_to_defaults)
        eq_layout.addWidget(self.reset_button, alignment=Qt.AlignRight)
        v.addWidget(eq_group)

        # (2) 원자료 기준값 (읽기 전용)
        info_group = QGroupBox(tr("(2) 원자료 기준값 (읽기 전용)"))
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(6)

        self.range_value_label = QLabel("-")
        self.range_value_label.setWordWrap(True)
        info_layout.addRow(tr("적합 직경범위"), self.range_value_label)

        self.growth_value_label = QLabel("-")
        info_layout.addRow(tr("연간 직경생장량\n(1~10 / 11~20 / 21~30년, cm/yr)"), self.growth_value_label)

        self.default_coeffs_label = QLabel("-")
        self.default_coeffs_label.setStyleSheet("color: #555;")
        info_layout.addRow(tr("기본 (a, b, CF)"), self.default_coeffs_label)

        v.addWidget(info_group)

        # 레코드 출처·기존 또는 가정 생장률 안내.
        self.source_note_label = QLabel()
        self.source_note_label.setWordWrap(True)
        self.source_note_label.setStyleSheet(
            "color: #7A5C00; background: #FFF8E1; border: 1px solid #F0E0A0; "
            "border-radius: 4px; padding: 6px;"
        )
        v.addWidget(self.source_note_label)

        v.addStretch(1)
        return wrap

    # ----- 이벤트 -----

    @staticmethod
    def _test_diameter_range(rec: LibraryRecord) -> tuple[float, float]:
        """수종 유효 범위(cm)의 양 끝 10%를 가급적 피한 테스트 구간."""
        span = max(0.0, rec.range_max - rec.range_min)
        low = rec.range_min + span * TEST_DIAMETER_MARGIN_RATIO
        high = rec.range_max - span * TEST_DIAMETER_MARGIN_RATIO
        if low > high:
            low = rec.range_min
            high = rec.range_max
        if low > high:
            value = (rec.range_min + rec.range_max) / 2.0
            return value, value
        return low, high

    def _fill_random_test_values(self) -> None:
        """기존 선택/검증 경로를 유지하면서 유효한 테스트 값만 채운다.

        유효범위가 제공되지 않은 레코드(확장 라이브러리 일부)는 테스트 값을
        생성할 정의역이 없으므로 후보에서 제외한다.
        """
        available = [name for name in self._names
                     if name in self._species_map and self._species_map[name].has_range]
        if not available:
            return
        quantity_low, quantity_high = (
            TEST_TREE_QUANTITY_RANGE if self.kind == "tree" else TEST_SHRUB_QUANTITY_RANGE
        )
        candidate = None
        for _ in range(20):
            species = random.choice(available)
            rec = self._species_map[species]
            diameter_low, diameter_high = self._test_diameter_range(rec)
            diameter = round(random.uniform(diameter_low, diameter_high), 1)
            diameter = max(rec.range_min, min(rec.range_max, diameter))
            candidate = (species, diameter, random.randint(quantity_low, quantity_high))
            if candidate != self._last_random_test_values:
                break
        if candidate is None:
            return
        species, diameter, quantity = candidate
        self._last_random_test_values = candidate

        # 검색으로 목록이 필터된 상태에서도 전체 원본 목록으로 복원한 뒤 기존
        # currentIndexChanged → _on_species_changed 흐름을 그대로 발생시킨다.
        self.combo.search.blockSignals(True)
        self.combo.search.clear()
        self.combo.search.blockSignals(False)
        self.combo.set_items([(species_name(name), name) for name in self._names])
        index = self.combo.combo.findData(species)
        if index >= 0:
            self.combo.combo.setCurrentIndex(index)

        self.diameter_spin.setValue(diameter)
        self.quantity_spin.setValue(quantity)

    def _on_species_changed(self, species: str) -> None:
        rec = self._species_map.get(species)
        if rec is None:
            return

        # 설명변수 라벨 — 레코드마다 DBH/RCD/수고가 다르다.
        self._diameter_label_widget.setText(
            tr("변수 ({label})").format(label=rec.var1_label))

        # 두 번째 변수 입력(다변수 식만).
        self._var2_label_widget.setVisible(rec.is_multivar)
        self.var2_spin.setVisible(rec.is_multivar)
        if rec.is_multivar:
            self._var2_label_widget.setText(rec.var2_label)
            self.var2_spin.setRange(float(rec.var2_min), float(rec.var2_max))
            self.var2_spin.setValue(float(rec.var2_default))

        # 계수 편집은 core 레코드에서만 의미가 있다 (extension 은 식 문자열).
        sp = rec.species_data
        editable = sp is not None
        for spin in (self.a_spin, self.b_spin, self.cf_spin):
            spin.setEnabled(editable)
        self.reset_button.setEnabled(editable)

        self.a_spin.blockSignals(True); self.b_spin.blockSignals(True); self.cf_spin.blockSignals(True)
        if sp is not None:
            self.a_spin.setValue(sp.a)
            self.b_spin.setValue(sp.b)
            self.cf_spin.setValue(sp.cf)
        else:
            self.a_spin.setValue(0.0)
            self.b_spin.setValue(0.0)
            self.cf_spin.setValue(lib.CARBON_FACTOR)
        self.a_spin.blockSignals(False); self.b_spin.blockSignals(False); self.cf_spin.blockSignals(False)

        # 직경 입력은 제한하지 않는다(범위 밖 값도 입력 가능). 다만 수종을 바꿨을 때
        # 현재 값이 새 수종의 유효 범위를 벗어나면 유효 최소값으로 한 번 맞춰 주어
        # 합리적인 기본값에서 시작하도록 한다(사용자는 이후 자유롭게 수정 가능).
        if rec.has_range:
            d = self.diameter_spin.value()
            if d < rec.range_min or d > rec.range_max:
                self.diameter_spin.setValue(max(0.01, float(rec.range_min)))

        # 참고 정보 표시
        self.range_value_label.setText(rec.range_text())
        if sp is not None:
            self.growth_value_label.setText(
                f"{sp.growth_y10:.2f}  /  {sp.growth_y20:.2f}  /  {sp.growth_y21:.2f}"
            )
            self.default_coeffs_label.setText(
                f"a = {sp.a:g} ,  b = {sp.b:g} ,  CF = {sp.cf:g}")
            self.source_note_label.setText(
                tr("핵심 라이브러리 수종 — 연도별·직경 기준 그래프를 모두 지원합니다."))
        else:
            self.growth_value_label.setText(tr("제공 없음 — 연 2% 가정 적용"))
            self.default_coeffs_label.setText(tr("식 문자열 기반 (계수 편집 불가)"))
            self.source_note_label.setText(
                tr("확장 라이브러리 수종 — 연 2% 가정 생장률로 연도별 그래프와 3D를 표시합니다."))
        self._refresh_formula()

    def _refresh_formula(self) -> None:
        species = self.combo.current_data()
        rec = self._species_map.get(species)
        if rec is None:
            return
        if rec.species_data is None:
            self.formula_label.setText(
                f"{rec.formula_text()}\nX = {rec.var1_label}")
            return
        a = self.a_spin.value()
        b = self.b_spin.value()
        cf = self.cf_spin.value()
        x_term = "(10 × X)" if rec.species_data.equation_diameter_unit == "mm" else "X"
        self.formula_label.setText(
            # 두 줄로 나눠 대화상자 폭을 줄인다 (식 한 줄이 창의 최소 폭을 결정했다).
            f"Y  =  {a:g}  ×  {x_term}^{b:g}\n"
            f"C  =  Y  ×  {cf:g}  ×  N      (X = {rec.var1_label})"
        )

    def _reset_to_defaults(self) -> None:
        rec = self._species_map.get(self.combo.current_data())
        if rec is None or rec.species_data is None:
            return
        sp = rec.species_data
        self.a_spin.setValue(sp.a)
        self.b_spin.setValue(sp.b)
        self.cf_spin.setValue(sp.cf)

    def accept(self) -> None:
        """'추가' 시 유효 범위와 식 평가 가능성을 검증. 실패 시 다이얼로그를 닫지 않는다."""
        species = self.combo.current_data()
        rec = self._species_map.get(species)
        if rec is not None:
            d = self.diameter_spin.value()
            if rec.has_range and (d < rec.range_min or d > rec.range_max):
                u = self._diameter_unit
                QMessageBox.warning(
                    self, tr("유효 직경 범위 아님"),
                    tr("입력한 직경 {d:g} {u} 은(는) '{species}'의 유효 범위"
                       "({vmin:g} {u} ~ {vmax:g} {u})를 벗어납니다.\n\n"
                       "값을 유효 범위 안으로 수정한 뒤 다시 [추가]를 눌러 주세요.")
                    .format(d=d, u=u, species=species_name(species),
                            vmin=rec.range_min, vmax=rec.range_max),
                )
                self.diameter_spin.setFocus()
                self.diameter_spin.selectAll()
                return  # 다이얼로그 유지 — 행은 추가되지 않음

            # 확장 레코드는 입력값에서 식이 실제로 평가되는지 미리 확인한다
            # (로그 항의 정의역 밖 입력 등을 추가 시점에 잡아낸다).
            if rec.species_data is None:
                try:
                    lib.carbon_per_individual(rec, d, self._current_var2(rec))
                except LibraryError as exc:
                    QMessageBox.warning(self, tr("입력값 오류"), str(exc))
                    self.diameter_spin.setFocus()
                    self.diameter_spin.selectAll()
                    return
        super().accept()

    # ----- 결과 -----

    def _current_var2(self, rec: LibraryRecord) -> Optional[float]:
        return self.var2_spin.value() if rec.is_multivar else None

    def values(self) -> Tuple[str, float, int, Optional[OverrideCoeffs], Optional[float]]:
        """
        Returns: (species, diameter, quantity, override_coeffs_or_None, var2_or_None)
        override_coeffs 는 core 레코드에서 a/b/CF 중 하나라도 기본값에서 변경된 경우에만
        (a, b, cf) 튜플. extension 레코드는 항상 None.
        """
        species = self.combo.current_data()
        diameter = self.diameter_spin.value()
        quantity = self.quantity_spin.value()

        rec = self._species_map.get(species)
        override = None
        if rec is not None and rec.species_data is not None:
            sp = rec.species_data
            current: OverrideCoeffs = (
                self.a_spin.value(), self.b_spin.value(), self.cf_spin.value())
            if not _coeffs_equal(current, (sp.a, sp.b, sp.cf)):
                override = current

        var2 = self._current_var2(rec) if rec is not None else None
        return species, diameter, quantity, override, var2

    def survival_values(self) -> Tuple[float, float]:
        """(현재 생존율 %, 연간 생존율 %)."""
        return self.survival_initial_spin.value(), self.survival_annual_spin.value()


# ------------------------------ 동적 입력 행 --------------------------------

class SpeciesInputRow(QFrame):
    """수종(콤보) + 직경(스피너) + 수량(스피너) + [삭제] 한 행. 인라인 편집 가능.

    `override_coeffs` 가 주어지면 해당 행은 사용자 정의 (a, b, CF) 로 계산된다.
    인라인 콤보(수종)를 변경하면 오버라이드는 자동으로 해제되고 기본값으로 복귀.
    """

    deleted = pyqtSignal(object)         # emits self

    def __init__(self, kind: str, species: str, diameter: float, quantity: int,
                 names: list, override_coeffs: Optional[OverrideCoeffs] = None,
                 records: Optional[dict] = None, var2: Optional[float] = None,
                 survival: Tuple[float, float] = (DEFAULT_SURVIVAL_PCT, DEFAULT_SURVIVAL_PCT),
                 parent=None):
        super().__init__(parent)
        self.kind = kind
        is_tree = kind == "tree"
        self._override_coeffs: Optional[OverrideCoeffs] = override_coeffs
        self._records = records or {}
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #FBFDFC; border: 1px solid #DCE1E6; border-radius: 8px; }"
        )

        diameter_label = "DBH(cm)" if is_tree else "RCD(cm)"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # 1행: 수종 콤보 + 삭제 버튼
        # (그래프 표시 토글은 우측 추정 그래프 옆의 체크박스 범례에서 항목별로 제어한다)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.combo = NoWheelComboBox()
        # 표시는 현재 언어의 수종명, 데이터는 계산에 쓰는 국명 키.
        for _name in names:
            self.combo.addItem(species_name(_name), _name)
        if species in names:
            self.combo.setCurrentIndex(names.index(species))
        # 반응형: 패널을 좁혀도 콤보가 줄어들어 삭제 버튼이 항상 보이도록.
        # (긴 수종명 때문에 최소 너비가 커져 행이 뷰포트를 넘기는 문제 방지)
        self.combo.setSizeAdjustPolicy(NoWheelComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(3)
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo.setToolTip(self.combo.currentText())
        self.combo.currentIndexChanged.connect(self._on_species_changed)
        top.addWidget(self.combo, 1)

        self.delete_button = QPushButton(tr("삭제"))
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setMinimumWidth(self.delete_button.sizeHint().width())
        self.delete_button.clicked.connect(self._on_delete)
        top.addWidget(self.delete_button)
        outer.addLayout(top)

        # 2행: 직경(설명변수)
        d_row = QHBoxLayout()
        d_row.setSpacing(4)
        self._d_label = QLabel(diameter_label)
        self._d_label.setMinimumWidth(px(60))
        d_row.addWidget(self._d_label)
        self.diameter_spin = NoWheelDoubleSpinBox()
        self.diameter_spin.setDecimals(2)
        self.diameter_spin.setSingleStep(0.1)
        self.diameter_spin.setRange(0.01, 100000.0)
        self.diameter_spin.setValue(max(0.01, float(diameter)))
        d_row.addWidget(self.diameter_spin, 1)
        outer.addLayout(d_row)

        # 2-1행: 두 번째 변수 (다변수 식 수종만 표시)
        v2_row = QHBoxLayout()
        v2_row.setSpacing(4)
        self._v2_label = QLabel(tr("두 번째 변수"))
        self._v2_label.setMinimumWidth(px(60))
        v2_row.addWidget(self._v2_label)
        self.var2_spin = NoWheelDoubleSpinBox()
        self.var2_spin.setDecimals(2)
        self.var2_spin.setSingleStep(0.5)
        self.var2_spin.setRange(0.0, 1000000.0)
        v2_row.addWidget(self.var2_spin, 1)
        outer.addLayout(v2_row)
        self._initial_var2 = var2

        # 3행: 수량
        q_row = QHBoxLayout()
        q_row.setSpacing(4)
        q_label = QLabel(tr("수량"))
        q_label.setMinimumWidth(px(60))
        q_row.addWidget(q_label)
        self.quantity_spin = NoWheelSpinBox()
        self.quantity_spin.setRange(0, 99999)
        self.quantity_spin.setValue(max(0, int(quantity)))
        q_row.addWidget(self.quantity_spin, 1)
        outer.addLayout(q_row)

        # 3-1행: 생존율 (현재 · 연간). 기본 100 % = 전량 생존.
        s_row = QHBoxLayout()
        s_row.setSpacing(4)
        s_label = QLabel(tr("생존율(%)"))
        s_label.setMinimumWidth(s_label.sizeHint().width())
        s_label.setToolTip(tr("현재 생존율(0년차 수량에 적용) · 연간 생존율(해마다 누적)"))
        s_row.addWidget(s_label)
        self.survival_initial_spin = _survival_spin(survival[0])
        self.survival_initial_spin.setToolTip(tr("현재 생존율 (%)"))
        self.survival_annual_spin = _survival_spin(survival[1])
        self.survival_annual_spin.setToolTip(tr("연간 생존율 (%/년)"))
        s_row.addWidget(self.survival_initial_spin, 1)
        s_row.addWidget(QLabel("·"))
        s_row.addWidget(self.survival_annual_spin, 1)
        outer.addLayout(s_row)

        # 4행: 오버라이드 표시 라벨 (수정된 a/b/CF 가 적용된 경우만 표시)
        self.override_label = QLabel()
        self.override_label.setStyleSheet(
            "color: #C0392B; font-style: italic; padding: 0 2px;"
        )
        self.override_label.setVisible(False)
        outer.addWidget(self.override_label)
        self._refresh_override_label()
        self._refresh_for_record(initial=True)

    def _on_delete(self) -> None:
        self.deleted.emit(self)

    def _on_species_changed(self, _index: int) -> None:
        # 좁아진 콤보에서 텍스트가 잘려도 전체 수종명을 툴팁으로 확인 가능
        self.combo.setToolTip(self.combo.currentText())
        # 수종을 인라인 변경하면 오버라이드 해제 (기본 계수로 복원)
        if self._override_coeffs is not None:
            self._override_coeffs = None
            self._refresh_override_label()
        self._refresh_for_record()

    def _current_record(self):
        return self._records.get(self.combo.currentData())

    def _refresh_for_record(self, initial: bool = False) -> None:
        """선택된 레코드에 맞춰 변수 라벨과 두 번째 변수 입력을 갱신한다."""
        rec = self._current_record()
        if rec is None:
            self._v2_label.setVisible(False)
            self.var2_spin.setVisible(False)
            return
        self._d_label.setText(rec.predictor_short + "(cm)"
                              if rec.predictor_short in ("DBH", "RCD")
                              else rec.var1_label)
        multivar = rec.is_multivar
        self._v2_label.setVisible(multivar)
        self.var2_spin.setVisible(multivar)
        if not multivar:
            return
        self._v2_label.setText(rec.var2_label)
        self.var2_spin.setRange(float(rec.var2_min), float(rec.var2_max))
        value = self._initial_var2 if (initial and self._initial_var2 is not None) \
            else float(rec.var2_default)
        self.var2_spin.setValue(float(value))

    def _refresh_override_label(self) -> None:
        if self._override_coeffs is None:
            self.override_label.setVisible(False)
            return
        a, b, cf = self._override_coeffs
        self.override_label.setText(
            tr("⚙ 사용자 식 적용: a={a:g}, b={b:g}, CF={cf:g}").format(a=a, b=b, cf=cf)
        )
        self.override_label.setVisible(True)

    def values(self) -> Tuple[str, float, int]:
        return (self.combo.currentData(), self.diameter_spin.value(),
                self.quantity_spin.value())

    def var2_value(self) -> Optional[float]:
        """다변수 식 수종의 두 번째 입력. 단일변수 수종은 None."""
        rec = self._current_record()
        if rec is None or not rec.is_multivar:
            return None
        return self.var2_spin.value()

    def override_coeffs(self) -> Optional[OverrideCoeffs]:
        return self._override_coeffs

    def survival_values(self) -> Tuple[float, float]:
        """(현재 생존율 %, 연간 생존율 %)."""
        return self.survival_initial_spin.value(), self.survival_annual_spin.value()


# ------------------------------ 메인 윈도우 ----------------------------------

class MainWindow(QMainWindow):

    def __init__(self, environment: str = DEFAULT_ENVIRONMENT,
                 region_name: str = "", area_w: int = 0, area_h: int = 0):
        super().__init__()
        self.setWindowTitle(
            tr("ForeCarb (Ver. {version} - Python)").format(version=__version__)
        )
        # 창 크기는 combined_window(통합 실행 진입점 main.py) 에서 설정.
        # centralWidget 만 사용되므로 이 창 자체의 크기는 영향 없음.

        # 지역 메타데이터(통합창에서 주입) — Excel 자동 네이밍·요약 시트에 사용.
        self.region_name = region_name
        self.area_w = area_w
        self.area_h = area_h

        # 대상지 유형 — 대상지별 식을 보유한 수종은 그 식을, 나머지는 기본식에
        # 대상지별 생장량 보정계수를 적용한 레코드를 사용한다.
        self.environment = environment

        # 통합 라이브러리 77종 — 설명변수가 DBH 인 레코드는 교목 탭, RCD 는 관목 탭.
        # 각 맵은 core(성장차 보유) 를 먼저, 확장 레코드를 뒤에 둔다.
        self._tree_records = lib.records_for_kind(lib.KIND_TREE, environment)
        self._shrub_records = lib.records_for_kind(lib.KIND_SHRUB, environment)
        self._tree_names = list(self._tree_records.keys())
        self._shrub_names = list(self._shrub_records.keys())

        self.tree_rows: List[SpeciesInputRow] = []
        self.shrub_rows: List[SpeciesInputRow] = []

        # 마지막 계산 결과 캐시 — Excel 저장·체크박스 범례 재렌더에 사용.
        #   _{kind}_entries : List[_Entry] (각 항목의 곡선 curve/label 포함, 계산 후 채워짐)
        #   _{kind}_years   : 연도축 배열 (0~30) 또는 None (아직 계산 전/유효 항목 없음)
        #   _{kind}_checks  : 항목별 표시 체크박스 (entries 와 같은 순서)
        #   _{kind}_total_cb: "총 탄소저장량" 표시 체크박스 또는 None (항목 2개 미만이면 None)
        self._tree_entries: List[_Entry] = []
        self._shrub_entries: List[_Entry] = []
        self._tree_years = None
        self._shrub_years = None
        self._tree_checks: List[QCheckBox] = []
        self._shrub_checks: List[QCheckBox] = []
        self._tree_total_cb: Optional[QCheckBox] = None
        self._shrub_total_cb: Optional[QCheckBox] = None
        self._carbon_price_per_tonne = 30000.0  # Assumed KRW per tonne of carbon (tC).
        self._displayed_total_carbon_kg = 0.0

        self._build_ui()

    # ----- UI 구성 -----

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        left = self._build_left_panel()
        right = self._build_right_panel()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        # 반응형: 입력 패널(좌)은 폭을 유지하고, 창을 키우면 그래프/결과(우)가 확장.
        splitter.setChildrenCollapsible(False)
        left.setMinimumWidth(px(300))
        left.setMaximumWidth(px(560))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([px(400), px(1000)])
        root.addWidget(splitter)

    def _build_left_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        tabs = QTabWidget()
        self._input_tabs = tabs
        layout.addWidget(tabs, 1)

        # 교목 탭
        tree_tab, self.tree_rows_layout = self._build_input_tab("tree", tr("+ 교목 추가"))
        tabs.addTab(tree_tab, tr("교목"))

        # 관목 탭
        shrub_tab, self.shrub_rows_layout = self._build_input_tab("shrub", tr("+ 관목 추가"))
        tabs.addTab(shrub_tab, tr("관목"))

        # 입력 데이터 엑셀(수종·직경·개체수·생존율)을 불러와 이 지역의 입력을 한 번에 채운다.
        self.preset_button = QPushButton(tr("데이터 불러오기"))
        self.preset_button.setCursor(Qt.PointingHandCursor)
        self.preset_button.setToolTip(tr("양식 엑셀의 수종 목록으로 이 지역의 교목·관목 입력을 채우고 계산합니다."))
        self.preset_button.clicked.connect(self.on_load_preset)
        layout.addWidget(self.preset_button)

        # 하단 보조 버튼 행: [전체 초기화] [Excel로 저장]
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.clear_button = QPushButton(tr("전체 초기화"))
        self.clear_button.setObjectName("deleteButton")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.on_clear)
        actions.addWidget(self.clear_button)

        self.save_button = QPushButton(tr("Excel로 저장"))
        self.save_button.setObjectName("accentButton")
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self.on_save_excel)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

        # 계산 버튼 (주 액션 — 스타일은 전역 테마의 #calcButton 규칙)
        self.calc_button = QPushButton(tr("계   산"))
        self.calc_button.setObjectName("calcButton")
        font = QFont()
        font.setPointSize(pt(HEADING_PT))
        font.setBold(True)
        self.calc_button.setFont(font)
        self.calc_button.setCursor(Qt.PointingHandCursor)
        self.calc_button.clicked.connect(self.on_calculate)
        layout.addWidget(self.calc_button)

        return wrap

    def _build_input_tab(self, kind: str, add_button_text: str) -> Tuple[QWidget, QVBoxLayout]:
        """수종 입력 탭 1개 구성. (탭위젯, 행 컨테이너 레이아웃) 반환."""
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # 상단 추가 버튼 (스타일은 전역 테마의 #accentButton 규칙)
        add_btn = QPushButton(add_button_text)
        add_btn.setObjectName("accentButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda _checked=False, k=kind: self._open_add_dialog(k))
        v.addWidget(add_btn)

        # 스크롤 가능한 행 컨테이너
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # 가로 스크롤 금지 → 행이 패널 폭에 맞춰 줄어들고 삭제 버튼이 잘리지 않음
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        rows_layout = QVBoxLayout(container)
        rows_layout.setContentsMargins(2, 2, 2, 2)
        rows_layout.setSpacing(6)
        rows_layout.addStretch(1)  # 행은 stretch 위로 추가됨

        scroll.setWidget(container)
        v.addWidget(scroll, 1)

        # 안내 라벨 (행이 비었을 때 보임)
        empty_hint = QLabel(tr("아직 추가된 항목이 없습니다.\n위의 추가 버튼을 눌러 입력하세요."))
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_hint.setStyleSheet("color: #888; padding: 12px;")
        # 안내는 스크롤 컨테이너 내부에 함께 둠
        rows_layout.insertWidget(0, empty_hint)
        if kind == "tree":
            self._tree_empty_hint = empty_hint
        else:
            self._shrub_empty_hint = empty_hint

        return tab, rows_layout

    def _open_add_dialog(self, kind: str) -> None:
        if kind == "tree":
            species_map, names = self._tree_records, self._tree_names
        else:
            species_map, names = self._shrub_records, self._shrub_names
        dlg = AddSpeciesDialog(kind, species_map, names, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        species, diameter, quantity, override, var2 = dlg.values()
        self._append_row(kind, species, diameter, quantity,
                         override_coeffs=override, var2=var2,
                         survival=dlg.survival_values())

    def _append_row(self, kind: str, species: str, diameter: float, quantity: int,
                    override_coeffs: Optional[OverrideCoeffs] = None,
                    var2: Optional[float] = None,
                    survival: Tuple[float, float] = (DEFAULT_SURVIVAL_PCT, DEFAULT_SURVIVAL_PCT),
                    ) -> None:
        names = self._tree_names if kind == "tree" else self._shrub_names
        records = self._tree_records if kind == "tree" else self._shrub_records
        row = SpeciesInputRow(kind, species, diameter, quantity, names,
                              override_coeffs=override_coeffs,
                              records=records, var2=var2, survival=survival)
        row.deleted.connect(self._on_row_deleted)

        if kind == "tree":
            self.tree_rows.append(row)
            layout = self.tree_rows_layout
            self._tree_empty_hint.setVisible(False)
        else:
            self.shrub_rows.append(row)
            layout = self.shrub_rows_layout
            self._shrub_empty_hint.setVisible(False)

        # stretch 바로 앞에 삽입 (rows_layout에 stretch가 마지막에 있음)
        insert_index = layout.count() - 1
        layout.insertWidget(insert_index, row)

    def _on_row_deleted(self, row: "SpeciesInputRow") -> None:
        if row in self.tree_rows:
            self.tree_rows.remove(row)
            if not self.tree_rows:
                self._tree_empty_hint.setVisible(True)
        elif row in self.shrub_rows:
            self.shrub_rows.remove(row)
            if not self.shrub_rows:
                self._shrub_empty_hint.setVisible(True)
        row.setParent(None)
        row.deleteLater()

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # 게이지 3개
        self.tree_gauge = LinearGauge(0, 2000, [0, 500, 1000, 1500, 2000])
        self.shrub_gauge = LinearGauge(0, 100, [0, 20, 40, 60, 80, 100])
        self.total_gauge = LinearGauge(0, 3000, [0, 500, 1000, 1500, 2000, 2500, 3000])

        self.tree_value_label = self._make_value_field("0.00")
        self.shrub_value_label = self._make_value_field("0.00")
        self.total_value_label = self._make_value_field("0.00")

        # 교목·관목·총 탄소저장량을 가로로 나란히: [제목] 아래 [바 | 값]. 세로 여백을 줄여
        # 주 디스플레이(그래프)에 높이를 더 준다.
        self._gauge_value_labels: dict = {}
        self._gauge_host = QWidget()
        gauges = QGridLayout(self._gauge_host)
        gauges.setContentsMargins(0, 0, 0, 0)
        gauges.setHorizontalSpacing(px(6))
        gauges.setVerticalSpacing(px(2))
        groups = (
            (tr("교목 탄소저장량 (kgC)"), self.tree_gauge, self.tree_value_label),
            (tr("관목 탄소저장량 (kgC)"), self.shrub_gauge, self.shrub_value_label),
            (tr("총 탄소저장량 (kgC)"), self.total_gauge, self.total_value_label),
        )
        for i, (title, gauge, value) in enumerate(groups):
            col = 3 * i
            self._add_gauge(gauges, col, title, gauge, value)
            if i < len(groups) - 1:
                gauges.setColumnMinimumWidth(col + 2, px(14))    # 그룹 사이 간격
        self.economic_value_button = QPushButton()
        self.economic_value_button.setFlat(True)
        self.economic_value_button.setCursor(Qt.PointingHandCursor)
        self.economic_value_button.setStyleSheet(
            "QPushButton { color: #246B43; border: none; padding: 0px 4px; }"
            "QPushButton:hover { color: #154B2D; text-decoration: underline; }"
        )
        self.economic_value_button.clicked.connect(self._edit_carbon_price)
        self._refresh_economic_value()
        # 막대 읽는 법: 옅은 막대 = 전량 생존, 안쪽 진한 막대 = 생존률 반영.
        legend = QLabel(tr("막대: 옅은 색 = 전량 생존 · 진한 색 = 생존률 반영"))
        legend.setStyleSheet("color: #6B7780;")
        legend.setToolTip(tr("생존률 반영: N(t) = 수량 × 현재 생존율 × 연간 생존율^t (수종별)"))
        last = 3 * (len(groups) - 1)
        gauges.addWidget(legend, 2, 0, 1, last + 1, Qt.AlignLeft | Qt.AlignVCenter)
        gauges.addWidget(self.economic_value_button, 2, last + 1, Qt.AlignRight | Qt.AlignVCenter)
        v.addWidget(self._gauge_host)

        # 그래프 영역: [교목 추정 / 교목 기여도 / 관목 추정 / 관목 기여도] sub tab.
        # 2-row 동시 배치는 그래프가 작아 보이므로, 각 그래프가 전체 영역을 차지하도록 탭 분리.
        self.tree_canvas = MatplotlibCanvas(width=7, height=4)
        self.tree_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.tree_pie_canvas = MatplotlibCanvas(width=5, height=4)
        self.tree_pie_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.shrub_canvas = MatplotlibCanvas(width=7, height=4)
        self.shrub_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.shrub_pie_canvas = MatplotlibCanvas(width=5, height=4)
        self.shrub_pie_canvas.show_message(tr("계산 버튼을 눌러주세요"))

        year_row = QHBoxLayout()
        year_row.setSpacing(px(8))
        year_row.addWidget(QLabel(tr("0년")))
        self.year_slider = QSlider(Qt.Horizontal)
        self.year_slider.setRange(0, 30)
        year_row.addWidget(self.year_slider, 1)
        year_row.addWidget(QLabel(tr("30년")))
        year_row.addSpacing(px(16))
        self.year_label = QLabel(tr("현재: 0년"))
        self.year_label.setStyleSheet("font-weight: bold; color: #246B43;")
        year_row.addWidget(self.year_label)
        v.addLayout(year_row)

        # 그래프 영역: 버튼 한 줄 [교목][관목][시각화] · 보기 [연도별][생존률 반영][직경별]
        # 아래에 꺾은선(왼쪽) + 기여도 원형(오른쪽). 탭 두 줄이 그래프 높이를 잡아먹지 않게 한다.
        stack = QStackedWidget()
        self._graph_pages: dict = {}
        for kind in ("tree", "shrub"):
            diameter_canvas = MatplotlibCanvas(width=7, height=4)
            diameter_pie = MatplotlibCanvas(width=5, height=4)
            survival_pie = MatplotlibCanvas(width=5, height=4)
            setattr(self, f"{kind}_diameter_canvas", diameter_canvas)
            setattr(self, f"{kind}_diameter_pie_canvas", diameter_pie)
            setattr(self, f"{kind}_survival_pie_canvas", survival_pie)
            for canvas in (diameter_canvas, diameter_pie, survival_pie):
                canvas.show_message(tr("계산 버튼을 눌러주세요"))
            for view, left, pie in (
                ("year", self._build_estimation_tab(kind), getattr(self, f"{kind}_pie_canvas")),
                ("survival", self._build_survival_tab(kind), survival_pie),
                ("diameter", self._build_estimation_tab(kind, BASIS_DIAMETER), diameter_pie),
            ):
                stack.addWidget(self._pair_page(left, pie))
                self._graph_pages[(kind, view)] = stack.count() - 1
        self.visualization_tab = VegetationVisualizationTab(
            snapshot_provider=self._build_visualization_snapshot,
            fingerprint_provider=self._visualization_fingerprint,
            year_slider=self.year_slider,
            parent=self,
        )
        stack.addWidget(self.visualization_tab)
        self._graph_pages[("vis", None)] = stack.count() - 1
        self._graph_tabs = stack
        self.year_slider.valueChanged.connect(self._on_visualization_year_changed)
        stack.currentChanged.connect(self._sync_graph_buttons)
        stack.currentChanged.connect(self._on_result_tab_changed)

        bar = QWidget()
        bar.setStyleSheet(_SEG_BUTTON_QSS)
        bar_row = QHBoxLayout(bar)
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(px(4))
        self._kind_group = QButtonGroup(bar)
        self._view_group = QButtonGroup(bar)
        self._kind_buttons: dict = {}
        self._view_buttons: dict = {}
        for key, text in (("tree", tr("교목")), ("shrub", tr("관목")), ("vis", tr("시각화"))):
            btn = self._seg_button(text)
            self._kind_group.addButton(btn)
            self._kind_buttons[key] = btn
            bar_row.addWidget(btn)
        bar_row.addSpacing(px(18))
        view_label = QLabel(tr("보기"))
        view_label.setStyleSheet("color: #6B7780;")
        bar_row.addWidget(view_label)
        for key, text in (("year", tr("연도별")), ("survival", tr("생존률 반영")),
                          ("diameter", tr("직경별"))):
            btn = self._seg_button(text)
            self._view_group.addButton(btn)
            self._view_buttons[key] = btn
            bar_row.addWidget(btn)
        bar_row.addStretch(1)
        for btn in list(self._kind_buttons.values()) + list(self._view_buttons.values()):
            btn.clicked.connect(self._select_graph_page)
        self._sync_graph_buttons(stack.currentIndex())

        graph_tabs = QWidget()          # 버튼 줄 + 페이지 (아래 스플리터의 위쪽 칸)
        graph_col = QVBoxLayout(graph_tabs)
        graph_col.setContentsMargins(0, 0, 0, 0)
        graph_col.setSpacing(px(2))
        graph_col.addWidget(bar)
        graph_col.addWidget(stack, 1)

        # 결과 테이블
        tables_widget = QWidget()
        tables = QHBoxLayout(tables_widget)
        tables.setContentsMargins(0, 0, 0, 0)
        self.tree_table = self._make_result_table()
        self.shrub_table = self._make_result_table()
        tables.addLayout(self._table_box(tr("교목 결과 (DBH·cm)"), self.tree_table, "tree"))
        tables.addLayout(self._table_box(tr("관목 결과 (RCD·cm)"), self.shrub_table, "shrub"))
        # 표는 헤더 + 4행이 보이는 높이만 확보한다(더 보려면 스플리터를 내리면 된다).
        # 여기를 크게 잡으면 글꼴이 커진 만큼 그래프 영역을 그대로 빼앗는다.
        # 주 디스플레이 비율을 지키려면 표가 줄어들 수 있어야 한다 — 최소는 머리글 + 1행
        # (나머지는 스크롤). 그마저 비율을 깨면 _MainDisplayGuard 가 표 영역을 접는다.
        for table in (self.tree_table, self.shrub_table):
            one_row = int(table.fontMetrics().height() * 1.6) + px(6)
            table.setMinimumHeight(table.horizontalHeader().sizeHint().height() + one_row
                                   + 2 * table.frameWidth() + px(4))

        # 그래프(sub tab) ↔ 결과 테이블 사이 높이를 세로 드래그로 조절.
        # 그래프·시각화가 주 화면이므로 최소 높이를 따로 확보하고 배분도 더 준다.
        graph_tabs.setMinimumHeight(px(360))
        body_splitter = QSplitter(Qt.Vertical)
        body_splitter.setChildrenCollapsible(False)
        self._tables_widget = tables_widget
        body_splitter.addWidget(graph_tabs)
        body_splitter.addWidget(tables_widget)
        body_splitter.setStretchFactor(0, 4)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setSizes([px(760), px(190)])
        body_splitter.setCollapsible(1, True)   # 공간이 모자라면 표만 접힌다(손잡이를 끌어 다시 펼침)
        v.addWidget(body_splitter, 1)
        self._body_splitter = body_splitter
        self._display_guard = _MainDisplayGuard(wrap, body_splitter)

        return wrap

    def _build_survival_tab(self, kind: str) -> QWidget:
        """수종별·합계의 전량 생존(실선) 대비 생존률 반영(점선) 연도별 비교."""
        wrap = QFrame()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(2, 2, 2, 2)
        canvas = MatplotlibCanvas(width=7, height=4)
        canvas.setToolTip(tr("실선: 전량 생존(기본 결과) · 점선: 생존률 반영  —  "
                             "N(t) = 수량 × 현재 생존율 × 연간 생존율^t"))
        canvas.show_message(tr("계산 버튼을 눌러주세요"))
        col.addWidget(canvas, 1)
        setattr(self, f"{kind}_survival_canvas", canvas)
        setattr(self, f"_{kind}_survival_marker", None)
        return wrap

    def _build_estimation_tab(self, kind: str, basis: str = BASIS_YEAR) -> QWidget:
        suffix = "" if basis == BASIS_YEAR else "_diameter"
        canvas = getattr(self, f"{kind}{suffix}_canvas")
        wrap = QFrame()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(2, 2, 2, 2)
        note = QLabel()
        note.setVisible(basis == BASIS_DIAMETER)
        note.setWordWrap(True)
        note.setStyleSheet("color: #7A5C00;")
        setattr(self, f"_{kind}{suffix}_basis_note", note)
        col.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(max(px(48), self.fontMetrics().height() + px(26)))
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        legend = QHBoxLayout(host)
        legend.addStretch(1)
        scroll.setWidget(host)
        col.addWidget(scroll)
        col.addWidget(canvas, 1)
        setattr(self, f"_{kind}{suffix}_legend_layout", legend)
        setattr(self, f"_{kind}{suffix}_checks", [])
        setattr(self, f"_{kind}{suffix}_total_cb", None)
        return wrap

    @staticmethod
    def _pair_page(left: QWidget, pie: QWidget) -> QWidget:
        """꺾은선(왼쪽 2/3) + 기여도 원형(오른쪽 1/3). 경계는 끌어서 조절."""
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(pie)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        split.setSizes([2000, 1000])
        return split

    def _seg_button(self, text: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("segButton")
        btn.setText(text)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        f = btn.font()
        f.setPointSize(pt(SMALL_PT))
        btn.setFont(f)
        return btn

    def _select_graph_page(self) -> None:
        """버튼 상태 → 페이지. 시각화를 고르면 '보기' 버튼은 쓰지 않는다."""
        kind = next(k for k, b in self._kind_buttons.items() if b.isChecked())
        if kind == "vis":
            self._graph_tabs.setCurrentIndex(self._graph_pages[("vis", None)])
            return
        view = next((k for k, b in self._view_buttons.items() if b.isChecked()), "year")
        self._graph_tabs.setCurrentIndex(self._graph_pages[(kind, view)])

    def _sync_graph_buttons(self, index: int) -> None:
        """페이지 → 버튼 상태 (코드에서 페이지를 바꿔도 버튼이 맞게)."""
        kind, view = next(key for key, i in self._graph_pages.items() if i == index)
        self._kind_buttons[kind].setChecked(True)
        for b in self._view_buttons.values():
            b.setEnabled(kind != "vis")
        if view is not None:
            self._view_buttons[view].setChecked(True)

    def _make_value_field(self, initial: str) -> QLabel:
        lbl = QLabel(initial)
        lbl.setMinimumWidth(px(130))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C4CCD3; "
            "border-radius: 6px; padding: 2px 8px; color: #246B43;"
        )
        font = QFont()
        font.setPointSize(pt(VALUE_PT))
        font.setBold(True)
        lbl.setFont(font)
        return lbl

    def _add_gauge(self, grid: QGridLayout, col: int, title: str,
                   gauge: LinearGauge, value_label: QLabel) -> None:
        """col 열에 [제목] (0행) 과 [바 | 값] (1행) 을 놓는다.

        바는 값 상자와 같은 높이의 밴드 안에서 세로 중앙에 그려지므로 둘의 중심선이
        맞고, 눈금값은 바 아래에 붙는다. 제목은 글자 높이만큼만 차지한다.
        """
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        band = max(px(30), value_label.sizeHint().height())
        value_label.setFixedHeight(band)
        gauge.set_band_height(band)
        self._gauge_value_labels[gauge] = value_label
        grid.addWidget(title_label, 0, col, 1, 2, Qt.AlignLeft | Qt.AlignBottom)
        grid.addWidget(gauge, 1, col, Qt.AlignTop)
        grid.addWidget(value_label, 1, col + 1, Qt.AlignTop)
        grid.setColumnStretch(col, 1)

    def _make_result_table(self) -> QTableWidget:
        # 수종(0열)이 flex — 남는 폭을 흡수해 패널 폭에 정확히 맞춤
        table = ResultTable(flex_col=0)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([tr("수종"), tr("직경"), tr("수량"), tr("탄소량(kgC)")])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)

        # 테이블 값/헤더 글꼴 — 본문보다 한 단계 큰 섹션 크기
        tfont = table.font()
        tfont.setPointSize(pt(HEADING_PT))
        table.setFont(tfont)

        # 숫자 열 기본 너비(드래그 조절 가능). 수종 열은 ResultTable 이 잔여 폭으로 채움.
        table.setColumnWidth(1, px(120))   # 직경
        table.setColumnWidth(2, px(100))   # 수량
        table.setColumnWidth(3, px(170))   # 탄소량
        # 행 높이는 글꼴 크기에 맞춰 자동
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        return table

    def _table_box(self, title: str, table: QTableWidget,
                   kind: Optional[str] = None) -> QVBoxLayout:
        box = QVBoxLayout()
        lbl = QLabel(title)
        # 결과 섹션 제목 — 강조색 + 본문보다 한 단계 큰 섹션 크기
        title_font = lbl.font()
        title_font.setPointSize(pt(HEADING_PT))
        title_font.setBold(True)
        lbl.setFont(title_font)
        lbl.setStyleSheet("color: #246B43;")
        box.addWidget(lbl)
        box.addWidget(table)

        # 핵심/확장 라이브러리 소계 — 총합에는 둘 다 포함되지만, 논문에 쓰이는
        # 핵심 22종 기준 수치를 따로 확인할 수 있도록 분리해 표시한다.
        if kind is not None:
            subtotal = QLabel()
            subtotal.setWordWrap(True)
            subtotal.setStyleSheet("color: #555;")
            subtotal.setMinimumHeight(subtotal.fontMetrics().lineSpacing() + px(4))
            box.addWidget(subtotal)
            if kind == "tree":
                self._tree_subtotal_label = subtotal
            else:
                self._shrub_subtotal_label = subtotal
        return box

    def _refresh_subtotals(self, kind: str, entries: List[_Entry]) -> None:
        """결과 테이블 아래에 핵심/확장 라이브러리 소계를 갱신한다."""
        label = (self._tree_subtotal_label if kind == "tree"
                 else self._shrub_subtotal_label)
        if not entries:
            label.setText("")
            return
        core = sum(e.carbon_kg for e in entries if e.record.is_core)
        ext = sum(e.carbon_kg for e in entries if e.record.is_extension)
        core_n = sum(1 for e in entries if e.record.is_core)
        ext_n = sum(1 for e in entries if e.record.is_extension)
        if not ext_n:
            text = tr("핵심 라이브러리 {n}건 · {c:,.2f} kgC").format(n=core_n, c=core)
        else:
            text = (tr("핵심 {cn}건 {cc:,.2f} kgC  +  확장 {en}건 {ec:,.2f} kgC  =  {t:,.2f} kgC")
                    .format(cn=core_n, cc=core, en=ext_n, ec=ext, t=core + ext))
        label.setText(text)

    # ----- 동작 -----

    def on_calculate(self) -> None:
        tree_entries, total_tree, tree_qty, w_tree = self._collect_entries("tree")
        shrub_entries, total_shrub, shrub_qty, w_shrub = self._collect_entries("shrub")

        # Diameter-domain errors are reported before the site-area check.  The
        # calculation boundary repeats the range guard so invalid rows cannot
        # bypass the entry dialog.
        warnings = w_tree + w_shrub
        if warnings:
            QMessageBox.warning(
                self, tr("입력값 오류 (해당 행 제외)"), "\n".join(warnings)
            )

        # Validate the combined footprint instead of applying independent or
        # absolute count thresholds.  The per-individual areas are configurable
        # data-entry safeguards, not species-specific planting recommendations.
        area_budget = planting_area_budget(
            area_w=self.area_w,
            area_h=self.area_h,
            tree_quantity=tree_qty,
            shrub_quantity=shrub_qty,
        )
        if area_budget is not None and area_budget.is_exceeded:
            QMessageBox.warning(
                self,
                tr("식재 면적 입력 한도"),
                tr(
                    "교목과 관목의 식재 면적 합계가 설정된 대상지 면적을 초과합니다.\n\n"
                    "대상지 면적: {site_area:,.2f} m²\n"
                    "교목: {tree_quantity:,}개체 × {tree_unit_area:.2f} m² = {tree_area:,.2f} m²\n"
                    "관목: {shrub_quantity:,}개체 × {shrub_unit_area:.2f} m² = {shrub_area:,.2f} m²\n"
                    "필요 식재 면적: {required_area:,.2f} m²\n"
                    "초과 면적: {excess_area:,.2f} m²\n\n"
                    "개체 수를 줄이거나 대상지 면적을 늘려 주세요. 계산은 수행되지 않았습니다.\n"
                    "개체당 기본 식재 면적은 입력 오류 방지를 위한 설정값이며 수종별 식재 권고가 아닙니다."
                ).format(
                    site_area=area_budget.site_area_m2,
                    tree_quantity=area_budget.tree_quantity,
                    tree_unit_area=TREE_PLANTING_AREA_M2_PER_INDIVIDUAL,
                    tree_area=area_budget.tree_area_m2,
                    shrub_quantity=area_budget.shrub_quantity,
                    shrub_unit_area=SHRUB_PLANTING_AREA_M2_PER_INDIVIDUAL,
                    shrub_area=area_budget.shrub_area_m2,
                    required_area=area_budget.required_area_m2,
                    excess_area=area_budget.excess_area_m2,
                ),
            )
            return

        # 다음 계산/저장에서 재사용할 수 있도록 캐시.
        self._tree_entries = tree_entries
        self._shrub_entries = shrub_entries

        # 결과 테이블 + 핵심/확장 소계
        self._populate_table(self.tree_table, [self._entry_to_row(e) for e in tree_entries])
        self._populate_table(self.shrub_table, [self._entry_to_row(e) for e in shrub_entries])
        self._refresh_subtotals("tree", tree_entries)
        self._refresh_subtotals("shrub", shrub_entries)

        # 게이지 + 숫자
        self.tree_gauge.setValue(total_tree)
        self.shrub_gauge.setValue(total_shrub)
        grand_total = total_tree + total_shrub
        self.total_gauge.setValue(grand_total)
        self.tree_value_label.setText(f"{round(total_tree, 2):,.2f}")
        self.shrub_value_label.setText(f"{round(total_shrub, 2):,.2f}")
        self.total_value_label.setText(f"{round(grand_total, 2):,.2f}")

        # 추정 그래프(체크박스 범례) + 기여도 파이
        self._build_curves("tree", tree_entries)
        self._build_curves("shrub", shrub_entries)
        self._build_legend("tree", tree_entries)
        self._build_legend("shrub", shrub_entries)
        self._build_legend("tree", tree_entries, BASIS_DIAMETER)
        self._build_legend("shrub", shrub_entries, BASIS_DIAMETER)
        self._render_projection("tree")
        self._render_projection("shrub")
        self._render_pie("tree", tree_entries)
        self._render_pie("shrub", shrub_entries)
        self._render_pie("tree", tree_entries, BASIS_DIAMETER)
        self._render_pie("shrub", shrub_entries, BASIS_DIAMETER)
        self._render_survival()
        self.visualization_tab.refresh_snapshot()
        self._on_visualization_year_changed(self.year_slider.value())

    def on_clear(self) -> None:
        """입력 행·결과 테이블·게이지·그래프를 모두 비운다 (누적/캐시 방지)."""
        # 입력 행 전부 제거 (교목·관목)
        for row in list(self.tree_rows) + list(self.shrub_rows):
            row.setParent(None)
            row.deleteLater()
        self.tree_rows.clear()
        self.shrub_rows.clear()
        self._tree_empty_hint.setVisible(True)
        self._shrub_empty_hint.setVisible(True)

        # 결과·캐시 비우기
        self.tree_table.setRowCount(0)
        self.shrub_table.setRowCount(0)
        self._tree_subtotal_label.setText("")
        self._shrub_subtotal_label.setText("")
        self._tree_entries = []
        self._shrub_entries = []
        self._tree_years = None
        self._shrub_years = None
        # 체크박스 범례 비우고 stretch 만 남김
        self._clear_layout(self._tree_legend_layout)
        self._tree_legend_layout.addStretch(1)
        self._clear_layout(self._shrub_legend_layout)
        self._shrub_legend_layout.addStretch(1)
        self._tree_checks = []
        self._shrub_checks = []
        self._tree_total_cb = None
        self._shrub_total_cb = None

        # 게이지·숫자 초기화
        self.tree_gauge.setValue(0)
        self.shrub_gauge.setValue(0)
        self.total_gauge.setValue(0)
        self.tree_value_label.setText("0.00")
        self.shrub_value_label.setText("0.00")
        self.total_value_label.setText("0.00")

        # 그래프·파이 초기 메시지로 복귀
        self.tree_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.shrub_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.tree_pie_canvas.show_message(tr("계산 버튼을 눌러주세요"))
        self.shrub_pie_canvas.show_message(tr("계산 버튼을 눌러주세요"))

        for kind in ("tree", "shrub"):
            self._build_legend(kind, [], BASIS_DIAMETER)
            getattr(self, f"_{kind}_basis_note").clear()
            getattr(self, f"_{kind}_diameter_basis_note").clear()
            getattr(self, f"{kind}_diameter_canvas").show_message(tr("계산 버튼을 눌러주세요"))
            getattr(self, f"{kind}_diameter_pie_canvas").show_message(tr("계산 버튼을 눌러주세요"))
            setattr(self, f"_{kind}_year_marker", None)
        for kind in ("tree", "shrub"):
            getattr(self, f"{kind}_survival_canvas").show_message(tr("계산 버튼을 눌러주세요"))
            setattr(self, f"_{kind}_survival_marker", None)
        for kind in ("tree", "shrub"):
            getattr(self, f"{kind}_survival_pie_canvas").show_message(tr("계산 버튼을 눌러주세요"))
        for g in (self.tree_gauge, self.shrub_gauge, self.total_gauge):
            g.setSecondaryValue(None)
            self._gauge_value_labels[g].setToolTip("")
        self.year_slider.setValue(0)
        self.visualization_tab.refresh_snapshot()
        self._on_visualization_year_changed(0)

    # ----- 데이터 불러오기 / 저장 -----

    def apply_preset_rows(self, rows) -> None:
        """데이터 행(preset_io.PresetRow)으로 교목·관목 입력을 바꾼다 (계산은 호출측)."""
        self.on_clear()
        for r in rows:
            self._append_row(r.kind, r.species, r.diameter, r.quantity, var2=r.var2,
                             survival=(r.survival_initial, r.survival_annual))
        self._input_tabs.setCurrentIndex(0 if any(r.kind == "tree" for r in rows) else 1)

    def preset_rows(self) -> list:
        """현재 입력 행 → preset_io.PresetRow 목록 ([데이터 저장] 용).

        사용자 정의 계수(a, b, CF)는 양식에 열이 없어 저장하지 않는다.
        """
        out = []
        for kind, rows in (("tree", self.tree_rows), ("shrub", self.shrub_rows)):
            for row in rows:
                species, diameter, quantity = row.values()
                s0, s1 = row.survival_values()
                out.append(preset_io.PresetRow(kind, species, diameter, quantity, s0, s1,
                                               row.var2_value()))
        return out

    def on_load_preset(self) -> None:
        parent = QApplication.activeWindow() or self
        path, _f = QFileDialog.getOpenFileName(
            parent, tr("데이터 불러오기"), "", tr("Excel 파일 (*.xlsx)"))
        if not path:
            return
        try:
            result = preset_io.read_preset(path, self._tree_names, self._shrub_names,
                                           RESTORATION_ENVIRONMENTS)
        except Exception as exc:  # noqa: BLE001 — 형식 오류를 사용자에게 안내
            QMessageBox.warning(parent, tr("데이터 불러오기 실패"), str(exc))
            return
        if not result.regions:
            QMessageBox.warning(parent, tr("데이터 불러오기 실패"),
                                "\n".join(result.errors[:20]) or tr("불러올 수종 입력이 없습니다."))
            return
        region = next((r for r in result.regions if r.name == self.region_name), None)
        if region is None and len(result.regions) == 1:
            region = result.regions[0]
        if region is None:
            name, ok = QInputDialog.getItem(
                parent, tr("지역 선택"), tr("이 탭에 불러올 지역을 선택하세요:"),
                [r.name for r in result.regions], 0, False)
            if not ok:
                return
            region = next(r for r in result.regions if r.name == name)
        if (self.tree_rows or self.shrub_rows) and QMessageBox.question(
                parent, tr("데이터 불러오기"),
                tr("현재 입력을 '{name}' 데이터({n}개 행)로 바꿀까요?").format(name=region.name, n=len(region.rows)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        self.apply_preset_rows(region.rows)
        self.on_calculate()
        notes = list(result.errors) + list(result.notes)
        if (region.width_m, region.height_m) != (self.area_w, self.area_h):
            notes.append(tr("불러온 데이터의 면적 {w} × {h} m 대신 이 탭의 면적 {aw} × {ah} m 를 사용했습니다.")
                         .format(w=region.width_m, h=region.height_m, aw=self.area_w, ah=self.area_h))
        if notes:
            QMessageBox.information(parent, tr("데이터 불러오기 — 확인 사항"), "\n".join(notes[:25]))

    @staticmethod
    def _entry_to_row(e: _Entry) -> CarbonRow:
        return CarbonRow(e.species, e.diameter, e.quantity, e.carbon_kg)

    def region_total_carbon(self) -> Tuple[float, float, float]:
        """현재 입력 기준 (교목 합, 관목 합, 총합) — 지역 종합 분석에서 사용.

        UI 부수효과·경고창 없이 합계만 계산한다(범위 위반 행은 제외).
        """
        _te, total_tree, _tq, _wt = self._collect_entries("tree")
        _se, total_shrub, _sq, _ws = self._collect_entries("shrub")
        return total_tree, total_shrub, total_tree + total_shrub

    def region_inventory_summary(self) -> dict:
        """종합 비교용 유효 개체 수, 식재 면적, 탄소량을 한 번에 반환한다."""
        _te, total_tree, tree_quantity, _wt = self._collect_entries("tree")
        _se, total_shrub, shrub_quantity, _ws = self._collect_entries("shrub")
        budget = planting_area_budget(
            area_w=self.area_w,
            area_h=self.area_h,
            tree_quantity=tree_quantity,
            shrub_quantity=shrub_quantity,
        )
        return {
            "tree": total_tree,
            "shrub": total_shrub,
            "total": total_tree + total_shrub,
            "tree_quantity": tree_quantity,
            "shrub_quantity": shrub_quantity,
            "tree_planting_area": budget.tree_area_m2 if budget else 0.0,
            "shrub_planting_area": budget.shrub_area_m2 if budget else 0.0,
            "required_planting_area": budget.required_area_m2 if budget else 0.0,
        }

    def _collect_entries(self, kind: str) -> Tuple[List[_Entry], float, int, List[str]]:
        """입력 행을 순회해 유효 행의 `_Entry` 리스트·합계·총 수량·경고 메시지를 반환.

        반환하는 `total_qty` 는 직경·계수 검증을 통과한 행의 전체 수량이며, 교목과 관목의
        합산 식재 면적을 대상지 면적과 비교하는 입력 보호 로직에 사용한다.

        범위 위반 행은 경고에 누적하고 결과(합계·테이블)에서 제외하지만, 호출측에서 경고를
        한 번에 표시하도록 여기서는 메시지박스를 띄우지 않는다.
        """
        if kind == "tree":
            input_rows = self.tree_rows
            records = self._tree_records
        else:
            input_rows = self.shrub_rows
            records = self._shrub_records
        unit = "cm"

        entries: List[_Entry] = []
        total = 0.0
        total_qty = 0
        warnings: List[str] = []
        for input_row in input_rows:
            species_key, diameter, quantity = input_row.values()
            if quantity <= 0:
                continue
            record = records.get(species_key)
            if record is None:
                continue

            # core 레코드는 행에 사용자 정의 (a, b, CF) 가 있으면 임시 SpeciesData 구성.
            species_data = record.species_data
            if species_data is not None:
                override = input_row.override_coeffs()
                if override is not None:
                    a, b, cf = override
                    species_data = replace(species_data, a=a, b=b, cf=cf)
                record = replace(record, species_data=species_data)

            var2 = input_row.var2_value()
            try:
                lib.check_range(record, diameter)
                carbon_kg = lib.carbon_total(record, diameter, quantity, var2)
                project_record(record, diameter, quantity, var2)
            except LibraryError as e:
                warnings.append(str(e))
                continue

            total_qty += quantity
            s0, s1 = input_row.survival_values()
            entries.append(_Entry(
                species=species_key, record=record, species_data=species_data,
                diameter=diameter, quantity=quantity, carbon_kg=carbon_kg,
                unit=("m" if record.predictor_short not in ("DBH", "RCD") else unit), var2=var2,
                survival_initial=s0, survival_annual=s1,
            ))
            total += carbon_kg

        return entries, total, total_qty, warnings

    # ----- 지역별 3D 시각화 adapter -----

    @staticmethod
    def _gauge_ticks(maximum: float) -> list[float]:
        """0 부터 maximum 이상까지 1·2·2.5·5 계열의 읽기 좋은 눈금 (5개 안팎 구간)."""
        maximum = max(1.0, float(maximum))
        magnitude = 10.0 ** math.floor(math.log10(maximum / 5))
        step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude * 5 >= maximum)
        count = math.ceil(maximum / step - 1e-9)
        return [step * i for i in range(count + 1)]

    def _set_top_carbon_display(self, tree: float, shrub: float, total: float,
                                *, visualization_scale: bool = False) -> None:
        if visualization_scale:
            snapshot = self.visualization_tab.snapshot
            if snapshot is not None:
                maxima = snapshot.carbon_timeline_maxima()
                for gauge, maximum in zip(
                    (self.tree_gauge, self.shrub_gauge, self.total_gauge), maxima,
                ):
                    ticks = self._gauge_ticks(max(1.0, maximum * 1.03))
                    gauge.setRange(0, ticks[-1], ticks)
        else:
            self.tree_gauge.setRange(0, 2000, [0, 500, 1000, 1500, 2000])
            self.shrub_gauge.setRange(0, 100, [0, 20, 40, 60, 80, 100])
            self.total_gauge.setRange(0, 3000, [0, 500, 1000, 1500, 2000, 2500, 3000])
        self.tree_gauge.setValue(tree)
        self.shrub_gauge.setValue(shrub)
        self.total_gauge.setValue(total)
        self.tree_value_label.setText(f"{tree:,.2f}")
        self.shrub_value_label.setText(f"{shrub:,.2f}")
        self.total_value_label.setText(f"{total:,.2f}")
        self._displayed_total_carbon_kg = total
        self._refresh_economic_value()

    def _refresh_economic_value(self) -> None:
        value = self._displayed_total_carbon_kg / 1000.0 * self._carbon_price_per_tonne
        self.economic_value_button.setText(tr("경제가치: {value:,.0f}원").format(value=value))
        self.economic_value_button.setToolTip(
            tr("단가: {price:,.2f}원/tC · 클릭하여 수정").format(price=self._carbon_price_per_tonne)
        )

    def _edit_carbon_price(self) -> None:
        price, accepted = QInputDialog.getDouble(
            self, tr("탄소 단가 설정"),
            tr("탄소 1톤(tC = 1,000 kgC)당 가격 (원)"),
            self._carbon_price_per_tonne, 0.0, 1_000_000_000.0, 2,
        )
        if accepted:
            self._carbon_price_per_tonne = price
            self._refresh_economic_value()

    def _year_zero_carbon_totals(self) -> tuple[float, float, float]:
        tree = sum(e.carbon_kg for e in self._tree_entries)
        shrub = sum(e.carbon_kg for e in self._shrub_entries)
        return tree, shrub, tree + shrub

    def _on_visualization_year_changed(self, year: int) -> None:
        self.year_label.setText(tr("현재: {year}년").format(year=year))
        totals = []
        for kind in ("tree", "shrub"):
            entries = getattr(self, f"_{kind}_entries")
            totals.append(sum(float(e.curve[year]) for e in entries if e.curve is not None))
            self._render_pie(kind, entries)
            self._render_pie(kind, entries, BASIS_SURVIVAL)
            marker = getattr(self, f"_{kind}_year_marker", None)
            if marker is not None:
                marker.set_xdata([year, year])
                getattr(self, f"{kind}_canvas").draw_idle()
        self._set_top_carbon_display(*totals, sum(totals), visualization_scale=True)
        self._refresh_survival_gauges(year)
        for kind in ("tree", "shrub"):
            marker = getattr(self, f"_{kind}_survival_marker", None)
            if marker is not None:
                marker.set_xdata([year, year])
                getattr(self, f"{kind}_survival_canvas").draw_idle()

    # ----- 생존률 반영 (전량 생존 결과와 별도 표시) -----

    def _survival_totals(self, year: int) -> dict:
        """연차 year 의 교목·관목 (전량 생존 탄소, 생존 반영 탄소, 식재 수량, 생존 개체 수)."""
        out = {}
        for kind in ("tree", "shrub"):
            entries = [e for e in getattr(self, f"_{kind}_entries") if e.surv_curve is not None]
            out[kind] = (
                sum(float(e.curve[year]) for e in entries),
                sum(float(e.surv_curve[year]) for e in entries),
                sum(e.quantity for e in entries),
                sum(e.quantity * float(e.surv_factor[year]) for e in entries),
            )
        return out

    def _all_entries(self) -> List[_Entry]:
        return list(self._tree_entries) + list(self._shrub_entries)

    def _refresh_survival_gauges(self, year: int) -> None:
        """게이지 막대 안쪽(진한 색)에 생존률 반영 값을 그린다. 수치는 값 상자 툴팁."""
        entries = self._all_entries()
        if not entries or all(e.surv_curve is None for e in entries):
            for g in (self.tree_gauge, self.shrub_gauge, self.total_gauge):
                g.setSecondaryValue(None)
                self._gauge_value_labels[g].setToolTip("")
            return
        t = self._survival_totals(year)
        values = {
            self.tree_gauge: (t["tree"][1], t["tree"][3], t["tree"][2]),
            self.shrub_gauge: (t["shrub"][1], t["shrub"][3], t["shrub"][2]),
            self.total_gauge: (t["tree"][1] + t["shrub"][1], t["tree"][3] + t["shrub"][3],
                               t["tree"][2] + t["shrub"][2]),
        }
        for gauge, (carbon, n, n0) in values.items():
            gauge.setSecondaryValue(carbon)
            self._gauge_value_labels[gauge].setToolTip(tr("생존률 반영 ({year}년): {v:,.2f} kgC · 생존 개체 {n:,.1f} / {n0:,}주")
                           .format(year=year, v=carbon, n=n, n0=n0))

    def _render_survival(self) -> None:
        """교목·관목 각각의 생존률 반영 탭: 수종별·합계 전량 생존(실선) / 생존률 반영(점선)."""
        palette = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD", "#8C564B", "#E377C2",
                   "#17BECF", "#BCBD22", "#7F7F7F"]
        for kind in ("tree", "shrub"):
            canvas = getattr(self, f"{kind}_survival_canvas")
            setattr(self, f"_{kind}_survival_marker", None)
            years = getattr(self, f"_{kind}_years")
            entries = [e for e in getattr(self, f"_{kind}_entries") if e.surv_curve is not None]
            if years is None or not entries:
                canvas.show_message(tr("{kind} 정보 없음").format(
                    kind=tr("교목") if kind == "tree" else tr("관목")))
                continue
            groups = [(species_name(e.species), palette[i % len(palette)], e.curve, e.surv_curve)
                      for i, e in enumerate(entries)]
            if len(entries) >= 2:
                groups.append((tr("합계"), "#C0392B", self._sum_carbon([e.curve for e in entries]),
                               self._sum_carbon([e.surv_curve for e in entries])))
            canvas.plot_survival_projection(years, groups)
            marker = canvas.ax.axvline(self.year_slider.value(), color="#C0392B", linestyle=":")
            setattr(self, f"_{kind}_survival_marker", marker)
            canvas.draw_idle()

    def _on_result_tab_changed(self, _index: int) -> None:
        if self._graph_tabs.currentWidget() is not self.visualization_tab:
            self.visualization_tab.pause()
        self._on_visualization_year_changed(self.year_slider.value())

    def _visualization_inputs(self) -> Tuple[tuple[VisualizationInputGroup, ...], tuple[str, ...]]:
        """Use the same accepted calculation inventory as graphs and contributions."""
        result = tuple(
            VisualizationInputGroup(
                species=e.species, kind=kind, diameter=e.diameter,
                quantity=e.quantity, diameter_unit="cm",
                species_data=e.species_data, record=e.record, var2=e.var2,
            )
            for kind in ("tree", "shrub")
            for e in getattr(self, f"_{kind}_entries")
        )
        return result, ()

    def _visualization_fingerprint(self) -> str:
        inputs, _warnings = self._visualization_inputs()
        return input_fingerprint(
            self.region_name, self.environment, self.area_w, self.area_h, inputs,
        )

    def _build_visualization_snapshot(self):
        inputs, warnings = self._visualization_inputs()
        return build_snapshot(
            region_name=self.region_name,
            environment=self.environment,
            area_w=self.area_w,
            area_h=self.area_h,
            inputs=inputs,
            warnings=warnings,
        )

    def _populate_table(self, table: QTableWidget, rows: List[CarbonRow]) -> None:
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row.as_table_row()):
                # 0열(수종)은 현재 언어의 표시명으로 (영문 모드: 학명)
                text = species_name(val) if j == 0 else str(val)
                item = QTableWidgetItem(text)
                # 수종(0열)은 좌측 정렬(긴 이름 가독), 숫자 열은 가운데 정렬
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignCenter))
                item.setToolTip(text)  # 잘려도 전체 값을 툴팁으로 확인
                table.setItem(i, j, item)
        # 패널 폭에 맞춰 열 너비 재조정 (수종 열이 잔여 폭 흡수)
        if isinstance(table, ResultTable):
            table.fit_columns()

    # ----- 그래프 (추정 곡선 · 기여도 파이) -----

    @staticmethod
    def _clear_layout(layout) -> None:
        """레이아웃의 모든 항목(위젯·스페이서)을 제거한다."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    @staticmethod
    def _sum_carbon(carbons: list):
        """탄소량 배열 리스트의 연도별 합 (입력이 비면 None). 새 배열을 만들어 반환."""
        total = None
        for c in carbons:
            total = c if total is None else total + c
        return total

    def _build_curves(self, kind: str, entries: List[_Entry]) -> None:
        """각 항목의 곡선과 라벨을 채운다.

        - 연도축(`curve`): 기존 생장량 또는 연 2% 가정으로 전체 항목을 30년 투영.
        - 직경축(`d_axis`/`d_curve`): 77종 전부. 유효범위가 있으면 그 구간을,
          없으면 입력값 주변 구간을 훑는다(`species_library.diameter_axis`).
        """
        years_ref = None
        for e in entries:
            years, _predictors, e.curve = project_record(
                e.record, e.diameter, e.quantity, e.var2,
            )
            years_ref = years
            # 생존률 반영: 탄소량은 개체 수에 비례하므로 전량 생존 곡선에 생존 비율을 곱한다.
            e.surv_factor = survival_factors(e.survival_initial, e.survival_annual, years)
            e.surv_curve = e.curve * e.surv_factor

            e.d_axis = lib.diameter_axis(e.record, e.diameter)
            e.d_curve = lib.carbon_by_diameter(e.record, e.d_axis, e.quantity, e.var2)

            e.label = tr("{species} ({d:g}{unit}·{n:g}주)").format(
                species=species_name(e.species), d=e.diameter, unit=e.unit, n=e.quantity)
        if kind == "tree":
            self._tree_years = years_ref
        else:
            self._shrub_years = years_ref

    def _build_legend(self, kind: str, entries: List[_Entry], basis: str = BASIS_YEAR) -> None:
        """추정 그래프 위에 항목별 표시 체크박스 + '총 탄소저장량' 체크박스를 동적으로 구성.

        각 체크박스를 켜고 끄면 즉시 해당 분류의 추정 그래프가 다시 그려진다 (요구사항 2).
        """
        suffix = "" if basis == BASIS_YEAR else "_diameter"
        layout = getattr(self, f"_{kind}{suffix}_legend_layout")
        self._clear_layout(layout)

        checks: List[QCheckBox] = []
        for e in entries:
            cb = QCheckBox(e.label)
            cb.setChecked(True)
            cb.setToolTip(tr("{label} 곡선 표시").format(label=e.label))
            cb.toggled.connect(lambda _c, k=kind: self._render_projection(k))
            layout.addWidget(cb)
            checks.append(cb)

        total_cb = None
        if len(entries) >= 2 and basis == BASIS_YEAR:
            total_cb = QCheckBox(tr("총 탄소저장량"))
            total_cb.setChecked(True)
            total_cb.setToolTip(tr("전체 항목 합계 곡선 표시"))
            total_cb.setStyleSheet("QCheckBox { color: #C0392B; font-weight: bold; }")
            total_cb.toggled.connect(lambda _c, k=kind: self._render_projection(k))
            layout.addWidget(total_cb)

        layout.addStretch(1)
        setattr(self, f"_{kind}{suffix}_checks", checks)
        setattr(self, f"_{kind}{suffix}_total_cb", total_cb)

    def _render_projection(self, kind: str) -> None:
        self._render_year_projection(kind)
        entries = getattr(self, f"_{kind}_entries")
        canvas = getattr(self, f"{kind}_diameter_canvas")
        note = getattr(self, f"_{kind}_diameter_basis_note")
        note.clear()
        self._render_diameter_projection(
            kind, canvas, entries, getattr(self, f"_{kind}_diameter_checks"),
            None, tr("교목") if kind == "tree" else tr("관목"), note,
        )

    def _render_year_projection(self, kind: str) -> None:
        """범례 체크박스 상태와 x축 기준에 따라 추정 그래프를 다시 그린다.

        - 체크된 각 항목 → 개별 곡선.
        - '총 탄소저장량' 체크 → 전체 항목 합계 곡선(개별 체크와 독립적으로 토글).
        - 아무것도 체크되지 않으면 안내 메시지를 표시.

        가정 생장률이 적용된 항목 수를 그래프 위에 표시한다.
        """
        if kind == "tree":
            canvas, entries = self.tree_canvas, self._tree_entries
            checks, total_cb, label_kr = self._tree_checks, self._tree_total_cb, tr("교목")
            years, note = self._tree_years, self._tree_basis_note
        else:
            canvas, entries = self.shrub_canvas, self._shrub_entries
            checks, total_cb, label_kr = self._shrub_checks, self._shrub_total_cb, tr("관목")
            years, note = self._shrub_years, self._shrub_basis_note

        setattr(self, f"_{kind}_year_marker", None)
        note.setText("")
        if not entries:
            canvas.show_message(tr("{kind} 정보 없음").format(kind=label_kr))
            return

        plottable = list(zip(entries, checks))
        if years is None or not plottable:
            canvas.show_message(tr("{kind} 정보 없음").format(kind=label_kr))
            return

        series: list = []
        for e, cb in plottable:
            if cb.isChecked():
                series.append((e.label, years, e.curve, False))

        # '총 탄소저장량' = 연도축에 그릴 수 있는 항목의 연도별 합.
        # 그릴 수 있는 항목이 1개뿐이면 개별 곡선과 같아지므로 합계는 생략한다.
        if total_cb is not None and total_cb.isChecked() and len(plottable) >= 2:
            summed = self._sum_carbon([e.curve for e, _cb in plottable])
            if summed is not None:
                series.append((tr("총 탄소저장량"), years, summed, True))

        if not series:
            canvas.show_message(
                tr("{kind}: 표시할 항목을 선택하세요 (그래프 위 체크박스)").format(kind=label_kr))
            return

        # 제목은 패널 상단 라벨로 표시하므로 축 제목은 끈다 (그래프 영역 확보).
        canvas.plot_multi_projection(
            series,
            tr("[{kind}] 향후 30년 탄소저장량 변동 추정").format(kind=label_kr),
            show_title=False,
        )
        marker = canvas.ax.axvline(self.year_slider.value(), color="#C0392B", linestyle="--")
        setattr(self, f"_{kind}_year_marker", marker)
        canvas.draw_idle()

    def _render_diameter_projection(self, kind: str, canvas, entries: List[_Entry],
                                    checks: List[QCheckBox], total_cb, label_kr: str,
                                    note: QLabel) -> None:
        """직경축 추정 그래프 — 77종 전부를 유효범위(또는 입력값 주변)에 걸쳐 표현.

        항목마다 정의역이 다르므로 개별 곡선만 그리고 합계 곡선은 제공하지 않는다
        (서로 다른 x 격자의 값을 더하면 의미가 없다).
        """
        series: list = []
        unbounded = 0
        for e, cb in zip(entries, checks):
            if not cb.isChecked():
                continue
            if e.d_axis is None or e.d_curve is None:
                continue
            if not e.record.has_range:
                unbounded += 1
            series.append((e.label, e.d_axis, e.d_curve, False))

        if not series:
            canvas.show_message(
                tr("{kind}: 표시할 항목을 선택하세요 (그래프 위 체크박스)").format(kind=label_kr))
            return

        notes = []
        if total_cb is not None and total_cb.isChecked():
            notes.append(tr("직경별에서는 합계 곡선을 제공하지 않습니다"))
        if unbounded:
            notes.append(tr("{n}개 항목은 유효범위 미제공 — 입력값 주변만 표시")
                         .format(n=unbounded))
        note.setText(" · ".join(notes))

        predictors = {e.record.predictor_short for e, cb in zip(entries, checks)
                      if cb.isChecked()}
        xlabel = (f"{predictors.pop()} (cm)" if len(predictors) == 1
                  else tr("설명변수"))
        canvas.plot_multi_projection(
            series,
            tr("[{kind}] 직경별 탄소저장량").format(kind=label_kr),
            xlabel=xlabel,
            show_title=False,
        )

    def _render_pie(self, kind: str, entries: List[_Entry], basis: str = BASIS_YEAR) -> None:
        """수종별 탄소저장량 기여도 파이차트를 그린다 (기여도 sub tab)."""
        canvas = getattr(self, f"{kind}{_PIE_SUFFIX[basis]}_pie_canvas")
        label_kr = tr("교목") if kind == "tree" else tr("관목")
        year = self.year_slider.value()
        if basis == BASIS_SURVIVAL:
            values = [float(e.surv_curve[year]) if e.surv_curve is not None else e.carbon_kg for e in entries]
        elif basis == BASIS_YEAR:
            values = [float(e.curve[year]) if e.curve is not None else e.carbon_kg for e in entries]
        else:
            values = [e.carbon_kg for e in entries]
        if not entries or sum(values) <= 0:
            canvas.show_message(tr("[{kind}]\n기여도 없음").format(kind=label_kr))
            return
        labels = [species_name(e.species) for e in entries]
        # 제목은 패널 상단 라벨로 표시하므로 차트 제목은 끈다.
        canvas.plot_pie(
            labels, values, title=tr("{kind} 수종별 기여도").format(kind=label_kr),
            top_n=5, label_fs=PLOT_ANNOTATION_PT, title_fs=PLOT_TITLE_PT, show_title=False,
        )

    # ----- Excel 저장 (요구사항 3) -----

    def on_save_excel(self) -> None:
        # 화면(마지막 계산)과 저장 내용을 일치시키기 위해, 아직 계산 전이면 먼저 계산한다.
        if self._tree_years is None and self._shrub_years is None:
            self.on_calculate()
        if not self._tree_entries and not self._shrub_entries:
            QMessageBox.information(
                self, tr("저장할 내용 없음"),
                tr("저장할 입력/결과가 없습니다. 먼저 항목을 추가한 뒤 [계 산]을 눌러 주세요."),
            )
            return

        # 통합 창에 임베드된 경우 MainWindow 자체는 표시되지 않으므로, 화면에 보이는
        # 최상위 창(통합 윈도우 또는 단독 창)을 부모로 삼아 다이얼로그가 올바른 위치에 뜨게 한다.
        parent = QApplication.activeWindow() or self
        # 지역별 자동 파일명: 지역명이 있으면 '탄소저장량_<지역명>.xlsx'.
        default_name = (
            tr("탄소저장량_{name}.xlsx").format(name=self._safe_filename(self.region_name))
            if self.region_name else tr("탄소저장량_결과.xlsx"))
        path, _filter = QFileDialog.getSaveFileName(
            parent, tr("Excel로 저장"), default_name, tr("Excel 파일 (*.xlsx)"),
        )
        if not path:
            return  # 사용자가 취소
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        payload = self._build_export_payload()

        try:
            export_carbon1_to_excel(path, payload)
        except PermissionError:
            QMessageBox.warning(
                self, tr("저장 실패"),
                tr("파일이 다른 프로그램(Excel 등)에서 열려 있어 저장할 수 없습니다.\n"
                "해당 파일을 닫고 다시 시도해 주세요."),
            )
            return
        except Exception as exc:  # noqa: BLE001 — 사용자에게 원인 안내
            QMessageBox.warning(
                self, tr("저장 실패"),
                tr("저장 중 오류가 발생했습니다:\n{error}").format(error=exc))
            return

        QMessageBox.information(
            self, tr("저장 완료"),
            tr("현재 화면(마지막 계산) 기준으로 저장되었습니다:\n{path}").format(path=path),
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        """파일명에 부적합한 문자를 _ 로 치환한 안전한 이름."""
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
        return cleaned or tr("지역")

    def _render_graph_images(self) -> list:
        """현재 4개 그래프(교목/관목 × 추정/기여도)를 PNG 바이트로 렌더 → Excel 임베드용."""
        specs = [
            (tr("교목 향후 30년 탄소저장량 변동 추정"), self.tree_canvas),
            (tr("교목 수종별 기여도"), self.tree_diameter_pie_canvas),
            (tr("관목 향후 30년 탄소저장량 변동 추정"), self.shrub_canvas),
            (tr("관목 수종별 기여도"), self.shrub_diameter_pie_canvas),
        ]
        images = []
        for title, canvas in specs:
            try:
                buf = io.BytesIO()
                # 그림은 constrained_layout 으로 이미 정돈됨(범례 포함). 그대로 PNG 저장.
                canvas.figure.savefig(buf, format="png", dpi=150)
                images.append({"title": title, "png": buf.getvalue()})
            except Exception:  # noqa: BLE001 — 이미지 실패해도 나머지 저장은 진행
                continue
        return images

    def build_export_payload(self):
        """공개 래퍼: 계산 결과가 없으면 None, 있으면 export payload dict를 반환."""
        if not self._tree_entries and not self._shrub_entries:
            return None
        return self._build_export_payload()

    def _build_export_payload(self) -> dict:
        total_tree = sum(e.carbon_kg for e in self._tree_entries)
        total_shrub = sum(e.carbon_kg for e in self._shrub_entries)
        return {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "grand_total": total_tree + total_shrub,
            "region": {
                "name": self.region_name,
                "environment": self.environment,
                "area_w": self.area_w,
                "area_h": self.area_h,
                "area": self.area_w * self.area_h,
            },
            "tree": self._payload_for("tree", total_tree),
            "shrub": self._payload_for("shrub", total_shrub),
            "images": self._render_graph_images(),
        }

    def _payload_for(self, kind: str, total: float) -> dict:
        if kind == "tree":
            entries, years, checks = self._tree_entries, self._tree_years, self._tree_checks
        else:
            entries, years, checks = self._shrub_entries, self._shrub_years, self._shrub_checks
        unit = "cm"

        rows = [
            {
                "species": e.species, "diameter": e.diameter, "quantity": e.quantity,
                "carbon": e.carbon_kg,
                "checked": (checks[i].isChecked() if i < len(checks) else True),
                # 확장 라이브러리 항목은 계수 대신 식 문자열을 보유하므로 a/b/CF 는 None.
                "a": (e.species_data.a if e.species_data else None),
                "b": (e.species_data.b if e.species_data else None),
                "cf": (e.species_data.cf if e.species_data else lib.CARBON_FACTOR),
                "dmin": e.record.range_min, "dmax": e.record.range_max,
                "equation": e.record.equation,
                "source": e.record.source,
                "growth_assumption": assumption_note(e.record),
                "survival_initial": e.survival_initial,
                "survival_annual": e.survival_annual,
            }
            for i, e in enumerate(entries)
        ]
        total_qty = sum(e.quantity for e in entries)

        projection = None
        # 기존 생장량과 가정 생장률을 포함한 전체 연도축 시계열.
        year_entries = [(i, e) for i, e in enumerate(entries) if e.curve is not None]
        if years is not None and year_entries:
            # 저장 파일에는 '총 탄소저장량'(연도축 항목 합)을 기록 — 2개 이상일 때만.
            grand = (self._sum_carbon([e.curve for _i, e in year_entries])
                     if len(year_entries) >= 2 else None)
            projection = {
                "years": [int(y) for y in years],
                "series": [
                    {
                        "label": e.label,
                        "checked": (checks[i].isChecked() if i < len(checks) else True),
                        "carbon": [float(x) for x in e.curve],
                    }
                    for i, e in year_entries
                ],
                "total": ([float(x) for x in grand] if grand is not None else None),
            }

        contribution = []
        if total > 0:
            agg: dict = {}
            for e in entries:
                # 집계 키는 내부 수종 키(국명) — 표시는 excel_export 가 담당한다.
                agg[e.species] = agg.get(e.species, 0.0) + e.carbon_kg
            for name, val in sorted(agg.items(), key=lambda kv: -kv[1]):
                contribution.append({
                    "species": name, "carbon": val, "percent": val / total * 100,
                })

        survival = None
        surv_entries = [e for e in entries if e.surv_curve is not None]
        if years is not None and surv_entries:
            survival = {
                "years": [int(y) for y in years],
                "all": [float(x) for x in self._sum_carbon([e.curve for e in surv_entries])],
                "with_survival": [float(x) for x in self._sum_carbon([e.surv_curve for e in surv_entries])],
                "individuals": float(sum(e.quantity for e in surv_entries)),
                "individuals_survival": [
                    float(x) for x in self._sum_carbon([e.quantity * e.surv_factor for e in surv_entries])],
            }

        return {
            "unit": unit, "total": total, "total_qty": total_qty,
            "rows": rows, "projection": projection, "contribution": contribution,
            "survival": survival,
        }
