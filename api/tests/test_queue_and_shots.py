"""Whether a shot needs a person — the one rule, and the order it applies in.

This rule was implemented four times: the dot in the project tree, the reason in
the dashboard queue, the unconfirmed flag on the scene assembly, and the
needs_review field a comparison returns. They read the same threshold and then
disagreed about everything else, so a scene page could say "all settled" while
the dashboard listed three of its shots as waiting.

There is one implementation now, and the last class here is the test that keeps
it that way.
"""

from __future__ import annotations

from app.services.assessment import assess
from app.services.dashboard import Waiting, _queue_rank
from app.services.identify import camera_from_slate
from app.services.stringout import _letter

THRESHOLD = 0.15


def _assess(**overrides):
    base = dict(
        takes=4,
        has_verdict=True,
        confirmed=False,
        margin=0.5,
        circled_take=0,
        chosen_take=1,
        state="",
        segments=0,
        threshold=THRESHOLD,
    )
    base.update(overrides)
    return assess(**base)


class TestWhetherAShotNeedsAPerson:
    def test_a_clear_call_needs_nobody(self) -> None:
        """The product's central claim. If this returns a reason, the queue
        contains the whole shoot day and the claim is false."""
        assert _assess().waiting_reason is None
        assert _assess().status == "decided"

    def test_a_close_call_asks_for_a_person(self) -> None:
        result = _assess(margin=0.03)
        assert result.waiting_reason == "close call"
        assert result.status == "needs_review"

    def test_a_disagreement_with_the_circle_outranks_a_close_call(self) -> None:
        """Both are true here. An editor scanning eleven rows reads the reason
        column and nothing else, so it has to carry the thing they cannot work
        out for themselves — and the circle knows about performance, which this
        system deliberately never judges."""
        result = _assess(margin=0.02, circled_take=3, chosen_take=1)
        assert result.waiting_reason == "director circled take 3"
        assert result.status == "differs_from_circle"

    def test_a_disagreement_surfaces_even_when_the_call_was_not_close(self) -> None:
        """The whole value of holding the circle. A confident wrong answer is
        exactly the one nothing else would flag."""
        assert _assess(margin=0.8, circled_take=3, chosen_take=1).status == ("differs_from_circle")

    def test_agreeing_with_the_circle_is_not_a_reason_to_look(self) -> None:
        assert _assess(circled_take=2, chosen_take=2).waiting_reason is None

    def test_an_unjudged_shot_is_in_the_queue(self) -> None:
        result = _assess(has_verdict=False)
        assert result.waiting_reason == "not compared yet"
        assert result.status == "not_judged"

    def test_one_take_still_needs_a_range_chosen(self) -> None:
        """This asserted the opposite, and the reasoning expired.

        It said a one-take shot was "a fact, not work" whose only possible
        action was to shrug — true when the only thing a person could do to a
        shot was pick a winner between takes. A range can now be chosen and
        trimmed from a single take, so there is a real action and the queue was
        hiding it: the cockpit asked for a decision on exactly the shot the
        review page reported as settled.
        """
        result = _assess(takes=1, has_verdict=False)
        assert result.waiting_reason == "choose a range to use"
        assert result.status == "too_few_takes"

    def test_a_chosen_range_settles_a_single_take(self) -> None:
        """And once somebody has chosen one, it leaves the queue for good."""
        result = _assess(takes=1, has_verdict=False, segments=1)
        assert result.waiting_reason is None
        assert result.status == "confirmed"

    def test_a_chosen_range_settles_a_shot_nobody_compared(self) -> None:
        """The other direction of the same bug. A person who picked their
        ranges by hand has decided; telling them it is "not compared yet" is
        the system asking for permission it already has."""
        result = _assess(has_verdict=False, segments=3)
        assert result.waiting_reason is None
        assert result.status == "confirmed"

    def test_someone_working_a_single_take_says_so(self) -> None:
        """Same courtesy the multi-take path already extended: shown, not
        hidden, so a second editor does not start the same shot."""
        assert _assess(takes=1, state="in_progress").waiting_reason == "someone is on it"

    def test_a_confirmed_shot_leaves_the_queue(self) -> None:
        result = _assess(confirmed=True, margin=0.01)
        assert result.waiting_reason is None
        assert result.status == "confirmed"

    def test_a_person_marking_it_approved_ends_the_matter(self) -> None:
        """A set status is a claim by somebody with a name; a derived one is a
        claim about the system's confidence. The first outranks the second, even
        over a margin of nearly nothing and a disagreement with the circle."""
        result = _assess(margin=0.001, circled_take=9, chosen_take=1, state="approved")
        assert result.waiting_reason is None
        assert result.status == "confirmed"

    def test_someone_working_on_it_says_so_rather_than_vanishing(self) -> None:
        """Three editors sharing a project need to see that a shot is taken.
        Hiding it would send the second person to the same row."""
        assert _assess(margin=0.02, state="in_progress").waiting_reason == ("someone is on it")

    def test_decided_and_confirmed_are_not_the_same_thing(self) -> None:
        """A verdict nobody has looked at is not one an editor agreed with, and
        a tree showing them alike hides the only work actually left."""
        assert _assess().status == "decided"
        assert _assess(confirmed=True).status == "confirmed"


