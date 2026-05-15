"""
Task creator for Senior Developer Agent.
"""
from typing import Any


class SeniorDeveloperTaskCreator:
    """Handles opencode execution for various analysis results."""

    def __init__(self, agent: Any):
        self.agent = agent

    def create_tech_debt_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-tech-debt.md",
            variables={"repository": repository, "details": analysis.get("details", "General code quality improvements.")}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"Tech Debt Cleanup for {repository}")

    def create_modernization_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-modernization.md",
            variables={"repository": repository, "details": analysis.get("details", "Migrate legacy patterns to modern standards.")}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"Modernization for {repository}")

    def create_performance_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-performance.md",
            variables={"repository": repository, "details": analysis.get("details", "Identify and fix performance bottlenecks.")}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"Performance Tuning for {repository}")

    def create_security_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        issues_text = "\n".join([f"- {issue}" for issue in analysis.get("issues", [])])
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-security.md",
            variables={"repository": repository, "issues": issues_text}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"Security Hardening for {repository}")

    def create_cicd_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        improvements_text = "\n".join([f"- {imp}" for imp in analysis.get("improvements", [])])
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-cicd.md",
            variables={"repository": repository, "improvements": improvements_text}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"CI/CD Pipeline for {repository}")

    def create_feature_implementation_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        features_text = "\n".join([f"- {f.get('title')} (#{f.get('number')})" for f in analysis.get("features", [])])
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-features.md",
            variables={"repository": repository, "features": features_text}
        )
        return self.agent.run_opencode_on_repo(repository, instructions, f"Feature Implementation for {repository}")

    def create_audit_remediation_task(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any]:
        findings_text = "\n".join([f"- {f}" for f in analysis.get("findings", [])])
        instructions = self.agent.load_jules_instructions(
            template_name="jules-instructions-audit.md",
            variables={
                "repository": repository,
                "findings": findings_text,
                "criticality": analysis.get("criticality", "medium")
            }
        )
        return self.agent.run_opencode_on_repo(
            repository, instructions,
            f"Audit Remediation for {repository} ({analysis.get('criticality', 'medium')})"
        )
