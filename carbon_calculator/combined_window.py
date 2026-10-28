# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
통합 메인 윈도우 — **지역(권역)별 동적 탭** 관리.

- 상단 탭은 지역별로 동적으로 추가/삭제된다. 좌상단 [+ 지역 추가] 로 팝업을 띄워
  지역명·면적(가로×세로 m)·대상지 유형·위치(위도·경도, 선택)를 입력하면
  그 지역명을 라벨로 하는 새 탭(자생복원종 탄소저장량 추정 + 기여도 화면)이 생성된다.
- 우상단 [지역 종합 분석] 으로 모든 지역의 총 탄소저장량을 비교하는 대시보드를 연다.
- 국내·국외 통합 기여도(Carbon2) 모듈은 화면에 노출하지 않되 코드/인스턴스/수식은 보존한다.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QRect, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QTabBar, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from .calculations import calculate_site_carbon_metrics
from .data import RESTORATION_ENVIRONMENTS
from .i18n import (
    LANG_EN, LANG_KO, environment_name, get_language, save_language, set_language, tr,
)
from .excel_export import export_all_regions_to_excel
from . import preset_io
from .main_window import MainWindow as Carbon1Window
from .main_window2 import Carbon2MainWindow
from .plotting import MatplotlibCanvas, set_plot_font_scale
from .font_config import setup_application_fonts
from .ui_scale import apply_dialog_size, apply_window_size, pt, px, ui_scale
from .typography import BODY_PT, HEADING_PT, TITLE_PT
from .version import __version__


# 대상지 유형 선택지 — data.py 를 단일 출처로 사용하며 보고서 메타데이터로 보존한다.
ENVIRONMENTS = RESTORATION_ENVIRONMENTS


def build_region_comparison_record(region: dict) -> dict:
    """Build one auditable multi-site comparison record.

    Total stock is determined exclusively by the accepted inventory. Site area
    is then used as the denominator for the area-normalized reporting metric,
    in accordance with the controlled comparison presented in Figure 3 of the
    accompanying manuscript.
    """
    inventory = region["window"].region_inventory_summary()
    area = float(region["w"]) * float(region["h"])
    metrics = calculate_site_carbon_metrics(
        inventory["tree"], inventory["shrub"], area
    )
    location = region.get("location")
    return {
        "name": region["name"],
        "w": region["w"],
        "h": region["h"],
        "area": area,
        "env": region["env"],
        "latitude": location[0] if location else None,
        "longitude": location[1] if location else None,
        "tree": metrics.tree_carbon_kg,
        "shrub": metrics.shrub_carbon_kg,
        "total": metrics.total_carbon_kg,
        "density": metrics.area_normalized_kg_m2,
        "tree_quantity": inventory["tree_quantity"],
        "shrub_quantity": inventory["shrub_quantity"],
        "tree_planting_area": inventory["tree_planting_area"],
        "shrub_planting_area": inventory["shrub_planting_area"],
        "required_planting_area": inventory["required_planting_area"],
    }


# ------------------------------ 지역 위치 (위도·경도) ------------------------------

def map_url(lat: float, lon: float, name: str = "") -> str:
    """지도 서비스 주소 — 국문은 카카오맵(표식+이름), 영문은 OpenStreetMap."""
    if get_language() == LANG_KO:
        label = QUrl.toPercentEncoding((name or "지역").replace(",", " ")).data().decode()
        return f"https://map.kakao.com/link/map/{label},{lat:.6f},{lon:.6f}"
    return (f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}"
            f"#map=15/{lat:.6f}/{lon:.6f}")


