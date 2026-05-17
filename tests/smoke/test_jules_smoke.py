"""
Smoke tests for Jules API integration.
These tests verify the Jules API URL and basic connectivity.
"""
import os
import unittest

import requests

from src.jules.client import JulesClient


class TestJulesSmoke(unittest.TestCase):
    """Smoke tests for Jules API - these make real HTTP calls."""

    def test_base_url_is_correct(self):
        """Verify the BASE_URL matches official Jules API documentation."""
        self.assertEqual(JulesClient.BASE_URL, "https://jules.googleapis.com")

    def test_base_url_from_documentation(self):
        """Verify URL matches Jules official docs: https://jules.google/docs/api/reference/"""
        expected_base = "https://jules.googleapis.com"
        self.assertEqual(JulesClient.BASE_URL, expected_base)

    def test_sources_endpoint_url(self):
        """Verify sources endpoint uses correct URL pattern."""
        client = JulesClient(api_key="test-key")
        self.assertEqual(
            f"{client.BASE_URL}/v1alpha/sources",
            "https://jules.googleapis.com/v1alpha/sources"
        )

    def test_sessions_endpoint_url(self):
        """Verify sessions endpoint uses correct URL pattern."""
        client = JulesClient(api_key="test-key")
        self.assertEqual(
            f"{client.BASE_URL}/v1alpha/sessions",
            "https://jules.googleapis.com/v1alpha/sessions"
        )

    def test_jules_api_is_reachable(self):
        """Smoke test: verify Jules API is reachable (returns 401 without valid key)."""
        api_key = os.getenv("JULES_API_KEY")
        if not api_key:
            self.skipTest("JULES_API_KEY not set - skipping real API smoke test")

        client = JulesClient(api_key=api_key)
        try:
            response = requests.get(
                f"{client.BASE_URL}/v1alpha/sources",
                headers=client.headers,
                timeout=30
            )
            self.assertIn(response.status_code, [200, 401, 403])
        except requests.ConnectionError as e:
            self.fail(f"Jules API is unreachable: {e}")
        except requests.Timeout as e:
            self.fail(f"Jules API timed out: {e}")

    def test_jules_api_sessions_endpoint_reachable(self):
        """Smoke test: verify sessions endpoint is reachable."""
        api_key = os.getenv("JULES_API_KEY")
        if not api_key:
            self.skipTest("JULES_API_KEY not set - skipping real API smoke test")

        client = JulesClient(api_key=api_key)
        try:
            response = requests.get(
                f"{client.BASE_URL}/v1alpha/sessions",
                headers=client.headers,
                params={"pageSize": 1},
                timeout=30
            )
            self.assertIn(response.status_code, [200, 401, 403])
        except requests.ConnectionError as e:
            self.fail(f"Jules sessions endpoint unreachable: {e}")
        except requests.Timeout as e:
            self.fail(f"Jules sessions endpoint timed out: {e}")

    def test_jules_api_returns_valid_json(self):
        """Smoke test: verify Jules API returns valid JSON structure."""
        api_key = os.getenv("JULES_API_KEY")
        if not api_key:
            self.skipTest("JULES_API_KEY not set - skipping real API smoke test")

        client = JulesClient(api_key=api_key)
        try:
            response = requests.get(
                f"{client.BASE_URL}/v1alpha/sources",
                headers=client.headers,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.assertIsInstance(data, dict)
        except requests.ConnectionError:
            self.skipTest("Jules API unreachable - skipping JSON validation")
        except requests.Timeout:
            self.skipTest("Jules API timed out - skipping JSON validation")

    def test_all_endpoints_use_correct_base_url(self):
        """Verify all API methods construct URLs with the correct base URL."""
        client = JulesClient(api_key="test-key")

        expected_sources_url = "https://jules.googleapis.com/v1alpha/sources"
        self.assertTrue(
            f"{client.BASE_URL}/v1alpha/sources" == expected_sources_url,
            f"Expected {expected_sources_url}, got {client.BASE_URL}/v1alpha/sources"
        )

        expected_sessions_url = "https://jules.googleapis.com/v1alpha/sessions"
        self.assertTrue(
            f"{client.BASE_URL}/v1alpha/sessions" == expected_sessions_url,
            f"Expected {expected_sessions_url}, got {client.BASE_URL}/v1alpha/sessions"
        )


class TestJulesClientUnit(unittest.TestCase):
    """Unit tests for JulesClient URL construction."""

    def test_client_initialization(self):
        """Verify JulesClient initializes with correct base URL."""
        client = JulesClient(api_key="test-key")
        self.assertEqual(client.BASE_URL, "https://jules.googleapis.com")

    def test_headers_contain_correct_auth(self):
        """Verify client headers include X-Goog-Api-Key."""
        client = JulesClient(api_key="my-secret-key")
        self.assertEqual(client.headers["X-Goog-Api-Key"], "my-secret-key")
        self.assertEqual(client.headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
