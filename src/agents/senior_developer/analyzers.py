"""
Analyzers for Senior Developer Agent.
"""
from typing import Any
from github.GithubException import UnknownObjectException, GithubException

class SeniorDeveloperAnalyzer:
    """Handles repository analysis for security, CI/CD, roadmap, tech debt, and more."""

    def __init__(self, agent: Any):
        self.agent = agent

    def analyze_security(self, repository: str) -> dict[str, Any]:
        """Analyze repository for security issues."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        issues = []
        try:
            gitignore = repo_info.get_contents(".gitignore")
            content = gitignore.decoded_content.decode('utf-8')
            if '.env' not in content:
                issues.append("Missing .env in .gitignore")
            if 'secrets' not in content.lower():
                issues.append("Consider adding common secret patterns to .gitignore")
        except Exception:
            issues.append("Missing .gitignore file")

        try:
            repo_info.get_contents(".github/dependabot.yml")
        except (UnknownObjectException, GithubException) as e:
            try:
                repo_info.get_contents("renovate.json")
            except (UnknownObjectException, GithubException):
                issues.append("No automated dependency updates (Dependabot/Renovate)")
        except Exception as e:
            self.agent.log(f"Unexpected error checking dependency updates for {repository}: {e}", "WARNING")

        return {"needs_attention": len(issues) > 0, "issues": issues}

    def analyze_cicd(self, repository: str) -> dict[str, Any]:
        """Analyze CI/CD setup."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"needs_improvement": False}

        improvements = []
        try:
            workflows = repo_info.get_contents(".github/workflows")
            if not workflows:
                improvements.append("No GitHub Actions workflows found")
        except Exception:
            improvements.append("Set up GitHub Actions for CI/CD")

        try:
            contents = repo_info.get_contents("")
            has_tests = any('test' in item.name.lower() for item in contents)
            if not has_tests:
                improvements.append("No test directory found - add comprehensive tests")
        except (UnknownObjectException, GithubException):
            improvements.append("Empty repository or no files found - add project structure and tests")
        except Exception as e:
            self.agent.log(f"Unexpected error checking tests for {repository}: {e}", "WARNING")

        return {"needs_improvement": len(improvements) > 0, "improvements": improvements}

    def analyze_roadmap_features(self, repository: str) -> dict[str, Any]:
        """Analyze roadmap for features to implement."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"has_features": False}

        try:
            repo_info.get_contents("ROADMAP.md")
            issues = list(repo_info.get_issues(state='open'))[:20]
            feature_issues = [
                i for i in issues
                if any(label.name.lower() in ['feature', 'enhancement'] for label in i.labels)
            ]
            return {
                "has_features": len(feature_issues) > 0,
                "features": [{"title": i.title, "number": i.number} for i in feature_issues[:5]]
            }
        except (UnknownObjectException, GithubException):
            return {"has_features": False, "features": []}
        except Exception as e:
            self.agent.log(f"Unexpected error checking roadmap for {repository}: {e}", "WARNING")
            return {"has_features": False, "features": []}

    def analyze_tech_debt(self, repository: str) -> dict[str, Any]:
        """Analyze repository for technical debt."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        debt_items = []
        try:
            if not repo_info.default_branch:
                return {"needs_attention": False}
            tree = repo_info.get_git_tree(repo_info.default_branch, recursive=True)
            for item in tree.tree:
                if item.path.endswith(('.py', '.js', '.ts', '.go')):
                    if item.size and item.size > 20480:
                        debt_items.append(f"Large file detected: `{item.path}` (potential high complexity)")
            utils_files = [i.path for i in tree.tree if 'utils' in i.path.lower()]
            if len(utils_files) > 5:
                debt_items.append(f"High number of utility files ({len(utils_files)})")
        except (UnknownObjectException, GithubException):
            pass
        except Exception as e:
            self.agent.log(f"Error in tech debt analysis for {repository}: {e}", "WARNING")

        return {"needs_attention": len(debt_items) > 0, "details": "\n".join([f"- {i}" for i in debt_items[:10]])}

    def analyze_modernization(self, repository: str) -> dict[str, Any]:
        """Analyze repository for modernization opportunities."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"needs_modernization": False}

        modernization_needs = []
        try:
            if not repo_info.default_branch:
                return {"needs_modernization": False}
            tree = repo_info.get_git_tree(repo_info.default_branch, recursive=True)
            has_ts = any(i.path.endswith('.ts') for i in tree.tree)
            js_files = [i.path for i in tree.tree if i.path.endswith('.js')]
            if js_files and has_ts:
                modernization_needs.append("Mixed JS/TS codebase - complete TypeScript migration")
            elif js_files and not has_ts:
                modernization_needs.append("Legacy JavaScript codebase - consider TypeScript migration")

            if js_files:
                sample_js = repo_info.get_contents(js_files[0])
                content = sample_js.decoded_content.decode('utf-8')
                if 'require(' in content or 'module.exports' in content:
                    modernization_needs.append("CommonJS detected - migrate to ES Modules")
                if '.then(' in content:
                    modernization_needs.append("Legacy Promise chains detected - refactor to async/await")
        except (UnknownObjectException, GithubException):
            pass
        except Exception as e:
            self.agent.log(f"Error in modernization analysis for {repository}: {e}", "WARNING")

        return {"needs_modernization": len(modernization_needs) > 0, "details": "\n".join([f"- {n}" for n in modernization_needs])}

    def analyze_performance(self, repository: str) -> dict[str, Any]:
        """Analyze repository for performance optimization opportunities."""
        repo_info = self.agent.get_repository_info(repository)
        if not repo_info:
            return {"needs_optimization": False}

        obs = []
        try:
            try:
                pkg = repo_info.get_contents("package.json")
                if 'lodash' in pkg.decoded_content.decode('utf-8'):
                    obs.append("Using heavy utility library (lodash)")
            except (UnknownObjectException, GithubException):
                pass
            
            if repo_info.default_branch:
                tree = repo_info.get_git_tree(repo_info.default_branch, recursive=True)
                if len(tree.tree) > 200:
                    obs.append("Large codebase - perform general performance audit")
        except (UnknownObjectException, GithubException):
            pass
        except Exception as e:
            self.agent.log(f"Error in performance analysis for {repository}: {e}", "WARNING")

        return {"needs_optimization": len(obs) > 0, "details": "\n".join([f"- {o}" for o in obs])}
