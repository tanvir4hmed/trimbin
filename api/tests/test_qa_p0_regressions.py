"""The production QA's release blockers, pinned so they cannot come back.

Seven P0 findings were raised against the deployed build on 2026-09-03. Six of
them already have repairs on this tree; this file is what makes that claim
checkable rather than asserted, and what stops the next refactor undoing them
quietly.

The fix plan asked for these as *failing* tests written before the repair. That
order was not available: the repairs were already on the working tree when the
plan arrived, so a "failing" test for P0.6 would have passed the moment it was
written and proved nothing. They are written as verification tests instead —
same defects, same evidence, honest about when they were added.

P0.1 has no test here on purpose. "Guest login opens an empty product" is not a
code defect: `demo_project_id` points at project 1 and project 1 was deleted.
No assertion about this repository can fix or detect that; it needs a public
project to exist. It is tracked in the D0 report, not pretended about here.
"""

from __future__ import annotations

import pytest

from app.services import assessment
from app.services.structure import _normalise_code, resolve_codes


class Shot:
    def __init__(self, shot: int, slug: str = "") -> None:
        self.shot = shot
        self.slug = slug


class Scene:
    def __init__(self, scene: int, scene_code: str, shots: list[Shot]) -> None:
        self.scene = scene
        self.scene_code = scene_code
        self.shots = shots


class TestP02SlateCodesResolveAgainstThePlan:
    """`SCENE 3` became internal scene `300`, and the project stored scene 3 as
    `3`, so automatic slate matching could not work at all. The reader used a
    sortable ordinal as if it were a durable id.

    Codes are production names now, matched against declared structure.
    """

    @pytest.mark.asyncio
    async def test_a_plain_number_matches_the_planned_scene(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def plan(project_id):
            return [Scene(3, "3", [Shot(1, "3A")])]

        monkeypatch.setattr("app.services.structure.for_project", plan)
        assert await resolve_codes(1, "3", "3A") == (3, 1)

    @pytest.mark.asyncio
    async def test_it_never_multiplies_a_code_into_an_ordinal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact shape of the bug: 3 must not become 300."""

        async def plan(project_id):
            return [Scene(3, "3", [Shot(1, "3A")])]

        monkeypatch.setattr("app.services.structure.for_project", plan)
        scene, _ = await resolve_codes(1, "3", "3A")
        assert scene == 3
        assert scene != 300

    @pytest.mark.asyncio
    async def test_a_string_code_survives_as_itself(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`12A-PU` and `A012C` are ordinary slate codes. The plan froze them as
        strings; nothing may turn them into numbers."""

        async def plan(project_id):
            return [Scene(12, "A012C", [Shot(2, "12A-PU")])]

        monkeypatch.setattr("app.services.structure.for_project", plan)
        assert await resolve_codes(1, "A012C", "12A-PU") == (12, 2)

    @pytest.mark.asyncio
    async def test_an_unknown_code_invents_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zero means "ask a person", which is the whole point. Guessing a
        scene into existence is the failure that scatters a shoot day."""

        async def plan(project_id):
            return [Scene(3, "3", [Shot(1, "3A")])]

        monkeypatch.setattr("app.services.structure.for_project", plan)
        assert await resolve_codes(1, "99", "99Z") == (0, 0)

    @pytest.mark.asyncio
    async def test_an_ambiguous_shot_stops_at_the_scene(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scene with two shots and no shot on the board resolves the scene
        and leaves the shot for verification."""

        async def plan(project_id):
            return [Scene(3, "3", [Shot(1, "3A"), Shot(2, "3B")])]

        monkeypatch.setattr("app.services.structure.for_project", plan)
        assert await resolve_codes(1, "3", "") == (3, 0)

    def test_codes_compare_without_changing_what_is_displayed(self) -> None:
        """Matching ignores punctuation and case; the code an editor typed is
        still the code they see."""
        assert _normalise_code(" 12a-pu ") == _normalise_code("12A_PU") == "12APU"


class TestP04NewFootageReopensADecision:
    """Scene 3 / Shot 1 stayed *confirmed* and the dashboard said "Everything
    decided" after Take 4 arrived — a decision made about three takes silently
    remaining authoritative over four.

    A decision now records the evidence set it reviewed.
    """

    def test_the_same_takes_hash_the_same(self) -> None:
        assert assessment.source_set_hash(["b", "a"]) == assessment.source_set_hash(["a", "b"])

    def test_a_new_take_changes_the_hash(self) -> None:
        """This is what reopens the shot. If adding a take left the hash alone,
        nothing downstream could notice the evidence had changed."""
        before = assessment.source_set_hash(["a", "b"])
        assert assessment.source_set_hash(["a", "b", "c"]) != before

    def test_a_removed_take_changes_the_hash_too(self) -> None:
        before = assessment.source_set_hash(["a", "b", "c"])
        assert assessment.source_set_hash(["a", "b"]) != before

    def test_no_evidence_is_not_a_hash(self) -> None:
        """Empty must not collide with a real set, or a shot with no footage
        would look like a shot whose decision is current."""
        assert assessment.source_set_hash([]) == ""
        assert assessment.source_set_hash(["a"]) != ""

    def test_blank_ids_do_not_shift_the_evidence(self) -> None:
        assert assessment.source_set_hash(["a", "", "b"]) == assessment.source_set_hash(["a", "b"])


class TestP05SearchNeverInventsADecision:
    """`off-camera voice calls cut` returned Take 4 as "selected / by the
    panel". There was no decision row for Take 4 at all.

    A ClickHouse LEFT JOIN with `join_use_nulls=0` gives a missing right-side
    Enum its *first value* rather than NULL, and the first value of the outcome
    Enum is `selected`. `ifNull(outcome, 'analysed')` therefore never fired:
    the column was never null. The archive fabricated editorial history.

    The query now carries an explicit `has_decision` flag, so absence is read
    from a column that cannot be defaulted into a lie.
    """

    def test_the_query_tests_a_flag_rather_than_a_null(self) -> None:
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "search.py").read_text(
            encoding="utf-8"
        )
        assert "has_decision" in source, "the explicit-presence flag is gone"
        assert "ifNull(d.outcome" not in source, (
            "ifNull on a joined Enum cannot detect a missing row under join_use_nulls=0"
        )

    def test_every_left_joined_decision_is_guarded(self) -> None:
        """Only a LEFT JOIN can produce the defaulted Enum. Reading `outcome`
        straight from `decisions`, or aggregating it inside a subquery over
        that table, sees real rows by construction and needs no guard — so the
        invariant is one guard per LEFT JOIN, not one per projection.

        My first version of this test counted every `AS outcome` and reported
        five unguarded. All five read from `decisions` directly. The assertion
        was wrong, not the query."""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "search.py").read_text(
            encoding="utf-8"
        )
        joins = source.count("LEFT JOIN latest_decision AS d")
        guarded = source.count(
            "if(d.has_decision = 1, toString(d.outcome), 'analysed') AS outcome,"
        )
        assert joins > 0, "the joined-decision shape is gone; this test needs rewriting"
        assert joins == guarded, f"{joins - guarded} LEFT JOIN(ed) decision(s) unguarded"


