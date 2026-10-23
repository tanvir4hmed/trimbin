"""Upload grants must reject tampering, expiration and unbounded uploads."""

import time

import pytest

from app.services import file_capabilities as grants


@pytest.fixture(autouse=True)
def signing(monkeypatch):
    monkeypatch.setattr(
        grants.settings, "session_secret", "unit-test-secret-with-at-least-32-characters"
    )


def test_roundtrip_is_scoped_to_object_and_size():
    token = grants.issue_upload("p7/clip/original.mov", 1234, time.time() + 30)
    assert grants.verify_upload(token) == ("p7/clip/original.mov", 1234)


def test_modified_payload_is_refused():
    token = grants.issue_upload("p7/clip/original.mov", 1234, time.time() + 30)
    with pytest.raises(ValueError):
        grants.verify_upload("x" + token[1:])


def test_expired_upload_is_refused():
    with pytest.raises(ValueError, match="expired"):
        grants.verify_upload(grants.issue_upload("p7/clip/a", 1, time.time() - 1))


def test_unbounded_upload_is_refused():
    with pytest.raises(ValueError):
        grants.verify_upload(grants.issue_upload("p7/clip/a", 0, time.time() + 30))
