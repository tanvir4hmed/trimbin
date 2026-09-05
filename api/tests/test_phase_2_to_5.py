"""Exit-gate tests for the approved review, ingest, coverage and search paths."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.routes import ask, review, uploads
from app.routes import projects as project_routes
from app.services import analytics, jobs, search, stringout

CLIP = UUID("3f758068-eebe-4df5-8a5d-e982646f09dd")
JOB = UUID("7c1722c9-d910-466b-82ba-526db3e30da1")


def entry(shot: int) -> stringout.Entry:
    return stringout.Entry(
        scene=12,
        shot=shot,
        slug=f"12{chr(64 + shot)}",
        clip_id=str(CLIP),
        take_no=4,
        start_s=4,
        end_s=31,
        proxy_uri="https://proxy/index.m3u8",
        sprite_uri="https://proxy/sprite.jpg",
        reason="human confirmed",
        decided_by="human",
        actor="editor@example.com",
        margin=0.2,
        needs_review=False,
        circled_take=4,
        open_comments=0,
    )


def test_coverage_timeline_keeps_a_missing_shot_as_a_gap() -> None:
    meta = {
        (12, 1): SimpleNamespace(shot=1, slug="12A"),
        (12, 2): SimpleNamespace(shot=2, slug="12B"),
        (12, 3): SimpleNamespace(shot=3, slug="12C"),
    }
    timeline = stringout.coverage_timeline(12, [entry(1), replace(entry(1), shot=3)], meta)
    assert [item["kind"] for item in timeline] == ["selected", "gap", "selected"]
    assert timeline[1]["entry"] is None
    assert timeline[1]["slug"] == "12B"


def test_coverage_timeline_keeps_multiple_ordered_ranges_for_one_shot() -> None:
    meta = {(12, 1): SimpleNamespace(shot=1, slug="12A")}
    first = replace(entry(1), segment_id="a", position=0, start_s=2, end_s=7)
    second = replace(entry(1), segment_id="b", position=1, start_s=18, end_s=21)
    timeline = stringout.coverage_timeline(12, [second, first], meta)
    assert [row["segment_id"] for row in timeline[0]["entries"]] == ["a", "b"]
    assert timeline[0]["duration_s"] == 8


def test_a_segment_match_at_zero_still_has_an_exact_playable_range() -> None:
    match = ask._as_match(
        {
            "clip_id": str(CLIP),
            "scene": 12,
            "setup": 2,
            "take_no": 4,
            "duration_s": 70,
            "outcome": "selected",
            "reason": "The actor crosses to the window.",
            "reason_code": "segment.match",
            "decided_by": "human",
            "proxy_uri": "https://proxy/index.m3u8",
            "finding_codes": ["segment.match"],
            "finding_starts_s": [0.0],
            "usable_to_s": 8.5,
            "relevance": 0.9,
        }
    )
    assert match.where is not None
    assert match.where.start_s == 0
    assert match.where.end_s == 8.5
    assert match.description == "The actor crosses to the window."


@pytest.mark.asyncio
async def test_source_picker_can_return_a_clip_from_another_shot(monkeypatch) -> None:
    class Principal:
        async def assert_can_read(self, project_id: int) -> None:
            assert project_id == 7

    class Archive:
        async def query(self, sql, parameters):
            assert "current_clip_placement" in sql
            assert parameters["q"] == "window"
            return SimpleNamespace(
                result_rows=[
                    [
                        CLIP,
                        12,
                        3,
                        4,
                        70.0,
                        "proxy",
                        "sprite",
                        "crosses window",
                        "B",
                        24.0,
                        "12",
                        "12C",
                    ]
                ]
            )

    async def archive():
        return Archive()

    async def no_plan(project_id: int):
        assert project_id == 7
        return []

    monkeypatch.setattr(review, "client", archive)
    monkeypatch.setattr(review.structure, "for_project", no_plan)
    rows = await review.project_sources(7, Principal(), q="window", limit=20)
    assert rows[0]["shot"] == 3
    assert rows[0]["clip_id"] == str(CLIP)


@pytest.mark.asyncio
async def test_finding_search_returns_the_finding_range_not_the_take_range(monkeypatch) -> None:
    captured: dict = {}

    async def execute(sql, params, project_id):
        captured.update(sql=sql, params=params, project_id=project_id)
        return (
            [
                {
                    "clip_id": str(CLIP),
                    "scene": 12,
                    "setup": 2,
                    "take_no": 5,
                    "duration_s": 65,
                    "outcome": "analysed",
                    "reason": "Foreground wall obstructs frame.",
                    "reason_code": "finding.match",
                    "decided_by": "agent",
                    "proxy_uri": "https://proxy/index.m3u8",
                    "finding_codes": ["frame.obstruction"],
                    "finding_starts_s": [0.0],
                    "usable_from_s": 0.0,
                    "usable_to_s": 16.0,
                    "relevance": 1.0,
                }
            ],
            4,
        )

    monkeypatch.setattr(search, "_execute", execute)
    rows, _, _ = await search.run(7, {"finding": "frame.obstruction", "limit": 20})
    match = ask._as_match(rows[0])

    assert "FROM current_findings AS f" in captured["sql"]
    assert captured["params"]["finding"] == "frame.obstruction"
    assert match.where is not None
    assert (match.where.start_s, match.where.end_s) == (0.0, 16.0)
    assert match.description == "Foreground wall obstructs frame."


@pytest.mark.asyncio
async def test_search_fails_closed_when_official_mcp_is_unavailable(monkeypatch) -> None:
    from trimbin_agents.tools import clickhouse_mcp

    class MissingSession:
        async def __aenter__(self):
            raise clickhouse_mcp.ReaderMissing("no reader")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(clickhouse_mcp, "session", lambda: MissingSession())
    with pytest.raises(search.SearchUnavailable):
        await search._execute(
            "SELECT 1 WHERE project_id = 7 LIMIT 1",
            {},
            7,
        )


@pytest.mark.asyncio
async def test_one_search_reuses_one_official_mcp_process(monkeypatch) -> None:
    """Moment search has several query branches but only one process startup."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from trimbin_agents.tools import clickhouse_mcp

    opened = 0
    queries = 0

    class FakeMCP:
        async def run_query(self, sql, project_id, columns=None):
            nonlocal queries
            queries += 1
            return SimpleNamespace(rows=[])

    @asynccontextmanager
    async def fake_session():
        nonlocal opened
        opened += 1
        yield FakeMCP()

    monkeypatch.setattr(clickhouse_mcp, "session", fake_session)
    async with search.execution_session():
        await search._execute("SELECT 1 WHERE project_id = 7 LIMIT 1", {}, 7)
        await search._execute("SELECT 2 WHERE project_id = 7 LIMIT 1", {}, 7)

    assert opened == 1
    assert queries == 2


