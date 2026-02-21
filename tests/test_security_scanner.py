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
    mock_repo1.default_branch = "main"
    mock_repo1.owner.login = "juninmd"
    
    mock_repo2 = Mock()
    mock_repo2.full_name = "juninmd/repo2"
    mock_repo2.default_branch = "develop"
    mock_repo2.owner.login = "juninmd"
    
    mock_user = Mock()
    mock_user.get_repos.return_value = [mock_repo1, mock_repo2]
    
    mock_github_client.g.get_user.return_value = mock_user
    
    repos = security_scanner_agent._get_all_repositories()
    
    assert len(repos) == 2
    assert repos[0] == {"name": "juninmd/repo1", "default_branch": "main"}
    assert repos[1] == {"name": "juninmd/repo2", "default_branch": "develop"}


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
    assert "Relatório do Security Scanner" in call_args[0][0]


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
                "default_branch": "main",
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
    assert "Repositórios com Vulnerabilidades" in message
    # Account for telegram escaping
    assert "test" in message  # test-repo will be escaped
    # Verify GitHub URL is present and properly formatted
    assert "github.com" in message
    assert "blob/main" in message
    assert "config.py" in message
    assert "#L10" in message


def test_send_notification_limits_findings(security_scanner_agent, mock_github_client):
    """Test that notifications limit findings to 10 per repository."""
    # Create 11 findings to test limit of 10
    findings = []
    for i in range(11):
        findings.append({
            "rule_id": f"rule-{i}",
            "file": f"config{i}.py",
            "line": i*10,
            "commit": "abc123de"
        })

    results = {
        "scanned": 1,
        "total_repositories": 1,
        "failed": 0,
        "total_findings": 11,
        "repositories_with_findings": [
            {
                "repository": "juninmd/test-repo",
                "default_branch": "main",
                "findings": findings
            }
        ],
        "scan_errors": []
    }
    
    security_scanner_agent._send_notification(results)
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    message = call_args[0][0]
    
    # Should show exactly 10 findings
    for i in range(10):
        assert f"config{i}.py" in message

    # Should NOT show the 11th finding
    assert "config10.py" not in message

    # Should indicate remaining findings
    assert "1 outros achados" in message


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
                "default_branch": "main",
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
    # Verify the URL structure is correct with branch instead of commit
    assert "github.com/juninmd/test-repo/blob/main" in message


def test_send_error_notification(security_scanner_agent, mock_github_client):
    """Test sending error notification."""
    security_scanner_agent._send_error_notification("Test error message")
    
    mock_github_client.send_telegram_msg.assert_called_once()
    call_args = mock_github_client.send_telegram_msg.call_args
    assert "Security Scanner Error" in call_args[0][0]
    assert "Test error message" in call_args[0][0]




