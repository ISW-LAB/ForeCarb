# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
애플리케이션 전역 폰트 설정 (화면 크기 반응형).

QApplication 의 기본 폰트를 일괄 변경하여 모든 위젯(콤보, 스피너, 라벨,
테이블, 메뉴 등) 의 글자 크기를 한 번에 조정한다.

설계 기준 해상도(1920×1080)에서는 ``typography.BODY_PT`` 그대로 표시되고,
더 작은 모니터에서는 ui_scale 배수만큼 비례 축소하여 화면을 넘지 않게 한다.

matplotlib 폰트는 plotting.set_plot_font_scale 로 동일 스케일을 적용.
"""
from __future__ import annotations

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from .ui_scale import ui_scale
from .i18n import get_language
from .qt_locale import apply_dialog_font, install_qt_translator
from .typography import BODY_PT, font_family, scaled_point_size


def setup_application_fonts(app: QApplication,
                            scale: float | None = None,
                            base_pt: int = BODY_PT) -> None:
    """애플리케이션 기본 폰트를 화면 스케일에 맞춰 설정한다."""
    if scale is None:
        scale = ui_scale(app)

    # Start from a fixed design size: language changes must not grow the font.
    f = QFont(font_family(get_language()))
    f.setPointSize(scaled_point_size(base_pt, scale))
    app.setFont(f)
    apply_dialog_font(app)
    install_qt_translator(app, get_language())
