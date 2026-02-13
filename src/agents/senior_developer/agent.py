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
        super().__init__(*args, name="senior_developer", **kwargs)

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
            "tech_debt_tasks": [],
            "modernization_tasks": [],
            "performance_tasks": [],
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

                # Tech Debt Analysis
                tech_debt_analysis = self.analyze_tech_debt(repo)
                if tech_debt_analysis.get("needs_attention"):
                    task = self.create_tech_debt_task(repo, tech_debt_analysis)
                    results["tech_debt_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id")
                    })

                # Modernization Analysis
                modernization_analysis = self.analyze_modernization(repo)
                if modernization_analysis.get("needs_modernization"):
                    task = self.create_modernization_task(repo, modernization_analysis)
                    results["modernization_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id")
                    })

                # Performance Analysis
                performance_analysis = self.analyze_performance(repo)
                if performance_analysis.get("needs_optimization"):
                    task = self.create_performance_task(repo, performance_analysis)
                    results["performance_tasks"].append({
                        "repository": repo,
                        "task_id": task.get("task_id")
                    })

            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({
                    "repository": repo,
                    "error": str(e)
                })

        self.log(f"Completed: {len(results['feature_tasks'])} features, "
                f"{len(results['security_tasks'])} security, "
                f"{len(results['cicd_tasks'])} CI/CD, "
                f"{len(results['tech_debt_tasks'])} tech debt, "
                f"{len(results['modernization_tasks'])} modernization, "
                f"{len(results['performance_tasks'])} performance tasks.")
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

    def analyze_tech_debt(self, repository: str) -> Dict[str, Any]:
        """Analyze repository for technical debt."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        debt_items = []
        try:
            # Simple heuristic: look for large files or lack of tests/docs
            tree = repo_info.get_git_tree("main", recursive=True)
            for item in tree.tree:
                if item.path.endswith(('.py', '.js', '.ts', '.go')):
                    # Use size as a proxy for complexity (e.g., > 20KB is roughly 500-1000 LOC)
                    if item.size and item.size > 20480:
                        debt_items.append(f"Large file detected: `{item.path}` (potential high complexity)")
            
            # Check for generic 'utils' files which often become debt magnets
            utils_files = [i.path for i in tree.tree if 'utils' in i.path.lower()]
            if len(utils_files) > 5:
                debt_items.append(f"High number of utility files ({len(utils_files)}) - consider architectural refactoring")

        except Exception as e:
            self.log(f"Error in tech debt analysis for {repository}: {e}", "WARNING")

        return {
            "needs_attention": len(debt_items) > 0,
            "details": "\n".join([f"- {item}" for item in debt_items[:10]])
        }

    def analyze_modernization(self, repository: str) -> Dict[str, Any]:
        """Analyze repository for modernization opportunities."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"needs_modernization": False}

        modernization_needs = []
        try:
            tree = repo_info.get_git_tree("main", recursive=True)
            has_ts = any(i.path.endswith('.ts') for i in tree.tree)
            js_files = [i.path for i in tree.tree if i.path.endswith('.js')]
            
            if js_files and has_ts:
                modernization_needs.append("Mixed JS/TS codebase - complete TypeScript migration")
            elif js_files and not has_ts:
                modernization_needs.append("Legacy JavaScript codebase - consider TypeScript migration")

            # Check for legacy patterns if we can sample some content
            if js_files:
                sample_js = repo_info.get_contents(js_files[0])
                content = sample_js.decoded_content.decode('utf-8')
                if 'require(' in content or 'module.exports' in content:
                    modernization_needs.append("CommonJS detected - migrate to ES Modules")
                if '.then(' in content:
                    modernization_needs.append("Legacy Promise chains detected - refactor to async/await")

        except Exception as e:
            self.log(f"Error in modernization analysis for {repository}: {e}", "WARNING")

        return {
            "needs_modernization": len(modernization_needs) > 0,
            "details": "\n".join([f"- {need}" for need in modernization_needs])
        }

    def analyze_performance(self, repository: str) -> Dict[str, Any]:
        """Analyze repository for performance optimization opportunities."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {"needs_optimization": False}

        obs = []
        try:
            # Check for potentially heavy dependencies in package.json or requirements.txt
            try:
                pkg = repo_info.get_contents("package.json")
                if 'lodash' in pkg.decoded_content.decode('utf-8'):
                    obs.append("Using heavy utility library (lodash) - consider tree-shaking or native alternatives")
            except: pass

            # General large project observation
            tree = repo_info.get_git_tree("main", recursive=True)
            if len(tree.tree) > 200:
                obs.append("Large codebase - perform general performance audit and look for bottleneck hotspots")

        except Exception as e:
            self.log(f"Error in performance analysis for {repository}: {e}", "WARNING")

        return {
            "needs_optimization": len(obs) > 0,
            "details": "\n".join([f"- {o}" for o in obs])
        }

    def create_tech_debt_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for tech debt reduction."""
        instructions = self.load_jules_instructions(
            template_name="jules-instructions-tech-debt.md",
            variables={
                "repository": repository,
                "details": analysis.get("details", "General code quality improvements.")
            }
        )
        return self.create_jules_task(repository=repository, instructions=instructions, title=f"Tech Debt Cleanup for {repository}")

    def create_modernization_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for code modernization."""
        instructions = self.load_jules_instructions(
            template_name="jules-instructions-modernization.md",
            variables={
                "repository": repository,
                "details": analysis.get("details", "Migrate legacy patterns to modern standards.")
            }
        )
        return self.create_jules_task(repository=repository, instructions=instructions, title=f"Modernization for {repository}")

    def create_performance_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jules task for performance optimization."""
        instructions = self.load_jules_instructions(
            template_name="jules-instructions-performance.md",
            variables={
                "repository": repository,
                "details": analysis.get("details", "Identify and fix performance bottlenecks.")
            }
        )
        return self.create_jules_task(repository=repository, instructions=instructions, title=f"Performance Tuning for {repository}")

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
