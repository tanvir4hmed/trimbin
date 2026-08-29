"""Tests for the queue, the dot beside a shot, and reading a camera off a board.

These three decide what an editor is told to do next, so the thing worth testing
is not that they return a value but that they return the *right* one when two
rules apply at once. A shot that is both a close call and disagrees with the
take the room circled has to say the second thing, because that is the one a
person cannot work out for themselves.
"""

from __future__ import annotations

from app.routes.review import _status
from app.services.dashboard import Waiting, _queue_rank, _why_it_waits
from app.services.identify import camera_from_slate
from app.services.stringout import _letter

THRESHOLD = 0.15


class TestWhyAShotWaits:
    def test_a_clear_call_needs_nobody(self) -> None:
        """The product's central claim. If this returns a reason, the queue
        contains the whole shoot day and the claim is false."""
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.5,
            threshold=THRESHOLD, circled=0, chosen=2, state="",
        ) is None

    def test_a_close_call_asks_for_a_person(self) -> None:
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.03,
            threshold=THRESHOLD, circled=0, chosen=2, state="",
        ) == "close call"

    def test_a_disagreement_with_the_circle_outranks_a_close_call(self) -> None:
        """Both are true here. An editor scanning eleven rows reads the reason
        column and nothing else, so it has to carry the thing they cannot work
        out for themselves — and the circle knows about performance, which this
        system deliberately never judges."""
        reason = _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.02,
            threshold=THRESHOLD, circled=3, chosen=1, state="",
        )
        assert reason == "director circled take 3"

    def test_a_disagreement_surfaces_even_when_the_call_was_not_close(self) -> None:
        """This is the whole value of holding the circle. A confident wrong
        answer is exactly the one nothing else would flag."""
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.8,
            threshold=THRESHOLD, circled=3, chosen=1, state="",
        ) == "director circled take 3"

    def test_agreeing_with_the_circle_is_not_a_reason_to_look(self) -> None:
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.5,
            threshold=THRESHOLD, circled=2, chosen=2, state="",
        ) is None

    def test_an_unjudged_shot_is_in_the_queue(self) -> None:
        assert _why_it_waits(
            takes=4, has_verdict=False, confirmed=False, margin=0.0,
            threshold=THRESHOLD, circled=0, chosen=0, state="",
        ) == "not compared yet"

    def test_one_take_is_a_fact_rather_than_work(self) -> None:
        """Nothing to compare. Putting it in the queue would fill the morning
        with rows whose only possible action is to shrug."""
        assert _why_it_waits(
            takes=1, has_verdict=False, confirmed=False, margin=0.0,
            threshold=THRESHOLD, circled=0, chosen=0, state="",
        ) is None

    def test_a_confirmed_shot_leaves_the_queue(self) -> None:
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=True, margin=0.01,
            threshold=THRESHOLD, circled=0, chosen=2, state="",
        ) is None

    def test_a_person_marking_it_approved_ends_the_matter(self) -> None:
        """Derived status is a claim about the system's confidence; a set status
        is a claim by somebody with a name. The second one wins, even over a
        margin of nearly nothing and a disagreement with the circle."""
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.001,
            threshold=THRESHOLD, circled=9, chosen=1, state="approved",
        ) is None

    def test_someone_working_on_it_says_so_rather_than_vanishing(self) -> None:
        """Three editors sharing a project need to see that a shot is taken.
        Hiding it would send the second person to the same row."""
        assert _why_it_waits(
            takes=4, has_verdict=True, confirmed=False, margin=0.02,
            threshold=THRESHOLD, circled=0, chosen=1, state="in_progress",
        ) == "someone is on it"


def _waiting(**overrides) -> Waiting:
    base = dict(
        project_id=1, scene=12, shot=1, slug="12A", takes=4, margin=0.1,
        reason="close call", assignee="", state="", circled_take=0,
        chosen_take=1, open_comments=0,
    )
    base.update(overrides)
    return Waiting(**base)  # type: ignore[arg-type]


