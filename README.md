# ForeCarb

**Integrating allometric-equation management, carbon-stock assessment, and growth-scenario analysis for early-stage forest restoration**

**English** · [한국어](README.ko.md)

ForeCarb is an open-source Windows desktop application for assessing live biomass carbon stocks in mixed tree and shrub inventories at forest restoration sites. It combines allometric-equation management, unit-consistent calculation, cross-site comparison, deterministic growth scenarios over a **30-year horizon**, 3D visualization, and XLSX reporting.

This README describes ForeCarb v1.1 and follows the accompanying manuscript. Figures 1–7 and Tables 1–5 match the manuscript; installation, build, and repository guidance is provided below.

#### Code metadata

| Nr | Description | Value |
|:---:|---|---|
| C1 | Current code version | v1.1 |
| C2 | Permanent link to code/repository used for this code version | https://github.com/ISW-LAB/ForeCarb/tree/v1.1 (equation library: [`species_data.json`](species_data.json)) |
| C3 | Permanent link to Reproducible Capsule | Not applicable |
| C4 | Legal Code License | [MIT](LICENSE); [KOGL Type 1](DATA_LICENSE.md) for `species_data.json` |
| C5 | Code versioning system used | Git |
| C6 | Languages, tools, and services used | Python, PyQt5, NumPy, Matplotlib, openpyxl, Pillow, PyVista/VTK, PyInstaller, Inno Setup |
| C7 | Compilation requirements, OS & dependencies | Microsoft Windows 10/11 (64-bit); Python ≥ 3.10; `pip install -r requirements.txt`; `python main.py --lang en` |
| C8 | Developer documentation/manual | [README.en.md](README.en.md) (English); [README.ko.md](README.ko.md) (Korean); runnable example: [`reproduce_examples.py`](reproduce_examples.py) |
| C9 | Support email | [kc.jeong-isw@cbnu.ac.kr](mailto:kc.jeong-isw@cbnu.ac.kr); [gc.jo-isw@cbnu.ac.kr](mailto:gc.jo-isw@cbnu.ac.kr) |

