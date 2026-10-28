# SPDX-License-Identifier: MIT
"""Verify output naming without invoking PyInstaller or downloading packages."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import updater_app as updater


class UpdaterBuildTests(unittest.TestCase):
    def test_executable_names(self):
        for value, expected in (
            ("ForeCarb.exe", "ForeCarb.exe"),
            ("세종 수목원", "세종 수목원.exe"),
            (" custom.EXE ", "custom.exe"),
            ("release.v2", "release.v2.exe"),
        ):
            with self.subTest(value=value):
                self.assertEqual(updater._normalize_exe_name(value), expected)
        for value in ("", " ", ".exe", "..", "../outside", "folder\\app.exe",
                      "C:app.exe", "a?.exe", "CON.exe", "nul.txt", "LPT1.exe",
                      "COM¹.exe", "trailing .exe", "a\x00b", "a" * 252):
            with self.subTest(value=value), self.assertRaises(ValueError):
                updater._normalize_exe_name(value)

    def test_worker_copies_custom_output_in_both_modes(self):
        for onedir in (False, True):
            with self.subTest(onedir=onedir), TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                source.mkdir()
                (source / "build_exe.py").write_text("# test stub", encoding="utf-8")
                data = root / "species_data.json"
                data.write_text("{}", encoding="utf-8")
                output = root / "output"
                def fake_build(cmd, **kwargs):
                    work = Path(kwargs["cwd"])
                    target = work / "dist"
                    if onedir:
                        target /= updater._BUILT_APP_NAME
                    target.mkdir(parents=True)
                    (target / updater._BUILT_EXE_NAME).write_bytes(b"test executable")
                    if onedir:
                        (target / "_internal").mkdir()
                        (target / "_internal" / "data.txt").write_text("dependency")
                    self.assertEqual((work / updater.JSON_NAME).read_text(), "{}")
                    return Mock(stdout=iter(()), returncode=0)
                worker = updater.BuildWorker(data, output, ["--onedir"] if onedir else [],
                                             exe_name="세종 계산기")
                results = []
                worker.finished.connect(lambda ok, info: results.append((ok, info)))
                with patch.object(updater, "SRC_ROOT", source), \
                     patch.object(updater, "_find_python", return_value=Path("python")), \
                     patch.object(updater.subprocess, "Popen", side_effect=fake_build):
                    worker.run()
                target_dir = output / "세종 계산기" if onedir else output
                final = target_dir / "세종 계산기.exe"
                self.assertEqual(results, [(True, str(final))])
                self.assertEqual(final.read_bytes(), b"test executable")
                self.assertFalse((target_dir / updater._BUILT_EXE_NAME).exists())
                if onedir:
                    self.assertEqual((target_dir / "_internal" / "data.txt").read_text(), "dependency")
