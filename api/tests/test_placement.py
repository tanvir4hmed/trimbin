"""Where an uploaded clip lands, and when the slate is worth arguing with.

The declared target always wins. Moving somebody's footage because a slate was
misread is the one mistake here that scatters a shoot day silently, and it would
look like the system working.

A disagreement is reported instead. A clip sent to 12C whose slate reads 15B is
usually a file dragged from the wrong folder, and saying so at upload is the
difference between catching it now and finding it in the cut.
"""

from __future__ import annotations

from app.worker.ingest import place


class TestNothingDeclared:
    """The old behaviour, unchanged: the slate decides."""

    def test_the_slate_places_the_clip(self) -> None:
        assert place(0, 0, 12, 3, True) == (12, 3, "")

    def test_an_unread_slate_leaves_it_ungrouped(self) -> None:
        """Group zero shows as ungrouped. Guessing would be worse: a wrong
        grouping is inherited by every comparison downstream."""
        assert place(0, 0, 0, 0, False) == (0, 0, "")

    def test_no_target_never_produces_a_mismatch(self) -> None:
        _, _, mismatch = place(0, 0, 12, 3, True)
        assert mismatch == ""


class TestDeclaredTarget:
    def test_the_target_wins_when_the_slate_agrees(self) -> None:
        assert place(12, 3, 12, 3, True) == (12, 3, "")

    def test_the_target_wins_when_the_slate_disagrees(self) -> None:
        """It is kept where it was sent. The flag is the output, not a move."""
        scene, shot, mismatch = place(12, 3, 15, 2, True)
        assert (scene, shot) == (12, 3)
        assert mismatch

    def test_the_mismatch_says_what_the_slate_read(self) -> None:
        """An editor has to be able to tell a wrong-folder file from a misread
        board without opening the clip."""
        _, _, mismatch = place(12, 3, 15, 2, True)
        assert "15" in mismatch and "2" in mismatch

    def test_an_unreadable_slate_is_not_a_disagreement(self) -> None:
        """An unread board is not evidence of anything. Flagging it here would
        put an amber row on every clip shot without a slate."""
        assert place(12, 3, 0, 0, False) == (12, 3, "")

    def test_a_low_confidence_reading_is_not_a_disagreement(self) -> None:
        """The slate reader returns a guess with confidence. Only a confident
        reading gets to contradict a person who said where the footage goes."""
        assert place(12, 3, 15, 2, False) == (12, 3, "")

    def test_a_different_shot_in_the_same_scene_is_still_flagged(self) -> None:
        """The common real case: right scene, wrong folder within it."""
        _, _, mismatch = place(12, 3, 12, 5, True)
        assert mismatch

class TestASceneWithoutAShot:
    """A day of coverage on one scene arrives exactly this way: the editor names
    the scene, and the slates sort the shots inside it.

    Shot zero means "not declared". Reading it as shot number zero files the
    whole day as ungrouped — which the first version did, while also flagging
    every clip as a mismatch. The test that let it through asserted only the
    scene number.
    """

    def test_the_slate_chooses_the_shot(self) -> None:
        assert place(12, 0, 12, 4, True) == (12, 4, "")

    def test_it_is_not_filed_as_shot_zero(self) -> None:
        assert place(12, 0, 12, 4, True)[1] != 0

    def test_a_shot_the_editor_did_not_name_is_not_a_disagreement(self) -> None:
        _, _, mismatch = place(12, 0, 12, 7, True)
        assert mismatch == ""

    def test_the_wrong_scene_is_still_caught(self) -> None:
        """The check that survives: the editor named scene 12 and this clip is
        slated 15."""
        scene, _, mismatch = place(12, 0, 15, 2, True)
        assert scene == 12
        assert mismatch

    def test_an_unread_slate_leaves_the_shot_ungrouped(self) -> None:
        """Nothing to sort it by, and no complaint to make about that."""
        assert place(12, 0, 0, 0, False) == (12, 0, "")
