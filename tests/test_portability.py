"""Regressions for locale, file paths and persisted results across host systems."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE = "market_entry_agent"
ROOT = Path(__file__).resolve().parents[1]


class PortabilityTests(unittest.TestCase):
    def test_country_data_under_non_utf8_locale(self):
        # C locale on POSIX, ANSI code page on Windows; -X utf8=0 disables the override.
        code = "import locale,json;locale.setlocale(locale.LC_CTYPE,'C');from " + MODULE + ".countries import baseline;print(json.dumps(baseline('VNM')['name']))"
        result = subprocess.run([sys.executable, "-X", "utf8=0", "-c", code],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(result.stdout), "Viet Nam")

    def test_unicode_paths_and_closed_database_handles(self):
        core = importlib.import_module(MODULE + ".core")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "研究 workspace"
            store = core.Store(workspace)
            bundle = core.load_json(ROOT / "examples/demo-evidence.json")
            store.import_evidence(bundle)
            expected = store.export_evidence()
            moved = workspace.with_name("已移动 workspace")
            workspace.rename(moved)
            reopened = core.Store(moved)
            self.assertEqual(reopened.export_evidence(), expected)
            self.assertEqual(reopened.import_evidence(bundle)["added"], 0)
            target = moved / "报告 output.json"
            core.atomic_json(target, {"内容": "中文报告"})
            self.assertEqual(core.load_json(target), {"内容": "中文报告"})

    def test_cli_utf8_json_with_legacy_redirected_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1252")
            result = subprocess.run([sys.executable, "-X", "utf8=0", "-m", MODULE,
                                     "--workspace", str(Path(temporary) / "工作 space"), "country", "越南"],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertEqual(json.loads(result.stdout.decode("utf-8"))["baseline"]["code"], "VNM")

