"""Tests for the worker's front door.

The interesting behaviour here is not the happy path — it is what the worker
says back. The HTTP status *is* the acknowledgement, so getting it wrong does
not raise an error anywhere: a clip is quietly dropped, or one bad file is
redelivered five times and parked while the shoot waits behind it.

So these tests are almost entirely about the reply.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.worker import main as worker_main


@pytest.fixture
def client() -> TestClient:
    return TestClient(worker_main.app)


def envelope(attributes: dict[str, str] | None = None, **message) -> dict:
    body = {"message": {"messageId": "1", **message}}
    if attributes is not None:
        body["message"]["attributes"] = attributes
    return body


VALID = {
    "job_id": "6f1a1a3e-3d2b-4c1e-9a7f-1c2d3e4f5a6b",
    "clip_id": "0c9a1b2c-3d4e-5f60-8a9b-0c1d2e3f4a5b",
    "project_id": "1",
}


class TestAcknowledgement:
    def test_success_acknowledges(self, client, monkeypatch):
        async def ok(attributes):
            return True

        monkeypatch.setattr(worker_main, "handle_message", ok)
        assert client.post("/pubsub", json=envelope(VALID)).status_code == 204

    def test_failure_asks_for_redelivery(self, client, monkeypatch):
        """A 500 is the only way to say "try again". Anything in the 2xx range
        acknowledges, and the clip is gone."""

        async def failed(attributes):
            return False

        monkeypatch.setattr(worker_main, "handle_message", failed)
        assert client.post("/pubsub", json=envelope(VALID)).status_code == 500

    def test_a_clip_we_cannot_use_is_not_retried(self, client, monkeypatch):
        """handle_message returns True for a rejection, because a corrupt file
        will still be corrupt on the fifth delivery. The reason is recorded
        against the job; the message is done with."""
        seen = {}

        async def rejected(attributes):
            seen.update(attributes)
            return True

        monkeypatch.setattr(worker_main, "handle_message", rejected)
        assert client.post("/pubsub", json=envelope(VALID)).status_code == 204
        assert seen["clip_id"] == VALID["clip_id"]


class TestMalformedDelivery:
    """All of these acknowledge. None of them can succeed on a retry, and a
    message that cannot succeed but is never acknowledged occupies the
    subscription until the dead letter policy catches it."""

    def test_body_that_is_not_json(self, client, monkeypatch):
        monkeypatch.setattr(worker_main, "handle_message", _must_not_run)
        response = client.post(
            "/pubsub", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 204

    def test_no_attributes_and_no_data(self, client, monkeypatch):
        monkeypatch.setattr(worker_main, "handle_message", _must_not_run)
        assert client.post("/pubsub", json=envelope()).status_code == 204

    def test_attributes_missing_the_clip(self, client, monkeypatch):
        monkeypatch.setattr(worker_main, "handle_message", _must_not_run)
        body = envelope({"job_id": VALID["job_id"]})
        assert client.post("/pubsub", json=body).status_code == 204

    def test_attributes_missing_the_project(self, client, monkeypatch):
        """The worker builds the object path from the project id. Without one it
        looked in a prefix that cannot exist and reported the clip as never
        uploaded — blaming the upload for a fault in the queue. Rejecting the
        message names the real problem."""
        monkeypatch.setattr(worker_main, "handle_message", _must_not_run)
        body = envelope({"job_id": VALID["job_id"], "clip_id": VALID["clip_id"]})
        assert client.post("/pubsub", json=body).status_code == 204

    def test_identifier_that_is_not_a_uuid(self, client, monkeypatch):
        """Reaches handle_message, which raises ValueError parsing it. Without
        the guard in the route that would be a 500 and five redeliveries of a
        message that can never parse."""

        async def real_parse(attributes):
            raise ValueError("badly formed hexadecimal UUID string")

        monkeypatch.setattr(worker_main, "handle_message", real_parse)
        body = envelope({**VALID, "clip_id": "not-a-uuid"})
        assert client.post("/pubsub", json=body).status_code == 204


class TestEnvelopeParsing:
    def test_falls_back_to_the_data_field(self, client, monkeypatch):
        """Publishers that put the payload in data rather than attributes still
        work, so a message published by hand for debugging is processed."""
        seen = {}

        async def capture(attributes):
            seen.update(attributes)
            return True

        monkeypatch.setattr(worker_main, "handle_message", capture)
        encoded = base64.b64encode(json.dumps(VALID).encode()).decode()
        assert client.post("/pubsub", json=envelope(data=encoded)).status_code == 204
        assert seen == VALID

    def test_attributes_win_over_data(self, client, monkeypatch):
        """The publisher's contract is attributes. If the two disagree, trusting
        data would let a stale copy in the body address a different clip."""
        seen = {}

        async def capture(attributes):
            seen.update(attributes)
            return True

        monkeypatch.setattr(worker_main, "handle_message", capture)
        other = base64.b64encode(json.dumps({**VALID, "clip_id": "wrong"}).encode()).decode()
        client.post("/pubsub", json=envelope(VALID, data=other))
        assert seen["clip_id"] == VALID["clip_id"]

    def test_data_that_is_not_base64_json(self, client, monkeypatch):
        monkeypatch.setattr(worker_main, "handle_message", _must_not_run)
        assert client.post("/pubsub", json=envelope(data="%%%")).status_code == 204


def test_health_touches_nothing(client):
    """It answers during an encode, so it must not wait on a database."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["role"] == "ingest-worker"


async def _must_not_run(attributes):
    raise AssertionError(f"should not have been processed: {attributes}")
