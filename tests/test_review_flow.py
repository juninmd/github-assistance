"""Tests for the review workspace (clone/exec) and review orchestration."""

import os
import subprocess
from unittest.mock import MagicMock

import pytest

from src.agents.pr_assistant import review_flow
from src.agents.pr_assistant import review_workspace as ws


def _pr():
    pr = MagicMock()
    pr.title = "Titulo"
    pr.head.sha = "sha123"
    pr.head.ref = "feature"
    pr.head.repo.full_name = "juninmd/x"
    pr.base.ref = "main"
    pr.get_files.return_value = []
    return pr


class _Completed:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


# --- review_workspace --------------------------------------------------------

def test_cleanup_stale_review_dirs(tmp_path):
    old = tmp_path / "pr-review-old"
    old.mkdir()
    os.utime(old, (0, 0))
    fresh = tmp_path / "pr-review-new"
    fresh.mkdir()
    ws.cleanup_stale_review_dirs(str(tmp_path))
    assert not old.exists()
    assert fresh.exists()


def test_litellm_base_normalizes(monkeypatch):
    monkeypatch.setenv("LITELLM_API_BASE", "http://x:4000")
    assert ws.litellm_base() == "http://x:4000/v1"
    monkeypatch.setenv("LITELLM_API_BASE", "http://x:4000/v1/")
    assert ws.litellm_base() == "http://x:4000/v1"


def test_review_timeout_and_model_defaults(monkeypatch):
    monkeypatch.delenv("OPENCODE_REVIEW_TIMEOUT", raising=False)
    monkeypatch.delenv("OPENCODE_REVIEW_MODEL", raising=False)
    assert ws.review_timeout() == 300
    assert ws.review_model() == "litellm/cloud/auto"
    monkeypatch.setenv("OPENCODE_REVIEW_TIMEOUT", "15")
    monkeypatch.setenv("OPENCODE_REVIEW_MODEL", "litellm/other")
    assert ws.review_timeout() == 15
    assert ws.review_model() == "litellm/other"


def test_write_opencode_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_API_BASE", "http://litellm:4000/v1")
    ws.write_opencode_config(str(tmp_path))
    text = (tmp_path / "opencode.json").read_text(encoding="utf-8")
    assert "litellm" in text and "cloud/auto" in text and "http://litellm:4000/v1" in text


def test_run_opencode_success_failure_and_timeout(monkeypatch):
    monkeypatch.setattr(ws, "proc_run", lambda *a, **k: _Completed(0, "out"))
    assert ws.run_opencode("/tmp", "p", "m", 1) == "out"
    monkeypatch.setattr(ws, "proc_run", lambda *a, **k: _Completed(1))
    assert ws.run_opencode("/tmp", "p", "m", 1) is None

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(["opencode"], 1)

    monkeypatch.setattr(ws, "proc_run", _boom)
    assert ws.run_opencode("/tmp", "p", "m", 1) is None


def test_local_diff_truncates(monkeypatch):
    monkeypatch.setattr(ws, "proc_run", lambda *a, **k: _Completed(0, "x" * 100))
    assert ws.local_diff("/tmp", "main", 10) == "x" * 10


def test_clone_pr_head_raises_on_failure(monkeypatch):
    monkeypatch.setattr(ws, "proc_run", lambda *a, **k: _Completed(1))
    with pytest.raises(RuntimeError):
        ws.clone_pr_head(_pr(), "/tmp", "tok")


# --- review_flow -------------------------------------------------------------

def test_run_review_without_token_and_client(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_PAT", raising=False)
    assert review_flow.run_review(_pr()) is None


def test_run_review_falls_back_to_litellm(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(review_flow, "_via_opencode", lambda *a: None)
    client = MagicMock()
    client.generate.return_value = '{"verdict":"APPROVE","summary":"ok"}'
    verdict = review_flow.run_review(_pr(), client)
    assert verdict is not None and verdict.approved


def test_run_review_parses_opencode_output(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(
        review_flow, "_via_opencode",
        lambda *a: '{"verdict":"REQUEST_CHANGES","summary":"x"}',
    )
    verdict = review_flow.run_review(_pr())
    assert verdict is not None and verdict.verdict == "REQUEST_CHANGES"


def test_via_opencode_success(monkeypatch):
    monkeypatch.setattr(ws, "clone_pr_head", lambda pr, tmp, tok: tmp)
    monkeypatch.setattr(ws, "write_opencode_config", lambda d: None)
    monkeypatch.setattr(ws, "local_diff", lambda d, b, m: "diff")
    monkeypatch.setattr(ws, "run_opencode", lambda d, p, m, t: "raw")
    assert review_flow._via_opencode(_pr(), "tok", "m") == "raw"


def test_via_opencode_cleans_tempdir_on_failure(monkeypatch):
    state: dict = {}

    class _FakeTmp:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return "/tmp/fake-review"

        def __exit__(self, *a):
            state["exited"] = True
            return False

    monkeypatch.setattr(review_flow.tempfile, "TemporaryDirectory", _FakeTmp)
    monkeypatch.setattr(ws, "clone_pr_head", MagicMock(side_effect=RuntimeError("clone failed")))
    monkeypatch.setattr(review_flow.shutil, "rmtree", lambda *a, **k: state.setdefault("rm", True))
    assert review_flow._via_opencode(_pr(), "tok", "m") is None
    assert state.get("exited") is True
    assert state.get("rm") is True
