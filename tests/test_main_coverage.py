import sys
from unittest.mock import MagicMock, patch

import pytest

from src.main import main


def test_main_exception_handling():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.pr_ref = "123"
        mock_args.return_value.provider = "gemini"
        mock_args.return_value.model = "flash"

        # Mock PRAssistantAgent to raise exception
        with patch("src.main.PRAssistantAgent") as MockAgent:
            MockAgent.side_effect = Exception("Critical Error")

            with patch("sys.exit") as mock_exit:
                main()
                mock_exit.assert_called_with(1)

def test_main_provider_ollama():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.pr_ref = "123"
        mock_args.return_value.provider = "ollama"
        mock_args.return_value.model = "llama3"

        with patch("src.main.PRAssistantAgent") as MockAgent:
            with patch("src.main.GithubClient"): # Mock GithubClient
                with patch("src.main.JulesClient"): # Mock JulesClient
                    with patch("src.main.Settings.from_env") as mock_settings:
                        mock_settings.return_value.ollama_base_url = "http://ollama"
                        mock_settings.return_value.github_owner = "owner"
                        mock_settings.return_value.repository_allowlist_path = "allowlist.json"

                        main()

                        # Check PRAssistantAgent called with correct config
                        call_args = MockAgent.call_args
                        assert call_args.kwargs["ai_provider"] == "ollama"
                        assert call_args.kwargs["ai_config"]["base_url"] == "http://ollama"

def test_main_provider_openai():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.pr_ref = "123"
        mock_args.return_value.provider = "openai"
        mock_args.return_value.model = "gpt-4"

        with patch("src.main.PRAssistantAgent") as MockAgent:
            with patch("src.main.GithubClient"): # Mock GithubClient
                with patch("src.main.JulesClient"): # Mock JulesClient
                    with patch("src.main.Settings.from_env") as mock_settings:
                        mock_settings.return_value.openai_api_key = "sk-test"
                        mock_settings.return_value.github_owner = "owner"
                        mock_settings.return_value.repository_allowlist_path = "allowlist.json"

                        main()

                        # Check PRAssistantAgent called with correct config
                        call_args = MockAgent.call_args
                        assert call_args.kwargs["ai_provider"] == "openai"
                        assert call_args.kwargs["ai_config"]["api_key"] == "sk-test"
