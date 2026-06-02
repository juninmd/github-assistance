from unittest.mock import MagicMock, patch

from src.agents.conflict_resolver.agent import ConflictResolverAgent


def _agent() -> ConflictResolverAgent:
    agent = ConflictResolverAgent(
        github_client=MagicMock(),
        jules_client=MagicMock(),
        telegram=MagicMock(),
        allowlist=MagicMock(),
        target_owner="juninmd",
    )
    agent.telegram.escape_html = lambda value: value
    return agent


@patch("src.agents.conflict_resolver.agent.resolve_conflicts_autonomously")
def test_process_conflict_failure_marks_manual_without_closing(mock_resolve):
    agent = _agent()
    pr = MagicMock()
    pr.number = 123
    pr.user.login = "dependabot[bot]"
    pr.base.repo.full_name = "owner/repo"
    pr.html_url = "https://github.com/owner/repo/pull/123"
    pr.title = "Update dependency"
    results = {"resolved": [], "manual": []}
    mock_resolve.return_value = (False, "Unresolved conflict files remain: package.json")
    agent.github_client.add_label_to_pr.return_value = (True, "label added")

    agent._process_conflict(pr, results)

    assert results["resolved"] == []
    assert results["manual"] == [
        {"pr": 123, "repo": "owner/repo", "error": "Unresolved conflict files remain: package.json"}
    ]
    agent.github_client.comment_on_pr.assert_called_once()
    agent.github_client.add_label_to_pr.assert_called_once_with(
        pr, ConflictResolverAgent.MANUAL_CONFLICT_LABEL
    )
    pr.edit.assert_not_called()
