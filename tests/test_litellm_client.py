"""Tests for LiteLLMClient."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.ai.litellm_client import LiteLLMClient


def _mock_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class TestLiteLLMClientInit:
    def test_defaults(self):
        client = LiteLLMClient()
        assert client.model == "cloud/llama-70b"
        assert client.api_key is None
        assert client.api_base is None

    def test_explicit_params(self):
        client = LiteLLMClient(model="openai/gpt-4o", api_key="sk-test", api_base="http://proxy")
        assert client.model == "openai/gpt-4o"
        assert client.api_key == "sk-test"
        assert client.api_base == "http://proxy"

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("LITELLM_MODEL", "anthropic/claude-sonnet-4-6")
        monkeypatch.setenv("LITELLM_API_KEY", "env-key")
        monkeypatch.setenv("LITELLM_API_BASE", "http://env-base")
        client = LiteLLMClient()
        assert client.model == "anthropic/claude-sonnet-4-6"
        assert client.api_key == "env-key"
        assert client.api_base == "http://env-base"


class TestLiteLLMClientGenerate:
    def _client(self, **kwargs) -> LiteLLMClient:
        return LiteLLMClient(model="openai/gpt-4o", **kwargs)

    @patch("src.ai.litellm_client.litellm")
    def test_generate_returns_text(self, mock_litellm):
        mock_litellm.completion.return_value = _mock_response("  hello world  ")
        client = self._client()
        result = client.generate("Say hello")
        assert result == "hello world"
        mock_litellm.completion.assert_called_once()
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["model"] == "openai/gpt-4o"
        assert call_kwargs["messages"] == [{"role": "user", "content": "Say hello"}]

    @patch("src.ai.litellm_client.litellm")
    def test_generate_passes_api_key_and_base(self, mock_litellm):
        mock_litellm.completion.return_value = _mock_response("ok")
        client = self._client(api_key="sk-x", api_base="http://proxy")
        client.generate("test")
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-x"
        assert call_kwargs["api_base"] == "http://proxy"

    @patch("src.ai.litellm_client.litellm")
    def test_generate_empty_on_bad_response(self, mock_litellm):
        mock_litellm.completion.return_value = SimpleNamespace(choices=[])
        client = self._client()
        assert client.generate("test") == ""

    @patch("src.ai.litellm_client.litellm")
    def test_resolve_conflict(self, mock_litellm):
        mock_litellm.completion.return_value = _mock_response("resolved code")
        client = self._client()
        result = client.resolve_conflict("file content", "conflict block")
        assert "resolved code" in result
        prompt_sent = mock_litellm.completion.call_args.kwargs["messages"][0]["content"]
        assert "conflict" in prompt_sent.lower()

    @patch("src.ai.litellm_client.litellm")
    def test_generate_pr_comment(self, mock_litellm):
        mock_litellm.completion.return_value = _mock_response("Please fix this issue.")
        client = self._client()
        result = client.generate_pr_comment("pipeline failed")
        assert result == "Please fix this issue."

    @patch("src.ai.litellm_client.litellm")
    def test_extra_kwargs_forwarded(self, mock_litellm):
        mock_litellm.completion.return_value = _mock_response("ok")
        client = LiteLLMClient(model="openai/gpt-4o", temperature=0.2, max_tokens=512)
        client.generate("test")
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["max_tokens"] == 512


class TestLiteLLMFactory:
    def test_factory_returns_litellm_client(self):
        from src.ai.factory import get_ai_client

        client = get_ai_client("litellm", model="openai/gpt-4o")
        assert isinstance(client, LiteLLMClient)
        assert client.model == "openai/gpt-4o"
