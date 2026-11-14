import subprocess

from src.agents.pr_assistant import build_check as bc


def _git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)  # noqa: S603, S607


def _py_project(path, test_body):
    _git_repo(path)
    (path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    (path / "tests").mkdir()
    (path / "tests" / "test_a.py").write_text(test_body)


def test_off_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("PR_FIX_VALIDATE", "off")
    assert bc.run_project_checks(str(tmp_path)) == (True, "build gate off")


def test_no_check_is_skipped(tmp_path):
    _git_repo(tmp_path)
    ok, msg = bc.run_project_checks(str(tmp_path))
    assert ok and "skipped" in msg


def test_failing_tests_reject_fix(tmp_path):
    _py_project(tmp_path, "def test_x():\n    assert 1 == 2\n")
    ok, msg = bc.run_project_checks(str(tmp_path))
    assert not ok and msg.startswith("pytest failed")


def test_passing_tests_accept_fix(tmp_path):
    _py_project(tmp_path, "def test_x():\n    assert True\n")
    ok, msg = bc.run_project_checks(str(tmp_path))
    assert ok and "passed: pytest" in msg


def test_missing_dependency_is_env_skip_not_failure(tmp_path):
    _py_project(tmp_path, "import not_installed_pkg_xyz\n\ndef test_x():\n    pass\n")
    ok, msg = bc.run_project_checks(str(tmp_path))
    assert ok and "skipped" in msg and "env" in msg


def test_artifacts_created_by_checks_are_removed(tmp_path):
    _py_project(tmp_path, "from pathlib import Path\n\ndef test_x():\n    Path('out.bin').write_text('1')\n")
    ok, _ = bc.run_project_checks(str(tmp_path))
    assert ok and not (tmp_path / "out.bin").exists()


def test_timeout_never_blocks(monkeypatch, tmp_path):
    _py_project(tmp_path, "def test_x():\n    pass\n")

    def boom(*a, **k):
        if a[0][0] == "git":
            return subprocess.CompletedProcess(a[0], 0, "", "")
        raise subprocess.TimeoutExpired(a[0], 1)

    monkeypatch.setattr(bc, "proc_run", boom)
    ok, msg = bc.run_project_checks(str(tmp_path))
    assert ok and "TimeoutExpired" in msg


def test_detect_go_and_cargo(monkeypatch, tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    monkeypatch.setattr(bc.shutil, "which", lambda n: "/bin/" + n)
    labels = [label for label, _ in bc.detect_commands(str(tmp_path))]
    assert labels == ["go build", "cargo check"]
