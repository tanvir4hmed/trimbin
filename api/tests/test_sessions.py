"""Tests for the second way in.

An OAuth client is the one thing in this system that no API can create — it is a
form in a console — so a deployment without a second door has every screen behind
sign-in built, shipped and unreachable. That is the state this one was in.

What matters here is not the happy path. It is that a forged token is refused,
that an expired one is refused, and above all that a guest cannot type their way
into somebody else's authority.
"""

from __future__ import annotations

import time

import pytest

from app.services import members, sessions

SECRET = "a-test-signing-secret-that-is-long-enough"
GUEST = "guest-code-abc"
TEAM = f"{members.LEAD_EDITOR}:lead-code-xyz,{next(iter(members.EDITORS))}:editor-code-123"


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sessions.settings, "session_secret", SECRET)
    monkeypatch.setattr(sessions.settings, "guest_pass", GUEST)
    monkeypatch.setattr(sessions.settings, "team_passes", TEAM)


class TestTheGuestCannotBecomeAnEditor:
    """The hole this design has to close.

    A guest types whatever they like into the username box, and `role_of` reads
    an address against the roster. Type the lead editor's address and, without
    namespacing, you would be handed the lead editor's role — no password for it
    required, because the guest password is the one you already have.
    """

    def test_typing_a_roster_address_with_the_guest_password_is_refused(self) -> None:
        """The strongest form: a guest holding the shared password cannot use a
        roster address at all, not even to become a guest named after one.

        There are two locks and this is the outer one. It exists because the
        inner one — namespacing — is a string format, and string formats get
        edited by somebody who does not know what they are load-bearing for.
        """
        with pytest.raises(sessions.BadPass):
            sessions.redeem(members.LEAD_EDITOR, GUEST)

    def test_an_address_that_looks_official_is_still_namespaced(self) -> None:
        """The inner lock, on an address nobody on the roster holds. Without it,
        `role_of` would read what was typed and hand out whatever role it found.
        """
        session = sessions.redeem("admin@trimbin.com", GUEST)
        assert session.role == "guest"
        assert session.email.endswith(f"@{sessions.GUEST_DOMAIN}")
        assert session.email != "admin@trimbin.com"
        assert members.role_of(session.email) == "guest"

    def test_a_verified_guest_token_cannot_be_promoted_either(self) -> None:
        """The role is re-derived from the roster on the way back in rather than
        trusted from the payload, so even a token that somehow claimed otherwise
        would come back as a guest."""
        token = sessions.mint(sessions.redeem("Some Judge", GUEST))
        assert sessions.verify(token).role == "guest"


class TestEditorSignIn:
    def test_an_editor_gets_their_own_identity(self) -> None:
        session = sessions.redeem(members.LEAD_EDITOR, "lead-code-xyz")
        assert session.email == members.LEAD_EDITOR
        assert session.role == "lead"

    def test_the_local_part_is_enough(self) -> None:
        """Nobody types "@gmail.com" twice a day."""
        session = sessions.redeem(members.LEAD_EDITOR.split("@")[0], "lead-code-xyz")
        assert session.email == members.LEAD_EDITOR

    def test_the_address_is_not_case_sensitive(self) -> None:
        session = sessions.redeem(members.LEAD_EDITOR.upper(), "lead-code-xyz")
        assert session.email == members.LEAD_EDITOR

    def test_each_editor_has_their_own_password(self) -> None:
        """One shared team code would have been three lines shorter and would
        have made every override in the archive say "one of the three of us"."""
        with pytest.raises(sessions.BadPass):
            sessions.redeem(members.LEAD_EDITOR, "editor-code-123")

    def test_a_wrong_password_does_not_fall_through_to_guest(self) -> None:
        """The trap: an editor typing their address and the *guest* password
        would otherwise be signed in as a guest called by their own name, which
        looks like a successful login and silently is not."""
        with pytest.raises(sessions.BadPass):
            sessions.redeem(members.LEAD_EDITOR, GUEST)


