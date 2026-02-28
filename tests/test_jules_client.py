import os
import unittest
from unittest.mock import MagicMock, patch

from src.jules.client import JulesClient


class TestJulesClient(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"JULES_API_KEY": "key"}):
            self.client = JulesClient()

    def test_init_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            client = JulesClient()
            self.assertIsNone(client.api_key)

    @patch("src.jules.client.requests.get")
    def test_list_sources(self, mock_get):
        mock_get.return_value.json.side_effect = [
            {"sources": ["s1"], "nextPageToken": "token"},
            {"sources": ["s2"]}
        ]
        sources = self.client.list_sources()
        self.assertEqual(sources, ["s1", "s2"])
        self.assertEqual(mock_get.call_count, 2)

    def test_get_source_name(self):
        self.assertEqual(self.client.get_source_name("owner/repo"), "sources/github/owner/repo")

    @patch("src.jules.client.requests.post")
    def test_create_session(self, mock_post):
        mock_post.return_value.json.return_value = {"id": "123"}
        result = self.client.create_session("source", "prompt", "title", "main", "AUTO", True)
        self.assertEqual(result["id"], "123")

        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['title'], "title")
        self.assertEqual(kwargs['json']['automationMode'], "AUTO")
        self.assertTrue(kwargs['json']['requirePlanApproval'])

    @patch("src.jules.client.requests.get")
    def test_get_session(self, mock_get):
        mock_get.return_value.json.return_value = {"id": "123"}
        result = self.client.get_session("123")
        self.assertEqual(result["id"], "123")

    @patch("src.jules.client.requests.get")
    def test_list_sessions(self, mock_get):
        mock_get.return_value.json.return_value = {"sessions": ["s1"]}
        result = self.client.list_sessions()
        self.assertEqual(result, ["s1"])

    @patch("src.jules.client.requests.post")
    def test_approve_plan(self, mock_post):
        mock_post.return_value.json.return_value = {"status": "approved"}
        result = self.client.approve_plan("123")
        self.assertEqual(result["status"], "approved")

    @patch("src.jules.client.requests.post")
    def test_send_message(self, mock_post):
        mock_post.return_value.text = "{}"
        mock_post.return_value.json.return_value = {}
        result = self.client.send_message("123", "prompt")
        self.assertEqual(result, {})

    @patch("src.jules.client.requests.get")
    def test_list_activities(self, mock_get):
        mock_get.return_value.json.return_value = {"activities": ["a1"]}
        result = self.client.list_activities("123")
        self.assertEqual(result, ["a1"])

    @patch("src.jules.client.time.sleep")
    @patch("src.jules.client.time.time")
    def test_wait_for_session_success(self, mock_time, mock_sleep):
        mock_time.side_effect = [0, 1, 2, 3] # Start, check1, check2...

        with patch.object(self.client, 'get_session') as mock_get:
            mock_get.side_effect = [
                {"status": "RUNNING"},
                {"status": "COMPLETED", "outputs": ["pr"]}
            ]

            result = self.client.wait_for_session("123")
            self.assertEqual(result["outputs"], ["pr"])

    @patch("src.jules.client.time.sleep")
    @patch("src.jules.client.time.time")
    def test_wait_for_session_timeout(self, mock_time, mock_sleep):
        mock_time.side_effect = [0, 100, 200]

        with patch.object(self.client, 'get_session') as mock_get:
            mock_get.return_value = {"status": "RUNNING"}

            with self.assertRaises(TimeoutError):
                self.client.wait_for_session("123", max_wait_seconds=50)

    def test_create_pull_request_session(self):
        with patch.object(self.client, 'create_session') as mock_create:
            mock_create.return_value = {"id": "123"}
            result = self.client.create_pull_request_session("owner/repo", "prompt")
            self.assertEqual(result["id"], "123")

            args, kwargs = mock_create.call_args
            self.assertEqual(kwargs['source'], "sources/github/owner/repo")
            self.assertEqual(kwargs['automation_mode'], "AUTO_CREATE_PR")
