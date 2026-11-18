# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""Reproduce the worked examples of the accompanying manuscript without opening the GUI.

The script loads an input workbook (by default the example workbook in
``presets/``, which holds the inventories of Profiles 1-3), runs every site through
the same code path as the Assessment Application, prints the carbon stocks at
years 0, 15 and 30 together with the fitted-range audit, and compares the
numbers with ``presets/expected_profiles.json``.

Usage::

    python reproduce_examples.py                 # run and check the bundled examples
    python reproduce_examples.py --out reports   # also write one XLSX report per site
    python reproduce_examples.py --workbook my_sites.xlsx --no-check
    python reproduce_examples.py --lang ko

The exit status is 0 when every checked value agrees with the expected value
(to 0.01 kg C and 0.1 percentage point) and 1 otherwise.

Only the 3-D renderer is replaced by a stub, because it needs a GPU context;
inventory validation, carbon calculation, growth scenarios, the fitted-range
audit and the XLSX export are the application's own.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = ROOT / "presets" / "ForeCarb_데이터_예시.xlsx"
EXPECTED_FILE = ROOT / "presets" / "expected_profiles.json"
CHECK_YEARS = (0, 15, 30)
STOCK_TOLERANCE_KG = 0.01
SHARE_TOLERANCE_PCT = 0.1


def _series_sum(category: dict, year: int) -> float:
    projection = category.get("projection") or {}
    return float(sum(s["carbon"][year] for s in projection.get("series", [])))


def summarize_payload(payload: dict) -> dict:
    """Reduce an export payload to the numbers reported in the manuscript."""
    region = payload["region"]
    audit = payload.get("audit") or {}
    stocks = {}
    for year in CHECK_YEARS:
        tree = _series_sum(payload["tree"], year)
        shrub = _series_sum(payload["shrub"], year)
        stocks[str(year)] = {
            "tree": round(tree, 2), "shrub": round(shrub, 2), "total": round(tree + shrub, 2),
            "extrapolated": round(float(audit["extrapolated"][year]), 2) if audit else 0.0,
            "extrapolated_share_pct": round(float(audit["share"][year]), 1) if audit else 0.0,
        }
    survival = {}
    for year in CHECK_YEARS:
        total = 0.0
        for key in ("tree", "shrub"):
            series = (payload[key].get("survival") or {}).get("with_survival")
            if series:
                total += float(series[year])
        survival[str(year)] = round(total, 2)
    records = []
    for key in ("tree", "shrub"):
        for row in payload[key]["rows"]:
            records.append({
                "equation_id": row["equation_id"],
                "diameter_cm": row["diameter"],
                "count": row["quantity"],
                "carbon_kg": round(float(row["carbon"]), 2),
                "first_year_outside_range": row["first_outside"],
                "carbon_year30_kg": round(float(row["final_carbon"]), 2),
            })
    area = float(region["area"])
    from carbon_calculator.species_names_en import ENVIRONMENT_EN

    return {
        "site_area_m2": area,
        "site_category": ENVIRONMENT_EN.get(region["environment"], region["environment"]),
        "stocks_kg_c": stocks,
        "density_year0_kg_c_m2": round(stocks["0"]["total"] / area, 4) if area > 0 else None,
        "with_survival_kg_c": survival,
        "records": records,
        "excluded_rows": sum(len(payload[key].get("excluded") or []) for key in ("tree", "shrub")),
    }


class _StubPlotter:
    """Stand-in for the pyvistaqt interactor (the 3-D view is not needed here)."""

    def __new__(cls, parent=None, **_kwargs):
        from PyQt5.QtWidgets import QWidget

        widget = QWidget(parent)
        widget.iren = Mock()
        widget.interactor = Mock()
        widget.set_background = lambda *a, **k: None
        widget.enable_terrain_style = lambda *a, **k: None
        widget.clear_actors = lambda *a, **k: None
        widget.add_text = lambda *a, **k: None
        return widget


