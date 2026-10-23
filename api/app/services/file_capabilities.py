"""Signed, expiring and bounded upload capabilities."""

import base64
import hashlib
import hmac
import json
import time

from ..config import settings


def issue_upload(path, maximum, expires):
    if len(settings.session_secret) < 32:
        raise ValueError("Session signing is not configured")
    payload = (
        base64.urlsafe_b64encode(json.dumps([path, maximum, expires]).encode()).decode().rstrip("=")
    )
    signature = hmac.new(
        settings.session_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return payload + "." + signature


def verify_upload(token):
    if len(settings.session_secret) < 32:
        raise ValueError("Session signing is not configured")
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(
        settings.session_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid upload capability")
    path, maximum, expires = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    if time.time() >= expires or maximum <= 0:
        raise ValueError("Upload capability expired")
    return path, maximum
