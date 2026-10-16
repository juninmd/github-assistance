"""Tests for the Dependency Manager agent and its ecosystem detection."""

import unittest
from unittest.mock import MagicMock

from src.agents.dependency_manager import detect
from src.agents.dependency_manager.agent import DependencyManagerAgent
from src.notifications.telegram import TelegramNotifier


class _Item:
    def __init__(self, path: str) -> None:
        self.path = path


def _tree(*paths: str):
    tree = MagicMock()
    tree.tree = [_Item(p) for p in paths]
    return tree


class TestDetect(unittest.TestCase):
    def test_no_dependencies(self):
        self.assertEqual(detect.detect_ecosystems(["README.md", "src/main.py"]), [])

    def test_node_with_lockfile(self):
        found = detect.detect_ecosystems(["package.json", "pnpm-lock.yaml"])
        self.assertEqual([e.name for e in found], ["node"])
        self.assertEqual(found[0].lockfile, "pnpm-lock.yaml")

    def test_python_without_lockfile(self):
        found = detect.detect_ecosystems(["pyproject.toml"])
        self.assertEqual([e.name for e in found], ["python"])
        self.assertIsNone(found[0].lockfile)

    def test_multiple_ecosystems(self):
        found = detect.detect_ecosystems(["package.json", "go.mod", "go.sum"])
        self.assertEqual({e.name for e in found}, {"node", "go"})

    def test_subdirectory_files_are_ignored(self):
        found = detect.detect_ecosystems(["frontend/package.json"])
        self.assertEqual(found, [])

    def test_root_filenames_filters_paths(self):
        self.assertEqual(detect.root_filenames(["a.txt", "dir/b.txt"]), {"a.txt"})


class TestDependencyManagerAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo"]
        self.allowlist.is_allowed.return_value = True
        self.telegram = MagicMock(spec=TelegramNotifier)
        self.telegram.escape_html = TelegramNotifier.escape_html
        self.agent = DependencyManagerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testuser",
        )
        self.agent.get_allowed_repositories = MagicMock(return_value=["owner/repo"])

    def _repo(self, *paths: str):
        repo = MagicMock()
        repo.full_name = "owner/repo"
        repo.name = "repo"
        repo.default_branch = "main"
        repo.get_git_tree.return_value = _tree(*paths)
        return repo

    def test_init_uses_allowlist(self):
        self.assertTrue(self.agent.uses_repository_allowlist())

    def test_run_opens_pr_when_dependencies_found(self):
        self.github_client.get_repo.return_value = self._repo("package.json", "package-lock.json")
        self.agent.create_opencode_task = MagicMock(
            return_value={"status": "task_created", "task_url": "http://pr"}
        )

        result = self.agent.run()

        self.assertEqual(len(result["processed"]), 1)
        self.assertEqual(result["processed"][0]["ecosystems"], ["node"])
        self.assertEqual(result["processed"][0]["pr_url"], "http://pr")
        self.agent.create_opencode_task.assert_called_once()

    def test_run_skips_repo_without_dependencies(self):
        self.github_client.get_repo.return_value = self._repo("README.md", "src/main.py")
        self.agent.create_opencode_task = MagicMock()

        result = self.agent.run()

        self.assertEqual(result["skipped"][0]["reason"], "no_dependencies")
        self.agent.create_opencode_task.assert_not_called()

    def test_run_records_failure(self):
        self.github_client.get_repo.side_effect = Exception("boom")
        result = self.agent.run()
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["error"], "boom")

    def test_instructions_prioritize_security(self):
        ecosystems = detect.detect_ecosystems(["pyproject.toml", "uv.lock"])
        text = self.agent._build_instructions(ecosystems)
        self.assertIn("Segurança primeiro", text)
        self.assertIn("python", text)
        self.assertIn("testes", text)

    def test_detect_handles_tree_error(self):
        repo = MagicMock()
        repo.full_name = "owner/repo"
        repo.default_branch = "main"
        repo.get_git_tree.side_effect = Exception("api")
        self.assertEqual(self.agent._detect(repo), [])

    def test_dry_run_does_not_create_task(self):
        import os
        from unittest.mock import patch

        self.github_client.get_repo.return_value = self._repo("package.json")
        self.agent.create_opencode_task = MagicMock()
        with patch.dict(os.environ, {"DEPENDENCY_DRY_RUN": "true"}):
            result = self.agent.run()
        self.assertEqual(result["processed"][0]["status"], "dry_run")
        self.agent.create_opencode_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
