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


class TestP01GuestEntryOpensAProduct:
    """Guest login succeeded and the project list came back empty. The demo was
    one id in config — `demo_project_id = 1` — and project 1 had been deleted,
    so a judge clicking "Try it as a guest" reached an empty application.

    A demo that depends on one row surviving forever is a fuse, not a demo. It
    is a rule now: the team's own active productions are open to readers.
    """

    def test_the_team_s_work_is_open_to_readers(self) -> None:
        from app.services import members, projects

        class P:
            state = "active"
            is_public = False
            owner_email = members.LEAD_EDITOR

        assert projects.open_to_readers(P()) is True

    def test_a_deleted_project_is_open_to_nobody(self) -> None:
        """The exact failure. A removed production must not be the thing a
        visitor is sent to."""
        from app.services import members, projects

        class P:
            state = "deleted"
            is_public = True
            owner_email = members.LEAD_EDITOR

        assert projects.open_to_readers(P()) is False

    def test_a_guest_owned_project_stays_private(self) -> None:
        """ "Everyone sees the team's work" must not become "everyone sees
        everyone's work". A guest's own production is theirs until they publish
        it."""
        from app.services import projects

        class P:
            state = "active"
            is_public = False
            owner_email = "someone@guest.trimbin"

        assert projects.open_to_readers(P()) is False

    def test_a_guest_who_publishes_is_readable(self) -> None:
        from app.services import projects

        class P:
            state = "active"
            is_public = True
            owner_email = "someone@guest.trimbin"

        assert projects.open_to_readers(P()) is True

    def test_nothing_is_open(self) -> None:
        from app.services import projects

        assert projects.open_to_readers(None) is False

    def test_no_hardcoded_demo_id_decides_access(self) -> None:
        """The mechanism that broke. If an id ever gates read access again, it
        can point at a project somebody deletes."""
        from pathlib import Path

        auth_source = (Path(__file__).parents[1] / "app" / "auth.py").read_text(encoding="utf-8")
        code = chr(10).join(
            line for line in auth_source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "demo_project_id" not in code


class TestTheClientCanDoTheWork:
    """Trimbin is one company's tool. The guest role is the client, reviewing
    alongside the editors — not a stranger on a tour.

    So on any production open to readers a client compares, judges, curates and
    uploads exactly as an editor does. The one thing they may not do is destroy
    the editors' material, and that is a per-record rule rather than a
    project-wide capability.
    """

    @pytest.mark.asyncio
    async def test_a_client_may_curate_and_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app import auth
        from app.services import members

        class Readable:
            project_id = 7
            owner_email = members.LEAD_EDITOR
            member_emails: list[str] = []
            is_public = False
            state = "active"
            rev = 0

        async def readable(project_id: int, **kwargs):
            return Readable()

        monkeypatch.setattr(auth.projects, "get", readable)
        client = auth.Principal(email="client@example.com")
        await client.assert_can_read(7)
        await client.assert_can_comment(7)
        await client.assert_can_curate(7)
        await client.assert_can_upload(7)

    def test_the_editors_footage_stays_protected(self) -> None:
        """The boundary that remains. A guest removes only what they uploaded,
        enforced on the record rather than on the project."""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "routes" / "clips.py").read_text(
            encoding="utf-8"
        )
        assert 'members.role_of(principal.email) == "guest"' in source
        assert 'found["uploaded_by"]' in source