class Principal:
    email = "owner@example.com"

    async def assert_can_curate(self, project_id: int) -> None:
        assert project_id == 7

    async def assert_is_owner(self, project_id: int) -> None:
        assert project_id == 7


@pytest.mark.asyncio
async def test_ingest_commit_settles_before_it_queues_analysis(monkeypatch) -> None:
    order: list[str] = []
    settled: dict = {}
    job = jobs.Job(
        job_id=JOB,
        project_id=7,
        kind="ingest",
        state=jobs.State.DONE,
        total_items=1,
        completed_items=1,
        failed_items=0,
        items=[{"clip_id": str(CLIP), "scene": 12, "shot": 2, "take_no": 4}],
    )

    async def get_job(job_id):
        return job

    async def settle(*args, **kwargs):
        order.append("settled")
        settled.update(kwargs)

    async def activity(*args, **kwargs):
        order.append("activity")

    async def verified(*args, **kwargs):
        order.append("verified")

    async def candidates(project_id):
        assert order[:3] == ["settled", "activity", "verified"]
        return [{"clip_id": CLIP, "group_id": 12, "subgroup_id": 2, "duration_s": 70}]

    async def queue(project_id, clips):
        order.append("analysis")
        return len(clips)

    async def limits(project_id):
        return SimpleNamespace(takes_per_shot=0)

    monkeypatch.setattr(uploads.jobs, "get_job", get_job)
    monkeypatch.setattr(uploads.settlement.placements, "resolve", settle)
    monkeypatch.setattr(uploads.settlement.activity, "record", activity)
    monkeypatch.setattr(uploads.jobs, "mark_verified", verified)
    monkeypatch.setattr(
        uploads.settlement.analysis_store, "active_clips_without_analysis", candidates
    )
    monkeypatch.setattr(uploads.jobs, "enqueue_analysis", queue)
    monkeypatch.setattr(uploads.quota, "limits_for_project", limits)

    result = await uploads.commit_ingest(
        JOB,
        uploads.CommitIngest(items=[uploads.IngestResolution(clip_id=CLIP, action="keep", take=7)]),
        Principal(),
    )
    assert result == {"status": "committed", "committed": 1, "analysis_queued": 1}
    assert order[-1] == "analysis"
    assert settled["take_no"] == 7


