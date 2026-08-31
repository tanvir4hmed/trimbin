"""Signing somebody in without Google.

Google Sign-In needs an OAuth client, and an OAuth client can only be created by
hand in a console — there is no API for it, which is why `docs/oauth-client.md`
exists and why this deployment has spent a week with every screen behind a door
nobody could open. A product you cannot sign in to is not a product.

So there is a second way in: a pass. Somebody types a handle and a code, and the
API mints a session token of its own.

Two kinds of pass, and the difference is the whole design:

**The guest pass** is one code, shared deliberately — with a judge, in a
submission, with anyone we want to look. It grants the guest role and nothing
else. That is safe because of what a guest can do rather than because of who
holds the code: every action a guest takes is additive, attributed and
reversible. They can overrule any call we made, and the panel's verdict survives
underneath it in the archive.

**A team pass** is one code per editor. It grants that editor's own identity, so
the archive records who actually decided something. One shared team code would
have been less work and would have made every override say "one of the three of
us", which is the attribution this whole system exists to keep.

The identity a guest gets is namespaced — `someone@guest.trimbin` — so it can
never collide with a real address and can never match the roster. Without that,
a guest typing a roster address into the handle box would be handed the lead
editor's role by `role_of`, which is the obvious hole and the easy one to miss.

Tokens are HMAC-signed with the standard library rather than with a JWT package.
PyJWT is present in the image, but only because google-auth happens to depend on
it — building authentication on a transitive dependency means a token format
that breaks when something unrelated changes its requirements. Forty lines of
hmac is auditable in one sitting.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass

from ..config import settings
from . import members

log = logging.getLogger(__name__)

# Long enough for a working day, short enough that a token left in a shared edit
# suite stops working before anyone gets back to it.
TTL_SECONDS = 12 * 60 * 60

# Where a pass identity lives. `.trimbin` is not a real top-level domain, so
# nothing here can ever be mistaken for a deliverable address, and no roster
# entry can ever be spelled this way.
GUEST_DOMAIN = "guest.trimbin"

_HANDLE = re.compile(r"[^a-z0-9]+")


class NotConfigured(Exception):
    """No signing secret, so no token can be minted or trusted.

    Loud rather than silent, and refusing rather than falling back. A deployment
    that cannot sign a token is a configuration mistake somebody has to see; one
    that signs with a default is a deployment anybody can forge.
    """


class BadPass(Exception):
    """The code did not match anything. Deliberately says no more than that."""


@dataclass(frozen=True)
class Session:
    email: str
    name: str
    role: str
    expires_at: int


def _secret() -> bytes:
    if not settings.session_secret:
        raise NotConfigured(
            "TRIMBIN_SESSION_SECRET is unset, so no session token can be signed "
            "or verified. Sign-in by pass is disabled."
        )
    return settings.session_secret.encode()


def handle_to_email(handle: str) -> str:
    """Turn what somebody typed into a stable, namespaced identity.

    Stable on purpose: the same handle tomorrow is the same person, so a guest
    who made a project yesterday can open it today. Two people choosing the same
    handle share an identity, which is why the form says the handle *is* the
    identity — the alternative is a random suffix per session, and then nobody
    can ever get back to their own work.

    An address typed in full is accepted and namespaced anyway, so
    `tanvir4hmed@gmail.com` becomes `tanvir4hmed-gmail-com@guest.trimbin` and
    carries no more authority than any other guest.
    """
    slug = _HANDLE.sub("-", (handle or "").strip().lower()).strip("-")[:40]
    return f"{slug or 'guest'}@{GUEST_DOMAIN}"


def _team_passes() -> dict[str, str]:
    """`email:password` pairs, parsed once per call from the secret.

    Not cached. This is read on a sign-in attempt and nowhere near a hot path,
    and a cache would mean a rotated password kept working until the instance
    was next replaced.
    """
    found: dict[str, str] = {}
    for pair in (settings.team_passes or "").split(","):
        email, _, code = pair.strip().partition(":")
        if email and code:
            found[email.strip().lower()] = code.strip()
    return found


def redeem(username: str, password: str) -> Session:
    """Turn a username and password into a session, or refuse.

    An editor is matched first, by address, and their password is compared in
    constant time. Only if no editor matches is the guest password tried — a
    guest password that happened to equal an editor's would otherwise resolve to
    a guest, which is the quiet kind of wrong.

    An editor may type the whole address or just the part before the @, because
    on a team of three nobody types "@gmail.com" twice a day.
    """
    username = (username or "").strip()
    password = (password or "").strip()
    if not password:
        raise BadPass("A password is required.")

    typed = username.lower()
    for email, known in _team_passes().items():
        if typed in (email, email.split("@")[0]):
            if hmac.compare_digest(password, known):
                role = members.role_of(email)
                log.info("sign-in: %s as %s", email, role)
                return _issue(email=email, name=email.split("@")[0], role=role)

            # A known username with the wrong password is refused here, and
            # never allowed to fall through to the guest check below.
            #
            # The first version fell through, on the reasoning that refusing at
            # this point tells somebody probing that the username is real. That
            # reasoning is worthless: the three addresses are in members.py in a
            # public repository, so there is nothing left to enumerate.
            #
            # What falling through actually bought was an editor typing their
            # own address and the *shared* guest password being signed in as a
            # guest named after themselves. It looks exactly like a successful
            # login, and every decision they make for the rest of the day is
            # attributed to `them@guest.trimbin` instead of to them — which is
            # the one thing this archive exists to get right.
            raise BadPass("That username and password did not match.")

    if settings.guest_pass and hmac.compare_digest(password, settings.guest_pass.strip()):
        if not username:
            raise BadPass("Choose a name so your decisions are recorded against it.")
        email = handle_to_email(username)
        # The role is forced, never derived from what was typed. `role_of` reads
        # an address against the roster, and the namespacing above already makes
        # a match impossible — this is the second lock on the same door, because
        # the first one is a string format and string formats get edited.
        log.info("guest sign-in: %s", email)
        return _issue(email=email, name=username[:60], role="guest")

    log.info("rejected a sign-in for %r", username[:40])
    raise BadPass("That username and password did not match.")


def _issue(email: str, name: str, role: str) -> Session:
    return Session(
        email=email,
        name=name or email.split("@")[0],
        role=role,
        expires_at=int(time.time()) + TTL_SECONDS,
    )


def mint(session: Session) -> str:
    """A signed token the browser holds and sends back.

    Payload then signature, both base64url without padding, joined by a dot. The
    payload is readable by anyone holding the token — it describes them, so
    there is nothing in it to hide — and it is the signature that decides
    whether any of it is true.
    """
    payload = {
        "email": session.email,
        "name": session.name,
        "role": session.role,
        "exp": session.expires_at,
        # Which door this came through, so a log can tell a Google sign-in from
        # a pass without guessing from the address.
        "via": "pass",
    }
    raw = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{raw}.{_b64(_sign(raw))}"


def verify(token: str) -> Session | None:
    """The session a token stands for, or None.

    None for every kind of failure — expired, forged, malformed, unsigned —
    because the caller has the same answer for all of them and telling them
    apart is only useful to somebody probing.
    """
    try:
        raw, _, signature = (token or "").partition(".")
        if not raw or not signature:
            return None

        expected = _b64(_sign(raw))
        if not hmac.compare_digest(signature, expected):
            return None

        payload = json.loads(_unb64(raw))
        if int(payload.get("exp", 0)) < time.time():
            return None

        email = str(payload.get("email", "")).lower()
        if not email:
            return None

        # The role is re-derived from the roster rather than trusted from the
        # payload. The signature makes forgery impractical; re-deriving makes it
        # irrelevant — a token minted before somebody joined or left the team
        # follows the roster as it is now, not as it was.
        #
        # A namespaced guest address can never match the roster, so a guest
        # token cannot be promoted by this.
        return Session(
            email=email,
            name=str(payload.get("name", "")) or email.split("@")[0],
            role=members.role_of(email),
            expires_at=int(payload.get("exp", 0)),
        )
    except NotConfigured:
        raise
    except Exception:
        # Malformed input from a browser is normal, not exceptional.
        return None


def _sign(raw: str) -> bytes:
    return hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def available() -> dict:
    """Which doors are open, said without revealing a code.

    The interface asks this before drawing a sign-in screen. A page that offers
    Google on a deployment with no OAuth client is a button that does nothing,
    and a page that hides the pass on a deployment that has one is a door
    somebody never finds.
    """
    return {
        "google": bool(settings.oauth_client_id),
        "password": bool(settings.session_secret and (settings.guest_pass or settings.team_passes)),
    }
