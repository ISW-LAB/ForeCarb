# SPDX-License-Identifier: MIT
"""선택 개체의 현재 연도 특성을 보여주는 작은 상세창."""
from __future__ import annotations

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..i18n import species_name, tr
from ..ui_scale import px
from .inspection import InstanceInspection


def _profile_pixmap(info: InstanceInspection) -> QPixmap:
    """외부 사진 대신 현재 render profile을 설명하는 수형 예시 그림을 만든다."""
    pixmap = QPixmap(px(190), px(230))
    pixmap.fill(QColor("#EEF3F0"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    w, h = pixmap.width(), pixmap.height()
    painter.setPen(QPen(QColor("#8AA07E"), 2))
    painter.drawLine(px(16), h - px(24), w - px(16), h - px(24))
    crown = QColor(info.profile_color)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#76543A"))
    if info.kind == "tree":
        painter.drawRoundedRect(w // 2 - px(8), h // 2, px(16), h // 2 - px(24), 4, 4)
    else:
        for offset in (-px(18), 0, px(18)):
            painter.drawRoundedRect(w // 2 + offset - px(3), h // 2 + px(35), px(6), px(70), 3, 3)
    painter.setBrush(crown)
    shape = info.profile_shape
    if shape in ("layered_conifer", "pyramid"):
        for i in range(3):
            top = px(24 + i * 42)
            half = px(34 + i * 12)
            painter.drawPolygon(
                QPoint(w // 2, top), QPoint(w // 2 - half, top + px(75)),
                QPoint(w // 2 + half, top + px(75)),
            )
    elif shape == "shrub_upright":
        painter.drawEllipse(w // 2 - px(42), px(28), px(84), px(155))
    elif shape == "shrub_spreading":
        painter.drawEllipse(px(18), px(88), w - px(36), px(90))
    else:
        painter.drawEllipse(px(25), px(35), w - px(50), px(135 if info.kind == "tree" else 125))
        if shape in ("open_oval", "spreading", "shrub_multistem"):
            painter.drawEllipse(px(10), px(82), px(85), px(90))
            painter.drawEllipse(w - px(95), px(76), px(85), px(94))
    painter.end()
    return pixmap


class VegetationDetailDialog(QDialog):
    def __init__(self, info: InstanceInspection, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("{species} · {year}년 개체 정보")
                            .format(species=species_name(info.species), year=info.year))
        self.setModal(False)
        self.setMinimumWidth(px(980))
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        image = QLabel()
        image.setPixmap(_profile_pixmap(info))
        image.setAlignment(Qt.AlignCenter)
        image.setToolTip(tr("현재 3D render profile을 단순화한 수형 예시이며 실제 수종 사진이 아닙니다."))
        body.addWidget(image)

        form = QFormLayout()
        kind_label = tr("교목") if info.kind == "tree" else tr("관목")
        diameter_name = "DBH" if info.kind == "tree" else "RCD"
        rows = (
            (tr("수종"), species_name(info.species)), (tr("구분"), kind_label),
            (tr("경과 연도"), tr("{year}년").format(year=info.year)),
            (tr("같은 입력 그룹 수량"),
             tr("{n:,}주").format(n=info.group_quantity)),
            (info.predictor_label or tr("현재 {name}").format(name=diameter_name),
             f"{info.predictor_value:,.2f}"),
            (tr("현재 개체 탄소저장량"),
             tr("{carbon:,.4f} kgC/주").format(carbon=info.carbon_kgc)),
            (tr("상대생장식 계수"), info.formula or f"a={info.a:g} · b={info.b:g} · CF={info.cf:g}"),
            (tr("연간 직경생장량"),
             info.scenario_note or tr("1~10년 {y10:g} · 11~20년 {y20:g} · 21~30년 {y21:g} cm/yr")
             .format(y10=info.growth_y10, y20=info.growth_y20, y21=info.growth_y21)),
            (tr("지역 내 위치"), f"X {info.x_m:,.2f} m · Y {info.y_m:,.2f} m"),
            (tr("표현 줄기 직경 (시각화용)"), f"{info.rendered_trunk_diameter_m:,.3f} m"),
            (tr("표현 수고 (시각화용)"), f"{info.rendered_height_m:,.2f} m"),
            (tr("표현 수관 폭 (시각화용)"), f"{info.crown_width_m:,.2f} m"),
            (tr("표현 수관 길이 (시각화용)"), f"{info.crown_length_m:,.2f} m"),
            (tr("표현 풍성함 (시각화용)"), f"{info.visual_development * 100:,.0f}%"),
            (tr("데이터 구분"), info.scenario_note or tr("DBH/RCD·탄소: 상대생장식 라이브러리 / 수고·수관·풍성함: 시각화용 설정값")),
        )
        for label, value in rows:
            field = QLabel(value); field.setWordWrap(True); field.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label, field)
        body.addLayout(form, 1)
        root.addLayout(body)
        note = QLabel(tr("왼쪽 그림과 모든 '표현' 값은 3D 시각화용이며 탄소 계산에는 영향을 주지 않습니다."))
        note.setWordWrap(True); note.setStyleSheet("color:#6B7780; padding:4px;")
        root.addWidget(note)
        close_btn = QPushButton(tr("닫기")); close_btn.clicked.connect(self.close)
        root.addWidget(close_btn, alignment=Qt.AlignRight)
