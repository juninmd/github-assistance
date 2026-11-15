from src.insight.cost import record_run, summarize


def test_ledger_roundtrip(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv("AI_USAGE_LOG", str(log))
    m = {"agent_name": "a", "llm_calls": 2, "llm_cache_hits": 1,
         "llm_tokens_in_est": 100, "llm_tokens_out_est": 50, "llm_tokens_saved_est": 10}
    record_run(m)
    record_run({**m, "agent_name": "b", "llm_tokens_in_est": 1})
    record_run({"agent_name": "idle"})  # no LLM use: not logged
    rows = summarize(str(log))
    assert [r["agent"] for r in rows] == ["a", "b"] and rows[0]["tokens"] == 150


def test_disabled_and_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_USAGE_LOG", raising=False)
    record_run({"llm_calls": 1})
    assert summarize(str(tmp_path / "none")) == []
