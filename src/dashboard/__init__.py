"""Control-room dashboard: a static, dependency-free UI over the admin API.

The shell is plain HTML/CSS/ES modules (no build step) and carries no data: every
figure comes from `/api/*`, which requires the admin bearer token.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

STATIC_DIR = Path(__file__).parent / "static"
SECURITY_HEADERS = {
    # No inline script/style and no third-party origin: the page can only talk to this server.
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",
}


class DashboardFiles(StaticFiles):
    """Static files with a strict CSP; `no-cache` + ETag keeps deploys instant."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(SECURITY_HEADERS)
        return response


def mount_dashboard(app: FastAPI) -> None:
    """Serve the dashboard at `/dashboard/` and redirect `/` to it."""

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/dashboard/")

    app.mount("/dashboard", DashboardFiles(directory=STATIC_DIR, html=True), name="dashboard")
