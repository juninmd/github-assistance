"""Additional coverage tests for src/queue/cli.py."""

from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.queue.cli import cmd_stats, cmd_worker, main
from src.queue.store import JobStore


def _settings(tmp_path) -> Settings:
    return Settings(github_token="token", webhook_database_path=str(tmp_path / "queue.db"))


def test_queue_cli_stats_text(tmp_path, capsys):
    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "o/r#1", {"mode": "observe"}, now=1.0)

    with patch("src.queue.cli.Settings.from_env", return_value=settings):
        cmd_stats(MagicMock(json=False))
    out = capsys.readouterr().out
    assert "pending" in out
    assert "1" in out


def test_queue_cli_worker_daemon_and_interrupt(tmp_path, capsys):
    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()

    with (
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.QueueWorker.run", side_effect=KeyboardInterrupt),
    ):
        cmd_worker(MagicMock(once=False, observe=False))
    out = capsys.readouterr().out
    assert "worker started" in out
    assert "worker stopped" in out


def test_queue_cli_main_subcommands(tmp_path):
    settings = _settings(tmp_path)

    # 1. worker
    with (
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.cmd_worker") as mock_worker,
        patch("sys.argv", ["queue-worker", "worker", "--once"]),
    ):
        main()
        mock_worker.assert_called_once()

    # 2. reprocess
    with (
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.cmd_reprocess") as mock_reprocess,
        patch("sys.argv", ["queue-worker", "reprocess", "--pr", "o/r#2"]),
    ):
        main()
        mock_reprocess.assert_called_once()

    # 3. list
    with (
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.cmd_list") as mock_list,
        patch("sys.argv", ["queue-worker", "list", "--limit", "10"]),
    ):
        main()
        mock_list.assert_called_once()

    # 4. stats
    with (
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.cmd_stats") as mock_stats,
        patch("sys.argv", ["queue-worker", "stats", "--json"]),
    ):
        main()
        mock_stats.assert_called_once()


def test_queue_cli_main_dunder_entry(tmp_path):
    import runpy

    settings = _settings(tmp_path)
    with (
        patch("sys.argv", ["queue-worker", "stats", "--json"]),
        patch("src.queue.cli.Settings.from_env", return_value=settings),
        patch("src.queue.cli.cmd_stats"),
    ):
        runpy.run_module("src.queue.cli", run_name="__main__")
