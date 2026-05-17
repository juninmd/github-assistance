import unittest
from unittest.mock import MagicMock

from src.agents.pr_assistant.utils import is_trusted_author


class TestPRAssistantUtils(unittest.TestCase):
    def test_is_trusted_author(self):
        allowed_authors = ["jules", "bot[bot]", "admin"]

        trusted_cases = ["jules", "JULES", "bot", "bot[bot]", "admin"]
        for author in trusted_cases:
            with self.subTest(author=author, trusted=True):
                self.assertTrue(is_trusted_author(author, allowed_authors))

        untrusted_cases = ["unknown", "hacker"]
        for author in untrusted_cases:
            with self.subTest(author=author, trusted=False):
                self.assertFalse(is_trusted_author(author, allowed_authors))

if __name__ == "__main__":
    unittest.main()
