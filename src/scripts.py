from src.config.settings import Settings
from src.run_agent import run_agent, run_all


def _run(agent_name: str) -> None:
    settings = Settings.from_env()
    if agent_name == "all":
        run_all(settings)
    else:
        run_agent(agent_name, settings)

def product_manager() -> None: _run("product-manager")
def interface_developer() -> None: _run("interface-developer")
def senior_developer() -> None: _run("senior-developer")
def pr_assistant() -> None: _run("pr-assistant")
def security_scanner() -> None: _run("security-scanner")
def ci_health() -> None: _run("ci-health")
def pr_sla() -> None: _run("pr-sla")
def jules_tracker() -> None: _run("jules-tracker")
def secret_remover() -> None: _run("secret-remover")
def project_creator() -> None: _run("project-creator")
def conflict_resolver() -> None: _run("conflict-resolver")
def code_reviewer() -> None: _run("code-reviewer")
def branch_cleaner() -> None: _run("branch-cleaner")
def intelligence_standardizer() -> None: _run("intelligence-standardizer")
def all_agents() -> None: _run("all")
