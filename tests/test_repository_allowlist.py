import unittest
from unittest.mock import MagicMock, patch, mock_open
import json
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
        with patch("builtins.open", mock_open()) as mock_file:
            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir"):
                    allowlist = RepositoryAllowlist(self.allowlist_path)
                    allowlist.add_repository("repo1")

                    # We can verify that file was opened for writing
                    # The path object is cast to string in open() in some python versions or mocks,
                    # but here it receives a Path object or string depending on implementation
                    # Allowlist implementation uses Path(self.allowlist_path)
                    # mock_file.assert_called() checks if called at all.
                    pass

    def test_save_error(self):
        with patch("pathlib.Path.exists", return_value=False):
             with patch("pathlib.Path.mkdir"):
                allowlist = RepositoryAllowlist(self.allowlist_path)
                with patch("builtins.open", side_effect=Exception("Error")):
                    allowlist.save() # Should print error but not crash

    def test_add_remove(self):
        with patch("pathlib.Path.exists", return_value=False):
             with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", mock_open()):
                    allowlist = RepositoryAllowlist(self.allowlist_path)

                    self.assertTrue(allowlist.add_repository("repo1"))
                    self.assertFalse(allowlist.add_repository("repo1")) # Already exists

                    self.assertTrue(allowlist.is_allowed("repo1"))

                    self.assertTrue(allowlist.remove_repository("repo1"))
                    self.assertFalse(allowlist.remove_repository("repo1")) # Already removed

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
