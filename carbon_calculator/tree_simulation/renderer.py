# SPDX-License-Identifier: MIT
"""PyVista/VTK 기반 지역 식생 glyph 렌더러."""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
import pyvista as pv
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import (
    vtkActor, vtkBillboardTextActor3D, vtkGlyph3DMapper, vtkPointPicker, vtkPolyDataMapper,
    vtkTextProperty,
)

from ..i18n import LANG_KO, get_language, tr
from ..typography import AXIS_LABEL_PT, AXIS_TITLE_PT
from .growth_models import render_states
from .models import RegionVisualizationSnapshot, RenderState
from .species_profiles import profile_by_key


def _find_korean_font_file() -> str | None:
    """한글 축 제목용 TrueType 글꼴 경로 (없으면 None → VTK 기본 글꼴 유지)."""
    import os
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("malgun.ttf", "gulim.ttc", "batang.ttc"):
        path = os.path.join(fonts, name)
        if os.path.exists(path):
            return path
    return None


_KOREAN_FONT_FILE = _find_korean_font_file()


class VegetationRenderer:
    """actor를 재사용하고 point/scale 배열만 갱신하는 glyph renderer."""

    def __init__(self, plotter):
        self.plotter = plotter
        self.snapshot: RegionVisualizationSnapshot | None = None
        self._ground_actor = None
        self._actors: list[vtkActor] = []
        self._datasets: dict[tuple[str, str, int], vtkPolyData] = {}
        self._pick_actor: vtkActor | None = None
        self._pick_dataset: vtkPolyData | None = None
        self._pick_instance_ids: tuple[int, ...] = ()
        self._z_axis_max = 1.0
        self._z_title_actor: vtkBillboardTextActor3D | None = None

    def clear(self) -> None:
        for actor in self._actors:
            self.plotter.renderer.RemoveActor(actor)
        self._actors.clear()
        self._datasets.clear()
        self._pick_actor = None
        self._pick_dataset = None
        self._pick_instance_ids = ()
        self.plotter.remove_bounds_axes()
        self._remove_z_title()
        self._z_axis_max = 1.0
        if self._ground_actor is not None:
            self.plotter.remove_actor(self._ground_actor)
            self._ground_actor = None
        self.snapshot = None
        self.plotter.render()

    def set_snapshot(self, snapshot: RegionVisualizationSnapshot) -> None:
        self.clear()
        self.snapshot = snapshot
        ground = pv.Plane(
            center=(snapshot.area_w / 2, snapshot.area_h / 2, 0),
            direction=(0, 0, 1),
            i_size=max(1.0, snapshot.area_w),
            j_size=max(1.0, snapshot.area_h),
            i_resolution=max(1, min(20, int(snapshot.area_w))),
            j_resolution=max(1, min(20, int(snapshot.area_h))),
        )
        self._ground_actor = self.plotter.add_mesh(
            ground, color="#B8C99D", show_edges=True, edge_color="#879A72",
            opacity=0.82, pickable=False,
        )
        states = render_states(snapshot, 0)
        self._create_glyph_actors(states)
        self._create_pick_actor(states)
        self._update_height_axis(states)
        self.plotter.view_isometric()
        self.plotter.camera.up = (0.0, 0.0, 1.0)
        self.plotter.reset_camera()
        self.plotter.render()

    @staticmethod
    def _nice_height_axis(max_height: float) -> tuple[float, float, int, str]:
        """최대 수고에 여백을 더하고 1·2·5 계열의 읽기 좋은 Z축을 만든다."""
        padded = max(1.0, float(max_height) * 1.15)
        # 화면에서 짧게 투영되는 Z축에 4개 안팎의 구간을 우선해 겹침을 막는다.
        rough_step = padded / 4.0
        magnitude = 10.0 ** math.floor(math.log10(rough_step))
        normalized = rough_step / magnitude
        if normalized <= 1.0:
            step = magnitude
        elif normalized <= 2.0:
            step = 2.0 * magnitude
        elif normalized <= 5.0:
            step = 5.0 * magnitude
        else:
            step = 10.0 * magnitude
        z_max = math.ceil(padded / step) * step
        label_count = max(2, min(5, int(round(z_max / step)) + 1))
        label_format = "%.0f" if step >= 1.0 else "%.1f"
        return z_max, step, label_count, label_format

    def _update_height_axis(self, states: tuple[RenderState, ...]) -> None:
        if self.snapshot is None:
            return
        max_height = max((s.rendered_height_m.value for s in states), default=0.0)
        z_max, _step, label_count, label_format = self._nice_height_axis(max_height)
        self.plotter.remove_bounds_axes()
        self._remove_z_title()
        # VTK 축 제목은 vtkVectorText(ASCII 전용)로 그려져 한글이 사라진다.
        # 한글이면 축 제목을 비우고, 같은 위치에 FreeType 글꼴 파일 기반 라벨을 따로 띄운다.
        korean_title = get_language() == LANG_KO and _KOREAN_FONT_FILE is not None
        axis = self.plotter.show_grid(
            xtitle="X (m)", ytitle="Y (m)", ztitle=" " if korean_title else tr("수고 (m)"),
            bounds=(0, self.snapshot.area_w, 0, self.snapshot.area_h, 0, z_max),
            # font_family 는 VTK 가 아는 3종(arial/courier/times)만 허용된다.
            n_zlabels=label_count, font_family="arial", font_size=AXIS_LABEL_PT,
        )
        # X/Y 형식은 기존 show_grid 기본값을 유지하고 Z축만 간결하게 표시한다.
        axis.SetZLabelFormat(label_format)
        for axis_name in ("X", "Y", "Z"):
            getattr(axis, f"Get{axis_name}AxesLabelProperty")().SetFontSize(AXIS_LABEL_PT)
            getattr(axis, f"Get{axis_name}AxesTitleProperty")().SetFontSize(AXIS_TITLE_PT)
        if korean_title:
            self._add_z_title(tr("수고 (m)"), z_max)
        self._z_axis_max = z_max

    def _add_z_title(self, text: str, z_max: float) -> None:
        """기본 등각 시점에서 Z축이 놓이는 모서리(x = 가로, y = 0) 위에 축 제목을 둔다."""
        actor = vtkBillboardTextActor3D()
        actor.SetInput(text)
        actor.SetPosition(self.snapshot.area_w, 0.0, z_max * 1.12)
        actor.PickableOff()
        prop = actor.GetTextProperty()
        prop.SetFontFamily(vtkTextProperty.GetFontFamilyFromString("File"))
        prop.SetFontFile(_KOREAN_FONT_FILE)
        prop.SetFontSize(AXIS_TITLE_PT)
        prop.SetColor(0.0, 0.0, 0.0)
        prop.SetJustificationToCentered()
        prop.SetVerticalJustificationToBottom()
        self.plotter.renderer.AddActor(actor)
        self._z_title_actor = actor

    def _remove_z_title(self) -> None:
        if self._z_title_actor is not None:
            self.plotter.renderer.RemoveActor(self._z_title_actor)
            self._z_title_actor = None

    @staticmethod
    def _source_for(profile_key: str, component: str, layer: int):
        profile = profile_by_key(profile_key)
        if component == "trunk":
            return pv.Cylinder(
                center=(0, 0, 0), direction=(0, 0, 1), radius=0.5,
                height=1.0, resolution=8, capping=True,
            )
        if profile.shape in ("layered_conifer", "pyramid"):
            resolution = 9 if profile.shape == "pyramid" else 11
            return pv.Cone(
                center=(0, 0, 0), direction=(0, 0, 1), height=1.0,
                radius=0.5, resolution=resolution, capping=True,
            )
        if profile.shape.startswith("shrub_"):
            return pv.Sphere(radius=0.5, theta_resolution=10, phi_resolution=7)
        return pv.Sphere(radius=0.5, theta_resolution=12, phi_resolution=8)

    @staticmethod
    def _polydata(points: np.ndarray, scales: np.ndarray) -> vtkPolyData:
        data = vtkPolyData()
        vtk_points = vtkPoints()
        vtk_points.SetData(numpy_to_vtk(points.astype(np.float32), deep=True))
        data.SetPoints(vtk_points)
        arr = numpy_to_vtk(scales.astype(np.float32), deep=True)
        arr.SetName("scale")
        data.GetPointData().AddArray(arr)
        data.GetPointData().SetActiveVectors("scale")
        return data

    def _add_glyph_actor(self, key: tuple[str, str, int], points: np.ndarray,
                         scales: np.ndarray, color: str, opacity: float) -> None:
        dataset = self._polydata(points, scales)
        mapper = vtkGlyph3DMapper()
        mapper.SetInputData(dataset)
        mapper.SetSourceData(self._source_for(*key))
        mapper.SetScaleArray("scale")
        mapper.SetScaleModeToScaleByVectorComponents()
        mapper.ScalingOn()
        mapper.OrientOff()
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(pv.Color(color).float_rgb)
        actor.GetProperty().SetOpacity(opacity)
        self.plotter.renderer.AddActor(actor)
        self._actors.append(actor)
        self._datasets[key] = dataset

    def _geometry_arrays(self, states: tuple[RenderState, ...]):
        buckets: dict[tuple[str, str, int], tuple[list, list]] = defaultdict(lambda: ([], []))
        for state in states:
            profile = profile_by_key(state.profile_key)
            h = state.rendered_height_m.value
            crown_l = min(h, state.rendered_crown_length_m.value)
            crown_w = state.rendered_crown_width_m.value
            trunk_h = max(0.15, h - crown_l * (0.84 if state.kind == "shrub" else 0.72))
            # 실제 DBH는 계산에 그대로 보존하고, 단순 cylinder가 지나치게 가늘게
            # 보이는 문제만 렌더링 전용 비선형 보정으로 완화한다.
            trunk_d = state.rendered_trunk_diameter_m.value
            if state.kind == "tree":
                key = (state.profile_key, "trunk", 0)
                buckets[key][0].append((state.x_m, state.y_m, trunk_h / 2))
                buckets[key][1].append((trunk_d, trunk_d, trunk_h))
            else:
                # 관목은 한 개의 구체가 아니라 수관 아래에서 갈라지는 짧은 다간 줄기로 표현한다.
                stem_count = 5 if profile.shape == "shrub_multistem" else 3
                stem_h = max(0.28, h * (0.58 if profile.shape == "shrub_upright" else 0.46))
                for stem in range(stem_count):
                    angle = state.instance_id * 1.19 + stem * (2 * np.pi / stem_count)
                    radius = min(crown_w * 0.13, 0.18) * (stem / max(1, stem_count - 1))
                    sx = state.x_m + np.cos(angle) * radius
                    sy = state.y_m + np.sin(angle) * radius
                    key = (state.profile_key, "trunk", stem)
                    buckets[key][0].append((sx, sy, stem_h / 2))
                    buckets[key][1].append((trunk_d * 0.72, trunk_d * 0.72, stem_h))

            layers = max(1, profile.crown_layers)
            for layer in range(layers):
                frac = (layer + 0.5) / layers
                z = max(0.08, h - crown_l + crown_l * frac)
                taper = 1.0 - 0.24 * layer / max(1, layers - 1)
                if profile.shape in (
                    "open_oval", "rounded", "dense_oval", "spreading",
                    "shrub_rounded", "shrub_spreading", "shrub_multistem",
                ):
                    offset = profile.crown_irregularity * crown_w
                    x = state.x_m + offset * np.sin(state.instance_id * 1.73 + layer)
                    y = state.y_m + offset * np.cos(state.instance_id * 1.31 + layer)
                else:
                    x, y = state.x_m, state.y_m
                key = (state.profile_key, "crown", layer)
                buckets[key][0].append((x, y, z))
                # 크기는 DBH/RCD 성장비가 담당하고, 경과 연도는 수관 element의
                # 부피감만 완만하게 보강한다(LAI/밀도 값이 아님).
                fullness = 0.84 + 0.16 * state.visual_development
                width = crown_w * taper * fullness
                shrub_shape = profile.shape.startswith("shrub_")
                layer_h = crown_l * fullness / (layers * (0.72 if shrub_shape else 0.58))
                buckets[key][1].append((width, width, max(0.18, layer_h)))
        return {
            key: (np.asarray(points, dtype=float), np.asarray(scales, dtype=float))
            for key, (points, scales) in buckets.items()
        }

    def _create_glyph_actors(self, states: tuple[RenderState, ...]) -> None:
        for key, (points, scales) in self._geometry_arrays(states).items():
            profile = profile_by_key(key[0])
            color = "#76543A" if key[1] == "trunk" else profile.color
            opacity = 1.0 if key[1] == "trunk" else profile.opacity
            self._add_glyph_actor(key, points, scales, color, opacity)

    def _create_pick_actor(self, states: tuple[RenderState, ...]) -> None:
        points = np.asarray([
            (s.x_m, s.y_m, s.rendered_height_m.value * 0.55) for s in states
        ], dtype=float)
        dataset = vtkPolyData()
        vtk_points = vtkPoints()
        vtk_points.SetData(numpy_to_vtk(points.astype(np.float32), deep=True))
        dataset.SetPoints(vtk_points)
        vertices = vtkCellArray()
        for point_id in range(len(states)):
            vertices.InsertNextCell(1)
            vertices.InsertCellPoint(point_id)
        dataset.SetVerts(vertices)
        mapper = vtkPolyDataMapper(); mapper.SetInputData(dataset)
        actor = vtkActor(); actor.SetMapper(mapper)
        actor.GetProperty().SetRepresentationToPoints()
        actor.GetProperty().SetPointSize(18)
        actor.GetProperty().SetOpacity(0.01)
        actor.SetPickable(True)
        self.plotter.renderer.AddActor(actor)
        self._actors.append(actor)
        self._pick_actor = actor
        self._pick_dataset = dataset
        self._pick_instance_ids = tuple(s.instance_id for s in states)

    def pick_instance(self, display_x: int, display_y: int) -> int | None:
        if self._pick_actor is None:
            return None
        picker = vtkPointPicker()
        picker.SetTolerance(0.035)
        picker.PickFromListOn()
        picker.AddPickList(self._pick_actor)
        if not picker.Pick(display_x, display_y, 0, self.plotter.renderer):
            return None
        point_id = picker.GetPointId()
        if 0 <= point_id < len(self._pick_instance_ids):
            return self._pick_instance_ids[point_id]
        return None

    def update_year(self, year: int) -> None:
        if self.snapshot is None:
            return
        states = render_states(self.snapshot, year)
        arrays = self._geometry_arrays(states)
        # snapshot 내 개체/프로파일 구성은 고정이므로 key와 point 수는 연도에 따라 동일하다.
        for key, dataset in self._datasets.items():
            points, scales = arrays[key]
            dataset.GetPoints().SetData(numpy_to_vtk(points.astype(np.float32), deep=True))
            scale_arr = numpy_to_vtk(scales.astype(np.float32), deep=True)
            scale_arr.SetName("scale")
            dataset.GetPointData().RemoveArray("scale")
            dataset.GetPointData().AddArray(scale_arr)
            dataset.GetPointData().SetActiveVectors("scale")
            dataset.Modified()
        if self._pick_dataset is not None:
            pick_points = np.asarray([
                (s.x_m, s.y_m, s.rendered_height_m.value * 0.55) for s in states
            ], dtype=np.float32)
            self._pick_dataset.GetPoints().SetData(numpy_to_vtk(pick_points, deep=True))
            self._pick_dataset.Modified()
        # 축 actor만 교체하며 camera position/focal point/up은 변경하지 않는다.
        self._update_height_axis(states)
        self.plotter.render()
