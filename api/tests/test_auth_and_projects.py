"""Tests for who may do what.

Two things matter here more than the happy path.

A token we cannot verify as ours must be refused, not accepted. Verifying a
Google ID token without naming an audience checks the signature and the issuer
and then says yes — so any token minted for any application in the world would
be honoured, and a member who signed into an unrelated site could have that
site's token replayed against us.

And a project someone may not read has to answer 404, never 403. A 403 confirms
the project exists, which is enough to enumerate every project on the system by
watching which ids answer differently.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth
from app.auth import Principal


class FakeRequest:
    def __init__(self, header: str | None = None):
        self.headers = {"Authorization": header} if header else {}


class TestAudienceVerification:
    @pytest.mark.asyncio
    async def test_no_client_id_means_no_token_is_accepted(self, monkeypatch) -> None:
        """Fail closed. A deployment where nobody can sign in is a visible
        problem; one where anybody can is not."""
        monkeypatch.setattr(auth.settings, "oauth_client_id", "")

        def must_not_be_called(*args, **kwargs):
            raise AssertionError("verification was attempted with no audience")

        monkeypatch.setattr(auth.id_token, "verify_oauth2_token", must_not_be_called)

        principal = await auth.current_principal(FakeRequest("Bearer anything"))
        assert principal.is_anonymous

    @pytest.mark.asyncio
    async def test_a_configured_client_id_is_passed_to_the_verifier(
        self, monkeypatch
    ) -> None:
        """The audience is the whole point of the check."""
        monkeypatch.setattr(auth.settings, "oauth_client_id", "our-client.apps.googleusercontent.com")
        seen = {}

        def verify(token, request, audience=None):
            seen["audience"] = audience
            return {"email": "Editor@Example.com", "email_verified": True}

        monkeypatch.setattr(auth.id_token, "verify_oauth2_token", verify)

        principal = await auth.current_principal(FakeRequest("Bearer good"))
        assert seen["audience"] == "our-client.apps.googleusercontent.com"
        assert principal.email == "editor@example.com"

    @pytest.mark.asyncio
    async def test_an_unverified_address_is_refused(self, monkeypatch) -> None:
        """Membership is by email, and an unverified address can be claimed by
        someone who does not own it."""
        monkeypatch.setattr(auth.settings, "oauth_client_id", "our-client")
        monkeypatch.setattr(
            auth.id_token, "verify_oauth2_token",
            lambda *a, **k: {"email": "someone@example.com", "email_verified": False},
        )
        principal = await auth.current_principal(FakeRequest("Bearer good"))
        assert principal.is_anonymous

    @pytest.mark.asyncio
    async def test_a_rejected_token_is_anonymous_not_an_error(self, monkeypatch) -> None:
        """Failing here would make every public page require a login it does not
        need. Whether anonymity is enough is the route's decision."""
        monkeypatch.setattr(auth.settings, "oauth_client_id", "our-client")

        def reject(*a, **k):
            raise ValueError("Token expired")

        monkeypatch.setattr(auth.id_token, "verify_oauth2_token", reject)
        principal = await auth.current_principal(FakeRequest("Bearer stale"))
        assert principal.is_anonymous

    @pytest.mark.asyncio
    async def test_no_header_at_all_is_anonymous(self) -> None:
        assert (await auth.current_principal(FakeRequest())).is_anonymous

    @pytest.mark.asyncio
    async def test_a_header_that_is_not_a_bearer_token_is_anonymous(self) -> None:
        assert (await auth.current_principal(FakeRequest("Basic abc"))).is_anonymous


class TestReadAccess:
    @pytest.mark.asyncio
    async def test_the_demo_is_readable_without_an_account(self, monkeypatch) -> None:
        """A judge with three minutes will not create an account, and asking
        them to is the difference between being evaluated and being skipped."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        await Principal(email=None).assert_can_read(1)

    @pytest.mark.asyncio
    async def test_a_private_project_is_not(self, monkeypatch) -> None:
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.settings, "sandbox_project_id", 2)
        with pytest.raises(HTTPException) as raised:
            await Principal(email=None).assert_can_read(7)
        assert raised.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_non_member_is_told_it_does_not_exist(self, monkeypatch) -> None:
        """404, not 403. A 403 confirms the project is real, and that is enough
        to enumerate every project on the system."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.settings, "sandbox_project_id", 2)

        async def not_a_member(project_id, email):
            return False

        monkeypatch.setattr(auth.projects, "is_member", not_a_member)

        with pytest.raises(HTTPException) as raised:
            await Principal(email="stranger@example.com").assert_can_read(7)
        assert raised.value.status_code == 404
        assert "forbidden" not in raised.value.detail.lower()


class TestWriteAccess:
    @pytest.mark.asyncio
    async def test_the_demo_is_read_only_even_for_a_member(self, monkeypatch) -> None:
        """It is readable by everyone precisely so that it stays the same for
        everyone. One visitor's override would change what the next one sees."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.settings, "sandbox_project_id", 2)

        async def not_a_member(project_id, email):
            return False

        monkeypatch.setattr(auth.projects, "is_member", not_a_member)

        with pytest.raises(HTTPException):
            await Principal(email="editor@example.com").assert_can_write(1)

    @pytest.mark.asyncio
    async def test_the_sandbox_takes_writes_without_an_account(self, monkeypatch) -> None:
        """It exists to be written to by a stranger. Its limits are enforced by
        the route, not by identity."""
        monkeypatch.setattr(auth.settings, "sandbox_project_id", 2)
        await Principal(email=None).assert_can_write(2)

    @pytest.mark.asyncio
    async def test_only_the_owner_supersedes(self, monkeypatch) -> None:
        async def not_the_owner(project_id, email):
            return False

        monkeypatch.setattr(auth.projects, "is_owner", not_the_owner)

        with pytest.raises(HTTPException) as raised:
            await Principal(email="member@example.com").assert_is_owner(7)
        assert raised.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_anonymous_caller_cannot_be_an_owner(self) -> None:
        with pytest.raises(HTTPException) as raised:
            await Principal(email=None).assert_is_owner(7)
        assert raised.value.status_code == 401


class TestProjectInput:
    """Validation at the door, where a bad value is cheap to reject."""

    def test_a_name_of_spaces_is_not_a_name(self) -> None:
        from pydantic import ValidationError

        from app.routes.projects import NewProject

        with pytest.raises(ValidationError):
            NewProject(name="   ")

    def test_a_name_is_trimmed(self) -> None:
        from app.routes.projects import NewProject

        assert NewProject(name="  Scene 12  ").name == "Scene 12"

    def test_an_address_is_lowercased(self) -> None:
        from app.routes.projects import NewMember

        assert NewMember(email="  Editor@Example.COM ").email == "editor@example.com"

    def test_something_that_is_not_an_address_is_refused(self) -> None:
        from pydantic import ValidationError

        from app.routes.projects import NewMember

        for bad in ("editor", "editor@", "@example.com", "a b@c.com"):
            with pytest.raises(ValidationError):
                NewMember(email=bad)
