# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
애플리케이션 전역 테마(QSS) 정의.

세종수목원 탄소저장량 모듈의 통일된 UI/UX 를 위해 색상·여백·모서리 둥글기를
한 곳에서 관리한다. 픽셀 단위 여백/둥글기는 화면 스케일(ui_scale)에 비례시켜
작은 화면에서도 균형 잡힌 비율을 유지한다.

색상 팔레트 (수목원/탄소 테마 — 그린 계열)
    ACCENT       #2E8B57  주 강조 (버튼/선택)
    ACCENT_DARK  #246B43  강조 hover/pressed
    ACCENT_SOFT  #E8F4EC  연한 강조 배경
    BG           #F4F6F8  창 배경
    SURFACE      #FFFFFF  카드/입력 표면
    BORDER       #D8DEE4  일반 테두리
    TEXT         #232A2E  기본 텍스트
    MUTED        #6B7780  보조 텍스트
"""
from __future__ import annotations

from PyQt5.QtWidgets import QApplication

from .ui_scale import ui_scale
from .typography import BODY_PT, HEADING_PT, scaled_point_size


# ─────────────────────────── 색상 팔레트 ───────────────────────────
ACCENT = "#2E8B57"
ACCENT_DARK = "#246B43"
ACCENT_SOFT = "#E8F4EC"
DANGER = "#D9534F"
DANGER_DARK = "#B5413D"
BG = "#F4F6F8"
SURFACE = "#FFFFFF"
BORDER = "#D8DEE4"
TEXT = "#232A2E"
MUTED = "#6B7780"
HEADER_BG = "#EEF2F5"


def build_stylesheet(scale: float = 1.0) -> str:
    """현재 스케일을 반영한 전역 QSS 문자열 생성."""
    def s(v: float) -> int:           # 스케일 적용 픽셀
        return max(1, round(v * scale))

    radius = s(8)
    radius_sm = s(6)
    # 표 글자는 본문보다 한 단계 크게 — 수치를 읽는 곳이라 가독성이 우선이다.
    table_pt = scaled_point_size(HEADING_PT, scale)
    pad_v = s(6)
    pad_h = s(12)

    return f"""
    /* ===== 전역 ===== */
    QMainWindow, QDialog {{ background: {BG}; }}
    QWidget {{ color: {TEXT}; }}
    QMessageBox QLabel {{ font-size: {scaled_point_size(BODY_PT, scale)}pt; }}
    QToolTip {{
        background: {TEXT}; color: #FFFFFF; border: none;
        padding: {s(4)}px {s(8)}px; border-radius: {radius_sm}px;
    }}

    /* ===== 그룹 박스(카드) ===== */
    QGroupBox {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
        margin-top: {s(16)}px;
        padding: {s(12)}px {s(10)}px {s(10)}px {s(10)}px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {s(12)}px;
        padding: 0 {s(6)}px;
        color: {ACCENT_DARK};
    }}

    /* ===== 입력 위젯 ===== */
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
        background: {SURFACE};
        border: 1px solid #C4CCD3;
        border-radius: {radius_sm}px;
        padding: {s(5)}px {s(8)}px;
        min-height: {s(20)}px;
        selection-background-color: {ACCENT};
        selection-color: #FFFFFF;
    }}
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border: 1px solid #9FB0BC; }}
    QComboBox::drop-down {{ border: none; width: {s(22)}px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT_SOFT};
        selection-color: {TEXT};
        outline: none;
    }}

    /* ===== 일반 버튼 ===== */
    QPushButton {{
        background: {SURFACE};
        border: 1px solid #C4CCD3;
        border-radius: {radius_sm}px;
        padding: {pad_v}px {pad_h}px;
    }}
    QPushButton:hover {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; }}
    QPushButton:pressed {{ background: #DCEDE2; }}

    /* 강조 버튼(추가/계산 등) - 객체 이름으로 지정 */
    QPushButton#accentButton {{
        background: {ACCENT}; color: #FFFFFF; border: none; font-weight: bold;
        padding: {s(8)}px {s(14)}px; border-radius: {radius_sm}px;
    }}
    QPushButton#accentButton:hover {{ background: {ACCENT_DARK}; }}
    QPushButton#accentButton:pressed {{ background: #1E5836; }}

    /* 계산 버튼(가장 큰 주 액션) */
    QPushButton#calcButton {{
        background: {ACCENT}; color: #FFFFFF; border: none; font-weight: bold;
        padding: {s(12)}px; border-radius: {radius}px;
    }}
    QPushButton#calcButton:hover {{ background: {ACCENT_DARK}; }}
    QPushButton#calcButton:pressed {{ background: #1E5836; }}

    /* 삭제 버튼 */
    QPushButton#deleteButton {{
        background: {DANGER}; color: #FFFFFF; border: none;
        padding: {s(4)}px; border-radius: {radius_sm}px;
    }}
    QPushButton#deleteButton:hover {{ background: {DANGER_DARK}; }}

    /* ===== 탭 ===== */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: {radius}px;
        top: -1px; background: {SURFACE};
    }}
    QTabBar::tab {{
        background: #E7ECF0; color: {MUTED};
        padding: {s(8)}px {s(16)}px;
        border-top-left-radius: {radius_sm}px;
        border-top-right-radius: {radius_sm}px;
        margin-right: {s(2)}px;
    }}
    QTabBar::tab:selected {{ background: {ACCENT}; color: #FFFFFF; }}
    QTabBar::tab:!selected:hover {{ background: #D7DEE4; }}

    /* ===== 테이블 ===== */
    QTableWidget, QHeaderView::section {{
        /* 스타일시트가 걸린 위젯은 앱 기본 폰트를 잃고 스타일 기본값(작은 글씨)으로
           돌아갈 수 있다. 모든 표가 같은 크기로 보이도록 여기서 못 박는다.
           (QSS 는 위젯의 setFont 보다 우선하므로 표 글자 크기는 이 값이 기준이다.) */
        font-size: {table_pt}pt;
    }}
    QTableWidget {{
        background: {SURFACE};
        gridline-color: #E6EAEE;
        border: 1px solid {BORDER};
        border-radius: {radius_sm}px;
        alternate-background-color: #F7FAF8;
    }}
    QTableWidget::item {{ padding: {s(3)}px; }}
    QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
    QHeaderView::section {{
        background: {HEADER_BG}; color: #333;
        padding: {s(6)}px; border: none;
        border-right: 1px solid {BORDER};
        border-bottom: 1px solid {BORDER};
        font-weight: bold;
    }}

    /* ===== 스크롤 영역 / 스크롤바 ===== */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent; width: {s(12)}px; margin: {s(2)}px;
    }}
    QScrollBar::handle:vertical {{
        background: #C4CCD3; border-radius: {s(6)}px; min-height: {s(28)}px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #9FB0BC; }}
    QScrollBar:horizontal {{
        background: transparent; height: {s(12)}px; margin: {s(2)}px;
    }}
    QScrollBar::handle:horizontal {{
        background: #C4CCD3; border-radius: {s(6)}px; min-width: {s(28)}px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: #9FB0BC; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ===== 메뉴/상태바 ===== */
    QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
    QMenuBar::item:selected {{ background: {ACCENT_SOFT}; }}
    QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
    QStatusBar {{ background: {HEADER_BG}; color: {MUTED}; }}
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:horizontal {{ width: {s(8)}px; }}
    """


def apply_theme(app: QApplication, scale: float | None = None) -> None:
    """애플리케이션 전역 스타일시트 적용."""
    if scale is None:
        scale = ui_scale(app)
    app.setStyleSheet(build_stylesheet(scale))
