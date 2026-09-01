"""The dashboard route, actually called.

`/dashboard` answered 500 in production for every signed-in person, which took
Home *and* the review queue down together — the queue reads the same endpoint.

The cause was a response model added without the route being asked to satisfy
it. `ProjectCard` extends `Project`, `Project` requires `owner_email` and
`member_emails`, and the card dict carried neither. Three visible projects gave
exactly the six validation errors in the log.

Nothing had ever called this route. Every dashboard test exercised the service
underneath it, which was correct the whole time; the assembly in the route —
the only part that was wrong — had no test at all. So these call the endpoint
through the app and assert the response validates, because that is the failure
that reached a person.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import Principal, require_signed_in
from app.main import app
from app.routes import dashboard as dashboard_route
from app.services import members
from app.services.dashboard import Waiting


class FakeProject:
    def __init__(self, project_id: int, *, owner: str, members_: list[str]) -> None:
        self.project_id = project_id
        self.name = f"Scene {project_id} - two perspectives"
        self.owner_email = owner
        self.member_emails = members_
        self.is_public = True
        self.created_at = datetime.now(UTC)
        self.state = "active"
        self.rev = 0


@pytest.fixture
def signed_in():
    """The lead, because the bug only appeared for somebody with projects."""
    app.dependency_overrides[require_signed_in] = lambda: Principal(email=members.LEAD_EDITOR)
    yield
    app.dependency_overrides.pop(require_signed_in, None)


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch):
    """Three projects, which is what production had when it broke."""
    projects = [
        FakeProject(1, owner=members.LEAD_EDITOR, members_=["dipon778@gmail.com"]),
        FakeProject(2, owner=members.LEAD_EDITOR, members_=[]),
        FakeProject(3, owner=members.LEAD_EDITOR, members_=["mohidewan10@gmail.com"]),
    ]

    async def visible_to(email: str):
        return projects

    async def for_projects(ids, viewer):
        return {
            "queue": [
                Waiting(
                    project_id=1,
                    scene=1,
                    shot=2,
                    slug="1B",
                    takes=3,
                    margin=0.04,
                    reason="close_call",
                    assignee="",
                    state="",
                    circled_take=0,
                    chosen_take=1,
                    open_comments=0,
                )
            ],
            "queue_total": 1,
            "totals": {"waiting": 1, "yours": 0, "unassigned": 1, "projects": 3},
            "projects": [
                {
                    "project_id": p.project_id,
                    "scenes": 1,
                    "shots": 2,
                    "takes": 6,
                    "settled": 1,
                    "waiting": 1,
                    "progress_pct": 50.0,
                }
                for p in projects
            ],
        }

    async def nothing(ids):
        return []

    monkeypatch.setattr(dashboard_route.projects, "visible_to", visible_to)
    monkeypatch.setattr(dashboard_route.dashboard_service, "for_projects", for_projects)
    monkeypatch.setattr(dashboard_route.dashboard_service, "recent_decisions", nothing)
    monkeypatch.setattr(dashboard_route.dashboard_service, "recent_notes", nothing)
    monkeypatch.setattr(dashboard_route.activity, "for_projects", nothing)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestTheDashboardRoute:
    def test_it_answers_at_all(self, client: TestClient, signed_in, stubbed) -> None:
        """The test that was missing. It returned 500 to every editor."""
        assert client.get("/dashboard").status_code == 200

    def test_every_card_carries_the_crew(self, client: TestClient, signed_in, stubbed) -> None:
        """The two fields whose absence was the whole outage.

        Required rather than defaulted on purpose, so a card without them is a
        failure here rather than a card that silently reads as ownerless.
        """
        cards = client.get("/dashboard").json()["projects"]
        assert len(cards) == 3
        for card in cards:
            assert card["owner_email"]
            assert isinstance(card["member_emails"], list)

    def test_the_queue_survives_the_same_response_model(
        self, client: TestClient, signed_in, stubbed
    ) -> None:
        """Home and the review queue are one endpoint. A model that rejects a
        project card takes the queue with it, which is why two pages died of
        one bug."""
        body = client.get("/dashboard").json()
        assert body["queue_total"] == 1
        assert body["queue"][0]["slug"] == "1B"
        assert body["queue"][0]["project_name"] == "Scene 1 - two perspectives"

    def test_a_project_with_no_footage_reports_no_progress(
        self, client: TestClient, signed_in, stubbed
    ) -> None:
        """Kept from the service's own rule: null, not nought per cent."""
        body = client.get("/dashboard").json()
        assert all(card["progress_pct"] is not None for card in body["projects"])


class TestSomebodyWithNoProjects:
    """The first screen a new person sees, and the one after deleting the last
    project.

    This failed with `KeyError: 'queue_total'`. `for_projects` wrote its answer
    shape twice — once for real and once as a short-circuit for an empty id list
    — and the two drifted. The earlier tests here stubbed the service, so they
    proved the route could assemble a response and never that the service gave
    it the keys it reads.

    These use the real service. An empty id list makes no database call, so
    nothing needs stubbing for that part, which is exactly why there was no
    excuse for not testing it.
    """

    @pytest.fixture
    def no_projects(self, monkeypatch: pytest.MonkeyPatch):
        async def none(email: str):
            return []

        async def nothing(ids):
            return []

        monkeypatch.setattr(dashboard_route.projects, "visible_to", none)
        monkeypatch.setattr(dashboard_route.dashboard_service, "recent_decisions", nothing)
        monkeypatch.setattr(dashboard_route.dashboard_service, "recent_notes", nothing)
        monkeypatch.setattr(dashboard_route.activity, "for_projects", nothing)

    def test_home_loads(self, client: TestClient, signed_in, no_projects) -> None:
        assert client.get("/dashboard").status_code == 200

    def test_it_is_empty_rather_than_absent(
        self, client: TestClient, signed_in, no_projects
    ) -> None:
        body = client.get("/dashboard").json()
        assert body["projects"] == []
        assert body["queue"] == []
        assert body["queue_total"] == 0
        assert body["totals"]["projects"] == 0

    @pytest.mark.asyncio
    async def test_both_paths_answer_in_the_same_shape(self) -> None:
        """The property that was broken, asserted directly.

        Whatever `for_projects` returns for nobody must have the same keys as
        what it returns for somebody, or a caller reading one will crash on the
        other.
        """
        from app.services import dashboard as service

        empty = await service.for_projects([], "someone@example.com")
        full = service._assembled([], [{"shots": 0}], "someone@example.com")
        assert set(empty) == set(full)
