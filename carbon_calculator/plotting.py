# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
matplotlib 캔버스 래퍼 (PyQt5 임베드).
"""
from __future__ import annotations

import warnings

import matplotlib
matplotlib.use("Qt5Agg")

# 캔버스를 매우 좁게(스플리터로) 끌면 constrained_layout 이 "axes collapsed to zero"
# 경고를 매 draw 마다 출력한다. 그림은 정상적으로 그려지므로(무해) 콘솔 스팸만 억제한다.
warnings.filterwarnings("ignore", message=".*constrained_layout not applied.*")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from PyQt5.QtWidgets import QSizePolicy  # noqa: E402

from .i18n import get_language, species_name, tr  # noqa: E402
from .typography import (  # noqa: E402
    PLOT_ANNOTATION_PT, PLOT_BODY_PT, PLOT_LABEL_PT, PLOT_LEGEND_PT,
    PLOT_MESSAGE_PT, PLOT_TICK_PT, PLOT_TITLE_PT, font_family, scaled_point_size,
)


# 기준 해상도(1920×1080, scale=1.0)에서의 matplotlib 폰트 크기.
# set_plot_font_scale 로 화면 스케일을 곱해 작은 모니터에서 비례 축소한다.
_BASE_PLOT_FONTS = {
    "font.size": PLOT_BODY_PT,
    "axes.titlesize": PLOT_TITLE_PT,
    "axes.labelsize": PLOT_LABEL_PT,
    "xtick.labelsize": PLOT_TICK_PT,
    "ytick.labelsize": PLOT_TICK_PT,
    "legend.fontsize": PLOT_LEGEND_PT,
}

# 인라인 fontsize(파이/메시지/툴팁)에도 적용할 현재 스케일.
_PLOT_SCALE = 1.0


def set_plot_font_scale(scale: float = 1.0) -> None:
    """그래프 한글 폰트 + 글자 크기를 화면 스케일에 맞춰 설정. 실패 시 기본 폰트 유지."""
    global _PLOT_SCALE
    _PLOT_SCALE = scale
    try:
        plt.rcParams["font.family"] = [font_family(get_language()), "Malgun Gothic", "DejaVu Sans"]
        plt.rcParams["mathtext.fontset"] = "dejavusans"
        plt.rcParams["axes.unicode_minus"] = False
        for key, base in _BASE_PLOT_FONTS.items():
            plt.rcParams[key] = scaled_point_size(base, scale)
    except Exception:
        pass


def _fs(base: float) -> int:
    """인라인 fontsize 를 현재 스케일로 변환."""
    return scaled_point_size(base, _PLOT_SCALE)


# 기본(scale=1.0) 설정 — run 진입점에서 set_plot_font_scale 로 재설정됨.
set_plot_font_scale(1.0)


class MatplotlibCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width: float = 5, height: float = 2, dpi: int = 100):
        # constrained_layout: 폰트·라벨 크기 변화에 자동 적응 (tight_layout 보다 견고).
        # tight_layout 과 동시 사용 시 UserWarning 발생하므로 layout 만 사용한다.
        self.figure = Figure(figsize=(width, height), dpi=dpi, layout="constrained")
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)

        # 반응형: 캔버스가 창 크기에 따라 자유롭게 늘어나고 줄어들도록.
        # (기본 FigureCanvas 는 figsize 기반의 큰 최소 크기를 가져 작은 화면에서 넘침)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 90)

        # 호버 툴팁 상태
        self._hover_cid: int | None = None
        self._hover_ann = None
        # 다중 라인 지원: (line_artist, xdata, ydata, name) 튜플 리스트
        self._hover_specs: list = []
        self._hover_xlabel: str = "x"
        self._hover_ylabel: str = "y"

    # 설계 기준 패널 크기(px). 이보다 좁거나 낮은 패널에서는 축 글자를 비례 축소해
    # 그림 영역을 지킨다 (절대 확대하지는 않는다).
    _PANEL_REF_W = 900.0
    _PANEL_REF_H = 430.0
    _PANEL_MIN_SCALE = 0.72

    def _panel_scale(self) -> float:
        """캔버스가 설계 기준보다 작으면 1 미만의 배수를 돌려준다."""
        try:
            w, h = self.figure.bbox.width, self.figure.bbox.height
        except Exception:  # noqa: BLE001
            return 1.0
        if w <= 0 or h <= 0:
            return 1.0
        fit = min(w / self._PANEL_REF_W, h / self._PANEL_REF_H)
        return max(self._PANEL_MIN_SCALE, min(1.0, fit))

    def _fit_axes_text(self) -> None:
        """좁은 패널에서 축 제목·눈금·범례가 그림 영역을 잠식하지 않게 맞춘다.

        글자를 키우면 큰 창·내보낸 이미지에서는 잘 읽히지만, 앱 안의 낮은 그래프
        패널에서는 축 라벨이 그림을 밀어내고 잘리기까지 한다. 캔버스 실제 크기에
        맞춰 축 글자만 비례 축소한다(데이터 라벨·제목 크기 기준은 그대로).
        """
        scale = self._panel_scale()
        if scale >= 0.999:
            return
        try:
            ax = self.ax
            label_pt = scaled_point_size(PLOT_LABEL_PT, _PLOT_SCALE * scale)
            ax.xaxis.label.set_fontsize(label_pt)
            ax.yaxis.label.set_fontsize(label_pt)
            ax.title.set_fontsize(scaled_point_size(PLOT_TITLE_PT, _PLOT_SCALE * scale))
            ax.tick_params(axis="both",
                           labelsize=scaled_point_size(PLOT_TICK_PT, _PLOT_SCALE * scale))
            legend = ax.get_legend()
            if legend is not None:
                legend_pt = scaled_point_size(PLOT_LEGEND_PT, _PLOT_SCALE * scale)
                for text in legend.get_texts():
                    text.set_fontsize(legend_pt)
                if legend.get_title() is not None:
                    legend.get_title().set_fontsize(legend_pt)
        except Exception:  # noqa: BLE001 — 조정 실패 시 기본 크기 유지
            pass
        self._fit_axis_labels()

    def _fit_axis_labels(self) -> None:
        """긴 축 제목이 캔버스를 넘치면 들어갈 크기까지 줄인다.

        'Area-normalized carbon density (kg C/m²)' 처럼 긴 y축 제목은 낮은 패널에서
        세로로 잘린다. 비례 축소만으로는 모자라므로 실제 길이를 재서 맞춘다.
        """
        try:
            self.figure.draw_without_rendering()
            limits = ((self.ax.yaxis.label, self.figure.bbox.height),
                      (self.ax.xaxis.label, self.figure.bbox.width))
            changed = False
            for label, room in limits:
                if not label.get_text() or room <= 0:
                    continue
                box = label.get_window_extent()
                length = box.height if label is self.ax.yaxis.label else box.width
                if length <= room * 0.98:
                    continue
                floor = _fs(PLOT_ANNOTATION_PT)
                shrunk = max(floor, label.get_fontsize() * (room * 0.95) / length)
                label.set_fontsize(shrunk)
                changed = True
            if changed:
                self.figure.draw_without_rendering()
        except Exception:  # noqa: BLE001 — 측정 실패 시 원래 크기 유지
            pass

    def resizeEvent(self, event):   # noqa: N802 — Qt 시그니처
        super().resizeEvent(event)
        self._fit_axes_text()

    def _teardown_hover(self) -> None:
        if self._hover_cid is not None:
            try:
                self.mpl_disconnect(self._hover_cid)
            except Exception:
                pass
            self._hover_cid = None
        self._hover_ann = None
        self._hover_specs = []

    def clear(self) -> None:
        self._teardown_hover()
        self.ax.clear()
        self.draw_idle()

    def _set_title(self, title: str, **kwargs) -> None:
        self.ax.set_title(title, **kwargs)

    def _fit_title(self) -> None:
        """제목이 캔버스를 벗어나면 들어갈 크기까지 줄인다.

        범례를 축 바깥에 두면 축이 좁아져, 가운데 정렬된 제목이 캔버스 왼쪽으로
        삐져나갈 수 있다. 글자를 키운 뒤 특히 두드러지므로 범례까지 배치한 뒤
        실제 폭을 재서 맞춘다.
        """
        text = self.ax.title
        if not text.get_text():
            return
        try:
            self.figure.draw_without_rendering()
            fig_w = self.figure.bbox.width
            bb = text.get_window_extent()
            if bb.width <= 0 or fig_w <= 0:
                return
            cx = 0.5 * (bb.x0 + bb.x1)
            half_avail = min(cx, fig_w - cx) * 0.92   # 캔버스 가장자리 여유
            scale = half_avail / (bb.width / 2.0)
            if scale < 1.0:
                floor = _fs(PLOT_ANNOTATION_PT)
                text.set_fontsize(max(floor, text.get_fontsize() * scale))
        except Exception:  # noqa: BLE001 — 측정 실패 시 원래 크기 유지
            pass

    def plot_projection(self, years, carbon, title: str, ylabel: str | None = None,
                        xlabel: str | None = None) -> None:
        # 기본값을 import 시점에 굳히면 언어 설정 전 문자열이 박힌다 → 호출 시 해석.
        ylabel = tr("탄소저장량 (kgC)") if ylabel is None else ylabel
        xlabel = tr("경과 기간 (년)") if xlabel is None else xlabel
        self._teardown_hover()
        self.ax.clear()
        line, = self.ax.plot(
            years, carbon, marker="o", color="#2E8B57",
            linewidth=2.0, markersize=5, picker=False,
        )
        line.set_pickradius(6)
        self._set_title(title)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, alpha=0.4)
        self._install_hover([(line, list(years), list(carbon), "")], xlabel, ylabel)
        self._fit_axes_text()
        self._fit_title()
        self.draw_idle()

    def plot_multi_projection(self, series, title: str,
                              ylabel: str | None = None,
                              xlabel: str | None = None,
                              show_title: bool = True) -> None:
        """
        여러 추정 곡선을 한 그래프에 중첩 표시.

        series: [(label, years, carbon, is_total), ...]
          - is_total=True 인 곡선은 굵은 점선(강조색)으로 그려 "총합"을 시각 구분.
        show_title=False 면 축 제목을 그리지 않는다(호출측이 패널 위 라벨로 제목을 표시할 때).
        """
        # Resolve translated defaults at call time so the selected startup
        # language is reflected even though this module was imported earlier.
        ylabel = tr("탄소저장량 (kgC)") if ylabel is None else ylabel
        xlabel = tr("경과 기간 (년)") if xlabel is None else xlabel
        self._teardown_hover()
        self.ax.clear()
        if not series:
            self.show_message(tr("표시할 항목이 없습니다."))
            return

        color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
        specs: list = []
        ci = 0
        for label, years, carbon, is_total in series:
            if is_total:
                line, = self.ax.plot(
                    years, carbon, color="#C0392B", linewidth=2.6,
                    linestyle="--", marker="s", markersize=4, label=label, zorder=5,
                )
            else:
                color = color_cycle[ci % len(color_cycle)] if color_cycle else None
                ci += 1
                line, = self.ax.plot(
                    years, carbon, color=color, linewidth=1.8,
                    marker="o", markersize=3.5, label=label,
                )
            line.set_pickradius(6)
            specs.append((line, list(years), list(carbon), label))

        if show_title:
            self._set_title(title)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, alpha=0.4)
        # 범례는 그래프 내부를 침범하지 않도록 **축 바깥 오른쪽**에 배치 (constrained_layout 이
        # 가로 자리를 확보). 항목이 많으면 세로로 넘쳐 잘리므로 열 수를 늘려 옆으로 펼친다.
        ncol = 1 + (len(specs) - 1) // 10  # 한 열에 ~10개씩 → 16개 이상이면 2열+
        self.ax.legend(
            fontsize=_fs(PLOT_LEGEND_PT), loc="upper left", bbox_to_anchor=(1.01, 1.0),
            framealpha=0.95, borderaxespad=0.0, ncol=max(1, ncol),
        )
        self._install_hover(specs, xlabel, ylabel)
        self._fit_axes_text()
        self._fit_title()
        self.draw_idle()

    def plot_survival_projection(self, years, groups, ylabel: str | None = None,
                                 xlabel: str | None = None) -> None:
        """전량 생존(실선)과 생존률 반영(점선)을 같은 색으로 짝지어 그린다.

        groups: [(name, color, all_survive, with_survival), ...]
        """
        ylabel = tr("탄소저장량 (kgC)") if ylabel is None else ylabel
        xlabel = tr("경과 기간 (년)") if xlabel is None else xlabel
        self._teardown_hover()
        self.ax.clear()
        if not groups:
            self.show_message(tr("표시할 항목이 없습니다."))
            return
        from matplotlib.lines import Line2D
        specs: list = []
        handles: list = []
        for name, color, base, surv in groups:
            line, = self.ax.plot(years, base, color=color, linewidth=1.6, alpha=0.55)
            line.set_pickradius(6)
            specs.append((line, list(years), list(base), tr("{name} · 전량 생존").format(name=name)))
            line, = self.ax.plot(years, surv, color=color, linewidth=2.4, linestyle="--",
                                 marker="o", markersize=3.2)
            line.set_pickradius(6)
            specs.append((line, list(years), list(surv), tr("{name} · 생존률 반영").format(name=name)))
            handles.append(Line2D([], [], color=color, linewidth=2.4, label=name))
        # 범례는 '수종(색) 하나씩 + 선 모양 2개' 로 줄여 그래프 높이를 잠식하지 않게 한다.
        handles.append(Line2D([], [], color="#555555", linewidth=1.6, alpha=0.7,
                              label=tr("실선: 전량 생존")))
        handles.append(Line2D([], [], color="#555555", linewidth=2.4, linestyle="--",
                              label=tr("점선: 생존률 반영")))
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, alpha=0.4)
        self.ax.legend(
            handles=handles, fontsize=_fs(PLOT_LEGEND_PT), loc="upper left",
            bbox_to_anchor=(1.01, 1.0), framealpha=0.95, borderaxespad=0.0,
            ncol=1 + (len(handles) - 1) // 5,
        )
        self._install_hover(specs, xlabel, ylabel)
        self._fit_axes_text()
        self.draw_idle()

    def show_message(self, message: str) -> None:
        self._teardown_hover()
        self.ax.clear()
        self.ax.text(0.5, 0.5, message, ha="center", va="center",
                     transform=self.ax.transAxes, fontsize=_fs(PLOT_MESSAGE_PT), color="#777")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    # ----- 호버 툴팁 -----

    def _install_hover(self, specs: list, x_label: str, y_label: str) -> None:
        """라인(들) 위에 마우스 호버 시 (x, y) 라벨 표시 툴팁 설치.

        specs: [(line_artist, xdata, ydata, name), ...] — 여러 곡선을 지원.
        """
        if not specs:
            return
        ann = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="#FFFFE0", ec="#888", alpha=0.95),
            arrowprops=dict(arrowstyle="->", color="#888"),
            fontsize=_fs(PLOT_ANNOTATION_PT),
            # 모든 곡선(총합 곡선 zorder=5 포함)·마커 위에 항상 표시되도록 zorder 를 크게.
            zorder=100,
        )
        # 연결 화살표(arrow_patch)는 별도 zorder 를 가지므로 함께 올려 선 뒤에 가리지 않게 한다.
        if getattr(ann, "arrow_patch", None) is not None:
            ann.arrow_patch.set_zorder(100)
        # constrained_layout 이 호버 박스 크기에 반응해 축을 재배치하며 깜빡이는 것을 방지
        # (박스가 영역을 넘어도 레이아웃에 영향 주지 않음). 방향 뒤집기는 가독성용으로 별도 유지.
        ann.set_in_layout(False)
        ann.set_visible(False)
        self._hover_ann = ann
        self._hover_specs = list(specs)
        self._hover_xlabel = x_label
        self._hover_ylabel = y_label
        self._hover_cid = self.mpl_connect("motion_notify_event", self._on_hover_motion)

    def _on_hover_motion(self, event) -> None:
        ann = self._hover_ann
        specs = self._hover_specs
        if ann is None or not specs:
            return
        was_visible = ann.get_visible()
        if event.inaxes is not self.ax:
            if was_visible:
                ann.set_visible(False)
                self.draw_idle()
            return
        for line, xdata, ydata, name in specs:
            contains, info = line.contains(event)
            if contains and info.get("ind") is not None and len(info["ind"]) > 0:
                idx = int(info["ind"][0])
                x = xdata[idx]
                y = ydata[idx]
                ann.xy = (x, y)
                prefix = f"{name}\n" if name else ""
                ann.set_text(
                    f"{prefix}{self._hover_xlabel}: {x}\n{self._hover_ylabel}: {y:.4g}"
                )
                # 박스가 축 밖으로 나가 레이아웃이 재계산되며 깜빡이는 것을 막기 위해,
                # 실제 박스 크기를 측정해 우측/상단을 넘치면 좌측/하단으로 뒤집어 배치한다.
                self._place_annotation(ann, x, y)
                ann.set_visible(True)
                self.draw_idle()
                return
        if was_visible:
            ann.set_visible(False)
            self.draw_idle()

    def _renderer(self):
        """현재 렌더러(없거나 아직 그려지지 않았으면 None)."""
        try:
            return self.get_renderer()
        except Exception:
            return None

    def _place_annotation(self, ann, x: float, y: float, off: int = 16) -> None:
        """호버 박스를 측정해 그래프 영역을 넘치지 않도록 좌/우·상/하 방향을 정한다.

        텍스트 박스의 폭/높이는 위치(offset)와 무관하므로, 기준 위치에서 한 번 측정한 뒤
        점의 화면 좌표 + 오프셋 + 박스 크기가 축 경계를 넘으면 반대쪽으로 뒤집는다.
        렌더러를 얻지 못하면(최초 그리기 전) 위치 분율 0.5 기준으로 근사한다.
        """
        dx, dy, ha, va = off, off, "left", "bottom"
        renderer = self._renderer()
        measured = False
        # 보이지 않는 아티스트는 일부 matplotlib 버전에서 빈 extent 를 돌려주므로 먼저 표시.
        ann.set_visible(True)
        if renderer is not None:
            try:
                ann.set_position((off, off)); ann.set_ha("left"); ann.set_va("bottom")
                box = ann.get_window_extent(renderer)
                axbox = self.ax.get_window_extent(renderer)
                px, py = self.ax.transData.transform((x, y))
                if px + off + box.width > axbox.x1:   # 우측 넘침 → 왼쪽으로
                    dx, ha = -off, "right"
                if py + off + box.height > axbox.y1:  # 상단 넘침 → 아래로
                    dy, va = -off, "top"
                measured = True
            except Exception:
                measured = False
        if not measured:
            xmin, xmax = self.ax.get_xlim()
            ymin, ymax = self.ax.get_ylim()
            xfrac = (x - xmin) / ((xmax - xmin) or 1.0)
            yfrac = (y - ymin) / ((ymax - ymin) or 1.0)
            dx, ha = (-off, "right") if xfrac > 0.5 else (off, "left")
            dy, va = (-off, "top") if yfrac > 0.5 else (off, "bottom")
        ann.set_position((dx, dy))
        ann.set_ha(ha)
        ann.set_va(va)

    def plot_pie(self, labels: list[str], values: list[float],
                 title: str | None = None, top_n: int = 5,
                 label_fs: float = PLOT_LEGEND_PT, title_fs: float = PLOT_TITLE_PT,
                 show_title: bool = True) -> None:
        """
        Carbon2 의 plotCarbonPieChart 와 동등.
        - 수종별 합산
        - 내림차순 정렬, 상위 top_n + "기타" 그룹화
        - 라벨에 "수종 (퍼센트%)\\n값 kgC" 표시

        label_fs / title_fs: 작은 1/3 패널(Carbon1 기여도)에서 더 작은 글꼴을 쓰기 위한 인자.
        show_title=False 면 차트 제목을 그리지 않는다(호출측이 패널 위 라벨로 제목을 표시할 때).
        """
        title = tr("수종별 탄소저장량 기여도") if title is None else title
        self._teardown_hover()
        self.ax.clear()

        agg: dict[str, float] = {}
        for k, v in zip(labels, values):
            agg[k] = agg.get(k, 0.0) + v
        if not agg or sum(agg.values()) <= 0:
            self.show_message(tr("표시할 데이터가 없습니다."))
            return

        sorted_items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        if len(sorted_items) > top_n:
            major = sorted_items[:top_n]
            others = sum(v for _, v in sorted_items[top_n:])
            plot_labels = [k for k, _ in major] + [tr("기타")]
            plot_values = [v for _, v in major] + [others]
        else:
            plot_labels = [k for k, _ in sorted_items]
            plot_values = [v for _, v in sorted_items]

        total = sum(plot_values)
        full_labels = [
            f"{lbl} ({val / total * 100:.1f}%)\n{val:.1f} kgC"
            for lbl, val in zip(plot_labels, plot_values)
        ]

        _wedges, texts = self.ax.pie(
            plot_values, labels=full_labels,
            startangle=90, counterclock=False,
            radius=0.72,
            wedgeprops={"linewidth": 0.6, "edgecolor": "white"},
            textprops={"fontsize": _fs(label_fs)},
        )
        # 얇은 조각들은 라벨이 같은 방향에 몰려 겹친다 → 반지름 방향으로 번갈아 밀어낸다.
        thin = [i for i, v in enumerate(plot_values) if total > 0 and v / total < 0.08]
        for rank, i in enumerate(thin):
            x, y = texts[i].get_position()
            push = 1.14 + 0.32 * (rank % 2)
            texts[i].set_position((x * push, y * push))
        # 조각 바깥 라벨(영문판의 긴 학명)이 캔버스 밖으로 잘리지 않도록,
        # 실제 렌더된 글자 크기를 재서 축 범위를 넓힌다 → 원이 그만큼 작아진다.
        if not self._fit_pie_labels(texts):
            self._pie_with_legend(plot_values, plot_labels, label_fs)
        if show_title:
            self._set_title(title, fontsize=_fs(title_fs), fontweight="bold")
        self._fit_axes_text()
        self._fit_title()
        self.draw_idle()

    # 조각 바깥 라벨을 유지할 수 있는 최대 확장 배수. 이보다 더 넓혀야 하면
    # 원이 알아볼 수 없이 작아지므로 범례 배치로 전환한다.
    _PIE_MAX_HALF = 2.3

    def _fit_pie_labels(self, texts) -> bool:
        """파이 라벨이 모두 들어가도록 축 범위를 확장한다. 불가능하면 False.

        라벨 폭은 패널 너비·글자 크기에 따라 달라지므로 고정 여백으로는 넓은 창과
        좁은 1/3 패널을 동시에 만족시킬 수 없다. 한 번 렌더해 실제 글자 상자를
        데이터 좌표로 환산한 뒤 그 범위를 축에 반영한다(넓힌 만큼 원이 작아진다).
        """
        if not texts:
            return True
        try:
            self.figure.draw_without_rendering()
            inv = self.ax.transData.inverted()
            half_w = half_h = 1.0
            for t in texts:
                (x0, y0), (x1, y1) = inv.transform(t.get_window_extent().get_points())
                half_w = max(half_w, abs(x0), abs(x1))
                half_h = max(half_h, abs(y0), abs(y1))
            if half_w > self._PIE_MAX_HALF or half_h > self._PIE_MAX_HALF:
                return False
            pad = 0.06
            self.ax.set_xlim(-(half_w + pad), half_w + pad)
            self.ax.set_ylim(-(half_h + pad), half_h + pad)
        except Exception:  # noqa: BLE001 — 측정 실패 시 기본 범위 유지
            pass
        return True

    def _pie_with_legend(self, plot_values, plot_labels, label_fs) -> None:
        """좁은 패널용 파이 — 조각 옆 라벨 대신 오른쪽 범례로 수종을 표시한다.

        영문판의 긴 학명은 좁은 기여도 패널에서 조각 바깥에 들어가지 않아 서로
        겹치고 잘린다. 이때는 비율을 조각 위에 쓰고 이름만 범례로 빼서, 원과 글자
        모두 읽을 수 있는 크기를 유지한다(수치 상세는 옆 표에서 확인).
        """
        self.ax.clear()
        total = sum(plot_values)

        def pct(value: float) -> str:
            # 얇은 조각은 숫자가 겹치므로 비우고 범례로만 표시한다.
            return f"{value:.0f}%" if total > 0 and value >= 7.0 else ""

        wedges, _labels, pcts = self.ax.pie(
            plot_values, startangle=90, counterclock=False,
            autopct=pct, pctdistance=0.68,
            wedgeprops={"linewidth": 0.6, "edgecolor": "white"},
            textprops={"fontsize": _fs(label_fs)},
        )
        for t in pcts:
            t.set_color("white")
            t.set_fontweight("bold")
        # 비율은 조각 위에 있으므로 범례는 이름만 — 좁은 패널에서 원이 커진다.
        self.ax.legend(
            wedges, plot_labels, loc="center left", bbox_to_anchor=(1.0, 0.5),
            fontsize=_fs(label_fs), framealpha=0.95, labelspacing=0.5,
            handlelength=1.2, borderaxespad=0.2,
        )

    def plot_region_bars(self, names: list[str], tree_vals: list[float],
                         shrub_vals: list[float],
                         ylabel: str | None = None, show_title: bool = True,
                         title: str | None = None) -> None:
        """지역별 **총** 탄소저장량 비교 막대 차트.

        각 지역(=막대)을 **고유 색상 + 해치 패턴**(/, ., x …)으로 자동 구분하고, 범례를
        **축 바깥 오른쪽**에 두되 **지역명**을 표시한다(교목/관목은 범례로 표시하지 않음).
        교목/관목 세부 내역은 동일 다이얼로그의 표에서 확인.
        """
        ylabel = tr("탄소저장량 (kgC)") if ylabel is None else ylabel
        title = tr("지역별 탄소저장량 비교") if title is None else title
        self._teardown_hover()
        self.ax.clear()
        if not names:
            self.show_message(tr("비교할 지역이 없습니다."))
            return

        totals = [t + s for t, s in zip(tree_vals, shrub_vals)]
        x = list(range(len(names)))
        cmap = plt.get_cmap("tab10")  # 10색
        # 색상만으로 부족할 때(흑백 인쇄·유사색)도 구분되도록 지역마다 해치 패턴을 함께 배정.
        # 모든 막대가 해치를 갖도록 빈 패턴은 제외하고, 색상 주기(10)와 서로소인 9개를 써서
        # 색·해치 조합이 늦게(최소공배수 90) 반복되게 한다 → 10개 초과 지역도 구분 유지.
        hatches = ["//", "\\\\", "..", "xx", "++", "oo", "--", "**", "||"]  # 9개 (10과 서로소)

        for i, (xi, tot, name) in enumerate(zip(x, totals, names)):
            self.ax.bar(
                xi, tot, width=0.7,
                color=cmap(i % 10), hatch=hatches[i % len(hatches)],
                edgecolor="white", linewidth=0.8, label=name,
            )

        top = max(totals) if totals else 0.0
        for xi, tot in zip(x, totals):
            self.ax.text(xi, tot + (top * 0.01 if top else 0.0), f"{tot:,.1f}",
                         ha="center", va="bottom", fontsize=_fs(PLOT_ANNOTATION_PT),
                         fontweight="bold")

        # 지역 식별은 우측 범례가 담당 → x축 라벨 중복 제거(긴 지역명 겹침 방지).
        self.ax.set_xticks([])
        self.ax.set_ylabel(ylabel)
        # 막대 위 총합 라벨 공간 확보 (전부 0이면 라벨이 0 위치에 겹치지 않도록 최소 범위 지정)
        self.ax.set_ylim(0, top * 1.15 if top > 0 else 1.0)
        if show_title:
            self._set_title(title, fontweight="bold")
        # 범례: 지역명, 축 바깥 오른쪽. 지역이 많으면 열 수를 늘려 세로 넘침 방지.
        ncol = 1 + (len(names) - 1) // 12
        self.ax.legend(
            title=tr("지역"), loc="upper left", bbox_to_anchor=(1.01, 1.0),
            fontsize=_fs(PLOT_LEGEND_PT), framealpha=0.95, borderaxespad=0.0, ncol=max(1, ncol),
        )
        self.ax.grid(True, axis="y", alpha=0.3)
        self._fit_axes_text()
        self._fit_title()
        self.draw_idle()

    def plot_region_density_bars(
        self,
        names: list[str],
        density_vals: list[float],
        *,
        show_title: bool = True,
    ) -> None:
        """Plot area-normalized carbon density for each comparison site."""
        self._teardown_hover()
        self.ax.clear()
        if not names:
            self.show_message(tr("비교할 지역이 없습니다."))
            return
        if len(names) != len(density_vals):
            raise ValueError("names and density_vals must have the same length")

        x = list(range(len(names)))
        cmap = plt.get_cmap("tab10")
        hatches = ["//", "\\\\", "..", "xx", "++", "oo", "--", "**", "||"]
        for i, (xi, density, name) in enumerate(zip(x, density_vals, names)):
            self.ax.bar(
                xi,
                density,
                width=0.7,
                color=cmap(i % 10),
                hatch=hatches[i % len(hatches)],
                edgecolor="white",
                linewidth=0.8,
                label=name,
            )

        top = max(density_vals) if density_vals else 0.0
        for xi, density in zip(x, density_vals):
            self.ax.text(
                xi,
                density + (top * 0.01 if top else 0.0),
                f"{density:,.4f}",
                ha="center",
                va="bottom",
                fontsize=_fs(PLOT_ANNOTATION_PT),
                fontweight="bold",
            )

        self.ax.set_xticks([])
        # 제목이 '면적 정규화 탄소밀도' 이므로 축 이름은 짧게 둬 축 높이 안에 들어가게 한다.
        self.ax.set_ylabel(tr("탄소밀도 (kgC/㎡)"))
        self.ax.set_ylim(0, top * 1.18 if top > 0 else 1.0)
        if show_title:
            self._set_title(tr("지역별 면적 정규화 탄소밀도"), fontweight="bold")
        ncol = 1 + (len(names) - 1) // 12
        self.ax.legend(
            title=tr("지역"),
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            fontsize=_fs(PLOT_LEGEND_PT),
            framealpha=0.95,
            borderaxespad=0.0,
            ncol=max(1, ncol),
        )
        self.ax.grid(True, axis="y", alpha=0.3)
        self._fit_axes_text()
        self._fit_title()
        self.draw_idle()