class TestP07SearchLandsOnTheEvent:
    """A search for `off-camera voice calls cut` matched a take at 00:52 when
    the thing asked for happens at 01:23 — thirty-one seconds early, because
    the stored spans were the 60-second analysis windows rather than the
    events inside them.

    Moments are stored separately now, the query prefers the tightest one, and
    playback gets a run-up without the archive overstating how long the moment
    was.
    """

    def test_the_moment_query_prefers_the_tightest_span(self) -> None:
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "search.py").read_text(
            encoding="utf-8"
        )
        assert "(m.end_s - m.start_s)" in source, (
            "moments are no longer ordered shortest-first, so a long window can "
            "outrank the event inside it again"
        )

    def test_playback_starts_before_the_moment(self) -> None:
        from app.routes.ask import PLAYBACK_PREROLL_S, _as_match

        match = _as_match(
            {
                "clip_id": "62469df0-9ca9-465c-b345-a709080552c1",
                "scene": 1,
                "setup": 2,
                "take_no": 4,
                "duration_s": 85.96,
                "finding_starts_s": [83.2],
                "usable_to_s": 85.0,
                "finding_codes": ["moment.dialogue"],
                "outcome": "analysed",
                "reason": "he calls cut",
                "reason_code": "moment.dialogue",
                "decided_by": "",
                "proxy_uri": "",
                "relevance": 0.9,
            }
        )
        assert match.play_from_s == 83.2 - PLAYBACK_PREROLL_S

    def test_the_reported_span_is_not_widened(self) -> None:
        """The run-up is a seek, not a claim. Widening `where` would make the
        archive report a moment as longer than it was."""
        from app.routes.ask import _as_match

        match = _as_match(
            {
                "clip_id": "62469df0-9ca9-465c-b345-a709080552c1",
                "scene": 1,
                "setup": 2,
                "take_no": 4,
                "duration_s": 85.96,
                "finding_starts_s": [83.2],
                "usable_to_s": 85.0,
                "finding_codes": ["moment.dialogue"],
                "outcome": "analysed",
                "reason": "he calls cut",
                "reason_code": "moment.dialogue",
                "decided_by": "",
                "proxy_uri": "",
                "relevance": 0.9,
            }
        )
        assert match.where is not None
        assert match.where.start_s == 83.2

    def test_a_moment_at_the_very_start_does_not_seek_negative(self) -> None:
        from app.routes.ask import _as_match

        match = _as_match(
            {
                "clip_id": "62469df0-9ca9-465c-b345-a709080552c1",
                "scene": 1,
                "setup": 2,
                "take_no": 1,
                "duration_s": 30.0,
                "finding_starts_s": [0.4],
                "usable_to_s": 2.0,
                "finding_codes": ["moment.action"],
                "outcome": "analysed",
                "reason": "she enters",
                "reason_code": "moment.action",
                "decided_by": "",
                "proxy_uri": "",
                "relevance": 0.5,
            }
        )
        assert match.play_from_s == 0.0

    # The other half of this blocker — that the interface does not attribute an
    # absent decision to anybody — is `web/tests/ask.test.ts`. It called this
    # file's grep for the string "by the panel", which proves the source does
    # not contain a phrase, not that the five states are distinguished. That
    # rule is a pure function; it is now run rather than read.


class TestD3IngestIsRecoverable:
    """An interrupted batch has to be resumable, a cancelled one has to leave
    nothing behind, and every stage in between has to be visible.

    The QA found the middle of that pipeline silent: bytes reached storage and
    then the interface said nothing for minutes while the worker measured,
    read the slate and encoded a proxy.
    """

    def test_the_worker_reports_every_stage(self) -> None:
        """A stage nobody records is a minute the interface cannot explain."""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "worker" / "ingest.py").read_text(
            encoding="utf-8"
        )
        for stage in ("downloading", "measuring", "reading_slate", "encoding_proxy"):
            assert f'"{stage}"' in source, f"the {stage} stage is no longer reported"

    def test_cancelling_settles_nothing(self) -> None:
        """The gate: cancel a file mid-batch and no clip enters the project.

        It holds because placement is only canonical once a human commits —
        an abandoned job never calls the settlement command, so its clips never
        reach `current_clip_placement`.
        """
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "routes" / "uploads.py").read_text(
            encoding="utf-8"
        )
        cancel = source[
            source.index("async def cancel_ingest") : source.index("/jobs/{job_id}/commit")
        ]
        assert "jobs.abandon" in cancel
        assert "settlement.settle" not in cancel
        assert "placements." not in cancel

    def test_cancelling_deletes_no_bytes(self) -> None:
        """Deliberately. Somebody who uploaded forty gigabytes and cancelled the
        forty-first file has not asked us to throw the forty away."""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "routes" / "uploads.py").read_text(
            encoding="utf-8"
        )
        cancel = source[
            source.index("async def cancel_ingest") : source.index("/jobs/{job_id}/commit")
        ]
        assert "storage.delete" not in cancel
        assert "without deleting any bytes" in cancel

    def test_ingest_activity_is_a_typed_verb(self) -> None:
        """The QA found ingest commits missing from the activity feed. An
        unlisted verb is rejected by `activity.record`, so a typo silently
        drops the event rather than failing loudly."""
        from app.services import activity

        assert "ingest_committed" in activity.VERBS

    def test_the_inbox_polls_before_it_has_rows(self) -> None:
        """It polled only while something was already waiting, so the first row
        a worker produced never arrived — the screen had stopped asking."""
        from pathlib import Path

        for name in ("PlacementInbox.tsx", "PlacementBanner.tsx"):
            source = (Path(__file__).parents[2] / "web" / "components" / name).read_text(
                encoding="utf-8"
            )
            assert "refetchInterval: 8000" in source, f"{name} stopped polling unconditionally"