class TestTheTwoAnswersAgree:
    """The bug this file exists to prevent.

    `status` and `waiting_reason` are two views of one decision. When they were
    computed in different modules they drifted: the assembly called a shot
    settled while the queue was still listing it.

    Every state that means "a person is needed" must produce a reason, and every
    state that means "settled" must produce none. Exhaustively, not by example.
    """

    # `too_few_takes` moved across. It is only ever reached with no chosen
    # range, and in that state there is always something for a person to do.
    NEEDS_A_PERSON = {"not_judged", "needs_review", "differs_from_circle", "too_few_takes"}
    SETTLED = {"confirmed"}

    def _every_case(self):
        for takes in (1, 4):
            for has_verdict in (False, True):
                for confirmed in (False, True):
                    for margin in (0.01, 0.9):
                        for circled, chosen in ((0, 1), (3, 1), (2, 2)):
                            for state in ("", "needs_review", "in_progress", "approved"):
                                for segments in (0, 2):
                                    yield _assess(
                                        takes=takes,
                                        has_verdict=has_verdict,
                                        confirmed=confirmed,
                                        margin=margin,
                                        circled_take=circled,
                                        chosen_take=chosen,
                                        state=state,
                                        segments=segments,
                                    )

    def test_a_status_that_needs_a_person_always_carries_a_reason(self) -> None:
        for result in self._every_case():
            if result.status in self.NEEDS_A_PERSON:
                assert result.waiting_reason, f"{result.status} with no reason"

    def test_a_settled_status_never_carries_a_reason(self) -> None:
        for result in self._every_case():
            if result.status in self.SETTLED:
                assert result.waiting_reason is None, (
                    f"{result.status} but queued for {result.waiting_reason}"
                )

    def test_needs_a_person_is_exactly_having_a_reason(self) -> None:
        for result in self._every_case():
            assert result.needs_a_person == (result.waiting_reason is not None)

    def test_every_status_is_one_the_interface_draws(self) -> None:
        """The tree has a dot class per status. A status nobody styled renders
        as an invisible dot, which reads as a shot with nothing wrong."""
        drawn = {
            "too_few_takes",
            "not_judged",
            "needs_review",
            "differs_from_circle",
            "decided",
            "confirmed",
        }
        for result in self._every_case():
            assert result.status in drawn


def _waiting(**overrides) -> Waiting:
    base = dict(
        project_id=1,
        scene=12,
        shot=1,
        slug="12A",
        takes=4,
        margin=0.1,
        reason="close call",
        assignee="",
        state="",
        circled_take=0,
        chosen_take=1,
        open_comments=0,
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
        assert _queue_rank(_waiting(assignee="ashik@example.com"), self.ME)[0] == 2

    def test_within_a_group_the_closest_call_is_first(self) -> None:
        assert _queue_rank(_waiting(margin=0.01), self.ME) < _queue_rank(
            _waiting(margin=0.14), self.ME
        )

    def test_a_disagreement_outranks_a_close_call_in_the_order_too(self) -> None:
        """It is the top reason in the column and it should be the top row on
        the page. A reason ranked first and sorted last is a reason nobody
        reads."""
        circled = _waiting(reason="director circled take 3", margin=0.9)
        close = _waiting(reason="close call", margin=0.01)
        assert _queue_rank(circled, self.ME) < _queue_rank(close, self.ME)


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
