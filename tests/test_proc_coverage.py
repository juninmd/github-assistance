"""Additional coverage tests for src/utils/proc.py."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.utils.proc import _terminate_tree, run


def test_run_with_input_passes_stdin():
    result = run(
        [sys.executable, "-c", "import sys; print('got:' + sys.stdin.read().strip())"],
        input="hello world",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "got:hello world"


def test_run_without_capture_output():
    # capture_output=False branch
    result = run(
        [sys.executable, "-c", "print('quiet')"],
        capture_output=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout is None
    assert result.stderr is None


def test_run_handles_base_exception_and_terminates():
    with patch("subprocess.Popen.communicate", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=10)


def test_terminate_tree_handles_os_errors():
    proc = MagicMock()
    proc.pid = 12345
    # Simulate os.killpg raising OSError
    with (
        patch("os.killpg", side_effect=OSError("Process lookup failed")),
        patch("os.getpgid", return_value=12345),
    ):
        _terminate_tree(proc)
        proc.kill.assert_called_once()


def test_terminate_tree_missing_killpg_or_getpgid():
    proc = MagicMock()
    proc.pid = 12345
    with patch("os.killpg", None):
        _terminate_tree(proc)
        proc.kill.assert_called_once()


def test_terminate_tree_non_posix():
    proc = MagicMock()
    proc.pid = 12345
    with patch("src.utils.proc._POSIX", False):
        _terminate_tree(proc)
        proc.kill.assert_called_once()


def test_run_non_posix():
    with patch("src.utils.proc._POSIX", False):
        res = run(
            [sys.executable, "-c", "print('no-posix')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert res.returncode == 0
        assert res.stdout.strip() == "no-posix"
