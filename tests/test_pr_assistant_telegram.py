from unittest.mock import MagicMock

from src.agents.pr_assistant.telegram_summary import build_and_send_summary


def test_build_and_send_summary_empty():
    telegram = MagicMock()
    results = {}
    build_and_send_summary(results, telegram, "test_owner")
    telegram.send_message.assert_not_called()


def test_build_and_send_summary_merged():
    telegram = MagicMock()
    telegram.escape = lambda x: x.replace("#", "\\#").replace(".", "\\.").replace("-", "\\-")

    results = {
        "merged": [
            {"repository": "repo1", "pr": 1, "title": "PR 1"},
            {"repository": "repo2", "pr": 2, "title": "PR 2"},
            {"repository": "repo3", "pr": 3, "title": "PR 3"},
            {"repository": "repo4", "pr": 4, "title": "PR 4"},
            {"repository": "repo5", "pr": 5, "title": "PR 5"},
            {"repository": "repo6", "pr": 6, "title": "PR 6"},
            {"repository": "repo7", "pr": 7, "title": "PR 7"},
            {"repository": "repo8", "pr": 8, "title": "PR 8"},
            {"repository": "repo9", "pr": 9, "title": "PR 9"},
            {"repository": "repo10", "pr": 10, "title": "PR 10"},
            {"repository": "repo11", "pr": 11, "title": "PR 11"},
        ]
    }

    build_and_send_summary(results, telegram, "test_owner")
    telegram.send_message.assert_called_once()
    msg = telegram.send_message.call_args[0][0]

    assert "Merged" in msg
    assert "repo1" in msg
    assert "repo11" not in msg
    assert "\\+ 1 outros\\.\\.\\." in msg


def test_build_and_send_summary_conflicts():
    telegram = MagicMock()
    telegram.escape = lambda x: x.replace("#", "\\#").replace(".", "\\.").replace("-", "\\-")

    results = {
        "conflicts_resolved": [
            {"repository": "repo1", "pr": 1, "title": "PR 1"},
        ]
    }

    build_and_send_summary(results, telegram, "test_owner")
    telegram.send_message.assert_called_once()
    msg = telegram.send_message.call_args[0][0]

    assert "Conflitos resolvidos" in msg
    assert "repo1" in msg


def test_build_and_send_summary_pipeline_failures():
    telegram = MagicMock()
    telegram.escape = lambda x: x.replace("#", "\\#").replace(".", "\\.").replace("-", "\\-")

    results = {
        "pipeline_failures": [
            {"repository": "repo1", "pr": 1, "title": "PR 1", "state": "failure"},
            {"repository": "repo2", "pr": 2, "title": "PR 2", "state": "failure", "coverage": 85.5},
            {"repository": "repo3", "pr": 3, "title": "PR 3", "state": "failure", "coverage": [{"check": "codecov", "coverage": 90.0}]},
            {"repository": "repo4", "pr": 4, "title": "PR 4", "state": "failure", "coverage": []},
        ]
    }

    build_and_send_summary(results, telegram, "test_owner")
    telegram.send_message.assert_called_once()
    msg = telegram.send_message.call_args[0][0]

    assert "Pipeline failures" in msg
    assert "repo1" in msg
    assert "failure" in msg
    assert "85.5%" in msg
    assert "90\\.0%" in msg


def test_build_and_send_summary_skipped():
    telegram = MagicMock()
    telegram.escape = lambda x: x.replace("#", "\\#").replace(".", "\\.").replace("-", "\\-")

    results = {
        "skipped": [
            {"repository": "repo1", "pr": 1, "title": "PR 1", "reason": "reason1"},
            {"repository": "repo2", "pr": 2, "title": "PR 2", "reason": "reason1"},
            {"repository": "repo3", "pr": 3, "title": "PR 3", "reason": "reason1"},
            {"repository": "repo4", "pr": 4, "title": "PR 4", "reason": "reason1"},
            {"repository": "repo5", "pr": 5, "title": "PR 5", "reason": "reason1"},
            {"repository": "repo6", "pr": 6, "title": "PR 6", "reason": "reason1"},
            {"repository": "repo7", "pr": 7, "title": "PR 7", "reason": "reason2"},
        ]
    }

    build_and_send_summary(results, telegram, "test_owner")
    telegram.send_message.assert_called_once()
    msg = telegram.send_message.call_args[0][0]

    assert "Skipped" in msg
    assert "reason1" in msg
    assert "reason2" in msg
    assert "\\+ 1 outros\\.\\.\\." in msg
    assert "repo7" in msg
