"""OpenCode runner for agent-based repository automation."""
import os
import random
import re
import subprocess
import tempfile
from datetime import datetime


class OpencodeRunner:
    """Handles opencode-based repository operations."""

    _model_cache: str | None = None

    def __init__(self, allowlist, log_func, github_client):
        self.allowlist = allowlist
        self.log = log_func
        self.github_client = github_client

    def get_random_free_opencode_model(self) -> str:
        """Pick a random free opencode model. Falls back to big-pickle on failure."""
        if OpencodeRunner._model_cache is not None:
            return OpencodeRunner._model_cache
        try:
            result = subprocess.run(
                ["opencode", "models"], capture_output=True, text=True, timeout=15,
            )
            models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
            free = [m for m in models if m.endswith("-free") or m == "opencode/big-pickle"]
            if free:
                chosen = random.choice(free)
                self.log(f"Selected free opencode model: {chosen}")
                OpencodeRunner._model_cache = chosen
                return chosen
        except Exception as e:
            self.log(f"Could not list opencode models: {e}", "WARNING")
        OpencodeRunner._model_cache = "opencode/big-pickle"
        return OpencodeRunner._model_cache

    def run_on_repo(self, repository: str, instructions: str, title: str) -> dict:
        """Clone repo, run opencode on a new branch, commit, push and open a PR."""
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"opencode denied: Repository {repository} is not in allowlist")

        model = self.get_random_free_opencode_model()
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = f"https://{github_token}@github.com/{repository}.git"
        branch = "agent/" + re.sub(r"[^a-z0-9-]", "-", title.lower())[:60] + "-" + datetime.now().strftime("%Y%m%d%H%M")

        with tempfile.TemporaryDirectory() as tmpdir:
            clone = subprocess.run(
                ["git", "clone", "--depth=1", clone_url, tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            if clone.returncode != 0:
                self.log(f"[{title}] git clone failed: {clone.stderr}", "ERROR")
                return {"status": "clone_failed", "error": clone.stderr[:300]}

            subprocess.run(["git", "config", "user.email", "github-assistance@github.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "github-assistance"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "checkout", "-b", branch], cwd=tmpdir, capture_output=True)

            self.log(f"[{title}] Warming up opencode...")
            subprocess.run(
                ["opencode", "run", "--model", model, "ping"],
                capture_output=True, text=True, timeout=120, cwd=tmpdir,
            )

            self.log(f"[{title}] Running opencode on {repository} (branch: {branch})...")
            run_result = subprocess.run(
                ["opencode", "run", "--model", model, instructions],
                capture_output=True, text=True, timeout=600, cwd=tmpdir,
            )
            if run_result.returncode != 0:
                self.log(f"[{title}] opencode failed (rc={run_result.returncode}): {run_result.stderr}", "WARNING")
                return {"status": "opencode_failed", "stderr": run_result.stderr[:300]}

            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            commit = subprocess.run(
                ["git", "commit", "-m", f"feat: {title}\n\nApplied by github-assistance senior_developer agent via opencode."],
                cwd=tmpdir, capture_output=True, text=True,
            )
            if "nothing to commit" in commit.stdout + commit.stderr:
                self.log(f"[{title}] opencode made no changes.")
                return {"status": "no_changes"}

            push = subprocess.run(
                ["git", "push", "origin", branch],
                cwd=tmpdir, capture_output=True, text=True, timeout=60,
            )
            if push.returncode != 0:
                self.log(f"[{title}] git push failed: {push.stderr}", "ERROR")
                return {"status": "push_failed", "error": push.stderr[:300]}

        pr_url = self._open_pull_request(repository, branch, title, run_result.stdout)
        self.log(f"[{title}] PR opened: {pr_url}")
        return {"status": "success", "branch": branch, "pr_url": pr_url}

    def _open_pull_request(self, repository: str, branch: str, title: str, opencode_output: str) -> str:
        """Open a pull request for the given branch and return the PR URL."""
        repo = self.github_client.get_repo(repository)
        base = repo.default_branch
        body = (
            f"## \U0001f916 Altera\u00e7\u00f5es aplicadas pelo agente `senior_developer`\n\n"
            f"**Modelo utilizado:** opencode (free tier)\n\n"
            f"### O que foi feito\n"
            f"{title}\n\n"
            f"### Sa\u00edda do opencode\n"
            f"```\n{opencode_output[:1500]}\n```\n\n"
            f"---\n_Pull request criado automaticamente pelo agente github-assistance._"
        )
        pr = repo.create_pull(title=f"[agent] {title}", body=body, head=branch, base=base)
        return pr.html_url