class TestQueueOrder:
    ME = "maya@example.com"

    def test_my_shots_come_before_unassigned_ones(self) -> None:
        """Assignment sorts above urgency deliberately. A queue that put the
        tightest margin first regardless of whose shot it is sends two editors
        to the same row, which is the failure assignment was added to prevent."""
        mine = _waiting(assignee=self.ME, margin=0.9)
        loose = _waiting(margin=0.01)
        assert _queue_rank(mine, self.ME) < _queue_rank(loose, self.ME)

    def test_unassigned_comes_before_somebody_elses(self) -> None:
        free = _waiting(margin=0.9)
        theirs = _waiting(assignee="ashik@example.com", margin=0.01)
        assert _queue_rank(free, self.ME) < _queue_rank(theirs, self.ME)

    def test_somebody_elses_work_is_visible_rather_than_hidden(self) -> None:
        """Sorted last, never filtered out. A queue that hid other people's work
        would let three editors each believe the scene is nearly done."""
        theirs = _waiting(assignee="ashik@example.com")
        assert _queue_rank(theirs, self.ME)[0] == 2

    def test_within_a_group_the_closest_call_is_first(self) -> None:
        close = _waiting(margin=0.01)
        clear = _waiting(margin=0.14)
        assert _queue_rank(close, self.ME) < _queue_rank(clear, self.ME)

    def test_a_disagreement_outranks_a_close_call_in_the_order_too(self) -> None:
        """It is the top reason in the column and it should be the top row on
        the page. A reason ranked first and sorted last is a reason nobody
        reads."""
        circled = _waiting(reason="director circled take 3", margin=0.9)
        close = _waiting(reason="close call", margin=0.01)
        assert _queue_rank(circled, self.ME) < _queue_rank(close, self.ME)


class TestTheDotBesideAShot:
    def test_decided_and_confirmed_are_not_the_same_thing(self) -> None:
        """A verdict nobody has looked at is not one an editor agreed with, and
        a tree showing them alike hides the only work actually left."""
        assert _status(4, True, False, 0.5) == "decided"
        assert _status(4, True, True, 0.5) == "confirmed"

    def test_a_close_call_needs_a_person(self) -> None:
        assert _status(4, True, False, 0.01) == "needs_review"

    def test_a_disagreement_has_its_own_state(self) -> None:
        assert _status(4, True, False, 0.9, circled=3, chosen=1) == "differs_from_circle"

    def test_a_disagreement_outranks_a_close_call(self) -> None:
        assert _status(4, True, False, 0.01, circled=3, chosen=1) == "differs_from_circle"

    def test_approved_by_a_person_shows_as_confirmed(self) -> None:
        assert _status(4, True, False, 0.001, circled=9, chosen=1, state="approved") == "confirmed"

    def test_one_take_says_so(self) -> None:
        assert _status(1, False, False, 0.0) == "too_few_takes"

    def test_nothing_judged_yet_says_so(self) -> None:
        assert _status(4, False, False, 0.0) == "not_judged"


class TestReadingTheCameraOffABoard:
    """The tempting shortcut is to read the letter in "12A" as the camera.

    It is not. That letter is the setup — 12A the wide, 12B her close-up — and
    treating it as a camera would put every shot of a single-camera day on a
    different one, which is worse than not knowing.
    """

    def test_an_explicit_camera_is_read(self) -> None:
        assert camera_from_slate("SCENE 12A TAKE 3 CAM B") == "B"

    def test_the_other_word_order_works(self) -> None:
        assert camera_from_slate("12A / TAKE 3 / A CAMERA") == "A"

    def test_the_spelled_out_form_works(self) -> None:
        assert camera_from_slate("SC 4 CAMERA C TAKE 1") == "C"

    def test_a_setup_letter_is_not_a_camera(self) -> None:
        """The failure this whole function exists to avoid."""
        assert camera_from_slate("SCENE 12A TAKE 3") == ""

    def test_a_board_with_no_camera_on_it_says_nothing(self) -> None:
        """Empty is an answer on a single-camera production, which is most of
        them, and not a gap to be filled with a guess."""
        assert camera_from_slate("RAIN SCENE / 4 / 2") == ""

    def test_an_empty_board_does_not_crash(self) -> None:
        assert camera_from_slate("") == ""
        assert camera_from_slate(None) == ""  # type: ignore[arg-type]

    def test_it_is_not_case_sensitive(self) -> None:
        assert camera_from_slate("12a take 3 cam b") == "B"


class TestShotLetters:
    """Only used when nobody has written a slug. A shot with no name reads as a
    database row; "12C" reads as a shot, and an editor can find it on the
    board."""

    def test_the_first_shot_is_a(self) -> None:
        assert _letter(1) == "A"

    def test_the_twenty_sixth_is_z(self) -> None:
        assert _letter(26) == "Z"

    def test_it_carries_past_the_alphabet(self) -> None:
        assert _letter(27) == "AA"

    def test_zero_is_nothing_rather_than_a_letter(self) -> None:
        assert _letter(0) == ""
