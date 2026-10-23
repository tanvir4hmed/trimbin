"""Deferred authenticated portable API discovery/isolation on real PostgreSQL."""

import os

import pytest
from fastapi.testclient import TestClient
from test_evidence_postgres import workspace  # noqa: F401

from app.auth import Principal, require_signed_in
from app.portable import app
from app.routes import workflow

pytestmark = pytest.mark.skipif(not os.getenv("FOUNDATION_TEST_DSN"), reason="PostgreSQL required")


def test_project_discovery_and_summary_do_not_leak(request, monkeypatch):
    store, project, _ = request.getfixturevalue("workspace")
    monkeypatch.setattr(workflow.settings, "database_url", store.dsn)
    email = f"viewer-{project}@example.test"
    with store.connection() as conn:
        conn.execute("INSERT INTO project_members VALUES (%s,%s,'viewer')", (project, email))
    identity = {"email": email}
    app.dependency_overrides[require_signed_in] = lambda: Principal(email=identity["email"])
    try:
        with TestClient(app) as client:
            visible = client.get("/workflow/projects").json()["projects"]
            assert any(p["id"] == project for p in visible)
            result = client.get(f"/workflow/{project}/summary")
            assert result.status_code == 200
            assert result.json()["sources"] == 1
            assert result.headers["cache-control"] == "private, no-store"
            identity["email"] = "outsider@example.test"
            assert client.get("/workflow/projects").json()["projects"] == []
            assert client.get(f"/workflow/{project}/summary").status_code == 404
            assert client.get("/workflow/projects?offset=-1").status_code == 422

    finally:
        app.dependency_overrides.clear()
