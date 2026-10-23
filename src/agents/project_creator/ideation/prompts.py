"""Prompt builders for each ideation stage."""

from __future__ import annotations

import json

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


def diverge_prompt(seed: Seed, history: list[str], n: int) -> str:
    return (
        f"You are a product-minded staff engineer inventing side projects for {_OWNER}.\n\n"
        f"Existing repositories (do NOT duplicate or lightly rename any): {', '.join(history) or 'none'}\n\n"
        f"Creative brief:\n{_seed_block(seed)}\n\n"
        f"Propose {n} DISTINCT candidate projects. Rules:\n"
        "- Each solves one concrete, painful problem for a clearly named user; no 'platform for everything'.\n"
        "- Forbidden: generic expense/budget/finance trackers, todo apps, habit trackers, weather apps, "
        "'AI assistant' wrappers, dashboards without a unique data source.\n"
        "- Candidates must differ from each other in problem, user and mechanism.\n"
        "- Names are memorable and specific (not 'smart-xyz-manager').\n"
        "- Scope: a polished, tested v1 buildable by one autonomous coding agent in one session.\n\n"
        'Reply with JSON only: {"candidates": [{"repository_name": "kebab-case", "title": "...", '
        '"problem": "...", "target_user": "...", "core_mechanism": "...", '
        '"differentiator": "what exists today and why this is better"}]}'
    )


def critique_prompt(candidates: list[dict], history: list[str]) -> str:
    return (
        "You are a skeptical product reviewer. Score each candidate 1-5 (integers, be harsh; 3 is "
        "average, 5 is exceptional) on:\n"
        "- novelty: not a clone of a popular tool or a tutorial project\n"
        "- utility: a real user would adopt it repeatedly\n"
        "- feasibility: a complete tested v1 fits in one session\n"
        "- distinctiveness: clearly different from the existing repos "
        f"({', '.join(history) or 'none'})\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False, indent=1)}\n\n"
        'Reply with JSON only: {"scores": [{"index": 0, "novelty": 1, "utility": 1, '
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
