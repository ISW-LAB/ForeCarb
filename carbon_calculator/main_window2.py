# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
Carbon2 - 탄소저장량 기여도 모듈 (Python 포팅).

원본 MATLAB: Carbon2_251013_1.mlapp
원본 동작 유지 사항:
- 식은 문자열로 저장하고 동적 평가 (calculate logic 원본 유지)
- 탄소전환계수 = 0.5 (하드코딩)
- 결과: 국내 테이블, 국외 테이블, 총합 게이지, 파이차트

UI:
- 좌측: [+ 국내, 국외 나무 추가] 단일 버튼 + 통합 행 리스트
- 팝업 다이얼로그: Carbon1 (AddSpeciesDialog) 와 동일 포맷 — 좌측 입력, 우측 상대생장식
- 동적 행 + 행별 [삭제] 버튼
"""
from __future__ import annotations

from typing import List, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .data2 import (
    CARBON_FACTOR, DOMESTIC_NAMES, DOMESTIC_SPECIES, FOREIGN_NAMES, FOREIGN_SPECIES,
    EquationSpecies, species_map, species_names,
)
from .equation_eval import EvaluationError, evaluate
from .i18n import species_name, tr
from .version import __version__
from .plotting import MatplotlibCanvas
from .ui_scale import apply_dialog_size, pt, px
from .typography import HEADING_PT, VALUE_PT
from .widgets import (
    LinearGauge, NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox,
    ResultTable, SearchableComboBox, align_gauge_row,
)


def origin_label(origin: str) -> str:
    """국내/국외 표시명 — 언어 설정 후에 평가되도록 함수로 둔다."""
    return tr("국내") if origin == "domestic" else tr("국외")


# ------------------------------ 결과 데이터 ----------------------------------

class _Result:
    """단일 입력의 계산 결과."""
    __slots__ = ("origin", "species", "diameter", "quantity", "carbon_kg")

    def __init__(self, origin: str, species: str, diameter: float,
                 quantity: int, carbon_kg: float):
        self.origin = origin
        self.species = species
        self.diameter = diameter
        self.quantity = quantity
        self.carbon_kg = carbon_kg

    def as_table_row(self) -> list:
        return [self.species, self.diameter, self.quantity, round(self.carbon_kg, 2)]


# ------------------------------ 입력 다이얼로그 ------------------------------

class AddTreeDialog(QDialog):
    """국내·국외 통합 수종 + DBH + 수량 입력 모달.

    레이아웃은 Carbon1 (AddSpeciesDialog) 와 동일한 좌·우 2패널 포맷:
      좌측: 카테고리(수종) · 변수(DBH) · 개수(수량)
      우측: (1) 상대생장식 [읽기 전용 — 식 문자열 그대로 표시]
            (2) 수종 정보 [구분(국내/국외), 유효 직경 범위]

    Carbon1 과 달리 Carbon2 의 식은 문자열로 저장되므로 (a, b, CF) 편집은 제공하지 않음.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("나무 추가"))
        self.setModal(True)
        apply_dialog_size(self, 840, 520)

        # 국내+국외 통합 항목: (표시명, (origin, species_key))
        self._items: List[Tuple[str, Tuple[str, str]]] = []
        for name in DOMESTIC_NAMES:
            self._items.append((tr("[국내] {name}").format(name=species_name(name)), ("domestic", name)))
        for name in FOREIGN_NAMES:
            self._items.append((tr("[국외] {name}").format(name=species_name(name)), ("foreign", name)))

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_left_panel(), 1)
        body.addWidget(self._build_right_panel(), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("추가 (Ctrl+Enter)"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("취소"))
        # 일반 Enter 로는 추가되지 않도록 기본 버튼 해제 (keyPressEvent 에서 Ctrl+Enter 만 허용)
        buttons.button(QDialogButtonBox.Ok).setAutoDefault(False)
        buttons.button(QDialogButtonBox.Ok).setDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

        self.search_combo.currentIndexChanged.connect(self._on_species_changed)
        self.search_combo.set_items(self._items)
        self._on_species_changed(0)

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

    def _build_left_panel(self) -> QWidget:
        group = QGroupBox(tr("입력"))
        form = QFormLayout(group)
        form.setSpacing(10)

        # 검색창 + 콤보 (키워드로 수종 검색)
        self.search_combo = SearchableComboBox(tr("🔍 수종 검색 (예: 소나무, 곰솔)"))
        form.addRow(tr("카테고리 (수종)"), self.search_combo)

        # 첫 번째 변수 (라벨은 수종에 따라 갱신)
        self.var1_label = QLabel(tr("변수 (DBH · cm)"))
        self.diameter_spin = NoWheelDoubleSpinBox()
        self.diameter_spin.setDecimals(2)
        self.diameter_spin.setSingleStep(1.0)
        self.diameter_spin.setRange(0.0, 9999.0)
        self.diameter_spin.setValue(6.0)
        form.addRow(self.var1_label, self.diameter_spin)

        # 두 번째 변수 (다변수 식일 때만 표시)
        self.var2_label = QLabel(tr("두 번째 변수"))
        self.var2_spin = NoWheelDoubleSpinBox()
        self.var2_spin.setDecimals(2)
        self.var2_spin.setRange(0.0, 100000.0)
        self.var2_spin.setValue(10.0)
        form.addRow(self.var2_label, self.var2_spin)

        self.quantity_spin = NoWheelSpinBox()
        self.quantity_spin.setRange(1, 99999)
        self.quantity_spin.setValue(1)
        form.addRow(tr("개수 (수량)"), self.quantity_spin)

        return group

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # (1) 상대생장식 (읽기 전용)
        eq_group = QGroupBox(tr("(1) 상대생장식 — 이 행의 계산에 적용되는 식"))
        eq_layout = QVBoxLayout(eq_group)
        eq_layout.setSpacing(8)

        self.formula_label = QLabel()
        self.formula_label.setStyleSheet(
            "background: #F0F8F0; padding: 8px; border: 1px solid #C8E0C8; "
            "border-radius: 3px; font-weight: bold;"
        )
        self.formula_label.setAlignment(Qt.AlignCenter)
        self.formula_label.setWordWrap(True)
        eq_layout.addWidget(self.formula_label)

        carbon_label = QLabel(tr("탄소량  C  =  Y  ×  {factor:g}  ×  N").format(factor=CARBON_FACTOR))
        carbon_label.setStyleSheet("color: #555; padding: 0 4px;")
        carbon_label.setAlignment(Qt.AlignCenter)
        eq_layout.addWidget(carbon_label)

        v.addWidget(eq_group)

        # (2) 수종 정보 (읽기 전용)
        info_group = QGroupBox(tr("(2) 수종 정보 (읽기 전용)"))
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(6)

        self.origin_value_label = QLabel("-")
        info_layout.addRow(tr("구분"), self.origin_value_label)

        self.range_value_label = QLabel("-")
        info_layout.addRow(tr("유효 입력 범위"), self.range_value_label)

        self.var2_info_label = QLabel("-")
        info_layout.addRow(tr("두 번째 변수"), self.var2_info_label)

        v.addWidget(info_group)
        v.addStretch(1)
        return wrap

    # ----- 이벤트 -----

    def _current_species(self):
        data = self.search_combo.current_data()
        if not data:
            return None, None, None
        origin, key = data
        return origin, key, species_map(origin).get(key)

    def _on_species_changed(self, _idx: int) -> None:
        origin, key, sp = self._current_species()
        if sp is None:
            return
        self.formula_label.setText(sp.equation)
        self.origin_value_label.setText(origin_label(origin))

        # 첫 번째 변수 라벨/범위
        self.var1_label.setText(tr("변수 ({label})").format(label=sp.var1_label))
        if sp.has_range:
            self.range_value_label.setText(
                f"{sp.diameter_min:g} ~ {sp.diameter_max:g}  ({sp.var1_label})"
            )
            self.diameter_spin.setRange(float(sp.diameter_min), float(sp.diameter_max))
            if self.diameter_spin.value() < sp.diameter_min:
                self.diameter_spin.setValue(float(sp.diameter_min))
        else:
            self.range_value_label.setText(tr("범위 검사 없음  ({label})").format(label=sp.var1_label))
            self.diameter_spin.setRange(0.0, 9999.0)

        # 두 번째 변수 (다변수 식일 때만 노출)
        if sp.is_multivar:
            self.var2_label.setText(sp.var2_label)
            self.var2_spin.setRange(float(sp.var2_min), float(sp.var2_max))
            self.var2_spin.setValue(float(sp.var2_default))
            self.var2_label.setVisible(True)
            self.var2_spin.setVisible(True)
            self.var2_info_label.setText(sp.var2_label)
        else:
            self.var2_label.setVisible(False)
            self.var2_spin.setVisible(False)
            self.var2_info_label.setText(tr("없음 (단일 변수 식)"))

    # ----- 결과 -----

    def values(self) -> Tuple[str, str, float, int, float | None]:
        origin, key, sp = self._current_species()
        h = self.var2_spin.value() if (sp and sp.is_multivar) else None
        return origin, key, self.diameter_spin.value(), self.quantity_spin.value(), h


# ------------------------------ 동적 입력 행 --------------------------------

class TreeInputRow(QFrame):
    """국내·국외 어느 쪽으로든 들어갈 수 있는 1개 입력 행. 인라인 편집 + 삭제.

    다변수 식 수종이면 두 번째 변수(H) 입력칸이 자동으로 표시된다.
    """

    deleted = pyqtSignal(object)

    def __init__(self, origin: str, species: str, diameter: float, quantity: int,
                 var2_value: float | None = None, parent=None):
        super().__init__(parent)
        self.origin = origin
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #FBFDFC; border: 1px solid #DCE1E6; border-radius: 8px; }"
        )

        names = species_names(origin)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # 1행: 라벨(구분) + 수종 + 삭제 버튼
        top = QHBoxLayout()
        top.setSpacing(4)
        origin_widget = QLabel(f"[{origin_label(origin)}]")
        origin_widget.setStyleSheet("color: #246B43; font-weight: bold;")
        origin_widget.setMinimumWidth(origin_widget.sizeHint().width())
        top.addWidget(origin_widget)
        self.combo = NoWheelComboBox()
        # 표시는 현재 언어의 수종명, 데이터는 계산에 쓰는 국명 키.
        for _name in names:
            self.combo.addItem(species_name(_name), _name)
        if species in names:
            self.combo.setCurrentIndex(names.index(species))
        # 반응형: 패널을 좁혀도 콤보가 줄어들어 삭제 버튼이 항상 보이도록.
        self.combo.setSizeAdjustPolicy(NoWheelComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(3)
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo.setToolTip(self.combo.currentText())
        top.addWidget(self.combo, 1)
        self.delete_button = QPushButton(tr("삭제"))
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setMinimumWidth(self.delete_button.sizeHint().width())
        self.delete_button.clicked.connect(lambda: self.deleted.emit(self))
        top.addWidget(self.delete_button)
        outer.addLayout(top)

        # 2행: 첫 번째 변수 (라벨은 수종에 따라 갱신)
        d_row = QHBoxLayout()
        d_row.setSpacing(4)
        self.d_lbl = QLabel("DBH(cm)")
        self.d_lbl.setMinimumWidth(px(70))
        d_row.addWidget(self.d_lbl)
        self.diameter_spin = NoWheelDoubleSpinBox()
        self.diameter_spin.setDecimals(2)
        self.diameter_spin.setSingleStep(1.0)
        self.diameter_spin.setRange(0.0, 9999.0)
        self.diameter_spin.setValue(max(0.0, float(diameter)))
        d_row.addWidget(self.diameter_spin, 1)
        outer.addLayout(d_row)

        # 3행: 두 번째 변수 (다변수 식일 때만 표시) — 컨테이너로 묶어 통째로 show/hide
        self.h_widget = QWidget()
        h_row = QHBoxLayout(self.h_widget)
        h_row.setContentsMargins(0, 0, 0, 0)
        h_row.setSpacing(4)
        self.h_lbl = QLabel("H")
        self.h_lbl.setMinimumWidth(px(70))
        self.h_lbl.setStyleSheet("color: #246B43;")
        h_row.addWidget(self.h_lbl)
        self.var2_spin = NoWheelDoubleSpinBox()
        self.var2_spin.setDecimals(2)
        self.var2_spin.setRange(0.0, 100000.0)
        h_row.addWidget(self.var2_spin, 1)
        outer.addWidget(self.h_widget)

        # 4행: 수량
        q_row = QHBoxLayout()
        q_row.setSpacing(4)
        q_lbl = QLabel(tr("수량"))
        q_lbl.setMinimumWidth(px(70))
        q_row.addWidget(q_lbl)
        self.quantity_spin = NoWheelSpinBox()
        self.quantity_spin.setRange(0, 99999)
        self.quantity_spin.setValue(max(0, int(quantity)))
        q_row.addWidget(self.quantity_spin, 1)
        outer.addLayout(q_row)

        # 수종에 맞춰 변수 라벨/범위/2번째변수 표시 갱신
        self.combo.currentTextChanged.connect(self._on_species_changed)
        self._refresh_for_species(species, initial_h=var2_value)

    def _on_species_changed(self, species: str) -> None:
        self.combo.setToolTip(species)
        self._refresh_for_species(species, initial_h=None)

    def _refresh_for_species(self, species: str, initial_h: float | None) -> None:
        sp = species_map(self.origin).get(species)
        if sp is None:
            return
        self.d_lbl.setText(sp.var1_label)
        if sp.has_range:
            self.diameter_spin.setRange(float(sp.diameter_min), float(sp.diameter_max))
        else:
            self.diameter_spin.setRange(0.0, 9999.0)

        if sp.is_multivar:
            self.h_lbl.setText(sp.var2_label)
            self.var2_spin.setRange(float(sp.var2_min), float(sp.var2_max))
            self.var2_spin.setValue(float(initial_h) if initial_h is not None
                                    else float(sp.var2_default))
            self.h_widget.setVisible(True)
        else:
            self.h_widget.setVisible(False)

    def _is_multivar(self) -> bool:
        sp = species_map(self.origin).get(self.combo.currentData())
        return bool(sp and sp.is_multivar)

    def values(self) -> Tuple[str, str, float, int, float | None]:
        h = self.var2_spin.value() if self._is_multivar() else None
        return (self.origin, self.combo.currentData(),
                self.diameter_spin.value(), self.quantity_spin.value(), h)


# ------------------------------ 메인 윈도우 ----------------------------------

class Carbon2MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            tr("ForeCarb (Ver. {version} - 탄소저장량 기여도)")
            .format(version=__version__)
        )
        # 창 크기는 combined_window(통합 실행 진입점 main.py) 에서 설정.
        # centralWidget 만 사용되므로 이 창 자체의 크기는 영향 없음.

        # 국내·국외 통합 단일 행 리스트.
        self.tree_rows: List[TreeInputRow] = []

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
        # 반응형: 입력 패널(좌)은 폭 유지, 창 확장 시 차트/결과(우)가 늘어남.
        splitter.setChildrenCollapsible(False)
        left.setMinimumWidth(px(300))
        left.setMaximumWidth(px(560))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([px(340), px(1000)])
        root.addWidget(splitter)

    def _build_left_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 통합 추가 버튼 (스타일은 전역 테마의 #accentButton 규칙)
        add_btn = QPushButton(tr("+ 국내, 국외 나무 추가"))
        add_btn.setObjectName("accentButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._open_add_dialog)
        layout.addWidget(add_btn)

        # 스크롤 영역 — 추가된 행 누적
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # 가로 스크롤 금지 → 행이 패널 폭에 맞춰 줄어들고 삭제 버튼이 잘리지 않음
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        self.rows_layout = QVBoxLayout(container)
        self.rows_layout.setContentsMargins(2, 2, 2, 2)
        self.rows_layout.setSpacing(6)
        self.rows_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self._empty_hint = QLabel(
            tr("아직 추가된 항목이 없습니다.\n위의 [+ 국내, 국외 나무 추가] 버튼을 눌러 입력하세요.")
        )
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setStyleSheet("color: #888; padding: 12px;")
        self.rows_layout.insertWidget(0, self._empty_hint)

        # 초기화 버튼 (입력·결과 전체 비우기)
        self.clear_button = QPushButton(tr("전체 초기화"))
        self.clear_button.setObjectName("deleteButton")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.on_clear)
        layout.addWidget(self.clear_button)

        # 계산 버튼 (주 액션 — 스타일은 전역 테마의 #calcButton 규칙)
        self.calc_button = QPushButton(tr("계   산"))
        self.calc_button.setObjectName("calcButton")
        font = QFont(); font.setPointSize(pt(HEADING_PT)); font.setBold(True)
        self.calc_button.setFont(font)
        self.calc_button.setCursor(Qt.PointingHandCursor)
        self.calc_button.clicked.connect(self.on_calculate)
        layout.addWidget(self.calc_button)

        return wrap

    def _open_add_dialog(self) -> None:
        dlg = AddTreeDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        origin, species, diameter, quantity, var2 = dlg.values()
        self._append_row(origin, species, diameter, quantity, var2)

    def _append_row(self, origin: str, species: str, diameter: float, quantity: int,
                    var2: float | None = None) -> None:
        row = TreeInputRow(origin, species, diameter, quantity, var2_value=var2)
        row.deleted.connect(self._on_row_deleted)
        self.tree_rows.append(row)
        self._empty_hint.setVisible(False)

        insert_index = self.rows_layout.count() - 1  # stretch 직전
        self.rows_layout.insertWidget(insert_index, row)

    def _on_row_deleted(self, row: "TreeInputRow") -> None:
        if row in self.tree_rows:
            self.tree_rows.remove(row)
            if not self.tree_rows:
                self._empty_hint.setVisible(True)
        row.setParent(None)
        row.deleteLater()

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # 총합 게이지 + 숫자
        self.total_gauge = LinearGauge(0, 2000, [0, 500, 1000, 1500, 2000])
        self.total_value_label = QLabel("0.00")
        self.total_value_label.setMinimumWidth(px(185))
        self.total_value_label.setAlignment(Qt.AlignCenter)
        self.total_value_label.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C4CCD3; "
            "border-radius: 6px; padding: 6px; color: #246B43;"
        )
        big = QFont(); big.setPointSize(pt(VALUE_PT)); big.setBold(True)
        self.total_value_label.setFont(big)

        # 제목·바·값을 같은 높이의 상단 밴드에 넣고 상단 정렬 → 세로 중심선 일치.
        gauge_row = QHBoxLayout()
        gauge_row.setSpacing(px(10))
        title = QLabel(tr("총 탄소저장량 (kgC)"))
        title.setMinimumWidth(px(185))
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title.setStyleSheet("font-weight: bold;")
        align_gauge_row(title, self.total_gauge, self.total_value_label)
        gauge_row.addWidget(title, 0, Qt.AlignTop)
        gauge_row.addWidget(self.total_gauge, 1, Qt.AlignTop)
        gauge_row.addWidget(self.total_value_label, 0, Qt.AlignTop)
        v.addLayout(gauge_row)

        # 파이 차트
        self.pie_canvas = MatplotlibCanvas(width=7, height=4)
        self.pie_canvas.show_message(tr("[수종별 탄소저장량 기여도] - 계산 버튼을 눌러주세요"))
        pie_frame = QFrame()
        pie_frame.setFrameShape(QFrame.StyledPanel)
        pf = QVBoxLayout(pie_frame); pf.setContentsMargins(2, 2, 2, 2)
        pf.addWidget(self.pie_canvas)
        # 그래프가 주 화면 — 표가 글꼴 크기만큼 커져도 그림 영역을 지키게 한다.
        pie_frame.setMinimumHeight(px(320))
        v.addWidget(pie_frame, 4)

        # 결과 테이블 2개
        tables = QHBoxLayout()
        self.domestic_table = self._make_result_table()
        self.foreign_table = self._make_result_table()
        tables.addLayout(self._table_box(tr("국내 결과"), self.domestic_table))
        tables.addLayout(self._table_box(tr("국외 결과"), self.foreign_table))
        v.addLayout(tables, 2)

        return wrap

    def _make_result_table(self) -> QTableWidget:
        # 수종(0열)이 flex — 남는 폭을 흡수해 패널 폭에 정확히 맞춤
        table = ResultTable(flex_col=0)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([tr("수종"), tr("변수값"), tr("수량"), tr("탄소량(kgC)")])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)

        # 테이블 값/헤더 글꼴 — 본문보다 한 단계 큰 섹션 크기
        tfont = table.font()
        tfont.setPointSize(pt(HEADING_PT))
        table.setFont(tfont)

        # 숫자 열 기본 너비(드래그 조절 가능). 수종 열은 ResultTable 이 잔여 폭으로 채움.
        table.setColumnWidth(1, px(125))   # DBH
        table.setColumnWidth(2, px(100))   # 수량
        table.setColumnWidth(3, px(170))   # 탄소량
        # 행 높이는 글꼴 크기에 맞춰 자동
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        return table

    def _table_box(self, title: str, table: QTableWidget) -> QVBoxLayout:
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
        return box

    # ----- 계산 -----

    def on_calculate(self) -> None:
        all_results, warnings = self._compute_rows(self.tree_rows)

        if warnings:
            QMessageBox.warning(self, tr("입력값 오류"), "\n".join(warnings))

        domestic_results = [r for r in all_results if r.origin == "domestic"]
        foreign_results = [r for r in all_results if r.origin == "foreign"]
        self._populate_table(self.domestic_table, domestic_results)
        self._populate_table(self.foreign_table, foreign_results)

        total = sum(r.carbon_kg for r in all_results)
        self.total_gauge.setValue(total)
        self.total_value_label.setText(f"{round(total, 2):,.2f}")

        # 파이 차트
        if all_results:
            labels = [species_name(r.species) for r in all_results]
            values = [r.carbon_kg for r in all_results]
            self.pie_canvas.plot_pie(labels, values, title=tr("수종별 탄소저장량 기여도"))
        else:
            self.pie_canvas.show_message(tr("표시할 데이터가 없습니다."))

    def on_clear(self) -> None:
        """입력 행·결과 테이블·게이지·차트를 모두 비운다 (누적/캐시 방지)."""
        # 입력 행 전부 제거
        for row in list(self.tree_rows):
            row.setParent(None)
            row.deleteLater()
        self.tree_rows.clear()
        self._empty_hint.setVisible(True)

        # 결과 테이블 비우기
        self.domestic_table.setRowCount(0)
        self.foreign_table.setRowCount(0)

        # 게이지·숫자·차트 초기화
        self.total_gauge.setValue(0)
        self.total_value_label.setText("0.00")
        self.pie_canvas.show_message(tr("[수종별 탄소저장량 기여도] - 계산 버튼을 눌러주세요"))

    def _compute_rows(self, rows: List[TreeInputRow]) -> Tuple[List[_Result], List[str]]:
        results: List[_Result] = []
        warnings: List[str] = []
        for row in rows:
            origin, species, dbh, qty, h = row.values()
            if qty <= 0:
                continue
            sp_map = species_map(origin)
            sp_data: EquationSpecies | None = sp_map.get(species)
            if sp_data is None:
                continue

            # 범위 검사 (둘 다 None 이 아닌 경우만)
            if sp_data.has_range:
                if dbh < sp_data.diameter_min or dbh > sp_data.diameter_max:
                    warnings.append(
                        tr("{species} 의 유효 {label} 범위는 {vmin:g} ~ {vmax:g} 입니다. (입력: {value:g})")
                        .format(species=species_name(species),
                                label=sp_data.var1_label,
                                vmin=sp_data.diameter_min,
                                vmax=sp_data.diameter_max, value=dbh)
                    )
                    continue

            try:
                biomass = evaluate(sp_data.equation, dbh, h)
            except EvaluationError as e:
                warnings.append(str(e))
                continue
            # 원본 MATLAB: nan/inf 발생 시 계산 결과가 표 행으로 들어가지 않도록 방어
            if not _is_finite(biomass) or biomass < 0:
                warnings.append(tr("{species} 의 식 평가값이 유효하지 않음 (Y={value})")
                                .format(species=species_name(species), value=biomass))
                continue

            carbon = biomass * CARBON_FACTOR * qty
            results.append(_Result(origin, species, dbh, qty, carbon))
        return results, warnings

    def _populate_table(self, table: QTableWidget, rows: List[_Result]) -> None:
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, val in enumerate(r.as_table_row()):
                text = str(val)
                item = QTableWidgetItem(text)
                # 수종(0열)은 좌측 정렬(긴 이름 가독), 숫자 열은 가운데 정렬
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignCenter))
                item.setToolTip(text)  # 잘려도 전체 값을 툴팁으로 확인
                table.setItem(i, j, item)
        # 패널 폭에 맞춰 열 너비 재조정 (수종 열이 잔여 폭 흡수)
        if isinstance(table, ResultTable):
            table.fit_columns()


def _is_finite(x: float) -> bool:
    import math
    try:
        return math.isfinite(x)
    except TypeError:
        return False
