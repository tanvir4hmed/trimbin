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
    def __init__(self, coverage_segments: list | None = None) -> None:
        self.rev = 3
        # The real `Shot` carries these; the screen reads chosen ranges off the
        # shot now rather than out of a comparison that may not exist.
        self.coverage_segments = coverage_segments or []

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

    async def takes_in_shot(project_id, scene, shot):
        """No footage. The shot screen reads the shot's takes directly now, so a
        stub that omitted this reached for ClickHouse and answered 503."""
        return []

    async def stages(project_id, clip_ids):
        """Pipeline state, which is a Firestore read like every other store
        here and has to be stubbed for the same reason."""
        return {}

    monkeypatch.setattr(screens.review_routes, "tree", tree)
    monkeypatch.setattr(screens.review_routes, "verdicts", verdicts)
    monkeypatch.setattr(screens.review_routes.review_service, "takes_in_shot", takes_in_shot)
    monkeypatch.setattr(screens.structure, "for_project", plan)
    monkeypatch.setattr(screens.projects, "get", project)
    monkeypatch.setattr(screens.shots, "get", shot)
    monkeypatch.setattr(screens.comments_service, "for_shot", comments)
    monkeypatch.setattr("app.services.jobs.analysis_states", stages)


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


class TestAShotWithOneTake:
    """Footage exists before a comparison does.

    An editor uploaded one clip into a new project, the proxy built, the
    analysis ran — and the cockpit drew "No takes have been compared for this
    shot yet" with no player. The takes were read out of the verdicts, and a
    comparison needs two takes, so a shot holding one had nothing to draw.

    The proxy was healthy the entire time. `/media/.../index.m3u8` answered 200
    with the right content type and its segments played; nothing ever asked for
    them.
    """

    @pytest.fixture
    def one_take(self, monkeypatch: pytest.MonkeyPatch, stubbed):
        async def takes_in_shot(project_id, scene, shot):
            return [
                {
                    "clip_id": "62469df0-9ca9-465c-b345-a709080552c1",
                    "take_no": 1,
                    "outcome": "",
                    "score": 0.0,
                    "margin": 0.0,
                    "reason": "",
                    "reason_code": "",
                    "findings": [],
                    "usable_from_s": 0.0,
                    "usable_to_s": 59.6,
                    "decided_by": "",
                    "actor": "",
                    "model_id": "",
                    "prompt_version": "",
                    "panel_convened": False,
                    "decided_at": None,
                    "proxy_uri": "/media/p6/62469df0/proxy/index.m3u8",
                    "sprite_uri": "/media/p6/62469df0/sprite.jpg",
                    "criteria": {},
                    "safe_ranges": [{"start_s": 0.0, "end_s": 59.6}],
                    "trim_reasons": [],
                    "duration_s": 59.6,
                    "camera": "",
                    "captured_at": None,
                    "fps": 25.0,
                    "scene_code": "",
                    "shot_code": "",
                }
            ]

        async def read(project_id, clip_id):
            return {
                "project_id": project_id,
                "clip_id": str(clip_id),
                "clip": {
                    "scene": 12,
                    "shot": 1,
                    "take_no": 1,
                    "duration_s": 59.6,
                    "proxy_uri": "/media/p6/62469df0/proxy/index.m3u8",
                    "sprite_uri": "/media/p6/62469df0/sprite.jpg",
                    "fps": 25.0,
                    "scene_code": "",
                    "shot_code": "",
                },
                "run": None,
                "status": "current",
                "coverage_complete": True,
                "description": "",
                "segments": [],
                "findings": [],
                "history": [],
                "safe_ranges": [],
                "primary_usable_range": None,
            }

        monkeypatch.setattr(screens.review_routes.review_service, "takes_in_shot", takes_in_shot)
        monkeypatch.setattr(screens.analysis_routes, "_read", read)

    def test_the_take_is_there_to_play(self, client: TestClient, one_take) -> None:
        body = client.get("/screens/shot/1/12/1").json()
        assert len(body["takes"]) == 1
        assert body["takes"][0]["proxy_uri"].endswith(".m3u8")

    def test_the_verdicts_are_still_null(self, client: TestClient, one_take) -> None:
        """Nothing was compared, and the screen says so rather than inventing a
        recommendation for a field of one."""
        body = client.get("/screens/shot/1/12/1").json()
        assert body["verdicts"] is None

    def test_the_whole_clip_is_selectable(self, client: TestClient, one_take) -> None:
        """No judgement has called any part of it unusable, so the range an
        editor trims from is the full duration."""
        take = client.get("/screens/shot/1/12/1").json()["takes"][0]
        assert take["usable_from_s"] == 0.0
        assert take["usable_to_s"] == take["duration_s"]

    def test_its_analysis_is_loaded_too(self, client: TestClient, one_take) -> None:
        """Analysis is per clip and never needed a comparison. It was skipped
        only because the loop ran over the verdicts."""
        body = client.get("/screens/shot/1/12/1").json()
        assert len(body["analyses"]) == 1


