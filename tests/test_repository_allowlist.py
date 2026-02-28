import json
import unittest
from unittest.mock import mock_open, patch

from src.config.repository_allowlist import RepositoryAllowlist


class TestRepositoryAllowlist(unittest.TestCase):
    def setUp(self):
        self.allowlist_path = "config/repositories.json"

    def test_load_success(self):
        data = {"repositories": ["repo1", "repo2"]}
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            with patch("pathlib.Path.exists", return_value=True):
                allowlist = RepositoryAllowlist(self.allowlist_path)
                self.assertEqual(len(allowlist.list_repositories()), 2)
                self.assertTrue(allowlist.is_allowed("repo1"))

    def test_load_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            allowlist = RepositoryAllowlist(self.allowlist_path)
            self.assertEqual(len(allowlist.list_repositories()), 0)

    def test_load_error(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Error")):
                allowlist = RepositoryAllowlist(self.allowlist_path)
                self.assertEqual(len(allowlist.list_repositories()), 0)

    def test_save(self):
        with patch("builtins.open", mock_open()):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir"):
                    allowlist = RepositoryAllowlist(self.allowlist_path)
                    allowlist.add_repository("repo1")

    def test_save_error(self):
        with patch("pathlib.Path.exists", return_value=False):
            with patch("pathlib.Path.mkdir"):
                allowlist = RepositoryAllowlist(self.allowlist_path)
                with patch("builtins.open", side_effect=Exception("Error")):
                    allowlist.save()  # Should print error but not crash

    def test_add_remove(self):
        with patch("pathlib.Path.exists", return_value=False):
            with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", mock_open()):
                    allowlist = RepositoryAllowlist(self.allowlist_path)

                    self.assertTrue(allowlist.add_repository("repo1"))
                    self.assertFalse(allowlist.add_repository("repo1"))  # Already exists

                    self.assertTrue(allowlist.is_allowed("repo1"))

                    self.assertTrue(allowlist.remove_repository("repo1"))
                    self.assertFalse(allowlist.remove_repository("repo1"))  # Already removed

                    self.assertFalse(allowlist.is_allowed("repo1"))

    def test_clear(self):
        with patch("pathlib.Path.exists", return_value=False):
            with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", mock_open()):
                    allowlist = RepositoryAllowlist(self.allowlist_path)
                    allowlist.add_repository("repo1")
                    allowlist.clear()
                    self.assertEqual(len(allowlist.list_repositories()), 0)

    def test_create_default(self):
        with patch("pathlib.Path.exists", return_value=False):
            allowlist = RepositoryAllowlist.create_default_allowlist()
            self.assertIsInstance(allowlist, RepositoryAllowlist)

    def test_load_ignores_invalid_entries(self):
        data = {"repositories": ["Owner/Repo", None, "", 123, " another/repo "]}
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            with patch("pathlib.Path.exists", return_value=True):
                allowlist = RepositoryAllowlist(self.allowlist_path)

        self.assertEqual(allowlist.list_repositories(), ["another/repo", "owner/repo"])

    def test_non_string_inputs_are_handled(self):
        with patch("pathlib.Path.exists", return_value=False):
            with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", mock_open()):
                    allowlist = RepositoryAllowlist(self.allowlist_path)
                    self.assertFalse(allowlist.is_allowed(None))
                    self.assertFalse(allowlist.add_repository(None))
                    self.assertFalse(allowlist.remove_repository(None))

    def test_invalid_repositories_shape_falls_back_to_empty(self):
        data = {"repositories": "owner/repo"}
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            with patch("pathlib.Path.exists", return_value=True):
                allowlist = RepositoryAllowlist(self.allowlist_path)

        self.assertEqual(allowlist.list_repositories(), [])
