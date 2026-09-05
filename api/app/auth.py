"""Who is asking, and what they may touch.

Three kinds of caller share every route: the lead editor, an editor, and a
guest — which is everybody else, including a judge with three minutes and no
intention of creating an account for us.

The rule that shapes this file is that a guest is not a spectator. They may read
our productions, comment on a shot, and overrule the panel with a reason,
because watching somebody disagree with the system is the product and a
demonstration you can only look at is a video. What they may not do is put
footage into our productions — a limit about storage and cost, not about trust.

In a project they created, a guest is an editor, upload included, under the
limits in services/members.py.

There is deliberately no development bypass. A header that grants access when an
environment variable is set is a backdoor that reaches production the first time
someone copies a deployment, and verifying a token properly is cheap enough that
the shortcut is never worth it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import settings
from .services import members, projects, sessions

log = logging.getLogger(__name__)

_request_adapter = google_requests.Request()


@dataclass(frozen=True)
class Principal:
    """The caller, and the questions worth asking about them."""

    email: str | None

    @property
    def is_anonymous(self) -> bool:
        return self.email is None

    @property
    def role(self) -> members.Role:
        return members.role_of(self.email)

    @property
    def is_staff(self) -> bool:
        return members.is_staff(self.email)

    # -- reading ------------------------------------------------------------

    async def assert_can_read(self, project_id: int) -> None:
        """Reading is allowed for members, and for anyone on a public project.

        Public projects are open on purpose: a judge with three minutes will not
        create an account, and asking them to is the difference between being
        evaluated and being skipped.

        The demo id comes from config and cannot be changed by anything a user
        does. Beyond that the project's own is_public flag decides — otherwise
        the flag would say one thing while the code did another, which is how
        the two worst bugs in this system started.
        """
        # One rule, shared with the project list, so what a guest is shown and
        # what a guest may open cannot disagree. It replaced a hardcoded
        # `demo_project_id`, which pointed at a project that had been deleted.
        if projects.open_to_readers(await projects.get(project_id)):
            return

        await self._assert_member(project_id)

    # -- saying something ---------------------------------------------------

    async def assert_can_comment(self, project_id: int) -> None:
        """A note or an override: anyone signed in, on anything they can read.

        This is the permission that used to be membership, and narrowing it that
        way was wrong. An override is an additive row with a name on it — the
        panel's verdict survives underneath, the archive keeps both, and the
        disagreement is the single most valuable thing in the table. Refusing a
        guest is refusing the evidence.

        Signed in, though. An anonymous override is a row saying a decision was
        made by nobody, and the whole argument of this system is that a decision
        is worth what its attribution is worth.
        """
        if self.is_anonymous:
            raise _unauthorised()
        await self.assert_can_read(project_id)

    # -- running the production ---------------------------------------------

    async def _owns_the_work(self, project_id: int) -> bool:
        """Whether this is their production to run.

        The owner, anyone they added, or an editor on a production the company
        owns — so a new editor is not locked out of an archive they were hired
        to work on for want of a membership row.
        """
        project = await projects.get(project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")

        email = (self.email or "").lower()
        if email == project.owner_email.lower():
            return True
        if email in {m.lower() for m in project.member_emails}:
            return True
        return bool(self.is_staff and members.is_staff(project.owner_email))

    async def assert_can_curate(self, project_id: int) -> None:
        """Running the panel, describing a shot, circling, assigning, statusing.

        This is the line between a guest and an editor, and it took a correction
        to place. A guest in our productions may read everything, say anything,
        and overrule any call we made — that last one is the whole demonstration.
        What they may not do is *run* the production: spend a model call on our
        footage, rewrite what a shot was meant to be, record what the director
        circled, put somebody's name on a shot, or declare it approved.

        Those are the editors' work on the editors' material. In a project a
        guest created, they are the editor and may do all of it.

        Deliberately the same predicate as uploading, with different wording.
        Two predicates that must agree is a bug with a comment on it.
        """
        if self.is_anonymous:
            raise _unauthorised()
        # A client is here to do the work, not watch it. This is one company's
        # tool: the guest role is the client who reviews with the editors, and
        # a review they cannot run is a review they cannot check. So on any
        # production open to readers they compare, judge, and curate exactly as
        # an editor does.
        #
        # What they may not do is destroy somebody else's material. That is not
        # enforced here, because it is not a project-wide capability — it is a
        # per-record rule, and it lives on the record: see routes/clips.py,
        # where a guest may remove only clips they uploaded themselves.
        if projects.open_to_readers(await projects.get(project_id)):
            return
        if await self._owns_the_work(project_id):
            return

        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can read this project, comment on any shot, and overrule any "
            "take it chose. Running the comparison and editing a shot's details "
            "are for the editors who own it — make your own project to do that "
            "with your footage.",
        )

    async def assert_can_upload(self, project_id: int) -> None:
        """Footage goes into our productions from the company only.

        And into anyone's own project by whoever owns it. That second clause is
        why this is not simply is_staff: a guest who made a project is an editor
        inside it, and the limits that bound the cost live in
        services/members.py rather than here.
        """
        if self.is_anonymous:
            raise _unauthorised()
        # Same rule as curate. A client checking the system needs to put a take
        # through it, and the quota in services/members.py is what bounds the
        # cost of that — not a permission that stops them trying.
        if projects.open_to_readers(await projects.get(project_id)):
            return
        if await self._owns_the_work(project_id):
            return

        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can comment on this project and overrule its calls, but "
            "uploading into it is for the editors who own it. Make your own "
            "project to work on your footage.",
        )

    async def assert_is_owner(self, project_id: int) -> None:
        """For the decisions that set other people's work aside."""
        if self.is_anonymous:
            raise _unauthorised()
        if not await projects.is_owner(project_id, self.email or ""):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only the project owner can do that.",
            )

    async def _assert_member(self, project_id: int) -> None:
        if self.is_anonymous:
            raise _unauthorised()
        if not await projects.is_member(project_id, self.email or ""):
            # Deliberately the same response as a project that does not exist.
            # Distinguishing them would let anyone enumerate which projects are
            # real by watching which ones answer differently.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")


