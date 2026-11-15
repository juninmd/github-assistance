from unittest.mock import MagicMock, patch

from src.agents.pr_assistant import billing_gate as bg
from tests.test_pr_assistant_agent import _allow_merge, _success_status, mock_agent  # noqa: F401


def _file(name, patch_text):
    f = MagicMock()
    f.filename = name
    f.patch = patch_text
    return f


def _pr(files):
    pr = MagicMock()
    pr.number = 9
    pr.title = "t"
    pr.base.repo.full_name = "o/private"
    pr.head.sha = "abcdef123"
    pr.get_files.return_value = files
    pr.get_issue_comments.return_value = []
    return pr


def _billing_status():
    s = _success_status()
    s["billing_checks"] = ["ci / test"]
    return s


def _setup(agent, pr):
    agent._evaluate_comments_with_llm = MagicMock(return_value=(True, "merge"))
    _allow_merge(agent)
    agent.github_client.get_repo.return_value.get_pull.return_value = pr
    agent.github_client.merge_pr.return_value = (True, "merged")


def test_is_billing_blocked():
    assert bg.is_billing_blocked({"billing_checks": ["x"]})
    assert not bg.is_billing_blocked({"billing_checks": []})
    assert not bg.is_billing_blocked({})


def test_scan_added_lines_only_looks_at_additions():
    token = "ghp_" + "a" * 30
    pr = _pr([_file("a.py", f"@@\n-old = '{token}'\n+safe = 1\n"), _file("b.py", f"@@\n+x = '{token}'\n")])
    out = bg.scan_added_lines(pr)
    assert [f["file"] for f in out] == ["b.py"] and "a" * 10 not in str(out)


def test_merges_with_disclaimer_when_billing_blocked_and_clean(mock_agent):  # noqa: F811
    pr = _pr([_file("a.py", "@@\n+x = 1\n")])
    _setup(mock_agent, pr)
    results = {"skipped": [], "merged": []}
    with patch("src.agents.pr_assistant.merge_flow.check_pipeline_status", return_value=_billing_status()):
        mock_agent._try_merge(pr, results)
    assert len(results["merged"]) == 1
    bodies = [c.args[1] for c in mock_agent.github_client.comment_on_pr.call_args_list]
    assert any(bg.BILLING_DISCLAIMER_MARKER in b and "billing" in b.lower() for b in bodies)


def test_disclaimer_not_duplicated(mock_agent):  # noqa: F811
    pr = _pr([])
    existing = MagicMock()
    existing.body = bg.BILLING_DISCLAIMER_MARKER
    pr.get_issue_comments.return_value = [existing]
    _setup(mock_agent, pr)
    with patch("src.agents.pr_assistant.merge_flow.check_pipeline_status", return_value=_billing_status()):
        mock_agent._try_merge(pr, {"skipped": [], "merged": []})
    bodies = [c.args[1] for c in mock_agent.github_client.comment_on_pr.call_args_list]
    assert not any(bg.BILLING_DISCLAIMER_MARKER in b for b in bodies)


def test_credential_in_diff_blocks_merge_when_ci_did_not_run(mock_agent):  # noqa: F811
    pr = _pr([_file("a.py", "@@\n+k = 'ghp_" + "b" * 30 + "'\n")])
    _setup(mock_agent, pr)
    results = {"skipped": [], "merged": [], "blocked": []}
    with patch("src.agents.pr_assistant.merge_flow.check_pipeline_status", return_value=_billing_status()):
        mock_agent._try_merge(pr, results)
    assert results["merged"] == [] and "billing_blocked_credential_found" in results["blocked"][0]["reason"]
    mock_agent.github_client.merge_pr.assert_not_called()


def test_normal_green_pipeline_unaffected(mock_agent):  # noqa: F811
    pr = _pr([])
    _setup(mock_agent, pr)
    with patch("src.agents.pr_assistant.merge_flow.check_pipeline_status", return_value=_success_status()):
        mock_agent._try_merge(pr, {"skipped": [], "merged": []})
    pr.get_files.assert_not_called()
