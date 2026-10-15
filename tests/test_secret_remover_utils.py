"""Tests for Secret Remover helper utilities (redaction, context, URLs)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.secret_remover import utils


class TestRedactContextLine(unittest.TestCase):
    def test_masks_quoted_value(self):
        out = utils.redact_context_line('API_KEY = "supersecretvalue"')
        self.assertIn("<redacted>", out)
        self.assertNotIn("supersecretvalue", out)

    def test_truncates_long_lines(self):
        out = utils.redact_context_line("x" * 500)
        self.assertLessEqual(len(out), 240)


class TestBuildRedactedContext(unittest.TestCase):
    def test_missing_file_path_is_reported(self):
        self.assertIn("missing file path", utils.build_redacted_context("/tmp", {}))

    def test_absent_file_is_reported(self):
        self.assertIn("not found", utils.build_redacted_context("/tmp", {"file": "nope.txt"}))

    def test_reads_window_and_marks_the_finding_line(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.txt"
            target.write_text("\n".join(f"line{i}" for i in range(1, 8)), encoding="utf-8")
            out = utils.build_redacted_context(directory, {"file": "f.txt", "line": 4})
        self.assertIn("> 4:", out)

    def test_marks_first_line_when_finding_line_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.txt"
            target.write_text("only\n", encoding="utf-8")
            out = utils.build_redacted_context(directory, {"file": "f.txt"})
        self.assertIn("> 1:", out)


class TestGetOriginalLine(unittest.TestCase):
    def test_returns_raw_line(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.txt"
            target.write_text("secret=abc\nsecond\n", encoding="utf-8")
            line = utils.get_original_line(directory, {"file": "f.txt", "line": 1})
        self.assertEqual(line, "secret=abc")

    def test_missing_file_returns_empty(self):
        self.assertEqual(utils.get_original_line("/tmp", {}), "")


class TestUrlBuilders(unittest.TestCase):
    def test_commit_url(self):
        self.assertEqual(
            utils.build_commit_url("o/r", "abc"), "https://github.com/o/r/commit/abc"
        )

    def test_file_line_url(self):
        self.assertEqual(
            utils.build_file_line_url("o/r", "abc", "a.py", 3),
            "https://github.com/o/r/blob/abc/a.py#L3",
        )

    def test_repo_url(self):
        self.assertEqual(utils.build_repo_url("o/r"), "https://github.com/o/r")


class TestFindLatestResults(unittest.TestCase):
    def test_returns_valid_scanner_result(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "zz_unique_scan_result.json").write_text(
                json.dumps({"repositories_with_findings": []}), encoding="utf-8"
            )
            with patch.dict(os.environ, {"RESULTS_DIR": directory}):
                found = utils.find_latest_results(lambda *_: None, "zz_unique_scan_*.json")
        self.assertIsNotNone(found)
        self.assertIn("repositories_with_findings", found)

    def test_returns_none_when_no_files_match(self):
        self.assertIsNone(utils.find_latest_results(lambda *_: None, "zzz_none_*.json"))

    def test_ignores_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "zz_bad_scan_result.json").write_text("{not json", encoding="utf-8")
            with patch.dict(os.environ, {"RESULTS_DIR": directory}):
                found = utils.find_latest_results(lambda *_: None, "zz_bad_scan_*.json")
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
