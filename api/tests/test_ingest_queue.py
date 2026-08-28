"""What a queued ingest message has to carry.

The worker reconstructs the object path from the message, so anything the
message leaves out becomes a lookup in a place that does not exist. That failed
once already, and it failed in the least useful way available: the clip was
reported as never uploaded, which sent the investigation to the browser.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.services import jobs


class FakePublisher:
    def __init__(self):
        self.published = []

    def topic_path(self, project, topic):
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic, data, **attributes):
        self.published.append((topic, data, attributes))


@pytest.fixture
def publisher(monkeypatch):
    fake = FakePublisher()
    monkeypatch.setattr(jobs, "publisher", lambda: fake)
    return fake


JOB = UUID("4b86f101-4d0a-44a2-a87d-ad3ca9ada835")
CLIPS = [
    UUID("5d39fad2-92d3-4ebb-a2a2-9cf47ef3b253"),
    UUID("0c9a1b2c-3d4e-5f60-8a9b-0c1d2e3f4a5b"),
]


@pytest.mark.asyncio
async def test_every_message_names_its_project(publisher):
    """Not a convenience field. It is half the object path."""
    await jobs.enqueue_ingest(job_id=JOB, project_id=7, clip_ids=CLIPS)

    assert len(publisher.published) == 2
    for _, _, attributes in publisher.published:
        assert attributes["project_id"] == "7"
        assert attributes["job_id"] == str(JOB)


@pytest.mark.asyncio
async def test_one_message_per_clip(publisher):
    """A batch message would let one unreadable file fail the other 199, and
    make a retry re-run the whole shoot day."""
    await jobs.enqueue_ingest(job_id=JOB, project_id=7, clip_ids=CLIPS)

    sent = {a["clip_id"] for _, _, a in publisher.published}
    assert sent == {str(c) for c in CLIPS}


@pytest.mark.asyncio
async def test_attributes_are_strings(publisher):
    """Pub/Sub rejects non-string attribute values at publish time, which would
    surface as a failed upload rather than a type error."""
    await jobs.enqueue_ingest(job_id=JOB, project_id=7, clip_ids=CLIPS[:1])

    _, _, attributes = publisher.published[0]
    assert all(isinstance(v, str) for v in attributes.values())
