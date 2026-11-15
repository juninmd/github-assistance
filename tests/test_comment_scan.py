from unittest.mock import MagicMock

from src.agents.pr_assistant import billing_gate as bg
from src.agents.pr_assistant import comment_scan as cs
from tests.test_pr_assistant_agent import mock_agent  # noqa: F401

TOKEN = "ghp_" + "c" * 30


def _c(cid, body):
    c = MagicMock()
    c.id, c.body, c.html_url = cid, body, f"https://x/{cid}"
    return c


def test_warns_once_per_exposed_comment_without_echoing_value():
    comments = [_c(1, f"my token {TOKEN}"), _c(2, "all good")]
    warns = cs.pending_warnings(comments)
    assert len(warns) == 1 and TOKEN not in warns[0] and "github-pat" in warns[0]
    comments.append(_c(3, warns[0]))  # warning already posted
    assert cs.pending_warnings(comments) == []


def test_our_warning_is_not_rescanned():
    assert cs.find_exposed_comments([_c(5, cs.WARNING_MARKER.format(id=1) + TOKEN)]) == []


def test_flow_posts_warning(mock_agent):  # noqa: F811
    mock_agent.simulation_mode = False
    pr = MagicMock()
    mock_agent._warn_exposed_comment_secrets(pr, [_c(1, TOKEN)])
    assert mock_agent.github_client.comment_on_pr.call_count == 1


def test_flow_silent_in_simulation(mock_agent):  # noqa: F811
    mock_agent.simulation_mode = True
    mock_agent._warn_exposed_comment_secrets(MagicMock(), [_c(1, TOKEN)])
    mock_agent.github_client.comment_on_pr.assert_not_called()


def test_forbidden_files():
    for p in (".env", "a/.env.production", "id_rsa", "certs/server.pem", "k/app.key"):
        assert bg.is_forbidden_file(p), p
    for p in (".env.example", "tests/fixtures/x.pem", "src/app.py"):
        assert not bg.is_forbidden_file(p), p


def test_billing_scan_flags_tracked_secret_file_but_not_deletions():
    added, removed = MagicMock(), MagicMock()
    added.filename, added.status, added.patch = "prod/.env", "added", "@@\n+A=1\n"
    removed.filename, removed.status, removed.patch = "old/.env", "removed", ""
    pr = MagicMock()
    pr.get_files.return_value = [added, removed]
    out = bg.scan_added_lines(pr)
    assert [(f["file"], f["rule_id"]) for f in out] == [("prod/.env", "forbidden-secret-file")]
