"""
Analyzers for Senior Developer Agent.
"""

import json
import re
from typing import Any

from github.GithubException import GithubException, UnknownObjectException

from src.agents.base_agent import BaseAgent


class SeniorDeveloperAnalyzer:
    """Handles repository analysis for security, CI/CD, roadmap, tech debt, and more."""

    def __init__(self, agent: BaseAgent):
        self.agent = agent

    def _get_repo_info(self, repository: str):
        repo_info = self.agent.get_repository_info(repository)
        return repo_info

    def analyze_security(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        issues = []
        try:
            gitignore = repo_info.get_contents(".gitignore")
            if isinstance(gitignore, list):
                gitignore = gitignore[0]
            content = gitignore.decoded_content.decode("utf-8")
            if ".env" not in content:
                issues.append("Missing .env in .gitignore")
            if "secrets" not in content.lower():
                issues.append("Consider adding common secret patterns to .gitignore")
        except Exception:
            issues.append("Missing .gitignore file")

        try:
            repo_info.get_contents(".github/dependabot.yml")
        except (UnknownObjectException, GithubException):
            try:
                repo_info.get_contents("renovate.json")
            except (UnknownObjectException, GithubException):
                issues.append("No automated dependency updates (Dependabot/Renovate)")
        except Exception as e:
            self.agent.log(
                f"Unexpected error checking dependency updates for {repository}: {e}", "WARNING"
            )

        return {"needs_attention": len(issues) > 0, "issues": issues}

    def analyze_cicd(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
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
            items = contents if isinstance(contents, list) else [contents]
            has_tests = any("test" in item.name.lower() for item in items)
            if not has_tests:
                improvements.append("No test directory found - add comprehensive tests")
        except (UnknownObjectException, GithubException):
            improvements.append(
                "Empty repository or no files found - add project structure and tests"
            )
        except Exception as e:
            self.agent.log(f"Unexpected error checking tests for {repository}: {e}", "WARNING")

        return {"needs_improvement": len(improvements) > 0, "improvements": improvements}

    def analyze_roadmap_features(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        if not repo_info:
            return {"has_features": False}

        try:
            repo_info.get_contents("ROADMAP.md")
            issues = list(repo_info.get_issues(state="open"))[:20]
            feature_issues = [
                i
                for i in issues
                if any(label.name.lower() in ["feature", "enhancement"] for label in i.labels)
            ]
            return {
                "has_features": len(feature_issues) > 0,
                "features": [{"title": i.title, "number": i.number} for i in feature_issues[:5]],
            }
        except (UnknownObjectException, GithubException):
            return {"has_features": False, "features": []}
        except Exception as e:
            self.agent.log(f"Unexpected error checking roadmap for {repository}: {e}", "WARNING")
            return {"has_features": False, "features": []}

    def analyze_tech_debt(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        if not repo_info:
            return {"needs_attention": False}

        debt_items = []
        try:
            if not repo_info.default_branch:
                return {"needs_attention": False}
            tree = repo_info.get_git_tree(repo_info.default_branch, recursive=True)
            for item in tree.tree:
                if item.path.endswith((".py", ".js", ".ts", ".go")):
                    if item.size and item.size > 20480:
                        debt_items.append(
                            f"Large file detected: `{item.path}` (potential high complexity)"
                        )
            utils_files = [i.path for i in tree.tree if "utils" in i.path.lower()]
            if len(utils_files) > 5:
                debt_items.append(f"High number of utility files ({len(utils_files)})")
        except (UnknownObjectException, GithubException):
            pass
        except Exception as e:
            self.agent.log(f"Error in tech debt analysis for {repository}: {e}", "WARNING")

        return {
            "needs_attention": len(debt_items) > 0,
            "details": "\n".join([f"- {i}" for i in debt_items[:10]]),
        }

    def analyze_modernization(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        if not repo_info:
            return {"needs_modernization": False}

        modernization_needs = []
        try:
            if not repo_info.default_branch:
                return {"needs_modernization": False}
            tree = repo_info.get_git_tree(repo_info.default_branch, recursive=True)
            has_ts = any(i.path.endswith(".ts") for i in tree.tree)
            js_files = [i.path for i in tree.tree if i.path.endswith(".js")]
            if js_files and has_ts:
                modernization_needs.append("Mixed JS/TS codebase - complete TypeScript migration")
            elif js_files and not has_ts:
                modernization_needs.append(
                    "Legacy JavaScript codebase - consider TypeScript migration"
                )

            if js_files:
                sample_js = repo_info.get_contents(js_files[0])
                if isinstance(sample_js, list):
                    sample_js = sample_js[0]
                content = sample_js.decoded_content.decode("utf-8")
                if "require(" in content or "module.exports" in content:
                    modernization_needs.append("CommonJS detected - migrate to ES Modules")
                if ".then(" in content:
                    modernization_needs.append(
                        "Legacy Promise chains detected - refactor to async/await"
                    )
        except (UnknownObjectException, GithubException):
            pass
        except Exception as e:
            self.agent.log(f"Error in modernization analysis for {repository}: {e}", "WARNING")

        return {
            "needs_modernization": len(modernization_needs) > 0,
            "details": "\n".join([f"- {n}" for n in modernization_needs]),
        }

    def analyze_performance(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        if not repo_info:
            return {"needs_optimization": False}

        obs = []
        try:
            try:
                pkg = repo_info.get_contents("package.json")
                if isinstance(pkg, list):
                    pkg = pkg[0]
                if "lodash" in pkg.decoded_content.decode("utf-8"):
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

    def ai_powered_audit(self, repository: str) -> dict[str, Any]:
        repo_info = self._get_repo_info(repository)
        ai_client = getattr(self.agent, "ai_client", None)
        if not repo_info or not ai_client:
            return {"needs_attention": False}

        critical_files = [
            ".env.example",
            "Dockerfile",
            "pyproject.toml",
            "package.json",
            "README.md",
        ]
        collected_content = []

        for file_path in critical_files:
            try:
                entry = repo_info.get_contents(file_path)
                if isinstance(entry, list):
                    entry = entry[0]
                content = entry.decoded_content.decode("utf-8")
                collected_content.append(f"--- FILE: {file_path} ---\n{content[:2000]}")
            except Exception:
                continue

        if not collected_content:
            return {"needs_attention": False}

        prompt = (
            f"You are a Senior Security & Architecture auditor analyzing the repository '{repository}'.\n"
            "Analyze these configuration files for security risks, misconfigurations, or missing best practices:\n\n"
            + "\n\n".join(collected_content)
            + "\n\nRespond with a JSON object containing:\n"
            '{"needs_attention": bool, "findings": [str], "criticality": "low|medium|high"}'
        )

        try:
            response = ai_client.generate(prompt)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                return result
        except Exception as e:
            self.agent.log(f"AI Audit failed for {repository}: {e}", "WARNING")

        return {"needs_attention": False}

    def ai_powered_feature_enhancement(self, repository: str) -> dict[str, Any]:
        """Brainstorm and suggest feature improvements using AI."""
        repo_info = self.agent.get_repository_info(repository)
        ai_client = getattr(self.agent, "ai_client", None)
        if not repo_info or not ai_client:
            return {"needs_enhancement": False}

        try:
            readme_file = cast(Any, repo_info.get_contents("README.md"))
            readme = readme_file.decoded_content.decode("utf-8")
        except Exception:
            readme = "No README.md found."

        try:
            # Get a glimpse of the project structure
            contents = cast(list[Any], repo_info.get_contents(""))
            structure = "\n".join([f"- {item.name} ({item.type})" for item in contents])
        except Exception:
            structure = "Could not retrieve structure."

        prompt = (
            f"You are a Lead Product Engineer analyzing '{repository}'.\n"
            f"README:\n{readme[:1500]}\n\n"
            f"Structure:\n{structure}\n\n"
            "Based on the project description and structure, suggest ONE concrete and impactful feature improvement or a new high-value functionality.\n"
            "Respond with a JSON object containing:\n"
            '{"needs_enhancement": true, "suggestion": "Title of the enhancement", "details": "Detailed technical description of what to implement"}'
        )

        try:
            import json
            import re

            response = ai_client.generate(prompt)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                return result
        except Exception as e:
            self.agent.log(f"Feature enhancement analysis failed for {repository}: {e}", "WARNING")

        return {"needs_enhancement": False}
