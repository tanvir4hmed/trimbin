"""The screen read-models, actually called.

These endpoints shipped and returned a 500 on every request. `capabilities()`
already reports `signed_in` and `_me` passed it again — a duplicate keyword, so
`schemas.Me(...)` raised a TypeError before the route did anything. `/me` gets
away with the same duplication because it builds a dict, where a repeated key is
an overwrite rather than an error.

CI was green. Every existing test exercised services and pure functions; nothing
had ever *called* a screen route, so the assembly step — the only new code —
was the one thing untested.

So these tests call the endpoints through the app, with the stores stubbed. They
are not about the data. They are about the route being able to construct its own
response at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import screens
from app.services import members


class FakeProject:
    def __init__(self, project_id: int = 1, public: bool = True):
        self.project_id = project_id
        self.name = "Rain scene"
        self.owner_email = members.LEAD_EDITOR
        self.member_emails: list[str] = []
        self.is_public = public
        self.created_at = datetime.now(UTC)


class FakeShot:
    def __init__(self) -> None:
        self.rev = 3

    @property
    def is_empty(self) -> bool:
        return False

    def as_dict(self) -> dict:
        return {
            "scene": 12,
            "shot": 1,
            "slug": "12A",
            "heading": "INT. APARTMENT - NIGHT",
            "action": "",
            "line": "",
            "notes": "",
            "look": "",
            "circled_take": 0,
            "circled_by": "",
            "assignee": "",
            "state": "",
            "state_by": "",
            "state_at": None,
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": "",
            "rev": self.rev,
        }


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch):
    """Every store the screens read, answered without one."""

    async def tree(project_id, principal, **kwargs):
        return {
            "project_id": project_id,
            "scenes": [],
            "cameras": [],
            "shoot_days": [],
            "review_margin": 0.15,
        }

    async def plan(project_id):
        return []

    async def project(project_id):
        return FakeProject(project_id)

    async def shot(project_id, scene, shot):
        return FakeShot()

    async def comments(project_id, scene, shot):
        return []

    async def verdicts(project_id, scene, shot, principal):
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_404_NOT_FOUND, "No verdicts for this shot yet")

    monkeypatch.setattr(screens.review_routes, "tree", tree)
    monkeypatch.setattr(screens.review_routes, "verdicts", verdicts)
    monkeypatch.setattr(screens.structure, "for_project", plan)
    monkeypatch.setattr(screens.projects, "get", project)
    monkeypatch.setattr(screens.shots, "get", shot)
    monkeypatch.setattr(screens.comments_service, "for_shot", comments)


class TestTheProjectScreen:
    def test_it_answers_at_all(self, client: TestClient, stubbed) -> None:
        """The test that would have caught the TypeError."""
        assert client.get("/screens/project/1").status_code == 200

    def test_it_carries_all_four_parts(self, client: TestClient, stubbed) -> None:
        """The reason this endpoint exists. Four requests meant four loading
        states and four opinions about who you are, with the last to arrive
        winning."""
        body = client.get("/screens/project/1").json()
        assert set(body) == {"project", "tree", "plan", "me"}

    def test_a_stranger_gets_the_shape_with_the_crew_emptied(
        self, client: TestClient, stubbed
    ) -> None:
        """Emptied, never omitted. Omitting is what took the workspace down: the
        page spreads `member_emails`, and spreading undefined throws."""
        body = client.get("/screens/project/1").json()
        assert body["project"]["member_emails"] == []
        assert body["project"]["owner_email"] == ""
        assert body["project"]["you_can_upload"] is False

    def test_it_says_who_is_asking(self, client: TestClient, stubbed) -> None:
        body = client.get("/screens/project/1").json()
        assert body["me"]["signed_in"] is False
        assert body["me"]["role"] == "guest"


class TestTheShotScreen:
    def test_it_answers_at_all(self, client: TestClient, stubbed) -> None:
        assert client.get("/screens/shot/1/12/1").status_code == 200

    def test_an_uncompared_shot_is_null_verdicts_not_a_404(
        self, client: TestClient, stubbed
    ) -> None:
        """A shot nothing has compared is a normal state with an obvious next
        action. Returning 404 made the page catch an error and reinterpret it as
        "press compare", which is where an error message ended up on a screen
        whose only real news was that."""
        response = client.get("/screens/shot/1/12/1")
        assert response.status_code == 200
        assert response.json()["verdicts"] is None

    def test_the_brief_comes_back_with_its_revision(self, client: TestClient, stubbed) -> None:
        """Without it the interface cannot send back what it was shown, and
        every edit is a blind write again."""
        assert client.get("/screens/shot/1/12/1").json()["brief"]["rev"] == 3

    def test_the_notes_arrive_with_the_takes(self, client: TestClient, stubbed) -> None:
        """They used to be a second request, so they appeared a beat late."""
        body = client.get("/screens/shot/1/12/1").json()
        assert body["comments"] == []
        assert body["open_comments"] == 0


class TestEveryScreenRouteConstructsItsResponse:
    """The general form of the bug.

    A response model that a route cannot build is a 500 on every request, and no
    amount of service-level testing sees it. This walks the registered screen
    routes so a new one added without a test is still called once.
    """

    def test_all_of_them_answer(self, client: TestClient, stubbed) -> None:
        paths = {
            "/screens/project/{project_id}": "/screens/project/1",
            "/screens/shot/{project_id}/{scene}/{shot}": "/screens/shot/1/12/1",
        }
        # From the published schema, not from app.routes: FastAPI includes
        # routers lazily, so the router objects sit in app.routes with no path
        # of their own and the set comes back empty — which would make this
        # assertion pass by finding nothing.
        registered = {p for p in app.openapi()["paths"] if p.startswith("/screens")}
        assert registered == set(paths), (
            f"a screen route has no smoke test: {registered ^ set(paths)}"
        )
        for url in paths.values():
            assert client.get(url).status_code == 200, url
