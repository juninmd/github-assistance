"""Tests for configurable job prioritization."""

import json
import tempfile
import unittest
from pathlib import Path

from src.config.priorities import Priorities


class TestPriorities(unittest.TestCase):
    def _write(self, data: dict) -> str:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, handle)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_missing_file_defaults_to_zero(self):
        priorities = Priorities("does-not-exist-xyz.json")
        self.assertEqual(priorities.priority_for("juninmd/repo#1"), 0)

    def test_rules_accumulate_across_repo_label_and_title(self):
        path = self._write(
            {
                "repositories": [{"pattern": "juninmd/", "priority": 5}],
                "labels": [{"pattern": "urgent", "priority": 3}],
                "titles": [{"pattern": "fix", "priority": 2}],
            }
        )
        priorities = Priorities(path)
        score = priorities.priority_for("juninmd/agar#10", labels=["urgent"], title="fix login")
        self.assertEqual(score, 10)

    def test_non_matching_rules_add_nothing(self):
        path = self._write({"repositories": [{"pattern": "other/", "priority": 9}]})
        priorities = Priorities(path)
        self.assertEqual(priorities.priority_for("juninmd/agar#1"), 0)

    def test_title_matching_is_case_as_written_by_pattern(self):
        path = self._write({"titles": [{"pattern": "^chore", "priority": 4}]})
        priorities = Priorities(path)
        self.assertEqual(priorities.priority_for("o/r#1", title="chore: bump"), 4)
        self.assertEqual(priorities.priority_for("o/r#1", title="feat: bump"), 0)

    def test_default_classmethod_uses_config_path(self):
        priorities = Priorities.default()
        self.assertEqual(priorities.path, "config/priorities.json")


if __name__ == "__main__":
    unittest.main()
