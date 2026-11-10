"""The agent catalog is the single source of truth: nothing may drift from it."""

import tomllib
from dataclasses import fields, replace
from importlib import import_module
from pathlib import Path

import pytest

from src import scripts
from src.agents.core.batch_runner import _ALWAYS_ENABLED, _ENABLED_ATTRS
from src.agents.core.catalog import AGENT_CATALOG, AGENTS_BY_NAME, AgentPriority, agent_names
from src.agents.core.fleet import fleet_status
from src.agents.core.orchestration import create_default_orchestrator
from src.agents.core.registry import AGENT_REGISTRY, AGENTS_WITH_AI, AGENTS_WITH_PR_REF
from src.config.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_names_are_unique_and_kebab_case():
    names = [spec.name for spec in AGENT_CATALOG]
    assert len(names) == len(set(names)) == len(AGENTS_BY_NAME)
    assert all(name == name.lower() and "_" not in name for name in names)


@pytest.mark.parametrize("spec", AGENT_CATALOG, ids=lambda spec: spec.name)
def test_every_spec_resolves_to_a_real_agent_package(spec):
    module_name, class_name = spec.import_path.split(":")
    assert hasattr(import_module(module_name), class_name)
    assert AGENT_REGISTRY[spec.name].__name__ == class_name
    assert (ROOT / "src" / "agents" / spec.package / "__init__.py").is_file()
    assert set(spec.depends_on) <= set(AGENTS_BY_NAME)


def test_toggles_exist_in_settings_and_env_example():
    setting_fields = {field.name for field in fields(Settings)}
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for spec in AGENT_CATALOG:
        if spec.toggle_env:
            assert spec.toggle_attr in setting_fields, spec.name
            assert f"{spec.toggle_env}=" in env_example, spec.name
        else:
            assert spec.toggle_attr is None


def test_settings_reads_toggles_from_the_catalog(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("PR_SLA_ENABLED", "false")
    monkeypatch.setenv("README_CURATOR_ENABLED", "off")
    settings = Settings.from_env()
    assert settings.enable_pr_sla is False and settings.enable_readme_curator is False
    assert settings.enable_pr_assistant is True


def test_console_scripts_cover_every_agent():
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    for spec in AGENT_CATALOG:
        assert declared[spec.name] == f"src.scripts:{spec.package}"
        assert callable(getattr(scripts, spec.package))
    assert "pr_assistant" in dir(scripts)
    with pytest.raises(AttributeError):
        _ = scripts.not_an_agent


def test_derived_tables_match_the_catalog():
    assert agent_names(requires_ai=True) == AGENTS_WITH_AI
    assert AGENTS_WITH_PR_REF == {"pr-assistant", "code-reviewer", "conflict-resolver"}
    assert agent_names(requires_ai=True, uses_jules=False) == {
        "secret-remover", "code-reviewer", "readme-curator",
    }
    assert set(_ENABLED_ATTRS) | set(_ALWAYS_ENABLED) == {s.name for s in AGENT_CATALOG if s.in_batch}
    assert _ALWAYS_ENABLED == ["conflict-resolver"] and "jules-cleaner" not in _ENABLED_ATTRS


def test_default_orchestrator_registers_the_whole_catalog():
    orchestrator = create_default_orchestrator()
    assert set(orchestrator.priorities) == set(AGENTS_BY_NAME)
    assert orchestrator.priorities["pr-sla"] is AgentPriority.LOW
    assert orchestrator.dependencies["secret-remover"].depends_on == ["security-scanner"]


def test_fleet_status_explains_why_an_agent_cannot_run():
    settings = Settings(github_token="x", jules_api_key="k", enable_ai=True, enable_pr_sla=False)
    by_name = {agent["name"]: agent for agent in fleet_status(settings)["agents"]}
    assert by_name["pr-assistant"]["runnable"] is True
    assert by_name["pr-sla"]["blocked_reason"] == "PR_SLA_ENABLED=false"
    assert by_name["secret-remover"]["depends_on"] == ["security-scanner"]

    offline = fleet_status(replace(settings, enable_ai=False, jules_api_key=None))
    reasons = {agent["name"]: agent["blocked_reason"] for agent in offline["agents"]}
    assert reasons["code-reviewer"] == "ENABLE_AI=false"
    assert reasons["jules-tracker"] == "JULES_API_KEY ausente"
    assert offline["ai"] == {"enabled": False, "provider": "litellm", "model": "cloud/auto"}
