"""Tests for the public pages.

These are the routes a stranger hits first, and the ones that must not lie. The
cases worth covering are all about what happens when there is nothing to report:
a fresh deployment has no measurements, and a page that renders that as 0%
accuracy is worse than one that says so.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analytics


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return TestClient(app)


class TestEmptyDeployment:
    """A deployment with no data yet must be legible, not broken."""

    def test_accuracy_reports_no_data_rather_than_zero(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero would say the system is wrong every time. Null says nothing has
        been measured, which is the truth on a fresh deployment."""

        async def empty() -> dict:
            return {
                "decision_accuracy_pct": None,
                "confident_decisions": 0,
                "confident_overturned": 0,
                "flagged_for_review": 0,
                "flagged_changed_pct": None,
                "auto_decided_pct": None,
                "shots_total": 0,
            }

        monkeypatch.setattr(analytics, "accuracy_summary", empty)
        body = client.get("/public/accuracy").json()

        assert body["decision_accuracy_pct"] is None
        assert body["shots_total"] == 0

    def test_eval_says_it_has_not_run(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty axes list with no explanation reads as a broken page. The
        state is named so the interface can say what is actually happening."""

        async def none() -> list:
            return []

        monkeypatch.setattr(analytics, "eval_summary", none)
        body = client.get("/public/eval").json()

        assert body["state"] == "not_run"
        assert body["axes"] == []
        assert "not been run" in body["message"]

    def test_scale_returns_zeros_not_an_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Counts genuinely are zero here, unlike accuracy, so zero is honest."""

        async def empty() -> dict:
            return {
                "productions": 0, "clips": 0, "scenes": 0,
                "shots": 0, "decisions": 0, "footage_hours": 0.0,
            }

        monkeypatch.setattr(analytics, "scale", empty)
        assert client.get("/public/scale").json()["clips"] == 0


class TestPopulatedDeployment:
    def test_accuracy_carries_its_own_definition(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A figure whose definition lives in a slide deck is not one anyone can
        check. It travels with the number."""

        async def measured() -> dict:
            return {
                "decision_accuracy_pct": 98.8,
                "confident_decisions": 45918,
                "confident_overturned": 571,
                "flagged_for_review": 9231,
                "flagged_changed_pct": 41.5,
                "auto_decided_pct": 83.3,
                "shots_total": 55149,
            }

        monkeypatch.setattr(analytics, "accuracy_summary", measured)
        body = client.get("/public/accuracy").json()

        assert body["decision_accuracy_pct"] == 98.8
        assert "flagged for review are excluded" in body["definition"]
        # The weakness is published beside the number, not omitted.
        assert "weaker evidence" in body["caveat"]

    def test_eval_keeps_misses_and_false_alarms_apart(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """They are not equally bad and are never summed: a missed problem
        reaches the cut, a false alarm costs ten seconds."""

        async def measured() -> list:
            return [
                {
                    "axis": "stability", "cases": 7, "missed": 0,
                    "false_alarms": 0, "recall_pct": 100.0,
                    "precision_pct": 100.0, "timecode_accuracy_pct": 100.0,
                    "last_run": "2026-08-28T09:00:00",
                }
            ]

        monkeypatch.setattr(analytics, "eval_summary", measured)
        axis = client.get("/public/eval").json()["axes"][0]

        assert "missed" in axis
        assert "false_alarms" in axis
        assert "accuracy_pct" not in axis


class TestCaching:
    def test_public_pages_are_cacheable(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """A burst of visitors should cost one query. The window is short enough
        that the page stays visibly live, which is the point of it."""

        async def empty() -> dict:
            return {"shots_total": 0}

        monkeypatch.setattr(analytics, "accuracy_summary", empty)
        response = client.get("/public/accuracy")
        assert "max-age" in response.headers["cache-control"]


class TestHealth:
    def test_health_does_not_depend_on_the_database(self, client: TestClient) -> None:
        """A health check that fails when a dependency is slow takes the service
        down for a problem it could have survived."""
        assert client.get("/public/health").json() == {"status": "ok"}
