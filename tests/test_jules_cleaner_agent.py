from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.agents.jules_cleaner.agent import JulesCleanerAgent


def _agent(jules: MagicMock) -> JulesCleanerAgent:
    return JulesCleanerAgent(
        jules_client=jules,
        github_client=MagicMock(),
        allowlist=MagicMock(),
        telegram=MagicMock(),
    )


def test_deletes_only_old_sessions():
    old = (datetime.now(UTC) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    jules = MagicMock()
    from src.jules.client import JulesClient

    jules._parse_create_time.side_effect = JulesClient("key")._parse_create_time
    jules.list_sessions.return_value = [
        {"name": "sessions/old", "createTime": old},
        {"name": "sessions/recent", "createTime": recent},
    ]

    result = _agent(jules).run()

    assert result["status"] == "success"
    assert result["scanned"] == 2
    assert result["deleted"] == 1
    assert result["skipped_recent"] == 1
    jules.delete_session.assert_called_once_with("sessions/old")


def test_reports_delete_failures():
    old = (datetime.now(UTC) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    jules = MagicMock()
    from src.jules.client import JulesClient

    jules._parse_create_time.side_effect = JulesClient("key")._parse_create_time
    jules.list_sessions.return_value = [{"id": "old", "createTime": old}]
    jules.delete_session.side_effect = RuntimeError("boom")

    result = _agent(jules).run()

    assert result["status"] == "failed"
    assert result["failed"] == 1
    assert result["failed_sessions"] == ["old"]


@patch.dict("os.environ", {"JULES_CLEANER_MAX_AGE_DAYS": "7", "JULES_CLEANER_PAGE_SIZE": "50"})
def test_uses_retention_env():
    jules = MagicMock()
    jules.list_sessions.return_value = []

    result = _agent(jules).run()

    assert result["retention_days"] == 7
    jules.list_sessions.assert_called_once_with(page_size=50, timeout=90)