@pytest.mark.asyncio
async def test_retrying_an_ingest_commit_does_not_append_another_event(monkeypatch) -> None:
    item = {
        "clip_id": str(CLIP),
        "scene": 12,
        "shot": 2,
        "verified": True,
    }
    job = jobs.Job(
        job_id=JOB,
        project_id=7,
        kind="ingest",
        state=jobs.State.COMMITTED,
        total_items=1,
        completed_items=1,
        failed_items=0,
        items=[item],
    )

    async def get_job(job_id):
        return job

    async def limits(project_id):
        return SimpleNamespace(takes_per_shot=0)

    async def must_not_run(*args, **kwargs):
        raise AssertionError("a committed item was written twice")

    monkeypatch.setattr(uploads.jobs, "get_job", get_job)
    monkeypatch.setattr(uploads.quota, "limits_for_project", limits)
    monkeypatch.setattr(uploads.settlement.placements, "resolve", must_not_run)
    monkeypatch.setattr(uploads.settlement.activity, "record", must_not_run)

    result = await uploads.commit_ingest(
        JOB,
        uploads.CommitIngest(items=[uploads.IngestResolution(clip_id=CLIP, action="keep")]),
        Principal(),
    )
    assert result == {"status": "committed", "committed": 0, "analysis_queued": 0}


def test_verified_placement_migration_never_promotes_an_open_proposal() -> None:
    sql = (
        Path(__file__).parents[2] / "clickhouse/migrations/022_verified_placements.sql"
    ).read_text(encoding="utf-8")
    assert "WHERE state IN ('settled', 'ignored')" in sql
    assert "LEFT JOIN settled_placement" in sql
    assert "proposed.state = 'open'" in sql
    assert "c.project_id AS project_id" in sql
    assert "c.clip_id AS clip_id" in sql
    assert "SELECT\n    c.* EXCEPT" not in sql


@pytest.mark.asyncio
async def test_parallel_screen_reads_share_one_clickhouse_client(monkeypatch) -> None:
    opened = 0
    fake = SimpleNamespace()

    async def open_client(**kwargs):
        nonlocal opened
        opened += 1
        await asyncio.sleep(0.01)
        return fake

    monkeypatch.setattr(analytics.clickhouse_connect, "get_async_client", open_client)
    monkeypatch.setattr(analytics, "_client", None)
    first, second, third = await asyncio.gather(
        analytics.client(), analytics.client(), analytics.client()
    )

    assert opened == 1
    assert first is second is third is fake
    monkeypatch.setattr(analytics, "_client", None)


@pytest.mark.asyncio
async def test_project_archive_carries_the_revision_the_owner_saw(monkeypatch) -> None:
    current = SimpleNamespace(
        project_id=7,
        name="Rain scene",
        owner_email="owner@example.com",
        member_emails=[],
        is_public=False,
        created_at=datetime.now(UTC),
        state="active",
        rev=4,
    )
    seen = {}

    async def get(project_id, include_deleted=False):
        return current

    async def change(project_id, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(**{**vars(current), "state": "archived", "rev": 5})

    monkeypatch.setattr(project_routes.projects, "get", get)
    monkeypatch.setattr(project_routes.projects, "change", change)
    result = await project_routes.change_project(
        7,
        project_routes.ProjectCommand(rev=4, action="archive"),
        Principal(),
    )
    assert seen == {"expected_rev": 4, "name": None, "state": "archived"}
    assert result["state"] == "archived"
    assert result["rev"] == 5