class TestP06UnassignedIsNotSceneZero:
    """ "Leave unassigned" filed footage canonically under Scene 0 / Shot 0. It
    then appeared in the tree, the review queue, search and take counts, while
    the wizard said every clip was organised.

    Unassigned is a state now, with its own read model.
    """

    def test_the_migration_gives_unassigned_its_own_relation(self) -> None:
        from pathlib import Path

        sql = (
            Path(__file__).parents[2] / "clickhouse" / "migrations" / "024_explicit_unassigned.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE VIEW current_unassigned_clips" in sql

    def test_the_canonical_relation_is_rebuilt_alongside_it(self) -> None:
        """`current_clip_placement` is what every operational screen reads. If
        unassigned rows were not removed from it, a separate bin would just be
        a second place showing the same contamination."""
        from pathlib import Path

        sql = (
            Path(__file__).parents[2] / "clickhouse" / "migrations" / "024_explicit_unassigned.sql"
        ).read_text(encoding="utf-8")
        assert "DROP VIEW IF EXISTS current_clip_placement" in sql
        assert "CREATE VIEW current_clip_placement" in sql

    def test_the_service_reads_the_bin_rather_than_scene_zero(self) -> None:
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "placements.py").read_text(
            encoding="utf-8"
        )
        assert "current_unassigned_clips" in source


class TestP07SearchReturnsTheEventNotTheWindow:
    """A match landed at `00:52`, thirty-one seconds before the thing asked
    for, because the stored spans were the 60-second analysis windows.

    Moments are stored separately; windows stay as provenance.
    """

    def test_moments_have_their_own_table(self) -> None:
        from pathlib import Path

        sql = (
            Path(__file__).parents[2] / "clickhouse" / "migrations" / "025_clip_moments.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS clip_moments" in sql

    def test_semantic_search_runs_against_moments(self) -> None:
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "search.py").read_text(
            encoding="utf-8"
        )
        assert "_run_moments" in source, "semantic queries no longer reach the moment index"


