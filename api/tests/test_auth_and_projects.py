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
from app.services import members


class FakeProject:
    """Only the fields the access checks read."""

    def __init__(self, project_id: int, is_public: bool):
        self.project_id = project_id
        self.is_public = is_public
        self.owner_email = "owner@example.com"
        self.member_emails: list[str] = []


async def _public_project(project_id: int):
    return FakeProject(project_id, is_public=True)


async def _private_project(project_id: int):
    return FakeProject(project_id, is_public=False)


async def _no_such_project(project_id: int):
    return None


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
    async def test_a_configured_client_id_is_passed_to_the_verifier(self, monkeypatch) -> None:
        """The audience is the whole point of the check."""
        monkeypatch.setattr(
            auth.settings, "oauth_client_id", "our-client.apps.googleusercontent.com"
        )
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
            auth.id_token,
            "verify_oauth2_token",
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
        monkeypatch.setattr(auth.projects, "get", _no_such_project)
        with pytest.raises(HTTPException) as raised:
            await Principal(email=None).assert_can_read(7)
        assert raised.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_project_that_says_it_is_public_is_readable(self, monkeypatch) -> None:
        """The flag has to mean something, or it is a field that says one thing
        while the code does another — which is how the last two bugs here
        started. Read only: whether a public project accepts writes is a
        separate question with a separate answer."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.projects, "get", _public_project)

        await Principal(email=None).assert_can_read(3)

    @pytest.mark.asyncio
    async def test_public_does_not_mean_uploadable(self, monkeypatch) -> None:
        """The flag governs who may look, and never who may put footage in.

        It used to be tested against a single write permission that covered both
        commenting and uploading. Splitting those was the point of this release:
        a stranger on a public project may argue with every call it contains and
        may not add a frame to it.
        """
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.projects, "get", _public_project)

        with pytest.raises(HTTPException):
            await Principal(email="stranger@example.com").assert_can_upload(3)

    @pytest.mark.asyncio
    async def test_a_non_member_is_told_it_does_not_exist(self, monkeypatch) -> None:
        """404, not 403. A 403 confirms the project is real, and that is enough
        to enumerate every project on the system."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.projects, "get", _private_project)

        async def not_a_member(project_id, email):
            return False

        monkeypatch.setattr(auth.projects, "is_member", not_a_member)

        with pytest.raises(HTTPException) as raised:
            await Principal(email="stranger@example.com").assert_can_read(7)
        assert raised.value.status_code == 404
        assert "forbidden" not in raised.value.detail.lower()


class TestCommentingAndOverruling:
    """The permission that used to be membership, and narrowing it that way was
    wrong.

    An override is an additive row with a name on it: the panel verdict survives
    underneath, the archive keeps both, and the disagreement is the single most
    valuable thing in the table. Refusing a guest is refusing the evidence.
    """

    @pytest.mark.asyncio
    async def test_a_guest_may_overrule_us_on_a_public_project(self, monkeypatch) -> None:
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.projects, "get", _public_project)

        await Principal(email="a-judge@example.com").assert_can_comment(3)

    @pytest.mark.asyncio
    async def test_a_guest_may_overrule_us_on_the_demo(self, monkeypatch) -> None:
        """This is a deliberate reversal. The demo used to be read-only for
        everyone so that it stayed identical for every visitor; the product
        argument won instead. Watching somebody disagree with the system is the
        thing worth showing, and every version of every decision is kept,
        attributed, and undoable."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        await Principal(email="a-judge@example.com").assert_can_comment(1)

    @pytest.mark.asyncio
    async def test_an_anonymous_visitor_may_not(self, monkeypatch) -> None:
        """A row saying a decision was made by nobody. The whole argument of
        this system is that a decision is worth what its attribution is worth,
        so an unattributed one is worse than none."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        with pytest.raises(HTTPException) as raised:
            await Principal(email=None).assert_can_comment(1)
        assert raised.value.status_code == 401

    @pytest.mark.asyncio
    async def test_commenting_still_needs_read_access(self, monkeypatch) -> None:
        """Signed in is not the same as allowed. A private project a guest
        cannot read is a private project a guest cannot argue with."""
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        monkeypatch.setattr(auth.projects, "get", _private_project)

        async def not_a_member(project_id, email):
            return False

        monkeypatch.setattr(auth.projects, "is_member", not_a_member)

        with pytest.raises(HTTPException) as raised:
            await Principal(email="a-judge@example.com").assert_can_comment(7)
        assert raised.value.status_code == 404


class TestUploading:
    """The one thing a guest cannot do in our productions.

    Not for lack of trust. Footage costs storage, encoding and model time, and
    none of those are free.
    """

    @pytest.mark.asyncio
    async def test_a_guest_may_not_upload_into_a_company_project(self, monkeypatch) -> None:
        async def company_project(project_id):
            project = FakeProject(project_id, is_public=True)
            project.owner_email = members.LEAD_EDITOR
            return project

        monkeypatch.setattr(auth.projects, "get", company_project)

        with pytest.raises(HTTPException) as raised:
            await Principal(email="a-judge@example.com").assert_can_upload(7)
        assert raised.value.status_code == 403
        # The refusal has to say what they can do instead, or it reads as a
        # wall rather than as a rule.
        assert "your own project" in raised.value.detail.lower()

    @pytest.mark.asyncio
    async def test_a_guest_may_upload_a_bounded_sample_into_the_public_example(
        self, monkeypatch
    ) -> None:
        async def company_project(project_id):
            project = FakeProject(project_id, is_public=True)
            project.owner_email = members.LEAD_EDITOR
            return project

        monkeypatch.setattr(auth.projects, "get", company_project)
        monkeypatch.setattr(auth.settings, "demo_project_id", 1)
        await Principal(email="a-judge@example.com").assert_can_upload(1)

    @pytest.mark.asyncio
    async def test_a_guest_uploads_into_their_own_project(self, monkeypatch) -> None:
        """Inside a project they made, a guest is an editor. Without this the
        guest role is a read-only tour with extra steps."""

        async def their_project(project_id):
            project = FakeProject(project_id, is_public=False)
            project.owner_email = "a-judge@example.com"
            return project

        monkeypatch.setattr(auth.projects, "get", their_project)
        await Principal(email="a-judge@example.com").assert_can_upload(9)

    @pytest.mark.asyncio
    async def test_an_editor_uploads_into_a_company_project(self, monkeypatch) -> None:
        """Membership rows are not the only route in. A new editor on the roster
        should not be locked out of the archive they were hired to work on."""

        async def company_project(project_id):
            project = FakeProject(project_id, is_public=True)
            project.owner_email = members.LEAD_EDITOR
            return project

        monkeypatch.setattr(auth.projects, "get", company_project)
        await Principal(email=next(iter(members.EDITORS))).assert_can_upload(1)

    @pytest.mark.asyncio
    async def test_an_editor_may_not_upload_into_a_strangers_project(self, monkeypatch) -> None:
        """Being on the roster is not being on everything. A guest project is
        somebody else's work."""

        async def their_project(project_id):
            project = FakeProject(project_id, is_public=False)
            project.owner_email = "a-judge@example.com"
            return project

        monkeypatch.setattr(auth.projects, "get", their_project)

        with pytest.raises(HTTPException):
            await Principal(email=next(iter(members.EDITORS))).assert_can_upload(9)

    @pytest.mark.asyncio
    async def test_an_anonymous_visitor_may_not_upload_anywhere(self, monkeypatch) -> None:
        with pytest.raises(HTTPException) as raised:
            await Principal(email=None).assert_can_upload(1)
        assert raised.value.status_code == 401


class TestWriteAccess:
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
