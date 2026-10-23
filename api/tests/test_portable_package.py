"""Deferred package/evidence-policy checks; no claim of deployed acceptance."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_filters_local_credentials_media_and_archive():
    allowed = tool("package_portable").allowed
    for name in [
        "web/package-lock.json",
        "LICENSE",
        "deploy/production/api.Dockerfile",
        "deploy/production/web.Dockerfile",
        ".env.example",
        "docs/diagrams/system-overview.png",
        "docs/diagrams/system-overview.svg",
    ]:
        assert allowed(name)
    for name in [
        "web/.env.production",
        "api/credentials.json",
        "api/archive/a.py",
        "web/node_modules/a.js",
        "api/footage.mp4",
        "api/private-frame.png",
        "docs/private-footage.png",
        "../api/app.py",
        ".secrets/key.json",
    ]:
        assert not allowed(name)


def test_empty_or_fixture_evidence_cannot_pass(tmp_path):
    module = tool("workflow_acceptance")
    record = module.template()
    assert module.check(record, tmp_path)
    for gate in record["gates"].values():
        gate.update(status="passed", evidence=[{"path": "fixture.json", "fixture_only": True}])
    (tmp_path / "fixture.json").write_text("{}")
    failures = module.check(record, tmp_path)
    assert any("invalid_evidence" in f for f in failures)


def test_compatibility_entrypoint_is_the_canonical_application():
    from app.portable import app

    paths = set(app.openapi()["paths"])
    assert "/workflow/projects" in paths
    assert "/renders/{project}/jobs/{job_id}/download" in paths
    assert "/health" in paths
    from app.main import app as canonical

    assert app is canonical
    assert any(p.startswith("/uploads") for p in paths)
