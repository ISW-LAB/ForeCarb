# FORECAST-SW v1.1

FORECAST-SW v1.1 (ForeCarb v1.1) is the source revision prepared for the
revised SoftwareX manuscript. It adds the audit and provenance features requested
in peer review; the allometric equations, coefficients, carbon fractions and
growth increments of the equation library are unchanged, and every value of the
manuscript examples computed with v1.0 is reproduced.

The release is tagged `v1.1`, which is the version cited in the manuscript; it does not include rebuilt v1.1 binaries. The documentation follows the manuscript: the source compilation defines the response of the 22 core equations as the dry weight of the whole individual (total biomass), and the planting-area defaults are based on crown widths measured in our young-tree and shrub sampling.

## Fitted-range audit of growth scenarios

- Every projected estimate is now labelled by the audit flag
  `v_i(t) = 1 if D_min,i <= D_i(t) <= D_max,i else 0`
  (`carbon_calculator/extrapolation.py`). The audit only labels estimates; it
  never changes a trajectory.
- The year-based plots draw estimates outside the fitted range with dotted
  lines and open markers, shade the extrapolated part of the total, and print
  the extrapolated share at year 30. A line above each plot reports, for the
  selected year, the number of records outside their fitted range and the
  extrapolated share of the tree or shrub stock and of the site total.
- Records whose source publishes no fitted range are reported as not auditable
  rather than being counted as within range.

## Calculation details in the XLSX report

- New sheet `Calculation_details` (`계산근거`): for each accepted inventory
  record the equation ID, collection, library key, equation applied, predictor,
  input value, predictor scaling, secondary input, biomass per individual,
  carbon fraction, count, carbon stock, user changes to `a`, `b` or `CF`
  (library value → value used), fitted range, growth setting, first year
  outside the fitted range, and the status at year 30. Records excluded from
  the calculation are listed with the reason. The sheet header records the
  software version, the content fingerprint of the equation library, the site,
  and the planting areas used by the safeguard.
- New sheet `Fitted_range_audit` (`적합범위_점검`): year-by-year totals, the
  carbon stock obtained by extrapolation, its share, and the flag of each record.
- Equation IDs are the collection letter (T tree, S shrub, D domestic,
  I international) followed by the position of the record in the library, for
  example `T01` for *Pinus densiflora*. The entry dialog shows the ID.
- Figures embedded in a report are rendered at a fixed size, so plots on tabs
  that were never opened are no longer cramped.

## Planting-area safeguard

- The planting areas per tree and per shrub are user settings
  (Settings > Planting-area safeguard). The defaults remain 1.00 and 0.25 m2,
  the values are kept for later sessions, and the values in use are written to
  the report. They never enter the biomass or carbon calculation.

## Reproducible examples

- `reproduce_examples.py` runs the example inventories of the manuscript
  (the example workbook in `presets/`) through
  the application code path without opening the GUI, prints the stocks at
  years 0, 15 and 30 with the fitted-range audit, compares them with
  `presets/expected_profiles.json`, and can write the XLSX reports.
- `presets/example_report_Profile_1.xlsx` is the report that the application
  writes for Profile 1.

## Verification

- 20 regression tests were added (`tests/test_fitted_range_audit.py`); the suite
  now has 80 tests. For Profile 1 the tests fix the totals 198.89, 900.20 and
  3,444.50 kg C at years 0, 15 and 30, the extrapolated share of 46.2 % at
  year 30, and the first years outside the fitted range (*Rhododendron yedoense*
  f. *poukhanense* 4, *Weigela subsessilis* 9, *Pinus densiflora* 30).

# FORECAST-SW v1.0

FORECAST-SW v1.0 is the first public, citable release evaluated in the accompanying
SoftwareX manuscript. This release establishes a synchronized baseline for the
scientific library, graphical interface, packaging metadata, citation file,
documentation, regression tests, and Windows distribution artifacts.

## Evaluated scope

- Primary workflow: 22 native records (seven trees and 15 shrubs)
- Compatibility library: 55 records (30 domestic and 25 international)
- Complete library: 77 equation records covering 67 distinct scientific names
- Supported release environment: Windows 10 and 11 with Python 3.10 or newer
- User outputs: current stock summaries, deterministic 0-50-year scenarios,
  cross-site comparisons, 2-D and 3-D views, and XLSX reports

The 22 native records are the operational coverage evaluated in the article.
The 55 compatibility records remain available to the Equation Library Manager
and equation evaluator but are not selectable in the primary site-assessment
interface.

## Verification and hardening

- New installations now open with an English-only language-selection dialog
  and English selected by default. Legacy Korean preferences from earlier
  package identifiers are not imported, while Korean remains available from
  the Language menu.
- English-mode coverage now includes domestic/international species prefixes,
  scientific species names, warnings, charts, legends, and workbook labels.
- The interface and XLSX reports now label the legacy site-category field as
  descriptive metadata; it does not select or modify allometric coefficients.
- Tree DBH and shrub RCD now share a centimetre-based public contract across
  inputs, validity ranges, tables, plots, visualizations, and XLSX exports.
  Legacy shrub coefficients fitted with RCD in millimetres remain unchanged;
  an explicit analytical adapter converts centimetre inputs immediately before
  equation evaluation and preserves the previous numerical results.
- The former absolute 1,000-individual warning has been replaced by a
  calculation-blocking site-area safeguard. The software now sums the default
  footprints of all accepted tree and shrub entries (1.00 and 0.25 m² per
  individual, respectively) and reports the component areas and excess when
  the combined requirement exceeds the configured site area. These values are
  input safeguards rather than species-specific planting recommendations.
- The multi-profile comparison dashboard now presents accepted tree and shrub
  counts, their configured planting areas, the combined site-area requirement,
  component carbon stocks, total stock, and area-normalized carbon density in
  one auditable view. Total stock and normalized density are also displayed as
  paired charts in both the dashboard and the combined XLSX report. A shared
  tested calculation service now defines the normalization as total carbon
  stock divided by positive site area.
- The interface version is imported from one package module, while a regression
  test checks the same value against the citation file, installer, and release
  notes.
- Windows executable resources identify the Assessment Application and Equation
  Library Manager as FORECAST-SW version 1.0 components.
- The Equation Library Manager provides a larger minimum font, high-DPI-aware
  scaling, expanded table rows and controls, a four-step workflow guide, and
  visually distinct primary and destructive actions for improved readability.
- Equation strings are evaluated through an abstract-syntax-tree allowlist;
  Python `eval` is not used.
- A tracked regression suite verifies the scientific core, data-library
  counts, every compatibility equation, boundary guards, deterministic
  scenarios, and rejection of unsafe expression syntax.
- A Windows continuous-integration workflow runs the suite with Python 3.10
  and 3.11.

## Licensing

The code, build scripts, documentation, and repository figures use the MIT
License. The scientific equation library in `species_data.json` uses KOGL Type
1 (Attribution), as described in `DATA_LICENSE.md` and the JSON schema metadata.

## Reproduction

Install the dependencies listed in `requirements.txt`, run the source entry
point as documented in `README.en.md`, or reproduce the Windows executable and
installer with the documented build scripts. The `v1.0` release tag and its
commit identify the exact source state evaluated in the manuscript.
