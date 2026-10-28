# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
MATLAB uigauge('linear') 와 유사한 수평 게이지 위젯.
"""
from __future__ import annotations

import difflib

from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFontMetrics, QPen, QFont
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)

from .i18n import tr
from .ui_scale import pt, px
from .typography import SMALL_PT


# 마우스 휠로 값이 의도치 않게 바뀌는 것을 방지하기 위한 입력 위젯들.
# 스크롤 영역 안의 행에서 스크롤할 때 카테고리/직경/수량 값이 변경되는 문제를 해결.
class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


def rank_items(query: str, items: list[tuple[str, object]]) -> list[tuple[str, object]]:
    """
    검색어로 (표시텍스트, 데이터) 목록을 유사도 순으로 정렬·필터.

    - 부분일치(공백 무시) 항목을 최우선 (등장 위치가 빠를수록 상위).
    - 부분일치가 없으면 difflib 유사도 상위 항목을 제시.
    - 어느 것도 없으면(완전 무관) 전체를 유사도순으로 반환해 콤보가 비지 않게 함.
    """
    q = "".join(query.split()).lower()
    if not q:
        return list(items)

    subs: list[tuple[int, int, str, object]] = []
    fuzzy: list[tuple[float, str, object]] = []
    for text, data in items:
        t = "".join(text.split()).lower()
        pos = t.find(q)
        if pos >= 0:
            subs.append((pos, len(t), text, data))
        else:
            ratio = difflib.SequenceMatcher(None, q, t).ratio()
            fuzzy.append((ratio, text, data))

    if subs:
        subs.sort(key=lambda e: (e[0], e[1]))
        return [(text, data) for _, _, text, data in subs]

    fuzzy.sort(key=lambda e: -e[0])
    close = [(text, data) for ratio, text, data in fuzzy if ratio >= 0.34]
    return close if close else [(text, data) for _, text, data in fuzzy]


class SearchableComboBox(QWidget):
    """
    검색창(QLineEdit) + 콤보박스(QComboBox) + 실시간 추천 리스트 결합 위젯.

    - 검색창에 키워드를 입력할 때마다 유사도 높은 순으로 콤보가 필터링되고,
      **검색창 바로 아래의 추천 리스트**에 후보가 실시간으로 표시된다(유사도 1위가 맨 위).
    - 추천 항목을 클릭하거나 Enter(검색창) 를 누르면 그 수종이 선택된다.
    - 각 항목은 (표시텍스트, 임의 데이터) 형태로 보관하며 ``current_data()`` 로
      선택 항목의 데이터를 얻는다.
    """

    currentIndexChanged = pyqtSignal(int)

    SUGGEST_LIMIT = 10   # 추천 리스트 최대 표시 개수

    def __init__(self, placeholder: str | None = None, parent=None):
        super().__init__(parent)
        if placeholder is None:
            placeholder = tr("🔍 검색 (예: 소나무)")
        self._all: list[tuple[str, object]] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(px(4))

        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        v.addWidget(self.search)

        self.combo = NoWheelComboBox()
        v.addWidget(self.combo)

        # 실시간 추천 리스트 (검색 중에만 표시)
        self.suggestions = QListWidget()
        self.suggestions.setVisible(False)
        self.suggestions.setMaximumHeight(px(210))
        self.suggestions.setStyleSheet(
            "QListWidget { border: 1px solid #C4CCD3; border-radius: 6px; background: #FFFFFF; }"
            "QListWidget::item { padding: 4px 6px; }"
            "QListWidget::item:selected { background: #E8F4EC; color: #232A2E; }"
        )
        v.addWidget(self.suggestions)

        self.search.textChanged.connect(self._on_search)
        self.search.returnPressed.connect(self._choose_top_suggestion)
        self.suggestions.itemClicked.connect(self._on_suggestion_chosen)
        self.combo.currentIndexChanged.connect(self.currentIndexChanged)

    def set_items(self, items: list[tuple[str, object]]) -> None:
        self._all = list(items)
        self._apply("")

    def _apply(self, query: str) -> None:
        ranked = rank_items(query, self._all)

        # 콤보 갱신 (현재 선택 = 유사도 1위)
        self.combo.blockSignals(True)
        self.combo.clear()
        for text, data in ranked:
            self.combo.addItem(text, data)
        self.combo.blockSignals(False)
        if self.combo.count() > 0:
            self.combo.setCurrentIndex(0)

        # 추천 리스트 갱신 (검색어가 있을 때만 표시)
        self._update_suggestions(query, ranked)

        # 목록이 바뀌었으니 현재 선택을 알림 (다이얼로그 우측 정보 갱신용)
        self.currentIndexChanged.emit(self.combo.currentIndex())

    def _update_suggestions(self, query: str, ranked: list[tuple[str, object]]) -> None:
        self.suggestions.clear()
        if not query.strip() or not ranked:
            self.suggestions.setVisible(False)
            return
        for rank, (text, data) in enumerate(ranked[: self.SUGGEST_LIMIT], 1):
            item = QListWidgetItem(f"{rank}. {text}")
            item.setData(Qt.UserRole, data)
            item.setData(Qt.UserRole + 1, text)   # 원본 표시텍스트(번호 제외)
            self.suggestions.addItem(item)
        self.suggestions.setCurrentRow(0)
        self.suggestions.setVisible(True)

    def _on_search(self, text: str) -> None:
        self._apply(text)

    def _select_data(self, data, display_text: str) -> None:
        idx = self.combo.findData(data)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        # 선택한 수종명을 검색창에 반영 (재필터 방지 위해 시그널 차단)
        self.search.blockSignals(True)
        self.search.setText(display_text)
        self.search.blockSignals(False)
        self.suggestions.setVisible(False)

    def _on_suggestion_chosen(self, item: QListWidgetItem) -> None:
        self._select_data(item.data(Qt.UserRole), item.data(Qt.UserRole + 1))

    def _choose_top_suggestion(self) -> None:
        if self.suggestions.isVisible() and self.suggestions.count() > 0:
            row = max(0, self.suggestions.currentRow())
            self._on_suggestion_chosen(self.suggestions.item(row))

    # ----- 조회 API -----
    def current_data(self):
        return self.combo.currentData()

    def currentText(self) -> str:
        return self.combo.currentText()

    def count(self) -> int:
        return self.combo.count()


class ResultTable(QTableWidget):
    """
    결과 테이블 — 패널 폭에 항상 정확히 맞고, 각 열 너비를 드래그로 조절 가능.

    동작
    ----
    - 모든 열 ``Interactive`` → 사용자가 열 경계를 드래그해 너비 조절.
    - ``flex_col``(기본 0번=수종)이 남는 폭을 흡수 → 모든 열 너비의 합이 항상
      뷰포트 폭과 정확히 일치한다(가로 스크롤바·우측 빈 공간 없음).
    - 창/패널 크기가 바뀌면 ``resizeEvent`` 에서 자동 재맞춤.
    - 사용자가 숫자 열을 드래그하면 그만큼 flex 열(수종)이 늘거나 줄어 폭을 유지한다.

    → 긴 수종명도 flex 열이 가용 폭을 최대한 차지하므로 잘림이 최소화되고,
      그래도 부족하면 셀 툴팁으로 전체 값을 확인할 수 있다(호출측에서 설정).
    """

    def __init__(self, flex_col: int = 0, parent=None):
        super().__init__(parent)
        self._flex_col = flex_col
        self._fitting = False
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(px(48))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header.sectionResized.connect(self._on_section_resized)

    def fit_columns(self) -> None:
        """flex 열을 조정해 전체 열 너비 합 = 뷰포트 폭이 되도록 맞춘다."""
        n = self.columnCount()
        if n == 0:
            return
        vp = self.viewport().width()
        if vp <= 0:
            return
        min_sec = self.horizontalHeader().minimumSectionSize()
        self._fitting = True
        try:
            metrics = QFontMetrics(self.horizontalHeader().font())
            for c in range(n):
                item = self.horizontalHeaderItem(c)
                if c != self._flex_col and item is not None:
                    minimum = metrics.horizontalAdvance(item.text()) + px(20)
                    self.setColumnWidth(c, max(self.columnWidth(c), minimum))
            others = sum(self.columnWidth(c) for c in range(n) if c != self._flex_col)
            self.setColumnWidth(self._flex_col, max(min_sec, px(160), vp - others))
        finally:
            self._fitting = False

    def _on_section_resized(self, idx: int, _old: int, _new: int) -> None:
        # flex 열 자체의 변경/내부 보정 중에는 무시(재귀 방지)
        if self._fitting or idx == self._flex_col:
            return
        # 숫자 열을 사용자가 드래그 → flex 열이 잔여 폭을 흡수
        self.fit_columns()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_columns()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_columns()


class LinearGauge(QWidget):
    """수평 선형 게이지 (눈금 + 채워지는 바).

    세로 구성은 위에서부터 [바 밴드] → [눈금] → [눈금값] 이다. 바는 **밴드(band)
    안에서 세로 중앙**에 그려지므로, 같은 행의 제목·값 라벨을 같은 밴드 높이로
    맞춰 상단 정렬하면 (제목 · 바 · 값) 세 요소의 중심선이 정확히 일치한다.
    행 구성은 :func:`align_gauge_row` 가 담당한다.

    양 끝 눈금값(예: 0, 2000)이 위젯 밖으로 잘리지 않도록 트랙 좌우에 눈금값
    절반 폭만큼 여백을 둔다.
    """

    _TRACK_H = 16      # 바 두께 (기준 해상도 px)
    _TICK_LEN = 5      # 눈금 길이
    _TICK_GAP = 3      # 눈금 끝 ↔ 눈금값 사이 여백
    _TICK_PT = SMALL_PT  # 눈금값 글자 크기(pt)
    _RADIUS = 4        # 바 모서리 둥글기

    def __init__(self, minimum: float = 0.0, maximum: float = 100.0,
                 major_ticks: list[float] | None = None, parent=None):
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        self._value = 0.0
        self._value2: float | None = None
        self._major_ticks = list(major_ticks) if major_ticks else self._default_ticks()
        self._band_h = px(34)
        self._apply_geometry()

    def _default_ticks(self) -> list[float]:
        span = self._max - self._min
        if span <= 0:
            return [self._min, self._max]
        step = span / 5
        return [self._min + step * i for i in range(6)]

    # ----- 세로 배치 -----

    def _tick_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(pt(self._TICK_PT))
        return font

    def band_height(self) -> int:
        """바가 세로 중앙에 놓이는 상단 밴드의 높이."""
        return self._band_h

    def set_band_height(self, height: int) -> None:
        """상단 밴드 높이를 지정 (같은 행 제목·값 라벨 높이와 통일하기 위함)."""
        height = max(px(self._TRACK_H) + px(4), int(height))
        if height == self._band_h:
            return
        self._band_h = height
        self._apply_geometry()

    def _apply_geometry(self) -> None:
        """밴드 + 눈금 + 눈금값 이 정확히 들어가는 높이로 고정."""
        label_h = QFontMetrics(self._tick_font()).height()
        self.setFixedHeight(self._band_h + px(self._TICK_LEN) + px(self._TICK_GAP) + label_h)
        self.updateGeometry()
        self.update()

    # ----- 값 -----

    def setValue(self, v: float) -> None:
        self._value = max(self._min, min(self._max, float(v)))
        self.update()

    def setRange(self, minimum: float, maximum: float,
                 major_ticks: list[float] | None = None) -> None:
        self._min = float(minimum)
        self._max = max(self._min + 1e-9, float(maximum))
        self._major_ticks = list(major_ticks) if major_ticks else self._default_ticks()
        self._value = max(self._min, min(self._max, self._value))
        if self._value2 is not None:
            self._value2 = max(self._min, min(self._max, self._value2))
        self.update()

    def value(self) -> float:
        return self._value

    def setSecondaryValue(self, v: float | None) -> None:
        """보조 값(예: 생존률 반영). None 이면 막대 하나만 그린다.

        보조 값이 있으면 기본 값 막대는 옅게, 보조 값은 그 안쪽에 진한 얇은 막대로 그려
        두 결과를 한 눈금 위에서 비교할 수 있게 한다.
        """
        self._value2 = None if v is None else max(self._min, min(self._max, float(v)))
        self.update()

    def secondaryValue(self) -> float | None:
        return self._value2

    @staticmethod
    def _level_color(ratio: float) -> QColor:
        """채움 비율에 따른 색: green → orange → red."""
        if ratio < 0.6:
            return QColor(0x2E, 0x8B, 0x57)
        if ratio < 0.85:
            return QColor(0xE0, 0x9A, 0x2B)
        return QColor(0xC0, 0x39, 0x2B)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._tick_font())
        metrics = p.fontMetrics()

        w = self.width()
        labels = [f"{tick:,g}" for tick in self._major_ticks]

        # 좌우 여백 = 양 끝 눈금값의 절반 폭 (끝 숫자가 잘리지 않도록)
        pad = px(2)
        if labels:
            pad = max(pad,
                      metrics.horizontalAdvance(labels[0]) // 2,
                      metrics.horizontalAdvance(labels[-1]) // 2)

        track_h = px(self._TRACK_H)
        track_top = max(0, (self._band_h - track_h) // 2)
        track_rect = QRectF(pad, track_top, max(1, w - 2 * pad), track_h)
        radius = min(px(self._RADIUS), track_h / 2)

        # Track
        p.setPen(QPen(QColor(150, 150, 150), 1))
        p.setBrush(QColor(235, 235, 235))
        p.drawRoundedRect(track_rect, radius, radius)

        # Fill bar
        span = max(self._max - self._min, 1e-9)
        ratio = (self._value - self._min) / span
        ratio = max(0.0, min(1.0, ratio))
        fill_rect = QRectF(track_rect.x(), track_rect.y(),
                           track_rect.width() * ratio, track_rect.height())
        color = self._level_color(ratio)
        if self._value2 is not None:
            color.setAlpha(95)                   # 보조 값이 있으면 기본 막대는 옅게
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if fill_rect.width() > 0:
            p.drawRoundedRect(fill_rect, radius, radius)

        # 보조 값(생존률 반영): 트랙 안쪽 가운데의 진한 얇은 막대
        if self._value2 is not None:
            ratio2 = max(0.0, min(1.0, (self._value2 - self._min) / span))
            inner_h = track_rect.height() * 0.6
            inner = QRectF(track_rect.x(), track_rect.center().y() - inner_h / 2,
                           track_rect.width() * ratio2, inner_h)
            if inner.width() > 0:
                p.setBrush(self._level_color(ratio2).darker(115))
                r2 = min(radius, inner_h / 2)
                p.drawRoundedRect(inner, r2, r2)

        # Ticks + labels
        p.setPen(QPen(QColor(80, 80, 80), 1))
        tick_bottom = int(track_rect.bottom()) + px(self._TICK_LEN)
        baseline = tick_bottom + px(self._TICK_GAP) + metrics.ascent()
        # 좁은 배치(게이지 가로 1행)에서 눈금값이 겹치면 k 개마다 하나만 쓴다.
        widest = max((metrics.horizontalAdvance(t) for t in labels), default=0) + px(8)
        slots = max(1, len(labels) - 1)
        step = 1
        while step < slots and track_rect.width() * step / slots < widest:
            step += 1
        for i, (tick, label) in enumerate(zip(self._major_ticks, labels)):
            if i % step and i != len(labels) - 1:
                label = ""
            elif i != len(labels) - 1 and len(labels) - 1 - i < step and i:
                label = ""                       # 마지막 값과 겹치는 바로 앞 값
            t_ratio = (tick - self._min) / span
            x = track_rect.x() + track_rect.width() * t_ratio
            p.drawLine(int(x), int(track_rect.bottom()), int(x), tick_bottom)
            tw = metrics.horizontalAdvance(label)
            tx = min(max(0.0, x - tw / 2), max(0.0, w - tw))
            p.drawText(int(tx), baseline, label)


def align_gauge_row(title_label: QLabel, gauge: LinearGauge,
                    value_label: QLabel) -> int:
    """(제목 · 게이지 바 · 값) 세 위젯의 세로 중심선을 한 줄로 맞춘다.

    세 위젯 중 가장 높은 것을 기준으로 행 상단 밴드 높이를 정하고, 제목·값 라벨을
    그 높이로 고정한 뒤 게이지도 같은 밴드 안에 바를 세로 중앙 배치하게 한다.
    호출측은 세 위젯을 ``Qt.AlignTop`` 으로 배치하면 된다. 밴드 높이를 반환한다.
    """
    band = max(px(34),
               title_label.sizeHint().height(),
               value_label.sizeHint().height())
    title_label.setFixedHeight(band)
    value_label.setFixedHeight(band)
    gauge.set_band_height(band)
    return band