class _LocationFields(QWidget):
    """위도·경도 입력 한 줄 (선택 입력, 십진수 도)."""

    def __init__(self, location=None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        # 입력 검증기는 두지 않는다 — '36.4986, 127.2896' 을 한 칸에 붙여 넣을 수 있어야
        # 하므로, 값 검사는 [확인] 시 validate_location 으로 한다.
        self.lat_edit = QLineEdit()
        self.lat_edit.setPlaceholderText(tr("위도 (예: 36.4986)"))
        self.lon_edit = QLineEdit()
        self.lon_edit.setPlaceholderText(tr("경도 (예: 127.2896)"))
        for edit in (self.lat_edit, self.lon_edit):
            edit.setToolTip(tr("선택 입력 — 십진수 도(WGS84). 지도 앱에서 위치를 길게 눌러 복사한 값을 붙여 넣을 수 있습니다."))
        self.lat_edit.textEdited.connect(self._split_pasted_pair)
        row.addWidget(self.lat_edit, 1)
        row.addWidget(QLabel(","))
        row.addWidget(self.lon_edit, 1)
        if location:
            self.lat_edit.setText(f"{location[0]:.6f}".rstrip("0").rstrip("."))
            self.lon_edit.setText(f"{location[1]:.6f}".rstrip("0").rstrip("."))

    def _split_pasted_pair(self, text: str) -> None:
        """'36.4986, 127.2896' 처럼 한 칸에 붙여 넣은 좌표쌍을 두 칸으로 나눈다."""
        parts = [t for t in text.replace(",", " ").split() if t]
        if len(parts) == 2:
            self.lat_edit.setText(parts[0])
            self.lon_edit.setText(parts[1])

    def location(self):
        """(위도, 경도) 또는 None. 잘못된 입력은 ValueError."""
        return preset_io.validate_location(self.lat_edit.text(), self.lon_edit.text())


class LocationDialog(QDialog):
    """지역 위치(위도·경도) 입력·수정."""

    def __init__(self, name: str, location=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("‘{name}’ 위치").format(name=name))
        self.setModal(True)
        apply_dialog_size(self, 460, 170)
        self.fields = _LocationFields(location)
        form = QFormLayout()
        form.addRow(tr("위도 , 경도"), self.fields)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("확인"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("취소"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        hint = QLabel(tr("두 칸을 모두 비우면 위치 정보가 삭제됩니다."))
        hint.setStyleSheet("color: #777;")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self._location = location

    def accept(self) -> None:
        try:
            self._location = self.fields.location()
        except ValueError as exc:
            QMessageBox.warning(self, tr("위치 확인"), str(exc))
            return
        super().accept()

    def value(self):
        return self._location


# ------------------------------ 지역 추가 다이얼로그 ------------------------------

class AddRegionDialog(QDialog):
    """지역명 · 면적(가로×세로 m) · 대상지 유형 · 위치(선택) 입력 모달."""

    def __init__(self, existing_names: List[str], parent=None):
        super().__init__(parent)
        self._existing = set(existing_names)
        self.setWindowTitle(tr("지역 추가"))
        self.setModal(True)
        apply_dialog_size(self, 520, 360)

        form = QFormLayout()
        form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("예: 세종, 청주, 오송 ..."))
        form.addRow(tr("지역명"), self.name_edit)

        # 면적: 가로 × 세로 (m), 기본 20 × 20
        area_row = QHBoxLayout()
        area_row.setSpacing(6)
        self.w_spin = QSpinBox(); self.w_spin.setRange(1, 100000); self.w_spin.setValue(20)
        self.w_spin.setSuffix(" m")
        self.h_spin = QSpinBox(); self.h_spin.setRange(1, 100000); self.h_spin.setValue(20)
        self.h_spin.setSuffix(" m")
        area_row.addWidget(self.w_spin, 1)
        area_row.addWidget(QLabel("×"))
        area_row.addWidget(self.h_spin, 1)
        area_wrap = QWidget(); area_wrap.setLayout(area_row)
        form.addRow(tr("면적 (가로 × 세로)"), area_wrap)

        self.env_combo = QComboBox()
        self.env_combo.addItems([environment_name(e) for e in ENVIRONMENTS])
        form.addRow(tr("대상지 유형 (메타데이터)"), self.env_combo)

        self.location_fields = _LocationFields()
        form.addRow(tr("위치 (선택)"), self.location_fields)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("추가"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("취소"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form, 1)
        layout.addWidget(buttons)

        self.name_edit.setFocus()

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("입력 필요"), tr("지역명을 입력해 주세요."))
            self.name_edit.setFocus()
            return
        if name in self._existing:
            QMessageBox.warning(
                self, tr("중복된 지역명"),
                tr("‘{name}’ 지역이 이미 있습니다. 다른 이름을 사용해 주세요.").format(name=name))
            self.name_edit.setFocus()
            self.name_edit.selectAll()
            return
        try:
            self._location = self.location_fields.location()
        except ValueError as exc:
            QMessageBox.warning(self, tr("위치 확인"), str(exc))
            self.location_fields.lat_edit.setFocus()
            return
        super().accept()

    def values(self):
        """(지역명, 가로 m, 세로 m, 대상지 유형, 위치 (위도, 경도) | None) 반환."""
        # 콤보는 표시명(영문일 수 있음)이므로 내부 키(한글 원문)로 되돌린다.
        env = ENVIRONMENTS[max(0, self.env_combo.currentIndex())]
        return (self.name_edit.text().strip(),
                self.w_spin.value(), self.h_spin.value(),
                env, getattr(self, "_location", None))


# ------------------------------ 지역 선택 다이얼로그 ------------------------------

class RegionSelectDialog(QDialog):
    """종합 분석에 포함할 지역을 체크박스로 선택하는 모달 (기본 전체 선택)."""

    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("지역 선택 — 종합 분석"))
        self.setModal(True)
        apply_dialog_size(self, 420, 460)

        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("비교 분석할 지역을 선택하세요 (2개 이상 권장):")))

        self.list = QListWidget()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list.addItem(item)
        v.addWidget(self.list, 1)

        # 전체 선택/해제
        toggle_row = QHBoxLayout()
        all_btn = QPushButton(tr("전체 선택"))
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn = QPushButton(tr("전체 해제"))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        toggle_row.addWidget(all_btn)
        toggle_row.addWidget(none_btn)
        toggle_row.addStretch(1)
        v.addLayout(toggle_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("분석"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("취소"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _set_all(self, state) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected_indices(self) -> List[int]:
        return [i for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


# ------------------------------ 지역 종합 분석 대시보드 ------------------------------

class RegionComparisonDialog(QDialog):
    """프로필별 식재 구성과 탄소저장량 비교 대시보드 (막대 차트 + 표)."""

    def __init__(self, data: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("지역 종합 분석"))
        self.setModal(True)
        # 대시보드는 크게 (화면을 넘지 않도록 apply_dialog_size 가 자동 클램프).
        apply_dialog_size(self, 1280, 860)

        v = QVBoxLayout(self)
        v.setSpacing(8)

        title = QLabel(tr("프로필별 식재 구성 및 탄소저장량 비교"))
        tf = title.font(); tf.setPointSize(pt(TITLE_PT)); tf.setBold(True)
        title.setFont(tf); title.setStyleSheet("color: #246B43;")
        v.addWidget(title)

        # 합계 요약
        grand = sum(d["total"] for d in data)
        if data:
            top = max(data, key=lambda d: d["total"])
            common_areas = {float(d["area"]) for d in data}
            if len(common_areas) == 1:
                summary = (
                    tr("{n}개 프로필 · 공통 대상지 면적 {area:,.0f} m²")
                    .format(n=len(data), area=next(iter(common_areas)))
                    + tr("   |   최대: {name} ({total:,.2f} kgC)")
                    .format(name=top["name"], total=top["total"])
                )
            elif max(d["total"] for d in data) - min(d["total"] for d in data) <= 1e-9:
                summary = tr(
                    "{n}개 프로필 · 동일 총 탄소량 {total:,.2f} kgC · "
                    "대상지 면적 {min_area:,.0f}–{max_area:,.0f} m²"
                ).format(
                    n=len(data),
                    total=data[0]["total"],
                    min_area=min(common_areas),
                    max_area=max(common_areas),
                )
            else:
                summary = (tr("총 {n}개 지역 · 전체 합계 {total:,.2f} kgC")
                           .format(n=len(data), total=grand)
                           + tr("   |   최대: {name} ({total:,.2f} kgC)")
                           .format(name=top["name"], total=top["total"]))
        else:
            summary = tr("지역 데이터 없음")
        sub = QLabel(summary); sub.setStyleSheet("color: #555;")
        v.addWidget(sub)

        # 총 탄소저장량과 면적 정규화 탄소밀도를 나란히 제시한다.
        chart_row = QHBoxLayout()
        stock_canvas = MatplotlibCanvas(width=5.2, height=4.6)
        stock_canvas.plot_region_bars(
            [d["name"] for d in data],
            [d["tree"] for d in data],
            [d["shrub"] for d in data],
            show_title=True,
        )
        density_canvas = MatplotlibCanvas(width=5.2, height=4.6)
        density_canvas.plot_region_density_bars(
            [d["name"] for d in data],
            [d["density"] for d in data],
            show_title=True,
        )
        chart_row.addWidget(stock_canvas, 1)
        chart_row.addWidget(density_canvas, 1)
        v.addLayout(chart_row, 3)

        # 비교 표
        table = QTableWidget()
        headers = [
            tr("지역"),
            tr("면적(㎡)"),
            tr("교목\n개수 | 식재면적(㎡)"),
            tr("관목\n개수 | 식재면적(㎡)"),
            tr("필요면적 / 대상지면적(㎡)"),
            tr("교목(kgC)"),
            tr("관목(kgC)"),
            tr("총 탄소저장량(kgC)"),
            tr("면적 정규화\n탄소밀도(kgC/㎡)"),
        ]
        # 표 글꼴을 다른 결과 표와 같은 크기로 못 박는다 — 전역 QSS 가 걸린 위젯은
        # 앱 기본 폰트를 잃고 스타일 기본값(작은 글씨)으로 돌아갈 수 있다.
        cell_font = QFont(table.font())
        cell_font.setPointSize(pt(HEADING_PT))
        header_font = QFont(cell_font)
        header_font.setBold(True)
        table.setFont(cell_font)
        table.horizontalHeader().setFont(header_font)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(data))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(False)
        # 열 제목은 폭이 모자라면 잘린다 → 단어 단위 줄바꿈을 켜고, 줄이 늘어난
        # 만큼의 높이를 미리 확보한다(영문 제목이 한글보다 길어 특히 필요하다).
        # Qt.TextWordWrap 은 TextFlag 라 AlignmentFlag 와 OR 하면 평범한 int 가 된다.
        # PyQt5 는 int 를 거부하므로(→ 예외 발생 시 앱이 그대로 종료된다) Alignment 로 감싼다.
        table.horizontalHeader().setDefaultAlignment(
            Qt.Alignment(Qt.AlignCenter | Qt.TextWordWrap))
        table.setWordWrap(True)
        cell_font_h = table.fontMetrics().height()
        for i, d in enumerate(data):
            tree_quantity = int(d.get("tree_quantity", 0))
            shrub_quantity = int(d.get("shrub_quantity", 0))
            tree_area = float(d.get("tree_planting_area", tree_quantity))
            shrub_area = float(d.get("shrub_planting_area", shrub_quantity * 0.25))
            required_area = float(d.get("required_planting_area", tree_area + shrub_area))
            cells = [
                d["name"],
                f"{d['area']:,}",
                f"{tree_quantity:,} | {tree_area:,.2f}",
                f"{shrub_quantity:,} | {shrub_area:,.2f}",
                f"{required_area:,.2f} / {d['area']:,.2f}",
                f"{d['tree']:,.2f}",
                f"{d['shrub']:,.2f}",
                f"{d['total']:,.2f}",
                f"{d['density']:,.4f}",
            ]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignCenter))
                table.setItem(i, j, item)
            table.setRowHeight(i, max(px(44), cell_font_h + px(14)))

        # 열 폭 → 머리글 높이 순서로 맞춘다(줄 수가 열 폭에 달려 있다).
        self._table = table
        self._table_headers = headers
        self._table_fonts = (cell_font, header_font)
        self._fit_column_widths(table, headers, cell_font, header_font)
        table.horizontalHeader().setMinimumHeight(
            self._wrapped_header_height(table, headers, header_font))

        # 지역 수가 적을 때 표가 잘려 보이지 않도록, 머리글 + 전체 행이 들어갈
        # 높이를 확보한다(많으면 스크롤).
        visible_rows = min(table.rowCount(), 8)
        row_h = max(px(44), cell_font_h + px(14))
        table.setMinimumHeight(table.horizontalHeader().minimumHeight()
                               + row_h * visible_rows + px(16))
        v.addWidget(table, 2)

        note = QLabel(
            tr("면적 정규화 탄소밀도는 총 탄소저장량을 대상지 면적으로 나눈 값입니다. "
               "교목·관목 열은 유효 개체 수 | 설정된 식재면적을 나타냅니다. "
               "식재면적은 입력 보호용 값이며 수종별 식재 권고가 아닙니다.")
        )
        note.setStyleSheet("color: #555;")
        note.setWordWrap(True)
        v.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr("닫기"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        v.addWidget(buttons)

    def resizeEvent(self, event):    # noqa: N802 — Qt 시그니처
        """창 폭이 바뀌면 열 폭과 머리글 높이를 다시 맞춘다."""
        super().resizeEvent(event)
        table = getattr(self, "_table", None)
        if table is None:
            return
        cell_font, header_font = self._table_fonts
        self._fit_column_widths(table, self._table_headers, cell_font, header_font)
        table.horizontalHeader().setMinimumHeight(
            self._wrapped_header_height(table, self._table_headers, header_font))

    def _fit_column_widths(self, table: QTableWidget, headers: List[str],
                           cell_font: QFont, header_font: QFont) -> None:
        """열마다 필요한 폭을 주고, 남는 폭은 첫 열(지역명)이 흡수하게 한다.

        모든 열을 같은 폭으로 나누면(Stretch) 값이 긴 열은 '...' 로 생략되고 짧은
        열은 남아돈다. 셀 값과 머리글의 가장 긴 낱말을 재서 열마다 따로 잡는다.
        """
        cell_metrics = QFontMetrics(cell_font)
        header_metrics = QFontMetrics(header_font)
        pad = px(22)
        widths: List[int] = []
        for column in range(table.columnCount()):
            cells = [table.item(row, column) for row in range(table.rowCount())]
            widest_cell = max((cell_metrics.horizontalAdvance(c.text())
                               for c in cells if c is not None), default=0)
            # 머리글은 줄바꿈되므로 가장 긴 '낱말' 만 들어가면 잘리지 않는다.
            words = headers[column].replace("\n", " ").split(" ") or [""]
            widest_word = max((header_metrics.horizontalAdvance(w) for w in words),
                              default=0)
            widths.append(max(widest_cell, widest_word) + pad)

        viewport = table.viewport().width() or (self.width() - px(40))
        total = sum(widths)
        slack = max(px(320), viewport) - total
        if slack > 0 and total > 0:
            widths = [w + int(slack * w / total) for w in widths]
        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)

    def _wrapped_header_height(self, table: QTableWidget, headers: List[str],
                               font: QFont) -> int:
        """열 제목이 줄바꿈된 뒤 필요한 머리글 높이(px)를 계산한다.

        열마다 폭이 다르므로 각 열의 실제 폭에서 몇 줄이 되는지 재고,
        가장 높은 값을 머리글 높이로 쓴다.
        """
        metrics = QFontMetrics(font)
        columns = max(1, len(headers))
        fallback = max(px(70), max(px(320), self.width() - px(40)) // columns)
        tallest = metrics.height()
        for index, text in enumerate(headers):
            column_w = table.columnWidth(index) or fallback
            # 스타일이 그릴 때의 좌우 여백을 넉넉히 빼고 재어, 줄 수를 모자라게
            # 잡아 마지막 줄이 잘리는 일이 없게 한다.
            box = metrics.boundingRect(
                QRect(0, 0, max(px(40), column_w - px(20)), px(400)),
                int(Qt.AlignCenter | Qt.TextWordWrap), text)
            tallest = max(tallest, box.height())
        return max(px(58), tallest + px(26))


# ------------------------------ 통합 메인 윈도우 ------------------------------

class CombinedMainWindow(QMainWindow):
    """지역별 동적 탭을 관리하는 최상위 윈도우."""

    def __init__(self):
        super().__init__()
        apply_window_size(self, wfrac=0.84, hfrac=0.88, min_w=1100, min_h=680)

        # 지역 목록: 각 항목 {name, w, h, env, window(Carbon1Window), container}
        self._regions: List[dict] = []
        self._placeholder: Optional[QWidget] = None

        # 국내·국외 통합(Carbon2)은 화면에 노출하지 않되 코드/수식 재사용을 위해 인스턴스 보존.
        self._carbon2 = Carbon2MainWindow()

        self._build_ui()

    # ----- UI 구성 (최초 생성과 언어 변경 시 재구성에 공용으로 쓰인다) -----

    def _build_ui(self) -> None:
        """창 제목·탭 영역·메뉴·상태바를 현재 언어로 (다시) 구성한다.

        기존 중앙 위젯이 있으면(=언어 변경으로 인한 재구성) 안전하게 떼어내
        (``takeCentralWidget``) 새 위젯으로 교체한 뒤 지연 삭제한다. 메뉴바는
        Qt가 재사용하는 기존 객체이므로 다시 채우기 전에 비운다.
        """
        self.setWindowTitle(
            tr("ForeCarb - 산림복원지 탄소추정 및 시나리오 분석 소프트웨어 (Ver. {version})")
            .format(version=__version__)
        )

        old_central = self.takeCentralWidget()

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)
        tabs.setDocumentMode(False)
        tabs.setMovable(True)
        tabs.setTabsClosable(True)
        tabs.tabCloseRequested.connect(self._close_region)
        tab_font = QFont(); tab_font.setPointSize(pt(BODY_PT)); tab_font.setBold(True)
        tabs.tabBar().setFont(tab_font)

        # 좌상단 [+ 지역 추가], 우상단 [지역 종합 분석]
        add_btn = QPushButton(tr("+ 지역 추가"))
        add_btn.setObjectName("accentButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_region)
        tabs.setCornerWidget(add_btn, Qt.TopLeftCorner)

        # 우상단 버튼 컨테이너 — 지역 종합 분석 + 통합 Excel 저장
        right_corner = QWidget()
        right_layout = QHBoxLayout(right_corner)
        right_layout.setContentsMargins(0, 0, 4, 0)
        right_layout.setSpacing(6)

        dash_btn = QPushButton(tr("지역 종합 분석"))
        dash_btn.setObjectName("accentButton")
        dash_btn.setCursor(Qt.PointingHandCursor)
        dash_btn.clicked.connect(self._open_dashboard)

        export_btn = QPushButton(tr("통합 Excel 저장"))
        export_btn.setObjectName("accentButton")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_all_regions_excel)

        right_layout.addWidget(dash_btn)
        right_layout.addWidget(export_btn)
        tabs.setCornerWidget(right_corner, Qt.TopRightCorner)

        self._tabs = tabs
        self.setCentralWidget(tabs)
        self._set_placeholder(True)

        if old_central is not None:
            old_central.deleteLater()

        self.menuBar().clear()
        self._build_menu()
        self._build_statusbar()

    # ----- 지역 추가/삭제 -----

    def _add_region(self) -> None:
        dlg = AddRegionDialog([r["name"] for r in self._regions], self)
        if dlg.exec_() != QDialog.Accepted:
            return
        name, w, h, env, location = dlg.values()
        self._create_region(name, w, h, env, location)

    def _create_region(self, name: str, w: int, h: int, env: str, location=None) -> int:
        """지역 탭을 생성하고 추가한다. 추가된 탭 인덱스를 반환."""
        self._set_placeholder(False)
        # 지역의 대상지 유형·이름·면적을 Carbon1 에 전달 → Excel 자동 네이밍/요약.
        window = Carbon1Window(environment=env, region_name=name, area_w=w, area_h=h)
        window.location = location
        region = {"name": name, "w": w, "h": h, "env": env, "location": location,
                  "window": window}
        region["container"] = self._wrap_region(region)
        idx = self._tabs.addTab(region["container"], name)
        self._regions.append(region)
        self._refresh_region_info(region)
        self._tabs.setCurrentIndex(idx)
        self._status_label.setText(
            tr("‘{name}’ 지역 추가됨 — 교목/관목 탭에서 [+ 추가] 후 [계 산]. "
               "여러 지역은 우상단 [지역 종합 분석]으로 비교.").format(name=name)
        )
        return idx

    def _wrap_region(self, region: dict) -> QWidget:
        """지역 정보 배너 + Carbon1 화면을 묶은 탭 컨테이너."""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        banner = QLabel()
        banner.setTextFormat(Qt.RichText)
        banner.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        banner.setOpenExternalLinks(False)
        banner.linkActivated.connect(lambda link, r=region: self._on_region_link(r, link))
        banner.setStyleSheet(
            "background: #EEF4EF; border: 1px solid #D8E3DB; border-radius: 6px; "
            "padding: 6px 10px; color: #246B43;"
        )
        region["banner"] = banner
        v.addWidget(banner)
        v.addWidget(region["window"].centralWidget(), 1)
        return container

    def _refresh_region_info(self, region: dict) -> None:
        """배너 문구와 탭 툴팁을 지역 정보(위치 포함)로 갱신한다."""
        name, w, h, env = region["name"], region["w"], region["h"], region["env"]
        location = region.get("location")
        text = (tr("📍 지역: <b>{name}</b>　|　면적: {w} × {h} m  (<b>{area}</b> ㎡)　|　"
                   "대상지 유형: <b>{env}</b>")
                .format(name=name, w=w, h=h, area=f"{w * h:,}", env=environment_name(env)))
        link_style = "color: #1F5FA8;"
        if location:
            text += (tr("　|　위치: <b>{loc}</b>").format(
                        loc=preset_io.format_location(*location))
                     + f' <a href="map" style="{link_style}">{tr("지도 보기")}</a>'
                     + f' · <a href="edit" style="{link_style}">{tr("수정")}</a>')
        else:
            text += f'　|　<a href="edit" style="{link_style}">{tr("위치 입력")}</a>'
        region["banner"].setText(text)
        tip = f"{name} · {w}×{h} m · {environment_name(env)}"
        if location:
            tip += " · " + preset_io.format_location(*location)
        idx = self._tabs.indexOf(region["container"])
        if idx >= 0:
            self._tabs.setTabToolTip(idx, tip)

    def _on_region_link(self, region: dict, link: str) -> None:
        if link == "map" and region.get("location"):
            lat, lon = region["location"]
            QDesktopServices.openUrl(QUrl(map_url(lat, lon, region["name"])))
            return
        dlg = LocationDialog(region["name"], region.get("location"), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        region["location"] = dlg.value()
        region["window"].location = region["location"]
        self._refresh_region_info(region)

    def _close_region(self, index: int) -> None:
        widget = self._tabs.widget(index)
        region = next((r for r in self._regions if r["container"] is widget), None)
        if region is None:
            return  # 안내(placeholder) 등 지역이 아닌 탭은 무시
        if QMessageBox.question(
            self, tr("지역 삭제"),
            tr("‘{name}’ 지역을 삭제할까요? 입력/결과가 사라집니다.")
            .format(name=region["name"]),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._tabs.removeTab(index)
        self._regions.remove(region)
        self._dispose_region(region)
        if not self._regions:
            self._set_placeholder(True)

    @staticmethod
    def _dispose_region(region: dict) -> None:
        """지역 하나의 창·컨테이너를 닫고 지연 삭제한다."""
        region["window"].close()
        region["window"].deleteLater()
        region["container"].deleteLater()

    def _teardown_regions(self) -> None:
        """모든 지역 인스턴스를 정리한다 (언어 변경으로 전체 재구성할 때 사용).

        탭에서 각각 제거할 필요는 없다 — 이 지역들을 담고 있던 탭 위젯
        자체가 ``_build_ui`` 에서 곧 통째로 교체·지연 삭제되기 때문이다.
        """
        for region in self._regions:
            self._dispose_region(region)
        self._regions = []
        if self._placeholder is not None:
            self._placeholder.deleteLater()
            self._placeholder = None

    def _set_placeholder(self, visible: bool) -> None:
        """지역이 없을 때 안내용 탭을 표시/제거한다."""
        if visible:
            if self._placeholder is not None:
                return
            hint = QLabel(tr(
                "‘+ 지역 추가’ 버튼으로 지역을 추가하세요.\n\n"
                "각 지역은 독립적인 [자생복원종 탄소저장량 추정 + 기여도] 화면을 가지며,\n"
                "여러 지역을 추가한 뒤 우상단 [지역 종합 분석]으로 총 탄소저장량을 비교할 수 있습니다."
            ))
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("color: #888; padding: 24px;")
            self._placeholder = hint
            idx = self._tabs.addTab(hint, tr("안내"))
            # 안내 탭에는 닫기 버튼을 두지 않는다.
            self._tabs.tabBar().setTabButton(idx, QTabBar.RightSide, None)
            self._tabs.tabBar().setTabButton(idx, QTabBar.LeftSide, None)
        else:
            if self._placeholder is None:
                return
            i = self._tabs.indexOf(self._placeholder)
            if i >= 0:
                self._tabs.removeTab(i)
            self._placeholder.deleteLater()
            self._placeholder = None

    # ----- 데이터 불러오기 / 저장 (입력 양식 엑셀) -----

    def _library_listing(self) -> dict:
        """양식의 [수종목록] 시트용: (수종 키, 설명변수, 적합 직경범위)."""
        from . import species_library as lib
        out = {}
        for kind in (lib.KIND_TREE, lib.KIND_SHRUB):
            out[kind] = [(name, rec.var1_label, rec.range_text())
                         for name, rec in lib.records_for_kind(kind, ENVIRONMENTS[0]).items()]
        return out

    def _save_data_workbook(self) -> None:
        """열린 지역들의 입력(면적·대상지 유형·수종·직경·개체수·생존율)을 양식 엑셀로 저장.

        저장한 파일은 [데이터 불러오기] 로 그대로 다시 열 수 있다. 열린 지역이 없으면
        예시 데이터(Profile 1~3)가 든 양식을 저장한다.
        """
        regions = [
            preset_io.PresetRegion(r["name"], int(r["w"]), int(r["h"]), r["env"],
                                   r["window"].preset_rows(),
                                   *(r.get("location") or (None, None)))
            for r in self._regions_in_tab_order()
        ]
        regions = [r for r in regions if r.rows]
        path, _f = QFileDialog.getSaveFileName(
            self, tr("데이터 저장"), tr("ForeCarb_데이터.xlsx"), tr("Excel 파일 (*.xlsx)"))
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            preset_io.write_template(path, list(ENVIRONMENTS), self._library_listing(),
                                     regions or None)
        except PermissionError:
            QMessageBox.warning(self, tr("저장 실패"),
                                tr("파일이 다른 프로그램(Excel 등)에서 열려 있어 저장할 수 없습니다.\n"
                                   "해당 파일을 닫고 다시 시도해 주세요."))
            return
        if regions:
            message = tr("{n}개 지역의 입력 데이터를 저장했습니다:\n{path}").format(n=len(regions), path=path)
        else:
            message = tr("입력된 지역이 없어 예시 데이터(Profile 1~3)가 든 양식을 저장했습니다:\n{path}").format(path=path)
        QMessageBox.information(self, tr("저장 완료"), message)

    def _load_preset_workbook(self) -> None:
        """양식 엑셀의 지역마다 탭을 만들고 수종 입력을 채운 뒤 계산한다."""
        from . import species_library as lib
        path, _f = QFileDialog.getOpenFileName(
            self, tr("데이터 불러오기"), "", tr("Excel 파일 (*.xlsx)"))
        if not path:
            return
        tree_names = list(lib.records_for_kind(lib.KIND_TREE, ENVIRONMENTS[0]).keys())
        shrub_names = list(lib.records_for_kind(lib.KIND_SHRUB, ENVIRONMENTS[0]).keys())
        try:
            result = preset_io.read_preset(path, tree_names, shrub_names, ENVIRONMENTS)
        except Exception as exc:  # noqa: BLE001 — 형식 오류 안내
            QMessageBox.warning(self, tr("데이터 불러오기 실패"), str(exc))
            return
        if not result.regions:
            QMessageBox.warning(self, tr("데이터 불러오기 실패"),
                                "\n".join(result.errors[:20]) or tr("불러올 수종 입력이 없습니다."))
            return

        existing = {r["name"] for r in self._regions}
        clash = [r.name for r in result.regions if r.name in existing]
        replace = False
        if clash:
            answer = QMessageBox.question(
                self, tr("같은 이름의 지역"),
                tr("이미 있는 지역: {names}\n\n예 = 기존 탭을 닫고 새로 만들기 · 아니요 = 이름 뒤에 번호를 붙여 추가")
                .format(names=", ".join(clash)),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
            if answer == QMessageBox.Cancel:
                return
            replace = answer == QMessageBox.Yes
        if replace:
            for region in [r for r in self._regions if r["name"] in clash]:
                self._tabs.removeTab(self._tabs.indexOf(region["container"]))
                self._regions.remove(region)
                self._dispose_region(region)
            existing -= set(clash)

        created = []
        for preset in result.regions:
            name, n = preset.name, 2
            while name in existing:
                name, n = f"{preset.name} ({n})", n + 1
            existing.add(name)
            location = ((preset.latitude, preset.longitude)
                        if preset.latitude is not None and preset.longitude is not None else None)
            self._create_region(name, preset.width_m, preset.height_m,
                                preset.environment or ENVIRONMENTS[0], location)
            window = self._regions[-1]["window"]
            window.apply_preset_rows(preset.rows)
            window.on_calculate()
            created.append(f"{name} ({len(preset.rows)})")
        self._status_label.setText(
            tr("{n}개 지역 데이터를 불러와 계산했습니다: {names}").format(n=len(created), names=", ".join(created)))
        notes = list(result.errors) + list(result.notes)
        if notes:
            QMessageBox.information(self, tr("데이터 불러오기 — 확인 사항"), "\n".join(notes[:25]))

    # ----- 지역 종합 분석 -----

    def _regions_in_tab_order(self) -> List[dict]:
        """현재 탭 순서대로 정렬된 지역 목록 (안내 placeholder 탭은 자연히 제외)."""
        by_container = {r["container"]: r for r in self._regions}
        ordered = []
        for i in range(self._tabs.count()):
            r = by_container.get(self._tabs.widget(i))
            if r is not None:
                ordered.append(r)
        return ordered

    def _open_dashboard(self) -> None:
        if not self._regions:
            QMessageBox.information(
                self, tr("지역 없음"),
                tr("분석할 지역이 없습니다. ‘+ 지역 추가’로 지역을 먼저 추가해 주세요."),
            )
            return

        # 탭을 드래그로 옮겨도 선택 목록 순서가 화면 탭 순서와 일치하도록 탭 순서로 정렬.
        ordered = self._regions_in_tab_order()

        # 비교할 지역을 사용자가 선택 (기본 전체 선택).
        sel = RegionSelectDialog([r["name"] for r in ordered], self)
        if sel.exec_() != QDialog.Accepted:
            return
        indices = sel.selected_indices()
        if not indices:
            QMessageBox.information(
                self, tr("선택 필요"), tr("비교할 지역을 1개 이상 선택해 주세요."),
            )
            return

        data = [build_region_comparison_record(ordered[i]) for i in indices]
        RegionComparisonDialog(data, self).exec_()

    def _export_all_regions_excel(self) -> None:
        """선택한 지역들의 탄소저장량 추정치·기여도·비교분석·그래프를 통합 Excel로 저장."""
        if not self._regions:
            QMessageBox.information(
                self, tr("지역 없음"),
                tr("내보낼 지역이 없습니다. '+ 지역 추가'로 지역을 먼저 추가해 주세요."),
            )
            return

        ordered = self._regions_in_tab_order()
        sel = RegionSelectDialog([r["name"] for r in ordered], self)
        if sel.exec_() != QDialog.Accepted:
            return
        indices = sel.selected_indices()
        if not indices:
            QMessageBox.information(self, tr("선택 필요"),
                                    tr("내보낼 지역을 1개 이상 선택해 주세요."))
            return

        payloads        = []
        comparison_data = []
        skipped         = []
        for i in indices:
            r       = ordered[i]
            payload = r["window"].build_export_payload()
            if payload is None:
                skipped.append(r["name"])
                continue
            payloads.append(payload)
            comparison_data.append(build_region_comparison_record(r))

        if not payloads:
            QMessageBox.information(
                self, tr("저장할 내용 없음"),
                tr("선택한 지역에 계산 결과가 없습니다.\n"
                   "각 지역에서 항목을 추가한 뒤 [계 산]을 눌러 주세요."),
            )
            return

        if skipped:
            QMessageBox.information(
                self, tr("일부 지역 제외"),
                tr("계산 결과가 없어 제외된 지역: {names}\n"
                   "나머지 지역으로 내보내기를 진행합니다.").format(names=", ".join(skipped)),
            )

        parent = QApplication.activeWindow() or self
        path, _ = QFileDialog.getSaveFileName(
            parent, tr("통합 Excel로 저장"), tr("탄소저장량_통합분석.xlsx"),
            tr("Excel 파일 (*.xlsx)"),
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            export_all_regions_to_excel(path, payloads, comparison_data)
        except PermissionError:
            QMessageBox.warning(
                self, tr("저장 실패"),
                tr("파일이 다른 프로그램(Excel 등)에서 열려 있어 저장할 수 없습니다.\n"
                   "해당 파일을 닫고 다시 시도해 주세요."),
            )
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("저장 실패"),
                                tr("저장 중 오류가 발생했습니다:\n{error}").format(error=exc))
            return

        QMessageBox.information(
            self, tr("저장 완료"),
            tr("통합 분석 결과가 저장되었습니다:\n{path}\n\n"
               "포함된 시트: 지역별_추정치 · 탄소_기여도 · 생존률_반영 · 지역_비교분석 · 그래프")
            .format(path=path),
        )

    # ----- 메뉴/상태바 -----

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("파일(&F)"))
        preset_action = QAction(tr("데이터 불러오기(&O)"), self)
        preset_action.setShortcut("Ctrl+O")
        preset_action.triggered.connect(self._load_preset_workbook)
        file_menu.addAction(preset_action)
        template_action = QAction(tr("데이터 저장(&S)"), self)
        template_action.setShortcut("Ctrl+S")
        template_action.triggered.connect(self._save_data_workbook)
        file_menu.addAction(template_action)
        file_menu.addSeparator()
        export_action = QAction(tr("통합 Excel 저장(&E)"), self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._export_all_regions_excel)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        exit_action = QAction(tr("종료(&X)"), self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(exit_action)

        region_menu = menubar.addMenu(tr("지역(&R)"))
        add_action = QAction(tr("지역 추가(&A)"), self)
        add_action.setShortcut("Ctrl+T")
        add_action.triggered.connect(self._add_region)
        region_menu.addAction(add_action)
        dash_action = QAction(tr("지역 종합 분석(&D)"), self)
        dash_action.setShortcut("Ctrl+D")
        dash_action.triggered.connect(self._open_dashboard)
        region_menu.addAction(dash_action)

        # 언어 — 필요 시 확인을 받은 뒤 저장하고, 이 창을 그대로 새 언어로 재구성한다
        # (프로세스 재시작 없음).
        lang_menu = menubar.addMenu(tr("언어(&L)"))
        group = QActionGroup(self)
        group.setExclusive(True)
        self._lang_actions: dict = {}
        for code, label in ((LANG_KO, tr("한국어(&K)")), (LANG_EN, tr("영어(&E)"))):
            action = QAction(label, self, checkable=True)
            action.setChecked(get_language() == code)
            action.triggered.connect(lambda _c=False, c=code: self._change_language(c))
            group.addAction(action)
            lang_menu.addAction(action)
            self._lang_actions[code] = action

        help_menu = menubar.addMenu(tr("도움말(&H)"))
        about_action = QAction(tr("정보(&A)"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _change_language(self, code: str) -> None:
        """언어를 바꾼다 — 프로세스 재시작 없이 이 창을 그 자리에서 새 언어로 다시 구성한다.

        (과거에는 exe 를 통째로 재실행했는데, frozen 빌드에서 두 인스턴스가
        PyInstaller onefile 압축 해제 폴더를 공유하다 구 인스턴스가 먼저 종료되며
        그 폴더를 정리해 버려 새 인스턴스가 `matplotlib` 등을 임포트하던 중
        `ImportError: cannot import name 'ft2font' ...` 로 죽는 문제가 있었다.
        같은 프로세스 안에서 창만 다시 구성하면 이 문제 자체가 발생하지 않는다.)
        """
        if code == get_language():
            return

        if self._regions:
            answer = QMessageBox.question(
                self, tr("언어 변경"),
                tr("언어를 변경하면 입력한 지역과 계산 결과가 모두 사라집니다.\n계속할까요?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                self._lang_actions[get_language()].setChecked(True)   # 선택 되돌리기
                return

        save_language(code)
        set_language(code)
        self._apply_language_change()

    def _apply_language_change(self) -> None:
        """현재 창을 유지한 채 전체 UI를 새 언어로 즉시 다시 구성한다."""
        setup_application_fonts(QApplication.instance())
        set_plot_font_scale(ui_scale())
        self._teardown_regions()
        self._carbon2.close()
        self._carbon2.deleteLater()
        self._carbon2 = Carbon2MainWindow()
        self._build_ui()

    def _build_statusbar(self) -> None:
        """상태바 문구를 현재 언어로 채운다.

        ``self.statusBar()`` 는 이미 있으면 기존 객체를 그대로 반환하므로
        (언어 변경으로 인한 재구성 시) 새로 만들지 않고 라벨 문구만 갱신한다
        — QMainWindow 가 소유한 상태바 객체를 교체할 때의 소유권 문제를 피한다.
        """
        bar = self.statusBar()
        if getattr(self, "_status_label", None) is not None:
            self._status_label.setText(tr("‘+ 지역 추가’로 지역을 추가하세요."))
            self._version_label.setText(tr("ForeCarb v{version}").format(version=__version__))
            return
        self._status_label = QLabel(tr("‘+ 지역 추가’로 지역을 추가하세요."))
        bar.addWidget(self._status_label, 1)
        self._version_label = QLabel(tr("ForeCarb v{version}").format(version=__version__))
        self._version_label.setStyleSheet("color: #777;")
        bar.addPermanentWidget(self._version_label)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            tr("ForeCarb"),
            tr("<b>ForeCarb (통합 Ver. {version})</b><br><br>").format(version=__version__)
            + tr("지역(권역)별로 탭을 동적으로 추가해 각 지역의 "
                 "<b>탄소저장량 추정 + 수종별 기여도</b>를 독립적으로 다룹니다.<br>")
            + tr("&nbsp;&nbsp;· [+ 지역 추가] — 지역명/면적/대상지 유형/위치(선택) 입력 → 지역 탭 생성<br>")
            + tr("&nbsp;&nbsp;· [지역 종합 분석] — 지역별 총 탄소저장량 비교 대시보드<br><br>")
            + tr("<i>국내·국외 통합 기여도 모듈은 현재 화면에서 비표시(코드·수식은 "
                 "보존).</i><br><br>")
            + tr("데이터 출처: <i>상대생장식 자료_최종본.xlsx</i> 「기초 DB 자료」 시트"),
        )

    def closeEvent(self, event) -> None:
        """창을 닫을 때 모든 지역 인스턴스와 보존된 Carbon2 인스턴스를 정리."""
        try:
            for r in self._regions:
                r["window"].close()
            self._carbon2.close()
        finally:
            super().closeEvent(event)