class TestD3ResumeMatchesTheRightFiles:
    """A browser cannot hand a page back its file bytes after a reload, so
    resuming means asking somebody to reselect the same footage. Which makes
    "is this the same footage" a correctness question: resuming a session with
    a different file of the same name writes the wrong bytes into an object
    somebody is waiting on.
    """

    # The fingerprint rule itself — order independence, duplicate counting,
    # rejecting different bytes behind the same filename — is
    # `web/tests/upload.test.ts`, which calls `matches()` with real batches.
    # It was three greps here for a type alias and a function name, neither of
    # which can tell a working comparison from a broken one.

    def test_a_mismatch_is_stated_rather_than_started_over(self) -> None:
        """A copy assertion, and only that: it pins the sentence a person sees
        when the batch does not match. The comparison behind it is tested in
        `web/tests/upload.test.ts`."""
        from pathlib import Path

        source = (Path(__file__).parents[2] / "web" / "components" / "Upload.tsx").read_text(
            encoding="utf-8"
        )
        assert "These are not the files that batch was uploading" in source


class TestD4TheShellHasNoDeadControls:
    """A control that does nothing teaches people not to trust the ones that
    do. The QA found a notification button that opened nothing.
    """

    def test_the_notification_button_is_gone(self) -> None:
        from pathlib import Path

        source = (Path(__file__).parents[2] / "web" / "components" / "AppShell.tsx").read_text(
            encoding="utf-8"
        )
        assert 'aria-label="Notifications"' not in source

    def test_there_is_a_favicon(self) -> None:
        """A browser tab with the default document icon reads as something
        half-built, whatever is on the page."""
        from pathlib import Path

        assert (Path(__file__).parents[2] / "web" / "app" / "icon.svg").exists()

    def test_the_structure_fields_are_named(self) -> None:
        """Four inputs with no accessible name, and two pairs a sighted person
        could not tell apart either: which box is the code on the board, and
        which is the slugline from the script?"""
        from pathlib import Path

        source = (Path(__file__).parents[2] / "web" / "components" / "Structure.tsx").read_text(
            encoding="utf-8"
        )
        for label in (
            "Scene code, as written on the slate",
            "Scene heading, from the script",
            "Shot code, as written on the slate",
            "What the shot is",
        ):
            assert label in source, f"missing accessible name: {label}"


class TestD4SceneCoverageCountsShots:
    """A shot with four ranges is one shot. The QA found the scene header
    counting the flattened range list, so choosing more coverage for a shot
    made the scene look less complete.
    """

    def test_the_header_counts_shots(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).parents[2]
            / "web"
            / "app"
            / "projects"
            / "[slug]"
            / "scenes"
            / "[scene]"
            / "coverage"
            / "page.tsx"
        ).read_text(encoding="utf-8")
        assert "{selectedShots.length}/{data.shots} shots confirmed" in source

    def test_transport_moves_between_shots(self) -> None:
        """Previous/Next used to step through source parts, so a shot with four
        ranges took four presses to leave."""
        from pathlib import Path

        source = (
            Path(__file__).parents[2]
            / "web"
            / "app"
            / "projects"
            / "[slug]"
            / "scenes"
            / "[scene]"
            / "coverage"
            / "page.tsx"
        ).read_text(encoding="utf-8")
        assert "moveShot(-1)" in source and "moveShot(1)" in source

    def test_the_scene_contract_carries_ranges_per_shot(self) -> None:
        from app.schemas import CoverageItem

        assert "entries" in CoverageItem.model_fields
        assert "kind" in CoverageItem.model_fields


