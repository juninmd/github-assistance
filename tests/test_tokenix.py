import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from src.insight.cost import record_trace, summarize_tokenix
from src.utils import tokenix


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("OPENCODE_CONFIG_CONTENT", "TOKENIX_ENABLED", "TOKENIX_BIN"):
        monkeypatch.delenv(name, raising=False)
    tokenix.version.cache_clear()


def _fake_bin(monkeypatch, tmp_path, rc=0):
    exe = tmp_path / "tokenix"
    exe.write_text(f"#!/bin/sh\n[ \"$1\" = --version ] && echo 'tokenix 9.9.9'\nexit {rc}\n")
    exe.chmod(0o755)
    monkeypatch.setenv("TOKENIX_BIN", str(exe))
    return str(exe)


def test_configure_registers_mcp_and_merges(monkeypatch, tmp_path):
    exe = _fake_bin(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", json.dumps({"mcp": {"other": {"type": "local"}}, "x": 1}))
    assert tokenix.configure_environ() is True
    cfg = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
    assert cfg["x"] == 1 and "other" in cfg["mcp"]
    assert cfg["mcp"]["tokenix"]["command"] == [exe, "mcp"]
    assert tokenix.is_active() is True
    assert tokenix.harness_suffix(True) == " + tokenix 9.9.9"
    assert tokenix.harness_suffix(False) == ""


def test_toggle_off_and_missing_binary(monkeypatch, tmp_path):
    _fake_bin(monkeypatch, tmp_path)
    monkeypatch.setenv("TOKENIX_ENABLED", "false")
    assert tokenix.configure_environ() is False
    assert "OPENCODE_CONFIG_CONTENT" not in os.environ
    monkeypatch.setenv("TOKENIX_ENABLED", "true")
    monkeypatch.setenv("TOKENIX_BIN", str(tmp_path / "nope"))
    assert tokenix.configure_environ() is False and tokenix.is_active() is False


def test_invalid_existing_config_is_untouched(monkeypatch, tmp_path):
    _fake_bin(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", "{not json")
    assert tokenix.configure_environ() is False
    assert os.environ["OPENCODE_CONFIG_CONTENT"] == "{not json"


def test_session_inactive_yields_false(tmp_path):
    with tokenix.session(str(tmp_path)) as ready:
        assert ready is False


def test_session_indexes_and_cleans_up(monkeypatch, tmp_path):
    _fake_bin(monkeypatch, tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TOKENIX_HOME", str(home))
    tokenix.configure_environ()
    clone = tmp_path / "clone"
    clone.mkdir()
    files = tokenix._project_files(str(clone))
    assert files == []
    ident = tokenix.hashlib.sha256(os.path.realpath(clone).encode()).hexdigest()[:16]
    (home / f"{ident}.db").write_text("x")
    keep = home / "filters.toml"
    keep.write_text("x")
    with tokenix.session(str(clone)) as ready:
        assert ready is True
        assert (home / f"{ident}.db").exists()
    assert not (home / f"{ident}.db").exists() and keep.exists()


def test_session_index_failure_is_fail_open(monkeypatch, tmp_path):
    _fake_bin(monkeypatch, tmp_path, rc=3)
    monkeypatch.setenv("TOKENIX_HOME", str(tmp_path / "h"))
    tokenix.configure_environ()
    logs = []
    with tokenix.session(str(tmp_path), lambda *a: logs.append(a)) as ready:
        assert ready is False
    assert logs and "index rc=3" in logs[0][0]


def test_session_index_timeout_is_fail_open(monkeypatch, tmp_path):
    _fake_bin(monkeypatch, tmp_path)
    monkeypatch.setenv("TOKENIX_HOME", str(tmp_path / "h"))
    tokenix.configure_environ()

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("tokenix", 1)

    monkeypatch.setattr(tokenix.subprocess, "run", boom)
    with tokenix.session(str(tmp_path)) as ready:
        assert ready is False


def test_sweep_stale_only_touches_index_files(monkeypatch, tmp_path):
    monkeypatch.setenv("TOKENIX_HOME", str(tmp_path))
    old = tmp_path / ("a" * 16 + ".db")
    fresh = tmp_path / ("b" * 16 + ".db")
    other = tmp_path / "filters.toml"
    for f in (old, fresh, other):
        f.write_text("x")
    os.utime(old, (1, 1))
    os.utime(other, (1, 1))
    tokenix.sweep_stale()
    assert not old.exists() and fresh.exists() and other.exists()


def test_calls_counts_only_tokenix_tools():
    assert tokenix.calls(("read", "tokenix_symbols", "tokenix_graph", "bash")) == 2


def test_ledger_compares_with_and_without(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv("AI_USAGE_LOG", str(log))

    def trace(harness, tin, tools=()):
        return SimpleNamespace(
            harness=harness, model="m", skills_used=(), skills_available=(), tokens_in=tin,
            tokens_out=10, cost=0.0, tools=tools,
        )

    record_trace(trace("opencode 2.3.0", 1000))
    record_trace(trace("opencode 2.3.0 + tokenix 1.1.1", 400, ("tokenix_symbols", "read")))
    out = summarize_tokenix(str(log))
    assert out["without"]["mean_tokens"] == 1010 and out["without"]["runs"] == 1
    assert out["with"]["mean_tokens"] == 410 and out["with"]["tokenix_calls"] == 1
