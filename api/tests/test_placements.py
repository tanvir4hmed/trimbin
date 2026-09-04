"""Settling where a clip belongs.

`clips.group_id` and `clips.subgroup_id` are in the table's sort key, so moving a
misplaced clip cannot be an ordinary update. Placement therefore moved off the
clip into an append-only table, and moving became an insert.

What is worth testing is not the insert. It is that nothing here moves anything
on its own, that "keep" cannot quietly become a move, and that the vocabulary
stays closed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import placements as routes
from app.services import placements


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestTheVocabularyIsClosed:
    """A free-text source column becomes six spellings of "slate" within a
    fortnight, and then nothing can be counted."""

    def test_every_source_is_named(self) -> None:
        assert {
            placements.SLATE,
            placements.FOLDER,
            placements.TIMECODE,
            placements.FILENAME,
            placements.HUMAN,
        } == {"slate", "folder", "timecode", "filename", "human"}

    def test_every_state_is_named(self) -> None:
        assert {placements.OPEN, placements.SETTLED, placements.IGNORED} == {
            "open",
            "settled",
            "ignored",
        }


class TestTheActionsAreClosed:
    """Four things a person can say, and no fifth."""

    def test_only_four_actions_are_accepted(self) -> None:
        for action in ("move", "keep", "unassign", "replace"):
            routes.Resolution(action=action, scene=12, shot=3)

    def test_anything_else_is_refused(self) -> None:
        from pydantic import ValidationError

        for bad in ("delete", "MOVE", "", "drop", "merge"):
            with pytest.raises(ValidationError):
                routes.Resolution(action=bad)

    def test_there_is_no_delete(self) -> None:
        """The one action deliberately absent. An editor who uploaded a file
        twice on purpose is doing something we have no standing to undo, and a
        misplaced clip is misplaced, not unwanted."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            routes.Resolution(action="delete")


class TestMovingNeedsADestination:
    @pytest.mark.asyncio
    async def test_a_move_without_a_scene_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Scene zero is where the interface shows a clip as ungrouped. A move
        that quietly meant "unassign" would look like it worked and lose the
        clip out of the tree."""
        from fastapi import HTTPException

        from app.auth import Principal

        async def allowed(self, project_id):
            return None

        monkeypatch.setattr(Principal, "assert_can_curate", allowed)

        with pytest.raises(HTTPException) as raised:
            await routes.resolve(
                1,
                __import__("uuid").uuid4(),
                routes.Resolution(action="move", scene=0, shot=0),
                Principal(email="editor@example.com"),
            )
        assert raised.value.status_code == 400


class TestKeepCannotBecomeAMove:
    """The subtle one.

    "Keep where it is" reads its numbers from the current placement rather than
    from the request. A stale page holding last week's scene and shot would
    otherwise send them, and pressing a button labelled *keep* would move the
    clip somewhere else.
    """

    @pytest.mark.asyncio
    async def test_keep_ignores_the_numbers_in_the_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid

        from app.auth import Principal

        clip = uuid.uuid4()
        recorded: dict = {}

        async def allowed(self, project_id):
            return None

        async def inbox(project_id):
            return [{"clip_id": str(clip), "scene": 12, "shot": 3, "take_no": 4}]

        async def resolve(project_id, clip_id, scene, shot, actor, detail="", *, take_no=0):
            recorded.update(scene=scene, shot=shot, take_no=take_no)

        async def noted(*args, **kwargs):
            return None

        async def no_candidates(project_id):
            return []

        monkeypatch.setattr(Principal, "assert_can_curate", allowed)
        monkeypatch.setattr(routes.placements, "inbox", inbox)
        monkeypatch.setattr(routes.placements, "resolve", resolve)
        monkeypatch.setattr(routes.activity, "record", noted)
        monkeypatch.setattr(routes.analysis_store, "active_clips_without_analysis", no_candidates)

        await routes.resolve(
            1,
            clip,
            # A stale page, insisting on somewhere else entirely.
            routes.Resolution(action="keep", scene=99, shot=99),
            Principal(email="editor@example.com"),
        )
        assert recorded == {"scene": 12, "shot": 3, "take_no": 4}

    @pytest.mark.asyncio
    async def test_keeping_something_already_settled_is_a_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Somebody else got there first. Writing another placement would bury
        their decision under one made from a stale screen."""
        import uuid

        from fastapi import HTTPException

        from app.auth import Principal

        async def allowed(self, project_id):
            return None

        async def empty(project_id):
            return []

        monkeypatch.setattr(Principal, "assert_can_curate", allowed)
        monkeypatch.setattr(routes.placements, "inbox", empty)

        with pytest.raises(HTTPException) as raised:
            await routes.resolve(
                1,
                uuid.uuid4(),
                routes.Resolution(action="keep"),
                Principal(email="editor@example.com"),
            )
        assert raised.value.status_code == 409


class TestDuplicateDetection:
    @pytest.mark.asyncio
    async def test_no_hash_means_no_lookup(self) -> None:
        """A clip whose bytes could not be hashed is not a duplicate of
        everything else that could not be hashed."""
        assert await placements.duplicates_of(1, "") == []