class TestP03OnePathToSettlement:
    """Clips committed through the ingest wizard were queued for full-take
    analysis; clips settled later through the Placement Inbox were not. Whether
    a take ever got intelligence depended on which screen an editor used.

    Both later grew the enqueue call, but as two copies of a sequence that had
    to stay in step by hand — the same bug waiting for whoever edited one of
    them next. The sequence lives in one command now.
    """

    def test_both_routes_call_the_same_command(self) -> None:
        from pathlib import Path

        routes = Path(__file__).parents[1] / "app" / "routes"
        uploads = (routes / "uploads.py").read_text(encoding="utf-8")
        inbox = (routes / "placements.py").read_text(encoding="utf-8")
        assert "settlement.settle(" in uploads
        assert "settlement.settle(" in inbox

    def test_neither_route_reimplements_the_sequence(self) -> None:
        """A route that appends its own placement is a route that can forget
        the step after it."""
        from pathlib import Path

        routes = Path(__file__).parents[1] / "app" / "routes"
        uploads = (routes / "uploads.py").read_text(encoding="utf-8")
        assert "placements.resolve(" not in uploads
        assert "placements.unassign(" not in uploads

    @pytest.mark.asyncio
    async def test_settling_queues_analysis_for_the_clip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid

        from app.services import settlement

        clip = uuid.uuid4()
        queued: list = []

        async def noop(*args, **kwargs):
            return None

        async def candidates(project_id):
            return [{"clip_id": clip}]

        async def enqueue(project_id, rows):
            queued.extend(rows)
            return len(rows)

        monkeypatch.setattr(settlement.placements, "resolve", noop)
        monkeypatch.setattr(settlement.activity, "record", noop)
        monkeypatch.setattr(settlement.analysis_store, "active_clips_without_analysis", candidates)
        monkeypatch.setattr(settlement.jobs, "enqueue_analysis", enqueue)

        assert (
            await settlement.settle(
                project_id=1,
                clip_id=clip,
                scene=12,
                shot=1,
                take_no=2,
                actor="editor@example.com",
                detail="moved",
            )
            == 1
        )
        assert len(queued) == 1

    @pytest.mark.asyncio
    async def test_unassigned_footage_is_not_analysed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Analysing a clip nobody has claimed spends the model's budget on a
        question nobody asked."""
        import uuid

        from app.services import settlement

        async def noop(*args, **kwargs):
            return None

        async def explode(*args, **kwargs):
            raise AssertionError("unassigned footage must not be queued")

        monkeypatch.setattr(settlement.placements, "unassign", noop)
        monkeypatch.setattr(settlement.activity, "record", noop)
        monkeypatch.setattr(settlement.analysis_store, "active_clips_without_analysis", explode)

        assert (
            await settlement.settle(
                project_id=1,
                clip_id=uuid.uuid4(),
                scene=0,
                shot=0,
                take_no=0,
                actor="editor@example.com",
                detail="left unassigned",
                unassign=True,
            )
            == 0
        )

    @pytest.mark.asyncio
    async def test_settling_twice_queues_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Idempotent by construction: the queue is asked only for clips the
        archive says have no analysis, so a replayed commit finds none."""
        import uuid

        from app.services import settlement

        clip = uuid.uuid4()
        analysed: set[str] = set()

        async def noop(*args, **kwargs):
            return None

        async def candidates(project_id):
            return [] if str(clip) in analysed else [{"clip_id": clip}]

        async def enqueue(project_id, rows):
            analysed.update(str(row["clip_id"]) for row in rows)
            return len(rows)

        monkeypatch.setattr(settlement.placements, "resolve", noop)
        monkeypatch.setattr(settlement.activity, "record", noop)
        monkeypatch.setattr(settlement.analysis_store, "active_clips_without_analysis", candidates)
        monkeypatch.setattr(settlement.jobs, "enqueue_analysis", enqueue)

        first = await settlement.settle(
            project_id=1,
            clip_id=clip,
            scene=12,
            shot=1,
            take_no=2,
            actor="e@x.com",
            detail="moved",
        )
        second = await settlement.settle(
            project_id=1,
            clip_id=clip,
            scene=12,
            shot=1,
            take_no=2,
            actor="e@x.com",
            detail="moved again",
        )
        assert (first, second) == (1, 0)


class TestNoMutationInTheReviewPath:
    """`normalise_group` ran one `ALTER TABLE clips UPDATE` per shot from the
    hot path of every comparison. A ClickHouse mutation rewrites every part it
    touches and runs asynchronously; queueing them per row is the most reliable
    way to make this database behave badly.

    Removing it was a release gate, so it is removed rather than left unused.
    """

    def test_the_helper_is_gone(self) -> None:
        from app.services import clips

        assert not hasattr(clips, "normalise_group")

    def test_no_service_issues_a_clips_mutation(self) -> None:
        from pathlib import Path

        for path in (Path(__file__).parents[1] / "app" / "services").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            code = "\n".join(
                line for line in source.splitlines() if not line.lstrip().startswith("#")
            )
            assert "ALTER TABLE clips UPDATE" not in code, f"{path.name} mutates clips"
