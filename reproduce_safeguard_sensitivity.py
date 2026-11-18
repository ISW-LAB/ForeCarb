# SPDX-License-Identifier: MIT
"""Reproduce Supplementary S7 using Profile 1 and the application code path.

Run ``python reproduce_safeguard_sensitivity.py --out sensitivity.csv``.
Only GPU rendering and modal messages are replaced. Session-only area settings
are restored on exit; no persisted user preferences or library data are changed.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from unittest.mock import patch

from reproduce_examples import DEFAULT_WORKBOOK, _StubPlotter, summarize_payload


def reproduce() -> list[dict]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from carbon_calculator import i18n, input_limits, preset_io, species_library as lib
    from carbon_calculator.data import RESTORATION_ENVIRONMENTS
    from carbon_calculator.main_window import MainWindow
    from carbon_calculator.tree_simulation import visualization_tab as vis

    app = QApplication.instance() or QApplication([])
    i18n.set_language("en")
    env = RESTORATION_ENVIRONMENTS[0]
    preset = preset_io.read_preset(
        str(DEFAULT_WORKBOOK), list(lib.records_for_kind(lib.KIND_TREE, env)),
        list(lib.records_for_kind(lib.KIND_SHRUB, env)), RESTORATION_ENVIRONMENTS)
    if preset.errors or not preset.regions:
        raise RuntimeError(f"Cannot read example workbook: {preset.errors}")
    profile = preset.regions[0]
    previous = input_limits.planting_unit_areas()
    results = []
    try:
        with patch.object(vis, "QtInteractor", _StubPlotter), \
                patch.object(vis, "VegetationRenderer"), \
                patch("carbon_calculator.main_window.QMessageBox.warning", return_value=0), \
                patch("carbon_calculator.main_window.QMessageBox.information", return_value=0):
            for site_area in (400, 100):
                for allowance, expected_area in ((0.10, 71.5), (0.25, 81.25), (0.50, 97.5), (1.00, 130.0)):
                    input_limits.set_planting_unit_areas(1.0, allowance)
                    window = MainWindow(environment=profile.environment or env,
                                        region_name="Profile 1 sensitivity",
                                        area_w=10, area_h=site_area / 10)
                    try:
                        window.apply_preset_rows(profile.rows)
                        inventory = window.region_inventory_summary()
                        assert inventory["tree_quantity"] == inventory["shrub_quantity"] == 65
                        assert abs(inventory["required_planting_area"] - expected_area) < 1e-9
                        window.on_calculate()
                        payload = window.build_export_payload()
                        accepted = payload is not None
                        assert accepted == (expected_area <= site_area)
                        stock = None
                        density = None
                        if accepted:
                            summary = summarize_payload(payload)
                            assert {r["equation_id"] for r in summary["records"]} == {"T01", "T04", "T07", "S02", "S10"}
                            stock = summary["stocks_kg_c"]["0"]["total"]
                            density = summary["density_year0_kg_c_m2"]
                            assert abs(stock - 198.89) < 0.01
                            assert abs(density - round(stock / site_area, 4)) < 0.00011
                        results.append(dict(site_area_m2=site_area, tree_allowance_m2=1.0,
                                            shrub_allowance_m2=allowance, required_area_m2=expected_area,
                                            accepted=accepted, year0_kg_c=stock,
                                            density_kg_c_m2=density))
                    finally:
                        window.visualization_tab.close()
                        window.close()
                        window.deleteLater()
                        app.processEvents()
    finally:
        input_limits.set_planting_unit_areas(*previous)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional CSV destination")
    args = parser.parse_args()
    rows = reproduce()
    for row in rows:
        print(row)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print("All 8 safeguard sensitivity cases passed.")


if __name__ == "__main__":
    main()
