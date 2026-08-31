"""Tests for how an upload URL gets signed.

This exists because the deployed service could not sign one at all while every
test passed. Signing needs a private key; a developer machine has one in a key
file and a Cloud Run instance has none, by design. The default code path assumes
the key is there, so the failure appeared only on a real instance, on the first
real upload, as a 500.

So these tests are about which signing path is chosen, not about the signature.
"""

from __future__ import annotations

import pytest

from app.services import storage


class FakeCredentials:
    """Stands in for whatever google.auth.default returns.

    Shaped by what the real code inspects: a local key file exposes a signer,
    the metadata server does not.
    """

    def __init__(self, *, signer=None, signer_email=None, email=None, valid=True):
        self.token = "an-access-token"
        self.valid = valid
        self.refreshed = False
        if signer is not None:
            self.signer = signer
        if signer_email is not None:
            self.signer_email = signer_email
        if email is not None:
            self.service_account_email = email

    def refresh(self, request):
        self.refreshed = True
        self.valid = True


@pytest.fixture
def credentials(monkeypatch):
    def install(creds):
        monkeypatch.setattr(storage.google.auth, "default", lambda scopes: (creds, "trimbin"))
        return creds

    return install


def test_a_local_key_file_signs_locally(credentials):
    """A key file needs no IAM call, so asking for one would add a network
    round trip and a permission requirement to every upload for nothing."""
    credentials(
        FakeCredentials(
            signer=object(), signer_email="dev@trimbin.iam.gserviceaccount.com"
        )
    )
    assert storage._signer() == {}


def test_cloud_run_signs_through_iam(credentials):
    """No signer means no key, which means the library must be told to use
    signBlob instead — which it only does when handed an email and a token."""
    creds = credentials(FakeCredentials(email="trimbin-api@trimbin.iam.gserviceaccount.com"))
    signer = storage._signer()
    assert signer["service_account_email"] == "trimbin-api@trimbin.iam.gserviceaccount.com"
    assert signer["access_token"] == creds.token


def test_an_expired_token_is_refreshed_first(credentials):
    """The token is being handed to IAM as proof of identity. A stale one is
    rejected there, and the error names the signature rather than the token."""
    creds = credentials(
        FakeCredentials(
            email="trimbin-api@trimbin.iam.gserviceaccount.com", valid=False
        )
    )
    storage._signer()
    assert creds.refreshed


def test_an_unnamed_account_is_an_error_not_a_bad_signature(credentials):
    """The metadata server answers 'default' until asked for the real address.
    Passing that through produces a signature IAM cannot attribute, and an error
    about signing rather than about identity."""
    credentials(FakeCredentials(email="default"))
    with pytest.raises(RuntimeError, match="identity"):
        storage._signer()

    credentials(FakeCredentials())
    with pytest.raises(RuntimeError, match="identity"):
        storage._signer()
