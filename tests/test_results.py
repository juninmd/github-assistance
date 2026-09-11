"""RunResult typed contract + batch failure propagation."""

from src.results import RunResult, item_count
from src.run_agent import _any_batch_failure, is_failed_result


def test_item_count_does_not_count_dict_keys():
    assert item_count(["a", "b"]) == 2
    assert item_count(("a",)) == 1
    assert item_count({"done": {"x": 1}, "skipped": {}}) == 0


def test_run_result_from_agent_dict():
    result = RunResult.from_agent_dict(
        "pr-assistant",
        {
            "merged": [{"pr": 1}],
            "pipeline_failures": [{"pr": 2}],
            "skipped": [{"pr": 3}],
            "blocked": [{"pr": 4}],
            "sha": "abc",
        },
    )
    assert result.items_done == 1
    assert result.items_failed == 1
    assert result.items_skipped == 1
    assert result.items_blocked == 1
    assert result.status == "blocked"
    assert result.cost is None


def test_run_result_cost_never_invented():
    result = RunResult.from_agent_dict("agent", {"merged": [{"pr": 1}]})
    assert result.cost is None
    data = result.to_dict()
    assert "cost" in data and data["cost"] is None


def test_pr_pipeline_failure_alone_is_blocked_not_failed_run():
    result = RunResult.from_agent_dict("pr-assistant", {"pipeline_failures": [{"pr": 2}]})
    assert result.status == "blocked"
    assert result.items_failed == 1
    assert is_failed_result({"_run_result": result.to_dict()}) is False


def test_is_failed_result_via_run_result():
    assert is_failed_result({"error": "x"}) is True
    assert is_failed_result({"status": "failed"}) is True
    assert is_failed_result({"_run_result": {"status": "failed"}}) is True
    # A PR waiting on CI must not fail the scheduled job (K8s retries/alerts).
    assert is_failed_result({"_run_result": {"status": "blocked"}}) is False
    assert is_failed_result({"_run_result": {"status": "succeeded"}}) is False


def test_any_batch_failure():
    assert _any_batch_failure({"a": {"status": "ok"}}) is False
    assert _any_batch_failure({"a": {"status": "ok"}, "b": {"error": "boom"}}) is True
    assert _any_batch_failure({"error": "top"}) is True
