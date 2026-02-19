import pytest
from unittest.mock import Mock, patch
from src.agents.security_scanner.agent import SecurityScannerAgent

@pytest.fixture
def mock_jules_client():
    return Mock()

@pytest.fixture
def mock_github_client():
    client = Mock()
    client.send_telegram_msg = Mock()
    client.g = Mock()
    return client

@pytest.fixture
def mock_allowlist():
    allowlist = Mock()
    allowlist.is_allowed = Mock(return_value=True)
    return allowlist

@pytest.fixture
def security_scanner_agent(mock_jules_client, mock_github_client, mock_allowlist):
    return SecurityScannerAgent(
        jules_client=mock_jules_client,
        github_client=mock_github_client,
        allowlist=mock_allowlist,
        target_owner="juninmd"
    )

def test_notification_pagination_all_repos(security_scanner_agent, mock_github_client):
    """
    Test that 'Todos os Repositórios' section lists ALL repositories and paginates correctly.
    """
    # Create repos with very long names to force pagination
    # Telegram limit is set to 3800 in code.

    long_name_repos = []
    for i in range(30):
        # ~150 chars per name. 30 * 150 = 4500 chars.
        # This guarantees split.
        name = f"juninmd/repo-pagination-{i}-" + "x" * 100
        long_name_repos.append({
            "name": name,
            "default_branch": "main"
        })

    results = {
        "scanned": 30,
        "total_repositories": 30,
        "failed": 0,
        "total_findings": 0,
        "all_repositories": long_name_repos,
        "repositories_with_findings": [],
        "scan_errors": []
    }

    security_scanner_agent._send_notification(results)

    # Should have sent at least 2 messages
    assert mock_github_client.send_telegram_msg.call_count >= 2

    messages = [call[0][0] for call in mock_github_client.send_telegram_msg.call_args_list]

    # Verify structure
    assert "📦 *Todos os Repositórios:*" in messages[0]
    assert "⚠️ *Continuação...*" in messages[1]

    # Verify all repos are present
    total_found = 0
    for i in range(30):
        # We look for the unique part of the name
        # Note: names are escaped in telegram msg. '-' becomes '\-'
        repo_id = rf"repo\-pagination\-{i}\-"
        found = False
        for msg in messages:
            if repo_id in msg:
                found = True
                break
        if found:
            total_found += 1

    assert total_found == 30, f"Expected 30 repos, found {total_found}"
