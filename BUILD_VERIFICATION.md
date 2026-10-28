# FORECAST-SW v1.0 build verification

Build and artifact verification: 2026-09-07 (Asia/Seoul)
Test suite re-verified: 2026-09-18 (Asia/Seoul), Python 3.13.5

The executable and installer checks below describe the earlier build; they
have not been repeated for the shared-year UI changes.

## Environment

- Windows NT 10.0.26100, 64 bit
- Python 3.11.16
- PyInstaller 6.22.2
- Inno Setup 6.7.3
- Release dependencies from `requirements.txt`

## Checks performed

1. `python -m unittest discover -s tests -v`: 60 tests passed, including the
   English coverage of both UIs (the assessment app and the Equation Library
   Manager, which carries its own translation table), the
   shared-centimeter DBH/RCD contract, legacy shrub-equation equivalence,
   combined planting-area boundary and over-limit cases, area-normalized
   carbon density, normalized-density values exported to XLSX, the unified
   77-record species library (growth-form assignment from the predictor
   variable, 30-year projections for 22 records with stored increments plus
   55 records with explicit 2% annual assumptions, and a finite diameter-basis
   curve for every record), and
   site-category resolution (every species stores one record per category with
   no category-independent base, published per-category equations for
   *Pinus densiflora*, and nine growth factors — three site categories × growth
   tiers 1–3, chosen by each species' tier — that scale annual increments (or the
   2% assumed rate) on top of the selected record without moving year-0 stock,
   with legacy six-factor files mapped to tiers 1 and 2).
   Optional site latitude/longitude is validated and round-trips through the
   data workbook.
   Additional checks cover graph/3D/inspection carbon parity, auxiliary-variable
   fingerprint changes, nine tabs, the shared year slider, fixed diameter
   contributions, recalculation, playback at year 30, and clearing results.
   The UI test uses real Qt controls and Matplotlib with the GPU renderer mocked.
   Updater output-name validation and custom EXE copying in onefile/onedir modes
   are tested with the PyInstaller subprocess mocked.
   The count above is checked by the suite itself: the test
   `test_build_verification_records_the_current_suite_size` discovers the tests
   at run time and fails if this document and the suite disagree, so adding or
   removing a test requires updating this line in the same change.
2. `python build_exe.py --onedir`: completed successfully.
3. `dist/FORECAST-SW/FORECAST-SW.exe`: English-interface startup smoke test
   passed.
4. `python build_updater.py`: completed successfully.
5. `dist/FORECAST-SW-Equation-Library-Manager.exe`: startup smoke test passed.
6. `installer.iss`: compiled successfully with Inno Setup.
7. Windows product-version metadata: version 1.0 confirmed for the Assessment
   Application, Equation Library Manager, and installer.

## Locally reproduced artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `dist/FORECAST-SW/FORECAST-SW.exe` | 13,194,908 | `D9FA13BA0C5E4E81803571524C7EBC8113B1144707850EFAA7A9C9AB554DFD2A` |
| `dist/FORECAST-SW-Equation-Library-Manager.exe` | 47,777,416 | `2BF4DEDD8F3C65BF097C06B310303F6339A28489D4567D48FFBC3010B9D1A409` |
| `installer_output/FORECAST-SW_Setup_1.0.exe` | 150,503,898 | `FC1B6AC150F61CC92C86F8F3CB75BBF33BA814CED396910ECF25471B854F6649` |

The executable and installer are reproducible local build outputs and are not
tracked in Git. The installer is not Authenticode-signed; users should verify
the release source tag and locally generated checksum when reproducing it.
