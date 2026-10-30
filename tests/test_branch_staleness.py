"""Tests for PR-base staleness detection."""

from unittest.mock import MagicMock

from src.agents.pr_assistant.branch_staleness import commits_behind


def _pr(behind):
    pr = MagicMock()
    pr.base.ref = "master"
    pr.head.ref = "feature"
    pr.base.repo.compare.return_value.behind_by = behind
    return pr


def test_commits_behind_value():
    assert commits_behind(_pr(15)) == 15
    assert commits_behind(_pr(0)) == 0


def test_commits_behind_negative_is_clamped():
    assert commits_behind(_pr(-3)) == 0


def test_commits_behind_unknown_returns_zero():
    pr = MagicMock()
    pr.base.repo.compare.side_effect = RuntimeError("no permission")
    assert commits_behind(pr) == 0


def test_commits_behind_non_int_returns_zero():
    assert commits_behind(MagicMock()) == 0
