# SPDX-License-Identifier: MIT
"""Fitted-range audit, calculation-details report, equation IDs and planting-area settings.

These tests cover the review revision (v1.1): the share of a scenario total
that is obtained by extrapolation, the first year each record leaves its
fitted range, the provenance recorded in the XLSX report, the user-defined
planting-area safeguard, and the reproducible example of the manuscript.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from openpyxl import load_workbook

from carbon_calculator import extrapolation, i18n, input_limits, preset_io
from carbon_calculator import species_library as lib
from carbon_calculator.data import RESTORATION_ENVIRONMENTS
from carbon_calculator.excel_export import export_all_regions_to_excel, export_carbon1_to_excel
from carbon_calculator.i18n import tr
from carbon_calculator.projections import project_record

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENV = RESTORATION_ENVIRONMENTS[0]

# Profile 1 of the manuscript (Table 2): (kind, library key, diameter cm, count).
PROFILE_1 = (
    ("tree", "소나무", 5.0, 30),
    ("tree", "졸참나무", 4.0, 20),
    ("tree", "신갈나무", 8.0, 15),
    ("shrub", "산철쭉", 1.2, 40),
    ("shrub", "병꽃나무", 1.5, 25),
)


@contextmanager
def assessment_window(**kwargs):
    """A real MainWindow with only the GPU renderer replaced (as in the shared-year UI test)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from carbon_calculator.main_window import MainWindow
    from carbon_calculator.tree_simulation import visualization_tab as vis
    from reproduce_examples import _StubPlotter

    messages: list = []

    def _collect(_parent, _title, text, *_args, **_kwargs):
        messages.append(text)
        return 0

    with patch.object(vis, "QtInteractor", _StubPlotter), \
            patch.object(vis, "VegetationRenderer"), \
            patch("carbon_calculator.main_window.QMessageBox.warning", _collect), \
            patch("carbon_calculator.main_window.QMessageBox.information", _collect):
        window = MainWindow(**kwargs)
        try:
            yield window, messages
        finally:
            window.visualization_tab.close()
            window.close()
            window.deleteLater()
            app.processEvents()


def table_rows(ws, first_header: str, second_header: str) -> list:
    """Rows (as dicts) of the table whose header row starts with the two given headers."""
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 1).value == first_header and ws.cell(r, 2).value == second_header:
            headers = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            rows = []
            r += 1
            while r <= ws.max_row and ws.cell(r, 1).value not in (None, ""):
                values = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
                rows.append(dict(zip(headers, values)))
                r += 1
            return rows
    raise AssertionError(f"no table starting with {first_header!r}, {second_header!r}")


class ExtrapolationMathTests(unittest.TestCase):
    def test_limits_are_inclusive_and_tolerate_accumulated_rounding(self) -> None:
        inside = extrapolation.within_fitted_range(1.0, 15.0, [0.99, 1.0, 15.0, 15.01])
        self.assertEqual(inside.tolist(), [False, True, True, False])
        # 1.5 + 8 x 0.3 accumulates to a float that is not exactly 3.9.
        value = 1.5
        for _ in range(8):
            value += 0.3
        self.assertTrue(extrapolation.within_fitted_range(0.6, 3.9, [value])[0])

    def test_first_year_outside(self) -> None:
        self.assertIsNone(extrapolation.first_year_outside(np.array([True, True])))
        self.assertEqual(extrapolation.first_year_outside(np.array([True, True, False, False])), 2)
        self.assertIsNone(extrapolation.first_year_outside(None))

    def test_summary_splits_the_total_by_audit_status(self) -> None:
        a = np.array([10.0, 20.0, 40.0])
        b = np.array([1.0, 2.0, 4.0])
        c = np.array([5.0, 5.0, 5.0])
        summary = extrapolation.summarize(
            [a, b, c],
            [np.array([True, True, False]), np.array([True, False, False]), None],
        )
        np.testing.assert_allclose(summary.total, [16.0, 27.0, 49.0])
        np.testing.assert_allclose(summary.extrapolated, [0.0, 2.0, 44.0])
        np.testing.assert_allclose(summary.unassessed, [5.0, 5.0, 5.0])
        np.testing.assert_allclose(summary.within, [11.0, 20.0, 0.0])
        self.assertAlmostEqual(summary.share_at(2), 100.0 * 44.0 / 49.0)
        combined = extrapolation.combine(summary, summary)
        np.testing.assert_allclose(combined.extrapolated, [0.0, 4.0, 88.0])
        np.testing.assert_allclose(combined.share_pct, summary.share_pct)

    def test_empty_inventory_gives_zero_share(self) -> None:
        summary = extrapolation.summarize([], [], length=31)
        self.assertEqual(len(summary.total), 31)
        self.assertEqual(float(summary.share_pct.sum()), 0.0)

    def test_audit_never_changes_the_trajectory(self) -> None:
        record = lib.records_for_kind(lib.KIND_SHRUB, ENV)["산철쭉"]
        _years, values, carbon = project_record(record, 1.2, 40)
        before = carbon.copy()
        inside = extrapolation.within_fitted_range(record.range_min, record.range_max, values)
        extrapolation.summarize([carbon], [inside])
        np.testing.assert_array_equal(carbon, before)


