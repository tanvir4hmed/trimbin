"""Who is asking, and what they may touch.

Two kinds of caller share every route. Someone signed in works on projects they
belong to; anyone at all can read the demo project without an account, because a
system that publishes its own error rate should not put that behind a signup.

There is deliberately no development bypass. A header that grants access when an
environment variable is set is a backdoor that reaches production the first time
someone copies a deployment, and the cost of verifying a token properly is small
enough that the shortcut is never worth it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import settings
from .services import projects

log = logging.getLogger(__name__)

_request_adapter = google_requests.Request()


@dataclass(frozen=True)
class Principal:
    """The caller, and the questions worth asking about them."""

    email: str | None

    @property
    def is_anonymous(self) -> bool:
        return self.email is None

    async def assert_can_read(self, project_id: int) -> None:
        """Reading is allowed for members, and for anyone on the public projects.

        The demo and the sandbox are open on purpose: a judge with three minutes
        will not create an account, and asking them to is the difference between
        being evaluated and being skipped.
        """
        if project_id in (settings.demo_project_id, settings.sandbox_project_id):
            return
        await self._assert_member(project_id)

    async def assert_can_write(self, project_id: int) -> None:
        """Writing always needs an identity.

        Including on the demo project — it is readable by everyone precisely so
        that it stays the same for everyone, and one visitor's override would
        change what the next one sees.
        """
        if project_id == settings.sandbox_project_id:
            # The sandbox exists to be written to without an account. Its limits
            # are enforced by the route, not by identity.
            return
        await self._assert_member(project_id)

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
            # real by watching which ones say "forbidden".
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

    try:
        claims = id_token.verify_oauth2_token(
            token,
            _request_adapter,
            audience=settings.oauth_client_id or None,
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


async def require_member(
    principal: Principal = Depends(current_principal),
) -> Principal:
    """For routes that need an identity before they know which project."""
    if principal.is_anonymous:
        raise _unauthorised()
    return principal
