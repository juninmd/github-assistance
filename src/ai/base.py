import abc
import json
import re
from typing import Any


class AIClient(abc.ABC):
    @abc.abstractmethod
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        """Resolve a git merge conflict given the full file context and conflict block."""
        pass  # pragma: no cover

    @abc.abstractmethod
    def generate_pr_comment(self, issue_description: str) -> str:
        """Generate a PR comment explaining a pipeline/issue failure."""
        pass  # pragma: no cover

    def generate(self, prompt: str) -> str:
        """General-purpose text generation (concrete clients should override)."""
        return self.generate_pr_comment(prompt)  # default fallback

    def classify_secret_finding(
        self,
        finding: dict[str, Any],
        redacted_context: str = "",
    ) -> dict[str, str]:
        """Return a binary decision for a gitleaks finding."""
        prompt = (
            "You are a security reviewer classifying a gitleaks finding.\n"
            "Decide using ONLY these actions:\n"
            "- REMOVE_FROM_HISTORY: real credential or secret material\n"
            "- IGNORE: placeholder, fake example, fixture, documentation snippet, or uncertain case\n\n"
            "IMPORTANT: Consider the file name and path when classifying.\n"
            "Files matching these patterns are very likely FALSE POSITIVES (IGNORE):\n"
            "- Test files (test_*, *_test.*, *_spec.*, *.test.*)\n"
            "- Example/sample files (*.example, *.sample, *.template, example_*)\n"
            "- Documentation (*.md, *.rst, *.txt, docs/*, README*)\n"
            "- Lock files (*.lock, package-lock.json, yarn.lock, pnpm-lock.yaml)\n"
            "- Config templates (.env.example, .env.sample, *.example.*)\n"
            "- Fixture/mock data (fixtures/*, mocks/*, __fixtures__/*)\n"
            "- Generated/vendor files (vendor/*, node_modules/*, dist/*)\n\n"
            "If context is insufficient, choose IGNORE.\n"
            "Respond with ONLY valid JSON:\n"
            '{"action": "REMOVE_FROM_HISTORY", "reason": "short explanation"}\n'
            "or\n"
            '{"action": "IGNORE", "reason": "short explanation"}\n\n'
            f"Rule: {finding.get('rule_id', 'unknown')} - {finding.get('description', '')}\n"
            f"File: {finding.get('file', '')}\n"
            f"Line: {finding.get('line', 0)}\n"
            f"Commit: {finding.get('commit', '')}\n"
            f"Date: {finding.get('date', '')}\n"
            f"Redacted local context:\n{redacted_context or 'Context unavailable.'}"
        )

        try:
            response_text = self.generate(prompt)
            data = self._extract_json_object(response_text)
            if not isinstance(data, dict):
                return {"action": "IGNORE", "reason": "Could not parse AI response"}

            action = str(data.get("action", "")).strip()
            if action not in {"REMOVE_FROM_HISTORY", "IGNORE"}:
                return {"action": "IGNORE", "reason": "Could not parse AI response"}

            reason = str(data.get("reason", "")).strip() or "No reason provided by AI"
            return {"action": action, "reason": reason}
        except Exception as exc:
            return {"action": "IGNORE", "reason": f"AI analysis failed: {exc}"}

    def analyze_pr_closure(self, persona: str, mission: str, comments_context: str) -> tuple[bool, str]:
        """
        Analyze PR comments and decide if it should be closed.
        Returns (should_close, reason).
        """
        prompt = (
            f"Persona: {persona}\n"
            f"Missão: {mission}\n\n"
            f"Abaixo estão os comentários de um Pull Request. "
            f"Analise se há uma solicitação clara de fechamento, código ruim ou inseguro, "
            f"rejeição ou desistência por parte de um autor autorizado.\n\n"
            f"Comentários:\n{comments_context}\n\n"
            f"Responda EXATAMENTE no formato JSON:\n"
            f"{{\"should_close\": true, \"reason\": \"motivo sucinto em português\"}}\n"
            f"or\n"
            f"{{\"should_close\": false, \"reason\": \"\"}}"
        )

        response_text = self.generate(prompt)

        data = self._extract_json_object(response_text)
        if isinstance(data, dict):
            return bool(data.get("should_close", False)), str(data.get("reason", ""))

        # Fallback if JSON parsing fails
        if "true" in response_text.lower() or "\"should_close\": true" in response_text.lower():
            return True, "Identificado motivo para fechamento (parsing fallback)"

        return False, ""

    def _extract_code_block(self, text: str) -> str:
        """Extract the first fenced code block from markdown; return original text if none found."""
        match = re.search(r"```(.*?)```", text, re.DOTALL)
        if match:
            content = match.group(1)
            if "\n" in content:
                first_line, remainder = content.split("\n", 1)
                if first_line.strip().isalnum() and remainder.strip():
                    return remainder.strip() + "\n"
            return content.strip() + "\n"
        return text.strip() + "\n"

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        """Extract the first JSON object found in a model response."""
        decoder = json.JSONDecoder()
        candidates = [text.strip(), self._extract_code_block(text).strip()]

        for candidate in candidates:
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
            for match in re.finditer(r"\{", candidate):
                try:
                    data, _ = decoder.raw_decode(candidate[match.start():])
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    return data
        return None