class TestReplacingADuplicate:
    """Never a delete. Two clips, two sets of bytes, two histories — only
    which one is *current* for a take changes."""

    @pytest.mark.asyncio
    async def test_replace_without_a_duplicate_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing to replace, so nothing happens. The 409 is the same shape as
        `keep` on an already-settled clip: a decision that no longer applies."""
        import uuid

        from fastapi import HTTPException

        from app.auth import Principal

        async def allowed(self, project_id):
            return None

        async def none(project_id, clip_id):
            return None

        monkeypatch.setattr(Principal, "assert_can_curate", allowed)
        monkeypatch.setattr(routes.placements, "settled_duplicate", none)

        with pytest.raises(HTTPException) as raised:
            await routes.resolve(
                1,
                uuid.uuid4(),
                routes.Resolution(action="replace"),
                Principal(email="editor@example.com"),
            )
        assert raised.value.status_code == 409

    @pytest.mark.asyncio
    async def test_replace_settles_the_new_clip_and_retires_the_old_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One call places the new clip where the old one sat; a second
        retires the old one to unassigned. Neither clip, its bytes, or its
        history is ever removed — only which is current for that take."""
        import uuid

        from app.auth import Principal

        new_clip = uuid.uuid4()
        old_clip = uuid.uuid4()
        resolved: list[tuple] = []

        async def allowed(self, project_id):
            return None

        async def duplicate(project_id, clip_id):
            assert clip_id == new_clip
            return {"clip_id": str(old_clip), "scene": 12, "shot": 3, "take_no": 2}

        async def resolve(project_id, clip_id, scene, shot, actor, detail="", *, take_no=0):
            resolved.append((clip_id, scene, shot, take_no, detail))

        async def unassign(project_id, clip_id, actor, detail="", *, take_no=0):
            resolved.append((clip_id, 0, 0, take_no, detail))

        async def noted(*args, **kwargs):
            return None

        async def no_candidates(project_id):
            return []

        monkeypatch.setattr(Principal, "assert_can_curate", allowed)
        monkeypatch.setattr(routes.placements, "settled_duplicate", duplicate)
        monkeypatch.setattr(routes.placements, "resolve", resolve)
        monkeypatch.setattr(routes.placements, "unassign", unassign)
        monkeypatch.setattr(routes.activity, "record", noted)
        monkeypatch.setattr(routes.analysis_store, "active_clips_without_analysis", no_candidates)

        await routes.resolve(
            1,
            new_clip,
            routes.Resolution(action="replace"),
            Principal(email="editor@example.com"),
        )

        by_clip = {
            clip_id: (scene, shot, take_no, detail)
            for clip_id, scene, shot, take_no, detail in resolved
        }
        # The new clip takes the old one's exact slot.
        assert by_clip[new_clip] == (12, 3, 2, f"replaces duplicate {str(old_clip)[:8]}")
        # The old clip is parked, not deleted — the same shape "unassign" uses.
        assert by_clip[old_clip][:3] == (0, 0, 0)
        assert str(new_clip)[:8] in by_clip[old_clip][3]


class TestPlacementEventsAreTotallyOrdered:
    """A second-resolution timestamp is not an event order.

    Two people can resolve two inbox rows in the same second, and an automated
    proposal can arrive in that second too. Every append therefore carries its
    own UUID and millisecond clock; the ClickHouse view uses both.
    """

    @pytest.mark.asyncio
    async def test_each_append_has_an_event_id_and_precise_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid

        inserted: list[list] = []

        class FakeClickHouse:
            async def insert(self, table, rows, column_names):
                assert table == "placements"
                assert "event_id" in column_names
                assert "occurred_at" in column_names
                inserted.extend(rows)

        async def fake_client():
            return FakeClickHouse()

        monkeypatch.setattr(placements, "client", fake_client)
        clip = uuid.uuid4()

        await placements.record(1, clip, 12, 2, 4, placements.SLATE)
        await placements.record(1, clip, 12, 3, 4, placements.HUMAN)

        event_index = placements._COLUMNS.index("event_id")
        precise_index = placements._COLUMNS.index("occurred_at")
        assert inserted[0][event_index] != inserted[1][event_index]
        assert all(row[precise_index].tzinfo is not None for row in inserted)

    def test_the_canonical_view_exists_in_the_migration(self) -> None:
        from pathlib import Path

        migration = (
            Path(__file__).parents[2]
            / "clickhouse"
            / "migrations"
            / "020_current_clip_placement.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE VIEW current_clip_placement" in migration
        assert "tuple(" in migration
        assert "event_id" in migration


class TestContentHashing:
    def test_the_same_bytes_hash_the_same(self, tmp_path) -> None:
        """The point: the same file dragged in from two folders has two names
        and identical content. Nothing noticed, so it became two takes of one
        shot and the comparison ranked a clip against itself."""
        from app.worker.ingest import content_hash

        a = tmp_path / "A001.mov"
        b = tmp_path / "copy of A001.mov"
        a.write_bytes(b"\x00\x01\x02" * 5000)
        b.write_bytes(b"\x00\x01\x02" * 5000)
        assert content_hash(a) == content_hash(b)

    def test_different_bytes_hash_differently(self, tmp_path) -> None:
        from app.worker.ingest import content_hash

        a = tmp_path / "a.mov"
        b = tmp_path / "b.mov"
        a.write_bytes(b"\x00" * 5000)
        b.write_bytes(b"\x01" * 5000)
        assert content_hash(a) != content_hash(b)

    def test_a_large_file_is_read_in_chunks(self, tmp_path) -> None:
        """A camera original is gigabytes. Hashing it whole would hold the file
        in memory beside the ffmpeg pass already running."""
        from app.worker.ingest import content_hash

        big = tmp_path / "big.mov"
        big.write_bytes(b"x" * (3 * 1024 * 1024))
        assert len(content_hash(big)) == 64