class ProfileOneAuditTests(unittest.TestCase):
    """The worked example of the manuscript, computed from the library without the GUI."""

    def _project(self):
        curves, flags, first = [], [], {}
        for kind, key, diameter, count in PROFILE_1:
            record = lib.records_for_kind(kind, ENV)[key]
            _years, values, carbon = project_record(record, diameter, count)
            inside = extrapolation.within_fitted_range(record.range_min, record.range_max, values)
            curves.append(carbon)
            flags.append(inside)
            first[key] = extrapolation.first_year_outside(inside)
        return curves, flags, first

    def test_totals_match_the_manuscript(self) -> None:
        curves, flags, _first = self._project()
        summary = extrapolation.summarize(curves, flags)
        self.assertAlmostEqual(round(float(summary.total[0]), 2), 198.89)
        self.assertAlmostEqual(round(float(summary.total[15]), 2), 900.20)
        self.assertAlmostEqual(round(float(summary.total[30]), 2), 3444.50)

    def test_extrapolated_share_and_first_years(self) -> None:
        curves, flags, first = self._project()
        summary = extrapolation.summarize(curves, flags)
        self.assertEqual(first, {"소나무": 30, "졸참나무": None, "신갈나무": None,
                                 "산철쭉": 4, "병꽃나무": 9})
        self.assertEqual(float(summary.extrapolated[3]), 0.0)
        self.assertAlmostEqual(round(float(summary.extrapolated[30]), 2), 1590.13)
        self.assertAlmostEqual(round(summary.share_at(30), 1), 46.2)
        self.assertAlmostEqual(round(summary.share_at(15), 1), 15.1)


