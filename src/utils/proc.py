"""Subprocess execution that never leaves orphaned children behind.

``subprocess.run(..., timeout=...)`` only kills the *direct* child when the
timeout fires. Grandchildren (git's transport/index-pack helpers, node workers)
survive: they keep burning I/O and are reparented to PID 1. In a container whose
PID 1 is not an init that reaps (``uv``), they pile up as zombies forever.

``run`` below is a drop-in replacement that starts the child in its own session
and signals the whole process group on timeout, so the entire tree dies with it.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any

__all__ = ["run"]

_POSIX = os.name == "posix"


def _terminate_tree(process: subprocess.Popen[Any]) -> None:
    """Kill the child and everything it spawned."""
    if _POSIX:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    process.kill()


def run(
    *popenargs: Any,
    input: Any = None,  # noqa: A002 - mirrors subprocess.run's signature
    capture_output: bool = False,
    timeout: float | None = None,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Like ``subprocess.run``, but a timeout kills the whole process group."""
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if _POSIX:
        kwargs.setdefault("start_new_session", True)

    with subprocess.Popen(*popenargs, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_tree(process)
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                process.args, timeout, output=stdout, stderr=stderr
            ) from exc
        except BaseException:
            _terminate_tree(process)
            process.wait()
            raise
        returncode = process.poll()

    if check and returncode:
        raise subprocess.CalledProcessError(
            returncode or 0, process.args, output=stdout, stderr=stderr
        )
    return subprocess.CompletedProcess(process.args, returncode or 0, stdout, stderr)
