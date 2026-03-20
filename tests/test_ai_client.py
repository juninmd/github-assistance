import pytest
from unittest.mock import patch, MagicMock
from src.ai_client import AIClient, GeminiClient, OllamaClient, OpenAIClient, get_ai_client

class DummyClient(AIClient):
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        pass
    def generate_pr_comment(self, issue_description: str) -> str:
        return f"Dummy comment: {issue_description}"

def test_ai_client_generate_fallback():
    client = DummyClient()
    assert client.generate("test prompt") == "Dummy comment: test prompt"

def test_ai_client_extract_code_block():
    client = DummyClient()
    text = "Here is the code:\n```python\nprint('hello')\n```"
    extracted = client._extract_code_block(text)
    assert extracted == "print('hello')\n"

    text_no_block = "Just some text"
    extracted = client._extract_code_block(text_no_block)
    assert extracted == "Just some text\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

    text_no_lang_or_space = "```print('test')\n```"
    extracted = client._extract_code_block(text_no_lang_or_space)
    assert extracted == "print('test')\n"

def test_ai_client_analyze_pr_closure_json():
    client = DummyClient()
    client.generate = MagicMock(return_value='```json\n{"should_close": true, "reason": "test reason"}\n```')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is True
    assert reason == "test reason"

def test_ai_client_analyze_pr_closure_json_invalid():
    client = DummyClient()
    # It hits the fallback because 'should_close": true' is still evaluated by the fallback condition.
    # We will test the JSON Exception path explicitly without the fallback matching.
    client.generate = MagicMock(return_value='```json\n{"should_close": fal \n```')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is False
    assert reason == ""

def test_ai_client_analyze_pr_closure_fallback():
    client = DummyClient()
    client.generate = MagicMock(return_value='"should_close": true')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is True
    assert "Identificado motivo para fechamento" in reason

def test_ai_client_analyze_pr_closure_false():
    client = DummyClient()
    client.generate = MagicMock(return_value='nothing to do')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is False
    assert reason == ""

@patch("src.ai_client.genai.Client")
def test_gemini_client(mock_genai_client):
    mock_client_instance = MagicMock()
    mock_genai_client.return_value = mock_client_instance
    mock_response = MagicMock()
    mock_response.text = "test response"
    mock_client_instance.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="test_key")

    assert client.generate("test") == "test response"

    mock_response.text = "```\nresolved code\n```"
    assert client.resolve_conflict("file_content", "conflict_block") == "resolved code\n"

    mock_response.text = "comment"
    assert client.generate_pr_comment("issue") == "comment"

def test_gemini_client_missing_key():
    client = GeminiClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")

@patch("src.ai_client.ollama.Client")
def test_ollama_client(mock_ollama_client):
    mock_client_instance = MagicMock()
    mock_ollama_client.return_value = mock_client_instance
    mock_response = MagicMock()
    mock_response.response = "test response"
    mock_client_instance.generate.return_value = mock_response

    client = OllamaClient()

    assert client.generate("test") == "test response"

    mock_response.response = "```\nresolved code\n```"
    assert client.resolve_conflict("file_content", "conflict_block") == "resolved code\n"

    mock_response.response = "comment"
    assert client.generate_pr_comment("issue") == "comment"

@patch("src.ai_client.requests.post")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
def test_openai_client_missing_key():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError):
        client.generate("test")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")
    with pytest.raises(ValueError):
        client.resolve_conflict("a", "b")
    with pytest.raises(ValueError):
        client.generate_pr_comment("issue")

def test_get_ai_client():
    with patch("src.ai_client.GeminiClient") as mock_gemini:
        get_ai_client("gemini")
        mock_gemini.assert_called_once()

    with patch("src.ai_client.OllamaClient") as mock_ollama:
        get_ai_client("ollama")
        mock_ollama.assert_called_once()

    with patch("src.ai_client.OpenAIClient") as mock_openai:
        get_ai_client("openai")
        mock_openai.assert_called_once()

    with pytest.raises(ValueError):
        get_ai_client("unknown")


def test_ai_client_analyze_pr_closure_json_true_fallback():
    client = DummyClient()
    # It parses JSON but should_close evaluates to False, then fallback kicks in
    # Actually wait, if parsing succeeds but should_close is False, it returns False.
    # What if it's true?
    client.generate = MagicMock(return_value='```json\n{"other": true}\n```')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is False
    assert reason == ""

def test_ai_client_analyze_pr_closure_json_true():
    client = DummyClient()
    # This hits lines 51-52 if fallback logic catches it
    client.generate = MagicMock(return_value='true')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is True
    assert "Identificado motivo para fechamento" in reason

def test_ai_client_analyze_pr_closure_json_exception():
    client = DummyClient()
    client.generate = MagicMock(return_value='{ "should_close": true ')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is True
    assert "Identificado motivo para fechamento" in reason

def test_ai_client_analyze_pr_closure_json_exception_explicit():
    client = DummyClient()
    # Malformed JSON with curlies
    client.generate = MagicMock(return_value='{ malformed_json ')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is False
    assert reason == ""

def test_ai_client_analyze_pr_closure_json_exception_explicit_with_curlies():
    client = DummyClient()
    # Malformed JSON with matching curlies
    client.generate = MagicMock(return_value='{ malformed_json }')
    should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
    assert should_close is False
    assert reason == ""
