from unittest.mock import MagicMock, patch

from src.agents.pr_assistant import credential_gate, review_flow
from src.agents.pr_assistant import review_verdict as rv

FAKE_TOKEN = "ghp_" + "A" * 36


def test_added_lines_ignores_removed_and_headers():
    patch_text = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old line\n+new line\n context"
    assert credential_gate.added_lines(patch_text) == "new line"
    assert "old line" not in credential_gate.added_lines(patch_text)


def test_clean_text_has_no_verdict():
    assert credential_gate.credential_verdict("print('hello')") is None


def test_token_in_added_text_blocks_without_echoing_value():
    verdict = credential_gate.credential_verdict(f"TOKEN = '{FAKE_TOKEN}'")
    assert verdict is not None
    assert verdict.verdict == rv.REQUEST_CHANGES
    assert verdict.blocks("error")
    assert all(FAKE_TOKEN not in f.issue for f in verdict.findings)


def test_run_review_blocks_pr_with_leaked_credential_before_any_model():
    file = MagicMock(patch=f"+++ b/app.py\n+TOKEN = '{FAKE_TOKEN}'")
    pr = MagicMock(number=7)
    pr.get_files.return_value = [file]
    with patch.object(review_flow, "_via_clone") as via_clone, \
            patch.object(review_flow.ws, "cleanup_stale_review_dirs"):
        verdict = review_flow.run_review(pr, ai_client=None)
    assert verdict is not None and verdict.blocks("error")
    via_clone.assert_not_called()


def test_regenerate_lockfiles_resets_and_regenerates_pnpm_lock():
    from src.agents.pr_assistant import conflict_resolver as cr

    ok_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch.object(cr, "proc_run", return_value=ok_proc) as run:
        ok, msg = cr._regenerate_lockfiles("/tmp/dir", ["pnpm-lock.yaml", "src/a.py"])
    assert ok is True and msg == "lockfile regenerated"
    cmds = [c.args[0] for c in run.call_args_list]
    assert ["git", "checkout", "--ours", "--", "pnpm-lock.yaml"] in cmds
    assert ["pnpm", "install", "--lockfile-only", "--ignore-scripts"] in cmds


def test_regenerate_lockfiles_fails_closed_when_tool_missing():
    from src.agents.pr_assistant import conflict_resolver as cr

    def fake_run(cmd, **_):
        if cmd[0] == "git":
            return MagicMock(returncode=0, stdout="", stderr="")
        raise FileNotFoundError(cmd[0])

    with patch.object(cr, "proc_run", side_effect=fake_run):
        ok, msg = cr._regenerate_lockfiles("/tmp/dir", ["yarn.lock"])
    assert ok is False and "yarn" in msg
