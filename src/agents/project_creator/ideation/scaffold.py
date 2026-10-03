"""Deterministic repository scaffold committed before the Jules session starts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .ci_templates import ci_workflow

_MIT = """MIT License

Copyright (c) {year} {owner}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_PR_TEMPLATE = (
    "## What changed\n\n## How it was tested\n\n## Linked issue\n`Closes #<number>`\n"
)


def build_files(spec: dict[str, Any], owner: str, now: datetime | None = None) -> dict[str, str]:
    """Path -> content for every scaffold file (CI only when the stack is recognised)."""
    year = (now or datetime.now(UTC)).year
    files = {
        "LICENSE": _MIT.format(year=year, owner=owner),
        "docs/SPEC.md": f"# {spec.get('title') or spec['repository_name']} — build spec\n\n"
                        f"{spec.get('idea_description', '')}\n\n"
                        f"**Stack:** {spec.get('tech_stack', '')}\n\n{spec.get('jules_prompt', '')}\n",
        ".env.example": "# Copy to .env and fill in. Never commit real secrets.\n",
        ".github/pull_request_template.md": _PR_TEMPLATE,
    }
    ci = ci_workflow(str(spec.get("tech_stack", "")))
    if ci:
        files[".github/workflows/ci.yml"] = ci
    return files


def apply_scaffold(
    repo: Any, spec: dict[str, Any], owner: str, log: Callable[..., None], branch: str = "master"
) -> list[str]:
    """Commit scaffold files to `branch`; per-file failures are logged and skipped."""
    created = []
    for path, content in build_files(spec, owner).items():
        try:
            repo.create_file(path, f"chore: scaffold {path}", content, branch=branch)
            created.append(path)
        except Exception as exc:
            log(f"Scaffold skipped {path}: {exc}", "WARNING")
    return created