[1. Architecture](#1-architecture-and-workflow) · [2. Equation library](#2-equation-library) · [3. Calculation](#3-calculation) · [4. Illustrative examples](#4-illustrative-examples) · [5. Install](#5-install-and-run) · [6. Edit & deploy](#6-edit-and-deploy-the-equation-library) · [7. Build](#7-build) · [8. Tests](#8-tests) · [9. Layout](#9-repository-layout) · [10. Citation](#10-citation) · [11. License](#11-license)

> [!IMPORTANT]
> **Scope.** Allometric equations define diameter–biomass relationships; diameter development is prescribed separately through annual increments. Trajectories are therefore **deterministic outcomes under the specified growth assumptions** — not validated predictions. Estimates beyond the fitted diameter range are **extrapolations**. The baseline scenario assumes that all planted individuals survive throughout the projection horizon; optional per-species survival rates produce a separate, survival-adjusted result (Section 3). Planting-area footprints and 3D geometry are software-defined settings, not ecological carrying capacity, appropriate planting density, or measured plant architecture. Confirm that the response variable, biomass component, predictor units, and measurement protocol match the intended assessment context.

---

## 1. Architecture and workflow

Python + PyQt5 for Microsoft Windows 10/11. NumPy (computation), Matplotlib (2D plots), openpyxl (XLSX), PyVista/VTK (optional 3D). Korean and English interfaces use the same computational services; the packaged application runs without a separate Python installation.

<p align="center">
  <img src="figures/paper/fig1_workflow.png" alt="Software architecture and eight-stage workflow of ForeCarb" width="100%">
</p>

> **Figure 1.** Software architecture and eight-stage workflow of ForeCarb, from equation-library management to carbon-stock assessment, scenario analysis, and reporting.

| Stage | Component | Core content |
|:---:|---|---|
| **1** | Library Manager | Define equations and parameters across four collections — coefficients, carbon fraction, fitted range, three period-specific increments (years 1–10 / 11–20 / 21–30) |
| **2** | Library Manager | Validate identifiers, duplicates, coefficients, range ordering, and expressions → save as JSON |
| **3** | Library Manager | Application loads the validated user library at startup; default release library kept as fallback |
| **4** | Assessment App | Enter site info and species / diameter / represented count. DBH and RCD entered in cm, converted to equation-native units; core-record a/b/CF overrides available |
| **5** | Assessment App | Entry- and calculation-level validation + planting-area safeguard |
| **6** | Assessment App | Shared engine evaluates each accepted record → aggregate by species and site → carbon density |
| **7** | Assessment App | 0–30-year scenarios projected from the stored increments, evaluated by the **same engine** as current stock |
| **8** | Assessment App | 2D plots, optional 3D views, cross-site comparison, XLSX export |

---

## 2. Equation library

The source compilation defines the response of each of the 22 core equations as the dry weight of the whole individual (total biomass), not separate aboveground and belowground components. The underlying data were collected directly in the Republic of Korea by whole-plant sampling (leaves/twigs, branches, stems, and roots): shrubs excavated at experimental nurseries in Sejong (2022–2025); young trees and shrubs from nurseries in Sejong, Jeongeup, Gochang, Yeongdong, Okcheon, Dangjin, Yesan, Yeoju, Sacheon, and Wando; and NIFoS data from burned and quarry restoration sites. Tables 1 and 2 list all 22 records; the [provenance ledger](docs/core_equation_provenance.tsv) lists 24 distinct equations, including all three T01 site variants. The 2025 report documents interval averaging but lacks the raw data needed to independently reconstruct all 66 stored growth increments.

The entry dialog initially displays the first item, or the first matching item after filtering. This is not a scientific recommendation: the user must select the appropriate named equation ID. Coefficient/CF overrides are available for core tree/shrub records only.

**77 equation records covering 67 distinct scientific names.** The primary tree and shrub collections contain 22 core equation records assembled in the 2025 project report from restoration and supporting studies; the domestic and international collections contain 55 equations compiled from published studies. Multiple records are retained for a species when source studies differ in geographic origin, stand condition, or biomass component — *Pinus thunbergii*, for example, has **four records**.

All 77 records are selectable in the site-assessment screen. Each record is filed under the tree or shrub input tab by its **predictor variable** — RCD records are shrubs, the rest are trees — which gives **59 tree** and **18 shrub** records.

| Collection | Records | Predictor | Stored form | Assessment | Graph basis |
|---|---:|---|---|:---:|:---:|
| Trees `TREE_BASE` | **7** | DBH (cm) | Coefficients `a, b, CF` + range + increments | ✅ | year · diameter |
| Shrubs `SHRUB_SPECIES` | **15** | RCD (fitted in mm) | Coefficients `a, b, CF` + range + increments | ✅ | year · diameter |
| Domestic `DOMESTIC_SPECIES` | **30** | DBH · RCD (+ height, density) | Expression string + range | ✅ | diameter |
| International `FOREIGN_SPECIES` | **25** | DBH · RCD · height (+ height, LAI, length) | Expression string + range | ✅ | diameter |
| **Total** | **77** | | | **77** | **77 diameter · 22 year** |

#### Table 1. Equations of the 22 core records (IDs as in the software and XLSX reports)

| ID | Scientific name | Allometric equation | Predictor | Range (cm) |
|:---:|---|---|:---:|:---:|
| ***Tree collection*** | | | | |
| T01 | *Pinus densiflora* | `Y = 0.0737·X^2.5735` | DBH | 1–15 |
| T02 | *Pinus thunbergii* | `Y = 0.0679·X^2.5770` | DBH | 1–29 |
| T03 | *Chamaecyparis obtusa* | `Y = 0.3617·X^2.0450` | DBH | 1–50 |
| T04 | *Quercus serrata* | `Y = 0.2002·X^2.3767` | DBH | 1–30 |
| T05 | *Robinia pseudoacacia* | `Y = 0.1391·X^2.5016` | DBH | 1–30 |
| T06 | *Quercus acuta* | `Y = 0.1926·X^2.4300` | DBH | 1–40 |
| T07 | *Quercus mongolica* | `Y = 0.0147·X^3.1075` | DBH | 6–30 |
| ***Shrub collection*** | | | | |
| S01 | *Euonymus japonicus* | `Y = 0.0002·(10X)^2.5` | RCD | 0.6–5.3 |
| S02 | *Rhododendron yedoense* f. *poukhanense* | `Y = 0.0003·(10X)^2.4` | RCD | 0.1–2.2 |
| S03 | *Spiraea prunifolia* | `Y = 0.00025·(10X)^2.6` | RCD | 0.5–4.4 |
| S04 | *Euonymus alatus* | `Y = 0.000022·(10X)^2.55` | RCD | 1.1–6.7 |
| S05 | *Buxus sinica* var. *insularis* | `Y = 0.000018·(10X)^2.7` | RCD | 0.8–3.0 |
| S06 | *Forsythia koreana* | `Y = 0.00028·(10X)^2.45` | RCD | 0.4–2.6 |
| S07 | *Nandina domestica* | `Y = 0.00031·(10X)^2.3` | RCD | 0.4–3.5 |
| S08 | *Viburnum erosum* | `Y = 0.00026·(10X)^2.5` | RCD | 0.7–3.9 |
| S09 | *Deutzia parviflora* | `Y = 0.00023·(10X)^2.6` | RCD | 0.4–2.5 |
| S10 | *Weigela subsessilis* | `Y = 0.00029·(10X)^2.4` | RCD | 0.6–3.9 |
| S11 | *Lespedeza bicolor* | `Y = 0.00015·(10X)^2.8` | RCD | 0.2–1.7 |
| S12 | *Syringa oblata* var. *dilatata* | `Y = 0.00005·(10X)^2.64` | RCD | 0.5–2.9 |
| S13 | *Callicarpa dichotoma* | `Y = 0.0021·(10X)^2.65` | RCD | 0.7–2.5 |
| S14 | *Ligustrum obtusifolium* | `Y = 0.00019·(10X)^2.75` | RCD | 0.4–3.5 |
| S15 | *Cornus alba* | `Y = 0.00027·(10X)^2.52` | RCD | 0.7–5.2 |

<sub>`X`: DBH or RCD (cm); `Y`: total individual biomass (kg).</sub>

#### Table 2. Inputs and sources of the 22 core records

| ID | Scientific name | CF | g1 / g2 / g3 | Sources |
|:---:|---|:---:|:---:|:---:|
| T01 | *Pinus densiflora* | 0.50 | 0.11 / 0.20 / 0.70 | 2, 4 |
| T02 | *Pinus thunbergii* | 0.50 | 0.24 / 0.32 / 0.32 | 2, 7 |
| T03 | *Chamaecyparis obtusa* | 0.50 | 0.11 / 0.23 / 0.23 | 2, 7 |
| T04 | *Quercus serrata* | 0.50 | 0.13 / 0.30 / 0.30 | 2, 7 |
| T05 | *Robinia pseudoacacia* | 0.50 | 0.14 / 0.20 / 0.20 | 2, 7 |
| T06 | *Quercus acuta* | 0.50 | 0.12 / 0.16 / 0.16 | 2, 7 |
| T07 | *Quercus mongolica* | 0.50 | 0.40 / 0.40 / 0.40 | 4, 7 |
| S01 | *Euonymus japonicus* | 0.50 | 0.30 / 0.22 / 0.22 | 6 |
| S02 | *Rhododendron yedoense* f. *poukhanense* | 0.50 | 0.31 / 0.17 / 0.17 | 6 |
| S03 | *Spiraea prunifolia* | 0.50 | 0.20 / 0.14 / 0.14 | 6 |
| S04 | *Euonymus alatus* | 0.50 | 0.38 / 0.25 / 0.25 | 6 |
| S05 | *Buxus sinica* var. *insularis* | 0.50 | 0.24 / 0.17 / 0.17 | 6 |
| S06 | *Forsythia koreana* | 0.50 | 0.16 / 0.16 / 0.16 | 3 |
| S07 | *Nandina domestica* | 0.50 | 0.24 / 0.22 / 0.22 | 5 |
| S08 | *Viburnum erosum* | 0.50 | 0.35 / 0.00 / 0.00 | 2 |
| S09 | *Deutzia parviflora* | 0.50 | 0.30 / 0.00 / 0.00 | 2 |
| S10 | *Weigela subsessilis* | 0.50 | 0.30 / 0.24 / 0.24 | 5 |
| S11 | *Lespedeza bicolor* | 0.50 | 0.10 / 0.06 / 0.06 | 2 |
| S12 | *Syringa oblata* var. *dilatata* | 0.45 | 0.25 / 0.23 / 0.23 | 3 |
| S13 | *Callicarpa dichotoma* | 0.50 | 0.24 / 0.16 / 0.16 | 5 |
| S14 | *Ligustrum obtusifolium* | 0.50 | 0.18 / 0.21 / 0.21 | 5 |
| S15 | *Cornus alba* | 0.50 | 0.29 / 0.26 / 0.26 | 5 |

<sub>CF: carbon fraction; `g1 / g2 / g3`: diameter increments (cm/year) in the three decades. CF and `g` are software inputs.</sub>

Source keys follow the 2025 compilation: 1, restoration-tree allometry (NIFoS, 2024); 2, young-tree allometry [28]; 3, garden/urban-shrub factors (KOAGI, 2024); 4, restoration-oak allometry [29]; 5–6, urban biodiversity studies [32, 31]; 7, Korean-tree biomass factors [30]. T01 additionally stores artificial-restoration (`0.0722·X^2.6044`, 1–22 cm, sources 2/4) and quarry (`0.1323·X^2.2619`, 1–25 cm, sources 1/2) variants. Bibliographic details appear in [Equation sources](#equation-sources).

- `g1 / g2 / g3`: annual diameter increment (cm yr⁻¹) in years 1–10, 11–20, and 21–30. **Zero = no prescribed growth** in that period.
- `X` = DBH for trees, RCD for shrubs, in cm. Shrub equations fitted in mm are written as **`10X`**, with fitted limits converted to cm — the original relationship is preserved without refitting.
- **Every species stores one record per site category**, and the application applies exactly the record for the selected category — there is no category-independent base equation (`SiteCategoryTests`). All four collections use the same `by_env` shape, keyed by the three categories.
- Records that the sources actually differentiate carry different values: *Pinus densiflora* uses sheet rows 1 / 2 / 3 for the three categories. Every other species is initialized identically across the three and can be differentiated in the Manager as evidence becomes available.
- **Growth factors** are applied on top of the selected record's annual diameter increments: nine factors, **three site categories × growth tiers 1–3** (default `1.0` = no adjustment). Each species is assigned a tier per category (default tier 1), and records without stored increments scale their assumed 2 % rate by the same factor. An optional per-species override takes precedence. The factors scale the 30-year scenario only; the equation is untouched, so year-0 stock does not move. Older files with one tree and one shrub factor per category are read as tiers 1 and 2.
- **Equation IDs.** Each record has an ID made of its collection letter (`T` tree, `S` shrub, `D` domestic, `I` international) and its position in the library: `T01`–`T07`, `S01`–`S15`, `D01`–`D30`, `I01`–`I25` (for example `T01` *Pinus densiflora*, `S10` *Weigela subsessilis*, `D21`–`D23` the three compiled *Pinus thunbergii* records). The entry dialog shows the ID and the XLSX report records it for every inventory record.
- Full inventory: [`species_data.json`](species_data.json).

#### Graph bases

The estimation panel plots carbon stock against either axis, selected per tab:

- **By year** — the 0–30-year deterministic scenario for the **22 primary tree and shrub records**, using stored period-specific diameter increments. The 55 domestic and international records have no stored increments and instead use an assumed 2% annual increase of the first predictor for exploratory scenarios.
- **By diameter** — carbon across the predictor axis, available for **all 77** records. Each curve spans that record's fitted range; the **20** records whose sources publish no domain are swept over a band around the entered value and flagged as such. Curves are not summed on this basis because records have different domains.

Records from the extension collections contribute to the site totals, the planting-area guard (whose per-individual areas are defined per growth form, not per species), and the Excel export. Each result table also reports the core and extension subtotals separately, so the 22-record figures remain readable. The manuscript's 3D growth examples use the same prescribed diameter increments as the primary year-based scenarios.

---

## 3. Calculation

```
B_i(t)    = a_i · [ q_i · D_i(t) ]^b_i
C_i(t)    = B_i(t) · CF_i · n_i                                        … Eq. (1)
C_site(t) = Σ C_i(t)        for i ∈ V (records retained after validation)

A_required = α_tree · Σ n_i(trees) + α_shrub · Σ n_i(shrubs)           … Eq. (2)
             defaults α_tree = 1.00 m², α_shrub = 0.25 m² per individual
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
- Eq. (2): `α_tree` and `α_shrub` are user settings (**Settings → Planting-area safeguard**; kept for later sessions and written to the report). The defaults correspond to a spacing of 1 m × 1 m and 0.5 m × 0.5 m. They only decide whether the calculation proceeds and never enter the biomass or carbon calculation.
- Eq. (5) runs **after** calculation and only flags extrapolation — it never alters trajectories. The year-based plots draw estimates outside the fitted range with dotted lines and open markers, shade the extrapolated part of the total and print the extrapolated share at year 30; the line above each plot gives the share for the selected year. The XLSX report records the first year each record leaves its fitted range (`Calculation_details`) and the extrapolated stock and share for every year (`Fitted_range_audit`). Records whose source publishes no fitted range are reported as not auditable.
- Domestic/international records use `Y_i = f_i(X_i, H_i)` via an AST allowlist (no Python `eval`). Storing no carbon fraction or increments, they apply a fixed **CF₀ = 0.5** and use an assumed 2% annual increase of the first predictor for exploratory scenarios. This is not a measured species-specific growth rate; see [GROWTH_ASSUMPTIONS.md](GROWTH_ASSUMPTIONS.md).

#### Survival-adjusted results (optional)

```
N_i(t)   = n_i · S0_i · s_i^t                                          … Eq. (6)
C_i^S(t) = C_i(t) · S0_i · s_i^t
```

- `S0_i` is the **initial survival** (%) applied to the year-0 count, as in the earlier MATLAB carbon calculator; `s_i` is the **annual survival** (%) compounded each year. Both default to 100 %, which reproduces the baseline exactly.
- Carbon scales linearly with the represented count, so Eq. (6) rescales the baseline trajectory without changing diameters or equations.
- Survival-adjusted values are reported **alongside** the all-survive baseline, never in place of it: the stock gauges draw them as a dark inner bar, the **With survival** view plots solid (all survive) against dashed (with survival) curves next to a survival-based contribution chart, and XLSX exports add a `생존률_반영` sheet. The 3D view and cross-site comparison use the baseline.

---

## 4. Illustrative examples

These examples illustrate **software behavior under the tested settings**, not agreement with independent field observations.

### 4.1 Equation-library configuration and deployment

<p align="center">
  <img width="1059" height="1125" alt="fig2_equation_library" src="https://github.com/user-attachments/assets/fcd2dc99-9dd9-4306-9f7c-27363815fa5d" />
</p>

> **Figure 2.** Equation-library management in ForeCarb, including record configuration, parameter editing, and deployment of the validated library.

The manager maintains records from four collections. Figure 2 shows the interface organized by restoration-site category, with tree and shrub subtabs and editable columns for coefficients, carbon fractions, fitted limits, and growth increments.

**(a)** add a record · **(b)** remove a record · **(c)** modify regression coefficients · **(d)** deploy the validated JSON — by rebuilding the application or applying it to an existing installation.

### 4.2 Integrated assessment of mixed tree and shrub inventories

<p align="center">
  <img src="figures/paper/fig3_assessment_workflow.png" alt="Integrated assessment workflow for Profile 1" width="100%">
</p>

> **Figure 3.** Profile 1 dashboard at year 15 (top), displaying 900.20 kg C (year 0: 198.89 kg C); (a) entry dialog with the selected equation and editable parameters; (b) trajectories and species contributions; (c) simulated 3D stand.

Profile 1 — three tree and two shrub species on a 20 m × 20 m site.

The upper overview shows the main workspace, including inventory entry and tree, shrub, and total carbon stocks at the selected scenario year. The labeled panels show **(a)** the tree/shrub entry dialog with the resolved equation, coefficients, carbon fraction, fitted range, and increments; **(b)** the 0–30-year carbon-stock trajectory and species contributions; and **(c)** the 3D stand visualization. A shared year bar synchronizes the scenario views over years 0–30.

### 4.3 Area-aware cross-site comparison

Designed to separate variation from **inventory composition** from that introduced by **area normalization**.

#### Table 3. Controlled inventories and outputs for the cross-site comparisons in Figure 4

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

The scenario illustrates how prescribed diameter increments translate into changes in carbon stock. For Profile 1, total stock increases from **198.89 kg C at year 0** to **3,444.50 kg C at year 30**.

<p align="center">
  <img src="figures/paper/fig5_trajectories.png" alt="Tree and shrub trajectories of Profile 1 with extrapolated estimates marked" width="100%">
</p>

> **Figure 5.** Profile 1 trajectories for (a) trees and (b) shrubs. Dotted lines/open markers flag extrapolation; shading shows its contribution. Year-30 extrapolated shares: trees 39.2%, shrubs 100%, whole site 46.2%.

<p align="center">
  <img src="figures/paper/fig6_growth_3d.png" alt="Simulated 3D stands of Profile 1 at years 0, 15 and 30" width="100%">
</p>

> **Figure 6.** Simulated 3D stands of Profile 1 at years 0 (a), 15 (b), and 30 (c) at a common scale, with whole-site totals and extrapolated shares. Geometry is software-defined.

| Year | Trees (kg C) | Shrubs (kg C) | **Total (kg C)** | Extrapolated share |
|:---:|---:|---:|---:|---:|
| 0 | 194.15 | 4.74 | **198.89** | 0.0 % |
| 15 | 763.85 | 136.35 | **900.20** | 15.1 % |
| 30 | 3,050.16 | 394.34 | **3,444.50** | 46.2 % |

**Extrapolated share.** Initial-diameter validation applies only to year 0, so projected diameters can leave the fitted ranges. In Profile 1 three of the five records do: *Rhododendron yedoense* f. *poukhanense* from year 4 (2.44 cm > 2.2 cm), *Weigela subsessilis* from year 9 (4.20 cm > 3.9 cm) and *Pinus densiflora* in year 30 (15.1 cm > 15 cm). Estimates outside the fitted ranges account for **15.1 % of the total at year 15** (136.35 of 900.20 kg C) and **46.2 % at year 30** (1,590.13 of 3,444.50 kg C; 39.2 % of the tree stock and 100 % of the shrub stock). The application shows these shares in the plots and in the XLSX report. The 3D views are software-defined scenario geometry, not measured plant architecture.

### 4.5 Two-level record validation and planting-area safeguard

#### Table 4. Test cases and outcomes for diameter-range validation and the planting-area safeguard

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

#### Table 5. Inputs and outputs of Profiles 1–3 (common-area inventories of Table 3; CF 0.50)

| Profile | ID | Record | D(0) (cm) | n | B(0) (kg) | C(0) (kg C) | D(30) (cm) | C(30) (kg C) | First year outside range |
|:---:|:---:|---|---:|---:|---:|---:|---:|---:|:---:|
| 1 | T01 | *Pinus densiflora* | 5.0 | 30 | 4.637 | 69.56 | 15.1 | 1,195.79 | 30 |
|  | T04 | *Quercus serrata* | 4.0 | 20 | 5.400 | 54.00 | 11.3 | 637.26 | – |
|  | T07 | *Quercus mongolica* | 8.0 | 15 | 9.412 | 70.59 | 20.0 | 1,217.11 | – |
|  | S02 | *Rhododendron yedoense* f. *poukhanense* | 1.2 | 40 | 0.1167 | 2.33 | 7.7 | 202.18 | 4 |
|  | S10 | *Weigela subsessilis* | 1.5 | 25 | 0.1928 | 2.41 | 9.3 | 192.16 | 9 |
| | | **Site total** | | | | **198.89** | | **3,444.50** | |
| 2 | T01 | *Pinus densiflora* | 7.0 | 60 | 11.024 | 330.71 | 17.1 | 3,293.85 | 28 |
|  | T04 | *Quercus serrata* | 8.0 | 25 | 28.044 | 350.55 | 15.3 | 1,636.93 | – |
|  | T07 | *Quercus mongolica* | 10.0 | 15 | 18.829 | 141.21 | 22.0 | 1,636.65 | – |
|  | S10 | *Weigela subsessilis* | 1.5 | 25 | 0.1928 | 2.41 | 9.3 | 192.16 | 9 |
| | | **Site total** | | | | **824.88** | | **6,759.60** | |
| 3 | T04 | *Quercus serrata* | 4.0 | 20 | 5.400 | 54.00 | 11.3 | 637.26 | – |
|  | T07 | *Quercus mongolica* | 6.0 | 10 | 3.850 | 19.25 | 18.0 | 584.85 | – |
|  | S02 | *Rhododendron yedoense* f. *poukhanense* | 1.8 | 120 | 0.3089 | 18.53 | 8.3 | 726.21 | 2 |
|  | S10 | *Weigela subsessilis* | 2.0 | 90 | 0.3845 | 17.30 | 9.8 | 784.43 | 7 |
| | | **Site total** | | | | **109.08** | | **2,732.75** | |

<sub>`D`: DBH/RCD; `n`: count; `B`: individual biomass; `C`: record carbon. Final column: first out-of-range year (–: none through year 30).</sub>

### 4.6 Result reporting

<p align="center">
  <img src="figures/paper/fig7_xlsx_export.png" alt="Example XLSX output from ForeCarb" width="100%">
</p>

> **Figure 7.** Selected XLSX fields for Profiles 1–3: (a) stocks/extrapolated shares at selected years; (b) year-0 contributions, IDs, overrides, first out-of-range years, and year-30 status. Species shares use tree/shrub subtotals. Displayed fields are rearranged; complete workbooks retain all records and years.

**(a)** total stock and extrapolated share per profile at selected years · **(b)** species-level stocks and shares, equation IDs, parameter changes, the first year outside the fitted range, and the status at year 30. Additional worksheets hold site-comparison results and associated figures.

Two further worksheets document how each value was obtained. **`Calculation_details`** lists, for every accepted inventory record, the equation ID, collection, library key, equation applied, predictor and input value, predictor scaling `q`, secondary input, biomass per individual, `CF`, count, carbon stock, any user change to `a`, `b` or `CF` (library value → value used), the fitted range, the growth setting, the first year outside the fitted range and the status at year 30; records excluded from the calculation are listed with the reason, and the header gives the software version, the content fingerprint (SHA-256) of the equation library, the site and the planting areas used by the safeguard. **`Fitted_range_audit`** gives, for every year, the totals, the stock obtained by extrapolation, its share, and the flag `v_i(t)` of each record.

---

## 5. Install and run

| Executable | Role |
|---|---|
| `ForeCarb.exe` | **Assessment Application** — site assessment, comparison, scenarios |
| `ForeCarb-Equation-Library-Manager.exe` | **Equation Library Manager** — equation editing, validation, deployment |

The installer bundles both programs and Python. Revision 1.1 binaries have not yet been rebuilt; the expected installer output is `FORECAST-SW_Setup_1.1.exe`. From source:

```powershell
pip install -r requirements.txt
python main.py              # language-selection dialog
python main.py --lang en    # English
python main.py --lang ko    # Korean
```

### Load and save input data

Inventories can be entered from an Excel workbook instead of adding species one by one.

| Menu | Action |
|---|---|
| **File → Load data** (`Ctrl+O`) | Creates one tab per site in the workbook and calculates immediately |
| **File → Save data** (`Ctrl+S`) | Writes the inputs of the open sites in the same format (example data if no site is open) |
| **Load data** button on a site tab | Fills only that tab from the workbook |

| Sheet | Columns |
|---|---|
| `지역` (Regions) | site name · width (m) · length (m) · site category · latitude · longitude (optional, decimal degrees) |
| `수종` (Species) | site name · type (tree/shrub) · species · diameter (cm) · count · initial survival (%) · annual survival (%) · second variable |

Korean or English headers and Korean or scientific species names are accepted; blank survival cells mean 100 %. Rows with unknown species or invalid values are skipped and listed after loading. [`presets/ForeCarb_데이터_예시.xlsx`](presets/ForeCarb_데이터_예시.xlsx) reproduces Profiles 1–3 of Table 3 and adds a survival example. User-edited coefficients (`a, b, CF`) are not stored in the workbook.

### Reproduce the manuscript examples

```powershell
python reproduce_examples.py                 # run Profiles 1–3 and check them
python reproduce_examples.py --out reports   # also write one XLSX report per site
python reproduce_examples.py --workbook my_sites.xlsx --no-check
```

The script loads the example workbook [`presets/ForeCarb_데이터_예시.xlsx`](presets/ForeCarb_데이터_예시.xlsx), runs every site through the application code path without opening the GUI (only the 3D renderer is replaced by a stub), prints the stocks at years 0, 15 and 30 with the fitted-range audit, and compares them with [`presets/expected_profiles.json`](presets/expected_profiles.json). It exits with status 0 when all values agree. The report that ForeCarb writes for Profile 1 is provided as [`presets/example_report_Profile_1.xlsx`](presets/example_report_Profile_1.xlsx). Expected totals for Profile 1 (site 20 m × 20 m, site category *post-fire site, natural restoration*):

| Year | Trees (kg C) | Shrubs (kg C) | Total (kg C) | Extrapolated (kg C) | Share |
|:---:|---:|---:|---:|---:|---:|
| 0 | 194.15 | 4.74 | **198.89** | 0.00 | 0.0 % |
| 15 | 763.85 | 136.35 | **900.20** | 136.35 | 15.1 % |
| 30 | 3,050.16 | 394.34 | **3,444.50** | 1,590.13 | 46.2 % |

---

## 6. Edit and deploy the equation library

The Manager opens `species_data.json` as editable tables (Figure 2), with validation before saving and an automatic `.bak` backup. It bundles the full core source, so it runs standalone.

Tables are organized by site category — **one tab per category** (post-fire natural, post-fire artificial, quarry artificial), each split into **tree** and **shrub**:

- Each table lists **every species of that growth form** — 59 trees and 18 shrubs — with the coefficient columns (`a, b, CF`, range, growth increments) and the equation columns (equation string, range, variables) merged into one grid. Columns that do not apply to a row are empty and cannot be edited, and a **type** column marks each row as core, domestic or international.
- Values are edited per category: the same species is adjusted independently on each of the three tabs.
- Adding or deleting a species applies to all three categories at once, so every species always has exactly one record per category.
- **Growth factor** inputs sit at the top of each category tab, one per growth tier (tier 1, 2, 3; default `1.0`). The **growth tier** column of the table shows and sets each species' tier for that category; the species' growth increments are multiplied by its tier's factor.

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

**Installer (optional):** `build_exe.py --onedir` → `build_updater.py` → compile `installer.iss` with [Inno Setup 6](https://jrsoftware.org/isdl.php) → `installer_output\FORECAST-SW_Setup_1.1.exe`.

---

## 8. Tests

```powershell
python -m unittest discover -s tests -v
```

22 regression tests reproduce Tables 3–4 and Figures 4–6: library record counts, area-normalized densities (`0.4972 / 0.3978 / 0.3315`), proportional scaling with represented count, diameter boundaries, scenario repeatability and year-zero agreement, shrub mm↔cm equivalence, execution of all 55 compatibility equations, and rejection of unsafe syntax. `tests/test_survival_preset.py` covers survival-adjusted projections (Eq. 6), the data workbook round trip, and the survival worksheet in XLSX exports. The same suite runs in CI on Windows with Python 3.10 and 3.11. `tests/test_fitted_range_audit.py` covers the fitted-range audit (Eq. 5), the extrapolated share and first years outside the fitted range for Profile 1, equation IDs, the `Calculation_details` and `Fitted_range_audit` worksheets, the planting-area settings, and the reproduction of the bundled example workbook. Build environment and checksums: [BUILD_VERIFICATION.md](BUILD_VERIFICATION.md).

---

## 9. Repository layout

```
├── main.py                        ← entry point
├── reproduce_examples.py          ← headless reproduction of the manuscript examples
├── species_data.json              ← equation library (77 records) — Tables 1–2
├── translations_ko_en.json        ← UI Korean→English strings (JSON override, no rebuild)
├── build_exe.py / build_updater.py / build_library_manager.bat
├── updater_app.py                 ← Equation Library Manager — Figure 2, stages 1–3
├── installer.iss                  ← Inno Setup installer script
├── carbon_calculator/
│   ├── calculations.py                calculation engine — Eq. (1), (3), stage 6
│   ├── input_limits.py                planting-area safeguard — Eq. (2), stage 5 (user settings)
│   ├── extrapolation.py               fitted-range audit — Eq. (5), extrapolated share
│   ├── survival.py                    survival-adjusted counts and stocks — Eq. (6)
│   ├── preset_io.py                   Excel data load/save (Regions + Species sheets)
│   ├── equation_eval.py               expression evaluation (AST allowlist)
│   ├── data.py / data2.py             coefficients and equations (JSON-load fallback)
│   ├── species_library.py             unified 77-record view (growth form, graph bases)
│   ├── main_window.py                 site assessment — Figure 3, stages 4–7
│   ├── combined_window.py             integrated window, per-site tabs — Figure 4
│   ├── tree_simulation/               3D growth visualization — Figure 6
│   ├── excel_export.py                XLSX export — Figure 7, stage 8
│   ├── main_window2.py                domestic/international screen (not exposed in v1.0)
│   ├── plotting.py / widgets.py / i18n.py / translations.py
│   └── theme.py / font_config.py / ui_scale.py / qt_locale.py
├── presets/                       ← example input workbooks and expected values
├── docs/                          ← user manual (Korean, PDF)
├── tests/test_core.py             ← 22 regression tests — Tables 3–4
├── tests/test_survival_preset.py  ← survival and data workbook tests
├── tests/test_fitted_range_audit.py ← fitted-range audit, report details, settings, reproduction
└── figures/paper/                 ← Figures 1–7 from the accompanying manuscript
```

**Troubleshooting** — missing PyQt5: `pip install -r requirements.txt` · PyInstaller build error: `--rebuild-venv` · exe exits at launch: rebuild with `--debug` and read the console · broken Korean glyphs: install "Malgun Gothic" · text too large/small: adjust `FONT_SIZE_DELTA` in `carbon_calculator\font_config.py`.

---

## 10. Citation

> Jeong, K., Jo, G., Kim, J., Kim, H.-K., Kim, C.-B., Im, S., Park, K. H., & Lee, E.
> *ForeCarb: Integrating allometric-equation management, carbon-stock assessment, and growth-scenario analysis for early-stage forest restoration.* Accompanying manuscript.

Machine-readable metadata: [`CITATION.cff`](CITATION.cff). **When using an individual allometric equation, also cite its original source publication.**

### Equation sources

Reference numbers follow the bibliography of the accompanying manuscript; the source keys are those of Table 2.

- <a id="ref-28"></a>**[28]** (source key 2) National Institute of Forest Science (2024). *Development of allometric equations for young trees.* Contract research report.
- <a id="ref-29"></a>**[29]** (source key 4) National Institute of Forest Science (2023). *Biomass measurement and development of allometric equations for oaks in forest restoration sites.* Research report.
- <a id="ref-30"></a>**[30]** (source key 7) Korea Forest Research Institute (2014). *Carbon emission factors and biomass allometric equations for major tree species in Korea.* Research report.
- <a id="ref-31"></a>**[31]** (source key 6) Korea Arboreta and Gardens Institute (2022). *Establishing a foundation for enhancing urban biodiversity.* Research report.
- <a id="ref-32"></a>**[32]** (source key 5) Korea Arboreta and Gardens Institute (2023). *Research on enhancing biodiversity in urban forests.* Research report.

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

### Planting-area sensitivity and cross-site comparison

`python reproduce_safeguard_sensitivity.py --out sensitivity.csv` reproduces the
sensitivity example of Section 3.5 of the manuscript through the application
code path. For Profile 1 (65 trees, 65 shrubs), shrub allowances of 0.10, 0.25,
0.50 and 1.00 m² give required areas of 71.50, 81.25, 97.50 and 130.00 m². All
pass at 400 m²; the last fails at 100 m². Accepted inventories retain
198.89 kg C at year 0. The script checks all eight cases, restores session
settings and never persists preferences. Expected results:
[docs/safeguard_sensitivity.csv](docs/safeguard_sensitivity.csv).

The defaults are 1.00 m² per tree and 0.25 m² per shrub (1 m and 0.5 m grids).
They are based on crown widths measured in our young-tree and shrub sampling;
the tree value also matches FAO's dense spacing. They limit the accepted counts
and never enter the biomass or carbon calculation.

For cross-site comparisons, use records with matching biomass pools and the same
area definition, and keep subtotals separate to avoid double counting. The 22
core equations estimate total (whole-plant) biomass; records in the domestic and
international collections state their own component. ForeCarb does not enforce
component compatibility automatically. Controlled examples demonstrate
computational consistency only; see [the provenance ledger](docs/core_equation_provenance.tsv).
