from src.config.settings import Settings
from src.run_agent import run_agent, run_all


def _run(agent_name: str):
    settings = Settings.from_env()
    if agent_name == "all":
        run_all(settings)
    else:
        run_agent(agent_name, settings)

def product_manager(): _run("product-manager")
def interface_developer(): _run("interface-developer")
def senior_developer(): _run("senior-developer")
def pr_assistant(): _run("pr-assistant")
def security_scanner(): _run("security-scanner")
def ci_health(): _run("ci-health")
def pr_sla(): _run("pr-sla")
def jules_tracker(): _run("jules-tracker")
def secret_remover(): _run("secret-remover")
def project_creator(): _run("project-creator")
def conflict_resolver(): _run("conflict-resolver")
def code_reviewer(): _run("code-reviewer")
def branch_cleaner(): _run("branch-cleaner")
def intelligence_standardizer(): _run("intelligence-standardizer")
def all_agents(): _run("all")
