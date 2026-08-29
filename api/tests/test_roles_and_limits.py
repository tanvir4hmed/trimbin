"""Tests for who may do what, and for what a guest project may hold.

This replaces the sandbox tests. The sandbox was a separate project with
separate rules reached by a separate page, and it was wrong for a reason worth
recording: it sent a visitor somewhere the real users never go, and then asked
them to judge the thing they had not seen.

So the shape being tested changed. What used to be "can an anonymous visitor
spend our money" is now "does a guest get the same application with smaller
limits, and are the limits load-bearing".

The one thing that has not changed: none of this is a security control. It is a
cost ceiling. Anything that must not be abused is behind a permission, and those
are tested here too.
"""

from __future__ import annotations

import pytest

from app.services import members, quota


class TestWhoIsWho:
    def test_the_lead_editor_is_recognised(self) -> None:
        assert members.role_of(members.LEAD_EDITOR) == "lead"

    def test_case_and_whitespace_do_not_change_a_role(self) -> None:
        """Google returns the address it has on file. A roster that matched on
        exact bytes would demote an editor whose address came back capitalised
        differently on one sign-in, and nothing would look broken."""
        assert members.role_of(f"  {members.LEAD_EDITOR.upper()}  ") == "lead"

    def test_the_editors_are_recognised(self) -> None:
        for address in members.EDITORS:
            assert members.role_of(address) == "editor"

    def test_everybody_else_is_a_guest(self) -> None:
        assert members.role_of("a-judge@example.com") == "guest"

    def test_nobody_is_a_guest_too(self) -> None:
        """Not "unknown", not None. A guest is a real role with real
        permissions, and treating it as an absence is how somebody ends up
        looking at a page with every button disabled."""
        assert members.role_of(None) == "guest"

    def test_staff_is_both_roles_and_not_the_third(self) -> None:
        assert members.is_staff(members.LEAD_EDITOR)
        assert members.is_staff(next(iter(members.EDITORS)))
        assert not members.is_staff("someone@example.com")


class TestWhatAGuestMayDo:
    """The correction that matters. A guest is not a spectator.

    They may change our results — reject a take, disagree with the panel, leave
    a note — because watching somebody disagree with the system is the product,
    and a demonstration you can only look at is a video.
    """

    def test_a_signed_in_guest_may_overrule_us(self) -> None:
        assert members.capabilities("a-judge@example.com")["can_override"]

    def test_a_signed_in_guest_may_comment(self) -> None:
        assert members.capabilities("a-judge@example.com")["can_comment"]

    def test_a_guest_may_not_upload_into_our_productions(self) -> None:
        caps = members.capabilities("a-judge@example.com")
        assert not caps["can_upload_to_team_projects"]

    def test_a_guest_may_make_their_own_project(self) -> None:
        """The whole of how a visitor gets a real workspace instead of a
        demonstration. Without this the guest role is a read-only tour."""
        assert members.capabilities("a-judge@example.com")["can_create_own_project"]

    def test_an_anonymous_visitor_reads_and_changes_nothing(self) -> None:
        caps = members.capabilities(None)
        assert caps["can_read"]
        assert not caps["can_comment"]
        assert not caps["can_override"]

    def test_only_the_lead_adds_members(self) -> None:
        assert members.capabilities(members.LEAD_EDITOR)["can_add_members"]
        assert not members.capabilities(next(iter(members.EDITORS)))["can_add_members"]
        assert not members.capabilities("a-judge@example.com")["can_add_members"]

    def test_an_editor_uploads_into_our_productions(self) -> None:
        caps = members.capabilities(next(iter(members.EDITORS)))
        assert caps["can_upload_to_team_projects"]


class TestTheLimitsAreActuallySet:
    """A limit of zero and a limit of a million are both configuration mistakes
    that look like working code."""

    def test_a_guest_gets_more_than_one_project(self) -> None:
        """One project cannot be deleted and remade, so a limit of one is a
        limit somebody hits and then cannot move past."""
        assert 2 <= members.GUEST_LIMITS.projects <= 5

    def test_a_guest_gets_enough_scenes_to_see_a_comparison(self) -> None:
        assert 2 <= members.GUEST_LIMITS.scenes <= 5

    def test_a_guest_gets_enough_takes_for_the_point_to_land(self) -> None:
        """Two takes is a coin toss. The product's claim is about picking one of
        several, and it cannot be shown below about four."""
        assert 4 <= members.GUEST_LIMITS.takes_per_shot <= 10

    def test_a_guest_clip_is_long_enough_to_hold_a_performance(self) -> None:
        assert 30 <= members.GUEST_LIMITS.clip_seconds <= 180

    def test_guest_footage_is_not_kept_indefinitely(self) -> None:
        """A visitor's footage is theirs. Keeping it because deleting is work
        would be the wrong default for material uploaded to try something."""
        assert 1 <= members.GUEST_LIMITS.retention_days <= 30

    def test_the_company_keeps_its_own_work(self) -> None:
        """Zero days means kept. A production swept after a week would be a
        catastrophe wearing the shape of a policy."""
        assert members.STAFF_LIMITS.retention_days == 0

    def test_the_company_is_not_bound_by_the_guest_limits(self) -> None:
        assert members.STAFF_LIMITS.takes_per_shot > members.GUEST_LIMITS.takes_per_shot
        assert members.STAFF_LIMITS.scenes > members.GUEST_LIMITS.scenes


