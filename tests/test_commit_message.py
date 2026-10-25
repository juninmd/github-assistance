from src.agents.commit_message import is_semantic, semantic_message


def test_semantic_message_format():
    msg = semantic_message("fix", "CI", "Corrige falha de pipeline.", "corpo")
    assert msg == "fix(ci): corrige falha de pipeline\n\ncorpo"
    assert is_semantic(msg)


def test_unknown_type_and_long_subject():
    msg = semantic_message("weird", "", "x" * 200)
    assert msg.startswith("chore: ") and len(msg.splitlines()[0]) <= 72


def test_is_semantic_rejects_legacy_messages():
    assert not is_semantic("fix: ")
    assert not is_semantic("Update stuff")
    assert is_semantic("feat(api)!: muda contrato")