class TestD5PerformanceIsNeverScored:
    """The line the whole product is built around: this system measures what a
    camera can be measured on and never judges a performance.

    A weight quietly added for `performance.note` would move a ranking without
    anybody deciding to, which is exactly the overreach the boundary forbids.
    So the tables are asserted rather than trusted.
    """

    def test_performance_carries_no_weight(self) -> None:
        from app.services import criteria

        for name, table in vars(criteria).items():
            if not isinstance(table, dict) or not name.isupper():
                continue
            assert "performance.note" not in table, (
                f"{name} scores performance, which the product boundary forbids"
            )

    def test_an_unnamed_observation_carries_no_weight_either(self) -> None:
        """`other` is something the model could not name. Scoring it is scoring
        a guess."""
        from app.services import criteria

        for name, table in vars(criteria).items():
            if not isinstance(table, dict) or not name.isupper():
                continue
            assert "other" not in table, f"{name} scores an unnamed observation"

    def test_the_analyst_is_told_it_is_not_judging_performance(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).parents[2] / "agents" / "trimbin_agents" / "analyst" / "agent.py"
        ).read_text(encoding="utf-8")
        assert "not a judgement of performance" in source


class TestD5FindingsAreReviewable:
    """A take with fourteen shake findings is a take nobody reviews. Each one
    described part of the same camera bump.
    """

    def test_a_settling_camera_is_one_finding(self) -> None:
        from app.services.clips import _events

        class Span:
            def __init__(self, a, b):
                self.start_s, self.end_s = a, b

        spans = [Span(1.0, 1.4), Span(1.6, 2.0), Span(2.3, 2.7), Span(2.9, 3.2)]
        assert _events(spans) == [(1.0, 3.2)]

    def test_separate_events_survive(self) -> None:
        """Merging that swallowed distinct knocks would trade one unusable
        screen for a dishonest one."""
        from app.services.clips import _events

        class Span:
            def __init__(self, a, b):
                self.start_s, self.end_s = a, b

        assert _events([Span(1.0, 1.5), Span(12.0, 12.5)]) == [(1.0, 1.5), (12.0, 12.5)]

    def test_nothing_is_discarded(self) -> None:
        """Merged, never dropped. A brief shake is still evidence an editor may
        want; what they cannot use is the same shake fourteen times."""
        from app.services.clips import _events

        class Span:
            def __init__(self, a, b):
                self.start_s, self.end_s = a, b

        merged = _events([Span(1.0, 1.4), Span(1.6, 2.0)])
        assert merged[0][0] == 1.0 and merged[0][1] == 2.0

    def test_the_post_cut_break_can_end_a_usable_range(self) -> None:
        """Take 4's suggested range ran past the point the actors broke after
        "Cut". The taxonomy has a code for it and the range builder uses it."""
        from pathlib import Path

        from trimbin_agents.contracts.base import FindingCode

        assert FindingCode.ACTION_POST_ROLL == "action.post_roll"
        source = (Path(__file__).parents[1] / "app" / "services" / "ranges.py").read_text(
            encoding="utf-8"
        )
        assert "action.post_roll" in source


class TestEveryHasDecisionReferenceHasAColumnBehindIt:
    """`has_decision` only exists inside a `latest_decision` CTE.

    The guard that stops a LEFT JOIN inventing an outcome was added to the
    query that reads `FROM decisions AS d` as well, where `d` is the table and
    the column does not exist. ClickHouse rejected the whole statement and
    archive search returned 503 in production — while every unit test passed,
    because the sibling test below counts guards in the SELECT list and this
    one was in the WHERE clause.

    So: every query that mentions `has_decision` must also define it.
    """

    @staticmethod
    def _statements() -> list[str]:
        """The source split into per-query chunks.

        `WITH latest_decision AS` opens each guarded query, so splitting on it
        puts a query's definition and its references in the same chunk. The
        first chunk is everything before any CTE — which is exactly where the
        production failure lived.
        """
        from pathlib import Path

        source = (Path(__file__).parents[1] / "app" / "services" / "search.py").read_text(
            encoding="utf-8"
        )
        # Comments explain the rule and naturally name the column, so they are
        # stripped before it is applied. This assertion is about SQL.
        code = chr(10).join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        return code.split("WITH latest_decision AS")

    def test_no_query_references_a_column_it_never_defines(self) -> None:
        for chunk in self._statements():
            if "has_decision" not in chunk:
                continue
            assert "toUInt8(1) AS has_decision" in chunk, (
                "a query references has_decision without a latest_decision CTE "
                "defining it; ClickHouse will reject the whole statement"
            )

    def test_the_direct_read_stays_unguarded(self) -> None:
        """Reading `FROM decisions AS d` cannot produce an absent row, so the
        guard is not merely invalid there — it is unnecessary."""
        before_any_cte = self._statements()[0]

        assert "FROM decisions AS d" in before_any_cte
        assert "has_decision" not in before_any_cte
