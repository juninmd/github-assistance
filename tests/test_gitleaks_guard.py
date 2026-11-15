import json
import subprocess

from src.utils import secret_scan as ss


def _fake_run(report, returncode):
    def run(argv, **kw):
        path = argv[argv.index("--report-path") + 1]
        if report is not None:
            open(path, "w").write(json.dumps(report))
        return subprocess.CompletedProcess(argv, returncode, "", "")

    return run


def test_disabled_and_missing_binary(monkeypatch):
    monkeypatch.setenv("PUSH_GUARD_GITLEAKS", "off")
    assert ss.gitleaks_enabled() is False
    monkeypatch.setenv("PUSH_GUARD_GITLEAKS", "auto")
    monkeypatch.setattr(ss.shutil, "which", lambda n: None)
    assert ss.gitleaks_enabled() is False
    monkeypatch.setattr(ss.shutil, "which", lambda n: "/usr/bin/gitleaks")
    assert ss.gitleaks_enabled() is True


def test_findings_are_relative_and_have_no_secret_values(monkeypatch, tmp_path):
    item = {"File": str(tmp_path / "cfg" / "a.env"), "RuleID": "aws-access-token",
            "StartLine": 3, "Secret": "REDACTED", "Match": "REDACTED"}
    monkeypatch.setattr(ss, "proc_run", _fake_run([item], 1))
    out = ss.gitleaks_scan(tmp_path)
    assert out == [{"file": "cfg/a.env", "rule_id": "gitleaks:aws-access-token", "line": 3}]


def test_tool_errors_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "proc_run", _fake_run(None, 2))
    assert ss.gitleaks_scan(tmp_path) == []

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("gitleaks", 1)

    monkeypatch.setattr(ss, "proc_run", boom)
    assert ss.gitleaks_scan(tmp_path) == []


def test_scan_clone_merges_and_dedupes(monkeypatch, tmp_path):
    # No secret-looking file on disk: other tests scan shared pytest temp dirs.
    monkeypatch.setattr(ss, "_scan_regex", lambda root, known, env: [{"file": "x.txt", "rule_id": "github-pat", "line": 1}])
    monkeypatch.setenv("PUSH_GUARD_GITLEAKS", "auto")
    monkeypatch.setattr(ss.shutil, "which", lambda n: "/usr/bin/gitleaks")
    items = [
        {"File": str(tmp_path / "x.txt"), "RuleID": "github-pat", "StartLine": 1},
        {"File": str(tmp_path / "y.txt"), "RuleID": "generic-api-key", "StartLine": 9},
    ]
    monkeypatch.setattr(ss, "proc_run", _fake_run(items, 1))
    out = ss.scan_clone(tmp_path, known=[])
    assert {(f["file"], f["line"]) for f in out} == {("x.txt", 1), ("y.txt", 9)}


def test_shared_ruleset_is_passed_to_gitleaks(monkeypatch, tmp_path):
    seen = {}

    def run(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(ss, "proc_run", run)
    ss.gitleaks_scan(tmp_path)
    assert "--config" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--config") + 1].endswith("config/gitleaks.toml")
    monkeypatch.setenv("GITLEAKS_CONFIG", str(tmp_path / "missing.toml"))
    ss.gitleaks_scan(tmp_path)
    assert "--config" not in seen["argv"]
