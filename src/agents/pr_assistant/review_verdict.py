"""Structured code-review verdict: parse the model JSON and render the PR comment.

Purely advisory: nothing here is read by ``merge_policy`` or the merge path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.agents.utils import build_origin_metadata

REVIEW_MARKER = "<!-- opencode-review -->"
APPROVE = "APPROVE"
REQUEST_CHANGES = "REQUEST_CHANGES"
LABEL_APPROVED = "review/approved"
LABEL_CHANGES = "review/needs-changes"
LABEL_CRITICAL = "review/critical"
GATE_NAME = "github-assistance/review"
LABEL_COLORS = {
    LABEL_APPROVED: "0e8a16",
    LABEL_CHANGES: "d93f0b",
    LABEL_CRITICAL: "b60205",
}

_APPROVE_WORDS = {"APPROVE", "APPROVED", "LGTM", "PASS"}
_CHANGES_WORDS = {"REQUEST_CHANGES", "CHANGES_REQUESTED", "REJECT", "REJECTED", "BLOCK"}
_SEVERITY_ICON = {"error": "🔴", "warn": "🟠", "warning": "🟠", "nit": "🟡", "info": "🔵"}


@dataclass(frozen=True)
class Finding:
    file: str = ""
    line: int = 0
    severity: str = "nit"
    issue: str = ""


@dataclass(frozen=True)
class ReviewVerdict:
    verdict: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    model: str = ""
    fixed: bool = False
    commit: str = ""

    @property
    def approved(self) -> bool:
        return self.verdict == APPROVE

    @property
    def critical(self) -> bool:
        return any((f.severity or "").lower() == "error" for f in self.findings)

    @property
    def label(self) -> str:
        return LABEL_APPROVED if self.approved else LABEL_CHANGES


def _extract_json(text: str) -> dict[str, Any] | None:
    """Return the first JSON object found in a model answer."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            data, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _normalize_verdict(value: Any) -> str | None:
    word = str(value or "").strip().upper().replace(" ", "_")
    if word in _APPROVE_WORDS:
        return APPROVE
    if word in _CHANGES_WORDS:
        return REQUEST_CHANGES
    return None


def _parse_findings(items: Any) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_line = item.get("line", 0)
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            line = 0
        findings.append(
            Finding(
                file=str(item.get("file") or item.get("path") or ""),
                line=line,
                severity=str(item.get("severity") or "nit").lower(),
                issue=str(item.get("issue") or item.get("message") or item.get("problem") or ""),
            )
        )
    return findings


def parse_review(text: str | None, model: str = "") -> ReviewVerdict | None:
    """Parse a model answer into a verdict; ``None`` when it is unusable."""
    if not text:
        return None
    data = _extract_json(text)
    if data is None:
        return None
    verdict = _normalize_verdict(data.get("verdict") or data.get("decision"))
    if verdict is None:
        return None
    return ReviewVerdict(
        verdict=verdict,
        summary=str(data.get("summary") or "").strip(),
        findings=_parse_findings(data.get("findings")),
        model=model,
    )


def _render_findings(verdict: ReviewVerdict) -> str:
    if not verdict.findings:
        return "Sem pontos bloqueantes. 🎉" if verdict.approved else "Nenhum detalhe adicional informado."
    if verdict.approved:
        lines = [
            f"- 🟡 `{f.file}`{f':{f.line}' if f.line else ''} — {f.issue}"
            for f in verdict.findings
        ]
        return "**Pontos de atenção (não bloqueantes):**\n" + "\n".join(lines)
    rows = [
        f"| {_SEVERITY_ICON.get(f.severity, '🟡')} {f.severity} | `{f.file}` | "
        f"{f.line or '-'} | {f.issue} |"
        for f in verdict.findings
    ]
    return "\n".join(
        ["| Severidade | Arquivo | Linha | Problema |", "|---|---|---|---|", *rows]
    )


def _render_fixes(verdict: ReviewVerdict) -> str:
    if verdict.approved:
        return ""
    if verdict.fixed:
        sha = (verdict.commit or "")[:8]
        return f"✅ Correções aplicadas e enviadas para este PR no commit `{sha}`."
    return "ℹ️ Nenhuma correção automática foi aplicada."


def build_review_comment(verdict: ReviewVerdict, head_sha: str = "", jules: bool = False) -> str:
    """Render the standardized, emoji-tagged PT-BR review comment."""
    header = "## ✅ Revisão aprovada! 🎉🚀" if verdict.approved else "## ❌ Mudanças sugeridas 🛠️"
    summary = verdict.summary or (
        "Tudo certo por aqui." if verdict.approved else "Encontrei pontos a corrigir."
    )
    footer = (
        f"<sub>🤖 Revisão automática via opencode · modelo `{verdict.model or 'cloud/auto'}` · "
        f"skills `code-review`/`security-ops`/`test-engineering`"
        + (f" · SHA `{head_sha[:8]}`" if head_sha else "")
        + "</sub>"
    )
    parts = [
        REVIEW_MARKER,
        header,
        f"**Resumo:** {summary}",
        "### 🔎 Achados",
        _render_findings(verdict),
    ]
    fixes = _render_fixes(verdict)
    if fixes:
        parts += ["### 🛠️ Correções", fixes]
    if verdict.critical:
        parts += [
            "### 🚨 Crítico",
            f"Achados de severidade `error` bloqueiam o merge (draft + check `{GATE_NAME}`) "
            "até serem corrigidos por um novo commit.",
        ]
    if jules and not verdict.approved:
        parts += [
            "### 🤖 Jules",
            "Este PR foi aberto pelo Jules — ele aplicará as correções automaticamente "
            "em um novo commit.",
        ]
    parts += [
        f"**Veredito:** `{verdict.verdict}` · label `{verdict.label}`",
        "*Comentário consultivo — não bloqueia o merge.*",
        footer,
        "---",
        build_origin_metadata("pr_assistant", verdict.model or "cloud/auto"),
    ]
    return "\n\n".join(part for part in parts if part)
