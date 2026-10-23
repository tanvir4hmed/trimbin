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
        "deploy/portable/api.Dockerfile",
        "web/portable.Dockerfile",
        ".env.example",
    ]:
        assert allowed(name)
    for name in [
        "web/.env.production",
        "api/credentials.json",
        "api/archive/a.py",
        "web/node_modules/a.js",
        "api/footage.mp4",
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


def test_portable_routes_do_not_mount_legacy_operations():
    from app.portable import app

    paths = {r.path for r in app.routes}
    assert "/workflow/projects" in paths
    assert "/renders/{project}/jobs/{job_id}/download" in paths
    assert "/health" in paths
    assert not any(p.startswith(("/film", "/uploads", "/maintenance")) for p in paths)
