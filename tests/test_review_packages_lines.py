import json

from src.agents.pr_assistant import review_flow
from src.agents.pr_assistant import review_lines as rl
from src.agents.pr_assistant import review_packages as pkg
from src.agents.pr_assistant import review_verdict as rv
from src.agents.pr_assistant import review_workspace as ws

DIFF = (
    "diff --git a/a/x.py b/a/x.py\n--- a/a/x.py\n+++ b/a/x.py\n@@ -1,2 +1,3 @@\n"
    " one\n+two\n three\n"
    "diff --git a/b/y.py b/b/y.py\n--- a/b/y.py\n+++ b/b/y.py\n@@ -5 +5 @@\n-old\n+new\n"
)


def test_parse_diff_visible_lines():
    vis = rl.parse_diff(DIFF)
    assert vis["a/x.py"] == {1, 2, 3}
    assert vis["b/y.py"] == {5}


def test_validate_findings_strips_bad_lines_and_dedupes():
    vis = rl.parse_diff(DIFF)
    fs = [
        rv.Finding("a/x.py", 2, "warn", "Bug aqui"),
        rv.Finding("a/x.py", 2, "warn", "bug  aqui"),
        rv.Finding("a/x.py", 99, "error", "fora"),
        rv.Finding("a/x.py", 1, "nit", " "),
    ]
    out = rl.validate_findings(fs, vis)
    assert [(f.line, f.issue) for f in out] == [(2, "Bug aqui"), (0, "fora")]
    assert [c["line"] for c in rl.inline_comments(out, vis)] == [2]


def test_packages_group_and_cap_budget():
    sections = pkg.split_by_file(DIFF)
    assert set(sections) == {"a/x.py", "b/y.py"}
    assert len(pkg.build_packages(sections, 10_000)) == 1
    assert len(pkg.build_packages(sections, 50)) == 2


def test_rules_glob(tmp_path):
    (tmp_path / ".review").mkdir()
    (tmp_path / ".review/rules.json").write_text(json.dumps({"rules": [{"path": "a/*.py", "rule": "sem print"}]}))
    rules = pkg.load_rules(str(tmp_path))
    assert "sem print" in pkg.rules_text(rules, ["a/x.py"])
    assert pkg.rules_text(rules, ["b/y.py"]) == ""
    assert pkg.load_rules(str(tmp_path / "nada")) == []


def test_merge_verdicts_any_block_wins():
    a = rv.ReviewVerdict(rv.APPROVE, "ok", [rv.Finding("f", 1, "nit", "x")], model="m")
    b = rv.ReviewVerdict(rv.REQUEST_CHANGES, "ruim", [rv.Finding("g", 2, "error", "y")], model="m")
    m = pkg.merge_verdicts([a, b])
    assert m.verdict == rv.REQUEST_CHANGES and len(m.findings) == 2


def test_review_with_models_reviews_each_package(monkeypatch):
    class PR:
        title = "t"
        base = type("B", (), {"ref": "main"})()
    monkeypatch.setattr(ws, "local_diff", lambda d, b, m: DIFF)
    monkeypatch.setattr(ws, "reset_trace", lambda: None)
    monkeypatch.setattr(ws, "last_trace", lambda: None)
    monkeypatch.setattr(pkg, "build_packages", lambda s, b: [{k: v} for k, v in s.items()])
    prompts = []
    def fake(d, prompt, model, t):
        prompts.append(prompt)
        return '{"verdict":"APPROVE","summary":"ok","findings":[]}'
    monkeypatch.setattr(ws, "run_opencode", fake)
    v = review_flow._review_with_models("/x", PR(), ["m"])
    assert v and len(prompts) == 2
