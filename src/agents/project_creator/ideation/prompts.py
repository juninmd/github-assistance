"""Prompt builders for each ideation stage."""

from __future__ import annotations

import json

from .portfolio import Portfolio
from .seed import Seed

_OWNER = "a Brazilian senior developer (Antonio Carlos)"


def _seed_block(seed: Seed) -> str:
    return (
        f"- Domain: {seed.domain}\n"
        f"- Niche angles to draw from (mix or go beyond): {'; '.join(seed.angles)}\n"
        f"- Project shape: {seed.archetype} ({seed.archetype_desc})\n"
        f"- Suggested stacks: {', '.join(seed.stacks)}\n"
        f"- Hard constraint: {seed.twist}"
    )


def portfolio_block(portfolio: Portfolio | None) -> str:
    """What the owner really builds (the bar) and what earlier runs got wrong (the anti-pattern)."""
    if not portfolio or not (portfolio.exemplars or portfolio.generated):
        return ""
    parts = []
    if portfolio.exemplars:
        listing = "\n".join(f"- {line}" for line in portfolio.exemplars)
        parts.append(f"Repos the owner built by hand (his taste and quality bar):\n{listing}")
    if portfolio.languages:
        parts.append(f"Languages he actually writes: {', '.join(portfolio.languages)}")
    if portfolio.generated:
        parts.append(
            "Earlier auto-generated repos he never used (generic back-office/SaaS style, "
            f"do NOT imitate): {', '.join(portfolio.generated)}"
        )
    return "Owner portfolio:\n" + "\n".join(parts) + "\n\n"


def diverge_prompt(seed: Seed, history: list[str], n: int, portfolio: Portfolio | None = None) -> str:
    return (
        f"You are a product-minded staff engineer inventing side projects for {_OWNER}.\n\n"
        f"Existing repositories (do NOT duplicate or lightly rename any): {', '.join(history) or 'none'}\n\n"
        f"{portfolio_block(portfolio)}"
        f"Creative brief:\n{_seed_block(seed)}\n\n"
        f"Propose {n} DISTINCT candidate projects. Rules:\n"
        "- Start from a friction the owner or a developer like him hits weekly (a concrete moment, not a "
        "market segment). Prefer a small sharp tool (one verb, useful within minutes) over a platform.\n"
        "- It must be usable by the owner himself on his own machine/server/phone from day one: no paying "
        "customers, no third-party business accounts, no back-office workflows (contracts, retainers, "
        "invoicing, release orchestration, 'autonomous X' platforms).\n"
        "- Prefer extending or pairing with something he already built (name it in `complements`) over a "
        "disconnected idea.\n"
        "- Forbidden: generic expense/budget/finance trackers, todo apps, habit trackers, weather apps, "
        "'AI assistant' wrappers, dashboards without a unique data source.\n"
        "- Candidates must differ from each other in problem, user and mechanism.\n"
        "- Names are memorable and specific (not 'smart-xyz-manager').\n"
        "- Scope: a polished, tested v1 buildable by one autonomous coding agent in one session.\n\n"
        'Reply with JSON only: {"candidates": [{"repository_name": "kebab-case", "title": "...", '
        '"friction": "the concrete weekly moment that hurts", "complements": "owner repo it pairs with, or standalone", '
        '"problem": "...", "target_user": "...", "core_mechanism": "...", '
        '"differentiator": "what exists today and why this is better"}]}'
    )


def critique_prompt(candidates: list[dict], history: list[str], portfolio: Portfolio | None = None) -> str:
    return (
        "You are a skeptical product reviewer. Score each candidate 1-5 (integers, be harsh; 3 is "
        "average, 5 is exceptional) on:\n"
        "- novelty: not a clone of a popular tool or a tutorial project\n"
        "- utility: a real user would adopt it repeatedly\n"
        "- fit: the owner (see portfolio) would plausibly use it himself within a week; 1 for generic "
        "business tooling nobody on his machine needs\n"
        "- feasibility: a complete tested v1 fits in one session\n"
        "- distinctiveness: clearly different from the existing repos "
        f"({', '.join(history) or 'none'})\n\n"
        f"{portfolio_block(portfolio)}"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False, indent=1)}\n\n"
        'Reply with JSON only: {"scores": [{"index": 0, "novelty": 1, "utility": 1, "fit": 1, '
        '"feasibility": 1, "distinctiveness": 1, "reason": "one sentence"}]}'
    )


def queries_prompt(candidate: dict) -> str:
    return (
        "Write 3 short search queries (English, 2-5 words each) a developer would type to find existing "
        "tools that already solve this problem, from most specific to broadest.\n\n"
        f"{json.dumps(candidate, ensure_ascii=False, indent=1)}\n\n"
        'Reply with JSON only: {"queries": ["...", "...", "..."]}'
    )


def specify_prompt(candidate: dict, seed: Seed, stack_hint: str, research: str = "none found") -> str:
    return (
        "You are a principal engineer writing the build spec an autonomous coding agent will follow.\n\n"
        f"Chosen project:\n{json.dumps(candidate, ensure_ascii=False, indent=1)}\n\n"
        f"Shape: {seed.archetype}. Preferred stack: {stack_hint}. Constraint: {seed.twist}.\n\n"
        f"Market research (existing GitHub projects and web hits):\n{research}\n\n"
        "Study the competitors: name what each does well and where it falls short, then borrow the "
        "proven features (adapted, never copied code) and pick a clear differentiator. If a competitor "
        "already does exactly this, say so in `overlap_risk`.\n\n"
        "Write a precise, opinionated spec. Features need testable acceptance criteria; the "
        "interface section lists exact commands/endpoints/screens with example I/O; roadmap items "
        "are independent, single-PR improvements beyond v1 (new capabilities, not chores).\n\n"
        "Reply with JSON only:\n"
        '{"repository_name": "kebab-case", "title": "...", '
        '"idea_description": "2-3 sentences: what, for whom, why it matters", "tech_stack": "...", '
        '"problem": "...", "target_user": "...", '
        '"features": [{"name": "...", "description": "...", "acceptance": "..."}], '
        '"architecture": "modules, data flow, key decisions", '
        '"interfaces": "exact CLI/API/UI surface with example input and output", '
        '"fixtures": "bundled sample data and how the demo runs", '
        '"test_plan": "unit, integration and edge cases to cover", '
        '"tagline": "one punchy line for the README hero", '
        '"competitors": [{"name": "owner/repo", "url": "...", "strengths": "...", "gaps": "..."}], '
        '"external_features": ["feature seen in competitors worth adopting, with source"], '
        '"overlap_risk": "low|medium|high with one sentence", '
        '"roadmap_features": [{"title": "...", "objective": "concrete goal and acceptance criteria"}]}\n'
        "features: 4-6 items. competitors: up to 5 from the research. "
        "roadmap_features: 10-12 independent items, most valuable first, including features borrowed "
        "from competitors, integrations, performance, UX polish and docs."
    )