class EquationIdTests(unittest.TestCase):
    def test_ids_follow_the_library_order_and_are_unique(self) -> None:
        ids = lib.equation_ids()
        self.assertEqual(len(ids), 77)
        self.assertEqual(len(set(ids.values())), 77)
        self.assertEqual(lib.equation_id("소나무"), "T01")
        self.assertEqual(lib.equation_id("신갈나무"), "T07")
        self.assertEqual(lib.equation_id("산철쭉"), "S02")
        self.assertEqual(lib.equation_id("병꽃나무"), "S10")
        self.assertEqual(lib.equation_id("없는나무"), "")
        counts = {code: sum(1 for v in ids.values() if v.startswith(code)) for code in "TSDI"}
        self.assertEqual(counts, {"T": 7, "S": 15, "D": 30, "I": 25})
        for key, record in lib.all_records(ENV).items():
            with self.subTest(record=key):
                self.assertEqual(ids[key][0], lib.collection_code(record))

    def test_library_identity_depends_on_content_only(self) -> None:
        identity = lib.library_identity()
        self.assertEqual(identity["file"], "species_data.json")
        self.assertRegex(identity["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(identity, lib.library_identity())


class PlantingAreaSettingTests(unittest.TestCase):
    def tearDown(self) -> None:
        input_limits.reset_planting_unit_areas()

    def test_defaults_are_the_documented_values(self) -> None:
        self.assertEqual(input_limits.planting_unit_areas(), (1.0, 0.25))
        self.assertTrue(input_limits.is_default_unit_areas())
        budget = input_limits.planting_area_budget(area_w=10, area_h=10,
                                                  tree_quantity=80, shrub_quantity=80)
        self.assertEqual(budget.required_area_m2, 100.0)
        self.assertFalse(budget.is_exceeded)

    def test_user_values_change_only_the_safeguard(self) -> None:
        record = lib.records_for_kind(lib.KIND_TREE, ENV)["소나무"]
        before = lib.carbon_total(record, 5.0, 30)
        input_limits.set_planting_unit_areas(4.0, 1.0)
        self.assertFalse(input_limits.is_default_unit_areas())
        budget = input_limits.planting_area_budget(area_w=10, area_h=10,
                                                  tree_quantity=80, shrub_quantity=80)
        self.assertEqual((budget.tree_unit_area_m2, budget.shrub_unit_area_m2), (4.0, 1.0))
        self.assertEqual(budget.required_area_m2, 400.0)
        self.assertTrue(budget.is_exceeded)
        self.assertEqual(lib.carbon_total(record, 5.0, 30), before)
        # An explicit argument still takes precedence over the session setting.
        explicit = input_limits.planting_area_budget(
            area_w=10, area_h=10, tree_quantity=80, shrub_quantity=80,
            tree_unit_area_m2=1.0, shrub_unit_area_m2=0.25)
        self.assertEqual(explicit.required_area_m2, 100.0)

    def test_invalid_values_are_rejected_and_leave_the_setting_unchanged(self) -> None:
        for tree, shrub in ((0.0, 0.25), (1.0, -1.0), (float("nan"), 0.25), (1000.0, 0.25)):
            with self.subTest(tree=tree, shrub=shrub), self.assertRaises(ValueError):
                input_limits.set_planting_unit_areas(tree, shrub)
        self.assertEqual(input_limits.planting_unit_areas(), (1.0, 0.25))


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        i18n.set_language(i18n.LANG_KO)

    def tearDown(self) -> None:
        input_limits.reset_planting_unit_areas()

    def test_profile_1_report_records_equations_and_the_extrapolated_share(self) -> None:
        with assessment_window(region_name="Profile 1", area_w=20, area_h=20) as (window, messages):
            for kind, key, diameter, count in PROFILE_1:
                window._append_row(kind, key, diameter, count)
            window.on_calculate()
            self.assertEqual(messages, [])
            window.year_slider.setValue(30)
            self.assertIn("46.2", window._tree_basis_note.text())
            self.assertIn("39.2", window._tree_basis_note.text())
            self.assertIn("100.0", window._shrub_basis_note.text())
            window.year_slider.setValue(3)
            self.assertIn(tr("{year}년: {kind} 추정이 모두 적합범위 안 (첫 외삽: {first}년)")
                          .format(year=3, kind=tr("관목"), first=4), window._shrub_basis_note.text())
            payload = window.build_export_payload()
            with TemporaryDirectory() as tmp:
                path = str(Path(tmp) / "profile1.xlsx")
                export_carbon1_to_excel(path, payload)
                wb = load_workbook(path, data_only=True)

        self.assertEqual(wb.sheetnames, [tr("추정_교목"), tr("추정_{kind}").format(kind=tr("관목")),
                                         tr("기여도"), tr("생존률_반영"), tr("계산근거"),
                                         tr("적합범위_점검"), tr("그래프")])
        details = table_rows(wb[tr("계산근거")], tr("구분"), tr("식 ID"))
        self.assertEqual([row[tr("식 ID")] for row in details], ["T01", "T04", "T07", "S02", "S10"])
        self.assertEqual([row[tr("범위 이탈 첫 연차")] for row in details],
                         ["30", tr("없음 (30년까지 범위 안)"), tr("없음 (30년까지 범위 안)"), "4", "9"])
        self.assertEqual({row[tr("계수 변경")] for row in details}, {tr("없음")})
        self.assertEqual([row[tr("식 입력 배율 q")] for row in details], [1, 1, 1, 10, 10])
        pine = details[0]
        self.assertEqual(pine[tr("적용 식")], "Y = 0.0737 × X^2.5735")
        self.assertAlmostEqual(pine[tr("개체 바이오매스(kg)")], 0.0737 * 5.0 ** 2.5735, places=5)
        self.assertAlmostEqual(pine[tr("탄소저장량(kgC)")], 69.5598, places=3)
        self.assertAlmostEqual(pine[tr("30년 설명변수 값")], 15.1, places=6)
        self.assertEqual(pine[tr("30년 추정 상태")], tr("외삽 (범위 밖)"))
        self.assertEqual(details[1][tr("30년 추정 상태")], tr("범위 안"))
        self.assertAlmostEqual(sum(row[tr("탄소저장량(kgC)")] for row in details), 198.89, places=2)

        audit = wb[tr("적합범위_점검")]
        header = [audit.cell(4, c).value for c in range(1, audit.max_column + 1)]
        self.assertEqual(header[:9], [
            tr("경과연도(년)"), tr("교목 합계(kgC)"), tr("교목 외삽(kgC)"), tr("관목 합계(kgC)"),
            tr("관목 외삽(kgC)"), tr("대상지 합계(kgC)"), tr("대상지 외삽(kgC)"),
            tr("외삽 비율(%)"), tr("범위 미제공(kgC)")])
        year30 = [audit.cell(35, c).value for c in range(1, audit.max_column + 1)]
        self.assertEqual(year30[0], 30)
        self.assertAlmostEqual(year30[5], 3444.50, places=2)
        self.assertAlmostEqual(year30[6], 1590.13, places=2)
        self.assertAlmostEqual(year30[7], 46.16, places=2)
        self.assertEqual(year30[9:], [0, 1, 1, 0, 0])          # v(t) of the five records
        year3 = [audit.cell(8, c).value for c in range(1, audit.max_column + 1)]
        self.assertEqual((year3[0], year3[6], year3[9:]), (3, 0, [1, 1, 1, 1, 1]))

    def test_report_lists_parameter_changes_excluded_rows_and_unassessed_records(self) -> None:
        input_limits.set_planting_unit_areas(2.0, 0.5)
        with assessment_window(region_name="A", area_w=30, area_h=30) as (window, messages):
            window._append_row("tree", "소나무", 5.0, 30, override_coeffs=(0.08, 2.5735, 0.47))
            window._append_row("tree", "소나무", 20.0, 5)                 # outside 1-15 cm
            window._append_row("tree", "곰솔(전체, 해안방재림)", 15.0, 3)  # no stored increments
            window._append_row("tree", "후박나무(지상부)", 10.0, 2)        # no published range
            window._append_row("shrub", "병꽃나무", 1.5, 0)                # zero count
            window.on_calculate()
            self.assertEqual(len(messages), 1)
            payload = window.build_export_payload()
            note = window._tree_basis_note.text()
            with TemporaryDirectory() as tmp:
                single = str(Path(tmp) / "single.xlsx")
                export_carbon1_to_excel(single, payload)
                ws = load_workbook(single, data_only=True)[tr("계산근거")]
                combined = str(Path(tmp) / "combined.xlsx")
                export_all_regions_to_excel(combined, [payload], [])
                wb_all = load_workbook(combined, data_only=True)

        self.assertIn(tr("유효범위 미제공 {n}개 항목은 점검 불가").format(n=1), note)
        details = table_rows(ws, tr("구분"), tr("식 ID"))
        self.assertEqual([row[tr("식 ID")] for row in details], ["T01", "D21", "D01"])
        self.assertEqual(details[0][tr("계수 변경")], "a: 0.0737 → 0.08; CF: 0.5 → 0.47")
        self.assertEqual(details[0][tr("적용 식")], "Y = 0.08 × X^2.5735")
        self.assertEqual(details[0]["CF"], 0.47)
        self.assertEqual(details[1][tr("계수 변경")], tr("없음"))
        self.assertIn("1.02^t", details[1][tr("연간 직경 생장량(cm/yr, 1~10/11~20/21~30년)")])
        self.assertEqual(details[1][tr("컬렉션")], tr("국내"))
        self.assertEqual(details[2][tr("범위 이탈 첫 연차")], tr("점검 불가 (범위 미제공)"))
        self.assertEqual(details[2][tr("적합범위")], tr("미제공"))

        excluded = table_rows(ws, tr("구분"), tr("수종"))
        self.assertEqual(len(excluded), 2)
        self.assertEqual([row[tr("수량")] for row in excluded], [5, 0])
        self.assertIn("1 cm ~ 15 cm", excluded[0][tr("제외 사유")])
        self.assertEqual(excluded[1][tr("제외 사유")], tr("수량이 0 이어서 제외"))
        text = [str(ws.cell(r, c).value) for r in range(1, 8) for c in range(1, 4)
                if ws.cell(r, c).value is not None]
        self.assertTrue(any("2 m²" in t and "0.5 m²" in t for t in text),
                        "the planting areas in use are recorded")

        self.assertIn(tr("계산근거"), wb_all.sheetnames)
        self.assertIn(tr("적합범위_점검"), wb_all.sheetnames)
        rows_all = table_rows(wb_all[tr("계산근거")], tr("지역"), tr("구분"))
        self.assertEqual([row[tr("식 ID")] for row in rows_all], ["T01", "D21", "D01"])
        self.assertEqual({row[tr("지역")] for row in rows_all}, {"A"})
        audit_all = wb_all[tr("적합범위_점검")]
        self.assertEqual([audit_all.cell(4, c).value for c in (2, 3, 4)],
                         [tr("합계(kgC)"), tr("외삽(kgC)"), tr("외삽 비율(%)")])
        self.assertEqual(audit_all.cell(35, 1).value, 30)

    def test_exports_accept_payloads_without_the_optional_audit_fields(self) -> None:
        years = [0, 1]
        category = {"unit": "cm", "total": 2.0, "total_qty": 1,
                    "rows": [{"species": "소나무", "diameter": 5.0, "quantity": 1, "carbon": 2.0,
                              "checked": True}],
                    "projection": {"years": years, "series": [
                        {"label": "x", "checked": True, "carbon": [2.0, 3.0]}], "total": None},
                    "contribution": []}
        empty = {"unit": "cm", "total": 0.0, "total_qty": 0, "rows": [], "projection": None,
                 "contribution": []}
        payload = {"generated_at": "", "grand_total": 2.0,
                   "region": {"name": "A", "environment": ENV, "area_w": 20, "area_h": 20, "area": 400},
                   "tree": category, "shrub": empty, "images": []}
        with TemporaryDirectory() as tmp:
            single = str(Path(tmp) / "single.xlsx")
            export_carbon1_to_excel(single, payload)
            wb = load_workbook(single, data_only=True)
            combined = str(Path(tmp) / "combined.xlsx")
            export_all_regions_to_excel(combined, [payload], [])
            wb_all = load_workbook(combined, data_only=True)
        self.assertEqual(wb[tr("적합범위_점검")].cell(4, 1).value, tr("추정 데이터가 없습니다."))
        self.assertEqual(len(table_rows(wb[tr("계산근거")], tr("구분"), tr("식 ID"))), 1)
        self.assertEqual(wb_all[tr("적합범위_점검")].cell(4, 1).value, tr("추정 데이터가 없습니다."))

    def test_figures_mark_extrapolated_estimates(self) -> None:
        with assessment_window(region_name="Profile 1", area_w=20, area_h=20) as (window, _messages):
            for kind, key, diameter, count in PROFILE_1:
                window._append_row(kind, key, diameter, count)
            window.on_calculate()
            for canvas, share in ((window.tree_canvas, "39.2"), (window.shrub_canvas, "100.0")):
                legend = [t.get_text() for t in canvas.ax.get_legend().get_texts()]
                self.assertIn(tr("적합범위 밖(외삽)"), legend)
                self.assertIn(tr("합계 중 외삽분"), legend)
                notes = [t.get_text() for t in canvas.ax.texts]
                self.assertIn(tr("{year}년 외삽 비율: {share:.1f} %").format(year=30, share=float(share)),
                              "\n".join(notes))
                self.assertIn(tr("대상지 전체 외삽 비율: {share:.1f} %").format(share=46.2),
                              "\n".join(notes))
            window.year_slider.setValue(15)
            self.assertIn("15.1", window._tree_basis_note.text())
            png = window.figure_png(window.shrub_canvas, (13.5, 6.0))
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            # Rendering for export must leave the on-screen figure size untouched.
            before = tuple(window.shrub_canvas.figure.get_size_inches())
            window.figure_png(window.shrub_canvas, (9.0, 4.0))
            self.assertEqual(tuple(window.shrub_canvas.figure.get_size_inches()), before)

    def test_plot_without_audit_arguments_is_unchanged(self) -> None:
        with assessment_window(region_name="B", area_w=20, area_h=20) as (window, _messages):
            window._append_row("tree", "졸참나무", 4.0, 20)
            window._append_row("tree", "신갈나무", 8.0, 15)
            window.on_calculate()
            legend = [t.get_text() for t in window.tree_canvas.ax.get_legend().get_texts()]
            self.assertNotIn(tr("적합범위 밖(외삽)"), legend)
            self.assertEqual([t.get_text() for t in window.tree_canvas.ax.texts if t.get_text()], [])
            self.assertEqual(window._tree_basis_note.text(), "")


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        i18n.set_language(i18n.LANG_KO)

    def tearDown(self) -> None:
        input_limits.reset_planting_unit_areas()

    def test_entry_dialog_shows_the_equation_id_of_the_selected_record(self) -> None:
        with assessment_window(region_name="A", area_w=20, area_h=20) as (window, _messages):
            from carbon_calculator.main_window import AddSpeciesDialog

            dialog = AddSpeciesDialog("tree", window._tree_records, window._tree_names, window)
            try:
                self.assertTrue(dialog.equation_id_label.text().startswith("T01"))
                index = dialog.combo.combo.findData("곰솔(전체, 해안방재림)")
                dialog.combo.combo.setCurrentIndex(index)
                self.assertTrue(dialog.equation_id_label.text().startswith("D21"))
                self.assertIn(tr("국내"), dialog.equation_id_label.text())
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_settings_dialog_changes_the_planting_area_safeguard(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication, QDialog

        app = QApplication.instance() or QApplication([])
        from carbon_calculator import combined_window
        from carbon_calculator.tree_simulation import visualization_tab as vis
        from reproduce_examples import _StubPlotter

        with patch.object(vis, "QtInteractor", _StubPlotter), \
                patch.object(vis, "VegetationRenderer"), \
                patch.object(input_limits, "save_unit_areas") as saved:
            window = combined_window.CombinedMainWindow()
            try:
                titles = [action.text() for action in window.menuBar().actions()]
                self.assertIn(tr("설정(&S)"), titles)

                dialog = combined_window.PlantingAreaDialog(window)
                self.assertEqual(dialog.values(), (1.0, 0.25))
                self.assertIn("10,000", dialog.density_label.text())
                self.assertIn("40,000", dialog.density_label.text())
                dialog.tree_spin.setValue(4.0)
                self.assertIn("2,500", dialog.density_label.text())
                dialog._restore_defaults()
                self.assertEqual(dialog.values(), (1.0, 0.25))
                dialog.deleteLater()

                # Cancelling leaves the setting unchanged and saves nothing.
                with patch.object(combined_window.PlantingAreaDialog, "exec_",
                                  return_value=QDialog.Rejected):
                    window._edit_planting_area()
                self.assertEqual(input_limits.planting_unit_areas(), (1.0, 0.25))
                saved.assert_not_called()

                with patch.object(combined_window.PlantingAreaDialog, "exec_",
                                  return_value=QDialog.Accepted), \
                        patch.object(combined_window.PlantingAreaDialog, "values",
                                     return_value=(2.0, 0.5)):
                    window._edit_planting_area()
                self.assertEqual(input_limits.planting_unit_areas(), (2.0, 0.5))
                saved.assert_called_once()
                self.assertIn("2 m²", window._status_label.text())
            finally:
                window.close()
                window.deleteLater()
                app.processEvents()


class ReproducibleExampleTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language(i18n.LANG_KO)

    def test_bundled_example_workbook_reproduces_the_expected_values(self) -> None:
        import reproduce_examples

        expected = json.loads(reproduce_examples.EXPECTED_FILE.read_text(encoding="utf-8"))
        self.assertEqual(sorted(expected)[0], "Profile 1")
        self.assertEqual(len(expected), 4)
        p1 = expected["Profile 1"]
        self.assertEqual(p1["stocks_kg_c"]["0"]["total"], 198.89)
        self.assertEqual(p1["stocks_kg_c"]["30"]["total"], 3444.5)
        self.assertEqual(p1["stocks_kg_c"]["30"]["extrapolated_share_pct"], 46.2)
        self.assertEqual(expected["Profile 2"]["stocks_kg_c"]["0"]["total"], 824.88)
        self.assertEqual(expected["Profile 3"]["stocks_kg_c"]["0"]["total"], 109.08)
        with TemporaryDirectory() as tmp:
            summaries = reproduce_examples.assess_workbook(
                reproduce_examples.DEFAULT_WORKBOOK, Path(tmp), "en")
            self.assertEqual(reproduce_examples.compare(summaries, expected), [])
            self.assertEqual(len(list(Path(tmp).glob("*.xlsx"))), 4)
            self.assertTrue((Path(tmp) / "Profile 1.xlsx").exists())
        broken = json.loads(json.dumps(expected))
        broken["Profile 1"]["stocks_kg_c"]["30"]["total"] += 1.0
        self.assertEqual(len(reproduce_examples.compare(summaries, broken)), 1)


if __name__ == "__main__":
    unittest.main()
