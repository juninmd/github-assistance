"""
Agents module for automated development workflows.
"""
from .base_agent import BaseAgent
from .ci_health.agent import CIHealthAgent
from .dependency_risk.agent import DependencyRiskAgent
from .interface_developer.agent import InterfaceDeveloperAgent
from .issue_escalation.agent import IssueEscalationAgent
from .pr_assistant.agent import PRAssistantAgent
from .pr_sla.agent import PRSLAAgent
from .product_manager.agent import ProductManagerAgent
from .release_watcher.agent import ReleaseWatcherAgent
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
    "ReleaseWatcherAgent",
    "DependencyRiskAgent",
    "PRSLAAgent",
    "IssueEscalationAgent"
]
