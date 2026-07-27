"""Regression tests for src.utils.proc: timeouts must not leak child processes."""

import os
import subprocess
import sys
import textwrap

import pytest

from src.utils.proc import run

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")


def test_run_returns_completed_process():
    result = run(
        [sys.executable, "-c", "print('hi')"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_run_check_raises_on_failure():
    with pytest.raises(subprocess.CalledProcessError):
        run([sys.executable, "-c", "raise SystemExit(3)"], capture_output=True, check=True)


def test_run_timeout_raises_timeout_expired():
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=1)


@POSIX_ONLY
def test_run_starts_child_in_its_own_session():
    result = run(
        [sys.executable, "-c", "import os; print(os.getpid() == os.getpgid(0))"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == "True"


@POSIX_ONLY
def test_timeout_kills_grandchildren(tmp_path):
    """The bug this module exists for: subprocess.run leaves grandchildren alive."""
    marker = tmp_path / "grandchild.pid"
    script = textwrap.dedent(
        f"""
        import os, subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open({str(marker)!r}, "w").write(str(child.pid))
        time.sleep(60)
        """
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", script], capture_output=True, timeout=5)

    grandchild_pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)
