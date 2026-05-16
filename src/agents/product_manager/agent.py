"""
Product Manager Agent - Responsible for roadmap planning and feature prioritization.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.product_manager.roadmap_generator import RoadmapGenerator
from src.ai import get_ai_client


class ProductManagerAgent(BaseAgent):
    """Product Manager Agent — roadmap planning and feature prioritization."""

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="product_manager", enforce_repository_allowlist=True, **kwargs)
        self._ai_client = get_ai_client(
            provider=ai_provider or "ollama",
            model=ai_model or "qwen3:1.7b",
            **(ai_config or {})
        )
        self.roadmap_gen = RoadmapGenerator(self)

    def run(self) -> dict[str, Any]:
        """Execute the Product Manager workflow across all allowed repositories."""
        self.log("Starting Product Manager workflow")
        repositories = self.get_allowed_repositories()
        if not repositories:
            return {"status": "skipped", "reason": "empty_allowlist"}

        results: dict[str, Any] = {
            "processed": [], "failed": [], "timestamp": datetime.now().isoformat()
        }
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.analyze_and_create_roadmap, repo): repo for repo in repositories}
            for future in as_completed(futures):
                repo = futures[future]
                try:
                    roadmap = future.result()
                    results["processed"].append({"repository": repo, "roadmap": roadmap})
                except Exception as e:
                    self.log(f"Failed to process {repo}: {e}", "ERROR")
                    results["failed"].append({"repository": repo, "error": str(e)})

        self._send_summary(results)
        return results

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        processed = results.get("processed", [])
        failed = results.get("failed", [])
        lines = [
            "📋 <b>PRODUCT MANAGER</b>",
            "──────────────────────",
            f"📦 <b>Roadmaps processados:</b> <code>{len(processed)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in processed[:5]:
            roadmap = item.get("roadmap") or {}
            if isinstance(roadmap, dict) and roadmap.get("skipped"):
                lines.append(f'  └ <code>{esc(item["repository"])}</code> — <i>{esc(roadmap.get("reason", "skipped"))}</i>')
            else:
                lines.append(f'  └ <code>{esc(item["repository"])}</code> — sessão criada')
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")

    def analyze_and_create_roadmap(self, repository: str) -> dict[str, Any]:
        """Analyse a repository and create/update its ROADMAP.md via Jules."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            raise ValueError(f"Could not access repository {repository}")

        if self.roadmap_gen.is_roadmap_up_to_date(repo_info):
            return {"repository": repository, "skipped": True, "reason": "roadmap_up_to_date"}

        if self.has_recent_jules_session(repository, "roadmap"):
            return {"repository": repository, "skipped": True, "reason": "recent_session_exists"}

        analysis = self.roadmap_gen.analyze_repository(repository, repo_info)
        roadmap_instructions = self.roadmap_gen.generate_instructions(repository, analysis)

        session = self.create_jules_session(
            repository=repository,
            instructions=roadmap_instructions,
            title=f"Update Product Roadmap for {repository}",
            base_branch=getattr(repo_info, "default_branch", "main"),
        )

        return {
            "repository": repository,
            "session_id": session.get("id"),
            "analysis_summary": analysis.get("summary", ""),
            "priority_count": len(analysis.get("priorities", [])),
        }