def test_send_notification_pagination(security_scanner_agent, mock_github_client):
    """
    Test pagination by mocking MAX_TELEGRAM_LENGTH or creating massive content.
    Since we cannot easily mock the constant inside the method without patching,
    we'll create very large content.
    """
    repos = []
    # Create 10 repos, each with enough content to consume ~500 chars
    for i in range(10):
        findings = []
        for j in range(5): # 5 findings per repo
            findings.append({
                "rule_id": f"rule-{j}",
                "file": f"path/to/file-{j}.py",
                "line": j,
                "commit": "abc123de",
                "author": "dev"
            })
        
        repos.append({
            "repository": f"juninmd/repo-{i}",
            "default_branch": "main",
            "findings": findings
        })

    results = {
        "scanned": 10,
        "total_repositories": 10,
        "failed": 0,
        "total_findings": 50,
        "repositories_with_findings": repos,
        "scan_errors": []
    }
    
    # Each repo entry will be roughly:
    # Header: ~30 chars
    # Findings: 2 * ~100 chars = 200 chars
    # overflow msg: ~20 chars
    # Total per repo ~ 250 chars.
    # 10 repos ~ 2500 chars.
    # Plus header ~ 200 chars.
    # Total ~ 2700 chars. Still under 3800.
    
    # We need to be more aggressive to trigger split. 
    # Let's inject a very long string in rule_id
    
    long_string = "a" * 1000 # 1000 chars
    
    repos_heavy = []
    for i in range(10):
        findings = [{
            "rule_id": f"rule-{long_string}", # 1000 chars
            "file": "file.py",
            "line": 1,
            "commit": "abc",
            "author": "dev"
        }]
        repos_heavy.append({
            "repository": f"juninmd/heavy-repo-{i}",
            "default_branch": "main",
            "findings": findings
        })
        
    results_heavy = {
        "scanned": 10,
        "total_repositories": 10,
        "failed": 0,
        "total_findings": 10,
        "repositories_with_findings": repos_heavy,
        "scan_errors": []
    }
    
    # Now each repo is > 1000 chars. 5 repos > 5000 chars. 
    # This MUST trigger split as 5000 > 3800.
    
    security_scanner_agent._send_notification(results_heavy)
    
    assert mock_github_client.send_telegram_msg.call_count >= 2
    
    messages = [call[0][0] for call in mock_github_client.send_telegram_msg.call_args_list]
    
    # Check flow
    assert "Relatório do Security Scanner" in messages[0]
    assert "Continuação..." in messages[1]
    
    # Verified that we have at least 5 repos detailed (indices 0-4)
    # Since all have 1 finding, order is stable or dependent on list order.
    total_repos_mentioned = 0
    for msg in messages:
        # Code uses short name and escapes it. 
        # juninmd/heavy-repo-0 -> heavy-repo-0 -> heavy\-repo\-0
        # formatted as *heavy\-repo\-0*
        total_repos_mentioned += msg.count("heavy\\-repo\\-")
        
    # We expect either all 10 detailed, or some detailed and a summary "and more..."
    # But our logic prioritization (MIN_REPOS_TO_SHOW = 5) ensures at least 5.
    
    # Since we are using 1000 chars per repo, and max is 3800.
    # Msg 1: Header (200) + Repo 0 (1000) + Repo 1 (1000) + Repo 2 (1000) = 3200.
    # Repo 3 (1000) -> 4200. No fit. Repo 3 goes to Msg 2.
    # Msg 1 has Repo 0, 1, 2. (3 repos)
    # Msg 2: Header "Continuação..." (30) + Repo 3 (1000) + Repo 4 (1000) + Repo 5 (1000) = 3030.
    # Repo 6 (1000) -> 4030. No fit. Repo 6 goes to Msg 3.
    # Msg 2 has Repo 3, 4, 5. (3 repos)
    # Msg 3: Header (30) + Repo 6 (1000) + Repo 7 (1000) + Repo 8 (1000) = 3030.
    # Msg 3 has Repo 6, 7, 8. (3 repos)
    # Msg 4: Header (30) + Repo 9 (1000). 
    # Summary? No, we show all because they are just 10.
    # Wait, loop logic:
    # if i >= MIN_REPOS_TO_SHOW (5).
    # When processing Repo 6 (i=6). 6 >= 5.
    # It checks if summary fits.
    # remaining = 10 - 6 = 4.
    # summary line = "... and 4 more". (30 chars).
    # current_message (Msg 3 so far empty? No.)
    # Msg 3 start. Repo 6 fits?
    # Wait.
    # Msg 2 ended with Repo 5.
    # Loop for Repo 6. 
    # current_message = "Continuação...".
    # len = 30.
    # full_repo_entry = 1000.
    # 30 + 1000 < 3800.
    # It fits!
    # So Repo 6 is added to Msg 3. 
    # And Repo 7, 8.
    # Repo 9.
    # So we don't summarize because we only summarize if ADDING the repo would exceed AND i >= 5.
    # Since Repo 6 fits in the new fresh message, we don't summarize yet.
    # We only summarize if we run out of space in a message AND we are past top 5.
    
    # The logic is: ensure at least top 5 are shown.
    # If we have space in the message after top 5, we show more.
    # If we run out of space after top 5, we summarize.
    # In this test case, we established that we hit the limit after Repo 5 (index 5) in Msg 2.
    # So we expect 6 repos (0-5) to be shown.
    
    assert total_repos_mentioned >= 5
    assert total_repos_mentioned == 10
    
    # And we expect a summary line in the last repository message (which is messages[1])

