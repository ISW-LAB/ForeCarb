# SPDX-License-Identifier: MIT
"""Regression coverage for assumed growth and shared yearly views."""
import os
import unittest
from unittest.mock import Mock, patch
import numpy as np
from carbon_calculator import species_library as lib
from carbon_calculator.calculations import project_future_carbon
from carbon_calculator.projections import project_record
from carbon_calculator.tree_simulation.models import VisualizationInputGroup
from carbon_calculator.tree_simulation.snapshot import build_snapshot, input_fingerprint
from carbon_calculator.tree_simulation.inspection import inspect_instance
from carbon_calculator.tree_simulation.growth_models import render_states

def inputs():
    result = []
    for r in lib.all_records().values():
        x = max(0.1, (r.range_min + r.range_max) / 2) if r.has_range else 10.0
        h = r.var2_default if r.is_multivar else None
        result.append(VisualizationInputGroup(r.key, r.kind, x, 2, "cm", r.species_data, r, h))
    return tuple(result)

class ProjectionTests(unittest.TestCase):
    def test_all_records_keep_current_stock_and_original_equations(self):
        for item in inputs():
            r = item.record
            with self.subTest(record=r.key):
                years, values, carbon = project_record(r, item.diameter, 2, item.var2)
                np.testing.assert_array_equal(years, np.arange(31))
                self.assertAlmostEqual(carbon[0], lib.carbon_total(r, item.diameter, 2, item.var2))
                if r.species_data is not None:
                    _, original = project_future_carbon(r.species_data, item.diameter, 2)
                    np.testing.assert_array_equal(carbon, original)
                else:
                    self.assertAlmostEqual(values[-1], item.diameter * 1.02 ** 30)
                    self.assertAlmostEqual(carbon[-1], lib.carbon_total(r, values[-1], 2, item.var2))
                self.assertTrue(np.isfinite(carbon).all())

    def test_snapshot_matches_graph_and_inspection_for_every_record(self):
        items = inputs()
        snapshot = build_snapshot(region_name="test", environment="", area_w=30, area_h=30, inputs=items)
        expected = np.zeros(31)
        for item, group in zip(items, snapshot.groups):
            _, _, carbon = project_record(item.record, item.diameter, item.quantity, item.var2)
            np.testing.assert_array_equal(group.carbon_by_year_kgc, carbon)
            expected += carbon
            instance = next(i for i in snapshot.instances if i.group_id == group.group_id)
            info = inspect_instance(snapshot, instance.instance_id, 30)
            self.assertAlmostEqual(info.carbon_kgc * item.quantity, carbon[-1])
        np.testing.assert_allclose(snapshot.total_carbon_by_year_kgc, expected)
        self.assertAlmostEqual(snapshot.carbon_totals_at(30)[2], expected[-1])
        self.assertEqual(render_states(snapshot, 31), render_states(snapshot, 30))

    def test_auxiliary_variable_changes_fingerprint_and_carbon(self):
        from dataclasses import replace
        item = next(i for i in inputs() if i.record.is_multivar)
        changed = replace(item, var2=item.var2 + 1)
        a = input_fingerprint("test", "", 10, 10, (item,))
        b = input_fingerprint("test", "", 10, 10, (changed,))
        self.assertNotEqual(a, b)
        self.assertNotEqual(project_record(item.record, item.diameter, 2, item.var2)[2][-1],
                            project_record(item.record, item.diameter, 2, changed.var2)[2][-1])

