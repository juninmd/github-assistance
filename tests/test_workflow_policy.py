"""Tests for the no-cron GitHub Actions workflow policy."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.security_scanner.workflow_policy import (
    detect_cron_workflows,
    scan_workflow_text,
)

CRON_WORKFLOW = """\
name: Nightly
on:
  schedule:
    - cron: "0 9 * * *"  # daily at 09:00
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
"""

EVENT_WORKFLOW = """\
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
"""

MULTI_CRON_WORKFLOW = """\
name: Multi
on:
  schedule:
    - cron: '0 0 * * *'
    - cron: 30 6 * * 1
"""


class TestScanWorkflowText(unittest.TestCase):
    def test_detects_quoted_cron_with_comment(self):
        violations = scan_workflow_text(CRON_WORKFLOW, file="nightly.yml")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["cron"], "0 9 * * *")
        self.assertEqual(violations[0]["file"], "nightly.yml")
        self.assertEqual(violations[0]["line"], 4)

    def test_event_driven_workflow_is_clean(self):
        self.assertEqual(scan_workflow_text(EVENT_WORKFLOW), [])

    def test_detects_multiple_cron_entries_and_strips_quotes(self):
        violations = scan_workflow_text(MULTI_CRON_WORKFLOW)
        crons = [v["cron"] for v in violations]
        self.assertEqual(crons, ["0 0 * * *", "30 6 * * 1"])

    def test_interval_schedule_is_not_a_false_positive(self):
        # dependabot-style schedule uses `interval:`, never `cron:`.
        text = "version: 2\nupdates:\n  - schedule:\n      interval: weekly\n"
        self.assertEqual(scan_workflow_text(text), [])


class TestDetectCronWorkflows(unittest.TestCase):
    def _make_repo(self, files: dict[str, str]) -> Path:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        for name, content in files.items():
            (wf_dir / name).write_text(content, encoding="utf-8")
        return root

    def test_no_workflows_dir_returns_empty(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.assertEqual(detect_cron_workflows(tmp.name), [])

    def test_finds_cron_across_files(self):
        root = self._make_repo(
            {
                "nightly.yml": CRON_WORKFLOW,
                "ci.yaml": EVENT_WORKFLOW,
                "multi.yml": MULTI_CRON_WORKFLOW,
            }
        )
        violations = detect_cron_workflows(root)
        self.assertEqual(len(violations), 3)
        files = {v["file"] for v in violations}
        self.assertEqual(
            files,
            {".github/workflows/nightly.yml", ".github/workflows/multi.yml"},
        )
        # Sorted by (file, line).
        self.assertEqual(violations[0]["file"], ".github/workflows/multi.yml")

    def test_approved_workflow_is_excluded(self):
        root = self._make_repo({"daily-project-creator.yml": CRON_WORKFLOW})
        self.assertEqual(
            detect_cron_workflows(root, approved={"daily-project-creator.yml"}), []
        )
        # Without the allowlist it is reported.
        self.assertEqual(len(detect_cron_workflows(root, approved=set())), 1)


if __name__ == "__main__":
    unittest.main()
