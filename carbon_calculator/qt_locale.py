# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""Qt 표준 문구(대화상자 버튼 Yes/No/Cancel 등)의 표시 언어와 글꼴.

앱 문자열은 ``tr()`` 이 번역하지만, ``QMessageBox`` 표준 버튼처럼 Qt 가 직접 그리는
문구는 Qt 번역 파일(qtbase_ko.qm)을 설치해야 국문으로 바뀐다. 또 Windows 에서
메시지 상자는 플랫폼 기본 글꼴을 써서 앱 글꼴보다 작게 보이므로 같이 맞춘다.
의존성은 PyQt5 뿐이라 계산 앱과 라이브러리 관리 프로그램이 함께 쓴다.
"""
from __future__ import annotations

import os

from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt5.QtWidgets import QApplication

_installed: list[QTranslator] = []


def install_qt_translator(app: QApplication, language: str) -> None:
    """``language`` 가 'ko' 면 Qt 표준 문구를 국문으로, 그 외에는 원래(영문)대로 둔다."""
    for translator in _installed:
        app.removeTranslator(translator)
    _installed.clear()
    if language != "ko":
        return
    translator = QTranslator(app)
    locale = QLocale(QLocale.Korean, QLocale.SouthKorea)
    if any(translator.load(locale, "qtbase", "_", path) for path in _translation_dirs()):
        app.installTranslator(translator)
        _installed.append(translator)


def _translation_dirs() -> list[str]:
    """Qt 번역 파일 폴더 후보.

    Qt 에 기록된 경로(QLibraryInfo)는 설치 경로에 한글이 있으면 깨져서(예: '세종수목원')
    파일을 찾지 못한다. PyQt5 패키지 위치(개발 환경·PyInstaller 공통)를 먼저 쓴다.
    """
    import PyQt5
    package_dir = os.path.dirname(os.path.abspath(PyQt5.__file__))
    return [os.path.join(package_dir, "Qt5", "translations"),
            os.path.join(package_dir, "Qt", "translations"),
            QLibraryInfo.location(QLibraryInfo.TranslationsPath)]


def apply_dialog_font(app: QApplication) -> None:
    """메시지 상자도 앱 기본 글꼴을 쓰게 한다 (본문 크기는 각 테마의 QSS 가 맞춘다)."""
    app.setFont(app.font(), "QMessageBox")
