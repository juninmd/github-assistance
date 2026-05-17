"""
Agents module for automated development workflows.
"""
from .base_agent import BaseAgent
from .ci_health.agent import CIHealthAgent
from .code_reviewer.agent import CodeReviewerAgent
from .conflict_resolver.agent import ConflictResolverAgent
from .interface_developer.agent import InterfaceDeveloperAgent
from .jules_tracker.agent import JulesTrackerAgent
from .pr_assistant.agent import PRAssistantAgent
from .pr_sla.agent import PRSLAAgent
from .product_manager.agent import ProductManagerAgent
from .project_creator.agent import ProjectCreatorAgent
from .secret_remover.agent import SecretRemoverAgent
from .security_scanner.agent import SecurityScannerAgent
from .senior_developer.agent import SeniorDeveloperAgent

__all__ = [
    "BaseAgent",
    "ProductManagerAgent",
    "InterfaceDeveloperAgent",
    "SeniorDeveloperAgent",
    "PRAssistantAgent",
    "SecurityScannerAgent",
    "CIHealthAgent",
    "PRSLAAgent",
    "ProjectCreatorAgent",
    "ConflictResolverAgent",
    "CodeReviewerAgent",
    "JulesTrackerAgent",
    "SecretRemoverAgent"
]
