import pytest
from unittest.mock import patch, MagicMock
import requests
from src.ai_client import get_ai_client, OllamaClient, GeminiClient, OpenAICodexClient, AIClient

def test_get_ai_client_invalid_provider():
    with pytest.raises(ValueError, match="Unknown AI provider: invalid"):
        get_ai_client("invalid")

def test_ollama_client_connection_error():
    with patch("src.ai_client.ollama.Client") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.generate.side_effect = Exception("Connection refused")

        client = OllamaClient(base_url="http://bad-url")
        with pytest.raises(Exception):
            client.resolve_conflict("content", "conflict")

        with pytest.raises(Exception):
            client.generate_pr_comment("issue")

def test_gemini_client_missing_api_key():
    # Ensure no env var
    with patch.dict("os.environ", {}, clear=True):
        client = GeminiClient(api_key=None)
        assert client.client is None

        with pytest.raises(ValueError, match="GEMINI_API_KEY is required"):
            client.resolve_conflict("content", "conflict")

        with pytest.raises(ValueError, match="GEMINI_API_KEY is required"):
            client.generate_pr_comment("issue")

def test_openai_client_missing_api_key():
    with patch.dict("os.environ", {}, clear=True):
        client = OpenAICodexClient(api_key=None)

        with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
            client.resolve_conflict("content", "conflict")

def test_openai_client_success():
    client = OpenAICodexClient(api_key="sk-test")
    mock_response = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Resolved Code"}
                ]
            }
        ]
    }
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        result = client.resolve_conflict("content", "conflict")
        assert "Resolved Code" in result

def test_openai_client_fallback_output_text():
    client = OpenAICodexClient(api_key="sk-test")
    mock_response = {"output_text": "Fallback Code"}
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        result = client.resolve_conflict("content", "conflict")
        assert "Fallback Code" in result

def test_openai_client_empty_response():
    client = OpenAICodexClient(api_key="sk-test")
    mock_response = {}
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        result = client.resolve_conflict("content", "conflict")
        assert result.strip() == ""

def test_ai_client_abstract_methods():
    # Verify we can't instantiate abstract class
    with pytest.raises(TypeError):
        AIClient()
