"""Admin API (`/api/*`) and the static dashboard shell."""

import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.dashboard import STATIC_DIR
from src.webhooks.server import create_app

AUTH = {"Authorization": "Bearer admin-token"}
ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        github_token="unused",
        admin_api_token="admin-token",
        webhook_database_path=str(tmp_path / "webhooks.db"),
        worker_enabled=False,
        webhook_purge_enabled=False,
    )


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as test_client:
        yield test_client


def _enqueue(client: TestClient, key: str, repo: str = "acme/api") -> str:
    job_id, _ = client.app.state.store.jobs.enqueue("pr", key, {"mode": "observe"}, repo=repo)
    return job_id


@pytest.mark.parametrize("path", ["/api/overview", "/api/agents", "/api/jobs/x"])
def test_new_routes_require_the_admin_token(client, path):
    assert client.get(path).status_code == 401
    assert client.post("/api/jobs/x/reprocess").status_code == 401


def test_jobs_endpoint_filters_searches_and_reports_total(client):
    for index in range(3):
        _enqueue(client, f"acme/api#{index}")
    _enqueue(client, "acme/web#9", repo="acme/web")
    page = client.get("/api/jobs?limit=2&offset=1", headers=AUTH).json()
    assert page["total"] == 4 and len(page["jobs"]) == 2
    assert client.get("/api/jobs?repo=acme/web", headers=AUTH).json()["total"] == 1
    assert client.get("/api/jobs?q=WEB", headers=AUTH).json()["jobs"][0]["key"] == "acme/web#9"
    assert client.get("/api/jobs?status=blocked", headers=AUTH).json() == {"jobs": [], "total": 0}
    assert client.get("/api/jobs?status=bogus", headers=AUTH).status_code == 422


def test_job_detail_and_reprocess(client):
    store = client.app.state.store.jobs
    job_id = _enqueue(client, "acme/api#1")
    assert client.get(f"/api/jobs/{job_id}", headers=AUTH).json()["key"] == "acme/api#1"
    assert client.get("/api/jobs/missing", headers=AUTH).status_code == 404
    assert client.post("/api/jobs/missing/reprocess", headers=AUTH).status_code == 404

    job = store.claim(limit=1)[0]
    assert client.post(f"/api/jobs/{job_id}/reprocess", headers=AUTH).status_code == 409
    store.complete(job["id"], "blocked", error="ci_failed")
    reset = client.post(f"/api/jobs/{job_id}/reprocess", headers=AUTH)
    assert reset.status_code == 200
    assert reset.json()["status"] == "pending" and reset.json()["attempts"] == 0


def test_overview_reports_queue_deliveries_and_service(client):
    _enqueue(client, "acme/api#1")
    client.app.state.store.record("d-1", "pull_request", {"action": "opened"})
    data = client.get("/api/overview?hours=48", headers=AUTH).json()
    assert data["totals"] == {"pending": 1} and data["window_hours"] == 48
    assert data["deliveries"] == [{"label": "pull_request", "value": 1}]
    assert data["service"] == {
        "mode": "observe", "simulation": False, "worker_enabled": False,
        "worker_alive": False, "poll_interval_seconds": 15,
    }
    assert client.get("/api/overview?hours=0", headers=AUTH).status_code == 422
    assert client.get("/api/overview?hours=9999", headers=AUTH).status_code == 422


def test_agents_endpoint_lists_the_fleet(client):
    data = client.get("/api/agents", headers=AUTH).json()
    names = [agent["name"] for agent in data["agents"]]
    assert len(names) == 17 and "pr-assistant" in names
    assert data["ai"]["enabled"] is False and data["owner"] == "juninmd"


def test_dashboard_shell_is_served_with_a_strict_csp(client):
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307 and root.headers["location"] == "/dashboard/"
    page = client.get("/dashboard/")
    assert page.status_code == 200 and "Central de Controle" in page.text
    csp = page.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "'unsafe-inline'" not in csp
    assert page.headers["cache-control"] == "no-cache"
    assert page.headers["x-content-type-options"] == "nosniff"
    script = client.get("/dashboard/js/main.js")
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]
    assert client.get("/dashboard/missing.js").status_code == 404


def test_dashboard_can_be_disabled(tmp_path):
    settings = replace(_settings(tmp_path), dashboard_enabled=False)
    with TestClient(create_app(settings)) as disabled:
        assert disabled.get("/dashboard/").status_code == 404
        assert disabled.get("/api/jobs", headers=AUTH).status_code == 200


def test_dashboard_assets_are_self_contained():
    """No build step: every referenced file must exist and nothing loads off-origin or inline."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for reference in re.findall(r'(?:href|src)="([^"#][^"]*)"', html):
        assert not reference.startswith(("http", "//")), reference
        assert (STATIC_DIR / reference).is_file(), reference
    assert "<style" not in html and not re.search(r"\sstyle=|\son\w+=", html)
    for module in (STATIC_DIR / "js").rglob("*.js"):
        source = module.read_text(encoding="utf-8")
        assert "innerHTML" not in source.replace("never innerHTML", ""), module.name
        for target in re.findall(r'from "(\.[^"]+)"', source):
            assert (module.parent / target).resolve().is_file(), f"{module.name} -> {target}"


def test_demo_seeder_builds_a_usable_database(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_demo_queue import seed

    path = str(tmp_path / "demo.db")
    assert seed(path, jobs=80, now=1_800_000_000.0) == {"jobs": 80, "deliveries": 240}
    with pytest.raises(SystemExit):
        seed(path, jobs=1)
    with TestClient(create_app(replace(_settings(tmp_path), webhook_database_path=path))) as demo:
        data = demo.get("/api/overview?hours=168", headers=AUTH).json()
    assert sum(data["totals"].values()) == 80 and data["totals"]["running"] == 2
