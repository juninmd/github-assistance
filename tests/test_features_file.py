import pytest

from src.config.features_file import apply_features_file, load_features_file


def test_missing_file_is_noop(tmp_path):
    assert load_features_file(str(tmp_path / "x.toml")) == {}


def test_env_wins_and_secrets_ignored(tmp_path, monkeypatch):
    f = tmp_path / "f.toml"
    f.write_text('[env]\nFT_A = true\nFT_B = 5\nFT_API_KEY = "x"\n')
    monkeypatch.setenv("FT_B", "9")
    monkeypatch.delenv("FT_A", raising=False)
    monkeypatch.delenv("FT_API_KEY", raising=False)
    applied = apply_features_file(str(f))
    import os
    assert applied == ["FT_A"] and os.environ["FT_A"] == "true"
    assert os.environ["FT_B"] == "9" and "FT_API_KEY" not in os.environ
    monkeypatch.delenv("FT_A")


def test_invalid_file_raises(tmp_path):
    f = tmp_path / "f.toml"
    f.write_text("[env\n")
    with pytest.raises(ValueError):
        load_features_file(str(f))
