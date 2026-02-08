"""
Senior Developer Agent - Expert in security, architecture, and CI/CD.
"""
from typing import Dict, Any
from src.agents.base_agent import BaseAgent
from datetime import datetime


class SeniorDeveloperAgent(BaseAgent):
    """
    Senior Developer Agent

    Reads instructions from instructions.md file.
    """

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, name="SeniorDeveloper", **kwargs)

    def run(self) -> Dict[str, Any]:
        """
        Execute the Senior Developer workflow:
        1. Read roadmaps to identify features to implement
        2. Check for security issues and missing CI/CD
        3. Create tasks for feature implementation
        4. Ensure infrastructure and deployment are solid

        Returns:
            Summary of development tasks created
        """
        self.log("Starting Senior Developer workflow")

        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = {
            "feature_tasks": [],
            "security_tasks": [],
            "cicd_tasks": [],
            "failed": [],
            "timestamp": datetime.now().isoformat()
        }

        for repo in repositories:
            try:
                self.log(f"Analyzing development needs for: {repo}")

                # Check for security issues
                security_analysis = self.analyze_security(repo)
                if security_analysis.get("needs_attention"):
                    task = self.create_security_task(repo, security_analysis)
                    results["security_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id")
                    })

                # Check CI/CD setup
                cicd_analysis = self.analyze_cicd(repo)
                if cicd_analysis.get("needs_improvement"):
                    task = self.create_cicd_task(repo, cicd_analysis)
                    results["cicd_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id")
                    })

                # Check for roadmap features to implement
                feature_analysis = self.analyze_roadmap_features(repo)
                if feature_analysis.get("has_features"):
                    task = self.create_feature_implementation_task(repo, feature_analysis)
                    results["feature_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id"),
                        "features_count": len(feature_analysis.get("features", []))
                    })

            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({
                    "repository": repo,
                    "error": str(e)
                })

        self.log(f"Completed: {len(results['feature_tasks'])} feature tasks, "
                f"{len(results['security_tasks'])} security tasks, "
                f"{len(results['cicd_tasks'])} CI/CD tasks")
        return results

    def analyze_security(self, repository: str) -> Dict[str, Any]:
        """
        Analyze repository for security issues.

        Args:
            repository: Repository identifier

        Returns:
            Security analysis results
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        issues = []

        # Check for .gitignore
        try:
            gitignore = repo_info.get_contents(".gitignore")
            # Basic check - should be more thorough
            content = gitignore.decoded_content.decode('utf-8')
            if '.env' not in content:
                issues.append("Missing .env in .gitignore")
            if 'secrets' not in content.lower():
                issues.append("Consider adding common secret patterns to .gitignore")
        except:
            issues.append("Missing .gitignore file")

        # Check for dependabot or renovate
        try:
            repo_info.get_contents(".github/dependabot.yml")
        except:
            try:
                repo_info.get_contents("renovate.json")
            except:
                issues.append("No automated dependency updates (Dependabot/Renovate)")

        return {
            "needs_attention": len(issues) > 0,
            "issues": issues
        }

    def analyze_cicd(self, repository: str) -> Dict[str, Any]:
        """
        Analyze CI/CD setup.

        Args:
            repository: Repository identifier

        Returns:
            CI/CD analysis results
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"needs_improvement": False}

        improvements = []

        # Check for GitHub Actions
        try:
            workflows = repo_info.get_contents(".github/workflows")
            if not workflows:
                improvements.append("No GitHub Actions workflows found")
        except:
            improvements.append("Set up GitHub Actions for CI/CD")

        # Check for tests
        try:
            # Look for test directories
            contents = repo_info.get_contents("")
            has_tests = any('test' in item.name.lower() for item in contents)
            if not has_tests:
                improvements.append("No test directory found - add comprehensive tests")
        except:
            pass

        return {
            "needs_improvement": len(improvements) > 0,
            "improvements": improvements
        }

    def analyze_roadmap_features(self, repository: str) -> Dict[str, Any]:
        """
        Analyze roadmap for features to implement.

        Args:
            repository: Repository identifier

        Returns:
            Feature analysis results
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"has_features": False}

        # Check for ROADMAP.md
        try:
            roadmap = repo_info.get_contents("ROADMAP.md")
            # In a real scenario, parse the roadmap to extract prioritized features
            # For now, check for open issues labeled as features
            issues = list(repo_info.get_issues(state='open'))[:20]
            feature_issues = [
                i for i in issues
                if any(label.name.lower() in ['feature', 'enhancement'] for label in i.labels)
            ]

            return {
                "has_features": len(feature_issues) > 0,
                "features": [{"title": i.title, "number": i.number} for i in feature_issues[:5]]
            }
        except:
            return {"has_features": False, "features": []}

    def create_security_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for security improvements."""
        issues_text = "\n".join([f"- {issue}" for issue in analysis.get("issues", [])])

        instructions = self.load_jules_instructions(
            template_name="jules-instructions-security.md",
            variables={
                "repository": repository,
                "issues": issues_text
            }
        )

        return self.create_jules_task(
            repository=repository,
            instructions=instructions,
            title=f"Security Hardening for {repository}"
        )

    def create_cicd_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for CI/CD setup."""
        improvements_text = "\n".join([f"- {imp}" for imp in analysis.get("improvements", [])])

        instructions = self.load_jules_instructions(
            template_name="jules-instructions-cicd.md",
            variables={
                "repository": repository,
                "improvements": improvements_text
            }
        )

        return self.create_jules_task(
            repository=repository,
            instructions=instructions,
            title=f"CI/CD Pipeline for {repository}"
        )

    def create_feature_implementation_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for feature implementation."""
        features_text = "\n".join([
            f"- {f.get('title')} (#{f.get('number')})"
            for f in analysis.get("features", [])
        ])

        instructions = self.load_jules_instructions(
            template_name="jules-instructions-features.md",
            variables={
                "repository": repository,
                "features": features_text
            }
        )

        return self.create_jules_task(
            repository=repository,
            instructions=instructions,
            title=f"Feature Implementation for {repository}"
        )