class TestClipLength:
    """Enforced after measurement because it cannot be known before it.

    A byte cap bounds what can arrive; only ffmpeg can tell sixty seconds from
    six minutes at a low bitrate.
    """

    def test_a_short_clip_passes(self) -> None:
        limits = members.GUEST_LIMITS
        assert not quota.clip_is_too_long(limits.clip_seconds - 1, limits)

    def test_exactly_the_limit_passes(self) -> None:
        """A limit of sixty seconds should accept a sixty-second clip. Off by
        one here means somebody who read the page and complied is refused."""
        limits = members.GUEST_LIMITS
        assert not quota.clip_is_too_long(float(limits.clip_seconds), limits)

    def test_a_long_clip_does_not(self) -> None:
        limits = members.GUEST_LIMITS
        assert quota.clip_is_too_long(limits.clip_seconds + 0.5, limits)

    def test_the_company_has_no_length_limit(self) -> None:
        """Zero means no limit, and a ten-minute take is an ordinary thing to
        shoot. A rule that read zero as "reject everything" would refuse every
        clip the company ever uploads."""
        assert not quota.clip_is_too_long(3600.0, members.STAFF_LIMITS)


class TestTheByteCap:
    def test_it_fits_a_minute_of_phone_video_and_not_a_feature(self) -> None:
        assert quota.MAX_GUEST_BYTES >= 100 * 1024**2
        assert quota.MAX_GUEST_BYTES < quota.MAX_STAFF_BYTES

    def test_it_is_far_below_what_the_company_may_upload(self) -> None:
        assert quota.MAX_GUEST_BYTES * 10 < quota.MAX_STAFF_BYTES


class TestTheMaintenanceRouteIsClosed:
    """Who may trigger the sweep.

    The first version accepted any request carrying any Authorization header,
    beside a comment claiming Cloud Run had already checked. It had not: this
    service has an allUsers invoker binding because the public pages need one,
    so Cloud Run lets everybody through and the application is the only gate.

    A check-shaped thing with a confident comment is worse than no check, since
    the comment stops anyone looking.
    """

    def test_no_header_is_refused(self) -> None:
        from app.routes.maintenance import _is_the_scheduler

        assert not _is_the_scheduler(None)

    def test_something_that_is_not_a_bearer_token_is_refused(self) -> None:
        from app.routes.maintenance import _is_the_scheduler

        assert not _is_the_scheduler("Basic abcdef")

    def test_an_unset_expected_account_refuses_rather_than_guesses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A maintenance route that runs for whoever asks is worse than one that
        never runs."""
        from app.routes import maintenance

        monkeypatch.setattr(maintenance.settings, "scheduler_service_account", "")
        assert not maintenance._is_the_scheduler("Bearer anything")

    def test_a_valid_token_from_the_wrong_account_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The signature being good is not the question. Plenty of accounts can
        mint a valid Google token; one of them is ours."""
        from app.routes import maintenance

        monkeypatch.setattr(
            maintenance.settings,
            "scheduler_service_account",
            "sched@trimbin.iam.gserviceaccount.com",
        )
        monkeypatch.setattr(
            maintenance.id_token,
            "verify_oauth2_token",
            lambda *a, **k: {"email": "someone-else@example.com"},
        )
        assert not maintenance._is_the_scheduler("Bearer good-but-wrong")

    def test_the_scheduler_itself_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes import maintenance

        monkeypatch.setattr(
            maintenance.settings,
            "scheduler_service_account",
            "Sched@trimbin.iam.gserviceaccount.com",
        )
        monkeypatch.setattr(
            maintenance.id_token,
            "verify_oauth2_token",
            lambda *a, **k: {"email": "sched@trimbin.iam.gserviceaccount.com"},
        )
        assert maintenance._is_the_scheduler("Bearer ours")

    def test_a_token_that_does_not_verify_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes import maintenance

        monkeypatch.setattr(
            maintenance.settings,
            "scheduler_service_account",
            "sched@trimbin.iam.gserviceaccount.com",
        )

        def reject(*a, **k):
            raise ValueError("Token expired")

        monkeypatch.setattr(maintenance.id_token, "verify_oauth2_token", reject)
        assert not maintenance._is_the_scheduler("Bearer stale")
