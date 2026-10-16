"""Tests for the README quality rubric."""

from src.agents.readme_curator.scoring import DEFAULT_MIN_SCORE, score_readme

_GOOD = (
    "# Project\n\n"
    "Uma descrição suficientemente longa para passar no critério de descrição da rubrica, "
    "explicando o que o projeto faz, para quem é e por que existe. Mais de 120 caracteres.\n\n"
    "[![CI](https://img.shields.io/badge/ci-passing-brightgreen.svg)](https://example.com)\n\n"
    "## Features\n\n- um\n\n"
    "## Installation\n\n```bash\npip install x\n```\n\n"
    "## Usage\n\n```bash\nx run\n```\n\n"
    "## Configuration\n\n| Var |\n|---|\n| `A` |\n\n"
    "## Diagram\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n"
    "## Contributing\n\nVeja o guia.\n\n"
    "## License\n\nMIT\n"
)


def test_good_readme_scores_high_and_needs_no_work():
    score = score_readme(_GOOD)
    assert score.score >= DEFAULT_MIN_SCORE
    assert score.missing == []
    assert score.needs_work(DEFAULT_MIN_SCORE) is False


def test_empty_readme_scores_zero():
    score = score_readme("   ")
    assert score.score == 0
    assert "title" in score.missing
    assert score.needs_work(DEFAULT_MIN_SCORE) is True


def test_missing_elements_are_reported():
    score = score_readme("# Title\n\n## Usage\n\nrun it\n")
    assert "installation" in score.missing
    assert "badges" in score.missing
    assert "license" in score.missing


def test_badges_and_diagram_are_detected():
    score = score_readme("# T\n\n" + "x" * 130 + "\n\n![b](https://img.shields.io/x)\n```mermaid\na-->b\n```\n")
    assert "badges" not in score.missing
    assert "visual (diagram/screenshot)" not in score.missing


def test_custom_threshold():
    score = score_readme("# T\n\n## Usage\n\nrun\n")
    assert score.needs_work(10) is False
    assert score.needs_work(90) is True
