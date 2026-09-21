"""MergePolicy: safe-merge decision logic (no bypass, no evidence tolerance)."""

from src.agents.pr_assistant.merge_policy import MergePolicy
from src.config.autonomy_policy import RepoAutonomy

MERGE_AUTONOMY = RepoAutonomy(mode="merge", merge=True, require_evidence=True)


def _status(state="success", *, failed=0, pending=0, cancelled=0, evidence=True):
    return {
        "state": state,
        "failed_checks": [{"context": "ci"} for _ in range(failed)],
        "pending_checks": [{"context": "ci"} for _ in range(pending)],
        "cancelled_checks": [{"context": "ci"} for _ in range(cancelled)],
        "success_checks": [{"context": "ci"}] if evidence else [],
        "has_evidence": evidence,
        "checks": {"total": 1, "success": 1, "failed": failed, "pending": pending, "cancelled": cancelled},
    }


def test_merge_when_green_with_evidence():
    decision = MergePolicy().evaluate(
        status=_status("success", evidence=True),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "merge"


def test_sha_changed_between_validation_and_merge_blocks():
    decision = MergePolicy().evaluate(
        status=_status("success", evidence=True),
        expected_sha="abc",
        current_sha="def",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "blocked"
    assert "sha_changed" in decision.reasons


def test_failed_checks_block():
    decision = MergePolicy().evaluate(
        status=_status("failure", failed=1),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "blocked"
    assert "checks_failed" in decision.reasons


def test_billing_blocked_checks_still_block_merge():
    """GitHub Actions billing outages never bypass the gate — only the reason changes."""
    status = _status("failure", failed=1)
    status["billing_blocked"] = True
    decision = MergePolicy().evaluate(
        status=status,
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "blocked"
    assert "checks_failed_billing" in decision.reasons
    assert "checks_failed" not in decision.reasons


def test_pending_checks_wait():
    decision = MergePolicy().evaluate(
        status=_status("pending", pending=1),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "wait"
    assert "checks_pending" in decision.reasons


def test_cancelled_checks_block():
    decision = MergePolicy().evaluate(
        status=_status("failure", cancelled=1),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "blocked"
    assert "checks_cancelled" in decision.reasons


def test_unknown_state_waits():
    decision = MergePolicy().evaluate(
        status=_status("unknown"),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "wait"
    assert "checks_unknown" in decision.reasons


def test_absent_evidence_waits():
    decision = MergePolicy().evaluate(
        status=_status("pending", evidence=False),
        expected_sha="abc",
        current_sha="abc",
        autonomy=MERGE_AUTONOMY,
    )
    assert decision.action == "wait"
    assert "no_evidence" in decision.reasons


def test_required_checks_missing_blocks():
    autonomy = RepoAutonomy(mode="merge", merge=True, require_evidence=True, required_checks=("lint", "test"))
    decision = MergePolicy().evaluate(
        status=_status("success", evidence=True),
        expected_sha="abc",
        current_sha="abc",
        autonomy=autonomy,
    )
    assert decision.action == "blocked"
    assert any(r.startswith("missing_checks:") for r in decision.reasons)


def test_observe_autonomy_blocks_even_with_green_checks():
    autonomy = RepoAutonomy(mode="observe", merge=False)
    decision = MergePolicy().evaluate(
        status=_status("success", evidence=True),
        expected_sha="abc",
        current_sha="abc",
        autonomy=autonomy,
    )
    assert decision.action == "blocked"
    assert "autonomy_mode:observe" in decision.reasons
