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
                "real_clips": 0, "synthetic_clips": 0,
                "real_productions": 0, "synthetic_productions": 0,
                "real_scenes": 0, "real_shots": 0,
                "real_hours": 0.0, "synthetic_hours": 0.0,
            }

        monkeypatch.setattr(analytics, "corpus", empty)
        assert client.get("/public/scale").json()["real"]["clips"] == 0


class TestProvenanceSeparation:
    """Real and generated rows must never be presented as one number.

    An accuracy figure computed over generated rows measures the generator. The
    separation exists so that inference is impossible to draw by accident, and
    these tests are what keep it that way.
    """

    def test_real_and_generated_are_never_summed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def mixed() -> dict:
            return {
                "real_clips": 7, "synthetic_clips": 306215,
                "real_productions": 1, "synthetic_productions": 400,
                "real_scenes": 1, "real_shots": 1,
                "real_hours": 0.02, "synthetic_hours": 4209.7,
            }

        monkeypatch.setattr(analytics, "corpus", mixed)
        body = client.get("/public/scale").json()

        assert body["real"]["clips"] == 7
        assert body["synthetic"]["clips"] == 306215
        # No total anywhere, deliberately. A combined figure is the thing a
        # reader would take as evidence about the system.
        assert "clips" not in body
        assert "total" not in body

    def test_generated_data_says_what_it_is_for(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The label travels in the payload, not only in the page that renders
        it, so it cannot be lost by whoever consumes the API."""

        async def mixed() -> dict:
            return {
                "real_clips": 0, "synthetic_clips": 306215,
                "real_productions": 0, "synthetic_productions": 400,
                "real_scenes": 0, "real_shots": 0,
                "real_hours": 0.0, "synthetic_hours": 4209.7,
            }

        monkeypatch.setattr(analytics, "corpus", mixed)
        purpose = client.get("/public/scale").json()["synthetic"]["purpose"]
        assert "Excluded from every accuracy figure" in purpose

    def test_accuracy_declares_that_it_excludes_generated_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def empty() -> dict:
            return {"shots_total": 0, "decision_accuracy_pct": None}

        monkeypatch.setattr(analytics, "accuracy_summary", empty)
        assert client.get("/public/accuracy").json()["counts_only_real_work"] is True


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