def _unauthorised() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Sign in to do that.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_principal(request: Request) -> Principal:
    """Resolve the caller from the Authorization header, or anonymously.

    A missing or unreadable token produces an anonymous principal rather than an
    error. Whether anonymity is enough is the route's decision, and failing here
    would make every public page require a login it does not need.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return Principal(email=None)

    token = header.removeprefix("Bearer ").strip()

    # Our own session token first.
    #
    # Cheap — one HMAC, no network — and it is the only way in on a deployment
    # without an OAuth client, which is the state this one was in while every
    # screen sat behind a door nobody could open.
    #
    # Tried before Google rather than after, because a Google verification is a
    # network call and failing one on every pass-issued request would put a
    # round trip in front of every action a guest takes.
    #
    # Told apart by segment count: a JWT is header, payload and signature; ours
    # is payload and signature, because there is no algorithm to negotiate when
    # only one side ever signs.
    #
    # The first version tested `not token.startswith("ey")`, on the belief that
    # only a JWT begins that way. Both do — base64 of a JSON object starting
    # `{"` is `ey` whatever follows — so every pass token was skipped here and
    # then rejected by Google, and a sign-in that returned a perfectly good
    # token produced a caller the API considered anonymous.
    if token.count(".") == 1:
        try:
            session = sessions.verify(token)
        except sessions.NotConfigured:
            # Said once, loudly, rather than swallowed into an anonymous
            # principal. A deployment that cannot verify its own tokens is a
            # configuration mistake, not a visitor problem.
            log.error("TRIMBIN_SESSION_SECRET is unset; refusing pass sign-in.")
            session = None
        if session is not None:
            return Principal(email=session.email)

    if not settings.oauth_client_id:
        # Fail closed, not open.
        #
        # verify_oauth2_token with audience=None checks the signature and the
        # issuer and then accepts the token — so any valid Google ID token,
        # minted for any application in the world, would be honoured here. A
        # member who signed into an unrelated site with Google could have that
        # site's token replayed against us.
        #
        # Refusing every token when we cannot name our own audience is a worse
        # experience and a correct one. It is loud rather than silent because a
        # deployment that cannot authenticate anyone is a configuration mistake
        # someone has to see.
        log.error(
            "TRIMBIN_OAUTH_CLIENT_ID is not set, so no bearer token can be "
            "verified as intended for this application. Rejecting sign-in."
        )
        return Principal(email=None)

    try:
        claims = id_token.verify_oauth2_token(
            token,
            _request_adapter,
            audience=settings.oauth_client_id,
        )
    except ValueError as exc:
        # Expired, malformed, wrong audience, wrong issuer. All of them mean the
        # same thing to us and none of them should say which to the caller.
        log.info("rejected a bearer token: %s", exc)
        return Principal(email=None)

    if not claims.get("email_verified"):
        # An unverified address can be claimed by someone who does not own it,
        # and membership is by email.
        log.warning("rejected an unverified email claim")
        return Principal(email=None)

    return Principal(email=(claims.get("email") or "").lower())


async def require_signed_in(
    principal: Principal = Depends(current_principal),
) -> Principal:
    """An identity, whatever role it carries.

    Most write routes want this rather than membership: a guest signing in with
    any Google account is a legitimate caller here, and the project-level
    question is asked afterwards by the assertion that knows which project.
    """
    if principal.is_anonymous:
        raise _unauthorised()
    return principal


# The old name, aliased rather than reimplemented.
#
# It now means something it never actually checked. Leaving two functions would
# leave one of them wrong, and a route reading as if it checks membership while
# checking only sign-in is exactly the comment-shaped security this codebase has
# already been bitten by twice.
require_member = require_signed_in
