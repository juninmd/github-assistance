from src.agents.pr_assistant.conflict_hunks import resolve_by_hunks

FILE = (
    "".join(f"line{i}\n" for i in range(40))
    + "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> br\n"
    + "".join(f"mid{i}\n" for i in range(40))
    + "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> br\n"
    + "tail\n"
)


def _take_theirs(snippet, hunk):
    return snippet.replace(hunk, hunk.split("=======\n")[1].split(">>>>>>>")[0])


def test_resolves_each_hunk_and_sends_less_than_whole_file():
    sent = []

    def resolver(snippet, hunk):
        sent.append(len(snippet))
        return _take_theirs(snippet, hunk)

    out = resolve_by_hunks(FILE, resolver, context_lines=3)
    assert "<<<<<<<" not in out and "theirs\n" in out and "b\n" in out and "ours" not in out
    assert out.count("line0\n") == 1 and out.endswith("tail\n")
    assert len(sent) == 2 and max(sent) < len(FILE) / 4


def test_context_rewrite_is_rejected():
    assert resolve_by_hunks(FILE, lambda s, h: _take_theirs(s, h).replace("line39", "HACK"), 3) is None


def test_surviving_markers_rejected():
    assert resolve_by_hunks(FILE, lambda s, h: s, 3) is None


def test_empty_answer_and_malformed_input():
    assert resolve_by_hunks(FILE, lambda s, h: "", 3) is None
    assert resolve_by_hunks("no conflicts\n", lambda s, h: s) is None
    assert resolve_by_hunks("<<<<<<< a\nx\n", lambda s, h: s) is None


def test_adjacent_hunks_do_not_overlap():
    adj = "a\n<<<<<<< H\n1\n=======\n2\n>>>>>>> b\n<<<<<<< H\n3\n=======\n4\n>>>>>>> b\nz\n"
    out = resolve_by_hunks(adj, _take_theirs, context_lines=5)
    assert out == "a\n2\n4\nz\n"


def test_large_file_uses_hunk_mode(monkeypatch):
    from src.agents.pr_assistant import conflict_resolver as cr

    monkeypatch.setenv("CONFLICT_HUNK_THRESHOLD", "100")
    seen = []

    class Client:
        def resolve_conflict(self, file_content, conflict_block):
            seen.append(len(file_content))
            return _take_theirs(file_content, conflict_block)

    resolved, label = cr._resolve_file_conflicts_with_model(FILE, Client(), "p", "m")
    assert resolved and "<<<<<<<" not in resolved and label == "p/m"
    assert len(seen) == 2 and max(seen) < len(FILE)
