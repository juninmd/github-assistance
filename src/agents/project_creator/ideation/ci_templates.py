"""Minimal, stack-aware CI workflows (push/PR only, never scheduled)."""

from __future__ import annotations

import re

_HEAD = "name: CI\non:\n  push:\n    branches: [master]\n  pull_request:\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"

_STACKS: dict[str, str] = {
    "python": (
        "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
        "      - run: |\n          python -m pip install --upgrade pip pytest ruff\n"
        "          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi\n"
        "          if [ -f pyproject.toml ]; then pip install -e . || true; fi\n"
        "      - run: ruff check .\n      - run: pytest -q\n"
    ),
    "node": (
        "      - uses: actions/setup-node@v4\n        with:\n          node-version: 22\n"
        "      - run: npm ci || npm install\n      - run: npm run lint --if-present\n"
        "      - run: npm test --if-present\n"
    ),
    "go": (
        "      - uses: actions/setup-go@v5\n        with:\n          go-version: stable\n"
        "      - run: go vet ./...\n      - run: go test ./...\n"
    ),
    "rust": (
        "      - uses: dtolnay/rust-toolchain@stable\n"
        "      - run: cargo clippy --all-targets -- -D warnings\n      - run: cargo test\n"
    ),
}


_NEEDLES = (
    ("rust", {"rust", "ratatui", "cargo"}),
    ("go", {"go", "golang", "chi"}),
    ("node", {"node", "node.js", "nodejs", "typescript", "react", "svelte", "vite", "javascript",
              "fastify"}),
    ("python", {"python", "fastapi", "textual", "typer", "duckdb"}),
)


def detect_stack(tech_stack: str) -> str | None:
    words = set(re.findall(r"[a-z0-9.]+", tech_stack.lower()))
    return next((key for key, needles in _NEEDLES if words & needles), None)


def ci_workflow(tech_stack: str) -> str | None:
    stack = detect_stack(tech_stack)
    return _HEAD + _STACKS[stack] if stack else None
