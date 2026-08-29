"""Tests for the limits that let a stranger use this.

A visitor with no account can upload footage and watch the pipeline run on it.
That is the strongest thing this project can show someone in three minutes, and
it is also an open door to a paid model and a video encoder.

The limits are several on purpose. Any one alone is easy to walk around: a byte
cap does not stop a hundred small files, a file count does not stop a hundred
requests, and a daily quota does not stop one enormous clip. What is tested here
is that each of them is actually load-bearing.

None of this is a security control. An IP is not a person. It is a cost ceiling,
and a test that treated it as authentication would be encoding a mistake.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import sandbox


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, peer: str | None = None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": peer})() if peer else None


class TestWhichProject:
    def test_the_sandbox_is_the_one_config_names(self) -> None:
        assert sandbox.is_sandbox(settings.sandbox_project_id)

    def test_a_real_project_is_not(self) -> None:
        assert not sandbox.is_sandbox(settings.sandbox_project_id + 900)


class TestFindingTheCaller:
    """Behind Cloud Run and a load balancer the socket peer is Google's
    infrastructure, so the visitor is the first entry in X-Forwarded-For."""

    def test_the_client_is_first_in_the_forwarded_chain(self) -> None:
        request = FakeRequest({"X-Forwarded-For": "203.0.113.7, 35.191.0.1, 130.211.0.2"})
        assert sandbox.caller_ip(request) == "203.0.113.7"

    def test_a_single_address_works(self) -> None:
        assert sandbox.caller_ip(FakeRequest({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"

    def test_it_falls_back_to_the_socket_peer(self) -> None:
        assert sandbox.caller_ip(FakeRequest(peer="198.51.100.4")) == "198.51.100.4"

    def test_an_unknowable_caller_is_named_rather_than_crashing(self) -> None:
        """A quota keyed on a missing value would either throw on every request
        or silently give everyone the same bucket. Saying "unknown" puts them in
        one bucket deliberately, which is the honest version of the same thing.
        """
        assert sandbox.caller_ip(FakeRequest()) == "unknown"


class TestClipLength:
    """Enforced after measurement because it cannot be known before it.

    A byte cap bounds what can arrive; only ffmpeg can tell thirty seconds from
    three minutes at a low bitrate.
    """

    def test_a_short_clip_passes(self) -> None:
        assert not sandbox.clip_is_too_long(settings.sandbox_max_seconds - 1)

    def test_exactly_the_limit_passes(self) -> None:
        """A limit of thirty seconds should accept a thirty-second clip. Off by
        one here means a visitor who read the page and complied is refused."""
        assert not sandbox.clip_is_too_long(float(settings.sandbox_max_seconds))

    def test_a_long_clip_does_not(self) -> None:
        assert sandbox.clip_is_too_long(settings.sandbox_max_seconds + 0.5)


class TestTooManyClipsAtOnce:
    @pytest.mark.asyncio
    async def test_more_than_the_limit_is_refused_before_anything_is_opened(self) -> None:
        """Refused before the job exists, so a rejected visitor leaves nothing
        behind — no job to close, no quota spent."""
        with pytest.raises(HTTPException) as raised:
            await sandbox.check_and_count(
                FakeRequest({"X-Forwarded-For": "203.0.113.9"}),
                settings.sandbox_max_clips + 1,
            )
        assert raised.value.status_code == 400
        assert str(settings.sandbox_max_clips) in raised.value.detail

    @pytest.mark.asyncio
    async def test_the_refusal_says_what_to_do_instead(self) -> None:
        """A limit with no way past it reads as a wall. Signing in is the way
        past it, and the message says so."""
        with pytest.raises(HTTPException) as raised:
            await sandbox.check_and_count(
                FakeRequest({"X-Forwarded-For": "203.0.113.9"}),
                settings.sandbox_max_clips + 1,
            )
        assert "sign in" in raised.value.detail.lower()


class TestTheByteCap:
    def test_it_fits_a_phone_clip_and_not_a_feature(self) -> None:
        """The only limit enforceable before anything arrives. Thirty seconds of
        phone video is tens of megabytes; a feature is tens of gigabytes."""
        assert sandbox.MAX_SANDBOX_BYTES >= 50 * 1024**2
        assert sandbox.MAX_SANDBOX_BYTES < settings.max_upload_bytes

    def test_it_is_far_below_the_signed_in_limit(self) -> None:
        assert sandbox.MAX_SANDBOX_BYTES * 10 < settings.max_upload_bytes


class TestTheLimitsAreActuallySet:
    """A limit of zero or a limit of a million are both configuration mistakes
    that look like working code."""

    def test_clips_per_upload_is_small(self) -> None:
        assert 1 <= settings.sandbox_max_clips <= 10

    def test_seconds_per_clip_is_short(self) -> None:
        assert 5 <= settings.sandbox_max_seconds <= 120

    def test_the_daily_quota_allows_at_least_one_real_attempt(self) -> None:
        """Below the per-upload limit, a visitor could not use their one upload
        — which would be a limit that forbids the thing it is meant to allow."""
        assert settings.sandbox_max_per_ip_per_day >= settings.sandbox_max_clips

    def test_footage_is_not_kept_indefinitely(self) -> None:
        """A visitor's footage is theirs. Keeping it because deleting is work
        would be the wrong default for material uploaded to try a demo."""
        assert 1 <= settings.sandbox_retention_hours <= 72