class TestRefusals:
    def test_no_password_is_refused(self) -> None:
        with pytest.raises(sessions.BadPass):
            sessions.redeem("someone", "")

    def test_an_unknown_password_is_refused(self) -> None:
        with pytest.raises(sessions.BadPass):
            sessions.redeem("someone", "not-a-real-code")

    def test_a_guest_must_say_who_they_are(self) -> None:
        """The username is the identity every decision is recorded against. An
        anonymous one would be a row saying somebody decided something."""
        with pytest.raises(sessions.BadPass):
            sessions.redeem("", GUEST)

    def test_nothing_is_minted_without_a_signing_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed. A deployment that signs with a default is a deployment
        anybody can forge."""
        monkeypatch.setattr(sessions.settings, "session_secret", "")
        with pytest.raises(sessions.NotConfigured):
            sessions.mint(sessions.Session("a@b.c", "a", "guest", 2**31))


class TestTokens:
    def test_a_token_round_trips(self) -> None:
        original = sessions.redeem("Alex Chen", GUEST)
        back = sessions.verify(sessions.mint(original))
        assert back is not None
        assert back.email == original.email
        assert back.name == "Alex Chen"

    def test_a_tampered_payload_is_refused(self) -> None:
        """The whole point of the signature. Editing the payload is trivial —
        it is base64 of readable JSON — and must change nothing."""
        token = sessions.mint(sessions.redeem("Alex", GUEST))
        payload, _, signature = token.partition(".")
        forged = f"{payload[:-4]}AAAA.{signature}"
        assert sessions.verify(forged) is None

    def test_a_token_signed_with_another_secret_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = sessions.mint(sessions.redeem("Alex", GUEST))
        monkeypatch.setattr(sessions.settings, "session_secret", "a-different-secret")
        assert sessions.verify(token) is None

    def test_an_expired_token_is_refused(self) -> None:
        expired = sessions.Session(
            email="alex@guest.trimbin", name="Alex", role="guest",
            expires_at=int(time.time()) - 60,
        )
        assert sessions.verify(sessions.mint(expired)) is None

    def test_rubbish_is_refused_rather_than_raising(self) -> None:
        """A browser sends malformed input as a matter of course. Every kind of
        failure answers the same, because the caller does the same thing with
        all of them and telling them apart only helps somebody probing."""
        for bad in ("", "x", "a.b", "...", "not.a.token.at.all"):
            assert sessions.verify(bad) is None

    def test_a_session_does_not_last_forever(self) -> None:
        """A token left in a shared edit suite should stop working before
        anybody gets back to it."""
        assert 0 < sessions.TTL_SECONDS <= 24 * 3600


class TestHandles:
    def test_a_handle_is_stable(self) -> None:
        """The same name tomorrow is the same person, so a guest can get back to
        the project they made yesterday."""
        assert sessions.handle_to_email("Alex Chen") == sessions.handle_to_email("alex  chen")

    def test_a_handle_is_readable_in_the_archive(self) -> None:
        """Attribution is the point. A hash would be stable and would make every
        row in the archive say nothing."""
        assert sessions.handle_to_email("Alex Chen").startswith("alex-chen@")

    def test_an_empty_handle_still_produces_an_address(self) -> None:
        assert sessions.handle_to_email("") == f"guest@{sessions.GUEST_DOMAIN}"


class TestWhatTheInterfaceIsTold:
    def test_both_doors_are_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sessions.settings, "oauth_client_id", "something.apps.googleusercontent.com")
        options = sessions.available()
        assert options["google"] and options["password"]

    def test_a_deployment_with_no_oauth_client_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The state this one shipped in. A page offering Google here draws a
        button that does nothing."""
        monkeypatch.setattr(sessions.settings, "oauth_client_id", "")
        options = sessions.available()
        assert not options["google"]
        assert options["password"]

    def test_no_code_is_ever_revealed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sessions.settings, "oauth_client_id", "x")
        rendered = str(sessions.available())
        assert GUEST not in rendered
        assert "lead-code-xyz" not in rendered


class TestTheTokenReachesThePrincipal:
    """Minting a good token and then not accepting it.

    The gap this closes was invisible from either side: `/auth/pass` returned a
    correctly signed token with the right role, and `/me` said the caller was
    anonymous. Nothing errored anywhere.

    The cause was the test that decided which kind of token had arrived —
    `not token.startswith("ey")`, on the belief that only a JWT begins that way.
    Both do: base64 of a JSON object starting `{"` is `ey` whatever follows. So
    every pass token was handed to Google's verifier, which correctly refused it.
    """

    @pytest.mark.asyncio
    async def test_a_minted_token_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import auth

        monkeypatch.setattr(auth.settings, "session_secret", SECRET)
        monkeypatch.setattr(auth.settings, "guest_pass", GUEST)
        monkeypatch.setattr(auth.settings, "team_passes", TEAM)

        token = sessions.mint(sessions.redeem(members.LEAD_EDITOR, "lead-code-xyz"))

        class Req:
            headers = {"Authorization": f"Bearer {token}"}

        principal = await auth.current_principal(Req())
        assert principal.email == members.LEAD_EDITOR
        assert principal.role == "lead"

    def test_our_token_looks_like_a_jwt_at_the_front(self) -> None:
        """The specific assumption that was wrong, pinned so nobody re-derives
        it. If this ever stops being true the discriminator can go back to a
        prefix — but it will not, because both formats are base64 of JSON."""
        token = sessions.mint(sessions.redeem("Alex", GUEST))
        assert token.startswith("ey")

    def test_our_token_has_two_segments_and_a_jwt_has_three(self) -> None:
        """What is actually load-bearing."""
        assert sessions.mint(sessions.redeem("Alex", GUEST)).count(".") == 1

    @pytest.mark.asyncio
    async def test_a_three_segment_token_is_left_for_google(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ours must not try to verify a JWT, or a real Google sign-in would be
        refused by the wrong verifier once an OAuth client exists."""
        from app import auth

        monkeypatch.setattr(auth.settings, "session_secret", SECRET)
        monkeypatch.setattr(auth.settings, "oauth_client_id", "")

        class Req:
            headers = {"Authorization": "Bearer eyJhbGc.eyJlbWFpbA.c2ln"}

        # No OAuth client configured, so it falls through to anonymous rather
        # than being mistaken for one of ours.
        assert (await auth.current_principal(Req())).is_anonymous
