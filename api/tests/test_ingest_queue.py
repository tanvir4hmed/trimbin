"""What a queued ingest message has to carry.

The worker reconstructs the object path from the message, so anything the
message leaves out becomes a lookup in a place that does not exist. That failed
once already, and it failed in the least useful way available: the clip was
reported as never uploaded, which sent the investigation to the browser.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services import analysis_queue, jobs


class FakePublisher:
    def __init__(self):
        self.published = []

    def topic_path(self, project, topic):
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic, data, **attributes):
        self.published.append((topic, data, attributes))


class FakeFuture:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def result(self, timeout: int):
        if self.error:
            raise self.error
        return "message-1"


class AnalysisPublisher(FakePublisher):
    def __init__(self, error: Exception | None = None):
        super().__init__()
        self.error = error

    def publish(self, topic, data, **attributes):
        super().publish(topic, data, **attributes)
        return FakeFuture(self.error)


class Ref:
    def __init__(self):
        self.data = {}

    async def set(self, fields: dict, merge: bool = False):
        self.data = {**self.data, **fields} if merge else dict(fields)

    async def get(self, **kwargs):
        data = dict(self.data)
        return SimpleNamespace(exists=bool(data), to_dict=lambda: data)


class Collection:
    def __init__(self, docs: dict[str, Ref]):
        self.docs = docs

    def document(self, key: str):
        return self.docs.setdefault(key, Ref())


class Store:
    def __init__(self):
        self.collections: dict[str, dict[str, Ref]] = {}

    def collection(self, name: str):
        return Collection(self.collections.setdefault(name, {}))

    def transaction(self):
        return self

    def set(self, ref, fields, merge=False):
        ref.data = {**ref.data, **fields} if merge else dict(fields)

    def update(self, ref, fields):
        self.set(ref, fields, merge=True)


@pytest.fixture(autouse=True)
def transactional_double(monkeypatch):
    monkeypatch.setattr(jobs.firestore, "async_transactional", lambda fn: fn)


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


@pytest.mark.asyncio
async def test_analysis_publish_is_confirmed_and_durably_tracked(monkeypatch):
    publisher = AnalysisPublisher()
    store = Store()
    monkeypatch.setattr(jobs, "publisher", lambda: publisher)
    monkeypatch.setattr(jobs, "db", lambda: store)

    queued = await jobs.enqueue_analysis(
        7,
        [
            {
                "clip_id": CLIPS[0],
                "group_id": 12,
                "subgroup_id": 2,
                "take_no": 4,
                "duration_s": 70,
            }
        ],
    )

    assert queued == 1
    task = next(iter(store.collections[jobs.ANALYSIS_QUEUE_COLLECTION].values())).data
    assert task["state"] == "queued"
    assert task["message_id"] == "message-1"
    assert publisher.published[0][2]["task"] == "full_take_analysis"


@pytest.mark.asyncio
async def test_analysis_publish_failure_is_visible_and_not_reported_as_queued(monkeypatch):
    publisher = AnalysisPublisher(RuntimeError("permission denied"))
    store = Store()
    monkeypatch.setattr(jobs, "publisher", lambda: publisher)
    monkeypatch.setattr(jobs, "db", lambda: store)

    queued = await jobs.enqueue_analysis(
        7,
        [{"clip_id": CLIPS[0], "duration_s": 70}],
    )

    assert queued == 0
    task = next(iter(store.collections[jobs.ANALYSIS_QUEUE_COLLECTION].values())).data
    assert task["state"] == "publish_failed"
    assert "permission denied" in task["error"]


@pytest.mark.asyncio
async def test_late_publish_response_cannot_downgrade_completed_work():
    store, ref = Store(), Ref()
    assert await analysis_queue.reserve(store, ref, {"dispatch_id": "first"})
    result, worker = await analysis_queue.claim(store, ref, "first")
    assert result == "claimed"
    assert await analysis_queue.advance(store, ref, "first", worker, "completed")
    await analysis_queue.published(store, ref, "first", message_id="late-message")
    assert ref.data["state"] == "completed"


@pytest.mark.asyncio
async def test_active_dispatch_and_worker_are_not_duplicated():
    store, ref = Store(), Ref()
    assert await analysis_queue.reserve(store, ref, {"dispatch_id": "first"})
    assert not await analysis_queue.reserve(store, ref, {"dispatch_id": "second"})
    result, worker = await analysis_queue.claim(store, ref, "first")
    assert result == "claimed"
    assert (await analysis_queue.claim(store, ref, "first"))[0] == "busy"
    assert (await analysis_queue.claim(store, ref, "old"))[0] == "obsolete"
    assert not await analysis_queue.advance(store, ref, "first", "other-worker", "completed")
    assert await analysis_queue.advance(store, ref, "first", worker, "failed", "retryable")
    assert await analysis_queue.reserve(store, ref, {"dispatch_id": "second"})
    assert (await analysis_queue.claim(store, ref, "first"))[0] == "obsolete"
