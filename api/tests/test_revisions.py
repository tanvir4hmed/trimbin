"""Two editors on one shot, and a browser that retried.

Every write to a shot was `set(merge=True)` — a blind write. It does not know
what the caller was looking at, so it cannot tell an edit from an overwrite: two
editors both succeeded and the second silently discarded the first. No error, no
record, and the only evidence is that somebody's change is gone.

The second half is a different problem wearing the same clothes. A browser
retries a POST it never saw the answer to, and a second editorial decision lands
in the archive. A revision cannot catch that — the first write moved the rev, so
the retry looks exactly like a conflict when it is not.
"""

from __future__ import annotations

import pytest

from app.services import revisions


class TestTheRevisionCheck:
    def test_a_matching_revision_passes(self) -> None:
        revisions.check(3, 3)

    def test_a_stale_revision_is_refused(self) -> None:
        """The whole point. The caller was shown 3, somebody else has since
        written 4, and this write was composed against something that is no
        longer true."""
        with pytest.raises(revisions.Conflict):
            revisions.check(3, 4)

    def test_a_revision_from_the_future_is_also_refused(self) -> None:
        """Not merely `expected < found`. A client sending a higher revision
        than exists is confused about something, and guessing which is worse
        than refusing."""
        with pytest.raises(revisions.Conflict):
            revisions.check(5, 4)

    def test_zero_is_a_real_revision(self) -> None:
        """A document nobody has written yet. Treating zero as "unset" would
        make the very first edit unprotected, which is the one most likely to
        race — two people setting up the same shot at once."""
        revisions.check(0, 0)
        with pytest.raises(revisions.Conflict):
            revisions.check(0, 1)

    def test_not_saying_is_accepted(self) -> None:
        """None means the caller did not look. Requiring it everywhere would
        break the first request after a deploy for every client that had not
        reloaded, and that costs more than the race it prevents on a field
        nobody edits concurrently."""
        revisions.check(None, 7)


class TestWhatAConflictSays:
    def test_it_is_a_409(self) -> None:
        with pytest.raises(revisions.Conflict) as raised:
            revisions.check(1, 2)
        assert raised.value.status_code == 409

    def test_it_carries_both_revisions(self) -> None:
        """An interface told only "conflict" can offer nothing but a reload. One
        handed the numbers can say what happened."""
        with pytest.raises(revisions.Conflict) as raised:
            revisions.check(1, 2)
        detail = raised.value.detail
        assert detail["expected_rev"] == 1
        assert detail["current_rev"] == 2

    def test_it_says_what_happened_in_words(self) -> None:
        with pytest.raises(revisions.Conflict) as raised:
            revisions.check(1, 2)
        assert "changed this while you" in raised.value.detail["detail"]


class TestReplayKeys:
    """Keyed on the command *and* the person.

    A key alone would make two editors pressing the same button one command: the
    second would silently receive the first one's answer, which is a worse bug
    than the duplicate it prevents.
    """

    def test_two_people_with_the_same_key_are_two_commands(self) -> None:
        assert revisions._id("abc", "maya@x.com") != revisions._id("abc", "ashik@x.com")

    def test_the_same_person_replaying_is_one_command(self) -> None:
        assert revisions._id("abc", "maya@x.com") == revisions._id("abc", "maya@x.com")

    def test_a_key_cannot_escape_its_document(self) -> None:
        """The key arrives in a header. A slash in a Firestore document id makes
        it a path, so a crafted key could address a document in another
        collection."""
        crafted = revisions._id("../../projects/1", "a@b.c")
        assert "/" not in crafted
        assert ".." not in crafted or crafted.count("/") == 0

    def test_a_long_key_is_bounded(self) -> None:
        assert len(revisions._id("x" * 5000, "y" * 5000)) < 200

    @pytest.mark.asyncio
    async def test_no_key_means_no_replay(self) -> None:
        """An absent header is the ordinary case and must not cost a read."""
        assert await revisions.replay("", "maya@x.com") is None

    @pytest.mark.asyncio
    async def test_remembering_nothing_is_a_no_op(self) -> None:
        await revisions.remember("", "maya@x.com", {"status": "recorded"})


class TestTheReplayWindow:
    def test_it_covers_a_retry_a_person_would_actually_make(self) -> None:
        """A refresh, a flaky connection, a laptop waking up."""
        assert revisions.REPLAY_WINDOW.total_seconds() >= 3600

    def test_it_does_not_last_forever(self) -> None:
        """Beyond it a repeat is a new command, which is right: somebody
        pressing the same button a day later means it."""
        assert revisions.REPLAY_WINDOW.total_seconds() <= 24 * 3600


class TestTheConflictSerialises:
    """A correctly raised 409 came back as a 500.

    The payload carried the current Firestore document, so the interface could
    "say what changed". Firestore documents hold DatetimeWithNanoseconds, which
    FastAPI's encoder refuses — so the conflict looked like a crash, which is
    the one thing a conflict must not look like.

    The client never used that field anyway: it invalidates and refetches.
    """

    def test_the_detail_survives_json(self) -> None:
        import json

        with pytest.raises(revisions.Conflict) as raised:
            revisions.check(1, 2)
        json.dumps(raised.value.detail)

    def test_it_carries_no_store_objects(self) -> None:
        with pytest.raises(revisions.Conflict) as raised:
            revisions.check(1, 2)
        assert set(raised.value.detail) == {"detail", "expected_rev", "current_rev"}
