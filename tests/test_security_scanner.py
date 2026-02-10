"""
Tests for SecurityScannerAgent.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from src.agents.security_scanner import SecurityScannerAgent


@pytest.fixture
def mock_jules_client():
    """Mock Jules client."""
    return Mock()


@pytest.fixture
def mock_github_client():
    """Mock GitHub client."""
    client = Mock()
    client.send_telegram_msg = Mock()
    client.g = Mock()
    return client


@pytest.fixture
def mock_allowlist():
    """Mock repository allowlist."""
    allowlist = Mock()
    allowlist.is_allowed = Mock(return_value=True)
    allowlist.list_repositories = Mock(return_value=["juninmd/test-repo"])
    return allowlist


@pytest.fixture
def security_scanner_agent(mock_jules_client, mock_github_client, mock_allowlist):
    """Create SecurityScannerAgent instance."""
    return SecurityScannerAgent(
        jules_client=mock_jules_client,
        github_client=mock_github_client,
        allowlist=mock_allowlist,
        target_owner="juninmd"
    )


def test_security_scanner_agent_initialization(security_scanner_agent):
    """Test agent initialization."""
    assert security_scanner_agent.name == "security_scanner"
    assert security_scanner_agent.target_owner == "juninmd"
    assert security_scanner_agent.persona is not None
    assert security_scanner_agent.mission is not None


def test_escape_telegram(security_scanner_agent):
    """Test Telegram text escaping."""
    text = "Test_with*special[chars]"
    escaped = security_scanner_agent._escape_telegram(text)
    assert "\\_" in escaped
    assert "\\*" in escaped
    assert "\\[" in escaped
    assert "\\]" in escaped


def test_sanitize_findings(security_scanner_agent):
    """Test sanitization of gitleaks findings."""
    raw_findings = [
        {
            "RuleID": "generic-api-key",
            "Description": "Generic API Key",
            "File": "config.py",
            "StartLine": 42,
            "Commit": "abc123def456",
            "Author": "test@example.com",
            "Date": "2024-01-01",
            "Secret": "this-should-be-removed",
            "Match": "sensitive-data"
        }
    ]
    
    sanitized = security_scanner_agent._sanitize_findings(raw_findings)
    
    assert len(sanitized) == 1
    assert sanitized[0]["rule_id"] == "generic-api-key"
    assert sanitized[0]["file"] == "config.py"
    assert sanitized[0]["line"] == 42
    assert sanitized[0]["commit"] == "abc123de"  # Short hash
    assert "Secret" not in sanitized[0]
    assert "Match" not in sanitized[0]


@patch('subprocess.run')
def test_ensure_gitleaks_installed_already_installed(mock_run, security_scanner_agent):
    """Test gitleaks installation check when already installed."""
    mock_run.return_value = Mock(returncode=0, stdout="gitleaks version 8.18.1")
    
    result = security_scanner_agent._ensure_gitleaks_installed()
    
    assert result is True
    mock_run.assert_called_once()


@patch('subprocess.run')
def test_ensure_gitleaks_installed_needs_install(mock_run, security_scanner_agent):
    """Test gitleaks installation when not installed."""
    # First call fails (not installed), second call succeeds (install script)
    mock_run.side_effect = [
        FileNotFoundError(),
        Mock(returncode=0)
    ]
    
    result = security_scanner_agent._ensure_gitleaks_installed()
    
    assert result is True


def test_get_all_repositories(security_scanner_agent, mock_github_client):
    """Test fetching all repositories."""
    # Mock user and repositories
    mock_repo1 = Mock()
    mock_repo1.full_name = "juninmd/repo1"
    mock_repo1.owner.login = "juninmd"
    
    mock_repo2 = Mock()
    mock_repo2.full_name = "juninmd/repo2"
    mock_repo2.owner.login = "juninmd"
    
    mock_user = Mock()
    mock_user.get_repos.return_value = [mock_repo1, mock_repo2]
    
    mock_github_client.g.get_user.return_value = mock_user
    
    repos = security_scanner_agent._get_all_repositories()
    
    assert len(repos) == 2
    assert "juninmd/repo1" in repos
    assert "juninmd/repo2" in repos


@patch('tempfile.TemporaryDirectory')
@patch('subprocess.run')
@patch('os.path.exists')
@patch('builtins.open', create=True)
def test_scan_repository_no_findings(mock_open, mock_exists, mock_run, mock_temp_dir, security_scanner_agent):
    """Test scanning repository with no findings."""
    mock_temp_dir.return_value.__enter__.return_value = "/tmp/test"
    mock_exists.return_value = True
    
    # Mock git clone success
    mock_run.side_effect = [
        Mock(returncode=0),  # git clone
        Mock(returncode=0)   # gitleaks scan (no leaks)
    ]
    
    # Mock empty findings file
    mock_open.return_value.__enter__.return_value.read.return_value = "[]"
    
    with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'}):
        result = security_scanner_agent._scan_repository("juninmd/test-repo")
    
    assert result["scanned"] is True
    assert len(result["findings"]) == 0
    assert result["error"] is None


@patch('tempfile.TemporaryDirectory')
@patch('subprocess.run')
def test_scan_repository_clone_failure(mock_run, mock_temp_dir, security_scanner_agent):
    """Test handling of repository clone failure."""
    mock_temp_dir.return_value.__enter__.return_value = "/tmp/test"
    
    # Mock git clone failure with stderr that might contain sensitive data
    mock_run.return_value = Mock(
        returncode=1, 
        stderr="fatal: could not read Username for 'https://x-access-token:ghs_SECRET@github.com'"
    )
    
    with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'}):
        result = security_scanner_agent._scan_repository("juninmd/test-repo")
    
    assert result["scanned"] is False
    assert result["error"] is not None
    assert "Clone failed" in result["error"]
    assert "exit code" in result["error"]  # Updated to match new error message
    # Verify no sensitive data in error message
    assert "SECRET" not in result["error"]
    assert "x-access-token" not in result["error"]


def test_send_notification_no_findings(security_scanner_agent, mock_github_client):
    """Test sending notification when no findings."""
    results = {
        "scanned": 5,
        "total_repositories": 5,
        "failed": 0,
        "total_findings": 0,
        "repositories_with_findings": [],
        "scan_errors": []
    }
    
    security_scanner_agent._send_notification(results)
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    assert "No exposed secrets found" in call_args[0][0]


def test_send_notification_with_findings(security_scanner_agent, mock_github_client):
    """Test sending notification with findings."""
    results = {
        "scanned": 3,
        "total_repositories": 3,
        "failed": 0,
        "total_findings": 2,
        "repositories_with_findings": [
            {
                "repository": "juninmd/test-repo",
                "findings": [
                    {
                        "rule_id": "aws-access-token",
                        "file": "config.py",
                        "line": 10,
                        "commit": "abc123de"
                    }
                ]
            }
        ],
        "scan_errors": []
    }
    
    security_scanner_agent._send_notification(results)
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    message = call_args[0][0]
    assert "Findings by Repository" in message
    # Account for telegram escaping
    assert "test" in message  # test-repo will be escaped
    # Verify GitHub URL is present and properly formatted
    assert "github.com" in message
    assert "blob/abc123de" in message
    assert "config.py" in message
    assert "#L10" in message


def test_send_notification_limits_findings_to_three(security_scanner_agent, mock_github_client):
    """Test that notifications limit findings to 3 per repository."""
    results = {
        "scanned": 1,
        "total_repositories": 1,
        "failed": 0,
        "total_findings": 5,
        "repositories_with_findings": [
            {
                "repository": "juninmd/test-repo",
                "findings": [
                    {
                        "rule_id": "aws-access-token",
                        "file": "config1.py",
                        "line": 10,
                        "commit": "abc123de"
                    },
                    {
                        "rule_id": "github-pat",
                        "file": "config2.py",
                        "line": 20,
                        "commit": "def456gh"
                    },
                    {
                        "rule_id": "generic-api-key",
                        "file": "config3.py",
                        "line": 30,
                        "commit": "ghi789jk"
                    },
                    {
                        "rule_id": "secret-key-4",
                        "file": "config4.py",
                        "line": 40,
                        "commit": "jkl012mn"
                    },
                    {
                        "rule_id": "secret-key-5",
                        "file": "config5.py",
                        "line": 50,
                        "commit": "mno345pq"
                    }
                ]
            }
        ],
        "scan_errors": []
    }
    
    security_scanner_agent._send_notification(results)
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    message = call_args[0][0]
    
    # Should show exactly 3 findings
    assert "config1.py" in message
    assert "config2.py" in message
    assert "config3.py" in message
    # Should NOT show the 4th and 5th findings
    assert "config4.py" not in message
    assert "config5.py" not in message
    # Should indicate remaining findings with proper Telegram escaping
    assert "and 2 more findings" in message or "\\.\\.\\. and 2 more findings" in message


def test_send_notification_with_special_chars_in_path(security_scanner_agent, mock_github_client):
    """Test that file paths with special characters are properly URL-encoded."""
    results = {
        "scanned": 1,
        "total_repositories": 1,
        "failed": 0,
        "total_findings": 1,
        "repositories_with_findings": [
            {
                "repository": "juninmd/test-repo",
                "findings": [
                    {
                        "rule_id": "aws-access-token",
                        "file": "path/with spaces/config file.py",
                        "line": 10,
                        "commit": "abc123de"
                    }
                ]
            }
        ],
        "scan_errors": []
    }
    
    security_scanner_agent._send_notification(results)
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    message = call_args[0][0]
    # Verify URL encoding is applied (spaces become %20)
    assert "path/with%20spaces/config%20file.py" in message
    # Verify the URL structure is correct
    assert "github.com/juninmd/test-repo/blob/abc123de" in message


def test_send_error_notification(security_scanner_agent, mock_github_client):
    """Test sending error notification."""
    security_scanner_agent._send_error_notification("Test error message")
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    assert "Security Scanner Error" in call_args[0][0]
    assert "Test error message" in call_args[0][0]