def assess_workbook(workbook: Path, out_dir: Path | None = None, language: str = "en") -> dict:
    """Run every site of ``workbook`` and return ``{site name: summary}``.

    When ``out_dir`` is given, the standard XLSX report of each site is written
    there as ``<site name>.xlsx``.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])

    from carbon_calculator import i18n, preset_io, species_library as lib
    from carbon_calculator.data import RESTORATION_ENVIRONMENTS
    from carbon_calculator.excel_export import export_carbon1_to_excel
    from carbon_calculator.main_window import MainWindow
    from carbon_calculator.tree_simulation import visualization_tab as vis

    i18n.set_language(language)
    default_env = RESTORATION_ENVIRONMENTS[0]
    tree_names = list(lib.records_for_kind(lib.KIND_TREE, default_env))
    shrub_names = list(lib.records_for_kind(lib.KIND_SHRUB, default_env))
    result = preset_io.read_preset(str(workbook), tree_names, shrub_names, RESTORATION_ENVIRONMENTS)
    for message in list(result.errors) + list(result.notes):
        print(f"  note: {message}")

    summaries: dict = {}
    messages: list = []

    def _collect(_parent, title, text, *_args, **_kwargs):
        messages.append(f"{title}: {text}")
        return 0

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(vis, "QtInteractor", _StubPlotter), \
            patch.object(vis, "VegetationRenderer"), \
            patch("carbon_calculator.main_window.QMessageBox.warning", _collect), \
            patch("carbon_calculator.main_window.QMessageBox.information", _collect):
        for region in result.regions:
            window = MainWindow(environment=region.environment or default_env,
                                region_name=region.name,
                                area_w=region.width_m, area_h=region.height_m)
            try:
                # Lay the window out at a typical desktop size so that the figures
                # embedded in the report have the proportions seen in the application.
                window.resize(1680, 1000)
                window.show()
                app.processEvents()
                window.apply_preset_rows(region.rows)
                window.on_calculate()
                app.processEvents()
                payload = window.build_export_payload()
                if payload is None:
                    print(f"  {region.name}: no accepted inventory record")
                    continue
                summaries[region.name] = summarize_payload(payload)
                if out_dir is not None:
                    target = out_dir / f"{MainWindow._safe_filename(region.name)}.xlsx"
                    export_carbon1_to_excel(str(target), payload)
                    print(f"  wrote {target}")
            finally:
                window.visualization_tab.close()
                window.close()
                window.deleteLater()
                app.processEvents()
    for message in messages:
        print(f"  message: {message}")
    return summaries


def _print_summary(name: str, summary: dict) -> None:
    print(f"\n{name}  (site area {summary['site_area_m2']:g} m2)")
    print("  year      trees     shrubs      total   extrapolated   share")
    for year in CHECK_YEARS:
        s = summary["stocks_kg_c"][str(year)]
        print(f"  {year:>4} {s['tree']:>10,.2f} {s['shrub']:>10,.2f} {s['total']:>10,.2f} "
              f"{s['extrapolated']:>14,.2f} {s['extrapolated_share_pct']:>6.1f} %")
    print(f"  carbon density at year 0: {summary['density_year0_kg_c_m2']:.4f} kg C m-2")
    survival = summary["with_survival_kg_c"]
    if abs(survival["30"] - summary["stocks_kg_c"]["30"]["total"]) > STOCK_TOLERANCE_KG:
        print("  with survival: " + ", ".join(
            f"year {year}: {survival[str(year)]:,.2f} kg C" for year in CHECK_YEARS))
    for record in summary["records"]:
        first = record["first_year_outside_range"]
        status = "within fitted range to year 30" if first is None else f"outside fitted range from year {first}"
        print(f"    {record['equation_id']}  {record['diameter_cm']:g} cm x {record['count']}: "
              f"{record['carbon_kg']:,.2f} kg C now, {record['carbon_year30_kg']:,.2f} kg C at year 30; {status}")


def compare(summaries: dict, expected: dict) -> list:
    """Return a list of human-readable differences (empty when everything agrees)."""
    problems = []
    for name, want in expected.items():
        got = summaries.get(name)
        if got is None:
            problems.append(f"{name}: site missing from the results")
            continue
        for year in CHECK_YEARS:
            for field in ("tree", "shrub", "total", "extrapolated"):
                a, b = got["stocks_kg_c"][str(year)][field], want["stocks_kg_c"][str(year)][field]
                if abs(a - b) > STOCK_TOLERANCE_KG:
                    problems.append(f"{name}: year {year} {field} = {a:.2f}, expected {b:.2f}")
            a = got["stocks_kg_c"][str(year)]["extrapolated_share_pct"]
            b = want["stocks_kg_c"][str(year)]["extrapolated_share_pct"]
            if abs(a - b) > SHARE_TOLERANCE_PCT:
                problems.append(f"{name}: year {year} extrapolated share = {a:.1f} %, expected {b:.1f} %")
            a, b = got["with_survival_kg_c"][str(year)], want["with_survival_kg_c"][str(year)]
            if abs(a - b) > STOCK_TOLERANCE_KG:
                problems.append(f"{name}: year {year} with survival = {a:.2f}, expected {b:.2f}")
        first_got = {(r["equation_id"], r["diameter_cm"]): r["first_year_outside_range"] for r in got["records"]}
        first_want = {(r["equation_id"], r["diameter_cm"]): r["first_year_outside_range"] for r in want["records"]}
        if first_got != first_want:
            problems.append(f"{name}: first years outside the fitted range differ: {first_got} != {first_want}")
        if abs(got["density_year0_kg_c_m2"] - want["density_year0_kg_c_m2"]) > 1e-4:
            problems.append(f"{name}: density = {got['density_year0_kg_c_m2']}, "
                            f"expected {want['density_year0_kg_c_m2']}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK,
                        help="input workbook (default: the bundled example inventories)")
    parser.add_argument("--out", type=Path, default=None,
                        help="directory for one XLSX report per site")
    parser.add_argument("--lang", choices=("en", "ko"), default="en",
                        help="language of the XLSX reports (default: en)")
    parser.add_argument("--no-check", action="store_true",
                        help="do not compare with presets/expected_profiles.json")
    parser.add_argument("--write-expected", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    # Messages can contain characters outside the console code page (for example on a
    # Korean Windows console); replace them instead of failing.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    print(f"Input workbook: {args.workbook}")
    summaries = assess_workbook(args.workbook, args.out, args.lang)
    for name, summary in summaries.items():
        _print_summary(name, summary)

    if args.write_expected is not None:
        args.write_expected.write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nExpected values written to {args.write_expected}")
        return 0
    if args.no_check:
        return 0

    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    problems = compare(summaries, expected)
    if problems:
        print("\nMISMATCH with presets/expected_profiles.json:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"\nAll {len(expected)} sites agree with presets/expected_profiles.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
