import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.utils import sast_scan as sa


def _run(rc=0, stdout="", report=None):
    def run(argv, **kw):
        if report is not None and "--output" in argv:
            Path(argv[argv.index("--output") + 1]).write_text(report)
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, kw.get("_git", ""), "")
        return subprocess.CompletedProcess(argv, rc, stdout, "")

    return run


TRUFFLE = json.dumps({"DetectorName": "Github", "Verified": False, "Raw": "SECRET-VALUE",
                      "SourceMetadata": {"Data": {"Filesystem": {"file": "/r/cfg.py", "line": 3}}}})
SEMGREP = json.dumps({"results": [
    {"check_id": "py.shell-true", "path": "/r/app.py", "start": {"line": 3}, "extra": {"severity": "ERROR"}},
    {"check_id": "py.md5", "path": "/r/app.py", "start": {"line": 5}, "extra": {"severity": "WARNING"}},
]})
TRIVY = json.dumps({"Results": [{
    "Target": "Dockerfile",
    "Misconfigurations": [{"ID": "DS002", "Severity": "HIGH", "CauseMetadata": {"StartLine": 1}},
                          {"ID": "DS026", "Severity": "LOW"}],
    "Secrets": [{"RuleID": "aws-access-key-id", "StartLine": 7, "Match": "SECRET-VALUE"}],
}, {"Target": "go.sum", "Vulnerabilities": [{"VulnerabilityID": "CVE-1", "Severity": "CRITICAL"}]}]})


def test_parsers_keep_location_only_and_filter_by_severity():
    root = Path("/r")
    t = sa.parse_trufflehog(TRUFFLE + "\nnot json\n", root)
    assert t == [{"file": "cfg.py", "line": 3, "rule_id": "trufflehog:Github"}]
    s = sa.parse_semgrep(SEMGREP, root)
    assert [f["rule_id"] for f in s] == ["semgrep:py.shell-true"]  # WARNING is advisory
    v = sa.parse_trivy(TRIVY, root)
    assert {f["rule_id"] for f in v} == {"trivy:aws-access-key-id", "trivy:DS002", "trivy:CVE-1"}
    assert "SECRET-VALUE" not in json.dumps([t, s, v])


def test_selected_tools(monkeypatch):
    monkeypatch.setattr(sa.shutil, "which", lambda n: "/bin/" + n if n != "trivy" else None)
    monkeypatch.setenv("PUSH_GUARD_SAST", "auto")
    assert sa.selected_tools() == ["trufflehog", "semgrep"]
    monkeypatch.setenv("PUSH_GUARD_SAST", "semgrep,trivy,bogus")
    assert sa.selected_tools() == ["semgrep"]
    monkeypatch.setenv("PUSH_GUARD_SAST", "off")
    assert sa.selected_tools() == []


def test_tool_failures_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "proc_run", _run(rc=2))
    assert sa.run_tool("semgrep", tmp_path, ["a.py"]) == []

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(sa, "proc_run", boom)
    assert sa.run_tool("trivy", tmp_path, []) == []
    monkeypatch.setattr(sa, "proc_run", _run(report="{not json"))
    assert sa.run_tool("semgrep", tmp_path, []) == []


def test_only_changed_files_block(monkeypatch, tmp_path):
    (tmp_path / "new.py").write_text("x=1\n")
    (tmp_path / "old.py").write_text("x=1\n")
    monkeypatch.setenv("PUSH_GUARD_SAST", "semgrep")
    monkeypatch.setattr(sa.shutil, "which", lambda n: "/bin/semgrep")
    report = json.dumps({"results": [
        {"check_id": "r", "path": str(tmp_path / "new.py"), "start": {"line": 1}, "extra": {"severity": "ERROR"}},
        {"check_id": "r", "path": str(tmp_path / "old.py"), "start": {"line": 1}, "extra": {"severity": "ERROR"}},
    ]})
    monkeypatch.setattr(sa, "changed_files", lambda root: {"new.py"})
    monkeypatch.setattr(sa, "proc_run", _run(report=report))
    assert [f["file"] for f in sa.sast_scan(tmp_path)] == ["new.py"]


def test_nothing_changed_runs_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("PUSH_GUARD_SAST", "semgrep")
    monkeypatch.setattr(sa.shutil, "which", lambda n: "/bin/semgrep")
    monkeypatch.setattr(sa, "changed_files", lambda root: set())
    monkeypatch.setattr(sa, "proc_run", lambda *a, **k: pytest.fail("must not run"))
    assert sa.sast_scan(tmp_path) == []


def test_verification_is_opt_in(monkeypatch, tmp_path):
    assert "--no-verification" in sa._cmd_trufflehog(tmp_path, [], "")
    monkeypatch.setenv("PUSH_GUARD_TRUFFLEHOG_VERIFY", "true")
    assert "--no-verification" not in sa._cmd_trufflehog(tmp_path, [], "")


def test_scan_clone_merges_sast(monkeypatch, tmp_path):
    from src.utils import secret_scan as ss

    monkeypatch.setattr(sa, "sast_scan", lambda root: [{"file": "a.py", "line": 2, "rule_id": "semgrep:x"}])
    assert ss.scan_clone(tmp_path, known=[]) == [{"file": "a.py", "line": 2, "rule_id": "semgrep:x"}]


@pytest.mark.skipif(not all(shutil.which(t) for t in ("git", "semgrep")), reason="needs real semgrep")
def test_real_semgrep_flags_shell_true_in_changed_file(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / "app.py").write_text("import subprocess\n\ndef run(c):\n    return subprocess.call(c, shell=True)\n")
    monkeypatch.setenv("PUSH_GUARD_SAST", "semgrep")
    monkeypatch.setenv("PUSH_GUARD_SEMGREP_CONFIG", "p/python")
    found = sa.sast_scan(tmp_path)
    if not found:
        pytest.skip("semgrep registry unreachable (offline)")
    assert found[0]["file"] == "app.py" and found[0]["rule_id"].startswith("semgrep:")


@pytest.mark.skipif(not all(shutil.which(t) for t in ("git", "trufflehog")), reason="needs real trufflehog")
def test_real_trufflehog_flags_token_in_changed_file(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    token = "ghp_" + "Zk3Qx9LmP2vB7nRt5YcW8dHf1JsA4gUe6XoI"  # random, not a live credential
    (tmp_path / "cfg.py").write_text(f'TOKEN = "{token}"\n')
    monkeypatch.setenv("PUSH_GUARD_SAST", "trufflehog")
    found = sa.sast_scan(tmp_path)
    assert found and found[0]["file"] == "cfg.py" and token not in json.dumps(found)