class TestTheTreeAgreesWithTheReel:
    """One shot, one answer.

    The column said "Everything is decided", the cockpit said "Human decision
    required" and the scene page said one shot needed a decision — about the
    same shot. The tree worked it out from comparison status and `chosen_take`,
    and `chosen_take` is not the question: a shot holding one take reports 1
    whether or not a human ever chose anything.

    The reel counts a shot with no coverage segments as a GAP. The tree now
    reports that same count, so the two cannot drift.
    """

    def test_a_shot_with_no_chosen_ranges_reports_none(self) -> None:
        from app.schemas import ShotNode

        node = ShotNode(
            shot=1,
            slug="1A",
            label="",
            takes=1,
            unusable=0,
            status="too_few_takes",
            state="",
            assignee="",
            circled_take=0,
            chosen_take=1,
            differs_from_circle=False,
            margin=0.0,
            cameras=[],
            shoot_day="",
            open_notes=0,
        )
        # Defaulted, because a tree built before this field existed must not
        # start claiming shots are resolved.
        assert node.segments == 0

    def test_chosen_take_is_not_the_signal(self) -> None:
        """The exact shape of the live bug: one take, chosen_take 1, nothing
        actually selected."""
        from app.schemas import ShotNode

        node = ShotNode(
            shot=1,
            slug="1A",
            label="",
            takes=1,
            unusable=0,
            status="too_few_takes",
            state="",
            assignee="",
            circled_take=0,
            chosen_take=1,
            differs_from_circle=False,
            margin=0.0,
            cameras=[],
            shoot_day="",
            open_notes=0,
            segments=0,
        )
        assert node.chosen_take == 1
        assert node.segments == 0


class TestChosenRangesSurviveWithoutAComparison:
    """The bug an editor hit: add ranges, save, refresh, and they are gone.

    They were never gone. `commit_coverage` writes them to the shot in
    Firestore and does not care whether anything has been compared — but the
    screen only ever returned them nested inside `verdicts`, and `verdicts` is
    null until a comparison runs. A comparison needs two takes. So on a
    one-take shot the ranges saved correctly, came back unread, and the tray
    redrew itself empty.

    The same omission as the takes and the analyses before it: three things
    that belong to the shot, read out of the one object that is allowed to not
    exist.
    """

    @pytest.fixture
    def with_saved_ranges(self, monkeypatch: pytest.MonkeyPatch, stubbed):
        clip = "62469df0-9ca9-465c-b345-a709080552c1"

        async def shot(project_id, scene, shot):
            return FakeShot(
                coverage_segments=[
                    {
                        "segment_id": "a3f1c2d4-0000-4000-8000-000000000001",
                        "clip_id": clip,
                        "take_no": 1,
                        "source_in_s": 4.0,
                        "source_out_s": 11.0,
                        "position": 0,
                        "reason": "better performance",
                        "created_by": "editor@example.com",
                    },
                    {
                        "segment_id": "a3f1c2d4-0000-4000-8000-000000000002",
                        "clip_id": clip,
                        "take_no": 1,
                        "source_in_s": 17.0,
                        "source_out_s": 25.0,
                        "position": 1,
                        "reason": "better performance",
                        "created_by": "editor@example.com",
                    },
                ]
            )

        monkeypatch.setattr(screens.shots, "get", shot)

    def test_they_come_back_on_an_uncompared_shot(
        self, client: TestClient, with_saved_ranges
    ) -> None:
        body = client.get("/screens/shot/1/12/1").json()
        assert body["verdicts"] is None
        assert len(body["coverage_segments"]) == 2

    def test_their_order_is_preserved(self, client: TestClient, with_saved_ranges) -> None:
        """Two ranges from one take, and which comes first is a decision
        somebody made — not something to re-derive from the timecodes."""
        segments = client.get("/screens/shot/1/12/1").json()["coverage_segments"]
        assert [s["position"] for s in segments] == [0, 1]
        assert segments[0]["source_in_s"] == 4.0
        assert segments[1]["source_in_s"] == 17.0

    def test_a_shot_with_none_reports_an_empty_list(self, client: TestClient, stubbed) -> None:
        """Empty, never absent — the same rule the crew fields follow."""
        body = client.get("/screens/shot/1/12/1").json()
        assert body["coverage_segments"] == []
