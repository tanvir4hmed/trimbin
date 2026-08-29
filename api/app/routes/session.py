"""Signing in.

Two doors, and the interface asks which are open rather than guessing.

Google Sign-In is the one an editor uses. It needs an OAuth client, and an OAuth
client can only be created by hand in a console — there is no API for it. This
deployment ran for a week without that step, which meant every screen behind
sign-in was unreachable: the dashboard, the queue, overrides, comments, guest
projects. All of it built, none of it openable.

So there is a pass. Somebody types a handle and a code and the API mints a
session of its own. It is not a fallback that degrades anything — a pass session
is a real session with a real identity and a real role.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..services import sessions

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# A guest pass is meant to be shared, so the only thing standing between a bot
# and a stream of attempts is this. Per-address, in memory, deliberately crude:
# an instance restart clears it and Cloud Run runs several, so it is a speed
# bump rather than a lock. The lock is that a guest can do nothing destructive.
MAX_ATTEMPTS = 12
WINDOW_S = 300

_attempts: dict[str, list[float]] = {}


class PassRequest(BaseModel):
    # An editor types their address; a guest types the name they want their
    # decisions recorded against. Either way it is the identity, which is why
    # it is not optional.
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@router.get("/options")
async def options() -> dict:
    """Which ways in exist on this deployment.

    Asked before a sign-in screen is drawn. A page offering Google where there is
    no OAuth client is a button that does nothing; a page hiding the pass where
    there is one is a door nobody finds. Neither reveals a code.
    """
    return sessions.available()


@router.post("/pass")
async def redeem_pass(
    body: PassRequest,
    request: Request,
    response: Response,
) -> dict:
    """Turn a username and password into a session token.

    The refusal says only that the pair did not match. Distinguishing "no such
    user" from "right user, wrong password" would tell somebody probing which
    half they had already got right.
    """
    caller = _caller(request)
    if not _within_rate_limit(caller):
        log.info("rate limited pass attempts from %s", caller)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Wait five minutes.",
            headers={"Retry-After": str(WINDOW_S)},
        )

    try:
        session = sessions.redeem(body.username, body.password)
    except sessions.NotConfigured as exc:
        # A deployment that cannot sign a token is a configuration mistake, and
        # saying so is more useful than a generic refusal — nobody typing a code
        # can fix it, but the person reading the logs can.
        log.error("%s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Password sign-in is not configured on this deployment.",
        ) from exc
    except sessions.BadPass as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    # Not cached anywhere, by anything.
    response.headers["Cache-Control"] = "no-store"

    return {
        "token": sessions.mint(session),
        "email": session.email,
        "name": session.name,
        "role": session.role,
        "expires_at": session.expires_at,
    }


def _caller(request: Request) -> str:
    """The address, as far as it can be known.

    Behind Cloud Run and a load balancer the socket peer is Google's
    infrastructure, so the client is the first entry in X-Forwarded-For. That
    header is client-settable on a direct connection, which is why this is a
    speed bump and not a security control.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _within_rate_limit(caller: str) -> bool:
    now = time.time()
    recent = [t for t in _attempts.get(caller, []) if now - t < WINDOW_S]
    recent.append(now)
    _attempts[caller] = recent

    # Bounded, so a stream of distinct addresses cannot grow this without end.
    if len(_attempts) > 5000:
        _attempts.clear()

    return len(recent) <= MAX_ATTEMPTS
