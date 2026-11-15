import json

from src.agents.opencode import trace as tr
from src.agents.pr_assistant import review_flow as rf
from src.agents.pr_assistant import review_verdict as rv
from src.agents.pr_assistant import review_workspace as ws
from src.insight import cost


def _ev(kind, **part):
    return json.dumps({"type": kind, "part": part})


STDOUT = "\n".join([
    _ev("step_start"),
    _ev("tool_use", tool="skill", state={"input": {"name": "code-review"}}),
    _ev("tool_use", tool="skill", state={"input": {"name": "code-review"}}),
    _ev("tool_use", tool="read", state={"input": {"filePath": "x"}}),
    _ev("text", text='{"verdict":"APPROVE","summary":"ok"}'),
    _ev("step_finish", tokens={"input": 100, "output": 20}, cost=0.5),
])


def test_parse_events_extracts_skills_tokens_text():
    text, facts = tr.parse_events(STDOUT)
    assert text == '{"verdict":"APPROVE","summary":"ok"}'
    assert facts["skills_used"] == ("code-review",)
    assert (facts["tokens_in"], facts["tokens_out"], facts["cost"]) == (100, 20, 0.5)
    assert facts["structured"] is True


def test_parse_events_plain_output_is_unchanged_and_unstructured():
    text, facts = tr.parse_events("just text")
    assert text == "just text" and facts["structured"] is False and facts["skills_used"] == ()


def test_available_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / ".config/opencode/skills/code-review"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("x")
    (tmp_path / ".config/opencode/skills/empty").mkdir()
    assert tr.available_skills() == ("code-review",)


def test_run_opencode_records_trace_and_ledger(monkeypatch, tmp_path):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AI_USAGE_LOG", str(log))
    monkeypatch.setattr(ws, "proc_run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": STDOUT})())
    monkeypatch.setattr(ws, "harness_version", lambda cmd="": "2.3.0")
    ws.reset_trace()
    assert ws.run_opencode(str(tmp_path), "p", "m", 1).startswith('{"verdict"')
    t = ws.last_trace()
    assert t.harness == "opencode 2.3.0" and t.skills_used == ("code-review",)
    row = json.loads(log.read_text().splitlines()[0])
    assert row["harness"] == "opencode 2.3.0" and row["skills_used"] == ["code-review"]
    skills = cost.summarize_skills(str(log))
    assert skills == [{"harness": "opencode 2.3.0", "skill": "code-review", "runs": 1}]


def test_footer_shows_only_observed_skills():
    v = rv.ReviewVerdict(rv.APPROVE, "ok", model="m", harness="opencode 2.3.0",
                         skills_used=("code-review", "security-ops"), skills_checked=True)
    out = rv.build_review_comment(v)
    assert "`opencode 2.3.0`" in out and "skills usadas `code-review`, `security-ops`" in out
    none = rv.build_review_comment(rv.ReviewVerdict(rv.APPROVE, "ok", harness="opencode 2.3.0", skills_checked=True))
    assert "nenhuma skill invocada" in none
    unknown = rv.build_review_comment(rv.ReviewVerdict(rv.APPROVE, "ok"))
    assert "skills não registradas" in unknown and "`code-review`/" not in unknown


def test_review_with_models_attaches_trace(monkeypatch):
    class PR:
        title = "t"
        class base:  # noqa: N801
            ref = "main"
    monkeypatch.setattr(ws, "local_diff", lambda *a, **k: "d")
    trace = tr.RunTrace(harness="opencode 2.3.0", skills_used=("code-review",), structured=True)
    def fake(*a, **k):
        ws._last_trace = trace
        return '{"verdict":"APPROVE","summary":"ok"}'
    monkeypatch.setattr(ws, "run_opencode", fake)
    v = rf._review_with_models("/x", PR, ["m"])
    assert v.harness == "opencode 2.3.0" and v.skills_used == ("code-review",) and v.skills_checked
