"""Additional coverage tests for secret_remover/utils edge cases and error handling."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.secret_remover import utils


class TestSecretRemoverUtilsCoverage(unittest.TestCase):
    def test_find_latest_results_glob_exception(self):
        logs = []
        with patch.object(Path, "glob", side_effect=RuntimeError("disk error")):
            result = utils.find_latest_results(
                lambda msg, level="INFO": logs.append((msg, level)), "scan_*.json"
            )
        self.assertIsNone(result)
        self.assertTrue(any("disk error" in msg and lvl == "WARNING" for msg, lvl in logs))

    def test_find_latest_results_non_dict_json(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "scan_list.json"
            file_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
            with patch.dict(os.environ, {"RESULTS_DIR": tmp_dir}):
                result = utils.find_latest_results(
                    lambda msg, level="INFO": logs.append((msg, level)), "scan_*.json"
                )
        self.assertIsNone(result)
        self.assertTrue(any("not a dict" in msg for msg, _ in logs))

    def test_find_latest_results_missing_key(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "scan_nokey.json"
            file_path.write_text(json.dumps({"some_other_key": 123}), encoding="utf-8")
            with patch.dict(os.environ, {"RESULTS_DIR": tmp_dir}):
                result = utils.find_latest_results(
                    lambda msg, level="INFO": logs.append((msg, level)), "scan_*.json"
                )
        self.assertIsNone(result)
        self.assertTrue(any("missing key" in msg for msg, _ in logs))

    def test_find_latest_results_open_read_exception(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "scan_perm.json"
            file_path.write_text("{}", encoding="utf-8")
            with (
                patch.dict(os.environ, {"RESULTS_DIR": tmp_dir}),
                patch("builtins.open", side_effect=PermissionError("denied")),
            ):
                result = utils.find_latest_results(
                    lambda msg, level="INFO": logs.append((msg, level)), "scan_*.json"
                )
        self.assertIsNone(result)
        self.assertTrue(any("denied" in msg for msg, _ in logs))

    def test_build_redacted_context_read_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test.py"
            file_path.write_text("test_content", encoding="utf-8")
            with patch("builtins.open", side_effect=OSError("read error")):
                res = utils.build_redacted_context(tmp_dir, {"file": "test.py", "line": 1})
            self.assertIn("Context unavailable: read error", res)

    def test_get_original_line_line_index_out_of_bounds(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "short.txt"
            file_path.write_text("", encoding="utf-8")
            # line=0 -> line_index=0, but len(lines)==0, so 0 <= line_index < len(lines) is False
            res = utils.get_original_line(tmp_dir, {"file": "short.txt", "line": 0})
            self.assertEqual(res, "")
            res_out = utils.get_original_line(tmp_dir, {"file": "short.txt", "line": 99})
            self.assertEqual(res_out, "")

    def test_get_original_line_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = utils.get_original_line(tmp_dir, {"file": "nonexistent.txt", "line": 1})
            self.assertEqual(res, "")

    def test_get_original_line_open_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "err.txt"
            file_path.write_text("line 1\n", encoding="utf-8")
            with patch("builtins.open", side_effect=PermissionError("denied")):
                res = utils.get_original_line(tmp_dir, {"file": "err.txt", "line": 1})
            self.assertEqual(res, "")


if __name__ == "__main__":
    unittest.main()
