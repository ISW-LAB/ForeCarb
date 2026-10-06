# ForeCarb

**Integrating allometric-equation management, carbon-stock assessment, and growth-scenario analysis for early-stage forest restoration**

**English** · [한국어](README.ko.md)

ForeCarb is an open-source Windows desktop application for assessing live biomass carbon stocks in mixed tree and shrub inventories at forest restoration sites. It combines allometric-equation management, unit-consistent calculation, cross-site comparison, deterministic growth scenarios over a **30-year horizon**, 3D visualization, and XLSX reporting.

This README describes ForeCarb v1.0 and follows the accompanying manuscript. Figure numbers and Tables 1–3 match the manuscript; installation, build, and repository guidance is provided below.

#### Code metadata

| Nr | Description | Value |
|:---:|---|---|
| C1 | Current code version | ForeCarb v1.0 |
| C2 | Permanent link to code repository | [ForeCarb repository](https://github.com/ISW-LAB/ForeCarb) |
| C3 | Permanent link to Reproducible Capsule | Not applicable |
| C4 | Legal Code License | [MIT](LICENSE); [KOGL Type 1](DATA_LICENSE.md) for `species_data.json` |
| C5 | Code versioning system used | Git |
| C6 | Languages, tools, and services used | Python, PyQt5, NumPy, Matplotlib, openpyxl, Pillow, PyVista/VTK, PyInstaller, Inno Setup |
| C7 | Compilation requirements, OS & dependencies | Windows 10/11; Python ≥ 3.10; see [`requirements.txt`](requirements.txt) |
| C8 | Developer documentation/manual | English: [README.en.md](README.en.md); Korean: [README.ko.md](README.ko.md) |
| C9 | Support email | [kc.jeong-isw@cbnu.ac.kr](mailto:kc.jeong-isw@cbnu.ac.kr); [gc.jo-isw@cbnu.ac.kr](mailto:gc.jo-isw@cbnu.ac.kr) |

[1. Architecture](#1-architecture-and-workflow) · [2. Equation library](#2-equation-library) · [3. Calculation](#3-calculation) · [4. Illustrative examples](#4-illustrative-examples) · [5. Install](#5-install-and-run) · [6. Edit & deploy](#6-edit-and-deploy-the-equation-library) · [7. Build](#7-build) · [8. Tests](#8-tests) · [9. Layout](#9-repository-layout) · [10. Citation](#10-citation) · [11. License](#11-license)

> [!IMPORTANT]
> **Scope.** Allometric equations define diameter–biomass relationships; diameter development is prescribed separately through annual increments. Trajectories are therefore **deterministic outcomes under the specified growth assumptions** — not validated predictions. Estimates beyond the fitted diameter range are **extrapolations**. Scenarios assume that all planted individuals survive throughout the projection horizon. Planting-area footprints and 3D geometry are software-defined settings, not ecological carrying capacity, appropriate planting density, or measured plant architecture. Confirm that the response variable, biomass component, predictor units, and measurement protocol match the intended assessment context.

---

## 1. Architecture and workflow

Python + PyQt5 for Windows. NumPy (computation), Matplotlib (2D plots), openpyxl (XLSX), PyVista/VTK (optional 3D). Korean and English interfaces use the same computational services; the packaged application runs without a separate Python installation.

<p align="center">
  <img src="figures/paper/fig1_workflow.png" alt="Software architecture and eight-stage workflow of ForeCarb" width="100%">
</p>

> **Figure 1.** Software architecture and eight-stage workflow of ForeCarb, from equation-library management to carbon-stock assessment, scenario analysis, and reporting.

| Stage | Component | Core content |
|:---:|---|---|
| **1** | Library Manager | Define equations and parameters across four collections — coefficients, carbon fraction, fitted range, three period-specific increments (years 1–10 / 11–20 / 21–30) |
| **2** | Library Manager | Validate identifiers, duplicates, coefficients, range ordering, and expressions → save as JSON |
| **3** | Library Manager | Application loads the validated user library at startup; default release library kept as fallback |
| **4** | Assessment App | Enter site info and species / diameter / represented count. DBH and RCD entered in cm, converted to equation-native units; record-specific overrides available |
| **5** | Assessment App | Entry- and calculation-level validation + planting-area safeguard |
| **6** | Assessment App | Shared engine evaluates each accepted record → aggregate by species and site → carbon density |
| **7** | Assessment App | 0–30-year scenarios projected from the stored increments, evaluated by the **same engine** as current stock |
| **8** | Assessment App | 2D plots, optional 3D views, cross-site comparison, XLSX export |

---

## 2. Equation library

**77 equation records covering 67 distinct scientific names.** The primary tree and shrub collections contain 22 equations developed by the research team from direct biomass measurements at restoration sites in South Korea; the domestic and international collections contain 55 equations compiled from published studies. Multiple records are retained for a species when source studies differ in geographic origin, stand condition, or biomass component — *Pinus thunbergii*, for example, has **four records**.

All 77 records are selectable in the site-assessment screen. Each record is filed under the tree or shrub input tab by its **predictor variable** — RCD records are shrubs, the rest are trees — which gives **59 tree** and **18 shrub** records.

| Collection | Records | Predictor | Stored form | Assessment | Graph basis |
|---|---:|---|---|:---:|:---:|
| Trees `TREE_BASE` | **7** | DBH (cm) | Coefficients `a, b, CF` + range + increments | ✅ | year · diameter |
| Shrubs `SHRUB_SPECIES` | **15** | RCD (fitted in mm) | Coefficients `a, b, CF` + range + increments | ✅ | year · diameter |
| Domestic `DOMESTIC_SPECIES` | **30** | DBH · RCD (+ height, density) | Expression string + range | ✅ | diameter |
| International `FOREIGN_SPECIES` | **25** | DBH · RCD · height (+ height, LAI, length) | Expression string + range | ✅ | diameter |
| **Total** | **77** | | | **77** | **77 diameter · 22 year** |

#### Table 1. Representative allometric equation records from the ForeCarb tree and shrub collections, including predictor definitions, fitted diameter ranges, and period-specific growth increments

| Scientific name | Allometric equation | Predictor | Fitted range | 1–10 | 11–20 | 21–30 | Reference |
|---|---|:---:|:---:|---:|---:|---:|---|
| ***Tree collection*** | | | | | | | |
| *Pinus densiflora* | `Y = 0.0737·X^2.5735` | DBH | 1–15 cm | 0.11 | 0.20 | 0.70 | [23](#ref-23), [24](#ref-24) |
| *Pinus thunbergii* | `Y = 0.0679·X^2.5770` | DBH | 1–29 cm | 0.24 | 0.32 | 0.32 | [23](#ref-23), [25](#ref-25) |
| *Chamaecyparis obtusa* | `Y = 0.3617·X^2.0450` | DBH | 1–50 cm | 0.11 | 0.23 | 0.23 | [23](#ref-23), [25](#ref-25) |
| *Quercus serrata* | `Y = 0.2002·X^2.3767` | DBH | 1–30 cm | 0.13 | 0.30 | 0.30 | [23](#ref-23), [25](#ref-25) |
| *Quercus mongolica* | `Y = 0.0147·X^3.1075` | DBH | 6–30 cm | 0.40 | 0.40 | 0.40 | [24](#ref-24), [25](#ref-25) |
| ***Shrub collection*** | | | | | | | |
| *Euonymus japonicus* | `Y = 0.0002·(10X)^2.5` | RCD | 0.6–5.3 cm | 0.30 | 0.22 | 0.22 | [26](#ref-26) |
| *Rhododendron yedoense* | `Y = 0.0003·(10X)^2.4` | RCD | 0.1–2.2 cm | 0.31 | 0.17 | 0.17 | [26](#ref-26) |
| *Euonymus alatus* | `Y = 0.000022·(10X)^2.55` | RCD | 1.1–6.7 cm | 0.38 | 0.25 | 0.25 | [26](#ref-26) |
| *Lespedeza bicolor* | `Y = 0.00015·(10X)^2.8` | RCD | 0.2–1.7 cm | 0.10 | 0.06 | 0.06 | [23](#ref-23) |
| *Weigela subsessilis* | `Y = 0.00029·(10X)^2.4` | RCD | 0.6–3.9 cm | 0.30 | 0.24 | 0.24 | [27](#ref-27) |

References identify the equation sources listed in the supporting reports and equation database, following the manuscript. Bibliographic details appear in [Equation sources](#equation-sources). The growth-increment columns are separate parameters; the reference mapping follows the manuscript's equation-source attribution.

- Columns 1–10, 11–20, and 21–30: annual diameter increment (cm yr⁻¹). **Zero = no prescribed growth** in that period.
- `X` = DBH for trees, RCD for shrubs, in cm. Shrub equations fitted in mm are written as **`10X`**, with fitted limits converted to cm — the original relationship is preserved without refitting.
- **Every species stores one record per site category**, and the application applies exactly the record for the selected category — there is no category-independent base equation (`SiteCategoryTests`). All four collections use the same `by_env` shape, keyed by the three categories.
- Records that the sources actually differentiate carry different values: *Pinus densiflora* uses sheet rows 1 / 2 / 3 for the three categories. Every other species is initialized identically across the three and can be differentiated in the Manager as evidence becomes available.
- **A growth factor** is applied on top of the selected record's annual diameter increments, held per category and growth form (default `1.0` = no adjustment), with an optional per-species override. It scales the 30-year scenario only; the equation is untouched, so year-0 stock does not move.
- Full inventory: [`species_data.json`](species_data.json).

#### Graph bases

The estimation panel plots carbon stock against either axis, selected per tab:

- **By year** — the 0–30-year deterministic scenario for the **22 primary tree and shrub records**, using stored period-specific diameter increments. The 55 domestic and international records have no stored increments and are excluded from the deterministic growth analysis described in the manuscript.
- **By diameter** — carbon across the predictor axis, available for **all 77** records. Each curve spans that record's fitted range; the **20** records whose sources publish no domain are swept over a band around the entered value and flagged as such. Curves are not summed on this basis because records have different domains.

Records from the extension collections contribute to the site totals, the planting-area guard (whose per-individual areas are defined per growth form, not per species), and the Excel export. Each result table also reports the core and extension subtotals separately, so the 22-record figures remain readable. The manuscript's 3D growth examples use the same prescribed diameter increments as the primary year-based scenarios.

---

## 3. Calculation

```
B_i(t)    = a_i · [ q_i · D_i(t) ]^b_i
C_i(t)    = B_i(t) · CF_i · n_i                                        … Eq. (1)
C_site(t) = Σ C_i(t)        for i ∈ V (records retained after validation)

A_required = 1.00 · Σ n_i(trees) + 0.25 · Σ n_i(shrubs)                … Eq. (2)
             → calculation halts when A_required > A_site

ρ_C(t) = C_site(t) / A_site                                            … Eq. (3)

D_i(t) = D_i(0) + Σ_{s=1..t} g_i,p(s)                                  … Eq. (4)
         p(s) = 1 (1–10 yr) · 2 (11–20 yr) · 3 (21–30 yr)

v_i(t) = 1 if D_min,i ≤ D_i(t) ≤ D_max,i, else 0                       … Eq. (5)
```

| Symbol | Meaning |
|---|---|
| `D_i(t)` | DBH or RCD **in cm** at year `t`; current stock at `t = 0` |
| `q_i` | Predictor scaling — `1` for cm-based tree equations, `10` for mm-based shrub equations |
| `n_i`, `CF_i` | Represented count; record-level carbon fraction (including overrides) |
| `v_i(t) = 0` | Post-calculation audit flag — estimate obtained by **extrapolation** |

- Eq. (1) aggregates records **individually**, so the site total preserves the power law's nonlinearity.
- `q_i` belongs to the equation record, so overrides (`a_i`, `b_i`, `CF_i`) never change it.
- Eq. (3): total stock is **independent of site area**; density varies **inversely** with it.
- Eq. (5) runs **after** calculation and only flags extrapolation — it never alters trajectories.
- Domestic/international records use `Y_i = f_i(X_i, H_i)` via an AST allowlist (no Python `eval`). Storing no carbon fraction or increments, they apply a fixed **CF₀ = 0.5** and are excluded from the deterministic growth scenario analysis described in the manuscript. Diameter-basis graphs remain available.

---

## 4. Illustrative examples

These examples illustrate **software behavior under the tested settings**, not agreement with independent field observations.

### 4.1 Equation-library configuration and deployment

<p align="center">
  <img src="figures/paper/fig2_equation_library.png" alt="Equation-library management in ForeCarb" width="100%">
</p>

> **Figure 2.** Equation-library management in ForeCarb, including record configuration, parameter editing, and deployment of the validated library.

The manager maintains records from four collections. Figure 2 shows the interface organized by restoration-site category, with tree and shrub subtabs and editable columns for coefficients, carbon fractions, fitted limits, and growth increments.

**(a)** add a record · **(b)** remove a record · **(c)** modify regression coefficients · **(d)** deploy the validated JSON — by rebuilding the application or applying it to an existing installation.

### 4.2 Integrated assessment of mixed tree and shrub inventories

<p align="center">
  <img src="figures/paper/fig3_assessment_workflow.png" alt="Integrated assessment workflow for Profile 1" width="100%">
</p>

> **Figure 3.** Integrated assessment workflow for Profile 1, including mixed tree and shrub inventory assessment, allometric-equation inspection, carbon-stock analysis, and 3D visualization.

Profile 1 — three tree and two shrub species on a 20 m × 20 m site.

The upper overview shows the main workspace, including inventory entry and tree, shrub, and total carbon stocks at the selected scenario year. The labeled panels show **(a)** the tree/shrub entry dialog with the resolved equation, coefficients, carbon fraction, fitted range, and increments; **(b)** the 0–30-year carbon-stock trajectory and species contributions; and **(c)** the 3D stand visualization. A shared year bar synchronizes the scenario views over years 0–30.

### 4.3 Area-aware cross-site comparison

Designed to separate variation from **inventory composition** from that introduced by **area normalization**.

#### Table 2. Controlled inventories and outputs for the cross-site comparisons in Figure 4

| Comparison | Profile | Site area (m²) | Tree records | Shrub records | Stock (kg C) | Density (kg C m⁻²) |
|---|:---:|:---:|---|---|---:|---:|
| **(1) Common area** | 1 | 400 | *P. densiflora* 5.0 × 30;<br>*Q. serrata* 4.0 × 20;<br>*Q. mongolica* 8.0 × 15 | *R. yedoense* f. *poukhanense* 1.2 × 40;<br>*W. subsessilis* 1.5 × 25 | 198.89 | 0.4972 |
| | 2 | 400 | *P. densiflora* 7.0 × 60;<br>*Q. serrata* 8.0 × 25;<br>*Q. mongolica* 10.0 × 15 | *W. subsessilis* 1.5 × 25 | **824.88** | 2.0622 |
| | 3 | 400 | *Q. serrata* 4.0 × 20;<br>*Q. mongolica* 6.0 × 10 | *R. yedoense* f. *poukhanense* 1.8 × 120;<br>*W. subsessilis* 2.0 × 90 | **109.08** | 0.2727 |
| **(2) Common inventory** | 1 | 400 | *P. densiflora* 5.0 × 30;<br>*Q. serrata* 4.0 × 20;<br>*Q. mongolica* 8.0 × 15 | *R. yedoense* f. *poukhanense* 1.2 × 40;<br>*W. subsessilis* 1.5 × 25 | 198.89 | **0.4972** |
| | 2 | 500 | *(unchanged)* | *(unchanged)* | 198.89 | **0.3978** |
| | 3 | 600 | *(unchanged)* | *(unchanged)* | 198.89 | **0.3315** |

<sub>Diameters are DBH for trees or RCD for shrubs, in cm. The multiplier following each diameter denotes the represented count; profiles are numbered within each comparison.</sub>

<p align="center">
  <img src="figures/paper/fig4_site_comparison.png" alt="Cross-site comparison of total carbon stock and carbon density" width="100%">
</p>

> **Figure 4.** Cross-site comparison of total carbon stock and area-normalized carbon density using three inventories at a common site area and one unchanged inventory across different site areas.

- **(a) Common area** — holding site area at 400 m² isolates inventory composition: **109.08 → 824.88 kg C** across the three inventories, reflecting differences in species composition, initial diameter, and represented count.
- **(b) Common inventory** — applying Profile 1 to 400 / 500 / 600 m² isolates site area: total stock **stays 198.89 kg C**, density falls **0.4972 → 0.3978 → 0.3315 kg C m⁻²**.

### 4.4 Deterministic growth scenario visualization

<p align="center">
  <img src="figures/paper/fig5_growth_scenario.png" alt="Deterministic growth scenario for Profile 1" width="100%">
</p>

The scenario illustrates how prescribed diameter increments translate into changes in carbon stock. For Profile 1, total stock increases from **198.89 kg C at year 0** to **3,444.50 kg C at year 30**.

> **Figure 5.** Deterministic growth scenario for Profile 1 at **(a) year 0** and **(b) year 30**, showing tree, shrub, and total carbon stocks together with the corresponding 3D stand visualizations.

| Year | Trees (kg C) | Shrubs (kg C) | **Total (kg C)** |
|:---:|---:|---:|---:|
| 0 | 194.15 | 4.74 | **198.89** |
| 30 | 3,050.16 | 394.34 | **3,444.50** |

Year-30 values may include **extrapolated estimates** where projected diameters exceed the fitted ranges. The 3D views are software-defined scenario geometry, not measured plant architecture.

### 4.5 Two-level record validation and planting-area safeguard

#### Table 3. Test cases and outcomes for diameter-range validation and the planting-area safeguard

| Check | Test case | Criterion | Outcome |
|---|---|---|---|
| ***(a) Diameter-range validation*** | | | |
| Tree entry | *P. densiflora*, DBH = 20 cm | Fitted range: 1–15 cm | **Rejected** |
| Shrub entry | *W. subsessilis*, RCD = 5.0 cm | Fitted range: 0.6–3.9 cm | **Rejected** |
| Fitted limits | DBH = 1.00 or 15.00 cm | Limits inclusive | **Accepted** |
| Outside limits | DBH = 0.99 or 15.01 cm | Outside fitted range | **Rejected** |
| Calculation level | Out-of-range record bypassing entry validation | Fitted-range check | **Excluded before calculation** |
| ***(b) Planting-area safeguard (A_site = 100 m²)*** | | | |
| Area exceeded | `A_required = 105.00 m²` | `A_required > A_site` | **Calculation halted** |
| Area boundary | `A_required = 100.00 m²` | `A_required = A_site` | **Accepted** |

Values outside the fitted ranges were rejected and values at the limits accepted; records bypassing the entry check were excluded during calculation; the area safeguard halted calculation only when the requirement **exceeded** the site area.

### 4.6 Result reporting

<p align="center">
  <img src="figures/paper/fig6_xlsx_export.png" alt="Example XLSX output from ForeCarb" width="100%">
</p>

> **Figure 6.** Example XLSX output from ForeCarb showing site-level carbon-stock projections and species-level carbon contributions.

**(a)** annual tree, shrub, and total stocks per profile across the scenario period · **(b)** species-level stocks and relative contributions. Additional worksheets hold site-comparison results and associated figures.

---

## 5. Install and run

| Executable | Role |
|---|---|
| `ForeCarb.exe` | **Assessment Application** — site assessment, comparison, scenarios |
| `ForeCarb-Equation-Library-Manager.exe` | **Equation Library Manager** — equation editing, validation, deployment |

Both are installed by `ForeCarb_Setup_1.0.exe` (no Python required). From source:

```powershell
pip install -r requirements.txt
python main.py              # language-selection dialog
python main.py --lang en    # English
python main.py --lang ko    # Korean
```

---

## 6. Edit and deploy the equation library

The Manager opens `species_data.json` as editable tables (Figure 2), with validation before saving and an automatic `.bak` backup. It bundles the full core source, so it runs standalone.

Tables are organized by site category — **one tab per category** (post-fire natural, post-fire artificial, quarry artificial), each split into **tree** and **shrub**:

- Each table lists **every species of that growth form** — 59 trees and 18 shrubs — with the coefficient columns (`a, b, CF`, range, growth increments) and the equation columns (equation string, range, variables) merged into one grid. Columns that do not apply to a row are empty and cannot be edited, and a **type** column marks each row as core, domestic or international.
- Values are edited per category: the same species is adjusted independently on each of the three tabs.
- Adding or deleting a species applies to all three categories at once, so every species always has exactly one record per category.
- **Growth factor** inputs sit at the top of each category tab, one for trees and one for shrubs (default `1.0`); they multiply that category's growth increments.

| Method | Description | Python required |
|---|---|:---:|
| **Rebuild the executable** | Rebuild `ForeCarb.exe` from the new `species_data.json` | 3.10+ |
| **Apply the JSON** | Copy `species_data.json` next to the existing `ForeCarb.exe` | No |

> When adding a species, fill in the scientific-name column so English mode displays it.

UI strings follow the same pattern: [`translations_ko_en.json`](translations_ko_en.json) holds every Korean-source → English string used by the interface. Edit the English column and restart — no rebuild required; place the edited file next to a deployed `ForeCarb.exe` to update it the same way.

---

## 7. Build

```powershell
python build_exe.py                  # onefile (default) · --onedir · --debug
python build_exe.py --clean-cache    # remove build/ and dist/ first
python build_exe.py --rebuild-venv   # force-recreate the build venv
python build_updater.py              # Equation Library Manager (or build_library_manager.bat)
```

`pyinstaller` need not be installed separately — the scripts create a dedicated venv (`~\.carboncalc_build_venv`); only the first build takes a few minutes. `species_data.json` is bundled automatically.

**Installer (optional):** `build_exe.py --onedir` → `build_updater.py` → compile `installer.iss` with [Inno Setup 6](https://jrsoftware.org/isdl.php) → `installer_output\ForeCarb_Setup_1.0.exe`.

---

## 8. Tests

```powershell
python -m unittest discover -s tests -v
```

22 regression tests reproduce Tables 2–3 and Figures 4–5: library record counts, area-normalized densities (`0.4972 / 0.3978 / 0.3315`), proportional scaling with represented count, diameter boundaries, scenario repeatability and year-zero agreement, shrub mm↔cm equivalence, execution of all 55 compatibility equations, and rejection of unsafe syntax. The same suite runs in CI on Windows with Python 3.10 and 3.11. Build environment and checksums: [BUILD_VERIFICATION.md](BUILD_VERIFICATION.md).

---

## 9. Repository layout

```
├── main.py                        ← entry point
├── species_data.json              ← equation library (77 records) — Table 1
├── translations_ko_en.json        ← UI Korean→English strings (JSON override, no rebuild)
├── build_exe.py / build_updater.py / build_library_manager.bat
├── updater_app.py                 ← Equation Library Manager — Figure 2, stages 1–3
├── installer.iss                  ← Inno Setup installer script
├── carbon_calculator/
│   ├── calculations.py                calculation engine — Eq. (1), (3), stage 6
│   ├── input_limits.py                planting-area safeguard — Eq. (2), stage 5
│   ├── equation_eval.py               expression evaluation (AST allowlist)
│   ├── data.py / data2.py             coefficients and equations (JSON-load fallback)
│   ├── species_library.py             unified 77-record view (growth form, graph bases)
│   ├── main_window.py                 site assessment — Figure 3, stages 4–7
│   ├── combined_window.py             integrated window, per-site tabs — Figure 4
│   ├── tree_simulation/               3D growth visualization — Figure 5
│   ├── excel_export.py                XLSX export — Figure 6, stage 8
│   ├── main_window2.py                domestic/international screen (not exposed in v1.0)
│   ├── plotting.py / widgets.py / i18n.py / translations.py
│   └── theme.py / font_config.py / ui_scale.py
├── tests/test_core.py             ← 22 regression tests — Tables 2–3
└── figures/paper/                 ← Figures 1–6 from the accompanying manuscript
```

**Troubleshooting** — missing PyQt5: `pip install -r requirements.txt` · PyInstaller build error: `--rebuild-venv` · exe exits at launch: rebuild with `--debug` and read the console · broken Korean glyphs: install "Malgun Gothic" · text too large/small: adjust `FONT_SIZE_DELTA` in `carbon_calculator\font_config.py`.

---

## 10. Citation

> Jeong, K., Jo, G., Kim, J., Kim, H.-K., Kim, C.-B., Im, S., Park, K. H., & Lee, E.
> *ForeCarb: Integrating allometric-equation management, carbon-stock assessment, and growth-scenario analysis for early-stage forest restoration.* Accompanying manuscript.

Machine-readable metadata: [`CITATION.cff`](CITATION.cff). **When using an individual allometric equation, also cite its original source publication.**

### Equation sources

Reference numbers match Table 1 and the bibliography of the accompanying manuscript.

- <a id="ref-23"></a>**[23]** National Institute of Forest Science (2024). *Development of allometric equations for young trees.* Contract research report.
- <a id="ref-24"></a>**[24]** National Institute of Forest Science (2023). *Biomass measurement and development of allometric equations for oaks in forest restoration sites.* Research report.
- <a id="ref-25"></a>**[25]** Korea Forest Research Institute (2014). *Carbon emission factors and biomass allometric equations for major tree species in Korea.* Research report.
- <a id="ref-26"></a>**[26]** Korea Arboreta and Gardens Institute (2022). *Establishing a foundation for enhancing urban biodiversity.* Research report.
- <a id="ref-27"></a>**[27]** Korea Arboreta and Gardens Institute (2023). *Research on enhancing biodiversity in urban forests.* Research report.

**Contact**: [kc.jeong-isw@cbnu.ac.kr](mailto:kc.jeong-isw@cbnu.ac.kr) · [gc.jo-isw@cbnu.ac.kr](mailto:gc.jo-isw@cbnu.ac.kr)

---

## 11. License

| Scope | License |
|---|---|
| Source code, build scripts, documentation, repository figures | [MIT License](LICENSE) |
| Scientific equation library in `species_data.json` | [KOGL Type 1 (Attribution)](DATA_LICENSE.md) |

Individual allometric equations must retain the bibliographic information of their original sources — see [DATA_LICENSE.md](DATA_LICENSE.md).

---

<sub>Supported by IPET (RS-2024-00398561, MAFRA), IITP (IITP-2026-RS-2020-II201462, MSIT), NRF (RS-2025-25430681, Ministry of Education), and NIFoS (FE0100-2022-01-2026), Republic of Korea.</sub>
