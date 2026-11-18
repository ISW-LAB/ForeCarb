# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
통합 실행 진입점.

Carbon1 (자생복원종) 과 Carbon2 (국내·국외 통합) 를 하나의 창에서 탭으로 전환.
이 파일이 FORECAST-SW(핵심 소프트웨어)의 유일한 실행 진입점이며,
build_exe.py 가 이 파일을 빌드 대상으로 삼는다.

표시 언어(한국어/English)는 최초 실행 시 선택하고 이후 저장값을 사용한다.
신규 v1.0 설정의 기본 선택은 English 이며, 이전 CarbonStorageModule 설정은
가져오지 않는다.
`--lang ko|en` 로 지정하면 선택 창 없이 그 언어로 시작한다. 실행 중 메뉴에서
언어를 바꿀 때는 프로세스를 재시작하지 않고 창을 그 자리에서 새 언어로
다시 구성한다(CombinedMainWindow._change_language 참고).
"""
import argparse
import sys

from PyQt5.QtWidgets import QApplication

from carbon_calculator import i18n, input_limits
from carbon_calculator.combined_window import CombinedMainWindow
from carbon_calculator.font_config import setup_application_fonts
from carbon_calculator.language_dialog import LanguageDialog
from carbon_calculator.plotting import set_plot_font_scale
from carbon_calculator.theme import apply_theme
from carbon_calculator.ui_scale import enable_high_dpi, ui_scale


def _parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", choices=(i18n.LANG_KO, i18n.LANG_EN), default=None)
    args, _rest = parser.parse_known_args(argv[1:])
    return args


def _resolve_language(args) -> str:
    """--lang → FORECAST-SW 저장값 → 영문 기본 선택 순서로 언어를 정한다."""
    if args.lang:
        return args.lang

    saved = i18n.load_saved_language()
    if saved:
        return saved

    dialog = LanguageDialog(i18n.LANG_EN)
    dialog.exec_()
    chosen = dialog.chosen()
    i18n.save_language(chosen)
    return chosen


def main() -> int:
    args = _parse_args(sys.argv)

    enable_high_dpi()                  # QApplication 생성 전 (고해상도 스케일링)
    app = QApplication(sys.argv)

    # 언어 결정은 폰트/테마 적용보다 앞선다 (선택 창은 자체 문구를 사용).
    i18n.set_language(_resolve_language(args))
    # 이전 실행에서 저장한 식재 면적 입력 한도(개체당 식재 면적)를 적용한다.
    input_limits.load_saved_unit_areas()

    scale = ui_scale(app)              # 모니터 크기 기준 UI 스케일 1회 계산
    setup_application_fonts(app, scale)
    set_plot_font_scale(scale)         # matplotlib 폰트도 동일 스케일
    apply_theme(app, scale)            # 통합 테마(QSS) 적용

    win = CombinedMainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
