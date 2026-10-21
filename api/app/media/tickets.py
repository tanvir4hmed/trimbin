"""Short-lived scoped playback URLs for native browser media elements."""

import base64
import hashlib
import hmac
import time

from .files import MediaError


def issue(secret: str, project: int, source: str, kind: str, expires: int | None = None) -> str:
    if len(secret) < 32:
        raise MediaError("media_sessions_not_configured")
    expires = int(time.time()) + 300 if expires is None else expires
    payload = f"media-v1/{project}/{source}/{kind}/{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{expires}." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def verify(secret: str, project: int, source: str, kind: str, token: str) -> None:
    try:
        expires = int(token.split(".", 1)[0])
        if expires <= time.time() or expires > time.time() + 301:
            raise ValueError
        expected = issue(secret, project, source, kind, expires)
        if not hmac.compare_digest(expected, token):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise MediaError("invalid_media_ticket") from exc