class SharedYearUiTests(unittest.TestCase):
    def test_tabs_slider_contributions_recalculation_playback_and_clear(self):
        # Exercise real Qt controls and Matplotlib; replace only the GPU renderer.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication, QWidget
        from carbon_calculator.main_window import MainWindow
        from carbon_calculator.tree_simulation import visualization_tab as vis
        app = QApplication.instance() or QApplication([])
        class Plotter(QWidget):
            def __init__(self, parent, **kwargs):
                super().__init__(parent)
                self.iren = Mock()
                self.interactor = Mock()
            def set_background(self, *a): pass
            def enable_terrain_style(self, **kw): pass
            def clear_actors(self): pass
            def add_text(self, *a, **kw): pass
        with patch.object(vis, "QtInteractor", Plotter), patch.object(vis, "VegetationRenderer"):
            w = MainWindow(region_name="test", area_w=30, area_h=30)
            try:
                from carbon_calculator.i18n import tr
                # 교목·관목 × (연도별 · 생존률 반영 · 직경별) + 시각화 = 7 페이지, 버튼 한 줄로 선택
                self.assertEqual(w._graph_tabs.count(), 7)
                self.assertEqual([b.text() for b in w._view_buttons.values()],
                                 [tr("연도별"), tr("생존률 반영"), tr("직경별")])
                w._kind_buttons["shrub"].click()
                w._view_buttons["survival"].click()
                self.assertEqual(w._graph_tabs.currentIndex(), w._graph_pages[("shrub", "survival")])
                w._graph_tabs.setCurrentIndex(w._graph_pages[("tree", "year")])
                self.assertTrue(w._kind_buttons["tree"].isChecked() and w._view_buttons["year"].isChecked())
                self.assertIs(w.visualization_tab.year_slider, w.year_slider)
                self.assertFalse(w.visualization_tab.isAncestorOf(w.year_slider))
                w._set_top_carbon_display(1000.0, 500.0, 1500.0)
                self.assertEqual(w.economic_value_button.text(), tr("경제가치: {value:,.0f}원").format(value=45000))
                with patch("carbon_calculator.main_window.QInputDialog.getDouble", return_value=(40000.0, True)):
                    w.economic_value_button.click()
                self.assertEqual(w.economic_value_button.text(), tr("경제가치: {value:,.0f}원").format(value=60000))
                with patch("carbon_calculator.main_window.QInputDialog.getDouble", return_value=(0.0, False)):
                    w.economic_value_button.click()
                self.assertEqual(w._carbon_price_per_tonne, 40000.0)
                selected = [
                    next(i for i in inputs() if i.kind == kind and (i.species_data is None) == assumed)
                    for kind in ("tree", "shrub") for assumed in (False, True)
                ]
                for item in selected:
                    w._append_row(item.kind, item.species, item.diameter, item.quantity, var2=item.var2)
                w.on_calculate()
                year_pie = w.tree_pie_canvas
                fixed_pie = w.tree_diameter_pie_canvas
                with patch.object(year_pie, "plot_pie") as yearly, patch.object(fixed_pie, "plot_pie") as fixed:
                    w.year_slider.setValue(20)
                    expected = [float(e.curve[20]) for e in w._tree_entries]
                    self.assertEqual(yearly.call_args.args[1], expected)
                    fixed.assert_not_called()
                snapshot = w.visualization_tab.snapshot
                self.assertEqual(w.total_value_label.text(), f"{snapshot.carbon_totals_at(20)[2]:,.2f}")
                self.assertEqual(w.economic_value_button.text(), tr("경제가치: {value:,.0f}원").format(
                    value=snapshot.carbon_totals_at(20)[2] / 1000 * 40000))
                self.assertEqual(list(w._tree_year_marker.get_xdata()), [20, 20])
                w.visualization_tab.renderer.update_year.assert_called_with(20)
                w.on_calculate()
                self.assertEqual(w.year_slider.value(), 20)
                payload = w._payload_for("tree", sum(e.carbon_kg for e in w._tree_entries))
                self.assertEqual(len(payload["projection"]["years"]), 31)
                self.assertEqual(len(payload["projection"]["series"]), 2)
                # 기본 생존율(100 %)이면 게이지의 생존 반영 값은 전량 생존 값과 같다.
                self.assertAlmostEqual(w.total_gauge.secondaryValue(), w.total_gauge.value(), places=6)
                w._graph_tabs.setCurrentIndex(w._graph_tabs.indexOf(w.visualization_tab))
                w.year_slider.setValue(29)
                w.visualization_tab.play()
                w.visualization_tab._advance_year()
                self.assertEqual(w.year_slider.value(), 30)
                self.assertFalse(w.visualization_tab._play_timer.isActive())
                w.visualization_tab.play()
                self.assertEqual(w.year_slider.value(), 0)
                w._graph_tabs.setCurrentIndex(0)
                self.assertFalse(w.visualization_tab._play_timer.isActive())
                w.on_clear()
                self.assertEqual(w.total_value_label.text(), "0.00")
                self.assertEqual(w.economic_value_button.text(), tr("경제가치: {value:,.0f}원").format(value=0))
                self.assertEqual(w._carbon_price_per_tonne, 40000.0)
                self.assertEqual(len(w.visualization_tab.snapshot.groups), 0)
            finally:
                w.visualization_tab.close()
                w.close()
                w.deleteLater()
                app.processEvents()
